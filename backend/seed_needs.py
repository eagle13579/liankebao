"""
链客宝 — 供需种子数据填充脚本
============================
直接SQLite写入（避免ORM跨模块依赖问题）
用法: python seed_needs.py
"""

import logging
import sqlite3
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DB_PATH = "D:/链客宝/backend/data/chainke.db"

# ============================================================
# 种子数据 — 15条需求，覆盖不同品类和多个buyer用户
# ============================================================

SEED_NEEDS = [
    # --- 大健康品类 ---
    {
        "user_id": 2,  # buyer1 (张三)
        "title": "急需采购一批高品质保健品原料",
        "description": "我们是国内知名保健品品牌，现急需采购一批高品质的辅酶Q10、鱼油、益生菌原料。要求有GMP认证、第三方检测报告。月需求量约500公斤，长期合作。",
        "category": "大健康",
        "budget": "20万-50万/月",
        "region": "全国",
        "contact_name": "张三",
        "contact_phone": "13800138001",
        "status": "open",
    },
    {
        "user_id": 2,  # buyer1 (张三)
        "title": "寻找中医理疗设备供应商",
        "description": "计划开设3家中医理疗连锁店，需要采购艾灸仪、拔罐器、针灸针、推拿床等全套设备。要求质量可靠，有医疗器械注册证。首批采购预算30万。",
        "category": "大健康",
        "budget": "25万-35万",
        "region": "华东地区",
        "contact_name": "张三",
        "contact_phone": "13800138001",
        "status": "open",
    },
    {
        "user_id": 5,  # 链客测试01
        "title": "代工生产功能性饮品（益生菌/胶原蛋白）",
        "description": "自有品牌，寻找OEM/ODM工厂代工生产益生菌固体饮料和胶原蛋白肽饮品。要求有SC认证、10万级净化车间。首批订单5万盒，可长期合作。",
        "category": "大健康",
        "budget": "10万-30万",
        "region": "华南地区",
        "contact_name": "测试用户01",
        "contact_phone": "13900139001",
        "status": "open",
    },
    # --- SaaS / 科技产品 ---
    {
        "user_id": 6,  # 流程测试02
        "title": "企业级CRM系统采购",
        "description": "公司规模200人，需要一套适合B2B销售管理的CRM系统。核心需求：客户管理、销售漏斗、合同管理、数据看板。需支持私有化部署，预算15-25万。",
        "category": "科技产品",
        "budget": "15万-25万",
        "region": "全国",
        "contact_name": "流程测试",
        "contact_phone": "13700137001",
        "status": "open",
    },
    {
        "user_id": 7,  # testuser
        "title": "寻求AI客服机器人解决方案",
        "description": "电商公司日均咨询量3000+，急需接入AI智能客服机器人。要求支持多轮对话、知识库自主维护、多平台接入（网站/小程序/公众号）。支持SaaS模式。",
        "category": "科技产品",
        "budget": "5万-15万/年",
        "region": "全国",
        "contact_name": "测试用户",
        "contact_phone": "13600136001",
        "status": "open",
    },
    {
        "user_id": 2,  # buyer1 (张三)
        "title": "采购人脸识别门禁考勤一体机",
        "description": "公司总部和3个分部需要升级门禁考勤系统。需求：人脸识别+体温检测+考勤统计一体机，支持云端管理，可对接钉钉/企业微信。总需求约15台。",
        "category": "科技产品",
        "budget": "8万-12万",
        "region": "珠三角",
        "contact_name": "张三",
        "contact_phone": "13800138001",
        "status": "open",
    },
    # --- 企业服务 ---
    {
        "user_id": 5,  # 链客测试01
        "title": "寻求年度法律顾问服务",
        "description": "中型科技企业，寻求专业律所提供年度法律顾问服务。涵盖：合同审查、知识产权保护、劳动人事合规、投融资法务支持等。要求有科技行业服务经验。",
        "category": "企业服务",
        "budget": "10万-20万/年",
        "region": "上海",
        "contact_name": "测试用户01",
        "contact_phone": "13900139001",
        "status": "open",
    },
    {
        "user_id": 6,  # 流程测试02
        "title": "企业财税代账与税务筹划服务",
        "description": "年营收5000万的贸易公司，需要专业的财税代账和税务合规筹划服务。要求有一般纳税人服务经验，熟悉进出口退税业务。",
        "category": "企业服务",
        "budget": "5万-8万/年",
        "region": "广州",
        "contact_name": "流程测试",
        "contact_phone": "13700137001",
        "status": "open",
    },
    {
        "user_id": 2,  # buyer1 (张三)
        "title": "寻找数字化转型咨询与实施服务",
        "description": "传统制造企业转型需求，需要专业团队提供数字化转型咨询、ERP系统选型与实施、生产流程数字化改造。项目周期6-12个月。",
        "category": "企业服务",
        "budget": "50万-100万",
        "region": "长三角",
        "contact_name": "张三",
        "contact_phone": "13800138001",
        "status": "open",
    },
    # --- AI / 软件 ---
    {
        "user_id": 7,  # testuser
        "title": "采购AI内容生成平台（AIGC）",
        "description": "市场营销部门需要采购AIGC平台用于公众号文章生成、短视频脚本创作、图片素材生成。要求支持中文优化、品牌风格定制。团队20人使用。",
        "category": "科技产品",
        "budget": "3万-8万/年",
        "region": "全国",
        "contact_name": "测试用户",
        "contact_phone": "13600136001",
        "status": "open",
    },
    {
        "user_id": 8,  # testuser2
        "title": "需要定制开发企业AI知识库系统",
        "description": "集团内部有大量文档和知识资产需要数字化管理，需要开发一套AI驱动的企业知识库系统。核心功能：文档智能分类、语义搜索、智能问答、权限管理。支持本地化部署。",
        "category": "科技产品",
        "budget": "30万-60万",
        "region": "北京",
        "contact_name": "Test2",
        "contact_phone": "13500135001",
        "status": "open",
    },
    # --- 物流 / 供应链 ---
    {
        "user_id": 5,  # 链客测试01
        "title": "寻找冷链物流合作伙伴",
        "description": "生鲜电商平台，日均发货2000单，需要覆盖全国主要城市的冷链物流服务。要求：全程温控、次日达、损耗率<1%。长期合作需求。",
        "category": "企业服务",
        "budget": "50万-100万/月",
        "region": "全国",
        "contact_name": "测试用户01",
        "contact_phone": "13900139001",
        "status": "open",
    },
    # --- 教育培训 ---
    {
        "user_id": 6,  # 流程测试02
        "title": "采购企业在线培训平台",
        "description": "集团员工3000人，需要采购一套企业在线培训系统。需求：课程管理、考试测评、学习路径、数据统计、支持移动端学习。预算15-30万。",
        "category": "教育培训",
        "budget": "15万-30万",
        "region": "全国",
        "contact_name": "流程测试",
        "contact_phone": "13700137001",
        "status": "open",
    },
    {
        "user_id": 8,  # testuser2
        "title": "寻找企业领导力培训课程供应商",
        "description": "计划为公司中层管理人员（约50人）提供领导力提升培训。需要定制化课程，涵盖：团队管理、战略思维、跨部门协作、决策能力。线上线下结合模式。",
        "category": "教育培训",
        "budget": "10万-20万",
        "region": "深圳",
        "contact_name": "Test2",
        "contact_phone": "13500135001",
        "status": "open",
    },
    {
        "user_id": 2,  # buyer1 (张三)
        "title": "团购有机农产品礼盒（端午节福利）",
        "description": "公司端午节员工福利采购，需要500份有机农产品礼盒。内容：有机五谷杂粮+山珍干货+有机蜂蜜组合。要求品质优良、包装精美、可一件代发。",
        "category": "大健康",
        "budget": "5万-8万",
        "region": "全国",
        "contact_name": "张三",
        "contact_phone": "13800138001",
        "status": "open",
    },
]


