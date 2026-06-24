"""
名片同步钩子 — 将 BusinessCard 同步至 BROCHURE_SYNC_STORE
供 brochure_bridge 实时读取

BROCHURE_SYNC_STORE: data/brochure_sync_store.json
"""

import json
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

SYNC_STORE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "brochure_sync_store.json",
)


def _load_store() -> dict:
    """加载同步存储"""
    if not os.path.exists(SYNC_STORE_PATH):
        return {"cards": [], "last_sync": None}
    try:
        with open(SYNC_STORE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"cards": [], "last_sync": None}


def _save_store(store: dict):
    """保存同步存储"""
    os.makedirs(os.path.dirname(SYNC_STORE_PATH), exist_ok=True)
    with open(SYNC_STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def init_models():
    """初始化同步存储（如果不存在）"""
    if not os.path.exists(SYNC_STORE_PATH):
        _save_store({"cards": [], "last_sync": None})
        logger.info(f"BROCHURE_SYNC_STORE 已初始化: {SYNC_STORE_PATH}")


def sync_brochure_from_card(card) -> bool:
    """
    将 BusinessCard 对象同步至 BROCHURE_SYNC_STORE。
    由 generate_card() 在末尾自动调用。
    """
    try:
        store = _load_store()

        # 提取名片数据
        card_data = {
            "id": getattr(card, "id", None),
            "user_id": getattr(card, "user_id", None),
            "fields": getattr(card, "fields", {}),
            "share_token": getattr(card, "share_token", None),
            "cover_image": getattr(card, "cover_image", None),
            "view_count": getattr(card, "view_count", 0),
            "created_at": (
                card.created_at.isoformat()
                if hasattr(card, "created_at") and card.created_at
                else datetime.utcnow().isoformat()
            ),
        }

        # 去重更新
        existing_ids = [c["id"] for c in store["cards"]]
        if card_data["id"] in existing_ids:
            idx = existing_ids.index(card_data["id"])
            store["cards"][idx] = card_data
        else:
            store["cards"].append(card_data)

        store["last_sync"] = datetime.utcnow().isoformat()
        _save_store(store)
        return True
    except Exception as e:
        logger.warning(f"BROCHURE_SYNC_STORE 同步失败: {e}")
        return False
