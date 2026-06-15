"""
乐观锁工具模块
=============
提供乐观锁冲突检测和版本更新辅助函数。

用法示例：
    obj = db.query(Product).filter(Product.id == product_id).first()
    check_version(obj, request.version, "Product")
    # ... 更新字段 ...
    obj.name = new_name
    increment_version(obj)
    db.commit()
"""

from fastapi import HTTPException, status
from sqlalchemy import BigInteger
from sqlalchemy.orm import Session


def check_version(obj, client_version: int, model_name: str = "资源"):
    """
    检查客户端提供的 version 是否与服务端一致。
    不一致时抛出 409 Conflict。
    """
    if client_version is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 400, "message": "缺少 version 字段，请先获取最新数据"},
        )
    if not hasattr(obj, "version"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": 500, "message": f"{model_name} 不支持乐观锁"},
        )
    if obj.version != client_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": 409,
                "message": f"{model_name}已被其他用户修改，请刷新后重试",
                "server_version": obj.version,
                "client_version": client_version,
            },
        )


def increment_version(obj):
    """
    原子性地递增 version 字段。
    需要在 db.commit() 之前调用。
    """
    obj.version = BigInteger(obj.version) + 1


def safe_update(db: Session, obj, update_data: dict, client_version: int, model_name: str = "资源"):
    """
    乐观锁安全更新辅助函数 —— 检查 version → 更新字段 → 递增 version → commit。

    返回更新后的对象。

    用法示例：
        updated = safe_update(db, product, {"name": "新名称", "price": 99.0}, request.version, "Product")
    """
    check_version(obj, client_version, model_name)

    for field, value in update_data.items():
        if value is not None and hasattr(obj, field):
            setattr(obj, field, value)

    increment_version(obj)
    db.commit()
    db.refresh(obj)
    return obj
