"""
WebSocket 连接管理器
基于 FastAPI WebSocket，管理多用户实时推送
"""
import asyncio
import json
import logging
from typing import Dict, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    WebSocket 连接管理器

    用法：
        manager = ConnectionManager()

        # 在 websocket 路由中：
        @app.websocket("/ws/{user_id}")
        async def websocket_endpoint(websocket: WebSocket, user_id: int):
            await manager.connect(websocket, user_id)
            try:
                while True:
                    data = await websocket.receive_text()
                    # 处理客户端消息 ...
            except WebSocketDisconnect:
                manager.disconnect(user_id)
    """

    def __init__(self):
        # user_id -> set of WebSocket connections (一个用户多设备/多tab)
        self._connections: Dict[int, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    # ---- 公开属性 ----

    @property
    def online_users(self) -> int:
        """当前在线用户数"""
        return len(self._connections)

    @property
    def active_connections(self) -> int:
        """当前活跃连接数"""
        return sum(len(ws_set) for ws_set in self._connections.values())

    # ---- 连接管理 ----

    async def connect(self, websocket: WebSocket, user_id: int):
        """
        接受 WebSocket 连接并将用户加入管理

        Args:
            websocket: FastAPI WebSocket 实例
            user_id:   用户ID
        """
        await websocket.accept()
        async with self._lock:
            if user_id not in self._connections:
                self._connections[user_id] = set()
            self._connections[user_id].add(websocket)

        logger.info(
            "WebSocket 连接已建立",
            extra={
                "user_id": user_id,
                "online_users": self.online_users,
                "active_connections": self.active_connections,
            },
        )

    async def disconnect(self, user_id: int, websocket: Optional[WebSocket] = None):
        """
        断开用户连接

        Args:
            user_id:    用户ID
            websocket:  指定要断开的 WebSocket（None 则断开该用户所有连接）
        """
        async with self._lock:
            if user_id not in self._connections:
                return

            if websocket is not None:
                self._connections[user_id].discard(websocket)
                if not self._connections[user_id]:
                    del self._connections[user_id]
            else:
                # 关闭所有该用户的连接
                for ws in self._connections[user_id]:
                    try:
                        await ws.close()
                    except Exception:
                        pass
                del self._connections[user_id]

        logger.info(
            "WebSocket 连接已断开",
            extra={
                "user_id": user_id,
                "online_users": self.online_users,
                "active_connections": self.active_connections,
            },
        )

    def is_online(self, user_id: int) -> bool:
        """检查用户是否在线"""
        return user_id in self._connections and bool(self._connections[user_id])

    # ---- 消息发送 ----

    async def send_to_user(
        self, user_id: int, message: dict, raise_on_disconnect: bool = False
    ) -> bool:
        """
        向指定用户推送消息（发送到该用户所有连接）

        Args:
            user_id:             目标用户ID
            message:             消息字典（会被 JSON 序列化）
            raise_on_disconnect: 断开时是否抛出异常（默认静默处理）

        Returns:
            True 如果至少成功发送到一条连接
        """
        if user_id not in self._connections:
            return False

        payload = json.dumps(message, ensure_ascii=False)
        sent = False
        disconnected_ws = []

        async with self._lock:
            ws_set = self._connections.get(user_id)
            if not ws_set:
                return False

            for ws in list(ws_set):
                try:
                    await ws.send_text(payload)
                    sent = True
                except Exception as exc:
                    logger.warning(
                        "WebSocket 发送失败，移除连接",
                        extra={
                            "user_id": user_id,
                            "error": str(exc),
                        },
                    )
                    disconnected_ws.append(ws)

            # 清理已断开的连接
            for ws in disconnected_ws:
                ws_set.discard(ws)
            if not ws_set:
                del self._connections[user_id]

        return sent

    async def broadcast(self, message: dict):
        """
        广播消息给所有在线用户

        Args:
            message: 消息字典
        """
        payload = json.dumps(message, ensure_ascii=False)
        disconnected = []

        async with self._lock:
            for user_id, ws_set in list(self._connections.items()):
                for ws in list(ws_set):
                    try:
                        await ws.send_text(payload)
                    except Exception:
                        disconnected.append((user_id, ws))

            # 清理断开的连接
            for uid, ws in disconnected:
                ws_set = self._connections.get(uid)
                if ws_set:
                    ws_set.discard(ws)
                    if not ws_set:
                        del self._connections[uid]

        if disconnected:
            logger.info(
                "广播完成，已清理断线连接",
                extra={"cleaned": len(disconnected)},
            )

    async def send_json_to_user(
        self,
        user_id: int,
        event: str,
        data: dict,
    ) -> bool:
        """
        便捷方法：向用户发送结构化事件消息

        Args:
            user_id: 目标用户ID
            event:   事件名（如 "notification", "order_update"）
            data:    事件数据

        Returns:
            True 如果发送成功
        """
        return await self.send_to_user(user_id, {"event": event, "data": data})


# ---- 全局单例 ----
ws_manager = ConnectionManager()
