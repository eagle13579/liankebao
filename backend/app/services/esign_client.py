"""
e签宝电子签约 API 客户端
===========================
封装 e签宝开放平台 (open.esign.cn) 的认证、签名、请求逻辑。

核心流程:
  1. 使用 AppKey + AppSecret 获取 AccessToken（自动缓存/刷新）
  2. 创建合同模板 → 填充模板变量 → 发起签署流程 → 获取签署链接
  3. 查询签署状态 → 处理回调通知

环境变量:
  - ESIGN_APP_KEY        — e签宝应用 AppKey
  - ESIGN_APP_SECRET     — e签宝应用 AppSecret
  - ESIGN_HOST           — e签宝 API 地址 (默认 https://open.esign.cn)

支持签署方类型:
  - 企业签署 (PSN_FIRM)    — 需传入企业名称 + 统一社会信用代码
  - 个人签署 (PSN_PERSON)  — 需传入个人姓名 + 身份证号/手机号

签署链接模式:
  - H5嵌入 (H5)           — 返回 URL，前端 iframe 嵌入
  - 直接访问 (URL)        — 浏览器新标签页打开
"""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 环境变量默认值
# ──────────────────────────────────────────────
ESIGN_APP_KEY = os.environ.get("ESIGN_APP_KEY", "")
ESIGN_APP_SECRET = os.environ.get("ESIGN_APP_SECRET", "")
ESIGN_HOST = os.environ.get("ESIGN_HOST", "https://open.esign.cn")


# ──────────────────────────────────────────────
# 数据模型
# ──────────────────────────────────────────────


@dataclass
class EsignSigner:
    """签署方信息"""

    name: str  # 签署方名称（企业名/个人姓名）
    id_number: str = ""  # 证件号（统一社会信用代码/身份证号）
    mobile: str = ""  # 手机号
    signer_type: str = "PSN_PERSON"  # PSN_FIRM=企业, PSN_PERSON=个人
    org_name: str = ""  # 企业名称（企业签署时必填）
    email: str = ""  # 邮箱（可选）


@dataclass
class EsignTemplateField:
    """模板填充字段"""

    name: str  # 字段名称（模板中定义的占位符名称）
    value: str  # 填充值


@dataclass
class EsignContractConfig:
    """发起签署的配置参数"""

    template_id: str  # 合同模板 ID
    signers: list[EsignSigner] = field(default_factory=list)  # 签署方列表
    fields: list[EsignTemplateField] = field(default_factory=list)  # 模板填充字段
    contract_name: str = ""  # 合同名称（默认取模板名称）
    expire_days: int = 30  # 签署有效期（天）
    auto_archive: bool = True  # 签署完成后是否自动归档


# ──────────────────────────────────────────────
# API 客户端
# ──────────────────────────────────────────────


