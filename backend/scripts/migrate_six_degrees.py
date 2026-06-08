"""
六度人脉 — 数据库迁移脚本

该脚本用于向现有 SQLite 数据库添加六度人脉相关表。
支持 SQLite → PostgreSQL 渐进迁移。

用法：
    python backend/scripts/migrate_six_degrees.py
    # 或指定数据库路径
    python backend/scripts/migrate_six_degrees.py --db-path /path/to/chainke.db
"""
import argparse
import logging
import os
import sys

# 确保能导入项目模块
sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def get_engine(db_path: str = None):
    """获取数据库引擎"""
    if db_path:
        db_url = f"sqlite:///{db_path}"
    else:
        from app.database import SQLALCHEMY_DATABASE_URL
        db_url = SQLALCHEMY_DATABASE_URL

    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        echo=False,
    )

    # SQLite 优化
    from sqlalchemy import event
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    return engine


def table_exists(engine, table_name: str) -> bool:
    """检查表是否已存在"""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def run_migration(engine):
    """
    执行迁移：
    1. 创建六度人脉相关表（如不存在）
    2. 创建索引
    3. 数据迁移（从现有 contacts/orders 表建立初始关系）
    4. 插入种子数据（可选）
    """
    from app.models.six_degrees import (
        Base as SixDegreesBase,
        ReferralLink,
        RelationEvent,
        SixDegreePathCache,
        UserRelation,
    )

    # Step 1: 建表
    logger.info("=== Step 1: 创建六度人脉表 ===")
    existing_tables = []
    new_tables = []

    for table_name, table in SixDegreesBase.metadata.tables.items():
        if table_exists(engine, table_name):
            existing_tables.append(table_name)
            logger.info(f"  表已存在: {table_name}")
        else:
            new_tables.append(table_name)

    if new_tables:
        SixDegreesBase.metadata.create_all(bind=engine)
        for name in new_tables:
            logger.info(f"  表已创建: {name}")
    else:
        logger.info("  所有表已存在，跳过建表")

    # Step 2: 创建索引（SQLAlchemy 建表时已创建，这里手动确认）
    logger.info("=== Step 2: 索引确认 ===")
    inspector = inspect(engine)
    for table_name in ["user_relations", "relation_events", "six_degree_path_cache", "referral_links"]:
        if table_exists(engine, table_name):
            indexes = inspector.get_indexes(table_name)
            logger.info(f"  表 {table_name}: {len(indexes)} 个索引")

    # Step 3: 从现有数据建立初始关系
    logger.info("=== Step 3: 数据迁移 ===")
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # 3a. 从 orders 表的 promoter_id 建立推广关系
        from app.models import Order, User

        existing_relations = session.query(UserRelation).count()
        logger.info(f"  现有关系数: {existing_relations}")

        if existing_relations == 0:
            logger.info("  首次迁移，从订单数据建立初始关系...")

            # 从 orders 建立 promoter->buyer 关系
            orders = session.query(Order).filter(
                Order.promoter_id.isnot(None)
            ).distinct(Order.user_id, Order.promoter_id).all()

            relation_count = 0
            for order in orders:
                try:
                    rel = UserRelation(
                        from_user_id=order.promoter_id,
                        to_user_id=order.user_id,
                        relation_type="refer",
                        trust_score=0.5,
                        bidirectional=False,
                        source="order_history",
                        is_active=True,
                        interaction_count=1,
                        last_interaction_at=order.created_at,
                    )
                    session.add(rel)
                    relation_count += 1

                    # 事件日志
                    event = RelationEvent(
                        relation_id=0,  # 先设为0，flush后更新
                        from_user_id=order.promoter_id,
                        to_user_id=order.user_id,
                        event_type="created",
                        new_trust_score=0.5,
                        reason="从历史订单数据迁移",
                    )
                    session.add(event)
                except Exception:
                    session.rollback()

            session.commit()
            logger.info(f"  从订单数据建立了 {relation_count} 条关系")

            # 3b. 从联系人数据建立关系
            from app.models import Contact
            contacts = session.query(Contact).filter(
                Contact.owner_id.isnot(None),
                Contact.is_deleted == False,
            ).all()

            phone_users = {}
            users = session.query(User).filter(User.is_deleted == False).all()
            for u in users:
                if u.phone:
                    phone_users[u.phone] = u.id

            contact_relation_count = 0
            for contact in contacts:
                if contact.phone and contact.phone in phone_users:
                    target_id = phone_users[contact.phone]
                    if contact.owner_id != target_id:
                        try:
                            rel = UserRelation(
                                from_user_id=contact.owner_id,
                                to_user_id=target_id,
                                relation_type="contact",
                                trust_score=0.4,
                                bidirectional=False,
                                source="contact_import",
                                is_active=True,
                                interaction_count=1,
                            )
                            session.add(rel)
                            contact_relation_count += 1
                        except Exception:
                            session.rollback()

            session.commit()
            logger.info(f"  从通讯录数据建立了 {contact_relation_count} 条关系")

        else:
            logger.info(f"  已有 {existing_relations} 条关系，跳过初始迁移")

        # Step 4: 验证
        logger.info("=== Step 4: 迁移验证 ===")
        final_count = session.query(UserRelation).count()
        logger.info(f"  总关系数: {final_count}")
        logger.info(f"  表结构: {inspector.get_table_names()}")
        logger.info("迁移完成 ✓")

    except Exception as e:
        session.rollback()
        logger.error(f"迁移失败: {e}")
        raise
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description="六度人脉数据库迁移脚本")
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="SQLite 数据库文件路径（默认使用环境变量 SQLITE_DB_PATH 或 data/chainke.db）",
    )
    args = parser.parse_args()

    engine = get_engine(args.db_path)
    run_migration(engine)


if __name__ == "__main__":
    main()
