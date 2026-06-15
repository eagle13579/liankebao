"""
六度人脉 — API 路由

核心端点：
  GET    /api/six-degrees/path/{target_user_id}     — 查找当前用户到目标用户的六度路径
  GET    /api/six-degrees/network                    — 获取当前用户的N度人脉网络
  POST   /api/six-degrees/relations                  — 建立关系边
  DELETE /api/six-degrees/relations/{relation_id}    — 删除关系边
  GET    /api/six-degrees/relations                  — 关系列表
  PUT    /api/six-degrees/relations/{relation_id}/trust — 更新信任度
  GET    /api/six-degrees/recommendations            — 推荐可能认识的人
  POST   /api/six-degrees/referral-link              — 生成邀请链接
  GET    /api/six-degrees/referral-link/{code}       — 通过邀请码查询邀请人
  POST   /api/six-degrees/referral-link/{code}/register — 通过邀请码注册
  GET    /api/six-degrees/stats                      — 六度人脉统计数据

通知端点（内部）：
  POST   /api/six-degrees/notify-connection          — 触发人脉连接通知
"""
import json
import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.models.six_degrees import ReferralLink, RelationEvent, UserRelation
from app.services.six_degrees import (
    PathCacheManager,
    RelationGraph,
    compute_trust_decay,
    compute_trust_score,
    create_relation,
    find_network,
    find_shortest_path,
    update_trust_score,
)
from app.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/six-degrees", tags=["六度人脉"])


# ============================================================
# 六度路径查询
# ============================================================

