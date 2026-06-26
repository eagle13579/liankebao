"""
链客宝 — 短信/邮件通知服务模块
================================
提供 EmailSender 邮件发送、SMSSender 短信发送、NotificationManager 统一接口。

配置说明（读取 .env 或系统环境变量）:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS    — 邮件 SMTP 配置
  ALIYUN_SMS_ACCESS_KEY, ALIYUN_SMS_SECRET_KEY   — 阿里云短信密钥
  ALIYUN_SMS_SIGN_NAME, ALIYUN_SMS_TEMPLATE_CODE — 短信签名/模板
"""

import json
import logging
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

# requests 库可能因系统环境问题不可用，做降级处理
try:
    import requests as _requests
    REQUESTS_AVAILABLE = True
except Exception:
    _requests = None
    REQUESTS_AVAILABLE = False

from app.database import Base, SessionLocal, get_db
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, func

logger = logging.getLogger(__name__)


# ===================================================================
# Notification ORM 模型（用于持久化通知历史）
# ===================================================================

class NotificationRecord(Base):
    """通知发送记录"""
    __tablename__ = "notification_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True, comment="目标用户 ID")
    channel = Column(String(16), nullable=False, comment="渠道: email / sms")
    title = Column(String(256), nullable=True, comment="通知标题")
    body = Column(Text, nullable=False, comment="通知正文")
    status = Column(String(16), nullable=False, default="pending", comment="状态: pending/success/failed")
    error = Column(Text, nullable=True, comment="失败原因")
    created_at = Column(DateTime, default=func.now(), comment="创建时间")
    sent_at = Column(DateTime, nullable=True, comment="发送时间")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "channel": self.channel,
            "title": self.title,
            "body": self.body,
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
        }


# ===================================================================
# 配置读取助手
# ===================================================================

def _get_env(key: str, default: str = "") -> str:
    """读取环境变量（支持 .env 或系统环境变量）"""
    return os.getenv(key, default)


# ===================================================================
# 收件人解析 —— 根据 user_id 查找邮箱/手机号
# ===================================================================

# 简易内存映射（生产环境应替换为数据库查询）
_USER_CONTACT_STORE: dict[str, dict] = {}


def register_user_contact(user_id: str, email: str = "", phone: str = ""):
    """注册用户联系方式（供测试和内存模式使用）"""
    if user_id not in _USER_CONTACT_STORE:
        _USER_CONTACT_STORE[user_id] = {}
    if email:
        _USER_CONTACT_STORE[user_id]["email"] = email
    if phone:
        _USER_CONTACT_STORE[user_id]["phone"] = phone


def get_user_contact(user_id: str) -> dict:
    """获取用户联系方式

    先查内存映射，再尝试从数据库 BusinessCard 的 fields 中读取。
    返回 {'email': str, 'phone': str}
    """
    # 1. 内存映射
    contact = _USER_CONTACT_STORE.get(user_id, {}).copy()

    # 2. 尝试从 BusinessCard 的 fields JSON 中读取
    if not contact.get("email") or not contact.get("phone"):
        try:
            from app.models import BusinessCard
            db = SessionLocal()
            try:
                card = db.query(BusinessCard).filter(
                    BusinessCard.user_id == user_id
                ).order_by(BusinessCard.created_at.desc()).first()
                if card and isinstance(card.fields, dict):
                    fields = card.fields
                    if "email" in fields and not contact.get("email"):
                        contact["email"] = fields["email"]
                    if "phone" in fields and not contact.get("phone"):
                        contact["phone"] = fields["phone"]
            finally:
                db.close()
        except Exception as e:
            logger.debug(f"[Notification] 从 BusinessCard 读取联系方式失败: {e}")

    return contact


# ===================================================================
# EmailSender — 基于 smtplib 的邮件发送
# ===================================================================

