"""
企业知识图谱 API 路由

提供企业库的 CRUD、搜索、关系图谱管理、以及公域数据采集补全接口。
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.enterprise_crawler import crawl_enterprise_relations, enrich_enterprise
from app.models import Enterprise, EnterpriseRelation, User
from app.schemas import (
    ApiResponse,
    EnterpriseCreate,
    EnterpriseEnrichRequest,
    EnterpriseRelationCreate,
    EnterpriseRelationResponse,
    EnterpriseResponse,
    EnterpriseUpdate,
    PaginatedData,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/enterprise", tags=["企业库"])


# ============================================================
# 工具函数
# ============================================================


def _enterprise_to_dict(ent: Enterprise) -> dict:
    """Enterprise ORM 对象转字典（含关系图谱）"""
    return {
        "id": ent.id,
        "name": ent.name,
        "short_name": ent.short_name,
        "credit_code": ent.credit_code,
        "legal_person": ent.legal_person,
        "registered_capital": ent.registered_capital,
        "established_date": ent.established_date,
        "industry": ent.industry,
        "region": ent.region,
        "business_scope": ent.business_scope,
        "tags": ent.tags,
        "website": ent.website,
        "data_source": ent.data_source,
        "confidence": ent.confidence,
        "extra": ent.extra,
        "created_at": ent.created_at.isoformat() if ent.created_at else None,
        "updated_at": ent.updated_at.isoformat() if ent.updated_at else None,
    }


def _relation_to_dict(rel: EnterpriseRelation) -> dict:
    """EnterpriseRelation ORM 对象转字典"""
    return {
        "id": rel.id,
        "source_id": rel.source_id,
        "target_id": rel.target_id,
        "relation_type": rel.relation_type,
        "relation_label": rel.relation_label,
        "confidence": rel.confidence,
        "source": rel.source,
        "created_at": rel.created_at.isoformat() if rel.created_at else None,
    }


def _build_relation_graph(ent: Enterprise) -> dict:
    """构建企业关系图谱（含源和目标关系，含对方企业简要信息）"""
    relations_out = []
    for rel in ent.source_relations:
        target = rel.target_enterprise
        relations_out.append(
            {
                "direction": "out",
                "relation_type": rel.relation_type,
                "relation_label": rel.relation_label,
                "confidence": rel.confidence,
                "target": {
                    "id": target.id,
                    "name": target.name,
                    "short_name": target.short_name,
                    "industry": target.industry,
                    "region": target.region,
                }
                if target
                else None,
            }
        )

    relations_in = []
    for rel in ent.target_relations:
        source = rel.source_enterprise
        relations_in.append(
            {
                "direction": "in",
                "relation_type": rel.relation_type,
                "relation_label": rel.relation_label,
                "confidence": rel.confidence,
                "source": {
                    "id": source.id,
                    "name": source.name,
                    "short_name": source.short_name,
                    "industry": source.industry,
                    "region": source.region,
                }
                if source
                else None,
            }
        )

    return {"outgoing": relations_out, "incoming": relations_in}


# ============================================================
# API 端点
# ============================================================


@router.get("/search", response_model=ApiResponse)
def search_enterprises(
    q: str = Query("", description="搜索关键词（企业名称/法人/信用代码）"),
    industry: str | None = Query(None, description="行业筛选"),
    region: str | None = Query(None, description="地区筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
):
    """企业搜索

    支持按关键词、行业、地区多维度筛选，分页返回。
    关键词模糊匹配：企业名称、法定代表人、统一社会信用代码。
    """
    query = db.query(Enterprise)

    if q and q.strip():
        keyword = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Enterprise.name.ilike(keyword),
                Enterprise.legal_person.ilike(keyword),
                Enterprise.credit_code.ilike(keyword),
                Enterprise.short_name.ilike(keyword),
            )
        )

    if industry:
        query = query.filter(Enterprise.industry.ilike(f"%{industry}%"))

    if region:
        query = query.filter(Enterprise.region.ilike(f"%{region}%"))

    # 统计总数
    total = query.count()

    # 分页
    query = query.order_by(Enterprise.updated_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    enterprises = query.all()

    return {
        "code": 200,
        "message": "success",
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [_enterprise_to_dict(e) for e in enterprises],
        },
    }


@router.get("/{enterprise_id}", response_model=ApiResponse)
def get_enterprise(
    enterprise_id: int,
    db: Session = Depends(get_db),
):
    """企业详情（含关系图谱）

    返回企业完整信息及其上下游关系图谱。
    """
    ent = db.query(Enterprise).filter(Enterprise.id == enterprise_id).first()
    if not ent:
        raise HTTPException(status_code=404, detail="企业不存在")

    result = _enterprise_to_dict(ent)
    result["relation_graph"] = _build_relation_graph(ent)

    return {"code": 200, "message": "success", "data": result}


@router.post("", response_model=ApiResponse)
def create_enterprise(
    data: EnterpriseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动创建企业（管理员权限）"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    # 查重：统一社会信用代码或企业名称
    if data.credit_code:
        exist = (
            db.query(Enterprise)
            .filter(Enterprise.credit_code == data.credit_code)
            .first()
        )
        if exist:
            raise HTTPException(status_code=409, detail="该统一社会信用代码已存在")

    exist_name = (
        db.query(Enterprise).filter(Enterprise.name == data.name).first()
    )
    if exist_name:
        raise HTTPException(status_code=409, detail="该企业名称已存在")

    ent = Enterprise(
        name=data.name,
        short_name=data.short_name,
        credit_code=data.credit_code,
        legal_person=data.legal_person,
        registered_capital=data.registered_capital,
        established_date=data.established_date,
        industry=data.industry,
        region=data.region,
        business_scope=data.business_scope,
        tags=data.tags,
        website=data.website,
        data_source=data.data_source,
        confidence=data.confidence,
        extra=data.extra,
    )
    db.add(ent)
    db.commit()
    db.refresh(ent)

    logger.info(f"企业创建成功: id={ent.id}, name={ent.name}, user={current_user.id}")

    return {
        "code": 201,
        "message": "企业创建成功",
        "data": _enterprise_to_dict(ent),
    }


@router.put("/{enterprise_id}", response_model=ApiResponse)
def update_enterprise(
    enterprise_id: int,
    data: EnterpriseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新企业信息（管理员权限）"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    ent = db.query(Enterprise).filter(Enterprise.id == enterprise_id).first()
    if not ent:
        raise HTTPException(status_code=404, detail="企业不存在")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(ent, field, value)

    db.commit()
    db.refresh(ent)

    return {
        "code": 200,
        "message": "企业信息已更新",
        "data": _enterprise_to_dict(ent),
    }


@router.delete("/{enterprise_id}", response_model=ApiResponse)
def delete_enterprise(
    enterprise_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除企业（管理员权限，级联删除关联关系）"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    ent = db.query(Enterprise).filter(Enterprise.id == enterprise_id).first()
    if not ent:
        raise HTTPException(status_code=404, detail="企业不存在")

    db.delete(ent)
    db.commit()

    return {"code": 200, "message": "企业已删除"}


@router.post("/{enterprise_id}/relation", response_model=ApiResponse)
def add_enterprise_relation(
    enterprise_id: int,
    data: EnterpriseRelationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """添加企业关系

    在 source_id=enterprise_id 和目标企业之间建立关系。
    """
    # 验证源企业存在
    source = (
        db.query(Enterprise).filter(Enterprise.id == enterprise_id).first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="源企业不存在")

    # 验证目标企业存在
    target = (
        db.query(Enterprise).filter(Enterprise.id == data.target_id).first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="目标企业不存在")

    # 查重：避免重复创建相同关系
    exist = (
        db.query(EnterpriseRelation)
        .filter(
            EnterpriseRelation.source_id == enterprise_id,
            EnterpriseRelation.target_id == data.target_id,
            EnterpriseRelation.relation_type == data.relation_type,
        )
        .first()
    )
    if exist:
        raise HTTPException(status_code=409, detail="该关系已存在")

    rel = EnterpriseRelation(
        source_id=enterprise_id,
        target_id=data.target_id,
        relation_type=data.relation_type,
        relation_label=data.relation_label,
        confidence=data.confidence,
        source=data.source,
    )
    db.add(rel)
    db.commit()
    db.refresh(rel)

    return {
        "code": 201,
        "message": "企业关系添加成功",
        "data": _relation_to_dict(rel),
    }


@router.get("/{enterprise_id}/relations", response_model=ApiResponse)
def get_enterprise_relations(
    enterprise_id: int,
    db: Session = Depends(get_db),
):
    """获取企业关系图谱

    返回该企业的所有出向和入向关系。
    """
    ent = db.query(Enterprise).filter(Enterprise.id == enterprise_id).first()
    if not ent:
        raise HTTPException(status_code=404, detail="企业不存在")

    return {
        "code": 200,
        "message": "success",
        "data": _build_relation_graph(ent),
    }


@router.delete("/{enterprise_id}/relation/{relation_id}", response_model=ApiResponse)
def delete_enterprise_relation(
    enterprise_id: int,
    relation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除企业关系（管理员权限）"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    rel = (
        db.query(EnterpriseRelation)
        .filter(
            EnterpriseRelation.id == relation_id,
            EnterpriseRelation.source_id == enterprise_id,
        )
        .first()
    )
    if not rel:
        raise HTTPException(status_code=404, detail="关系不存在")

    db.delete(rel)
    db.commit()

    return {"code": 200, "message": "企业关系已删除"}


@router.post("/enrich", response_model=ApiResponse)
def enrich_enterprise_info(
    data: EnterpriseEnrichRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """根据企业名自动补全信息（调用公域采集引擎）

    流程：
    1. 查本地库，已有则直接返回
    2. 调用采集引擎从天眼查/企查查等公开渠道抓取
    3. 自动写入本地库，返回补全后的企业信息
    """
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="企业名称不能为空")

    # 1. 先查本地库
    existing = (
        db.query(Enterprise).filter(Enterprise.name == name).first()
    )
    if existing:
        logger.info(f"本地库命中企业: {name}, id={existing.id}")
        result = _enterprise_to_dict(existing)
        result["relation_graph"] = _build_relation_graph(existing)
        return {"code": 200, "message": "已从本地库获取", "data": result}

    # 2. 调采集引擎
    crawled = enrich_enterprise(name)
    if not crawled or crawled.get("confidence", 0) == 0:
        return {
            "code": 404,
            "message": "未从公开渠道找到该企业信息，请手动创建",
            "data": {"name": name},
        }

    # 3. 自动写入本地库
    ent = Enterprise(
        name=crawled.get("name", name),
        short_name=crawled.get("short_name"),
        credit_code=crawled.get("credit_code"),
        legal_person=crawled.get("legal_person"),
        registered_capital=crawled.get("registered_capital"),
        established_date=crawled.get("established_date"),
        industry=crawled.get("industry"),
        region=crawled.get("region"),
        business_scope=crawled.get("business_scope"),
        tags=crawled.get("tags"),
        website=crawled.get("website"),
        data_source=crawled.get("data_source", "crawl"),
        confidence=crawled.get("confidence", 40),
        extra=crawled.get("_raw_json"),
    )
    db.add(ent)
    db.commit()
    db.refresh(ent)

    logger.info(
        f"企业采集补全成功: id={ent.id}, name={ent.name}, "
        f"confidence={ent.confidence}, user={current_user.id}"
    )

    # 异步尝试采集关系（不阻塞响应）
    try:
        import threading

        def _async_crawl_relations():
            relations = crawl_enterprise_relations(ent.id, ent.name)
            if relations:
                _save_crawled_relations(db, ent.id, relations)

        thread = threading.Thread(target=_async_crawl_relations, daemon=True)
        thread.start()
    except Exception as e:
        logger.debug(f"异步关系采集启动失败: {e}")

    result = _enterprise_to_dict(ent)
    return {
        "code": 201,
        "message": "企业信息采集补全成功",
        "data": result,
    }


def _save_crawled_relations(db: Session, source_id: int, relations: list[dict]):
    """将采集到的关系保存到本地库（仅保存目标企业在本地已存在的情况）"""
    saved_count = 0
    for rel in relations:
        target_name = rel.get("target_name", "")
        if not target_name:
            continue

        # 尝试在本地查找目标企业
        target = (
            db.query(Enterprise)
            .filter(Enterprise.name.ilike(f"%{target_name}%"))
            .first()
        )
        if not target:
            # 目标企业不在本地库，跳过
            continue

        # 查重
        exist = (
            db.query(EnterpriseRelation)
            .filter(
                EnterpriseRelation.source_id == source_id,
                EnterpriseRelation.target_id == target.id,
                EnterpriseRelation.relation_type == rel["relation_type"],
            )
            .first()
        )
        if exist:
            continue

        er = EnterpriseRelation(
            source_id=source_id,
            target_id=target.id,
            relation_type=rel["relation_type"],
            relation_label=rel.get("relation_label"),
            confidence=rel.get("confidence", 30),
            source=rel.get("source", "crawl"),
        )
        db.add(er)
        saved_count += 1

    if saved_count > 0:
        db.commit()
        logger.info(
            f"异步保存采集关系完成: source_id={source_id}, saved={saved_count}"
        )