class EsignClient:
    """
    e签宝 API 客户端

    用法:
        client = EsignClient()
        token = client.get_access_token()
        templates = client.list_templates()
        template = client.create_template(name="...", doc_pdf=...)
        contract = client.create_contract(config=...)
        link = client.get_sign_link(contract_id=..., signer_account_id=...)
        status = client.query_contract(contract_id=...)
    """

    def __init__(
        self,
        app_key: str | None = None,
        app_secret: str | None = None,
        host: str | None = None,
    ):
        """
        初始化 e签宝客户端

        Args:
            app_key: e签宝 AppKey（默认读取 ESIGN_APP_KEY 环境变量）
            app_secret: e签宝 AppSecret（默认读取 ESIGN_APP_SECRET 环境变量）
            host: API 地址（默认读取 ESIGN_HOST 环境变量，兜底 https://open.esign.cn）
        """
        self.app_key = app_key or ESIGN_APP_KEY
        self.app_secret = app_secret or ESIGN_APP_SECRET
        self.host = (host or ESIGN_HOST).rstrip("/")

        if not self.app_key or not self.app_secret:
            logger.warning("e签宝 API 密钥未配置: 请设置 ESIGN_APP_KEY 和 ESIGN_APP_SECRET 环境变量")

        # AccessToken 缓存
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0  # 过期时间戳

        # HTTP 会话（复用连接池）
        self._session = requests.Session()
        self._session.headers.update(
            {
                "X-OPEN-APP-KEY": self.app_key,
                "Content-Type": "application/json;charset=utf-8",
                "Accept": "application/json",
            }
        )

    # ── 认证 ──────────────────────────────────

    def get_access_token(self) -> str:
        """
        获取 AccessToken（自动缓存，过期自动刷新）

        Returns:
            AccessToken 字符串

        Raises:
            EsignError: 认证失败或网络异常
        """
        # 缓存有效期内直接返回
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token

        url = f"{self.host}/open/api/v2/access/getAccessToken"
        payload = {"openAppKey": self.app_key, "openAppSecret": self.app_secret}

        try:
            resp = self._session.post(url, json=payload, timeout=15)
            data = self._handle_response(resp)
            self._access_token = data["token"]
            # 默认过期时间 7200 秒（2小时），安全起见-60秒
            expires_in = int(data.get("expiresIn", 7200))
            self._token_expires_at = time.time() + expires_in - 60
            logger.info("e签宝 AccessToken 获取成功（有效期 %ds）", expires_in)
            return self._access_token  # type: ignore[return-value]
        except requests.RequestException as e:
            raise EsignError(f"获取 AccessToken 网络请求失败: {e}") from e

    def _refresh_token_if_needed(self) -> str:
        """检查并刷新 Token（内部调用）"""
        return self.get_access_token()

    # ── 请求封装 ──────────────────────────────

    def _build_headers(self) -> dict[str, str]:
        """构建带 AccessToken 的请求头"""
        token = self._refresh_token_if_needed()
        return {"X-OPEN-TOKEN": token}

    def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json_data: dict | None = None,
        files: dict | None = None,
    ) -> dict[str, Any]:
        """
        通用 API 请求封装

        Args:
            method: HTTP 方法 (GET/POST/PUT/DELETE)
            path: API 路径（例如 /open/api/v2/templates）
            params: URL 查询参数
            json_data: JSON 请求体
            files: 文件上传（用于创建模板上传 PDF）

        Returns:
            API 响应 JSON 中的 data 字段

        Raises:
            EsignError: API 返回错误码或网络异常
        """
        url = f"{self.host}{path}"
        headers = self._build_headers()

        try:
            if files:
                # 文件上传 — 使用 multipart/form-data
                headers.pop("Content-Type", None)
                resp = self._session.request(
                    method, url, params=params, data=json_data, files=files, headers=headers, timeout=60
                )
            else:
                resp = self._session.request(method, url, params=params, json=json_data, headers=headers, timeout=30)
            return self._handle_response(resp)
        except requests.RequestException as e:
            raise EsignError(f"API 请求失败 [{method} {path}]: {e}") from e

    @staticmethod
    def _handle_response(resp: requests.Response) -> dict[str, Any]:
        """
        统一处理 API 响应

        e签宝标准响应格式:
            {
                "code": 0,            # 0=成功，非0=错误
                "message": "成功",
                "data": { ... },      # 业务数据
                "result": { ... }     # 部分接口使用 result
            }

        Returns:
            合并后的 data/result 字典

        Raises:
            EsignError: 响应 code ≠ 0
        """
        try:
            body = resp.json()
        except json.JSONDecodeError as e:
            raise EsignError(f"API 响应非 JSON 格式 (HTTP {resp.status_code}): {resp.text[:500]}") from e

        code = body.get("code", -1)
        if code != 0:
            message = body.get("message", "未知错误")
            raise EsignError(
                f"e签宝 API 错误 [code={code}]: {message}",
                code=code,
                message=message,
                response=body,
            )

        # 兼容 data 和 result 两种字段名
        return body.get("data") or body.get("result") or {}

    # ── 模板管理 ──────────────────────────────

    def create_template(
        self,
        name: str,
        doc_pdf: bytes,
        doc_file_name: str = "contract.pdf",
        fields: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """
        创建合同模板（上传 PDF + 定义填充字段）

        Args:
            name: 模板名称
            doc_pdf: PDF 文件二进制内容
            doc_file_name: PDF 文件名（默认 contract.pdf）
            fields: 模板填充字段定义，例如 [{"name": "party_name", "type": "text", "position": {"x": 100, "y": 100, "page": 1}}]

        Returns:
            {
                "templateId": "xxx",
                "templateName": "...",
                ...
            }
        """
        # Step 1: 上传 PDF 文档
        upload_result = self._request(
            "POST",
            "/open/api/v2/files/fileByUpload",
            files={
                "file": (doc_file_name, doc_pdf, "application/pdf"),
                "contentType": (None, "application/pdf"),
                "contentMd5": (None, hashlib.md5(doc_pdf).hexdigest()),
                "convert2Pdf": (None, "true"),
            },
        )
        file_id = upload_result.get("fileId") or upload_result.get("id", "")

        # Step 2: 创建模板
        payload: dict[str, Any] = {
            "templateName": name,
            "fileId": file_id,
        }
        if fields:
            payload["fields"] = fields

        result = self._request("POST", "/open/api/v2/templates", json_data=payload)
        logger.info("e签宝合同模板创建成功: name=%s, templateId=%s", name, result.get("templateId"))
        return result

    def list_templates(
        self,
        page: int = 1,
        size: int = 20,
        keyword: str = "",
    ) -> dict[str, Any]:
        """
        查询合同模板列表

        Args:
            page: 页码（默认 1）
            size: 每页条数（默认 20，最大 100）
            keyword: 模板名称关键字搜索

        Returns:
            {
                "list": [...],
                "total": 100,
                "currentPage": 1,
                "pageSize": 20
            }
        """
        params: dict[str, Any] = {"page": page, "size": min(size, 100)}
        if keyword:
            params["keyword"] = keyword
        return self._request("GET", "/open/api/v2/templates", params=params)

    def get_template(self, template_id: str) -> dict[str, Any]:
        """
        查询单个模板详情

        Args:
            template_id: 模板 ID

        Returns:
            模板详情字典
        """
        return self._request("GET", f"/open/api/v2/templates/{template_id}")

    def delete_template(self, template_id: str) -> dict[str, Any]:
        """
        删除合同模板

        Args:
            template_id: 模板 ID
        """
        return self._request("DELETE", f"/open/api/v2/templates/{template_id}")

    # ── 签署流程 ──────────────────────────────

    def create_contract(self, config: EsignContractConfig) -> dict[str, Any]:
        """
        基于模板发起签署流程

        流程:
            1. 使用模板创建合同文档（填充变量）
            2. 添加签署方
            3. 发起签署

        Args:
            config: 签署配置（模板 ID、签署方列表、填充字段等）

        Returns:
            {
                "contractId": "xxx",       # 合同流程 ID
                "signUrl": "...",          # 签署链接
                "status": 0,               # 合同状态
                ...
            }
        """
        # Step 1: 创建合同文档（基于模板 + 填充字段）
        doc_payload: dict[str, Any] = {
            "templateId": config.template_id,
            "contractName": config.contract_name or "",
        }
        if config.fields:
            doc_payload["fields"] = [{"name": f.name, "value": f.value} for f in config.fields]

        doc_result = self._request("POST", "/open/api/v2/contracts/createByTemplate", json_data=doc_payload)
        contract_id = doc_result.get("contractId") or doc_result.get("id", "")

        # Step 2: 添加签署方
        for signer in config.signers:
            signer_payload = self._build_signer_payload(signer)
            self._request(
                "POST",
                f"/open/api/v2/contracts/{contract_id}/signers",
                json_data=signer_payload,
            )

        # Step 3: 发起签署
        start_payload: dict[str, Any] = {
            "contractId": contract_id,
            "expireDays": config.expire_days,
            "autoArchive": config.auto_archive,
        }
        start_result = self._request(
            "PUT",
            f"/open/api/v2/contracts/{contract_id}/start",
            json_data=start_payload,
        )

        logger.info(
            "e签宝签署流程发起成功: contractId=%s, signers=%d",
            contract_id,
            len(config.signers),
        )
        return {**doc_result, **start_result, "contractId": contract_id}

    def query_contract(self, contract_id: str) -> dict[str, Any]:
        """
        查询签署流程状态

        Args:
            contract_id: 合同流程 ID

        Returns:
            {
                "contractId": "xxx",
                "contractName": "...",
                "status": 0,            # 0=待签署, 1=签署中, 2=已完成, 3=已撤销, 4=已过期
                "signers": [...],
                "createTime": "...",
                ...
            }
        """
        return self._request("GET", f"/open/api/v2/contracts/{contract_id}")

    def get_sign_link(
        self,
        contract_id: str,
        signer_account_id: str = "",
        redirect_url: str = "",
        app_url: str = "",
    ) -> dict[str, Any]:
        """
        获取签署链接（H5 嵌入或 URL 直接访问）

        Args:
            contract_id: 合同流程 ID
            signer_account_id: 签署方账户 ID（不传则返回签署入口链接）
            redirect_url: 签署完成后的重定向 URL
            app_url: 移动端唤起 App 的 URL Scheme

        Returns:
            {
                "shortUrl": "...",          # 短链接
                "url": "...",               # 完整签署链接
                "qrcode": "...",            # 二维码
            }
        """
        payload: dict[str, Any] = {"contractId": contract_id}
        if signer_account_id:
            payload["signerAccountId"] = signer_account_id
        if redirect_url:
            payload["redirectUrl"] = redirect_url
        if app_url:
            payload["appUrl"] = app_url

        return self._request("POST", "/open/api/v2/signflow/signUrl", json_data=payload)

    def revoke_contract(
        self,
        contract_id: str,
        reason: str = "签署方主动撤销",
    ) -> dict[str, Any]:
        """
        撤销签署流程

        Args:
            contract_id: 合同流程 ID
            reason: 撤销原因
        """
        return self._request(
            "PUT",
            f"/open/api/v2/contracts/{contract_id}/revoke",
            json_data={"reason": reason},
        )

    def download_contract(self, contract_id: str, file_path: str = "") -> bytes:
        """
        下载已签署的合同 PDF

        Args:
            contract_id: 合同流程 ID
            file_path: 本地保存路径（可选，传空则直接返回 bytes）

        Returns:
            PDF 文件二进制内容
        """
        result = self._request("GET", f"/open/api/v2/contracts/{contract_id}/download")
        download_url = result.get("downloadUrl", "")
        if not download_url:
            raise EsignError(f"合同 {contract_id} 下载链接为空")

        # 使用公共 GET 请求下载文件（不需要带 Authorization）
        resp = requests.get(download_url, timeout=60)
        if resp.status_code != 200:
            raise EsignError(f"合同文件下载失败: HTTP {resp.status_code}")

        content = resp.content
        if file_path:
            os.makedirs(os.path.dirname(os.path.abspath(file_path)) or ".", exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(content)
            logger.info("合同 PDF 已保存: %s", file_path)

        return content

    # ── 内部辅助 ──────────────────────────────

    @staticmethod
    def _build_signer_payload(signer: EsignSigner) -> dict[str, Any]:
        """
        构建签署方请求体

        Args:
            signer: 签署方信息

        Returns:
            e签宝 API 签署方 payload
        """
        payload: dict[str, Any] = {
            "signerType": signer.signer_type,
            "signerName": signer.name,
        }

        # 企业签署
        if signer.signer_type == "PSN_FIRM":
            payload["orgName"] = signer.org_name or signer.name
            if signer.id_number:
                payload["orgIdNumber"] = signer.id_number
            if signer.mobile:
                payload["signerMobile"] = signer.mobile
            if signer.email:
                payload["signerEmail"] = signer.email

        # 个人签署
        else:
            if signer.id_number:
                payload["signerIdNumber"] = signer.id_number
            if signer.mobile:
                payload["signerMobile"] = signer.mobile
            if signer.email:
                payload["signerEmail"] = signer.email

        return payload


# ──────────────────────────────────────────────
# 异常
# ──────────────────────────────────────────────


class EsignError(Exception):
    """e签宝 API 调用异常"""

    def __init__(
        self,
        message: str,
        code: int = -1,
        message_raw: str = "",
        response: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message_raw = message_raw
        self.response = response or {}

    def __str__(self) -> str:
        if self.code != -1:
            return f"[EsignError code={self.code}] {self.args[0]}"
        return f"[EsignError] {self.args[0]}"


# ──────────────────────────────────────────────
# 回调解密（可选 — 回调通知验签）
# ──────────────────────────────────────────────


def verify_callback_signature(
    body: dict[str, Any],
    signature: str,
    app_secret: str | None = None,
) -> bool:
    """
    验证 e签宝回调通知的签名

    e签宝回调通知会在请求头 X-OPEN-SIGNATURE 中携带签名，
    验签方式: HMAC-SHA256(body_json, app_secret)

    Args:
        body: 回调请求体 (dict)
        signature: 请求头 X-OPEN-SIGNATURE 的值
        app_secret: AppSecret（默认读取 ESIGN_APP_SECRET 环境变量）

    Returns:
        True 验签通过 / False 验签失败
    """
    secret = (app_secret or ESIGN_APP_SECRET).encode("utf-8")
    body_str = json.dumps(body, separators=(",", ":"), ensure_ascii=False)

    import hmac

    expected = hmac.new(secret, body_str.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
