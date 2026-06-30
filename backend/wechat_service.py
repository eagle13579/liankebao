"""
链客宝 - 微信独立服务 (无数据库依赖)
提供: 扫码登录 / OAuth / JS-SDK 配置
"""
import logging, os, time, uuid
from fastapi import FastAPI, HTTPException, Query, Response
import io, qrcode
from pydantic import BaseModel
from app.wechat_sdk import WeChatOAuth

logging.basicConfig(level=logging.INFO)
app = FastAPI(title='链客宝-微信服务')

# ── 扫码登录会话存储（内存）──
_qr_sessions: dict = {}

class QRSession:
    def __init__(self):
        self.session_id = uuid.uuid4().hex[:16]
        self.created_at = time.time()
        self.expires_at = time.time() + 300
        self.status = "pending"
        self.openid = ""

@app.get('/health')
async def health():
    return {'status': 'ok', 'service': 'wechat'}

@app.get('/api/wechat/health')
async def api_health():
    return {'status': 'ok', 'service': 'wechat-独立服务'}

# ── 1. 创建扫码登录会话 ──
@app.post('/api/wechat/qr-session')
async def create_qr_session():
    session = QRSession()
    _qr_sessions[session.session_id] = session
    qr_content = f"https://liankebao.top/wechat-bridge?session={session.session_id}"
    qr_url = f"/api/wechat/qr-image?session_id={session.session_id}"
    return {
        "session_id": session.session_id,
        "qr_url": qr_url,
        "expires_in": 300,
        "bridge_url": qr_content,
    }

# ── 2. PC端轮询状态 ──
@app.get('/api/wechat/qr-session/{session_id}')
async def check_qr_session(session_id: str):
    session = _qr_sessions.get(session_id)
    if not session:
        return {"status": "expired", "message": "会话不存在"}
    if time.time() > session.expires_at:
        session.status = "expired"
        return {"status": "expired", "message": "二维码已过期"}
    result = {"status": session.status}
    if session.status == "completed" and session.openid:
        result["token"] = f"qr_{session.openid}"
        result["openid"] = session.openid
    return result

# ── 3. 手机端OAuth回调 ──
@app.get('/api/wechat/bridge/callback')
async def bridge_callback(session_id: str = Query(...), code: str = Query(...), state: str = ""):
    """手机扫码后在微信内完成OAuth"""
    session = _qr_sessions.get(session_id)
    if not session or session.status != "pending":
        return {"status": "error", "message": "会话无效或已过期"}
    try:
        oauth = WeChatOAuth()
        token_data = oauth.get_access_token(code)
        session.openid = token_data["openid"]
        session.status = "completed"
        return {"status": "ok", "message": "登录成功"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ── 4. JS-SDK 配置 ──
class JSConfigReq(BaseModel):
    url: str

@app.post('/api/wechat/js-config')
async def js_config(req: JSConfigReq):
    from app.wechat_sdk import WeChatJSConfig
    config = WeChatJSConfig().get_config(req.url)
    return {"appid": config.appid, "noncestr": config.noncestr,
            "timestamp": config.timestamp, "signature": config.signature}

# ── 5. qrconnect 扫码登录URL ──
class QrConnectReq(BaseModel):
    redirect_uri: str
    state: str = ""

class QrConnectResp(BaseModel):
    url: str
    appid: str

@app.post('/api/wechat/qrconnect-url')
async def get_qrconnect_url(req: QrConnectReq):
    try:
        oauth = WeChatOAuth.for_qrconnect()
        url = oauth.get_qrconnect_url(req.redirect_uri, req.state)
        return QrConnectResp(url=url, appid=oauth.appid)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── 6. OAuth 登录 ──
class OAuthLoginReq(BaseModel):
    code: str
    state: str = ""

@app.get('/api/wechat/qr-image')
async def qr_image(session_id: str = Query(...)):
    """返回二维码PNG图片"""
    data = f'https://liankebao.top/wechat-bridge?session={session_id}'
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return Response(content=buf.getvalue(), media_type='image/png')

@app.post('/api/wechat/oauth/login')
async def oauth_login(req: OAuthLoginReq):
    try:
        oauth = WeChatOAuth()
        token = oauth.get_access_token(req.code)
        user = oauth.get_userinfo(token['access_token'], token['openid'])
        return {
            'openid': user.openid, 'nickname': user.nickname,
            'headimgurl': user.headimgurl, 'unionid': user.unionid,
            'sex': user.sex, 'province': user.province, 'city': user.city,
        }
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
