"""
组织管理 API 路由

提供组织创建、成员管理、邀请管理、统计等 RESTful 接口。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.services.organization_service import (
    accept_invite,
    add_member,
    cancel_invite,
    create_invite,
    create_organization,
    delete_organization,
    get_org_invites,
    get_org_members,
    get_org_stats,
    get_organization,
    get_user_orgs,
    remove_member,
    update_member_role,
    update_organization,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orgs", tags=["组织管理"])


# ============================================================
# Pydantic Schemas
# ============================================================


class CreateOrgRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="组织名称")


class CreateOrgResponse(BaseModel):
    id: int
    name: str
    slug: str
    owner_id: int
    created_at: str


class UpdateOrgRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200, description="新组织名称")


class AddMemberRequest(BaseModel):
    user_id: int = Field(..., description="用户 ID")
    role: str = Field("member", description="角色: admin/member")


class CreateInviteRequest(BaseModel):
    email: str = Field(..., description="受邀邮箱")


class AcceptInviteRequest(BaseModel):
    token: str = Field(..., description="邀请令牌")


# ============================================================
# 组织 CRUD
# ============================================================


@router.post("", summary="创建组织")
def api_create_org(
    req: CreateOrgRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建组织，当前用户自动成为管理员"""
    org = create_organization(db=db, owner_id=current_user.id, name=req.name)
    return {
        "code": 200,
        "message": "组织创建成功",
        "data": {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "owner_id": org.owner_id,
            "created_at": org.created_at.isoformat(),
        },
    }


@router.get("", summary="我的组织列表")
def api_list_orgs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户所属的所有组织"""
    orgs = get_user_orgs(db=db, user_id=current_user.id)
    return {
        "code": 200,
        "message": "success",
        "data": orgs,
    }


@router.get("/{org_id}", summary="组织详情")
def api_get_org(
    org_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取组织详细信息"""
    _check_member(db, org_id, current_user.id)
    org = get_organization(db=db, org_id=org_id)
    if not org:
        raise HTTPException(status_code=404, detail="组织不存在")
    return {
        "code": 200,
        "message": "success",
        "data": {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "owner_id": org.owner_id,
            "created_at": org.created_at.isoformat(),
        },
    }


