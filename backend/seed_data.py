"""
链客宝种子数据填充脚本
========================
功能: 向 chainke.db, crm.db, growth.db 填充初始数据
运行: cd D:/链客宝/backend && python seed_data.py

数据分类:
  - 10 个产品 (覆盖5个分类)
  -  5 个用户 (不同角色)
  - 15 个线索 (CRM 6阶段)
  -  3 个组织 + 成员
  -  5 条邀请记录 + 5 条积分奖励
"""

import json
import logging
import os
import secrets
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

# ── 将 backend 加入 Python 路径 ──
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from passlib.hash import bcrypt as bcrypt_hasher
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# ── 数据库路径 ──
_DATA_DIR = os.path.join(_BACKEND_DIR, "data")
os.makedirs(_DATA_DIR, exist_ok=True)

CHAINKE_DB_PATH = os.path.join(_DATA_DIR, "chainke.db")
CRM_DB_PATH = os.path.join(_DATA_DIR, "crm.db")
GROWTH_DB_PATH = os.path.join(_DATA_DIR, "growth.db")

# ── 辅助: 检查并打印 ──
_seen = set()


def log_status(entity_type: str, name: str, status: str, detail: str = ""):
    """统一输出状态行"""
    key = (entity_type, name)
    if key in _seen:
        return  # 避免重复
    _seen.add(key)
    icon = {"CREATED": "✅", "SKIPPED": "⏭️", "ERROR": "❌"}.get(status, "❓")
    parts = [f"{icon} [{entity_type:>8}] {name:<30s} {status}"]
    if detail:
        parts.append(f"  ({detail})")
    logger.info("  ".join(parts))


# ====================================================================
#  1. 主数据库 (chainke.db) — 用户 / 产品 / 组织
# ====================================================================

