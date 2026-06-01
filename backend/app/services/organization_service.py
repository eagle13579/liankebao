"""
组织管理服务层

提供组织 CRUD、成员管理、邀请管理、组织统计等业务逻辑。
"""

import logging
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.organization import Invite, Organization, OrganizationMember

logger = logging.getLogger(__name__)


# ============================================================
# 组织 CRUD
# ============================================================


def create_organization(db: Session, owner_id: int, name: str) -> Organization:
    """创建组织，同时将 owner 添加为 admin 成员"""
    slug = _generate_slug(name)
    # 确保 slug 唯一
    base_slug = slug
    counter = 1
    while db.query(Organization).filter(Organization.slug == slug).first() is not None:
        slug = f"{base_slug}-{counter}"
        counter += 1

    org = Organization(name=name, slug=slug, owner_id=owner_id)
    db.add(org)
    db.flush()  # 获取 org.id

    # 将创建者设为 admin
    add_member(db, org_id=org.id, user_id=owner_id, role="admin")

    db.commit()
    db.refresh(org)
    logger.info(f"组织已创建: id={org.id}, name={org.name}, slug={org.slug}, owner_id={owner_id}")
    return org


def get_organization(db: Session, org_id: int) -> Organization | None:
    """按 ID 获取组织"""
    return db.query(Organization).filter(Organization.id == org_id).first()


def get_organization_by_slug(db: Session, slug: str) -> Organization | None:
    """按 slug 获取组织"""
    return db.query(Organization).filter(Organization.slug == slug).first()


def get_user_orgs(db: Session, user_id: int) -> list[dict]:
    """获取用户所属的所有组织（含成员角色信息）"""
    rows = (
        db.query(Organization, OrganizationMember.role)
        .join(OrganizationMember, Organization.id == OrganizationMember.org_id)
        .filter(OrganizationMember.user_id == user_id)
        .all()
    )
    results = []
    for org, role in rows:
        member_count = db.query(func.count(OrganizationMember.id)).filter(OrganizationMember.org_id == org.id).scalar()
        results.append(
            {
                "id": org.id,
                "name": org.name,
                "slug": org.slug,
                "owner_id": org.owner_id,
                "role": role,
                "member_count": member_count or 0,
                "created_at": org.created_at,
            }
        )
    return results


def update_organization(db: Session, org_id: int, name: str | None = None) -> Organization | None:
    """更新组织信息"""
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        return None
    if name is not None:
        org.name = name
    db.commit()
    db.refresh(org)
    return org


def delete_organization(db: Session, org_id: int) -> bool:
    """删除组织"""
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        return False
    db.delete(org)
    db.commit()
    return True


# ============================================================
# 成员管理
# ============================================================


def add_member(db: Session, org_id: int, user_id: int, role: str = "member") -> OrganizationMember:
    """添加成员到组织"""
    existing = (
        db.query(OrganizationMember)
        .filter(OrganizationMember.org_id == org_id, OrganizationMember.user_id == user_id)
        .first()
    )
    if existing:
        # 已存在则更新角色
        existing.role = role
        db.commit()
        db.refresh(existing)
        return existing

    member = OrganizationMember(org_id=org_id, user_id=user_id, role=role)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def remove_member(db: Session, org_id: int, user_id: int) -> bool:
    """从组织移除成员"""
    member = (
        db.query(OrganizationMember)
        .filter(OrganizationMember.org_id == org_id, OrganizationMember.user_id == user_id)
        .first()
    )
    if not member:
        return False
    # 不允许移除最后一个 admin
    if member.role == "admin":
        admin_count = (
            db.query(func.count(OrganizationMember.id))
            .filter(OrganizationMember.org_id == org_id, OrganizationMember.role == "admin")
            .scalar()
        )
        if admin_count <= 1:
            raise ValueError("不能移除组织中唯一的管理员")
    db.delete(member)
    db.commit()
    return True


def get_org_members(db: Session, org_id: int) -> list[dict]:
    """获取组织所有成员（含用户信息）"""
    from app.models import User

    rows = (
        db.query(OrganizationMember, User)
        .join(User, OrganizationMember.user_id == User.id)
        .filter(OrganizationMember.org_id == org_id)
        .all()
    )
    results = []
    for member, user in rows:
        results.append(
            {
                "id": member.id,
                "user_id": member.user_id,
                "org_id": member.org_id,
                "role": member.role,
                "joined_at": member.joined_at,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "name": user.name,
                    "phone": user.phone,
                    "company": user.company,
                    "position": user.position,
                    "avatar": user.avatar,
                },
            }
        )
    return results