@router.put("/{org_id}", summary="更新组织")
def api_update_org(
    org_id: int,
    req: UpdateOrgRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新组织信息（仅管理员）"""
    _check_admin(db, org_id, current_user.id)
    org = update_organization(db=db, org_id=org_id, name=req.name)
    if not org:
        raise HTTPException(status_code=404, detail="组织不存在")
    return {
        "code": 200,
        "message": "组织更新成功",
        "data": {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "owner_id": org.owner_id,
            "created_at": org.created_at.isoformat(),
        },
    }


@router.delete("/{org_id}", summary="删除组织")
def api_delete_org(
    org_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除组织（仅所有者/管理员）"""
    _check_admin(db, org_id, current_user.id)
    ok = delete_organization(db=db, org_id=org_id)
    if not ok:
        raise HTTPException(status_code=404, detail="组织不存在")
    return {"code": 200, "message": "组织已删除"}


# ============================================================
# 成员管理
# ============================================================


@router.get("/{org_id}/members", summary="成员列表")
def api_list_members(
    org_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取组织成员列表"""
    _check_member(db, org_id, current_user.id)
    members = get_org_members(db=db, org_id=org_id)
    return {
        "code": 200,
        "message": "success",
        "data": members,
    }


@router.post("/{org_id}/members", summary="添加成员")
def api_add_member(
    org_id: int,
    req: AddMemberRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """向组织添加成员（仅管理员）"""
    _check_admin(db, org_id, current_user.id)
    from app.models import User as UserModel

    user = db.query(UserModel).filter(UserModel.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    member = add_member(db=db, org_id=org_id, user_id=req.user_id, role=req.role)
    return {
        "code": 200,
        "message": "成员已添加",
        "data": {
            "id": member.id,
            "user_id": member.user_id,
            "org_id": member.org_id,
            "role": member.role,
            "joined_at": member.joined_at.isoformat(),
        },
    }


@router.put("/{org_id}/members/{user_id}/role", summary="更新成员角色")
def api_update_member_role(
    org_id: int,
    user_id: int,
    role: str = Query(..., description="角色: admin/member"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新成员角色（仅管理员）"""
    _check_admin(db, org_id, current_user.id)
    try:
        member = update_member_role(db=db, org_id=org_id, user_id=user_id, role=role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not member:
        raise HTTPException(status_code=404, detail="成员不存在")
    return {
        "code": 200,
        "message": "角色已更新",
        "data": {
            "id": member.id,
            "user_id": member.user_id,
            "org_id": member.org_id,
            "role": member.role,
            "joined_at": member.joined_at.isoformat(),
        },
    }


@router.delete("/{org_id}/members/{user_id}", summary="移除成员")
def api_remove_member(
    org_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """从组织移除成员（仅管理员）"""
    _check_admin(db, org_id, current_user.id)
    try:
        ok = remove_member(db=db, org_id=org_id, user_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="成员不存在")
    return {"code": 200, "message": "成员已移除"}


# ============================================================
# 邀请管理
# ============================================================


@router.post("/{org_id}/invites", summary="创建邀请")
def api_create_invite(
    org_id: int,
    req: CreateInviteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建组织邀请链接（仅管理员）"""
    _check_admin(db, org_id, current_user.id)
    invite = create_invite(db=db, org_id=org_id, email=req.email)
    return {
        "code": 200,
        "message": "邀请已创建",
        "data": {
            "id": invite.id,
            "org_id": invite.org_id,
            "email": invite.email,
            "token": invite.token,
            "status": invite.status,
            "created_at": invite.created_at.isoformat(),
        },
    }


@router.get("/{org_id}/invites", summary="邀请列表")
def api_list_invites(
    org_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取组织的所有邀请（仅管理员）"""
    _check_admin(db, org_id, current_user.id)
    invites = get_org_invites(db=db, org_id=org_id)
    return {
        "code": 200,
        "message": "success",
        "data": [
            {
                "id": inv.id,
                "org_id": inv.org_id,
                "email": inv.email,
                "token": inv.token,
                "status": inv.status,
                "created_at": inv.created_at.isoformat(),
            }
            for inv in invites
        ],
    }


@router.post("/invites/accept", summary="接受邀请")
def api_accept_invite(
    req: AcceptInviteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """接受组织邀请"""
    try:
        result = accept_invite(db=db, token=req.token, user_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "code": 200,
        "message": "已加入组织",
        "data": result,
    }


@router.delete("/{org_id}/invites/{invite_id}", summary="取消邀请")
def api_cancel_invite(
    org_id: int,
    invite_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """取消邀请（仅管理员）"""
    _check_admin(db, org_id, current_user.id)
    ok = cancel_invite(db=db, invite_id=invite_id)
    if not ok:
        raise HTTPException(status_code=404, detail="邀请不存在")
    return {"code": 200, "message": "邀请已取消"}


# ============================================================
# 组织统计
# ============================================================


@router.get("/{org_id}/stats", summary="组织统计")
def api_org_stats(
    org_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取组织统计：产品数、线索数、成员数"""
    _check_member(db, org_id, current_user.id)
    stats = get_org_stats(db=db, org_id=org_id)
    return {
        "code": 200,
        "message": "success",
        "data": stats,
    }


# ============================================================
# 权限辅助函数
# ============================================================


def _check_member(db: Session, org_id: int, user_id: int):
    """检查用户是否为组织成员"""
    from app.models.organization import OrganizationMember

    member = (
        db.query(OrganizationMember)
        .filter(OrganizationMember.org_id == org_id, OrganizationMember.user_id == user_id)
        .first()
    )
    if not member:
        raise HTTPException(status_code=403, detail="您不是该组织的成员")


def _check_admin(db: Session, org_id: int, user_id: int):
    """检查用户是否为组织管理员"""
    from app.models.organization import OrganizationMember

    member = (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.org_id == org_id,
            OrganizationMember.user_id == user_id,
            OrganizationMember.role == "admin",
        )
        .first()
    )
    if not member:
        raise HTTPException(status_code=403, detail="需要管理员权限")
