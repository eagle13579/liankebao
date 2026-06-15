"""
标准化合同模板管理服务
========================
提供预置招商加盟合同模板的加载、查询、渲染和一键发起签署功能。

模板文件存储在 data/esign_templates/ 目录下，每个模板为一个 JSON 文件。
支持 Jinja2 风格的 {{变量名}} 模板引擎进行合同文本渲染。

使用方式:
    mgr = ContractTemplateManager()
    templates = mgr.list_templates()
    contract_text = mgr.render_contract("franchise_standard", {...})
    result = mgr.sign_and_send("franchise_standard", {...}, signers=[...])
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── 模板数据目录 ────────────────────────────
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "data" / "esign_templates"

# ── 模板变量正则 ─────────────────────────────
VAR_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")

# ── Jinja2 条件块正则（简单模式，支持基础 if/endif） ──
IF_BLOCK_PATTERN = re.compile(r"\{%\s*if\s+(\w+)\s*%\}(.*?)\{%\s*endif\s*%\}", re.DOTALL)


class TemplateNotFoundError(Exception):
    """模板未找到异常"""

    pass


class TemplateValidationError(Exception):
    """模板验证异常"""

    pass


class ContractTemplate:
    """合同模板数据模型"""

    def __init__(self, data: dict[str, Any]):
        self.template_id: str = data.get("template_id", "")
        self.name: str = data.get("name", "")
        self.version: str = data.get("version", "")
        self.description: str = data.get("description", "")
        self.category: str = data.get("category", "")
        self.variables: list[dict[str, Any]] = data.get("variables", [])
        self.content_template: str = data.get("content_template", "")
        self.sign_positions: list[dict[str, Any]] = data.get("sign_positions", [])
        self.metadata: dict[str, Any] = data.get("metadata", {})

    def to_dict(self) -> dict[str, Any]:
        """序列化为可 JSON 序列化的字典"""
        return {
            "template_id": self.template_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "category": self.category,
            "variables": self.variables,
            "sign_positions": self.sign_positions,
            "metadata": self.metadata,
            # content_template 按需返回，体积较大
            "content_template_preview": self.content_template[:200] + "..."
            if len(self.content_template) > 200
            else self.content_template,
        }

    def to_dict_full(self) -> dict[str, Any]:
        """含完整 content_template 的完整序列化"""
        d = self.to_dict()
        d["content_template"] = self.content_template
        return d

    def get_required_variables(self) -> list[str]:
        """获取必填变量列表（无默认值且类型非 boolean 的变量）"""
        required = []
        for var in self.variables:
            name = var.get("name", "")
            # 只有 default 键不存在或值为 None 时才算无默认值
            has_default = "default" in var and var["default"] is not None
            var_type = var.get("type", "string")
            if not has_default and var_type != "boolean":
                required.append(name)
        return required


class ContractTemplateManager:
    """合同模板管理器——负责模板的加载、列表、渲染和一键签署"""

    def __init__(self, templates_dir: str | None = None):
        """
        初始化模板管理器

        Args:
            templates_dir: 模板目录路径（默认使用 data/esign_templates/）
        """
        self._templates_dir = Path(templates_dir) if templates_dir else TEMPLATES_DIR
        self._cache: dict[str, ContractTemplate] = {}
        self._load_all()

    # ── 内部方法 ──────────────────────────────

    def _load_all(self) -> None:
        """从目录加载所有模板文件到缓存"""
        if not self._templates_dir.exists():
            logger.warning("模板目录不存在: %s", self._templates_dir)
            return

        for fpath in sorted(self._templates_dir.glob("*.json")):
            try:
                with open(fpath, encoding="utf-8") as f:
                    data = json.load(f)
                template = ContractTemplate(data)
                if template.template_id:
                    self._cache[template.template_id] = template
                    logger.debug("已加载模板: %s (%s)", template.template_id, template.name)
                else:
                    logger.warning("模板文件缺少 template_id: %s", fpath)
            except json.JSONDecodeError as e:
                logger.error("模板文件 JSON 解析失败: %s — %s", fpath, e)
            except Exception as e:
                logger.error("加载模板文件异常: %s — %s", fpath, e)

        logger.info("模板管理器初始化完成，共加载 %d 个模板", len(self._cache))

    def _validate_variables(self, template: ContractTemplate, variables: dict[str, Any]) -> None:
        """验证填充变量是否完整（仅检查无默认值的变量）"""
        required = template.get_required_variables()
        missing = []
        for v in required:
            if v not in variables:
                missing.append(v)
            else:
                val = variables[v]
                # 布尔值 False 和数字 0 是有效值，不视为缺失
                if val is None or (isinstance(val, str) and val.strip() == ""):
                    missing.append(v)
        if missing:
            raise TemplateValidationError(f"模板 '{template.template_id}' 缺少必填变量: {', '.join(missing)}")

    def _render_jinja_like(self, template_str: str, variables: dict[str, Any]) -> str:
        """
        渲染类 Jinja2 模板

        支持:
        - {{ variable }} 变量替换
        - {% if var %}...{% endif %} 条件块（变量存在且非空时渲染）

        Args:
            template_str: 模板文本
            variables: 填充变量字典

        Returns:
            渲染后的文本
        """

        # 1. 处理条件块: {% if var %}...{% endif %}
        def _replace_if(match: re.Match) -> str:
            var_name = match.group(1)
            content = match.group(2)
            val = variables.get(var_name)
            # 判断变量是否存在且不为空
            if val is not None and val != "" and val != "0" and val is not False:
                return content
            return ""

        text = IF_BLOCK_PATTERN.sub(_replace_if, template_str)

        # 2. 处理变量替换: {{ var }}
        def _replace_var(match: re.Match) -> str:
            var_name = match.group(1)
            val = variables.get(var_name)
            if val is None:
                # 保留未填充的变量标记以便调试
                return f"{{{{{var_name}}}}}"
            return str(val)

        text = VAR_PATTERN.sub(_replace_var, text)

        return text

    # ── 公共 API ──────────────────────────────

    def load_template(self, template_id: str) -> ContractTemplate:
        """
        加载指定 ID 的模板

        Args:
            template_id: 模板 ID

        Returns:
            ContractTemplate 实例

        Raises:
            TemplateNotFoundError: 模板不存在
        """
        template = self._cache.get(template_id)
        if not template:
            # 尝试重新加载（支持热更新）
            self._load_all()
            template = self._cache.get(template_id)
        if not template:
            raise TemplateNotFoundError(f"模板未找到: {template_id}")
        return template

    def list_templates(self) -> list[dict[str, Any]]:
        """
        列出所有可用模板

        Returns:
            模板摘要信息列表（不含完整合同正文）
        """
        return [t.to_dict() for t in self._cache.values()]

    def get_template_detail(self, template_id: str) -> dict[str, Any]:
        """
        获取模板完整详情（含合同正文模板）

        Args:
            template_id: 模板 ID

        Returns:
            模板完整信息字典
        """
        template = self.load_template(template_id)
        return template.to_dict_full()

    def render_contract(self, template_id: str, variables: dict[str, Any]) -> dict[str, Any]:
        """
        填充变量生成最终合同文本

        Args:
            template_id: 模板 ID
            variables: 填充变量字典

        Returns:
            {
                "template_id": "...",
                "template_name": "...",
                "contract_text": "渲染后的合同全文",
                "variables_used": {...},
                "sign_positions": [...]
            }

        Raises:
            TemplateNotFoundError: 模板不存在
            TemplateValidationError: 必填变量缺失
        """
        template = self.load_template(template_id)
        self._validate_variables(template, variables)

        contract_text = self._render_jinja_like(template.content_template, variables)

        return {
            "template_id": template.template_id,
            "template_name": template.name,
            "contract_text": contract_text,
            "variables_used": variables,
            "sign_positions": template.sign_positions,
        }

    def sign_and_send(
        self,
        template_id: str,
        variables: dict[str, Any],
        signers: list[dict[str, Any]],
        contract_name: str = "",
        expire_days: int = 30,
        auto_archive: bool = True,
        esign_client=None,
    ) -> dict[str, Any]:
        """
        一键生成合同并通过 e签宝发起签署

        流程:
            1. 加载模板并填充变量生成合同文本
            2. 调用 e签宝创建模板（将合同文本转为 PDF）
            3. 添加签署方并发起签署流程

        Args:
            template_id: 模板 ID
            variables: 模板填充变量
            signers: 签署方列表，每项为 {
                "name": "...",
                "id_number": "...",
                "mobile": "...",
                "signer_type": "PSN_FIRM|PSN_PERSON",
                "org_name": "..."
            }
            contract_name: 合同名称（默认取模板名称）
            expire_days: 签署有效期（天）
            auto_archive: 是否自动归档
            esign_client: e签宝客户端实例（必传，用于实际发起签署）

        Returns:
            e签宝 API 返回结果

        Raises:
            TemplateNotFoundError: 模板不存在
            TemplateValidationError: 必填变量缺失
            ValueError: 缺少 e签宝客户端
        """
        if not esign_client:
            raise ValueError("请提供 e签宝客户端实例 (esign_client) 以发起签署")

        # 1. 填充变量生成合同文本
        template = self.load_template(template_id)
        self._validate_variables(template, variables)
        contract_text = self._render_jinja_like(template.content_template, variables)

        # 2. 构建合同名称
        if not contract_name:
            # 尝试使用品牌名或公司名作为合同名称前缀
            brand = variables.get("brand_name") or variables.get("project_name") or variables.get("product_name", "")
            contract_name = f"{brand}—{template.name}" if brand else template.name

        # 3. 调用 e签宝发起签署
        from app.services.esign_client import (
            EsignContractConfig,
            EsignSigner,
        )

        # 将合同文本转换为字节（后续由 esign_client 生成 PDF）
        contract_bytes = contract_text.encode("utf-8")

        # 4. 先创建模板（上传合同文档）
        fields = [{"name": k, "type": "text", "value": str(v)} for k, v in variables.items()]

        try:
            # 创建电子模板
            template_result = esign_client.create_template(
                name=contract_name,
                doc_pdf=contract_bytes,
                doc_file_name=f"{template_id}_contract.pdf",
                fields=fields,
            )
            esign_template_id = template_result.get("templateId", "")

            # 构建签署方
            esign_signers = [
                EsignSigner(
                    name=s.get("name", ""),
                    id_number=s.get("id_number", ""),
                    mobile=s.get("mobile", ""),
                    signer_type=s.get("signer_type", "PSN_PERSON"),
                    org_name=s.get("org_name", ""),
                    email=s.get("email", ""),
                )
                for s in signers
            ]

            # 构建配置并发起签署
            config = EsignContractConfig(
                template_id=esign_template_id,
                signers=esign_signers,
                fields=[],  # 已在模板中填充
                contract_name=contract_name,
                expire_days=expire_days,
                auto_archive=auto_archive,
            )

            contract_result = esign_client.create_contract(config)

            logger.info(
                "一键签署成功: template=%s, contractId=%s, signers=%d",
                template_id,
                contract_result.get("contractId", ""),
                len(signers),
            )

            return {
                "template_id": template_id,
                "contract_name": contract_name,
                "esign_template_id": esign_template_id,
                "contract_id": contract_result.get("contractId", ""),
                "sign_url": contract_result.get("signUrl", ""),
                "status": contract_result.get("status", 0),
            }

        except Exception:
            logger.exception("一键签署失败: template=%s", template_id)
            raise

    def reload(self) -> int:
        """重新加载所有模板（热更新）"""
        self._cache.clear()
        self._load_all()
        return len(self._cache)


# ── 全局单例 ──────────────────────────────────

_manager_instance: ContractTemplateManager | None = None


def get_template_manager() -> ContractTemplateManager:
    """获取模板管理器全局单例"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = ContractTemplateManager()
    return _manager_instance