def update_member_role(db: Session, org_id: int, user_id: int, role: str) -> OrganizationMember | None:
    """更新成员角色"""
    member = (
        db.query(OrganizationMember)
        .filter(OrganizationMember.org_id == org_id, OrganizationMember.user_id == user_id)
        .first()
    )
    if not member:
        return None
    # 不允许降级最后一个 admin
    if member.role == "admin" and role != "admin":
        admin_count = (
            db.query(func.count(OrganizationMember.id))
            .filter(OrganizationMember.org_id == org_id, OrganizationMember.role == "admin")
            .scalar()
        )
        if admin_count <= 1:
            raise ValueError("组织中至少需要一名管理员")
    member.role = role
    db.commit()
    db.refresh(member)
    return member


# ============================================================
# 邀请管理
# ============================================================


def create_invite(db: Session, org_id: int, email: str) -> Invite:
    """创建组织邀请，返回带令牌的邀请记录"""
    # 检查是否已有待处理的邀请
    existing = (
        db.query(Invite).filter(Invite.org_id == org_id, Invite.email == email, Invite.status == "pending").first()
    )
    if existing:
        return existing

    token = _generate_token()
    invite = Invite(org_id=org_id, email=email, token=token, status="pending")
    db.add(invite)
    db.commit()
    db.refresh(invite)
    logger.info(f"邀请已创建: org_id={org_id}, email={email}, token={token[:8]}...")
    return invite


def accept_invite(db: Session, token: str, user_id: int) -> dict:
    """接受邀请

    Args:
        token: 邀请令牌
        user_id: 接受邀请的用户 ID

    Returns:
        dict: {org_id, org_name, role}

    Raises:
        ValueError: 邀请无效或已过期
    """
    invite = db.query(Invite).filter(Invite.token == token).first()
    if not invite:
        raise ValueError("邀请不存在或已失效")
    if invite.status != "pending":
        raise ValueError("邀请已处理")

    org = db.query(Organization).filter(Organization.id == invite.org_id).first()
    if not org:
        raise ValueError("组织不存在")

    # 将用户添加为成员
    member = add_member(db, org_id=invite.org_id, user_id=user_id, role="member")

    # 更新邀请状态
    invite.status = "accepted"
    db.commit()
    db.refresh(invite)

    return {
        "org_id": org.id,
        "org_name": org.name,
        "role": member.role,
    }


def get_org_invites(db: Session, org_id: int) -> list[Invite]:
    """获取组织的所有邀请"""
    return db.query(Invite).filter(Invite.org_id == org_id).order_by(Invite.created_at.desc()).all()


def cancel_invite(db: Session, invite_id: int) -> bool:
    """取消邀请"""
    invite = db.query(Invite).filter(Invite.id == invite_id).first()
    if not invite:
        return False
    invite.status = "expired"
    db.commit()
    return True


# ============================================================
# 组织统计
# ============================================================


def get_org_stats(db: Session, org_id: int) -> dict:
    """获取组织统计信息：产品数、线索(deal)数、成员数"""
    from app.models import Product

    # 成员数
    member_count = db.query(func.count(OrganizationMember.id)).filter(OrganizationMember.org_id == org_id).scalar()

    # 产品数 — 通过 owner 的组织关联来统计（如果产品有 organization_id 则直接统计）
    try:
        product_count = (
            db.query(func.count(Product.id))
            .filter(Product.organization_id == org_id, Product.is_deleted == False)
            .scalar()
        )
    except Exception:
        # 兼容没有 organization_id 的情况
        product_count = 0

    # 线索/Deal 数
    deal_count = 0
    try:
        from app.models import Deal

        # Deal 通过 owner 关联组织，暂用粗略统计
        deal_count = db.query(func.count(Deal.id)).scalar()
    except Exception:
        pass

    return {
        "org_id": org_id,
        "member_count": member_count or 0,
        "product_count": product_count or 0,
        "deal_count": deal_count or 0,
    }


# ============================================================
# 辅助函数
# ============================================================


def _generate_slug(name: str) -> str:
    """从组织名生成 slug"""
    slug = name.lower().strip()
    # 替换非字母数字字符为连字符
    result = []
    for ch in slug:
        if ch.isalnum() or ch == "-":
            result.append(ch)
        else:
            result.append("-")
    slug = "".join(result)
    # 合并连续连字符，去除首尾连字符
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")
    if not slug:
        slug = "org"
    # 截断长度
    return slug[:80]


def _generate_token() -> str:
    """生成唯一邀请令牌"""
    return uuid.uuid4().hex + uuid.uuid4().hex[:16]