def seed():
    """直接SQLite写入种子数据"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # 检查已有数据
        cursor.execute("SELECT count(*) FROM business_needs")
        existing = cursor.fetchone()[0]
        if existing > 0:
            logger.info(f"business_needs 表中已有 {existing} 条数据，跳过种子填充")
            # 列出已有数据
            cursor.execute("SELECT id, user_id, title, category, status FROM business_needs")
            for row in cursor.fetchall():
                logger.info(f"  [{row['id']}] uid={row['user_id']} | {row['category']} | {row['title'][:30]}")
            return

        # 验证用户
        cursor.execute("SELECT id, username, name, role FROM users")
        users = {u["id"]: u for u in cursor.fetchall()}
        for uid in sorted(set(n["user_id"] for n in SEED_NEEDS)):
            if uid in users:
                u = users[uid]
                logger.info(f"用户 id={uid} ({u['name']}, {u['role']}) — OK")
            else:
                logger.warning(f"⚠ 用户 id={uid} 不存在，跳过")

        # 插入数据
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        count = 0
        for item in SEED_NEEDS:
            if item["user_id"] not in users:
                continue

            cursor.execute(
                """INSERT INTO business_needs
                   (user_id, title, description, category, budget, region,
                    contact_name, contact_phone, status, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (
                    item["user_id"],
                    item["title"],
                    item["description"],
                    item["category"],
                    item["budget"],
                    item.get("region", ""),
                    item["contact_name"],
                    item.get("contact_phone", ""),
                    item.get("status", "open"),
                    now,
                    now,
                ),
            )
            count += 1

        conn.commit()
        logger.info(f"\n✅ 成功插入 {count} 条需求种子数据！")

        # 打印摘要
        logger.info("\n===== 需求数据摘要 =====")
        cursor.execute(
            "SELECT bn.id, bn.user_id, u.name as uname, bn.category, bn.title "
            "FROM business_needs bn LEFT JOIN users u ON bn.user_id = u.id "
            "ORDER BY bn.id"
        )
        for row in cursor.fetchall():
            logger.info(f"  [{row['id']}] {row['uname']:10s} | {row['category']:8s} | {row['title'][:30]}")

        logger.info(f"\n总计: {count} 条需求")

    except Exception as e:
        conn.rollback()
        logger.error(f"种子数据插入失败: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
