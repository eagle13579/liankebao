"""
Seed 数据 — 为 RBAC 测试创建 admin/member/viewer 用户各1个

用法:
    python -m app.seed_rbac

或在 main.py 启动时调用:
    from app.seed_rbac import seed_rbac_users
    seed_rbac_users()
"""

import logging

from sqlalchemy.orm import Session

from app.auth import hash_password
from app.database import SessionLocal, init_db
from app.models import User

logger = logging.getLogger(__name__)

# ============================================================
# Seed 用户定义
# ============================================================

SEED_USERS = [
    {
        "username": "admin_test",
        "password": "admin123456",
        "name": "测试管理员",
        "phone": "13800000001",
        "company": "链客宝科技",
        "position": "系统管理员",
        "role": "admin",
    },
    {
        "username": "member_test",
        "password": "member123456",
        "name": "测试正式成员",
        "phone": "13800000002",
        "company": "链客宝科技",
        "position": "产品经理",
        "role": "member",
    },
    {
        "username": "viewer_test",
        "password": "viewer123456",
        "name": "测试观察者",
        "phone": "13800000003",
        "company": "合作企业",
        "position": "顾问",
        "role": "viewer",
    },
]


def seed_rbac_users(db: Session | None = None) -> list[User]:
    """
    创建 RBAC 测试用户（若已存在则跳过）。

    返回创建的用户列表。
    """
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    created_users = []

    try:
        for user_data in SEED_USERS:
            existing = db.query(User).filter(User.username == user_data["username"]).first()
            if existing:
                logger.info(f"用户已存在，跳过: {user_data['username']}")
                continue

            user = User(
                username=user_data["username"],
                password_hash=hash_password(user_data["password"]),
                name=user_data["name"],
                phone=user_data["phone"],
                company=user_data["company"],
                position=user_data["position"],
                role=user_data["role"],
            )
            db.add(user)
            db.flush()
            created_users.append(user)
            logger.info(f"创建RBAC测试用户: {user_data['username']} (role={user_data['role']})")

        db.commit()

        for u in created_users:
            db.refresh(u)

        return created_users
    finally:
        if should_close:
            db.close()


# ============================================================
# 独立运行入口
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger.info("正在初始化数据库表...")
    init_db()
    logger.info("正在创建 RBAC 测试用户...")
    users = seed_rbac_users()
    logger.info(f"完成！共创建/跳过 {len(users)} 个用户")
    if users:
        for u in users:
            logger.info(f"  - {u.username} (role={u.role}, id={u.id})")
    logger.info("")
    logger.info("测试用户凭据:")
    logger.info("  admin_test  / admin123456  (管理员)")
    logger.info("  member_test / member123456 (正式成员)")
    logger.info("  viewer_test / viewer123456 (观察者)")