def seed_chainke():
    """填充 chainke.db: 用户, 产品, 组织"""
    engine = create_engine(
        f"sqlite:///{CHAINKE_DB_PATH}",
        connect_args={"check_same_thread": False},
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # 导入模型确保表已创建
    from app.database import Base
    from app.models import User, Product  # noqa
    from app.models.organization import Organization, OrganizationMember, Invite  # noqa

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # ── 2. 用户 (8 个, 含六度人脉种子) ──
        users_data = [
            {
                "username": "admin",
                "password": "admin123",
                "name": "管理员",
                "phone": "13800000000",
                "company": "链客宝科技",
                "position": "系统管理员",
                "role": "admin",
                "avatar": "https://api.dicebear.com/7.x/avataaars/svg?seed=admin",
            },
            {
                "username": "supplier",
                "password": "supplier123",
                "name": "王供应",
                "phone": "13800000001",
                "company": "优质供应链集团",
                "position": "销售总监",
                "role": "supplier",
                "avatar": "https://api.dicebear.com/7.x/avataaars/svg?seed=supplier",
            },
            {
                "username": "buyer",
                "password": "buyer123",
                "name": "李采购",
                "phone": "13800000002",
                "company": "创新科技公司",
                "position": "采购经理",
                "role": "buyer",
                "avatar": "https://api.dicebear.com/7.x/avataaars/svg?seed=buyer",
            },
            {
                "username": "partner",
                "password": "partner123",
                "name": "赵合作",
                "phone": "13800000003",
                "company": "共赢合作伙伴",
                "position": "商务总监",
                "role": "partner",
                "avatar": "https://api.dicebear.com/7.x/avataaars/svg?seed=partner",
            },
            {
                "username": "demo",
                "password": "demo123",
                "name": "演示账号",
                "phone": "13800000004",
                "company": "链客宝演示",
                "position": "演示专员",
                "role": "buyer",
                "avatar": "https://api.dicebear.com/7.x/avataaars/svg?seed=demo",
            },
            # 六度人脉测试用户 (id=6~8)
            {
                "username": "liuliu",
                "password": "liuliu123",
                "name": "刘六",
                "phone": "13800000005",
                "company": "六合科技",
                "position": "技术总监",
                "role": "buyer",
                "avatar": "https://api.dicebear.com/7.x/avataaars/svg?seed=liuliu",
            },
            {
                "username": "chenqi",
                "password": "chenqi123",
                "name": "陈七",
                "phone": "13800000006",
                "company": "七星数据",
                "position": "CEO",
                "role": "supplier",
                "avatar": "https://api.dicebear.com/7.x/avataaars/svg?seed=chenqi",
            },
            {
                "username": "zhouba",
                "password": "zhouba123",
                "name": "周八",
                "phone": "13800000007",
                "company": "八方资源",
                "position": "商务经理",
                "role": "partner",
                "avatar": "https://api.dicebear.com/7.x/avataaars/svg?seed=zhouba",
            },
        ]

        created_users = {}  # username -> User object
        for u in users_data:
            existing = db.query(User).filter(User.username == u["username"]).first()
            if existing:
                created_users[u["username"]] = existing
                log_status("USER", u["username"], "SKIPPED", f"id={existing.id}")
                continue
            pwhash = bcrypt_hasher.hash(u["password"])
            user = User(
                username=u["username"],
                password_hash=pwhash,
                name=u["name"],
                phone=u["phone"],
                company=u["company"],
                position=u["position"],
                role=u["role"],
                avatar=u["avatar"],
            )
            db.add(user)
            db.flush()
            created_users[u["username"]] = user
            log_status("USER", u["username"], "CREATED", f"id={user.id}")

        # ── 1. 产品 (10 个, 覆盖5个分类) ──
        owner_id = created_users["admin"].id
        products_data = [
            # 食品/大健康 (2)
            {
                "name": "有机红枣礼盒 500g×3袋",
                "description": "精选新疆和田有机红枣，颗颗饱满肉厚，自然甜香。礼盒装自用送礼皆宜。",
                "price": 168.00,
                "category": "食品/大健康",
                "image_url": "https://picsum.photos/seed/dates/400/300",
            },
            {
                "name": "灵芝孢子粉胶囊 90粒装",
                "description": "长白山仿野生灵芝破壁孢子粉，多糖含量≥15%，增强免疫力。",
                "price": 298.00,
                "category": "食品/大健康",
                "image_url": "https://picsum.photos/seed/lingzhi/400/300",
            },
            # SaaS/科技 (3)
            {
                "name": "智能CRM管理系统 标准版",
                "description": "全渠道客户管理、销售自动化、数据分析看板，助力企业数字化转型。",
                "price": 9980.00,
                "category": "SaaS/科技",
                "image_url": "https://picsum.photos/seed/crm/400/300",
            },
            {
                "name": "AI智能客服机器人 年费版",
                "description": "基于大模型的智能客服，支持多轮对话、知识库自动匹配，7×24小时在线。",
                "price": 5800.00,
                "category": "SaaS/科技",
                "image_url": "https://picsum.photos/seed/chatbot/400/300",
            },
            {
                "name": "企业数据中台 基础版",
                "description": "一站式数据采集、清洗、分析平台，支持100+数据源接入。",
                "price": 29800.00,
                "category": "SaaS/科技",
                "image_url": "https://picsum.photos/seed/datacenter/400/300",
            },
            # 企业服务 (2)
            {
                "name": "企业法律顾问套餐 年度",
                "description": "全年法律顾问服务，含合同审核、法律咨询、知识产权保护、劳动仲裁支持。",
                "price": 2980.00,
                "category": "企业服务",
                "image_url": "https://picsum.photos/seed/legal/400/300",
            },
            {
                "name": "财税代理记账服务 年卡",
                "description": "专业会计师团队代理记账、税务申报、企业所得税汇算清缴，小微企业首选。",
                "price": 3600.00,
                "category": "企业服务",
                "image_url": "https://picsum.photos/seed/finance/400/300",
            },
            # 消费品 (2)
            {
                "name": "智能筋膜枪 S3 Pro",
                "description": "专业级肌肉筋膜枪，6档变速，超静音设计，Type-C快充续航8小时。",
                "price": 298.00,
                "category": "消费品",
                "image_url": "https://picsum.photos/seed/massage/400/300",
            },
            {
                "name": "负离子空气净化器 家用版",
                "description": "HEPA滤芯+负离子双重净化，CADR值300m³/h，适用面积35㎡，静音低至28dB。",
                "price": 1680.00,
                "category": "消费品",
                "image_url": "https://picsum.photos/seed/airpurifier/400/300",
            },
            # 教育培训 (1)
            {
                "name": "私域社群运营实战训练营",
                "description": "21天线上实战训练营，从0到1掌握私域社群运营全流程，含直播授课+社群实操+1v1辅导。",
                "price": 1980.00,
                "category": "教育培训",
                "image_url": "https://picsum.photos/seed/training/400/300",
            },
        ]

        for p in products_data:
            existing = db.query(Product).filter(
                Product.name == p["name"],
                Product.owner_id == owner_id,
            ).first()
            if existing:
                log_status("PRODUCT", p["name"], "SKIPPED", f"id={existing.id}")
                continue
            product = Product(
                name=p["name"],
                description=p["description"],
                price=p["price"],
                earn_per_share=round(p["price"] * 0.2, 2),
                sale_price=round(p["price"] * 1.2, 2),
                category=p["category"],
                brand="链客宝",
                stock=999,
                images=json.dumps([p["image_url"]]),
                specs=json.dumps({"规格": "标准版", "产地": "中国"}),
                details=f"<h3>{p['name']}</h3><p>{p['description']}</p>",
                tags=p["category"],
                files=json.dumps([]),
                is_featured=1,
                sort_order=1,
                status="approved",
                owner_id=owner_id,
            )
            db.add(product)
            db.flush()
            log_status("PRODUCT", p["name"], "CREATED", f"id={product.id}")

        # ── 4. 组织 (3 个) ──
        orgs_data = [
            {
                "name": "测试组织A",
                "slug": "org-a",
                "owner_username": "admin",
                "members": [
                    ("admin", "admin"),
                    ("supplier", "member"),
                ],
            },
            {
                "name": "测试组织B",
                "slug": "org-b",
                "owner_username": "supplier",
                "members": [
                    ("supplier", "admin"),
                    ("partner", "member"),
                ],
            },
            {
                "name": "测试组织C",
                "slug": "org-c",
                "owner_username": "buyer",
                "members": [
                    ("buyer", "admin"),
                    ("demo", "member"),
                ],
            },
        ]

        for o in orgs_data:
            existing_org = db.query(Organization).filter(
                Organization.slug == o["slug"]
            ).first()
            if existing_org:
                log_status("ORG", o["name"], "SKIPPED", f"id={existing_org.id}")
                continue

            owner = created_users[o["owner_username"]]
            org = Organization(name=o["name"], slug=o["slug"], owner_id=owner.id)
            db.add(org)
            db.flush()

            # 添加成员
            for username, role in o["members"]:
                user = created_users[username]
                existing_member = db.query(OrganizationMember).filter(
                    OrganizationMember.org_id == org.id,
                    OrganizationMember.user_id == user.id,
                ).first()
                if existing_member:
                    continue
                member = OrganizationMember(
                    org_id=org.id,
                    user_id=user.id,
                    role=role,
                )
                db.add(member)
        db.flush()
            log_status("ORG", o["name"], "CREATED", f"id={org.id}")

        # ── 5. 六度人脉 - 用户关系边 (UserRelation) ──
        # 关系图 (双向):
        #   管理员(1) ↔ 王供应(2), 李采购(3), 刘六(6), 陈七(7)
        #   王供应(2) ↔ 赵合作(4), 刘六(6)
        #   李采购(3) ↔ 演示账号(5), 陈七(7)
        #   赵合作(4) ↔ 周八(8)
        #   演示账号(5) ↔ 周八(8)
        #   刘六(6)   ↔ 陈七(7)
        # 共同好友示例:
        #   1&2 → [6],  1&3 → [7],  2&3 → [1],  2&4 → [],  6&7 → [1],  4&5 → [8]
        relation_pairs = [
            ("admin", "supplier"),
            ("admin", "buyer"),
            ("admin", "liuliu"),
            ("admin", "chenqi"),
            ("supplier", "partner"),
            ("supplier", "liuliu"),
            ("buyer", "demo"),
            ("buyer", "chenqi"),
            ("partner", "zhouba"),
            ("demo", "zhouba"),
            ("liuliu", "chenqi"),
        ]
        # 导入 UserRelation 模型
        from app.models.six_degrees import UserRelation
        _relation_types = ["brochure", "invite", "contact", "coop", "refer"]
        import random
        for uname_a, uname_b in relation_pairs:
            user_a = created_users.get(uname_a)
            user_b = created_users.get(uname_b)
            if not user_a or not user_b:
                continue
            # 检查是否已存在
            existing_rel = db.query(UserRelation).filter(
                UserRelation.from_user_id == user_a.id,
                UserRelation.to_user_id == user_b.id,
            ).first()
            if existing_rel:
                log_status("RELATION", f"{uname_a}↔{uname_b}", "SKIPPED", f"id={existing_rel.id}")
                continue
            rel = UserRelation(
                from_user_id=user_a.id,
                to_user_id=user_b.id,
                relation_type=random.choice(_relation_types),
                trust_score=round(random.uniform(0.3, 0.9), 2),
                interaction_count=random.randint(1, 20),
                bidirectional=True,
                is_active=True,
                source="brochure",
            )
            db.add(rel)
            db.flush()
            log_status("RELATION", f"{uname_a}↔{uname_b}", "CREATED", f"id={rel.id}")

        db.commit()
        logger.info(f"  ── chainke.db 种子数据填充完成 ──")
    except Exception as e:
        db.rollback()
        logger.error(f"chainke.db 失败: {e}")
        raise
    finally:
        db.close()


# ====================================================================
#  2. CRM 数据库 (crm.db) — 线索
# ====================================================================

CRM_STAGES = [
    "new_lead",      # 新线索
    "contacted",     # 已联系
    "negotiating",   # 洽谈中
    "quotation",     # 报价中
    "closed_won",    # 已成交
    "closed_lost",   # 已流失
]

STAGE_LABELS = {
    "new_lead": "新线索",
    "contacted": "已联系",
    "negotiating": "洽谈中",
    "quotation": "报价中",
    "closed_won": "已成交",
    "closed_lost": "已流失",
}


def _init_crm_db(conn: sqlite3.Connection):
    """初始化 CRM 表结构"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS leads (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            company         TEXT NOT NULL DEFAULT '',
            phone           TEXT DEFAULT '',
            source          TEXT DEFAULT 'manual',
            stage           TEXT NOT NULL DEFAULT 'new_lead',
            assigned_to     INTEGER DEFAULT NULL,
            assigned_name   TEXT DEFAULT '',
            next_action     TEXT DEFAULT '',
            next_action_date TEXT DEFAULT NULL,
            value           REAL DEFAULT 0.0,
            notes           TEXT DEFAULT '',
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS lead_notes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id     INTEGER NOT NULL,
            user_id     INTEGER DEFAULT NULL,
            user_name   TEXT DEFAULT '',
            content     TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_leads_stage ON leads(stage);
        CREATE INDEX IF NOT EXISTS idx_leads_assigned ON leads(assigned_to);
        CREATE INDEX IF NOT EXISTS idx_lead_notes_lead ON lead_notes(lead_id);
    """)


