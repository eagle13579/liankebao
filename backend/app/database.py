"""
统一数据库配置与初始化
- 从环境变量 DB_TYPE 读取数据库类型：sqlite / mysql / postgres
- 回退兼容：若 DB_TYPE 未设置但 DATABASE_URL 存在，按 URL 前缀自动判断
- 所有路由模块 import from app.database 保持不变
"""

import json
import logging
import os
import urllib.parse

from passlib.hash import bcrypt as bcrypt_hasher
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

# ============================================================
# 数据库类型检测
# ============================================================
DB_TYPE = os.environ.get("DB_TYPE", "").strip().lower()
DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_POSTGRES = os.environ.get("USE_POSTGRES", "0").strip().lower() in ("1", "true", "yes")

# USE_POSTGRES=1 覆盖 DB_TYPE，强制启用 PostgreSQL
if USE_POSTGRES:
    DB_TYPE = "postgres"

# 若 DB_TYPE 未设置，尝试从 DATABASE_URL 自动判断
if not DB_TYPE:
    if DATABASE_URL:
        if DATABASE_URL.startswith("mysql"):
            DB_TYPE = "mysql"
        elif DATABASE_URL.startswith("postgresql"):
            DB_TYPE = "postgres"
        else:
            DB_TYPE = "sqlite"
    else:
        DB_TYPE = "sqlite"

logger.info(f"数据库模式: {DB_TYPE}")

# ============================================================
# 引擎创建
# ============================================================
engine = None
SessionLocal = None

if DB_TYPE == "mysql":
    if not DATABASE_URL:
        raise ValueError(
            "DB_TYPE=mysql 但未设置 DATABASE_URL 环境变量。\n"
            "示例: DATABASE_URL=mysql+pymysql://user:pass@host:port/db?charset=utf8mb4"
        )
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        echo=False,
    )

elif DB_TYPE == "postgres":
    # 优先使用 PG_URL 或 DATABASE_URL，否则用 PG_* 变量拼装
    PG_URL = os.environ.get("PG_URL", DATABASE_URL)
    if not PG_URL:
        PG_HOST = os.environ.get("PG_HOST", "localhost")
        PG_PORT = os.environ.get("PG_PORT", "5432")
        PG_USER = os.environ.get("PG_USER", "")
        PG_PASSWORD = os.environ.get("PG_PASSWORD", "")
        PG_DATABASE = os.environ.get("PG_DATABASE", "")
        if not all([PG_USER, PG_PASSWORD, PG_DATABASE]):
            raise ValueError(
                "DB_TYPE=postgres 但未设置 PG_* 或 PG_URL 环境变量。\n"
                "请设置 PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DATABASE 或 PG_URL"
            )
        PG_URL = f"postgresql+psycopg2://{urllib.parse.quote_plus(PG_USER)}:{urllib.parse.quote_plus(PG_PASSWORD)}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}"
    engine = create_engine(
        PG_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        echo=False,
    )

else:  # sqlite (default)
    DB_DIR = os.environ.get(
        "SQLITE_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"),
    )
    DB_NAME = os.environ.get("SQLITE_DB_NAME", "chainke.db")
    DB_PATH = os.path.join(DB_DIR, DB_NAME)
    os.makedirs(DB_DIR, exist_ok=True)
    SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False,
    )
    # SQLite写锁缓解：繁忙时最多等待5秒再抛异常
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    logger.info(f"SQLite 数据库路径: {DB_PATH}")

engine = engine  # 确保非 None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ===== OpenTelemetry SQLAlchemy 追踪挂载 =====
try:
    from app.telemetry import instrument_sqlalchemy

    instrument_sqlalchemy(engine)
except Exception as e:
    logger.debug(f"OpenTelemetry SQLAlchemy 追踪挂载跳过: {e}")


def get_db_url() -> str:
    """获取当前数据库连接 URL（输出屏蔽密码）"""
    if DB_TYPE == "sqlite":
        return str(engine.url)
    url_str = str(engine.url)
    # 简单脱敏
    if "@" in url_str:
        user_part, host_part = url_str.split("@", 1)
        if ":" in user_part:
            user_info = user_part.split(":", 1)[0]
            return f"{user_info}:****@{host_part}"
    return url_str


def is_multi_tenant() -> bool:
    """判断当前是否为多租户模式（仅 PostgreSQL 启用）"""
    return DB_TYPE == "postgres"


