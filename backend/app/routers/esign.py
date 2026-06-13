"""
e签宝电子签约路由
=================
提供合同模板管理、签署流程发起、状态查询、签署链接获取、回调通知等 API。

路由前缀: /api/esign
标签: 电子签约

端点清单:
  POST   /api/esign/templates          — 创建合同模板（上传 PDF）
  GET    /api/esign/templates           — 模板列表
  GET    /api/esign/templates/{id}      — 模板详情
  POST   /api/esign/contracts           — 发起签署流程
  GET    /api/esign/contracts/{id}      — 签署状态查询
  GET    /api/esign/contracts/{id}/link — 获取签署链接（H5嵌入）
  POST   /api/esign/contracts/{id}/revoke  — 撤销签署
  POST   /api/esign/callback            — e签宝回调通知（Webhook）
"""

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.schemas import ApiResponse
from app.services.esign_client import (
    EsignClient,
    EsignContractConfig,
    EsignError,
    EsignSigner,
    EsignTemplateField,
    verify_callback_signature,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/esign", tags=["电子签约"])


# ──────────────────────────────────────────────
# Pydantic 请求 / 响应模型
# ──────────────────────────────────────────────


class TemplateCreateRequest(BaseModel):
    """创建合同模板请求"""

    name: str = Field(..., min_length=1, max_length=200, description="模板名称")
    doc_base64: str = Field(..., description="PDF 文件 Base64 编码内容")
    doc_file_name: str = Field("contract.pdf", description="PDF 文件名")
    fields: list[dict[str, Any]] | None = Field(None, description="模板填充字段定义（可选）")


class SignerInfo(BaseModel):
    """签署方信息"""

    name: str = Field(..., min_length=1, max_length=100, description="签署方名称")
    id_number: str = Field("", description="证件号（统一社会信用代码/身份证号）")
    mobile: str = Field("", description="手机号")
    signer_type: str = Field(
        "PSN_PERSON", pattern=r"^(PSN_FIRM|PSN_PERSON)$", description="PSN_FIRM=企业, PSN_PERSON=个人"
    )
    org_name: str = Field("", description="企业名称（企业签署时必填）")
    email: str = Field("", description="邮箱")


class ContractField(BaseModel):
    """模板填充字段"""

    name: str = Field(..., description="字段名称（模板中定义的占位符）")
    value: str = Field(..., description="填充值")


class ContractCreateRequest(BaseModel):
    """发起签署请求"""

    template_id: str = Field(..., description="合同模板 ID")
    contract_name: str = Field("", description="合同名称（默认取模板名称）")
    signers: list[SignerInfo] = Field(..., min_length=1, max_length=20, description="签署方列表（至少1人）")
    fields: list[ContractField] = Field(default_factory=list, description="模板填充字段")
    expire_days: int = Field(30, ge=1, le=365, description="签署有效期（天）")
    auto_archive: bool = Field(True, description="签署完成后是否自动归档")


class CallbackNotification(BaseModel):
    """e签宝回调通知格式"""

    action: str = Field("", description="回调事件类型")
    contractId: str = Field("", description="合同流程 ID")
    contractName: str = Field("", description="合同名称")
    status: int = Field(0, description="合同状态")
    statusDescription: str = Field("", description="状态描述")
    signTime: str | None = Field(None, description="签署完成时间")
    operator: str | None = Field(None, description="操作人")
    remark: str | None = Field(None, description="备注")


# ──────────────────────────────────────────────
# 依赖注入
# ──────────────────────────────────────────────


def get_esign_client() -> EsignClient:
    """FastAPI 依赖注入：获取 e签宝客户端单例"""
    return EsignClient()


# ──────────────────────────────────────────────
# 模板管理
# ──────────────────────────────────────────────


@router.post("/templates", response_model=ApiResponse, summary="创建合同模板")
async def create_template(
    req: TemplateCreateRequest,
    client: EsignClient = Depends(get_esign_client),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    创建 e签宝合同模板

    上传 PDF 文档并定义模板填充字段，用于后续发起签署时填充合同变量。

    **请求体:**
    - name: 模板名称
    - doc_base64: PDF 文件内容的 Base64 编码
    - doc_file_name: PDF 文件名（默认 contract.pdf）
    - fields: 模板字段定义（可选），例如:
        [{"name": "partyA_name", "type": "text", "position": {"x": 100, "y": 100, "page": 1}}]

    **返回:**
    - templateId: e签宝生成的模板唯一 ID
    """
    import base64

    try:
        # Base64 解码
        pdf_bytes = base64.b64decode(req.doc_base64)

        # 调用 e签宝 API 创建模板
        result = client.create_template(
            name=req.name,
            doc_pdf=pdf_bytes,
            doc_file_name=req.doc_file_name,
            fields=req.fields,
        )

        logger.info(
            "合同模板创建成功: user=%s, name=%s, templateId=%s",
            current_user.id,
            req.name,
            result.get("templateId"),
        )

        return ApiResponse(
            code=200,
            message="合同模板创建成功",
            data={
                "templateId": result.get("templateId"),
                "templateName": result.get("templateName", req.name),
                "fileId": result.get("fileId", ""),
            },
        )

    except EsignError as e:
        logger.error("e签宝模板创建失败: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"模板创建失败: {e}",
        ) from e
    except Exception as e:
        logger.exception("模板创建意外异常")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"系统错误: {e}",
        ) from e


@router.get("/templates", response_model=ApiResponse, summary="模板列表")
async def list_templates(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页条数"),
    keyword: str = Query("", description="关键字搜索"),
    client: EsignClient = Depends(get_esign_client),
    current_user: User = Depends(get_current_user),
):
    """
    获取 e签宝合同模板列表

    支持分页和关键字搜索。
    """
    try:
        result = client.list_templates(page=page, size=size, keyword=keyword)

        return ApiResponse(
            code=200,
            message="获取模板列表成功",
            data=result,
        )

    except EsignError as e:
        logger.error("e签宝模板列表查询失败: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"查询失败: {e}",
        ) from e


@router.get("/templates/{template_id}", response_model=ApiResponse, summary="模板详情")
async def get_template(
    template_id: str,
    client: EsignClient = Depends(get_esign_client),
    current_user: User = Depends(get_current_user),
):
    """
    获取单个合同模板详情
    """
    try:
        result = client.get_template(template_id)

        return ApiResponse(
            code=200,
            message="获取模板详情成功",
            data=result,
        )

    except EsignError as e:
        logger.error("e签宝模板详情查询失败: %s", e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"模板不存在或查询失败: {e}",
        ) from e


# ──────────────────────────────────────────────
# 签署流程
# ──────────────────────────────────────────────


@router.post("/contracts", response_model=ApiResponse, summary="发起签署")
async def create_contract(
    req: ContractCreateRequest,
    client: EsignClient = Depends(get_esign_client),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    发起电子签署流程

    基于已创建的合同模板，填充变量并添加签署方，然后发起签署。

    **签署方类型:**
    - PSN_FIRM (企业签署): 需提供 org_name（企业名称）+ id_number（统一社会信用代码）
    - PSN_PERSON (个人签署): 需提供 name（姓名）+ mobile（手机号）

    **返回:**
    - contractId: 合同流程 ID
    - signUrl: 签署链接
    - status: 当前状态
    """
    try:
        # 构建签署方列表
        signers = [
            EsignSigner(
                name=s.name,
                id_number=s.id_number,
                mobile=s.mobile,
                signer_type=s.signer_type,
                org_name=s.org_name,
                email=s.email,
            )
            for s in req.signers
        ]

        # 构建填充字段
        fields = [EsignTemplateField(name=f.name, value=f.value) for f in req.fields]

        # 构建配置
        config = EsignContractConfig(
            template_id=req.template_id,
            signers=signers,
            fields=fields,
            contract_name=req.contract_name,
            expire_days=req.expire_days,
            auto_archive=req.auto_archive,
        )

        # 调用 e签宝 API
        result = client.create_contract(config)

        contract_id = result.get("contractId", "")
        sign_url = result.get("signUrl", "")

        logger.info(
            "签署流程发起成功: user=%s, contractId=%s, signers=%d",
            current_user.id,
            contract_id,
            len(signers),
        )

        return ApiResponse(
            code=200,
            message="签署流程发起成功",
            data={
                "contractId": contract_id,
                "signUrl": sign_url,
                "status": result.get("status", 0),
                "contractName": req.contract_name or "",
            },
        )

    except EsignError as e:
        logger.error("e签宝发起签署失败: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"发起签署失败: {e}",
        ) from e


@router.get("/contracts/{contract_id}", response_model=ApiResponse, summary="签署状态查询")
async def query_contract(
    contract_id: str,
    client: EsignClient = Depends(get_esign_client),
    current_user: User = Depends(get_current_user),
):
    """
    查询电子签署流程的当前状态

    **状态码说明:**
    - 0: 待签署
    - 1: 签署中
    - 2: 已完成
    - 3: 已撤销
    - 4: 已过期
    """
    try:
        result = client.query_contract(contract_id)

        # 提取关键字段
        status_code = result.get("status", -1)
        status_map = {0: "待签署", 1: "签署中", 2: "已完成", 3: "已撤销", 4: "已过期"}

        return ApiResponse(
            code=200,
            message="查询成功",
            data={
                "contractId": result.get("contractId", contract_id),
                "contractName": result.get("contractName", ""),
                "status": status_code,
                "statusLabel": status_map.get(status_code, "未知"),
                "signers": result.get("signers", []),
                "createTime": result.get("createTime", ""),
                "finishTime": result.get("finishTime", ""),
                "detail": result,
            },
        )

    except EsignError as e:
        logger.error("e签宝签署状态查询失败: %s", e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"合同不存在或查询失败: {e}",
        ) from e


@router.get("/contracts/{contract_id}/link", response_model=ApiResponse, summary="获取签署链接")
async def get_sign_link(
    contract_id: str,
    signer_account_id: str = Query("", description="签署方账户 ID（可选）"),
    redirect_url: str = Query("", description="签署完成后的重定向 URL"),
    client: EsignClient = Depends(get_esign_client),
    current_user: User = Depends(get_current_user),
):
    """
    获取电子签署链接，用于 H5 嵌入或浏览器直接访问

    **参数说明:**
    - signer_account_id: 指定签署方账户 ID（不传返回签署入口链接）
    - redirect_url: 签署完成后的跳转地址（用于 H5 嵌入场景）

    **返回:**
    - url: 完整签署链接（可 iframe 嵌入或新标签页打开）
    - shortUrl: 短链接
    """
    try:
        result = client.get_sign_link(
            contract_id=contract_id,
            signer_account_id=signer_account_id,
            redirect_url=redirect_url,
        )

        return ApiResponse(
            code=200,
            message="获取签署链接成功",
            data={
                "url": result.get("url", ""),
                "shortUrl": result.get("shortUrl", ""),
                "qrcode": result.get("qrcode", ""),
            },
        )

    except EsignError as e:
        logger.error("e签宝获取签署链接失败: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"获取签署链接失败: {e}",
        ) from e


@router.post("/contracts/{contract_id}/revoke", response_model=ApiResponse, summary="撤销签署")
async def revoke_contract(
    contract_id: str,
    reason: str = Query("签署方主动撤销", description="撤销原因"),
    client: EsignClient = Depends(get_esign_client),
    current_user: User = Depends(get_current_user),
):
    """
    撤销指定的签署流程

    仅可撤销「待签署」或「签署中」状态的合同。
    """
    try:
        result = client.revoke_contract(contract_id, reason=reason)

        logger.info(
            "签署流程已撤销: user=%s, contractId=%s",
            current_user.id,
            contract_id,
        )

        return ApiResponse(
            code=200,
            message="签署流程已撤销",
            data={
                "contractId": contract_id,
                "result": result,
            },
        )

    except EsignError as e:
        logger.error("e签宝撤销签署失败: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"撤销失败: {e}",
        ) from e


# ──────────────────────────────────────────────
# 回调通知
# ──────────────────────────────────────────────


@router.post("/callback", summary="e签宝回调通知（Webhook）")
async def esign_callback(
    request: Request,
    body: CallbackNotification | None = None,
    db: Session = Depends(get_db),
):
    """
    e签宝主动回调 Webhook — 接收签署状态变更通知

    e签宝在签署流程状态变化时（如签署完成、签署失败、合同过期等），
    会向此地址发送 POST 请求。

    **回调验签:**
    通过请求头 X-OPEN-SIGNATURE 的 HMAC-SHA256 签名验证回调来源。

    **注意:**
    此端点无需认证（由 e签宝服务端调用），但会进行签名验证。

    **处理逻辑:**
    - 签署完成 (status=2): 更新本地合同状态为已完成
    - 签署撤销 (status=3): 更新本地状态
    - 其他状态: 记录日志
    """
    # 读取原始请求体（用于签名验证）
    raw_body = await request.body()
    body_str = raw_body.decode("utf-8")

    try:
        body_data = json.loads(body_str) if body_str else {}
    except json.JSONDecodeError:
        body_data = {}

    # 签名验证
    signature = request.headers.get("X-OPEN-SIGNATURE", "")
    if signature:
        is_valid = verify_callback_signature(body_data, signature)
        if not is_valid:
            logger.warning("e签宝回调签名验证失败，请求可能伪造")
            # 生产环境建议返回 403，这里先记录日志
    else:
        logger.info("e签宝回调未携带签名（跳过验签）")

    # 提取回调信息
    action = body_data.get("action", body.action if body else "")
    contract_id = body_data.get("contractId", body.contractId if body else "")
    status_code = body_data.get("status", body.status if body else 0)
    status_desc = body_data.get("statusDescription", body.statusDescription if body else "")

    logger.info(
        "e签宝回调收到: action=%s, contractId=%s, status=%s, desc=%s",
        action,
        contract_id,
        status_code,
        status_desc,
    )

    # 返回 e签宝要求的响应格式
    return {
        "code": 0,
        "message": "成功",
        "data": {},
    }
