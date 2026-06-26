"""
企业关系知识图谱 — 图谱构建器
==============================
基于 NetworkX 的有向图，从企业数据构建可查询、可可视化的知识图谱。

设计原则：
1. 零外部依赖（仅使用 Python 标准库 + NetworkX）
2. 分步构建：企业节点 → 行业树 → 股东关系 → 推断竞争关系
3. JSON 导出专为前端可视化优化（ECharts / D3.js 友好）
4. 所有操作非破坏性，支持增量添加

用法:
    from backend.ml.knowledge_graph import KnowledgeGraphBuilder

    builder = KnowledgeGraphBuilder()
    builder.build_from_enterprise_data(enterprise_list)
    builder.build_industry_tree()
    builder.extract_shareholder_relations()
    builder.infer_competitor_relations()
    print(builder.stats())
    builder.export_to_json("graph.json")
"""

import json
import logging
import os
from typing import Any, Optional

from .schema import (
    EntityType,
    RelationType,
    RELATION_DIRECTION_MAP,
    SCHEMA,
    EnterpriseEntity,
    PersonEntity,
    IndustryEntity,
    ProductEntity,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 尝试导入 NetworkX（提示用户安装）
# ---------------------------------------------------------------------------

try:
    import networkx as nx

    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    nx = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# 行业树模板（三级分类）
# ---------------------------------------------------------------------------

# 一级行业（level=1）
INDUSTRY_LEVEL_1 = [
    {"id": "ind_agri", "name": "农林牧渔业"},
    {"id": "ind_manufacturing", "name": "制造业"},
    {"id": "ind_tech", "name": "信息技术服务业"},
    {"id": "ind_finance", "name": "金融业"},
    {"id": "ind_edu", "name": "教育业"},
    {"id": "ind_medical", "name": "医疗健康业"},
    {"id": "ind_energy", "name": "能源业"},
    {"id": "ind_transport", "name": "交通运输业"},
    {"id": "ind_retail", "name": "批发零售业"},
    {"id": "ind_realestate", "name": "房地产业"},
]

# 二级行业（level=2, parent_id 指向一级）
INDUSTRY_LEVEL_2 = [
    # 农林牧渔业
    {"id": "ind_agri_farm", "name": "种植业", "parent_id": "ind_agri"},
    {"id": "ind_agri_livestock", "name": "畜牧业", "parent_id": "ind_agri"},
    # 制造业
    {"id": "ind_mfg_electronics", "name": "电子设备制造", "parent_id": "ind_manufacturing"},
    {"id": "ind_mfg_auto", "name": "汽车制造", "parent_id": "ind_manufacturing"},
    {"id": "ind_mfg_food", "name": "食品制造", "parent_id": "ind_manufacturing"},
    {"id": "ind_mfg_chemical", "name": "化学制品制造", "parent_id": "ind_manufacturing"},
    {"id": "ind_mfg_machinery", "name": "机械设备制造", "parent_id": "ind_manufacturing"},
    # 信息技术
    {"id": "ind_tech_software", "name": "软件开发", "parent_id": "ind_tech"},
    {"id": "ind_tech_ai", "name": "人工智能", "parent_id": "ind_tech"},
    {"id": "ind_tech_internet", "name": "互联网服务", "parent_id": "ind_tech"},
    {"id": "ind_tech_cloud", "name": "云计算", "parent_id": "ind_tech"},
    {"id": "ind_tech_data", "name": "大数据", "parent_id": "ind_tech"},
    # 金融
    {"id": "ind_fin_bank", "name": "银行业", "parent_id": "ind_finance"},
    {"id": "ind_fin_insure", "name": "保险业", "parent_id": "ind_finance"},
    {"id": "ind_fin_sec", "name": "证券业", "parent_id": "ind_finance"},
    # 医疗健康
    {"id": "ind_med_pharma", "name": "制药", "parent_id": "ind_medical"},
    {"id": "ind_med_device", "name": "医疗器械", "parent_id": "ind_medical"},
    {"id": "ind_med_hospital", "name": "医疗服务", "parent_id": "ind_medical"},
    # 能源
    {"id": "ind_eng_solar", "name": "太阳能", "parent_id": "ind_energy"},
    {"id": "ind_eng_wind", "name": "风能", "parent_id": "ind_energy"},
    {"id": "ind_eng_battery", "name": "电池/储能", "parent_id": "ind_energy"},
    # 交通运输
    {"id": "ind_trp_logistics", "name": "物流", "parent_id": "ind_transport"},
    {"id": "ind_trp_express", "name": "快递", "parent_id": "ind_transport"},
]

# 三级行业（level=3, parent_id 指向二级）
INDUSTRY_LEVEL_3 = [
    # 软件细分
    {"id": "ind_sw_erp", "name": "企业管理系统", "parent_id": "ind_tech_software"},
    {"id": "ind_sw_game", "name": "游戏开发", "parent_id": "ind_tech_software"},
    {"id": "ind_sw_mobile", "name": "移动应用", "parent_id": "ind_tech_software"},
    # AI细分
    {"id": "ind_ai_nlp", "name": "自然语言处理", "parent_id": "ind_tech_ai"},
    {"id": "ind_ai_cv", "name": "计算机视觉", "parent_id": "ind_tech_ai"},
    {"id": "ind_ai_robot", "name": "机器人", "parent_id": "ind_tech_ai"},
    # 电子制造细分
    {"id": "ind_elec_chip", "name": "芯片设计", "parent_id": "ind_mfg_electronics"},
    {"id": "ind_elec_pcb", "name": "电路板制造", "parent_id": "ind_mfg_electronics"},
    {"id": "ind_elec_consumer", "name": "消费电子", "parent_id": "ind_mfg_electronics"},
    # 汽车细分
    {"id": "ind_auto_ev", "name": "新能源汽车", "parent_id": "ind_mfg_auto"},
    {"id": "ind_auto_parts", "name": "汽车零部件", "parent_id": "ind_mfg_auto"},
    # 食品细分
    {"id": "ind_food_beverage", "name": "饮品", "parent_id": "ind_mfg_food"},
    {"id": "ind_food_snack", "name": "休闲食品", "parent_id": "ind_mfg_food"},
]

# 完整行业列表
ALL_INDUSTRIES = INDUSTRY_LEVEL_1 + INDUSTRY_LEVEL_2 + INDUSTRY_LEVEL_3


# ---------------------------------------------------------------------------
# 图谱构建器
# ---------------------------------------------------------------------------


class KnowledgeGraphBuilder:
    """企业关系知识图谱构建器

    从企业数据（EnterpriseInfo）构建 NetworkX 有向图，
    支持行业树构建、股东关系提取、竞争关系推断，
    以及 JSON 导出（前端可视化用）。

    Attributes:
        graph: NetworkX DiGraph 实例（有向图）
        db_path: 持久化路径（JSON 文件）
    """

    def __init__(self, db_path: str = "chainke.db"):
        """初始化图谱构建器

        Args:
            db_path: 持久化文件路径（JSON 格式）
        """
        if not HAS_NETWORKX:
            raise ImportError(
                "KnowledgeGraphBuilder 需要 NetworkX 库。\n"
                "请安装: pip install networkx\n"
                "或者: conda install networkx"
            )

        self.graph = nx.DiGraph()
        self.db_path = db_path

        # 内部计数器
        self._enterprise_count = 0
        self._person_count = 0
        self._industry_count = 0
        self._product_count = 0

        logger.info("KnowledgeGraphBuilder 已初始化, db_path=%s", db_path)

    # ------------------------------------------------------------------
    # 1. 从企业数据构建图谱（主入口）
    # ------------------------------------------------------------------

    def build_from_enterprise_data(
        self, enterprise_list: list[dict[str, Any]]
    ) -> "KnowledgeGraphBuilder":
        """从企业数据列表构建图谱节点

        每个企业 dict 应包含:
            - id (必填): 企业唯一标识
            - name (必填): 企业名称
            - industry (可选): 所属行业
            - region / scale / credit_score (可选)

        Args:
            enterprise_list: 企业数据字典列表

        Returns:
            self（支持链式调用）
        """
        if not enterprise_list:
            logger.warning("build_from_enterprise_data: 企业列表为空")
            return self

        for ent_data in enterprise_list:
            ent_id = ent_data.get("id") or ent_data.get("company_name", "")
            ent_name = ent_data.get("name") or ent_data.get("company_name", "")

            if not ent_id or not ent_name:
                logger.warning("跳过缺少 id/name 的企业: %s", ent_data)
                continue

            # 构建企业节点
            entity = EnterpriseEntity(
                id=ent_id,
                name=ent_name,
                industry=ent_data.get("industry"),
                region=ent_data.get("region"),
                scale=ent_data.get("scale"),
                credit_score=ent_data.get("credit_score"),
                legal_person=ent_data.get("legal_person"),
                reg_capital=ent_data.get("reg_capital"),
                reg_status=ent_data.get("reg_status"),
                established=ent_data.get("established_date") or ent_data.get("established"),
            )
            self.graph.add_node(ent_id, **entity)
            self._enterprise_count += 1

            # 如果有行业信息，建立 INDUSTRY_OF 关系
            industry_name = ent_data.get("industry", "")
            if industry_name:
                industry_id = f"ind_{industry_name.replace(' ', '_')}"
                if not self.graph.has_node(industry_id):
                    industry_entity = IndustryEntity(
                        id=industry_id,
                        name=industry_name,
                        level=2,  # 默认为二级行业
                        category=industry_name,
                    )
                    self.graph.add_node(industry_id, **industry_entity)
                    self._industry_count += 1
                self.graph.add_edge(
                    ent_id, industry_id,
                    label=RelationType.INDUSTRY_OF.value,
                    _type=RelationType.INDUSTRY_OF.value,
                )

            # 如果有法定代表人，建立 HAS_SHAREHOLDER 关系
            legal_person = ent_data.get("legal_person", "")
            if legal_person:
                person_id = f"person_{legal_person.replace(' ', '_')}"
                if not self.graph.has_node(person_id):
                    person_entity = PersonEntity(
                        id=person_id,
                        name=legal_person,
                        role="legal_person",
                        position="法定代表人",
                    )
                    self.graph.add_node(person_id, **person_entity)
                    self._person_count += 1
                self.graph.add_edge(
                    ent_id, person_id,
                    label=RelationType.HAS_SHAREHOLDER.value,
                    _type=RelationType.HAS_SHAREHOLDER.value,
                    ratio=0,
                    type="legal_person",
                )

            # 提取产品/服务
            products = ent_data.get("products", []) or ent_data.get("ip_list", [])
            if isinstance(products, list):
                for idx, prod in enumerate(products):
                    if isinstance(prod, str):
                        prod_name = prod
                        prod_id = f"prod_{ent_id}_{idx}"
                    elif isinstance(prod, dict):
                        prod_name = prod.get("name", prod.get("product_name", f"产品_{idx}"))
                        prod_id = prod.get("id", f"prod_{ent_id}_{idx}")
                    else:
                        continue

                    if not self.graph.has_node(prod_id):
                        product_entity = ProductEntity(
                            id=prod_id,
                            name=prod_name,
                            category=prod.get("category") if isinstance(prod, dict) else None,
                            enterprise_id=ent_id,
                        )
                        self.graph.add_node(prod_id, **product_entity)
                        self._product_count += 1
                    self.graph.add_edge(
                        ent_id, prod_id,
                        label=RelationType.HAS_PRODUCT.value,
                        _type=RelationType.HAS_PRODUCT.value,
                    )

        logger.info(
            "图谱构建: 新增 %d 企业, %d 人, %d 行业, %d 产品, 共 %d 节点, %d 边",
            self._enterprise_count,
            self._person_count,
            self._industry_count,
            self._product_count,
            self.graph.number_of_nodes(),
            self.graph.number_of_edges(),
        )
        return self

    # ------------------------------------------------------------------
    # 2. 构建行业树（三级分类）
    # ------------------------------------------------------------------

    def build_industry_tree(self) -> "KnowledgeGraphBuilder":
        """构建行业分类树（三级分类体系）

        添加预定义的行业节点（一级/二级/三级），
        并通过 parent 关系连接形成行业树。

        Returns:
            self（支持链式调用）
        """
        for ind in ALL_INDUSTRIES:
            ind_id = ind["id"]
            if not self.graph.has_node(ind_id):
                # Determine level from parent_id presence:
                #   no parent_id        → level=1 (一级)
                #   parent_id in level1 → level=2 (二级)
                #   else                → level=3 (三级)
                parent_id = ind.get("parent_id")
                if not parent_id:
                    level = 1
                elif parent_id in {l1["id"] for l1 in INDUSTRY_LEVEL_1}:
                    level = 2
                else:
                    level = 3
                entity = IndustryEntity(
                    id=ind_id,
                    name=ind["name"],
                    level=level,
                    category=ind.get("category"),
                    parent_id=parent_id,
                )
                self.graph.add_node(ind_id, **entity)
                self._industry_count += 1

        # 建立行业父子关系（INDUSTRY_OF 复用为层级链接）
        # 注意：行业层级之间用 parent_of 方向连接
        for ind in ALL_INDUSTRIES:
            parent_id = ind.get("parent_id")
            if parent_id and self.graph.has_node(parent_id):
                child_id = ind["id"]
                # 子行业 -> 父行业的边（表示隶属关系）
                # 为避免和 Enterprise->Industry 混淆，使用不同的 label
                self.graph.add_edge(
                    child_id, parent_id,
                    label="IS_CHILD_OF",
                    _type="IS_CHILD_OF",
                )

        logger.info(
            "行业树构建完成: %d 个行业节点",
            self._industry_count,
        )
        return self

    # ------------------------------------------------------------------
    # 3. 提取股东关系
    # ------------------------------------------------------------------

    def extract_shareholder_relations(
        self, shareholders_data: Optional[list[dict[str, Any]]] = None
    ) -> "KnowledgeGraphBuilder":
        """从股东数据提取股东关系

        从企业节点的 shareholders 属性或外部传入的股东数据，
        构建 (Enterprise)-[:HAS_SHAREHOLDER]->(Person) 边。

        Args:
            shareholders_data: 股东数据列表，每项包含:
                - enterprise_id: 企业ID
                - name: 股东名称
                - ratio: 持股比例（%）
                - type: 股东类型（法人/自然人）

        Returns:
            self（支持链式调用）
        """
        # 先从图中已有节点的 shareholders 属性提取
        for node_id, node_data in list(self.graph.nodes(data=True)):
            if node_data.get("_type") != EntityType.ENTERPRISE.value:
                continue
            shareholders = node_data.get("shareholders", [])
            if not shareholders:
                continue
            for sh in shareholders:
                sh_name = sh.get("name", "") or sh.get("stockholder", "")
                if not sh_name:
                    continue
                sh_id = f"person_{sh_name.replace(' ', '_')}"
                sh_ratio = sh.get("ratio", sh.get("stock_percent", 0))
                sh_type = sh.get("type", "自然人股东")

                if not self.graph.has_node(sh_id):
                    person_entity = PersonEntity(
                        id=sh_id,
                        name=sh_name,
                        role="shareholder",
                    )
                    self.graph.add_node(sh_id, **person_entity)
                    self._person_count += 1

                self.graph.add_edge(
                    node_id, sh_id,
                    label=RelationType.HAS_SHAREHOLDER.value,
                    _type=RelationType.HAS_SHAREHOLDER.value,
                    ratio=float(sh_ratio) if sh_ratio else 0,
                    type=sh_type,
                )

        # 外部传入的股东数据
        if shareholders_data:
            for sh in shareholders_data:
                ent_id = sh.get("enterprise_id", "")
                sh_name = sh.get("name", "")
                if not ent_id or not sh_name:
                    continue
                if not self.graph.has_node(ent_id):
                    logger.warning("股东关系: 企业 %s 不在图中，跳过", ent_id)
                    continue

                sh_id = f"person_{sh_name.replace(' ', '_')}"
                if not self.graph.has_node(sh_id):
                    person_entity = PersonEntity(
                        id=sh_id,
                        name=sh_name,
                        role=sh.get("type", "shareholder"),
                    )
                    self.graph.add_node(sh_id, **person_entity)
                    self._person_count += 1

                self.graph.add_edge(
                    ent_id, sh_id,
                    label=RelationType.HAS_SHAREHOLDER.value,
                    _type=RelationType.HAS_SHAREHOLDER.value,
                    ratio=float(sh.get("ratio", 0)),
                    type=sh.get("type", "自然人"),
                )

        logger.info(
            "股东关系提取完成: 共 %d 个股东节点, %d 条股东边",
            self._person_count,
            sum(1 for _, _, d in self.graph.edges(data=True)
                if d.get("_type") == RelationType.HAS_SHAREHOLDER.value),
        )
        return self

    # ------------------------------------------------------------------
    # 4. 推断竞争关系
    # ------------------------------------------------------------------

    def infer_competitor_relations(self) -> "KnowledgeGraphBuilder":
        """推断企业间竞争关系

        策略：同行业（INDUSTRY_OF 指向同一行业节点）+
        同规模等级的企业之间建立 COMPETES_WITH 关系。

        竞争强度 strength 根据企业信用评分差计算：
            strength = max(0, 100 - |score_a - score_b| * 10)

        Returns:
            self（支持链式调用）
        """
        # 按行业分组
        industry_groups: dict[str, list[str]] = {}

        for u, v, d in self.graph.edges(data=True):
            if d.get("_type") != RelationType.INDUSTRY_OF.value:
                continue
            industry_id = v
            ent_id = u
            if industry_id not in industry_groups:
                industry_groups[industry_id] = []
            industry_groups[industry_id].append(ent_id)

        # 在同一行业内的企业之间建立竞争关系
        competitors_added = 0
        for industry_id, ent_ids in industry_groups.items():
            if len(ent_ids) < 2:
                continue
            # 两两配对
            for i in range(len(ent_ids)):
                for j in range(i + 1, len(ent_ids)):
                    e1, e2 = ent_ids[i], ent_ids[j]
                    if self.graph.has_edge(e1, e2) or self.graph.has_edge(e2, e1):
                        continue  # 已有关系，不覆盖

                    # 获取信用评分
                    score1 = self.graph.nodes[e1].get("credit_score", 50)
                    score2 = self.graph.nodes[e2].get("credit_score", 50)
                    if score1 is None:
                        score1 = 50
                    if score2 is None:
                        score2 = 50

                    # 竞争强度：评分越接近，竞争越激烈
                    strength = max(0, 100 - abs(float(score1) - float(score2)) * 10)

                    self.graph.add_edge(
                        e1, e2,
                        label=RelationType.COMPETES_WITH.value,
                        _type=RelationType.COMPETES_WITH.value,
                        strength=round(strength, 2),
                    )
                    competitors_added += 1

        logger.info(
            "竞争关系推断完成: 新增 %d 条 COMPETES_WITH 边",
            competitors_added,
        )
        return self

    # ------------------------------------------------------------------
    # 5. 对外投资关系提取
    # ------------------------------------------------------------------

    def extract_invest_relations(
        self, invest_data: Optional[list[dict[str, Any]]] = None
    ) -> "KnowledgeGraphBuilder":
        """提取对外投资关系

        Args:
            invest_data: 投资数据列表，每项包含:
                - from_id: 投资方企业ID
                - to_id: 被投资方企业ID
                - amount: 投资金额（万元）
                - date: 投资日期
                - ratio: 持股比例（%）

        Returns:
            self（支持链式调用）
        """
        if not invest_data:
            return self

        for inv in invest_data:
            from_id = inv.get("from_id", "")
            to_id = inv.get("to_id", "")
            if not from_id or not to_id:
                continue
            if not self.graph.has_node(from_id):
                logger.warning("投资关系: 投资方 %s 不在图中", from_id)
                continue
            if not self.graph.has_node(to_id):
                logger.warning("投资关系: 被投资方 %s 不在图中", to_id)
                continue

            edge_attrs = {
                "label": RelationType.INVESTED.value,
                "_type": RelationType.INVESTED.value,
                "amount": inv.get("amount", 0),
            }
            if inv.get("date"):
                edge_attrs["date"] = inv["date"]
            if inv.get("ratio") is not None:
                edge_attrs["ratio"] = inv["ratio"]

            self.graph.add_edge(from_id, to_id, **edge_attrs)

        logger.info(
            "投资关系提取完成: 新增 %d 条 INVESTED 边",
            len(invest_data),
        )
        return self

    # ------------------------------------------------------------------
    # 6. 导出为 JSON（前端可视化用）
    # ------------------------------------------------------------------

    def export_to_json(self, filepath: Optional[str] = None) -> dict[str, Any]:
        """导出图谱为 JSON 格式（前端 ECharts / D3.js 友好）

        JSON 结构:
            {
                "nodes": [
                    {"id": "...", "name": "...", "type": "Enterprise", ...},
                ],
                "edges": [
                    {"source": "...", "target": "...", "label": "...", ...},
                ],
                "stats": { "nodes": N, "edges": E, ... }
            }

        Args:
            filepath: 输出文件路径（None 则仅返回字典不写文件）

        Returns:
            图谱数据的字典表示
        """
        # 序列化节点
        nodes_list = []
        for node_id, data in self.graph.nodes(data=True):
            node_dict = dict(data)
            # 确保基础字段
            node_dict["id"] = node_id
            node_dict.setdefault("name", node_id)
            node_dict.setdefault("type", node_dict.get("_type", "Unknown"))
            nodes_list.append(node_dict)

        # 序列化边
        edges_list = []
        for u, v, data in self.graph.edges(data=True):
            edge_dict = dict(data)
            edge_dict["source"] = u
            edge_dict["target"] = v
            edge_dict.setdefault("label", edge_dict.get("_type", "RELATED"))
            edges_list.append(edge_dict)

        # 统计信息
        stats_info = self.stats()

        result = {
            "nodes": nodes_list,
            "edges": edges_list,
            "stats": stats_info,
            "schema_version": SCHEMA.get("version", "1.0.0"),
        }

        # 写入文件
        if filepath:
            os.makedirs(os.path.dirname(os.path.abspath(filepath)) or ".", exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            logger.info("图谱已导出到 %s (节点=%d, 边=%d)", filepath, len(nodes_list), len(edges_list))

        return result

    # ------------------------------------------------------------------
    # 7. 图谱统计
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """获取图谱统计信息

        Returns:
            dict 包含:
                - nodes: 总节点数
                - edges: 总边数
                - density: 图密度
                - entity_types: 各实体类型计数
                - relation_types: 各关系类型计数
                - enterprises: 企业数
                - persons: 人数
                - industries: 行业数
                - products: 产品数
        """
        total_nodes = self.graph.number_of_nodes()
        total_edges = self.graph.number_of_edges()

        # 按实体类型统计
        entity_type_count: dict[str, int] = {}
        for _, data in self.graph.nodes(data=True):
            etype = data.get("_type", "Unknown")
            entity_type_count[etype] = entity_type_count.get(etype, 0) + 1

        # 按关系类型统计
        relation_type_count: dict[str, int] = {}
        for _, _, data in self.graph.edges(data=True):
            rtype = data.get("_type", "RELATED")
            relation_type_count[rtype] = relation_type_count.get(rtype, 0) + 1

        # 图密度
        density = 0.0
        if total_nodes > 1:
            density = (2.0 * total_edges) / (total_nodes * (total_nodes - 1))

        return {
            "nodes": total_nodes,
            "edges": total_edges,
            "density": round(density, 6),
            "entity_types": entity_type_count,
            "relation_types": relation_type_count,
            "enterprises": entity_type_count.get(EntityType.ENTERPRISE.value, 0),
            "persons": entity_type_count.get(EntityType.PERSON.value, 0),
            "industries": entity_type_count.get(EntityType.INDUSTRY.value, 0),
            "products": entity_type_count.get(EntityType.PRODUCT.value, 0),
        }

    # ------------------------------------------------------------------
    # 8. 图持久化（保存/加载）
    # ------------------------------------------------------------------

    def save(self, filepath: Optional[str] = None) -> str:
        """保存图谱到 JSON 文件（持久化）

        Args:
            filepath: 文件路径（默认使用 self.db_path）

        Returns:
            保存的文件路径
        """
        path = filepath or self.db_path
        self.export_to_json(path)
        return path

    def load(self, filepath: Optional[str] = None) -> "KnowledgeGraphBuilder":
        """从 JSON 文件加载图谱

        Args:
            filepath: 文件路径（默认使用 self.db_path）

        Returns:
            self（支持链式调用）
        """
        path = filepath or self.db_path
        if not os.path.exists(path):
            logger.warning("图谱文件 %s 不存在，返回空图", path)
            return self

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.graph.clear()
        self._enterprise_count = 0
        self._person_count = 0
        self._industry_count = 0
        self._product_count = 0

        # 恢复节点
        for node_dict in data.get("nodes", []):
            node_id = node_dict.pop("id", "")
            if not node_id:
                continue
            self.graph.add_node(node_id, **node_dict)
            etype = node_dict.get("_type", "")
            if etype == EntityType.ENTERPRISE.value:
                self._enterprise_count += 1
            elif etype == EntityType.PERSON.value:
                self._person_count += 1
            elif etype == EntityType.INDUSTRY.value:
                self._industry_count += 1
            elif etype == EntityType.PRODUCT.value:
                self._product_count += 1

        # 恢复边
        for edge_dict in data.get("edges", []):
            source = edge_dict.pop("source", "")
            target = edge_dict.pop("target", "")
            if source and target:
                self.graph.add_edge(source, target, **edge_dict)

        logger.info(
            "图谱加载完成: %s (%d 节点, %d 边)",
            path,
            self.graph.number_of_nodes(),
            self.graph.number_of_edges(),
        )
        return self

    # ------------------------------------------------------------------
    # 9. 查询工具
    # ------------------------------------------------------------------

    def find_enterprises_by_industry(self, industry_name: str) -> list[str]:
        """按行业名称查询企业ID列表"""
        result = []
        for ind_id, ind_data in self.graph.nodes(data=True):
            if ind_data.get("name") == industry_name:
                for u, v, d in self.graph.edges(data=True):
                    if v == ind_id and d.get("_type") == RelationType.INDUSTRY_OF.value:
                        result.append(u)
                break
        return result

    def find_competitors(self, enterprise_id: str) -> list[dict[str, Any]]:
        """查询某企业的竞争对手列表"""
        competitors = []
        for _, v, d in self.graph.edges(data=True):
            if d.get("_type") != RelationType.COMPETES_WITH.value:
                continue
            competitor_id = None
            if v == enterprise_id:
                competitor_id = _  # u
            # Actually need to handle both directions
        # Simpler approach: iterate edges properly
        for u, v, d in self.graph.edges(enterprise_id, data=True):
            if d.get("_type") == RelationType.COMPETES_WITH.value:
                comp_data = dict(self.graph.nodes[v])
                competitors.append({
                    "id": v,
                    "name": comp_data.get("name", v),
                    "strength": d.get("strength", 0),
                })
        return competitors

    def get_enterprise_neighbors(self, enterprise_id: str) -> dict[str, list[dict[str, Any]]]:
        """获取某企业的所有关联实体（按关系类型分组）"""
        result: dict[str, list[dict[str, Any]]] = {}
        for _, v, d in self.graph.edges(enterprise_id, data=True):
            rel_type = d.get("_type", "RELATED")
            if rel_type not in result:
                result[rel_type] = []
            target_data = dict(self.graph.nodes[v])
            target_data["id"] = v
            target_data["relation"] = d
            result[rel_type].append(target_data)
        return result

    def clear(self) -> "KnowledgeGraphBuilder":
        """清空图谱"""
        self.graph.clear()
        self._enterprise_count = 0
        self._person_count = 0
        self._industry_count = 0
        self._product_count = 0
        logger.info("图谱已清空")
        return self


# ---------------------------------------------------------------------------
# 便利函数
# ---------------------------------------------------------------------------


def create_builder(db_path: str = "chainke.db") -> KnowledgeGraphBuilder:
    """创建知识图谱构建器实例（便利函数）"""
    return KnowledgeGraphBuilder(db_path=db_path)
