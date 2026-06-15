"""
标准化合同模板 API 路由
========================
提供合同模板的列表、详情、渲染和一键发起签署功能。

路由前缀: /api/contract-templates
标签: 合同模板

端点清单:
  GET    /api/contract-templates           — 列出所有可用模板
  GET    /api/contract-templates/{id}      — 获取模板完整详情
  POST   /api/contract-templates/{id}/render  — 填充变量生成合同正文
  POST   /api/contract-templates/{id}/sign    — 一键生成并通过 e签宝发起签署
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.models import User
from app.schemas import ApiResponse
from app.services.contract_templates import (
    TemplateNotFoundError,
    TemplateValidationError,
    get_template_manager,
)
from app.services.esign_client import EsignClient, EsignError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/contract-templates", tags=["合同模板"])


# ──────────────────────────────────────────────
# Pydantic 请求 / 响应模型
# ──────────────────────────────────────────────


class RenderRequest(BaseModel):
    """填充变量渲染合同请求"""

    variables: dict[str, Any] = Field(..., description="模板填充变量字典，key 为变量名，value 为填充值")


class SignerInfo(BaseModel):
    """签署方信息"""

    name: str = Field(..., min_length=1, max_length=100, description="签署方名称")
    id_number: str = Field("", description="证件号（统一社会信用代码/身份证号）")
    mobile: str = Field("", description="手机号")
    signer_type: str = Field(
        "PSN_PERSON",
        pattern=r"^(PSN_FIRM|PSN_PERSON)$",
        description="PSN_FIRM=企业, PSN_PERSON=个人",
    )
    org_name: str = Field("", description="企业名称（企业签署时必填）")
    email: str = Field("", description="邮箱（可选）")


class SignRequest(BaseModel):
    """一键签署请求"""

    variables: dict[str, Any] = Field(..., description="模板填充变量字典")
    signers: list[SignerInfo] = Field(..., min_length=1, max_length=20, description="签署方列表")
    contract_name: str = Field("", description="合同名称（默认取模板名称）")
    expire_days: int = Field(30, ge=1, le=365, description="签署有效期（天）")
    auto_archive: bool = Field(True, description="签署完成后是否自动归档")


# ──────────────────────────────────────────────
# 依赖注入
# ──────────────────────────────────────────────


def get_template_mgr():
    """获取模板管理器单例"""
    return get_template_manager()


def get_esign_client() -> EsignClient:
    """获取 e签宝客户端单例"""
    return EsignClient()


# ──────────────────────────────────────────────
# API 端点
# ──────────────────────────────────────────────


@router.get("", response_model=ApiResponse, summary="列出所有可用模板")
async def list_templates(
    mgr=Depends(get_template_mgr),
    current_user: User = Depends(get_current_user),
):
    """
    获取所有预置的标准化合同模板列表

    返回模板的摘要信息（名称、描述、变量列表、签署方位置等），不含完整合同正文。

    **使用场景:**
    - 前端下拉框选择合同模板类型
    - 展示可用的模板列表供用户选择
    """
    try:
        templates = mgr.list_templates()
        return ApiResponse(
            code=200,
            message="获取模板列表成功",
            data={
                "total": len(templates),
                "templates": templates,
            },
        )
    except Exception as e:
        logger.exception("获取模板列表异常")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取模板列表失败: {e}",
        )


@router.get("/{template_id}", response_model=ApiResponse, summary="获取模板详情")
async def get_template_detail(
    template_id: str,
    mgr=Depends(get_template_mgr),
    current_user: User = Depends(get_current_user),
):
    """
    获取指定模板的完整详情

    包括模板名称、描述、版本、所有变量定义（含类型、说明、默认值）、
    签署位置定义、完整合同正文模板（含 {{变量名}} 占位符）、元数据等。

    **参数:**
    - template_id: 模板 ID（如 franchise_standard, partnership_agreement, distribution_deal）
    """
    try:
        detail = mgr.get_template_detail(template_id)
        return ApiResponse(
            code=200,
            message="获取模板详情成功",
            data=detail,
        )
    except TemplateNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("获取模板详情异常")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取模板详情失败: {e}",
        )


@router.post(
    "/{template_id}/render",
    response_model=ApiResponse,
    summary="填充变量生成合同正文",
)
async def render_contract(
    template_id: str,
    req: RenderRequest,
    mgr=Depends(get_template_mgr),
    current_user: User = Depends(get_current_user),
):
    """
    填充模板变量，生成最终合同文本

    根据模板 ID 加载对应的合同模板，将请求中的变量填充到合同正文中，
    返回渲染后的完整合同文本。

    **请求体示例:**
    ```json
    {
        "variables": {
            "partyA_name": "上海链客宝品牌管理有限公司",
            "partyB_name": "北京创业餐饮管理有限公司",
            "brand_name": "链客茶饮",
            "franchise_fee": "50000",
            "deposit": "30000",
            "contract_term_years": "3",
            "contract_start_date": "2025年06月15日",
            "contract_end_date": "2028年06月14日",
            "franchise_area": "北京市朝阳区",
            "sign_date": "2025年06月13日",
            "sign_location": "上海"
        }
    }
    ```

    **注意:**
    - 必填变量必须提供，否则返回 400 错误
    - 变量名需要与模板定义的 variables 中的 name 字段完全一致

    **返回:**
    - template_id: 模板 ID
    - template_name: 模板名称
    - contract_text: 渲染后的完整合同文本（纯文本格式，可转为 PDF）
    - variables_used: 使用的变量
    - sign_positions: 签署位置定义
    """
    try:
        result = mgr.render_contract(template_id, req.variables)

        logger.info(
            "合同渲染成功: user=%s, template=%s, variables=%d",
            current_user.id,
            template_id,
            len(req.variables),
        )

        return ApiResponse(
            code=200,
            message="合同渲染成功",
            data=result,
        )

    except TemplateNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except TemplateValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("合同渲染异常")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"合同渲染失败: {e}",
        )


@router.post(
    "/{template_id}/sign",
    response_model=ApiResponse,
    summary="一键生成合同并发起 e签宝签署",
)
async def sign_contract(
    template_id: str,
    req: SignRequest,
    mgr=Depends(get_template_mgr),
    esign_client: EsignClient = Depends(get_esign_client),
    current_user: User = Depends(get_current_user),
):
    """
    一键完成：填充模板变量 → 生成合同文本 → 通过 e签宝发起签署

    这是「一键签署」核心端点。流程如下:
    1. 加载指定模板并填充所有变量
    2. 自动生成合同 PDF 并上传至 e签宝创建电子模板
    3. 添加签署方并启动签署流程
    4. 返回签署链接供前端嵌入展示

    **前提条件:**
    - 已配置 ESIGN_APP_KEY 和 ESIGN_APP_SECRET 环境变量
    - 签署方信息必须真实有效（e签宝会进行实名认证）

    **请求体示例:**
    ```json
    {
        "variables": {
            "partyA_name": "上海链客宝品牌管理有限公司",
            "partyA_credit_code": "91310000MA1XXXXXXX",
            "partyA_legal": "张三",
            "partyA_address": "上海市浦东新区张江高科技园区",
            "partyB_name": "北京创业餐饮管理有限公司",
            "partyB_credit_code": "91110108MAXXXXXXXX",
            "partyB_legal": "李四",
            "partyB_address": "北京市海淀区中关村大街1号",
            "brand_name": "链客茶饮",
            "franchise_fee": "50000",
            "deposit": "30000",
            "royalty_rate": "3",
            "contract_term_years": "3",
            "contract_start_date": "2025年06月15日",
            "contract_end_date": "2028年06月14日",
            "franchise_area": "北京市朝阳区",
            "franchise_store_address": "北京市朝阳区建国路88号",
            "minimum_store_area": "30",
            "training_days": "15",
            "renewal_fee": "10000",
            "liquidated_damages_rate": "30",
            "sign_date": "2025年06月13日",
            "sign_location": "上海"
        },
        "signers": [
            {
                "name": "上海链客宝品牌管理有限公司",
                "id_number": "91310000MA1XXXXXXX",
                "mobile": "13900139000",
                "signer_type": "PSN_FIRM",
                "org_name": "上海链客宝品牌管理有限公司"
            },
            {
                "name": "李四",
                "id_number": "110101199001011234",
                "mobile": "13800138000",
                "signer_type": "PSN_PERSON",
                "org_name": "北京创业餐饮管理有限公司"
            }
        ],
        "contract_name": "链客茶饮—标准招商加盟合同",
        "expire_days": 30,
        "auto_archive": true
    }
    ```

    **返回:**
    - template_id: 使用的模板 ID
    - contract_name: 合同名称
    - esign_template_id: e签宝的模板 ID
    - contract_id: 合同流程 ID（可用于后续查询状态）
    - sign_url: 签署链接（前端可直接打开或 iframe 嵌入）
    - status: 合同状态
    """
    try:
        # 构建签署方列表
        signers = [
            {
                "name": s.name,
                "id_number": s.id_number,
                "mobile": s.mobile,
                "signer_type": s.signer_type,
                "org_name": s.org_name,
                "email": s.email,
            }
            for s in req.signers
        ]

        # 调用模板管理器的一键签署方法
        result = mgr.sign_and_send(
            template_id=template_id,
            variables=req.variables,
            signers=signers,
            contract_name=req.contract_name,
            expire_days=req.expire_days,
            auto_archive=req.auto_archive,
            esign_client=esign_client,
        )

        logger.info(
            "一键签署成功: user=%s, template=%s, contractId=%s",
            current_user.id,
            template_id,
            result.get("contract_id", ""),
        )

        return ApiResponse(
            code=200,
            message="签署流程发起成功",
            data=result,
        )

    except TemplateNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except TemplateValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except EsignError as e:
        logger.error("e签宝签署失败: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"e签宝签署失败: {e}",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("一键签署异常")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"一键签署失败: {e}",
        )
