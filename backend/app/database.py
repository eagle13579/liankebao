"""数据库配置与初始化"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from passlib.hash import bcrypt as bcrypt_hasher

# 数据库路径
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "chainke.db")
os.makedirs(DB_DIR, exist_ok=True)

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite需要
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI依赖注入：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库：创建所有表并填充种子数据"""
    from app.models import User, Product, Order, Withdrawal  # noqa: 确保模型已导入

    # 创建所有表
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # 检查是否已有数据
        if db.query(User).count() > 0:
            print("数据库已存在数据，跳过种子数据填充")
            return

        print("正在填充种子数据...")

        # === 创建用户 ===
        users = [
            User(
                username="admin",
                password_hash=bcrypt_hasher.hash("admin123"),
                name="管理员",
                phone="13800000000",
                company="链客宝科技",
                position="系统管理员",
                role="admin",
                avatar="https://api.dicebear.com/7.x/avataaars/svg?seed=admin",
            ),
            User(
                username="buyer1",
                password_hash=bcrypt_hasher.hash("123456"),
                name="张三",
                phone="13800000001",
                company="创新科技有限公司",
                position="CEO",
                role="buyer",
                avatar="https://api.dicebear.com/7.x/avataaars/svg?seed=buyer1",
            ),
            User(
                username="promoter1",
                password_hash=bcrypt_hasher.hash("123456"),
                name="李四",
                phone="13800000002",
                company="推广联盟",
                position="高级推广员",
                role="promoter",
                avatar="https://api.dicebear.com/7.x/avataaars/svg?seed=promoter1",
            ),
            User(
                username="supplier1",
                password_hash=bcrypt_hasher.hash("123456"),
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

        # === 创建产品 ===
        products = [
            Product(
                name="企业数字化管理平台",
                description="一站式企业数字化管理解决方案，包含CRM、ERP、OA等模块，助力企业数字化转型。支持私有化部署和SaaS模式。",
                price=99900.00,
                earn_per_share=19980.00,
                category="软件服务",
                stock=999,
                images='["https://picsum.photos/seed/prod1/400/300"]',
                status="approved",
                owner_id=4,  # supplier1
            ),
            Product(
                name="高端商务咨询包",
                description="为企业提供战略规划、市场分析、组织架构优化等高端咨询服务。由资深顾问团队一对一服务。",
                price=50000.00,
                earn_per_share=10000.00,
                category="咨询服务",
                stock=50,
                images='["https://picsum.photos/seed/prod2/400/300"]',
                status="approved",
                owner_id=4,
            ),
            Product(
                name="智能营销系统",
                description="基于AI的智能营销自动化系统，帮助企业实现精准获客、客户画像分析和营销效果追踪。",
                price=29900.00,
                earn_per_share=5980.00,
                category="软件服务",
                stock=200,
                images='["https://picsum.photos/seed/prod3/400/300"]',
                status="approved",
                owner_id=4,
            ),
            Product(
                name="企业培训课程套装",
                description="涵盖领导力、销售技巧、团队管理等方向的12门核心课程，含线上视频+线下工作坊。",
                price=19800.00,
                earn_per_share=3960.00,
                category="教育培训",
                stock=300,
                images='["https://picsum.photos/seed/prod4/400/300"]',
                status="approved",
                owner_id=4,
            ),
            Product(
                name="区块链溯源解决方案",
                description="基于区块链技术的产品全链路溯源系统，适用于食品、医药、奢侈品等行业。",
                price=150000.00,
                earn_per_share=30000.00,
                category="软件服务",
                stock=100,
                images='["https://picsum.photos/seed/prod5/400/300"]',
                status="pending",
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
                quantity=1,
                total_price=99900.00,
                status="received",
                promoter_id=3,  # promoter1
                commission=19980.00 * 0.5,  # 推广员分50%
            ),
            Order(
                user_id=2,
                product_id=3,
                quantity=2,
                total_price=59800.00,
                status="paid",
                promoter_id=3,
                commission=5980.00 * 0.5,
            ),
            Order(
                user_id=2,
                product_id=4,
                quantity=1,
                total_price=19800.00,
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
                amount=5000.00,
                status="approved",
                bank_info='{"bank_name":"中国银行","card_number":"6222****1234","holder_name":"李四"}',
            ),
            Withdrawal(
                user_id=3,
                amount=3000.00,
                status="pending",
                bank_info='{"bank_name":"中国银行","card_number":"6222****1234","holder_name":"李四"}',
            ),
        ]
        db.add_all(withdrawals)

        db.commit()
        print(f"种子数据填充完成：{len(users)}个用户, {len(products)}个产品, {len(orders)}个订单, {len(withdrawals)}个提现记录")

    except Exception as e:
        db.rollback()
        print(f"种子数据填充失败: {e}")
        raise
    finally:
        db.close()