@router.get("/path/{target_user_id}")
def find_path(
    target_user_id: int,
    max_depth: int = Query(6, ge=1, le=6, description="最大搜索深度(1~6)"),
    use_cache: bool = Query(True, description="是否使用缓存"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    查找当前用户到目标用户的六度人脉路径

    返回最短路径及沿途节点信息、信任度评分。
    路径中的每个节点包含：user_id, name, company, position, avatar, trust_score
    """
    if current_user.id == target_user_id:
        return {
            "code": 200,
            "message": "success",
            "data": {
                "path": [current_user.id],
                "nodes": [_user_to_brief(current_user)],
                "length": 0,
                "trust_score": 1.0,
                "decay": 1.0,
            },
        }

    # 检查目标用户是否存在
    target_user = db.query(User).filter(
        User.id == target_user_id, User.is_deleted == False
    ).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="目标用户不存在")

    result = find_shortest_path(
        db=db,
        from_user_id=current_user.id,
        to_user_id=target_user_id,
        max_depth=max_depth,
        use_cache=use_cache,
    )

    if not result:
        return {
            "code": 200,
            "message": "success",
            "data": {
                "path": [],
                "nodes": [],
                "length": -1,
                "trust_score": 0.0,
                "decay": 0.0,
                "message": f"未找到从 {current_user.name} 到 {target_user.name} 的六度路径"
            },
        }

    # 对路径中的每个节点补充衰减信任度
    decayed_nodes = []
    for i, node in enumerate(result.get("nodes", [])):
        node_copy = dict(node)
        node_copy["hop"] = i
        node_copy["decay"] = compute_trust_decay(i)
        if i < len(result.get("path", [])) - 1:
            # 下一跳的信任度
            next_id = result["path"][i + 1]
            for neighbor_id, trust in RelationGraph(db).get_neighbors(result["path"][i]):
                if neighbor_id == next_id:
                    node_copy["next_hop_trust"] = trust
                    break
        decayed_nodes.append(node_copy)

    return {
        "code": 200,
        "message": "success",
        "data": {
            "path": result["path"],
            "nodes": decayed_nodes,
            "length": result["length"],
            "trust_score": result["trust_score"],
            "search_time_ms": result.get("search_time_ms", 0),
            "decay": compute_trust_decay(result["length"]),
        },
    }


# ============================================================
# 人脉网络查询
# ============================================================

@router.get("/network")
def get_network(
    degree: int = Query(2, ge=1, le=6, description="人脉度数(1~6)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    min_trust: float = Query(0.0, ge=0.0, le=1.0, description="最小信任度阈值"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取当前用户的N度人脉网络

    返回值按度数分层，包含每度的人脉列表和统计信息。
    信任度从高到低排序。
    """
    result = find_network(
        db=db,
        user_id=current_user.id,
        degree=degree,
        page=page,
        page_size=page_size,
        min_trust=min_trust,
    )

    return {
        "code": 200,
        "message": "success",
        "data": result,
    }


# ============================================================
# 关系管理
# ============================================================

@router.get("/relations")
def list_relations(
    relation_type: str = Query(None, description="关系类型筛选"),
    is_active: bool = Query(True, description="仅显示有效关系"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取当前用户的关系列表（一度人脉）
    """
    query = db.query(UserRelation).filter(
        UserRelation.from_user_id == current_user.id,
        UserRelation.is_deleted == False,
    )

    if is_active:
        query = query.filter(UserRelation.is_active == True)

    if relation_type:
        query = query.filter(UserRelation.relation_type == relation_type)

    total = query.count()
    relations = (
        query.order_by(desc(UserRelation.trust_score))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for rel in relations:
        target_user = db.query(User).filter(User.id == rel.to_user_id).first()
        items.append({
            "id": rel.id,
            "relation_type": rel.relation_type,
            "trust_score": rel.trust_score,
            "bidirectional": rel.bidirectional,
            "interaction_count": rel.interaction_count,
            "last_interaction_at": rel.last_interaction_at.isoformat() if rel.last_interaction_at else None,
            "created_at": rel.created_at.isoformat(),
            "source": rel.source,
            "target_user": _user_to_brief(target_user) if target_user else None,
        })

    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.post("/relations")
def add_relation(
    target_user_id: int = Query(..., description="目标用户ID"),
    relation_type: str = Query("invite", description="关系类型: invite/contact/brochure/coop/refer"),
    trust_score: float = Query(0.5, ge=0.0, le=1.0, description="初始信任度"),
    bidirectional: bool = Query(False, description="是否双向关系"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    建立与目标用户的关系边

    当用户邀请伙伴、交换名片、或确认合作关系时调用。
    自动创建关系并记录事件日志。
    """
    if current_user.id == target_user_id:
        raise HTTPException(status_code=400, detail="不能和自己建立关系")

    target = db.query(User).filter(
        User.id == target_user_id, User.is_deleted == False
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="目标用户不存在")

    # 检查是否已存在
    existing = db.query(UserRelation).filter(
        UserRelation.from_user_id == current_user.id,
        UserRelation.to_user_id == target_user_id,
        UserRelation.is_deleted == False,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="关系已存在")

    relation = create_relation(
        db=db,
        from_user_id=current_user.id,
        to_user_id=target_user_id,
        relation_type=relation_type,
        trust_score=trust_score,
        bidirectional=bidirectional,
        source=relation_type,
    )

    # 如果设为双向，建立反向边
    if bidirectional:
        reverse = create_relation(
            db=db,
            from_user_id=target_user_id,
            to_user_id=current_user.id,
            relation_type=relation_type,
            trust_score=trust_score,
            bidirectional=True,
            source=relation_type,
        )

    return {
        "code": 200,
        "message": "success",
        "data": {
            "id": relation.id,
            "from_user_id": relation.from_user_id,
            "to_user_id": relation.to_user_id,
            "trust_score": relation.trust_score,
        },
    }


@router.delete("/relations/{relation_id}")
def remove_relation(
    relation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    删除/断开关系
    """
    relation = db.query(UserRelation).filter(
        UserRelation.id == relation_id,
        UserRelation.from_user_id == current_user.id,
        UserRelation.is_deleted == False,
    ).first()
    if not relation:
        raise HTTPException(status_code=404, detail="关系不存在")

    # 软删除
    relation.is_deleted = True
    relation.deleted_at = datetime.now(timezone.utc)
    relation.is_active = False

    # 记录事件
    event = RelationEvent(
        relation_id=relation.id,
        from_user_id=relation.from_user_id,
        to_user_id=relation.to_user_id,
        event_type="deactivated",
        old_trust_score=relation.trust_score,
        reason="用户主动删除关系",
    )
    db.add(event)
    db.commit()

    # 清除缓存
    cache_mgr = PathCacheManager(db)
    cache_mgr.invalidate_user(current_user.id)

    return {"code": 200, "message": "success"}


@router.put("/relations/{relation_id}/trust")
def update_relation_trust(
    relation_id: int,
    trust_score: float = Query(..., ge=0.0, le=1.0),
    reason: str = Query("", description="变更原因"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    更新关系信任度
    """
    relation = db.query(UserRelation).filter(
        UserRelation.id == relation_id,
        UserRelation.from_user_id == current_user.id,
        UserRelation.is_deleted == False,
    ).first()
    if not relation:
        raise HTTPException(status_code=404, detail="关系不存在")

    updated = update_trust_score(
        db=db,
        relation_id=relation_id,
        new_score=trust_score,
        reason=reason,
    )

    return {
        "code": 200,
        "message": "success",
        "data": {
            "id": updated.id,
            "old_score": relation.trust_score,
            "new_score": updated.trust_score,
        },
    }


# ============================================================
# 人脉推荐
# ============================================================

@router.get("/recommendations")
def recommend_connections(
    degree: int = Query(2, ge=2, le=4, description="推荐度数(2~4)"),
    limit: int = Query(20, ge=1, le=50),
    min_trust: float = Query(0.1, ge=0.0, le=1.0),
    same_industry: bool = Query(False, description="是否优先同行业"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    推荐可能认识的人（基于六度人脉）

    推荐逻辑：
    1. 优先推荐二度人脉（朋友的朋友）
    2. 按信任度从高到低排序
    3. 可选按行业筛选
    4. 排除已有直接关系的人
    """
    graph = RelationGraph(db)
    graph.load_ego_network(current_user.id, degrees=degree)

    # 获取已有直接关系（排除）
    direct_relations = set()
    direct = db.query(UserRelation).filter(
        UserRelation.from_user_id == current_user.id,
        UserRelation.is_active == True,
        UserRelation.is_deleted == False,
    ).all()
    for rel in direct:
        direct_relations.add(rel.to_user_id)
    direct_relations.add(current_user.id)

    # BFS获取推荐
    visited = {current_user.id: 0}
    from collections import deque
    queue = deque([(current_user.id, 0, [current_user.id])])
    recommendations = []

    while queue:
        node, depth, path = queue.popleft()
        if depth >= degree:
            break

        for neighbor_id, trust in graph.get_neighbors(node):
            if neighbor_id not in visited or visited[neighbor_id] > depth + 1:
                visited[neighbor_id] = depth + 1
                new_path = path + [neighbor_id]
                queue.append((neighbor_id, depth + 1, new_path))

                if depth + 1 >= 2 and neighbor_id not in direct_relations:
                    user_info = graph.get_user_info(neighbor_id)
                    if user_info:
                        from app.services.six_degrees import _compute_path_trust
                        path_trust = _compute_path_trust(graph, new_path)
                        if path_trust >= min_trust:
                            recommendations.append({
                                "user": user_info,
                                "degree": depth + 1,
                                "path_trust": path_trust,
                                "common_connections": [],
                            })

    # 补充共同联系人信息
    for rec in recommendations:
        uid = rec["user"]["user_id"]
        common = []
        for direct_id in direct_relations:
            if direct_id == current_user.id:
                continue
            # 检查直接关系是否也认识推荐人
            for nid, _ in graph.get_neighbors(direct_id):
                if nid == uid:
                    common_user = graph.get_user_info(direct_id)
                    if common_user:
                        common.append(common_user)
                    break
        rec["common_connections"] = common[:5]

    # 排序：按信任度降序
    recommendations.sort(key=lambda x: x["path_trust"], reverse=True)
    recommendations = recommendations[:limit]

    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": recommendations,
            "total": len(recommendations),
        },
    }


# ============================================================
# 邀请链接管理
# ============================================================

@router.post("/referral-link")
def create_referral_link(
    title: str = Query("", description="链接标题"),
    description: str = Query("", description="链接描述"),
    invite_type: str = Query("direct", description="邀请类型: direct/brochure/product"),
    redirect_url: str = Query(None, description="跳转目标URL"),
    expires_in_days: int = Query(30, ge=1, le=365, description="过期天数"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    生成邀请链接/二维码

    用于「/home邀请伙伴」入口，生成带邀请码的链接。
    新用户通过此链接注册时，自动建立关系边。
    """
    # 生成唯一邀请码
    code = secrets.token_urlsafe(16)
    while db.query(ReferralLink).filter(ReferralLink.code == code).first():
        code = secrets.token_urlsafe(16)

    expires_at = datetime.now(timezone.utc).replace(
        hour=23, minute=59, second=59
    ) + __import__('datetime').datetime.timedelta(days=expires_in_days)

    link = ReferralLink(
        owner_user_id=current_user.id,
        code=code,
        title=title or f"{current_user.name} 的邀请",
        description=description,
        invite_type=invite_type,
        redirect_url=redirect_url,
        expires_at=expires_at,
    )
    db.add(link)
    db.commit()
    db.refresh(link)

    invite_url = f"https://liankebao.top/invite/{code}"

    return {
        "code": 200,
        "message": "success",
        "data": {
            "id": link.id,
            "code": link.code,
            "invite_url": invite_url,
            "title": link.title,
            "expires_at": link.expires_at.isoformat(),
        },
    }


@router.get("/referral-link/{code}")
def lookup_referral_link(
    code: str,
    db: Session = Depends(get_db),
):
    """
    通过邀请码查询邀请人信息

    新用户扫码/点击链接时调用，显示邀请人信息。
    """
    link = db.query(ReferralLink).filter(
        ReferralLink.code == code,
        ReferralLink.is_active == True,
    ).first()
    if not link:
        raise HTTPException(status_code=404, detail="邀请链接无效或已过期")

    if link.expires_at and link.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="邀请链接已过期")

    # 增加扫码计数
    link.scan_count += 1
    db.commit()

    owner = db.query(User).filter(User.id == link.owner_user_id).first()

    return {
        "code": 200,
        "message": "success",
        "data": {
            "inviter": _user_to_brief(owner) if owner else None,
            "title": link.title,
            "description": link.description,
            "invite_type": link.invite_type,
            "redirect_url": link.redirect_url,
        },
    }


@router.post("/referral-link/{code}/register")
def register_via_referral(
    code: str,
    new_user_id: int = Query(..., description="新注册用户ID"),
    db: Session = Depends(get_db),
):
    """
    通过邀请码完成注册，自动建立关系边

    新用户注册时调用，在邀请人和被邀请人之间创建六度关系。
    """
    link = db.query(ReferralLink).filter(
        ReferralLink.code == code,
        ReferralLink.is_active == True,
    ).first()
    if not link:
        raise HTTPException(status_code=404, detail="邀请链接无效")

    if link.expires_at and link.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="邀请链接已过期")

    # 增加注册计数
    link.register_count += 1
    link.owner_user_id  # inviter

    # 建立关系边
    create_relation(
        db=db,
        from_user_id=link.owner_user_id,
        to_user_id=new_user_id,
        relation_type="invite",
        trust_score=0.6,  # 邀请注册默认信任度较高
        source="referral_link",
    )

    db.commit()

    return {"code": 200, "message": "success", "data": {"inviter_id": link.owner_user_id}}


# ============================================================
# 六度人脉统计
# ============================================================

@router.get("/stats")
def get_six_degrees_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取当前用户的六度人脉统计数据
    """
    # 一度人脉（直接关系）
    first_degree = db.query(UserRelation).filter(
        UserRelation.from_user_id == current_user.id,
        UserRelation.is_active == True,
        UserRelation.is_deleted == False,
    ).count()

    # 二度人脉（朋友的朋友）
    graph = RelationGraph(db)
    graph.load_ego_network(current_user.id, degrees=2)
    second_degree = 0
    direct_set = {
        rel.to_user_id
        for rel in db.query(UserRelation).filter(
            UserRelation.from_user_id == current_user.id,
            UserRelation.is_active == True,
        ).all()
    }
    direct_set.add(current_user.id)

    for nid, _ in graph.get_neighbors(current_user.id):
        for nnid, _ in graph.get_neighbors(nid):
            if nnid not in direct_set:
                second_degree += 1

    # 信任度分布
    high_trust = db.query(UserRelation).filter(
        UserRelation.from_user_id == current_user.id,
        UserRelation.trust_score >= 0.7,
        UserRelation.is_active == True,
    ).count()

    medium_trust = db.query(UserRelation).filter(
        UserRelation.from_user_id == current_user.id,
        UserRelation.trust_score >= 0.4,
        UserRelation.trust_score < 0.7,
        UserRelation.is_active == True,
    ).count()

    low_trust = db.query(UserRelation).filter(
        UserRelation.from_user_id == current_user.id,
        UserRelation.trust_score < 0.4,
        UserRelation.is_active == True,
    ).count()

    return {
        "code": 200,
        "message": "success",
        "data": {
            "first_degree": first_degree,
            "second_degree": second_degree,
            "total_relations": first_degree,
            "trust_distribution": {
                "high": high_trust,
                "medium": medium_trust,
                "low": low_trust,
            },
            "network_value": round(first_degree * 1.0 + second_degree * 0.36, 2),
        },
    }


# ============================================================
# 通知触发（内部）
# ============================================================

@router.post("/notify-connection", include_in_schema=False)
async def notify_connection(
    from_user_id: int = Query(...),
    to_user_id: int = Query(...),
    path_length: int = Query(...),
    db: Session = Depends(get_db),
):
    """
    触发人脉连接通知（内部端点）

    当有人通过你的人脉链接触达你时，发送实时通知。
    """
    from app.notifications import NotificationManager

    # 通知目标用户
    message = {
        "event": "six_degree_connection",
        "data": {
            "from_user_id": from_user_id,
            "to_user_id": to_user_id,
            "path_length": path_length,
            "type": "connection",
        },
    }

    # 1. WebSocket 实时推送
    sent = await ws_manager.send_json_to_user(
        user_id=to_user_id,
        event="six_degree_connection",
        data=message["data"],
    )

    # 2. 站内通知（离线兜底）
    from_user = db.query(User).filter(User.id == from_user_id).first()
    NotificationManager.create_notification(
        user_id=to_user_id,
        type_="system",
        title="新的人脉触达",
        content=(
            f"{from_user.name if from_user else '有人'} "
            f"通过{path_length}度人脉找到了您"
        ),
        related_id=from_user_id,
    )

    return {"code": 200, "message": "sent" if sent else "queued"}


# ============================================================
# 工具函数
# ============================================================

def _user_to_brief(user: User) -> dict:
    """将User对象转为简要信息"""
    if not user:
        return None
    return {
        "user_id": user.id,
        "name": user.name,
        "company": user.company or "",
        "position": user.position or "",
        "avatar": user.avatar or "",
        "role": user.role,
    }