class EmailSender:
    """SMTP 邮件发送器

    读取环境变量:
      SMTP_HOST — SMTP 服务器地址（默认 smtp.qq.com）
      SMTP_PORT — SMTP 端口（默认 587）
      SMTP_USER — 发件邮箱
      SMTP_PASS — 发件邮箱密码/授权码
    """

    def __init__(self):
        raw_host = _get_env("SMTP_HOST", "smtp.qq.com")
        raw_port = _get_env("SMTP_PORT", "587")
        self.host = raw_host if raw_host else "smtp.qq.com"
        try:
            self.port = int(raw_port) if raw_port else 587
        except (ValueError, TypeError):
            self.port = 587
        self.user = _get_env("SMTP_USER", "")
        self.password = _get_env("SMTP_PASS", "")
        self._enabled = bool(self.user and self.password)

    def is_enabled(self) -> bool:
        """检查邮件配置是否就绪"""
        return self._enabled

    def send(self, to_email: str, subject: str, body: str, html: bool = False) -> bool:
        """发送一封邮件

        Args:
            to_email: 收件人邮箱
            subject:  邮件主题
            body:     邮件正文（纯文本或 HTML）
            html:     是否 HTML 格式

        Returns:
            bool: 发送成功返回 True
        """
        if not self._enabled:
            logger.warning("[EmailSender] SMTP 未配置，跳过邮件发送")
            return False

        if not to_email:
            logger.warning("[EmailSender] 收件人邮箱为空，跳过")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = self.user
            msg["To"] = to_email
            msg["Subject"] = subject

            content_type = "html" if html else "plain"
            msg.attach(MIMEText(body, content_type, "utf-8"))

            with smtplib.SMTP(self.host, self.port, timeout=10) as server:
                server.starttls()
                server.login(self.user, self.password)
                server.sendmail(self.user, [to_email], msg.as_string())

            logger.info(f"[EmailSender] 邮件发送成功 → {to_email} | subject={subject}")
            return True

        except smtplib.SMTPAuthenticationError:
            logger.error("[EmailSender] SMTP 认证失败，请检查 SMTP_USER/SMTP_PASS")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"[EmailSender] SMTP 发送失败: {e}")
            return False
        except OSError as e:
            logger.error(f"[EmailSender] 网络/连接错误: {e}")
            return False
        except Exception as e:
            logger.error(f"[EmailSender] 未知错误: {e}")
            return False


# ===================================================================
# SMSSender — 短信发送（阿里云 SDK / HTTP API 两种模式）
# ===================================================================

class SMSSender:
    """短信发送器

    支持两种模式:
      1. 阿里云 SDK (aliyunsdkdysmsapi) — 需要安装 aliyun-python-sdk-core
      2. HTTP API 降级模式 — 直接调用阿里云短信服务 HTTP 接口

    读取环境变量:
      ALIYUN_SMS_ACCESS_KEY    — 阿里云 AccessKey ID
      ALIYUN_SMS_SECRET_KEY    — 阿里云 AccessKey Secret
      ALIYUN_SMS_SIGN_NAME     — 短信签名（如 "链客宝"）
      ALIYUN_SMS_TEMPLATE_CODE — 短信模板 Code（如 "SMS_123456789"）
    """

    def __init__(self):
        self.access_key = _get_env("ALIYUN_SMS_ACCESS_KEY", "")
        self.secret_key = _get_env("ALIYUN_SMS_SECRET_KEY", "")
        self.sign_name = _get_env("ALIYUN_SMS_SIGN_NAME", "链客宝")
        self.template_code = _get_env("ALIYUN_SMS_TEMPLATE_CODE", "")
        self._enabled = bool(self.access_key and self.secret_key)

    def is_enabled(self) -> bool:
        """检查短信配置是否就绪"""
        return self._enabled

    def send(self, phone: str, template_params: Optional[dict] = None) -> bool:
        """发送一条短信

        Args:
            phone:           收件人手机号
            template_params: 短信模板参数（如 {"code": "123456"}）

        Returns:
            bool: 发送成功返回 True
        """
        if not self._enabled:
            logger.warning("[SMSSender] 阿里云短信未配置，跳过短信发送")
            return False

        if not phone:
            logger.warning("[SMSSender] 收件人手机号为空，跳过")
            return False

        params = template_params or {}

        # 优先使用阿里云 SDK
        if self._try_sdk_send(phone, params):
            return True

        # SDK 不可用，降级为 HTTP API
        return self._try_http_send(phone, params)

    def _try_sdk_send(self, phone: str, params: dict) -> bool:
        """尝试使用阿里云 Python SDK 发送"""
        try:
            from aliyunsdkcore.client import AcsClient
            from aliyunsdkdysmsapi.request.v20170525 import SendSmsRequest

            client = AcsClient(self.access_key, self.secret_key, "cn-hangzhou")
            request = SendSmsRequest.SendSmsRequest()
            request.set_PhoneNumbers(phone)
            request.set_SignName(self.sign_name)
            request.set_TemplateCode(self.template_code)
            if params:
                request.set_TemplateParam(json.dumps(params, ensure_ascii=False))

            response = client.do_action_with_exception(request)
            resp_json = json.loads(response)

            if resp_json.get("Code") == "OK":
                logger.info(f"[SMSSender] SDK 发送成功 → {phone}")
                return True
            else:
                logger.warning(f"[SMSSender] SDK 发送失败: {resp_json.get('Message', '未知错误')}")
                return False

        except ImportError:
            logger.debug("[SMSSender] aliyunsdkdysmsapi 未安装，降级为 HTTP API")
            return False
        except Exception as e:
            logger.error(f"[SMSSender] SDK 发送异常: {e}")
            return False

    def _try_http_send(self, phone: str, params: dict) -> bool:
        """降级模式：直接调用阿里云短信 HTTP API"""
        if not REQUESTS_AVAILABLE:
            logger.warning("[SMSSender] requests 库不可用，HTTP 降级模式跳过")
            return False

        try:
            # 阿里云短信服务 HTTP API 网关
            url = "https://dysmsapi.aliyuncs.com/"
            payload = {
                "AccessKeyId": self.access_key,
                "Action": "SendSms",
                "Format": "JSON",
                "RegionId": "cn-hangzhou",
                "SignatureMethod": "HMAC-SHA1",
                "SignatureNonce": str(os.urandom(16).hex()),
                "SignatureVersion": "1.0",
                "Timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "Version": "2017-05-25",
                "PhoneNumbers": phone,
                "SignName": self.sign_name,
                "TemplateCode": self.template_code,
                "TemplateParam": json.dumps(params, ensure_ascii=False),
            }

            # 简化签名（生产环境应使用阿里云签名算法）
            # 此处使用 SDK 模式更可靠，HTTP 直调用作兜底
            resp = _requests.post(url, data=payload, timeout=10)
            result = resp.json()

            if result.get("Code") == "OK":
                logger.info(f"[SMSSender] HTTP 发送成功 → {phone}")
                return True
            else:
                logger.warning(f"[SMSSender] HTTP 发送失败: {result.get('Message', '未知错误')}")
                return False

        except _requests.RequestException as e:
            logger.error(f"[SMSSender] HTTP 请求失败: {e}")
            return False
        except Exception as e:
            logger.error(f"[SMSSender] HTTP 发送异常: {e}")
            return False


