"""
六度人脉 — WebSocket 实时通知端点

提供实时人脉触达通知、路径发现推送等能力。
"""
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth import decode_access_token
from app.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/six-degrees")
async def six_degrees_websocket(websocket: WebSocket):
    """
    六度人脉 WebSocket 端点

    连接方式：
        ws://host:port/ws/six-degrees?token=<JWT_TOKEN>

    消息格式（服务端 → 客户端）：
        {
            "event": "connection",           # 事件类型
            "data": {
                "from_user_id": 123,
                "from_user_name": "张三",
                "path_length": 2,
                "trust_score": 0.36,
                "type": "incoming"           # incoming/outgoing
            }
        }

    消息格式（客户端 → 服务端）：
        {"type": "ping"}                     # 心跳
        {"type": "subscribe", "target_user_id": 456}  # 订阅某人脉动态
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    # 验证 token
    try:
        payload = decode_access_token(token)
        user_id = payload.get("user_id")
        if not user_id:
            await websocket.close(code=4001, reason="Invalid token")
            return
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    # 接受连接
    await ws_manager.connect(websocket, user_id)

    # 发送欢迎消息
    await websocket.send_json({
        "event": "connected",
        "data": {
            "user_id": user_id,
            "message": "六度人脉实时通知已连接",
        },
    })

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"event": "pong"})

            elif msg_type == "subscribe":
                # 订阅目标用户的人脉动态（后续扩展）
                target_user_id = msg.get("target_user_id")
                if target_user_id:
                    logger.info(
                        f"User {user_id} subscribed to {target_user_id}'s network"
                    )

    except WebSocketDisconnect:
        logger.info(f"六度人脉 WebSocket 断开: user_id={user_id}")
    except Exception as exc:
        logger.warning(
            f"六度人脉 WebSocket 异常: user_id={user_id}, error={exc}"
        )
    finally:
        await ws_manager.disconnect(user_id, websocket)