def get_db():
    """
    FastAPI依赖注入：获取数据库会话。
    - SQLite 模式: 返回普通会话（无租户过滤）
    - PostgreSQL 模式: 自动从 TenantContext 读取当前 org_id 并附加过滤
    """
    db = SessionLocal()
    try:
        if is_multi_tenant():
            # 惰性导入避免循环依赖
            from app.tenant import get_current_org_id

            org_id = get_current_org_id()
            if org_id is not None:
                # 在数据库会话上设置一个自定义属性，供查询层使用
                db.info["tenant_org_id"] = org_id
        yield db
    finally:
        db.close()


def get_db_for_tenant():
    """
    FastAPI依赖注入：显式租户感知数据库会话。
    与 get_db() 行为完全一致，但语义更清晰，建议新增路由使用此名称。
    """
    yield from get_db()


def init_db():
    """初始化数据库：创建表并填充种子数据（如为空）"""
    from app.models import (
        Order,
        Product,
        User,
        Withdrawal,
    )  # noqa

    # === 交易保障：创建 escrow 表 ===
    from app.models.escrow import Deal, Dispute, Milestone  # noqa: F401

    # === 多租户：始终创建组织相关表（SQLite + PostgreSQL 均支持） ===
    from app.models.organization import Invite, Organization, OrganizationMember  # noqa: F401

    # === 多租户：PostgreSQL 模式下创建额外租户表 ===
    if is_multi_tenant():
        try:
            from app.tenant import Membership as TenantMembership  # noqa: F401,N806
        except ImportError:
            TenantMembership = None  # noqa: F841,N806

    # === 三层信任体系：确保信任相关表被创建 ===
    from app.models import Review, TrustScore, VerificationRequest  # noqa: F401

    # === 创建表（如果不存在） ===
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # 检查是否已有数据
        existing_users = db.query(User).count()
        if existing_users > 0:
            print(f"数据库已有数据 ({existing_users}个用户)，跳过种子数据填充")
            return

        print("正在填充种子数据...")

        # 注意：不再预创建默认admin账号
        # 管理员账号应由系统所有者手动创建，避免默认密码安全风险
        pwhash_123456 = bcrypt_hasher.hash("123456")

        # === 创建用户（测试用） ===
        # 注意：不创建默认admin账号，管理员应由所有者手动创建
        users = [
            User(
                username="buyer1",
                password_hash=pwhash_123456,
                name="张三",
                phone="13800000001",
                company="创新科技有限公司",
                position="CEO",
                role="buyer",
                avatar="https://api.dicebear.com/7.x/avataaars/svg?seed=buyer1",
            ),
            User(
                username="promoter1",
                password_hash=pwhash_123456,
                name="李四",
                phone="13800000002",
                company="推广联盟",
                position="高级推广员",
                role="promoter",
                avatar="https://api.dicebear.com/7.x/avataaars/svg?seed=promoter1",
            ),
            User(
                username="supplier1",
                password_hash=pwhash_123456,
                name="王五",
                phone="13800000003",
                company="供应链集团",
                position="销售总监",
                role="supplier",
                avatar="https://api.dicebear.com/7.x/avataaars/svg?seed=supplier1",
            ),
        ]
        db.add_all(users)
        db.flush()  # 获取id

        # === 创建产品：真实商品风格 ===
        products = [
            Product(
                name="有机红枣礼盒 500g×3袋",
                description="精选新疆和田有机红枣，颗颗饱满肉厚，自然甜香。礼盒装自用送礼皆宜。严格有机认证，无添加无农残。",
                price=168.00,
                earn_per_share=25.00,
                sale_price=198.00,
                category="食品/大健康",
                brand="丝路果园",
                stock=500,
                images=json.dumps(
                    [
                        "https://picsum.photos/seed/chainke-red-dates-1/400/300",
                        "https://picsum.photos/seed/chainke-red-dates-2/400/300",
                        "https://picsum.photos/seed/chainke-red-dates-3/400/300",
                    ]
                ),
                specs=json.dumps(
                    {
                        "规格": "500g×3袋",
                        "保质期": "12个月",
                        "产地": "新疆和田",
                        "贮存条件": "阴凉干燥处",
                        "包装": "礼盒装",
                    }
                ),
                details="<h3>产品亮点</h3><ul><li>新疆和田核心产区，日照充足</li><li>国家有机认证，零添加</li><li>颗颗精选，肉厚核小</li></ul><h3>食用建议</h3><p>开袋即食，也可泡茶煮粥。每日3-5颗，健康养颜。</p>",
                tags="有机,红枣,礼盒,大健康,滋补",
                files=json.dumps(
                    [
                        {"name": "产品质检报告.pdf", "url": "/uploads/红枣质检报告.pdf", "type": "pdf"},
                        {"name": "有机认证证书.pdf", "url": "/uploads/有机认证.pdf", "type": "pdf"},
                    ]
                ),
                is_featured=1,
                sort_order=1,
                status="approved",
                owner_id=4,
            ),
            Product(
                name="AI数字名片 Pro版 年卡",
                description="基于AI技术的智能数字名片，支持多模板、AI智能推荐、人脉管理、数据统计。企业家商务社交首选，让每一次相遇都有价值。",
                price=399.00,
                earn_per_share=80.00,
                sale_price=499.00,
                category="企业家服务",
                brand="链客宝AI",
                stock=9999,
                images=json.dumps(
                    [
                        "https://picsum.photos/seed/chainke-digital-card-1/400/300",
                        "https://picsum.photos/seed/chainke-digital-card-2/400/300",
                        "https://picsum.photos/seed/chainke-digital-card-3/400/300",
                    ]
                ),
                specs=json.dumps(
                    {
                        "版本": "Pro版年卡",
                        "有效期": "购买日起365天",
                        "模板数量": "50+精选模板",
                        "AI推荐次数": "无限次",
                        "人脉容量": "10000人",
                        "数据导出": "支持Excel/CSV",
                    }
                ),
                details="<h3>核心功能</h3><ul><li>AI智能名片设计</li><li>多模板自由切换</li><li>扫码一键交换</li><li>人脉智能分类管理</li><li>交换数据分析看板</li><li>团队名片统一管理</li></ul><h3>适用人群</h3><p>企业家、销售精英、商务人士、创业者</p>",
                tags="AI,数字名片,企业家,商务,人脉管理",
                files=json.dumps(
                    [
                        {"name": "产品使用手册.pdf", "url": "/uploads/数字名片手册.pdf", "type": "pdf"},
                        {"name": "功能对比表.xlsx", "url": "/uploads/功能对比.xlsx", "type": "xlsx"},
                    ]
                ),
                is_featured=1,
                sort_order=2,
                status="approved",
                owner_id=4,
            ),
            Product(
                name="企业法律顾问套餐 年度",
                description="全年企业法律顾问服务，含合同审核、法律咨询、风险评估、知识产权保护等。专业律师团队1对1服务，企业法律问题一站式解决。",
                price=2980.00,
                earn_per_share=596.00,
                sale_price=3680.00,
                category="企业服务",
                brand="法务通",
                stock=200,
                images=json.dumps(
                    [
                        "https://picsum.photos/seed/chainke-legal-1/400/300",
                        "https://picsum.photos/seed/chainke-legal-2/400/300",
                        "https://picsum.photos/seed/chainke-legal-3/400/300",
                    ]
                ),
                specs=json.dumps(
                    {
                        "服务周期": "12个月",
                        "合同审核": "不限次数（≤10页/份）",
                        "法律咨询": "不限次数（工作日9:00-18:00）",
                        "律师分配": "3人专属服务组",
                        "响应时效": "4小时内回复",
                        "适用规模": "10-500人企业",
                    }
                ),
                details="<h3>服务内容</h3><ul><li>日常法律咨询（电话/微信/邮件）</li><li>合同起草与审核（每年50份内）</li><li>企业规章制度审查</li><li>劳动人事法律支持</li><li>知识产权基础保护</li><li>律师函发送（5次/年）</li></ul><h3>服务流程</h3><p>在线下单 → 分配律师 → 建立服务群 → 全年无忧</p>",  # noqa: E501
                tags="法律顾问,企业服务,合同审核,知识产权,法律服务",
                files=json.dumps(
                    [
                        {"name": "服务合同模板.pdf", "url": "/uploads/法律顾问合同.pdf", "type": "pdf"},
                        {"name": "服务内容清单.pdf", "url": "/uploads/服务清单.pdf", "type": "pdf"},
                    ]
                ),
                is_featured=1,
                sort_order=3,
                status="approved",
                owner_id=4,
            ),
            Product(
                name="筋膜枪 肌肉放松 静音款",
                description="专业级肌肉筋膜枪，6档变速调节，超静音设计。运动后肌肉放松、日常疲劳缓解。Type-C快充，续航8小时。",
                price=298.00,
                earn_per_share=58.00,
                sale_price=368.00,
                category="大健康",
                brand="舒肌宝",
                stock=1000,
                images=json.dumps(
                    [
                        "https://picsum.photos/seed/chainke-massage-gun-1/400/300",
                        "https://picsum.photos/seed/chainke-massage-gun-2/400/300",
                        "https://picsum.photos/seed/chainke-massage-gun-3/400/300",
                    ]
                ),
                specs=json.dumps(
                    {
                        "型号": "S3 Pro",
                        "档位": "6档变速（1200-3200转/分）",
                        "噪音": "≤35dB（静音款）",
                        "电池": "2600mAh锂电池",
                        "续航": "约8小时",
                        "充电": "Type-C快充（2小时充满）",
                        "配件": "6种按摩头",
                        "重量": "约680g",
                    }
                ),
                details="<h3>产品特点</h3><ul><li>超静音电机，使用不扰人</li><li>6档智能变速，满足不同需求</li><li>6种专业按摩头，全身适用</li><li>Type-C通用快充</li><li>人体工学手柄，久握不累</li></ul><h3>适用人群</h3><p>运动爱好者、办公室白领、久站人群、中老年人</p>",
                tags="筋膜枪,肌肉放松,按摩,大健康,运动恢复",
                files=json.dumps(
                    [
                        {"name": "产品说明书.pdf", "url": "/uploads/筋膜枪说明书.pdf", "type": "pdf"},
                        {"name": "CE认证证书.pdf", "url": "/uploads/CE认证.pdf", "type": "pdf"},
                    ]
                ),
                is_featured=1,
                sort_order=4,
                status="approved",
                owner_id=4,
            ),
            Product(
                name="私域社群运营训练营",
                description="21天线上实战训练营，从0到1掌握私域社群运营全流程。含直播授课、社群实操、1v1辅导、结业认证。限时赠送社群运营SOP手册。",
                price=1980.00,
                earn_per_share=396.00,
                sale_price=2580.00,
                category="教育培训",
                brand="增长学堂",
                stock=300,
                images=json.dumps(
                    [
                        "https://picsum.photos/seed/chainke-training-1/400/300",
                        "https://picsum.photos/seed/chainke-training-2/400/300",
                        "https://picsum.photos/seed/chainke-training-3/400/300",
                    ]
                ),
                specs=json.dumps(
                    {
                        "学习周期": "21天（含周末）",
                        "授课形式": "直播+录播+社群实操",
                        "课程数量": "15节主课+5次答疑",
                        "辅导形式": "1v1导师辅导",
                        "适合人群": "运营从业者/创业者/品牌方",
                        "结业认证": "颁发结业证书",
                    }
                ),
                details="<h3>课程大纲</h3><ul><li>第一周：私域底层逻辑与定位</li><li>第二周：社群搭建与用户增长</li><li>第三周：转化变现与数据复盘</li></ul><h3>你将获得</h3><ul><li>一套完整的私域运营SOP</li><li>21天实操落地经验</li><li>行业人脉资源对接</li><li>结业证书+优秀学员推荐就业</li></ul>",
                tags="私域运营,社群运营,训练营,教育培训,增长",
                files=json.dumps(
                    [
                        {"name": "课程大纲.pdf", "url": "/uploads/训练营大纲.pdf", "type": "pdf"},
                        {"name": "讲师介绍.pdf", "url": "/uploads/讲师介绍.pdf", "type": "pdf"},
                    ]
                ),
                is_featured=1,
                sort_order=5,
                status="approved",
                owner_id=4,
            ),
            Product(
                name="智能考勤一体机 人脸识别",
                description="AI人脸识别考勤机，支持口罩识别、活体检测。超大存储容量，WiFi联网，手机APP远程管理。企业/学校/工地通用。",
                price=1280.00,
                earn_per_share=256.00,
                sale_price=1580.00,
                category="SaaS硬件",
                brand="云考勤",
                stock=800,
                images=json.dumps(
                    [
                        "https://picsum.photos/seed/chainke-attendance-1/400/300",
                        "https://picsum.photos/seed/chainke-attendance-2/400/300",
                        "https://picsum.photos/seed/chainke-attendance-3/400/300",
                    ]
                ),
                specs=json.dumps(
                    {
                        "识别方式": "人脸识别（支持口罩识别）",
                        "屏幕": "8英寸IPS高清屏",
                        "存储": "10000张人脸 / 50000条记录",
                        "联网": "WiFi / 以太网",
                        "活体检测": "支持",
                        "APP管理": "iOS/Android双端",
                        "防水等级": "IP65",
                        "电源": "DC 12V/2A",
                    }
                ),
                details="<h3>产品优势</h3><ul><li>AI深度学习算法，识别率>99.5%</li><li>支持戴口罩识别，防疫无忧</li><li>活体检测防照片/视频作弊</li><li>手机APP实时查看考勤报表</li><li>支持多班次/弹性打卡/加班审批</li></ul><h3>适用场景</h3><p>中小企业、学校、工厂、工地、办公楼</p>",
                tags="考勤机,人脸识别,智能硬件,企业管理,SaaS",
                files=json.dumps(
                    [
                        {"name": "产品安装指南.pdf", "url": "/uploads/考勤机安装指南.pdf", "type": "pdf"},
                        {"name": "APP操作手册.pdf", "url": "/uploads/考勤APP手册.pdf", "type": "pdf"},
                        {"name": "3C认证证书.pdf", "url": "/uploads/3C认证.pdf", "type": "pdf"},
                    ]
                ),
                is_featured=1,
                sort_order=6,
                status="approved",
                owner_id=4,
            ),
        ]
        db.add_all(products)
        db.flush()

        # === 创建订单 ===
        orders = [
            Order(
                user_id=2,  # buyer1
                product_id=1,
                quantity=2,
                total_price=336.00,
                status="received",
                promoter_id=3,  # promoter1
                commission=25.00 * 2 * 0.5,  # 推广员分50% = 25
            ),
            Order(
                user_id=2,
                product_id=2,
                quantity=1,
                total_price=399.00,
                status="paid",
                promoter_id=3,
                commission=80.00 * 0.5,  # 推广员分50% = 40
            ),
            Order(
                user_id=2,
                product_id=4,
                quantity=1,
                total_price=298.00,
                status="shipped",
                promoter_id=None,
                commission=0,
            ),
        ]
        db.add_all(orders)

        # === 创建提现记录 ===
        withdrawals = [
            Withdrawal(
                user_id=3,  # promoter1
                amount=15.00,
                status="approved",
                bank_info='{"bank_name":"中国银行","card_number":"6222****1234","holder_name":"李四"}',
            ),
            Withdrawal(
                user_id=3,
                amount=10.00,
                status="pending",
                bank_info='{"bank_name":"中国银行","card_number":"6222****1234","holder_name":"李四"}',
            ),
        ]
        db.add_all(withdrawals)

        db.commit()
        print(
            f"种子数据填充完成：{len(users)}个用户, {len(products)}个产品, {len(orders)}个订单, {len(withdrawals)}个提现记录"  # noqa: E501
        )

        # === 多租户：创建默认组织（仅 PostgreSQL 模式首次初始化） ===
        if is_multi_tenant():
            from app.tenant import Membership, Organization

            existing_orgs = db.query(Organization).count()
            if existing_orgs == 0:
                default_org = Organization(
                    name="链客宝AI科技有限公司",
                    slug="liankebao",
                    plan="enterprise",
                    settings={"display_name": "链客宝AI", "timezone": "Asia/Shanghai"},
                )
                db.add(default_org)
                db.flush()
                print(f"创建默认组织: {default_org.name} (slug={default_org.slug})")

                # 将所有现有用户关联到默认组织
                for user_obj in db.query(User).all():
                    membership = Membership(
                        user_id=user_obj.id,
                        org_id=default_org.id,
                        role="admin" if user_obj.role == "admin" else "member",
                    )
                    db.add(membership)
                    user_obj.organization_id = default_org.id

                db.commit()
                print(f"已将 {db.query(User).count()} 个用户关联到默认组织")

    except Exception as e:
        db.rollback()
        print(f"种子数据填充失败: {e}")
        raise
    finally:
        db.close()
