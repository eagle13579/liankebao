"""数据库配置与初始化"""
import os
import json
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
    """初始化数据库：重建表并填充种子数据"""
    from app.models import User, Product, Order, Withdrawal  # noqa: 确保模型已导入

    # === 先删表再重建（适配schema变更） ===
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        print("正在填充种子数据...")

        # 预计算密码哈希
        pwhash_admin = bcrypt_hasher.hash("admin123")
        pwhash_123456 = bcrypt_hasher.hash("123456")

        # === 创建用户 ===
        users = [
            User(
                username="admin",
                password_hash=pwhash_admin,
                name="管理员",
                phone="13800000000",
                company="链客宝科技",
                position="系统管理员",
                role="admin",
                avatar="https://api.dicebear.com/7.x/avataaars/svg?seed=admin",
            ),
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
            # --- 产品1: 有机红枣礼盒 ---
            Product(
                name="有机红枣礼盒 500g×3袋",
                description="精选新疆和田有机红枣，颗颗饱满肉厚，自然甜香。礼盒装自用送礼皆宜。严格有机认证，无添加无农残。",
                price=168.00,
                earn_per_share=25.00,
                sale_price=198.00,
                category="食品/大健康",
                brand="丝路果园",
                stock=500,
                images=json.dumps([
                    "https://picsum.photos/seed/chainke-red-dates-1/400/300",
                    "https://picsum.photos/seed/chainke-red-dates-2/400/300",
                    "https://picsum.photos/seed/chainke-red-dates-3/400/300"
                ]),
                specs=json.dumps({
                    "规格": "500g×3袋",
                    "保质期": "12个月",
                    "产地": "新疆和田",
                    "贮存条件": "阴凉干燥处",
                    "包装": "礼盒装"
                }),
                details="<h3>产品亮点</h3><ul><li>新疆和田核心产区，日照充足</li><li>国家有机认证，零添加</li><li>颗颗精选，肉厚核小</li></ul><h3>食用建议</h3><p>开袋即食，也可泡茶煮粥。每日3-5颗，健康养颜。</p>",
                tags="有机,红枣,礼盒,大健康,滋补",
                files=json.dumps([
                    {"name": "产品质检报告.pdf", "url": "/uploads/红枣质检报告.pdf", "type": "pdf"},
                    {"name": "有机认证证书.pdf", "url": "/uploads/有机认证.pdf", "type": "pdf"}
                ]),
                is_featured=1,
                sort_order=1,
                status="approved",
                owner_id=4,
            ),
            # --- 产品2: AI数字名片 ---
            Product(
                name="AI数字名片 Pro版 年卡",
                description="基于AI技术的智能数字名片，支持多模板、AI智能推荐、人脉管理、数据统计。企业家商务社交首选，让每一次相遇都有价值。",
                price=399.00,
                earn_per_share=80.00,
                sale_price=499.00,
                category="企业家服务",
                brand="链客宝",
                stock=9999,
                images=json.dumps([
                    "https://picsum.photos/seed/chainke-digital-card-1/400/300",
                    "https://picsum.photos/seed/chainke-digital-card-2/400/300",
                    "https://picsum.photos/seed/chainke-digital-card-3/400/300"
                ]),
                specs=json.dumps({
                    "版本": "Pro版年卡",
                    "有效期": "购买日起365天",
                    "模板数量": "50+精选模板",
                    "AI推荐次数": "无限次",
                    "人脉容量": "10000人",
                    "数据导出": "支持Excel/CSV"
                }),
                details="<h3>核心功能</h3><ul><li>AI智能名片设计</li><li>多模板自由切换</li><li>扫码一键交换</li><li>人脉智能分类管理</li><li>交换数据分析看板</li><li>团队名片统一管理</li></ul><h3>适用人群</h3><p>企业家、销售精英、商务人士、创业者</p>",
                tags="AI,数字名片,企业家,商务,人脉管理",
                files=json.dumps([
                    {"name": "产品使用手册.pdf", "url": "/uploads/数字名片手册.pdf", "type": "pdf"},
                    {"name": "功能对比表.xlsx", "url": "/uploads/功能对比.xlsx", "type": "xlsx"}
                ]),
                is_featured=1,
                sort_order=2,
                status="approved",
                owner_id=4,
            ),
            # --- 产品3: 企业法律顾问套餐 ---
            Product(
                name="企业法律顾问套餐 年度",
                description="全年企业法律顾问服务，含合同审核、法律咨询、风险评估、知识产权保护等。专业律师团队1对1服务，企业法律问题一站式解决。",
                price=2980.00,
                earn_per_share=596.00,
                sale_price=3680.00,
                category="企业服务",
                brand="法务通",
                stock=200,
                images=json.dumps([
                    "https://picsum.photos/seed/chainke-legal-1/400/300",
                    "https://picsum.photos/seed/chainke-legal-2/400/300",
                    "https://picsum.photos/seed/chainke-legal-3/400/300"
                ]),
                specs=json.dumps({
                    "服务周期": "12个月",
                    "合同审核": "不限次数（≤10页/份）",
                    "法律咨询": "不限次数（工作日9:00-18:00）",
                    "律师分配": "3人专属服务组",
                    "响应时效": "4小时内回复",
                    "适用规模": "10-500人企业"
                }),
                details="<h3>服务内容</h3><ul><li>日常法律咨询（电话/微信/邮件）</li><li>合同起草与审核（每年50份内）</li><li>企业规章制度审查</li><li>劳动人事法律支持</li><li>知识产权基础保护</li><li>律师函发送（5次/年）</li></ul><h3>服务流程</h3><p>在线下单 → 分配律师 → 建立服务群 → 全年无忧</p>",
                tags="法律顾问,企业服务,合同审核,知识产权,法律服务",
                files=json.dumps([
                    {"name": "服务合同模板.pdf", "url": "/uploads/法律顾问合同.pdf", "type": "pdf"},
                    {"name": "服务内容清单.pdf", "url": "/uploads/服务清单.pdf", "type": "pdf"}
                ]),
                is_featured=1,
                sort_order=3,
                status="approved",
                owner_id=4,
            ),
            # --- 产品4: 筋膜枪 ---
            Product(
                name="筋膜枪 肌肉放松 静音款",
                description="专业级肌肉筋膜枪，6档变速调节，超静音设计。运动后肌肉放松、日常疲劳缓解。Type-C快充，续航8小时。",
                price=298.00,
                earn_per_share=58.00,
                sale_price=368.00,
                category="大健康",
                brand="舒肌宝",
                stock=1000,
                images=json.dumps([
                    "https://picsum.photos/seed/chainke-massage-gun-1/400/300",
                    "https://picsum.photos/seed/chainke-massage-gun-2/400/300",
                    "https://picsum.photos/seed/chainke-massage-gun-3/400/300"
                ]),
                specs=json.dumps({
                    "型号": "S3 Pro",
                    "档位": "6档变速（1200-3200转/分）",
                    "噪音": "≤35dB（静音款）",
                    "电池": "2600mAh锂电池",
                    "续航": "约8小时",
                    "充电": "Type-C快充（2小时充满）",
                    "配件": "6种按摩头",
                    "重量": "约680g"
                }),
                details="<h3>产品特点</h3><ul><li>超静音电机，使用不扰人</li><li>6档智能变速，满足不同需求</li><li>6种专业按摩头，全身适用</li><li>Type-C通用快充</li><li>人体工学手柄，久握不累</li></ul><h3>适用人群</h3><p>运动爱好者、办公室白领、久站人群、中老年人</p>",
                tags="筋膜枪,肌肉放松,按摩,大健康,运动恢复",
                files=json.dumps([
                    {"name": "产品说明书.pdf", "url": "/uploads/筋膜枪说明书.pdf", "type": "pdf"},
                    {"name": "CE认证证书.pdf", "url": "/uploads/CE认证.pdf", "type": "pdf"}
                ]),
                is_featured=1,
                sort_order=4,
                status="approved",
                owner_id=4,
            ),
            # --- 产品5: 私域社群运营训练营 ---
            Product(
                name="私域社群运营训练营",
                description="21天线上实战训练营，从0到1掌握私域社群运营全流程。含直播授课、社群实操、1v1辅导、结业认证。限时赠送社群运营SOP手册。",
                price=1980.00,
                earn_per_share=396.00,
                sale_price=2580.00,
                category="教育培训",
                brand="增长学堂",
                stock=300,
                images=json.dumps([
                    "https://picsum.photos/seed/chainke-training-1/400/300",
                    "https://picsum.photos/seed/chainke-training-2/400/300",
                    "https://picsum.photos/seed/chainke-training-3/400/300"
                ]),
                specs=json.dumps({
                    "学习周期": "21天（含周末）",
                    "授课形式": "直播+录播+社群实操",
                    "课程数量": "15节主课+5次答疑",
                    "辅导形式": "1v1导师辅导",
                    "适合人群": "运营从业者/创业者/品牌方",
                    "结业认证": "颁发结业证书"
                }),
                details="<h3>课程大纲</h3><ul><li>第一周：私域底层逻辑与定位</li><li>第二周：社群搭建与用户增长</li><li>第三周：转化变现与数据复盘</li></ul><h3>你将获得</h3><ul><li>一套完整的私域运营SOP</li><li>21天实操落地经验</li><li>行业人脉资源对接</li><li>结业证书+优秀学员推荐就业</li></ul>",
                tags="私域运营,社群运营,训练营,教育培训,增长",
                files=json.dumps([
                    {"name": "课程大纲.pdf", "url": "/uploads/训练营大纲.pdf", "type": "pdf"},
                    {"name": "讲师介绍.pdf", "url": "/uploads/讲师介绍.pdf", "type": "pdf"}
                ]),
                is_featured=1,
                sort_order=5,
                status="approved",
                owner_id=4,
            ),
            # --- 产品6: 智能考勤一体机 ---
            Product(
                name="智能考勤一体机 人脸识别",
                description="AI人脸识别考勤机，支持口罩识别、活体检测。超大存储容量，WiFi联网，手机APP远程管理。企业/学校/工地通用。",
                price=1280.00,
                earn_per_share=256.00,
                sale_price=1580.00,
                category="SaaS硬件",
                brand="云考勤",
                stock=800,
                images=json.dumps([
                    "https://picsum.photos/seed/chainke-attendance-1/400/300",
                    "https://picsum.photos/seed/chainke-attendance-2/400/300",
                    "https://picsum.photos/seed/chainke-attendance-3/400/300"
                ]),
                specs=json.dumps({
                    "识别方式": "人脸识别（支持口罩识别）",
                    "屏幕": "8英寸IPS高清屏",
                    "存储": "10000张人脸 / 50000条记录",
                    "联网": "WiFi / 以太网",
                    "活体检测": "支持",
                    "APP管理": "iOS/Android双端",
                    "防水等级": "IP65",
                    "电源": "DC 12V/2A"
                }),
                details="<h3>产品优势</h3><ul><li>AI深度学习算法，识别率>99.5%</li><li>支持戴口罩识别，防疫无忧</li><li>活体检测防照片/视频作弊</li><li>手机APP实时查看考勤报表</li><li>支持多班次/弹性打卡/加班审批</li></ul><h3>适用场景</h3><p>中小企业、学校、工厂、工地、办公楼</p>",
                tags="考勤机,人脸识别,智能硬件,企业管理,SaaS",
                files=json.dumps([
                    {"name": "产品安装指南.pdf", "url": "/uploads/考勤机安装指南.pdf", "type": "pdf"},
                    {"name": "APP操作手册.pdf", "url": "/uploads/考勤APP手册.pdf", "type": "pdf"},
                    {"name": "3C认证证书.pdf", "url": "/uploads/3C认证.pdf", "type": "pdf"}
                ]),
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
        print(f"种子数据填充完成：{len(users)}个用户, {len(products)}个产品, {len(orders)}个订单, {len(withdrawals)}个提现记录")

    except Exception as e:
        db.rollback()
        print(f"种子数据填充失败: {e}")
        raise
    finally:
        db.close()