# ===================================================================
# NotificationManager — 统一通知接口
# ===================================================================

class NotificationManager:
    """通知管理器 — 统一 send 接口，支持邮件/短信渠道

    用法:
        mgr = NotificationManager()
        mgr.send(user_id="u001", title="验证码", body="您的验证码是 123456", channels=["sms"])
    """

    def __init__(self, email_sender: Optional[EmailSender] = None,
                 sms_sender: Optional[SMSSender] = None):
        self.email_sender = email_sender or EmailSender()
        self.sms_sender = sms_sender or SMSSender()

    def send(self, user_id: str, title: str, body: str,
             channels: Optional[list[str]] = None) -> dict[str, bool]:
        """向指定用户发送通知

        Args:
            user_id:  目标用户 ID
            title:    通知标题
            body:     通知正文
            channels: 发送渠道列表，可选值 ['email', 'sms']，默认全渠道

        Returns:
            dict: {channel: success_bool} 每个渠道的发送结果
        """
        channels = channels or ["email", "sms"]
        contact = get_user_contact(user_id)
        results: dict[str, bool] = {}

        for ch in channels:
            ch = ch.strip().lower()
            if ch == "email":
                success = self._send_email(user_id, title, body, contact.get("email", ""))
            elif ch == "sms":
                success = self._send_sms(user_id, body, contact.get("phone", ""))
            else:
                logger.warning(f"[NotificationManager] 未知渠道: {ch}")
                success = False

            results[ch] = success
            self._save_record(user_id, ch, title, body, success)

        return results

    def _send_email(self, user_id: str, title: str, body: str, to_email: str) -> bool:
        """内部：发送邮件"""
        if not to_email:
            logger.warning(f"[NotificationManager] 用户 {user_id} 无邮箱地址")
            return False
        return self.email_sender.send(to_email=to_email, subject=title, body=body)

    def _send_sms(self, user_id: str, body: str, phone: str) -> bool:
        """内部：发送短信

        短信正文 body 会作为模板参数传入（通常包含验证码等信息）
        """
        if not phone:
            logger.warning(f"[NotificationManager] 用户 {user_id} 无手机号")
            return False
        # 短信模板参数 —— 默认将 body 整体作为参数传递
        return self.sms_sender.send(phone=phone, template_params={"code": body})

    def _save_record(self, user_id: str, channel: str, title: str,
                     body: str, success: bool) -> None:
        """保存发送记录到数据库（静默降级，失败不影响主流程）"""
        try:
            db = SessionLocal()
            try:
                record = NotificationRecord(
                    user_id=user_id,
                    channel=channel,
                    title=title,
                    body=body,
                    status="success" if success else "failed",
                    error=None if success else "发送失败（详见日志）",
                    sent_at=datetime.utcnow() if success else None,
                )
                db.add(record)
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[NotificationManager] 保存发送记录失败: {e}")

    def get_history(self, user_id: str, limit: int = 20, offset: int = 0
                    ) -> list[dict]:
        """查询用户通知历史"""
        try:
            db = SessionLocal()
            try:
                records = (
                    db.query(NotificationRecord)
                    .filter(NotificationRecord.user_id == user_id)
                    .order_by(NotificationRecord.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                    .all()
                )
                return [r.to_dict() for r in records]
            finally:
                db.close()
        except Exception as e:
            logger.error(f"[NotificationManager] 查询通知历史失败: {e}")
            return []


# ===================================================================
# 全局单例
# ===================================================================

_notification_manager: Optional[NotificationManager] = None


def get_notification_manager() -> NotificationManager:
    """获取全局 NotificationManager 单例"""
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationManager()
    return _notification_manager