def seed_crm():
    """填充 crm.db: 15 个线索覆盖 6 个阶段"""
    conn = sqlite3.connect(CRM_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        _init_crm_db(conn)

        now = datetime.now(timezone.utc).isoformat()

        # 检查是否已有数据
        existing = conn.execute("SELECT COUNT(*) as cnt FROM leads").fetchone()
        if existing and existing["cnt"] > 0:
            logger.info(f"  ⏭️  [CRM LEAD] crm.db 已有 {existing['cnt']} 条线索，跳过")
            return

        # ── 15 个线索, 按阶段分布 ──
        leads_data = [
            # new_lead (3)
            {
                "name": "张伟",
                "company": "云帆科技",
                "phone": "13900000001",
                "stage": "new_lead",
                "value": 50000.0,
                "notes": "通过官网注册，对CRM产品感兴趣",
                "assigned_to": 1,
                "assigned_name": "管理员",
            },
            {
                "name": "陈静",
                "company": "海创集团",
                "phone": "13900000002",
                "stage": "new_lead",
                "value": 120000.0,
                "notes": "行业展会获取名片，有意向了解企业服务",
                "assigned_to": 1,
                "assigned_name": "管理员",
            },
            {
                "name": "刘洋",
                "company": "锐思咨询",
                "phone": "13900000003",
                "stage": "new_lead",
                "value": 30000.0,
                "notes": "朋友推荐，需要法律顾问服务",
                "assigned_to": 2,
                "assigned_name": "王供应",
            },
            # contacted (3)
            {
                "name": "王芳",
                "company": "盛世传媒",
                "phone": "13900000004",
                "stage": "contacted",
                "value": 80000.0,
                "notes": "已电话沟通，对方需要定制化方案，约了下周拜访",
                "assigned_to": 2,
                "assigned_name": "王供应",
            },
            {
                "name": "赵明",
                "company": "金源实业",
                "phone": "13900000005",
                "stage": "contacted",
                "value": 200000.0,
                "notes": "通过LinkedIn找到，已加微信初步交流，对公司数据中台感兴趣",
                "assigned_to": 1,
                "assigned_name": "管理员",
            },
            {
                "name": "孙丽",
                "company": "博文教育",
                "phone": "13900000006",
                "stage": "contacted",
                "value": 15000.0,
                "notes": "咨询训练营课程，已发邮件介绍，等待回复",
                "assigned_to": 3,
                "assigned_name": "李采购",
            },
            # negotiating (3)
            {
                "name": "周强",
                "company": "天工制造",
                "phone": "13900000007",
                "stage": "negotiating",
                "value": 150000.0,
                "notes": "正在进行POC测试，技术对接顺利，预算已批",
                "assigned_to": 1,
                "assigned_name": "管理员",
            },
            {
                "name": "吴敏",
                "company": "蓝海贸易",
                "phone": "13900000008",
                "stage": "negotiating",
                "value": 45000.0,
                "notes": "已试用了两周，反馈良好，正在谈合同细节",
                "assigned_to": 2,
                "assigned_name": "王供应",
            },
            {
                "name": "郑浩",
                "company": "星辰科技",
                "phone": "13900000009",
                "stage": "negotiating",
                "value": 88000.0,
                "notes": "对方CTO直接对接，技术方案已确认，在等法务审核",
                "assigned_to": 3,
                "assigned_name": "李采购",
            },
            # quotation (2)
            {
                "name": "黄磊",
                "company": "绿叶环保",
                "phone": "13900000010",
                "stage": "quotation",
                "value": 65000.0,
                "notes": "已发送正式报价单，含3年维护费用，客户反馈价格可接受",
                "assigned_to": 1,
                "assigned_name": "管理员",
            },
            {
                "name": "林婷",
                "company": "瑞康医疗",
                "phone": "13900000011",
                "stage": "quotation",
                "value": 95000.0,
                "notes": "报价已发，等待对方内部审批，预计下周出结果",
                "assigned_to": 2,
                "assigned_name": "王供应",
            },
            # closed_won (2)
            {
                "name": "徐峰",
                "company": "鼎盛建筑",
                "phone": "13900000012",
                "stage": "closed_won",
                "value": 280000.0,
                "notes": "已签约，合同金额28万，含智能考勤+CRM系统",
                "assigned_to": 1,
                "assigned_name": "管理员",
            },
            {
                "name": "何雪",
                "company": "悦美医美",
                "phone": "13900000013",
                "stage": "closed_won",
                "value": 36000.0,
                "notes": "购买了10套AI数字名片Pro版年卡，已付款，已交付",
                "assigned_to": 3,
                "assigned_name": "李采购",
            },
            # closed_lost (2)
            {
                "name": "马超",
                "company": "恒达物流",
                "phone": "13900000014",
                "stage": "closed_lost",
                "value": 50000.0,
                "notes": "选择了竞品，价格敏感度较高，后续关注",
                "assigned_to": 2,
                "assigned_name": "王供应",
            },
            {
                "name": "胡敏",
                "company": "新锐电商",
                "phone": "13900000015",
                "stage": "closed_lost",
                "value": 20000.0,
                "notes": "公司业务调整，暂停采购计划，标记为流失",
                "assigned_to": 1,
                "assigned_name": "管理员",
            },
        ]

        for lead in leads_data:
            now_ts = datetime.now(timezone.utc).isoformat()
            cursor = conn.execute(
                """INSERT INTO leads
                   (name, company, phone, source, stage, assigned_to, assigned_name,
                    next_action, value, notes, created_at, updated_at)
                   VALUES (?, ?, ?, 'manual', ?, ?, ?, '', ?, ?, ?, ?)""",
                (
                    lead["name"],
                    lead["company"],
                    lead["phone"],
                    lead["stage"],
                    lead["assigned_to"],
                    lead["assigned_name"],
                    lead["value"],
                    lead["notes"],
                    now_ts,
                    now_ts,
                ),
            )
            lead_id = cursor.lastrowid
            # 添加一条跟进记录
            stage_label = STAGE_LABELS.get(lead["stage"], lead["stage"])
            conn.execute(
                """INSERT INTO lead_notes (lead_id, user_id, user_name, content, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (lead_id, lead["assigned_to"], lead["assigned_name"],
                 f"✅ 种子数据创建，初始阶段: {stage_label}", now_ts),
            )
            log_status("CRM LEAD", f"{lead['name']}({lead['company']})", "CREATED",
                       f"stage={lead['stage']}, id={lead_id}")

        conn.commit()
        logger.info(f"  ── crm.db 种子数据填充完成 ──")
    except Exception as e:
        conn.rollback()
        logger.error(f"crm.db 失败: {e}")
        raise
    finally:
        conn.close()


# ====================================================================
#  3. 增长引擎数据库 (growth.db) — 邀请记录 + 积分奖励
# ====================================================================

def _init_growth_db(conn: sqlite3.Connection):
    """初始化 growth.db 表结构"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS invites (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT NOT NULL UNIQUE,
            inviter_id  INTEGER NOT NULL,
            inviter_name TEXT NOT NULL DEFAULT '',
            message     TEXT NOT NULL DEFAULT '',
            accepted    INTEGER NOT NULL DEFAULT 0,
            accepted_by INTEGER,
            accepted_name TEXT DEFAULT '',
            accepted_at TEXT,
            reward_earned INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT NOT NULL,
            expires_at  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS rewards (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            points      INTEGER NOT NULL DEFAULT 0,
            source      TEXT NOT NULL DEFAULT 'invite',
            source_code TEXT DEFAULT '',
            created_at  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_invites_code ON invites(code);
        CREATE INDEX IF NOT EXISTS idx_invites_inviter ON invites(inviter_id);
        CREATE INDEX IF NOT EXISTS idx_invites_accepted_by ON invites(accepted_by);
        CREATE INDEX IF NOT EXISTS idx_rewards_user ON rewards(user_id);
    """)


def _generate_code() -> str:
    return secrets.token_hex(4)  # 8 位


def seed_growth():
    """填充 growth.db: 5 条邀请记录 + 5 条积分奖励"""
    conn = sqlite3.connect(GROWTH_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        _init_growth_db(conn)

        # 检查是否已有数据
        existing = conn.execute("SELECT COUNT(*) as cnt FROM invites").fetchone()
        if existing and existing["cnt"] > 0:
            logger.info(f"  ⏭️  [INVITE] growth.db 已有 {existing['cnt']} 条邀请，跳过")
            return

        now = datetime.now(timezone.utc)
        expires = (now + timedelta(days=30)).isoformat()

        # ── 5 条邀请记录 ──
        invites_data = [
            {"inviter_id": 1, "inviter_name": "管理员", "message": "欢迎加入链客宝！一起探索商业机会！"},
            {"inviter_id": 2, "inviter_name": "王供应", "message": "邀请您成为供应链合作伙伴"},
            {"inviter_id": 3, "inviter_name": "李采购", "message": "一起采购更优惠！"},
            {"inviter_id": 1, "inviter_name": "管理员", "message": "加入我们，获取最新产品信息"},
            {"inviter_id": 4, "inviter_name": "赵合作", "message": "合作共赢，共创未来"},
        ]

        created_codes = []
        for i, inv in enumerate(invites_data):
            code = _generate_code()
            created_codes.append(code)
            # 前3条已接受, 后2条待接受
            accepted = 1 if i < 3 else 0
            accepted_by = 3 if i == 0 else (4 if i == 1 else (5 if i == 2 else None))
            accepted_name = "李采购" if i == 0 else ("赵合作" if i == 1 else ("演示账号" if i == 2 else ""))
            accepted_at = (now - timedelta(days=i)).isoformat() if accepted else None
            reward_earned = 50 if accepted else 0

            conn.execute(
                """INSERT INTO invites
                   (code, inviter_id, inviter_name, message, accepted,
                    accepted_by, accepted_name, accepted_at, reward_earned, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (code, inv["inviter_id"], inv["inviter_name"], inv["message"],
                 accepted, accepted_by, accepted_name, accepted_at,
                 reward_earned, now.isoformat(), expires),
            )

            status_str = "ACCEPTED" if accepted else "PENDING"
            log_status("INVITE", code, "CREATED",
                       f"inviter={inv['inviter_name']}, {status_str}")

        # ── 5 条积分奖励 (前3条来自邀请接受, 后2条手工) ──
        rewards_data = [
            # 邀请人获得的奖励 (50分/条)
            {"user_id": 1, "points": 50, "source": "invite_reward", "source_code": created_codes[0]},
            {"user_id": 2, "points": 50, "source": "invite_reward", "source_code": created_codes[1]},
            {"user_id": 3, "points": 50, "source": "invite_reward", "source_code": created_codes[2]},
            # 接受者获得的奖励 (100分/条)
            {"user_id": 3, "points": 100, "source": "accept_reward", "source_code": created_codes[0]},
            {"user_id": 4, "points": 100, "source": "accept_reward", "source_code": created_codes[1]},
        ]

        for r in rewards_data:
            conn.execute(
                """INSERT INTO rewards (user_id, points, source, source_code, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (r["user_id"], r["points"], r["source"], r["source_code"], now.isoformat()),
            )
            log_status("REWARD", f"user={r['user_id']},+{r['points']}pts", "CREATED",
                       f"source={r['source']}")

        conn.commit()
        logger.info(f"  ── growth.db 种子数据填充完成 ──")
    except Exception as e:
        conn.rollback()
        logger.error(f"growth.db 失败: {e}")
        raise
    finally:
        conn.close()


# ====================================================================
#  4. seed_all — 统一入口
# ====================================================================

def seed_all():
    """执行全部种子数据填充 (幂等)"""
    print("=" * 60)
    print("  链客宝 种子数据填充")
    print("=" * 60)
    print()

    print("── 1/3 主数据库 (chainke.db: 用户/产品/组织) ──")
    seed_chainke()
    print()

    print("── 2/3 CRM数据库 (crm.db: 线索管道) ──")
    seed_crm()
    print()

    print("── 3/3 增长引擎数据库 (growth.db: 邀请/积分) ──")
    seed_growth()
    print()

    print("=" * 60)
    print("  ✅ 全部种子数据填充完成")
    print("=" * 60)


if __name__ == "__main__":
    seed_all()
