"""链客宝AI客服机器人核心引擎

功能:
  - 意图识别: 基于关键词+规则的用户意图分类
  - FAQ知识库: 内置15+条招商加盟常见问答
  - 上下文管理: 保持会话最近3轮对话历史
  - 响应生成: 基于意图+FAQ匹配+企业数据生成回答
  - 转人工: 无法回答或用户要求时记录工单

设计原则:
  - 纯规则驱动，无外部LLM依赖（可用本地匹配）
  - 可扩展：FAQ通过add_faq动态添加
  - 生产级：完整try/except/logging/类型注解
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# ============================================================
# 常量定义
# ============================================================
MAX_CONTEXT_ROUNDS = 3  # 上下文保留轮数
INTENT_CONFIDENCE_THRESHOLD = 0.5  # 意图识别置信度阈值


# ============================================================
# 枚举
# ============================================================
class IntentType(str, Enum):
    """用户意图分类"""

    FRANCHISE_CONSULT = "franchise_consult"  # 招商加盟咨询
    SIGNING_PROGRESS = "signing_progress"  # 签约进度
    ENTERPRISE_QUERY = "enterprise_query"  # 企业查询
    HUMAN_ESCALATE = "human_escalate"  # 人工转接
    GREETING = "greeting"  # 问候寒暄
    FAQ_MATCH = "faq_match"  # 常规FAQ匹配
    UNKNOWN = "unknown"  # 未知


class MessageRole(str, Enum):
    """消息角色"""

    USER = "user"
    BOT = "bot"
    SYSTEM = "system"


class EscalationStatus(str, Enum):
    """转人工工单状态"""

    PENDING = "pending"
    PROCESSING = "processing"
    RESOLVED = "resolved"
    CLOSED = "closed"


# ============================================================
# 数据模型
# ============================================================
@dataclass
class FAQItem:
    """FAQ问答条目"""

    question: str
    answer: str
    keywords: list[str] = field(default_factory=list)
    category: str = "general"
    priority: int = 0  # 优先级，数字越大越优先

    def match_score(self, text: str) -> float:
        """计算文本与FAQ的匹配分数

        Args:
            text: 用户输入文本

        Returns:
            0.0 ~ 1.0 的匹配分数
        """
        text_lower = text.lower()
        score = 0.0

        # 精确匹配问题
        if self.question.lower() in text_lower:
            score = max(score, 1.0)

        # 关键词匹配
        matched_keywords = sum(1 for kw in self.keywords if kw.lower() in text_lower)
        if self.keywords:
            keyword_score = matched_keywords / len(self.keywords)
            score = max(score, keyword_score * 0.9)

        return score


@dataclass
class ChatMessage:
    """单条聊天消息"""

    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatSession:
    """聊天会话"""

    session_id: str
    user_id: int | None = None
    messages: list[ChatMessage] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    escalated: bool = False
    escalation_ticket: dict[str, Any] | None = None

    def add_message(self, message: ChatMessage) -> None:
        """添加消息到会话

        Args:
            message: 聊天消息
        """
        self.messages.append(message)
        self.updated_at = datetime.now(timezone.utc)

        # 裁剪上下文，只保留最近N轮
        self._trim_context()

    def _trim_context(self) -> None:
        """裁剪会话历史，只保留最近MAX_CONTEXT_ROUNDS轮对话"""
        # 统计用户轮次（user消息数）
        user_messages = [m for m in self.messages if m.role == MessageRole.USER]
        if len(user_messages) > MAX_CONTEXT_ROUNDS:
            # 找到需要裁剪的位置
            keep_user_count = len(user_messages) - MAX_CONTEXT_ROUNDS
            cut_index = 0
            user_count = 0
            for i, m in enumerate(self.messages):
                if m.role == MessageRole.USER:
                    user_count += 1
                if user_count > keep_user_count:
                    cut_index = i
                    break
            self.messages = self.messages[cut_index:]

    def get_recent_context(self, rounds: int = MAX_CONTEXT_ROUNDS) -> list[dict[str, str]]:
        """获取最近N轮对话上下文

        Args:
            rounds: 轮数

        Returns:
            对话上下文字典列表
        """
        result = []
        for msg in self.messages[-rounds * 2:]:  # 每轮包含user+bot
            result.append({
                "role": msg.role.value,
                "content": msg.content,
            })
        return result

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "messages": [
                {
                    "role": m.role.value,
                    "content": m.content,
                    "timestamp": m.timestamp.isoformat(),
                }
                for m in self.messages
            ],
            "context": self.context,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "escalated": self.escalated,
            "escalation_ticket": self.escalation_ticket,
        }


# ============================================================
# 默认FAQ知识库（15+条真实问答）
# ============================================================
def _build_default_faqs() -> list[FAQItem]:
    """构建默认FAQ知识库

    Returns:
        FAQ条目列表
    """
    return [
        FAQItem(
            question="如何成为链客宝的经销商/加盟商？",
            answer=(
                '成为链客宝经销商/加盟商的流程如下：\n\n'
                '1. **注册账号**：在链客宝官网或小程序注册账号\n'
                '2. **提交资质**：上传企业营业执照、法人身份证等信息\n'
                '3. **平台审核**：平台在1-3个工作日内完成资质审核\n'
                '4. **签订合同**：通过e签宝在线签署经销/加盟协议\n'
                '5. **缴纳费用**：根据选择的会员等级缴纳相应费用\n'
                '6. **开通权限**：审核通过后，平台开通经销商后台权限\n\n'
                '如有疑问，可联系客服热线 400-888-8888。'
            ),
            keywords=["经销商", "加盟商", "加盟", "如何成为", "入驻条件", "代理条件"],
            category="franchise",
            priority=10,
        ),
        FAQItem(
            question="加盟费是多少？有哪些会员等级？",
            answer=(
                '链客宝目前提供以下会员等级和费用标准：\n\n'
                '**【基础版】** 免费\n'
                '- 企业信息展示\n'
                '- 基础匹配推荐（每周3次）\n\n'
                '**【专业版】** ￥9,800/年\n'
                '- 企业信息展示+认证标识\n'
                '- 智能匹配推荐（不限次数）\n'
                '- 对接会优先参与权\n'
                '- 数据分析报告\n\n'
                '**【旗舰版】** ￥29,800/年\n'
                '- 包含专业版所有权益\n'
                '- AI数字分身\n'
                '- 专属客户经理\n'
                '- 优先签约通道\n'
                '- 品牌曝光位\n\n'
                '**【定制版】** 面议\n'
                '- 根据企业需求量身定制方案\n\n'
                '具体价格以官网最新公示为准，部分行业有专项优惠政策。'
            ),
            keywords=["加盟费", "费用", "会员等级", "价格", "多少钱", "收费标准", "年费"],
            category="franchise",
            priority=9,
        ),
        FAQItem(
            question="如何入驻链客宝平台？",
            answer=(
                '入驻链客宝平台的流程：\n\n'
                '1. **访问官网** www.go-aiport.com 或搜索链客宝小程序\n'
                '2. **点击注册**，选择企业入驻\n'
                '3. **填写企业信息**：企业名称、统一社会信用代码、联系人等\n'
                '4. **上传资质文件**：营业执照扫描件、法人身份证等\n'
                '5. **设置主营类目**：选择您所在的行业和供应品类\n'
                '6. **提交审核**：平台将在1-2个工作日内完成审核\n'
                '7. **审核通过**后即可发布供需信息\n\n'
                '入驻完全免费，不收取任何入驻费用！'
            ),
            keywords=["入驻", "入驻流程", "怎么入驻", "如何入驻", "注册", "平台注册"],
            category="onboarding",
            priority=8,
        ),
        FAQItem(
            question="企业信息如何认证？需要哪些材料？",
            answer=(
                '企业信息认证流程：\n\n'
                '**所需材料：**\n'
                '- 营业执照（原件照片或扫描件）\n'
                '- 法人身份证（正反面）\n'
                '- 企业授权委托书（非法人办理时需要）\n'
                '- 企业Logo（可选，建议200x200px以上）\n\n'
                '**认证步骤：**\n'
                '1. 登录后台 -> 企业设置 -> 企业认证\n'
                '2. 上传上述材料\n'
                '3. 系统自动识别营业执照信息\n'
                '4. 企查查数据交叉核验\n'
                '5. 人工终审（通常2小时内完成）\n\n'
                '认证通过后，企业信息页面会显示已认证标识，'
                '提升合作方信任度。认证信息每12个月需要更新一次。'
            ),
            keywords=["企业认证", "企业信息认证", "认证材料", "资质认证", "营业执照", "审核"],
            category="onboarding",
            priority=7,
        ),
        FAQItem(
            question="签约流程是怎样的？怎么在线签合同？",
            answer=(
                '链客宝使用e签宝进行在线电子签约，流程如下：\n\n'
                '**签约流程：**\n'
                '1. **匹配达成意向**：双方在平台匹配成功\n'
                '2. **发起签约**：需求方或供应方发起签约请求\n'
                '3. **选择模板**：系统根据合作类型推荐合同模板\n'
                '4. **填写条款**：在线填写合作细节（金额、周期等）\n'
                '5. **e签宝签署**：使用e签宝进行电子签名/盖章\n'
                '6. **合同生效**：双方签署完成，合同即时生效\n'
                '7. **合同存档**：平台/邮箱均可下载PDF合同\n\n'
                '**电子签章优势：**\n'
                '- 法律效力等同纸质合同\n'
                '- 全程线上操作，无需见面\n'
                '- 支持手机端签署\n'
                '- 区块链存证，不可篡改'
            ),
            keywords=["签约", "合同", "电子签约", "e签宝", "签约流程", "签合同", "在线签约"],
            category="contract",
            priority=8,
        ),
        FAQItem(
            question="对接会怎么参加？有什么要求？",
            answer=(
                '链客宝定期举办线上/线下对接会：\n\n'
                '**参加方式：**\n'
                '1. **自动邀约**：平台AI根据匹配度自动邀请优质企业\n'
                '2. **主动报名**：在活动中心查看近期对接会并报名\n'
                '3. **定向邀请**：客户经理一对一邀请核心企业\n\n'
                '**参会要求：**\n'
                '- 完成企业信息认证\n'
                '- 匹配评分>=50分（满分100）\n'
                '- 每家企业限2人参加\n\n'
                '**费用说明：**\n'
                '- 专业版及以上会员：免费参加\n'
                '- 基础版企业：￥299/次\n\n'
                '对接会每月举行2-4次，具体时间关注平台公告。'
            ),
            keywords=["对接会", "对接活动", "怎么参加", "活动", "线下对接", "线上对接"],
            category="event",
            priority=7,
        ),
        FAQItem(
            question="链客宝平台主要服务哪些行业？",
            answer=(
                '链客宝AI企业家生态平台主要服务于以下行业：\n\n'
                '**核心行业：**\n'
                '- 餐饮连锁（加盟招商）\n'
                '- 零售百货（供应链对接）\n'
                '- 生活服务（家政、美容等）\n'
                '- 教育培训（课程加盟）\n'
                '- 医疗健康（器械/药品供应链）\n'
                '- 农业科技（农产品供销）\n\n'
                '**覆盖角色：**\n'
                '- 品牌方（寻找经销商/加盟商）\n'
                '- 供应商（寻找采购方）\n'
                '- 创业者（寻找加盟/代理项目）\n'
                '- 经销商（寻找优质品牌代理）\n\n'
                '如果您所在的行业不在上述列表中，'
                '请联系客服评估是否可以加入平台。'
            ),
            keywords=["行业", "服务行业", "哪些行业", "覆盖领域", "餐饮", "零售", "教育"],
            category="general",
            priority=6,
        ),
        FAQItem(
            question="链客宝的AI匹配是怎么工作的？",
            answer=(
                '链客宝AI智能匹配引擎基于深度学习模型，通过以下维度进行精准匹配：\n\n'
                '**匹配维度：**\n'
                '1. **行业匹配**：供需双方的行业/类目匹配度\n'
                '2. **规模匹配**：企业规模、年营收等数据的匹配\n'
                '3. **地域匹配**：地理位置相近度\n'
                '4. **需求匹配**：需求描述与供应能力的语义匹配\n'
                '5. **历史行为**：企业的历史合作数据\n'
                '6. **信用评分**：企业信用、履约记录\n\n'
                '**输出结果：**\n'
                '- 匹配评分（0-100分）\n'
                '- 匹配摘要\n'
                '  高分（>=80分）：自动推荐签约\n'
                '  中分（50-79分）：邀约对接会\n'
                '  低分（<50分）：加入培育序列\n\n'
                '匹配引擎支持ML（机器学习）、Rule（规则）、Ensemble（集成）三种模式。'
            ),
            keywords=["AI匹配", "智能匹配", "匹配引擎", "匹配算法", "评分", "怎么匹配"],
            category="technology",
            priority=6,
        ),
        FAQItem(
            question="如何查看我的企业匹配结果？",
            answer=(
                '查看企业匹配结果的方法：\n\n'
                '**PC端：**\n'
                '1. 登录链客宝官网 www.go-aiport.com\n'
                '2. 进入供需匹配或智能推荐页面\n'
                '3. 查看匹配企业列表及其匹配评分\n'
                '4. 点击企业名称查看详细匹配报告\n\n'
                '**移动端（小程序）：**\n'
                '1. 打开链客宝小程序\n'
                '2. 点击底部发现或匹配标签\n'
                '3. 滑动查看推荐企业\n'
                '4. 点击匹配详情查看评分维度\n\n'
                '**推送通知：**\n'
                '- 新匹配结果生成时，系统会通过站内信和微信推送通知\n'
                '- 匹配评分超过60分时会有特别提醒'
            ),
            keywords=["匹配结果", "查看匹配", "匹配报告", "推荐企业", "评分结果"],
            category="general",
            priority=5,
        ),
        FAQItem(
            question="如何修改企业信息？",
            answer=(
                '修改企业信息的方法：\n\n'
                '**可修改的信息：**\n'
                '- 企业简介、主营业务\n'
                '- 联系方式（电话、邮箱）\n'
                '- 企业Logo、宣传图片\n'
                '- 供应/需求描述\n'
                '- 经营类目\n\n'
                '**修改步骤：**\n'
                '1. 登录后台 -> 企业设置 -> 企业信息\n'
                '2. 点击对应字段的编辑按钮\n'
                '3. 修改内容后点击保存\n'
                '4. 涉及工商信息（如企业名称、法人）的修改需重新提交认证\n\n'
                '**注意事项：**\n'
                '- 企业名称和统一社会信用代码无法自行修改\n'
                '- 如工商信息变更，需联系客服并提供新的营业执照\n'
                '- 修改信息后，匹配引擎会在2小时内重新计算匹配度'
            ),
            keywords=["修改企业信息", "编辑资料", "企业信息修改", "更新信息", "修改资料"],
            category="onboarding",
            priority=5,
        ),
        FAQItem(
            question="如何联系链客宝客服？",
            answer=(
                '您可以通过以下方式联系链客宝客服团队：\n\n'
                '**在线客服：**\n'
                '- 平台右下角在线客服按钮\n'
                '- 工作时间：周一至周日 9:00-22:00\n\n'
                '**电话热线：**\n'
                '- 客服热线：400-888-8888\n'
                '- 工作时间：周一至周五 9:00-18:00\n\n'
                '**邮件联系：**\n'
                '- support@go-aiport.com\n'
                '- 我们会在24小时内回复\n\n'
                '**企业微信：**\n'
                '- 搜索链客宝客服添加企业微信\n\n'
                '也可以直接在此对话框输入转人工或人工客服，'
                '系统会为您创建转人工工单，客服人员将尽快联系您。'
            ),
            keywords=["客服", "联系客服", "人工客服", "联系方式", "电话", "邮箱", "在线客服"],
            category="general",
            priority=9,
        ),
        FAQItem(
            question="我忘记密码了怎么办？",
            answer=(
                '找回密码的步骤：\n\n'
                '1. 在登录页面点击忘记密码\n'
                '2. 输入注册时使用的手机号或邮箱\n'
                '3. 获取验证码并输入\n'
                '4. 设置新密码（至少8位，包含字母和数字）\n'
                '5. 密码重置成功，使用新密码登录\n\n'
                '**提示：**\n'
                '- 验证码有效期为5分钟\n'
                '- 如未收到验证码，请检查是否被拦截\n'
                '- 如手机号已更换，请联系人工客服协助处理\n'
                '- 建议使用记住密码功能避免频繁登录'
            ),
            keywords=["忘记密码", "找密码", "密码重置", "密码忘了", "验证码"],
            category="account",
            priority=5,
        ),
        FAQItem(
            question="链客宝支持哪些支付方式？",
            answer=(
                '链客宝平台支持以下支付方式：\n\n'
                '**线上支付：**\n'
                '- 微信支付（推荐）\n'
                '- 支付宝\n'
                '- 企业对公转账\n\n'
                '**支付流程：**\n'
                '1. 在付款页面选择合适的支付方式\n'
                '2. 微信/支付宝：扫码或跳转支付\n'
                '3. 对公转账：获取平台对公账户信息，转账后上传凭证\n'
                '4. 平台确认到账后自动开通权益\n\n'
                '**注意事项：**\n'
                '- 微信/支付宝支付即时到账\n'
                '- 对公转账通常需1-3个工作日到账\n'
                '- 所有支付均开具正规发票\n'
                '- 支付遇到问题可联系客服协助'
            ),
            keywords=["支付", "付款", "支付方式", "微信支付", "支付宝", "对公转账", "发票"],
            category="payment",
            priority=6,
        ),
        FAQItem(
            question="如何退出或注销账号？",
            answer=(
                '账号注销流程：\n\n'
                '**注销条件：**\n'
                '- 账号无进行中的订单或合同\n'
                '- 账号无欠费或未结清款项\n'
                '- 账号无进行中的纠纷\n\n'
                '**注销步骤：**\n'
                '1. 登录后台 -> 账号安全 -> 注销账号\n'
                '2. 阅读注销须知\n'
                '3. 点击申请注销并确认\n'
                '4. 系统进入7天冷静期\n'
                '5. 冷静期内登录账号可取消注销\n'
                '6. 冷静期满后账号永久注销\n\n'
                '**注销后：**\n'
                '- 所有企业信息将被删除\n'
                '- 历史数据不可恢复\n'
                '- 已签署的合同仍然有效\n\n'
                '如有疑问，建议先联系客服确认。'
            ),
            keywords=["注销", "退出", "注销账号", "删除账号", "退会", "注销指南"],
            category="account",
            priority=4,
        ),
        FAQItem(
            question="链客宝平台的安全保障措施有哪些？",
            answer=(
                '链客宝采用多层次安全保障体系：\n\n'
                '**数据安全：**\n'
                '- 全链路AES-256-GCM加密传输\n'
                '- 数据分级存储，敏感信息脱敏展示\n'
                '- 数据库定期备份，多地容灾\n\n'
                '**交易安全：**\n'
                '- 电子合同区块链存证\n'
                '- 资金通过持牌支付机构结算\n'
                '- 交易双方实名认证\n\n'
                '**账户安全：**\n'
                '- 登录二次验证（短信/邮箱）\n'
                '- 异常登录实时告警\n'
                '- 会话超时自动退出\n\n'
                '**隐私保护：**\n'
                '- 严格执行《个人信息保护法》\n'
                '- 最小化数据采集原则\n'
                '- 用户数据可查、可删、可导出'
            ),
            keywords=["安全", "保障", "数据安全", "隐私保护", "加密", "安全保障"],
            category="general",
            priority=4,
        ),
        FAQItem(
            question="如何发起合作意向？如何与其他企业沟通？",
            answer=(
                '发起合作意向的步骤：\n\n'
                '1. **浏览企业**：在发现或匹配推荐页面浏览企业\n'
                '2. **查看详情**：点击企业卡片查看详细信息\n'
                '3. **发起意向**：点击合作意向按钮\n'
                '4. **填写意向**：选择意向类型（供应/需求/加盟等）\n'
                '5. **发送消息**：可附带简短留言\n'
                '6. **等待回复**：对方会在3个工作日内回复\n\n'
                '**沟通工具：**\n'
                '- 站内信：双方在平台内互相发送消息\n'
                '- 交换联系方式：双方同意后可见电话/微信\n'
                '- 邀约对接会：AI自动安排线上对接\n\n'
                '**提示：** 完善企业信息和认证可以提升对方回复率。'
            ),
            keywords=["合作意向", "发起合作", "沟通", "联系企业", "发送消息", "意向合作"],
            category="general",
            priority=5,
        ),
        FAQItem(
            question="平台撮合成功后的流程是怎样的？",
            answer=(
                '撮合成功后的完整流程：\n\n'
                '**第一步：意向确认**\n'
                '双方确认合作意向，平台生成合作备忘录\n\n'
                '**第二步：尽职调查**\n'
                '平台提供双方的企查查信用报告\n'
                '（专业版及以上会员可查看详细报告）\n\n'
                '**第三步：合同签署**\n'
                '使用e签宝在线签署电子合同\n'
                '支持自定义条款和标准模板\n\n'
                '**第四步：履约执行**\n'
                '按合同约定执行合作内容\n'
                '平台提供履约进度跟踪\n\n'
                '**第五步：评价反馈**\n'
                '合作完成后双方互评\n'
                '评价影响后续匹配评分\n\n'
                '全程有客户经理跟进，确保合作顺利推进。'
            ),
            keywords=["撮合成功", "合作流程", "撮合后", "合作成功后", "履约", "跟进"],
            category="contract",
            priority=6,
        ),
        FAQItem(
            question="企查查企业信息查询怎么用？",
            answer=(
                '企查查企业信息查询功能：\n\n'
                '**查询内容：**\n'
                '- 企业基本信息（注册资本、成立日期、法定代表人）\n'
                '- 股东信息\n'
                '- 司法风险（诉讼、被执行人）\n'
                '- 经营风险（行政处罚、经营异常）\n'
                '- 知识产权（商标、专利）\n'
                '- 招投标信息\n\n'
                '**使用方法：**\n'
                '1. 在企业查询或企业详情页面\n'
                '2. 输入企业名称或统一社会信用代码\n'
                '3. 系统自动拉取企查查数据\n'
                '4. 完整报告需专业版及以上会员\n\n'
                '**数据来源：** 企查查官方API，每日更新。'
            ),
            keywords=["企查查", "企业查询", "查企业", "信用报告", "工商信息", "企业信息查询"],
            category="enterprise",
            priority=7,
        ),
    ]


# 意图关键词映射
INTENT_KEYWORDS: dict[IntentType, list[str]] = {
    IntentType.FRANCHISE_CONSULT: [
        "加盟", "加盟商", "经销商", "代理", "招商", "怎么做代理",
        "加盟条件", "怎么合作", "开店", "品牌加盟", "招商加盟",
    ],
    IntentType.SIGNING_PROGRESS: [
        "签约", "合同", "签了吗", "签约进度", "正在签", "合同状态",
        "电子签约", "e签宝", "签合同", "签约完成", "签约流程",
    ],
    IntentType.ENTERPRISE_QUERY: [
        "查企业", "查公司", "企业信息", "公司信息", "企查查",
        "信用", "工商信息", "企业查询", "这家公司", "怎么样",
    ],
    IntentType.HUMAN_ESCALATE: [
        "转人工", "人工客服", "找客服", "人工", "客服电话",
        "转接人工", "我要找人工", "人工服务", "投诉", "举报",
    ],
    IntentType.GREETING: [
        "你好", "您好", "嗨", "hello", "hi", "在吗", "在不在",
        "早上好", "下午好", "晚上好", "hey", "哈喽",
    ],
}


# ============================================================
# AI客服核心引擎
# ============================================================
class AIChatbotEngine:
    """AI客服核心引擎

    包含意图识别、FAQ匹配、上下文管理、响应生成和转人工功能。

    用法:
        engine = AIChatbotEngine()
        response = engine.process_message("加盟费多少钱？", user_id=123)
    """

    def __init__(self, faqs: list[FAQItem] | None = None) -> None:
        """初始化AI客服引擎

        Args:
            faqs: 自定义FAQ列表，为空时使用DEFAULT_FAQS
        """
        self._faqs: list[FAQItem] = faqs or _build_default_faqs()
        self._sessions: dict[str, ChatSession] = {}
        self._escalation_counter: int = 0

        logger.info(
            "AIChatbotEngine 初始化完成",
            extra={"faq_count": len(self._faqs)},
        )

    # ----------------------------------------------------------
    # FAQ 管理
    # ----------------------------------------------------------
    @property
    def faqs(self) -> list[FAQItem]:
        """获取FAQ列表（防御性拷贝）"""
        return list(self._faqs)

    def add_faq(self, faq: FAQItem) -> None:
        """动态添加FAQ条目

        Args:
            faq: FAQ条目
        """
        self._faqs.append(faq)
        logger.info("FAQ已添加", extra={"question": faq.question})

    def get_faqs_dict(self) -> list[dict[str, Any]]:
        """获取FAQ列表（字典格式，用于API响应）"""
        return [
            {
                "question": f.question,
                "answer": f.answer,
                "category": f.category,
                "keywords": f.keywords,
            }
            for f in self._faqs
        ]

    # ----------------------------------------------------------
    # 意图识别
    # ----------------------------------------------------------
    def classify_intent(self, text: str) -> tuple[IntentType, float]:
        """识别用户意图

        Args:
            text: 用户输入文本

        Returns:
            (意图类型, 置信度)
        """
        text_lower = text.lower().strip()

        if not text_lower:
            return IntentType.UNKNOWN, 0.0

        best_intent = IntentType.UNKNOWN
        best_score = 0.0

        for intent, keywords in INTENT_KEYWORDS.items():
            matched = sum(1 for kw in keywords if kw.lower() in text_lower)
            if keywords:
                score = matched / len(keywords)
                if score > best_score:
                    best_score = score
                    best_intent = intent

        # 如果意图置信度低于阈值，尝试FAQ匹配
        if best_score < INTENT_CONFIDENCE_THRESHOLD:
            # 检查是否匹配FAQ
            matched_faq = self._match_faq(text_lower)
            if matched_faq and matched_faq[1] >= 0.6:
                return IntentType.FAQ_MATCH, matched_faq[1]

        return best_intent, round(best_score, 4)

    # ----------------------------------------------------------
    # FAQ 匹配
    # ----------------------------------------------------------
    def _match_faq(self, text: str) -> tuple[FAQItem | None, float]:
        """匹配FAQ知识库

        Args:
            text: 用户输入文本

        Returns:
            (匹配的FAQ条目, 匹配分数) 或 (None, 0.0)
        """
        best_faq: FAQItem | None = None
        best_score = 0.0

        for faq in self._faqs:
            score = faq.match_score(text)
            if score > best_score:
                best_score = score
                best_faq = faq

        return best_faq, best_score

    # ----------------------------------------------------------
    # 会话管理
    # ----------------------------------------------------------
    def get_or_create_session(
        self, session_id: str | None = None, user_id: int | None = None
    ) -> ChatSession:
        """获取或创建聊天会话

        Args:
            session_id: 会话ID，为空时创建新会话
            user_id: 用户ID

        Returns:
            ChatSession 实例
        """
        if session_id and session_id in self._sessions:
            session = self._sessions[session_id]
            if user_id is not None:
                session.user_id = user_id
            return session

        session = ChatSession(
            session_id=session_id or str(uuid.uuid4()),
            user_id=user_id,
        )
        self._sessions[session.session_id] = session

        logger.debug(
            "创建新会话",
            extra={
                "session_id": session.session_id,
                "user_id": user_id,
            },
        )
        return session

    def get_session(self, session_id: str) -> ChatSession | None:
        """获取指定会话

        Args:
            session_id: 会话ID

        Returns:
            ChatSession 或 None
        """
        return self._sessions.get(session_id)

    def get_session_history(
        self, session_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """获取会话历史

        Args:
            session_id: 会话ID
            limit: 返回消息数量限制

        Returns:
            消息字典列表
        """
        session = self._sessions.get(session_id)
        if not session:
            return []

        return [
            {
                "role": m.role.value,
                "content": m.content,
                "timestamp": m.timestamp.isoformat(),
            }
            for m in session.messages[-limit:]
        ]

    # ----------------------------------------------------------
    # 响应生成
    # ----------------------------------------------------------
    def process_message(
        self,
        text: str,
        session_id: str | None = None,
        user_id: int | None = None,
        enterprise_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """处理用户消息并生成回复

        Args:
            text: 用户输入文本
            session_id: 会话ID（为空则创建新会话）
            user_id: 用户ID
            enterprise_data: 企业相关数据（可选）

        Returns:
            响应字典，包含回复内容、意图、匹配的FAQ等
        """
        try:
            # ---- 1. 获取/创建会话 ----
            session = self.get_or_create_session(
                session_id=session_id, user_id=user_id
            )

            # ---- 2. 保存用户消息 ----
            user_msg = ChatMessage(
                role=MessageRole.USER,
                content=text,
            )
            session.add_message(user_msg)

            # ---- 3. 意图识别 ----
            intent, confidence = self.classify_intent(text)

            # ---- 4. 检查是否转人工 ----
            if intent == IntentType.HUMAN_ESCALATE:
                response_data = self._handle_escalation(session, text)
                return response_data

            # ---- 5. 生成回复 ----
            response_data = self._generate_response(
                session=session,
                text=text,
                intent=intent,
                intent_confidence=confidence,
                enterprise_data=enterprise_data,
            )

            # ---- 6. 保存机器人回复 ----
            bot_msg = ChatMessage(
                role=MessageRole.BOT,
                content=response_data["reply"],
                metadata={
                    "intent": intent.value,
                    "intent_confidence": confidence,
                    "matched_faq": response_data.get("matched_faq"),
                },
            )
            session.add_message(bot_msg)

            logger.info(
                "消息处理完成",
                extra={
                    "session_id": session.session_id,
                    "user_id": user_id,
                    "intent": intent.value,
                    "confidence": confidence,
                },
            )

            return {
                "session_id": session.session_id,
                "reply": response_data["reply"],
                "intent": intent.value,
                "intent_confidence": confidence,
                "matched_faq": response_data.get("matched_faq"),
                "suggestions": response_data.get("suggestions", []),
                "escalated": False,
            }

        except Exception as exc:
            logger.error(
                "处理消息异常",
                extra={
                    "session_id": session_id,
                    "user_id": user_id,
                    "error": str(exc),
                },
                exc_info=True,
            )
            return {
                "session_id": session_id or "",
                "reply": "抱歉，系统出现了异常，请稍后再试或联系人工客服。",
                "intent": "error",
                "intent_confidence": 0.0,
                "matched_faq": None,
                "suggestions": ["转人工", "联系客服"],
                "escalated": False,
            }

    def _generate_response(
        self,
        session: ChatSession,
        text: str,
        intent: IntentType,
        intent_confidence: float,
        enterprise_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """根据意图生成回复

        Args:
            session: 聊天会话
            text: 用户输入
            intent: 意图
            intent_confidence: 意图置信度
            enterprise_data: 企业数据

        Returns:
            回复字典
        """
        suggestions = self._get_suggestions(intent)

        # ---- 问候 ----
        if intent == IntentType.GREETING:
            return {
                "reply": (
                    "您好！我是链客宝AI客服助手，很高兴为您服务！\n\n"
                    "您可以问我以下问题：\n"
                    "1. 如何成为经销商/加盟商？\n"
                    "2. 加盟费用和会员等级\n"
                    "3. 如何入驻平台\n"
                    "4. 签约流程\n"
                    "5. 对接会参加方式\n\n"
                    "或者直接输入您的问题，我会尽力为您解答！"
                ),
                "matched_faq": None,
                "suggestions": [
                    "如何加盟？",
                    "费用多少？",
                    "怎么入驻？",
                    "转人工",
                ],
            }

        # ---- FAQ匹配 ----
        matched_faq, faq_score = self._match_faq(text)

        # 如果FAQ匹配度足够高（>0.4），直接返回FAQ答案
        if matched_faq and faq_score >= 0.4:
            return {
                "reply": matched_faq.answer,
                "matched_faq": matched_faq.question,
                "suggestions": suggestions,
            }

        # ---- 根据意图回复 ----
        intent_replies = {
            IntentType.FRANCHISE_CONSULT: (
                "我理解您对链客宝加盟感兴趣！以下是一些基本信息：\n\n"
                "**成为加盟商流程**：\n"
                "注册账号 -> 提交资质 -> 平台审核 -> 签署合同 -> 缴纳费用 -> 开通权限\n\n"
                "**会员等级**：\n"
                "基础版（免费）-> 专业版（￥9,800/年）-> 旗舰版（￥29,800/年）-> 定制版（面议）\n\n"
                "我可以为您详细介绍某一方面，请告诉我您更关心什么？"
            ),
            IntentType.SIGNING_PROGRESS: (
                "关于签约进度和合同相关的问题：\n\n"
                "**签约流程**：\n"
                "匹配成功 -> 发起签约 -> 选择模板 -> 填写条款 -> e签宝签署 -> 合同生效\n\n"
                "**查看签约进度**：\n"
                "登录后台 -> 合同管理 -> 查看合同状态\n\n"
                "如需查询具体合同的进度，请提供合同编号或相关企业名称。"
            ),
            IntentType.ENTERPRISE_QUERY: (
                "关于企业信息查询：\n\n"
                "您可以在链客宝平台直接查询企业信息，包括：\n"
                "- 工商基本信息\n"
                "- 司法/经营风险\n"
                "- 知识产权\n"
                "- 信用报告（专业版以上）\n\n"
                "数据来源：企查查官方API，每日更新。\n\n"
                "请输入您想查询的企业名称。"
            ),
        }

        if intent in intent_replies:
            return {
                "reply": intent_replies[intent],
                "matched_faq": None,
                "suggestions": suggestions,
            }

        # ---- 兜底回复 ----
        return {
            "reply": (
                "抱歉，我暂时无法回答这个问题。\n\n"
                "您可以尝试以下方式：\n"
                "1. 换个说法重新描述您的问题\n"
                "2. 从下面选择常见问题\n"
                "3. 输入转人工联系人工客服\n\n"
                "常见问题：\n"
                "- 如何成为加盟商？\n"
                "- 加盟费用多少？\n"
                "- 如何入驻平台？\n"
                "- 签约流程是怎样的？\n"
                "- 对接会怎么参加？"
            ),
            "matched_faq": None,
            "suggestions": [
                "如何加盟？",
                "费用多少？",
                "怎么入驻？",
                "转人工",
            ],
        }

    def _get_suggestions(self, intent: IntentType) -> list[str]:
        """根据意图获取快捷建议问题

        Args:
            intent: 用户意图

        Returns:
            建议问题列表
        """
        suggestions_map: dict[IntentType, list[str]] = {
            IntentType.FRANCHISE_CONSULT: [
                "加盟费多少？",
                "如何成为经销商？",
                "有哪些会员等级？",
            ],
            IntentType.SIGNING_PROGRESS: [
                "签约流程详解",
                "怎么用e签宝",
                "合同模板有哪些",
            ],
            IntentType.ENTERPRISE_QUERY: [
                "企查查怎么用",
                "企业认证需要什么",
            ],
            IntentType.GREETING: [
                "如何加盟？",
                "费用多少？",
                "怎么入驻？",
                "转人工",
            ],
            IntentType.HUMAN_ESCALATE: [],
            IntentType.UNKNOWN: [
                "如何加盟？",
                "费用多少？",
                "怎么入驻？",
                "转人工",
            ],
            IntentType.FAQ_MATCH: [
                "如何加盟？",
                "费用多少？",
                "怎么入驻？",
            ],
        }
        return suggestions_map.get(intent, [])

    # ----------------------------------------------------------
    # 转人工
    # ----------------------------------------------------------
    def _handle_escalation(
        self, session: ChatSession, text: str
    ) -> dict[str, Any]:
        """处理转人工请求

        Args:
            session: 聊天会话
            text: 用户输入

        Returns:
            响应字典包含转人工信息
        """
        self._escalation_counter += 1
        ticket_id = (
            "ESC-"
            f"{datetime.now(timezone.utc).strftime('%Y%m%d')}-"
            f"{self._escalation_counter:04d}"
        )

        ticket = {
            "ticket_id": ticket_id,
            "status": EscalationStatus.PENDING.value,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "user_message": text,
            "session_id": session.session_id,
            "user_id": session.user_id,
            "context_summary": self._build_context_summary(session),
        }

        session.escalated = True
        session.escalation_ticket = ticket

        # 记录转人工事件
        bot_msg = ChatMessage(
            role=MessageRole.BOT,
            content=(
                f"【系统】已创建转人工工单 {ticket_id}，"
                "客服人员将尽快与您联系。"
            ),
            metadata={"event": "escalation", "ticket_id": ticket_id},
        )
        session.add_message(bot_msg)

        logger.info(
            "转人工工单已创建",
            extra={
                "ticket_id": ticket_id,
                "session_id": session.session_id,
                "user_id": session.user_id,
            },
        )

        return {
            "session_id": session.session_id,
            "reply": (
                f"**已为您创建转人工工单**\n\n"
                f"工单编号：{ticket_id}\n"
                f"创建时间：{ticket['created_at']}\n\n"
                "我们的客服人员将在**30分钟内**与您联系，请保持通讯畅通。\n\n"
                "您也可以直接拨打客服热线：**400-888-8888**，"
                "提供工单号可快速对接。"
            ),
            "intent": IntentType.HUMAN_ESCALATE.value,
            "intent_confidence": 1.0,
            "matched_faq": None,
            "suggestions": ["客服电话", "服务时间", "查看工单"],
            "escalated": True,
            "ticket": ticket,
        }

    def _build_context_summary(self, session: ChatSession) -> str:
        """构建会话上下文摘要（用于转人工时提供给客服）

        Args:
            session: 聊天会话

        Returns:
            上下文摘要文本
        """
        recent = session.get_recent_context(rounds=3)
        if not recent:
            return "无历史对话记录"

        summary_parts = []
        for msg in recent:
            role_label = "用户" if msg["role"] == "user" else "系统"
            summary_parts.append(f"{role_label}: {msg['content'][:200]}")

        return "\n".join(summary_parts)

    def create_escalation_ticket(
        self,
        session_id: str,
        reason: str = "",
        user_id: int | None = None,
    ) -> dict[str, Any] | None:
        """主动创建转人工工单

        Args:
            session_id: 会话ID
            reason: 转人工原因
            user_id: 用户ID

        Returns:
            工单信息或None
        """
        try:
            session = self._sessions.get(session_id)
            if not session:
                logger.warning(
                    "会话不存在，无法创建转人工工单",
                    extra={"session_id": session_id},
                )
                return None

            # 模拟用户消息
            return self.process_message(
                text=reason or "需要人工帮助",
                session_id=session_id,
                user_id=user_id,
            )

        except Exception as exc:
            logger.error(
                "创建转人工工单异常",
                extra={"session_id": session_id, "error": str(exc)},
                exc_info=True,
            )
            return None


# ============================================================
# 模块级单例（惰性初始化）
# ============================================================
_chatbot_instance: AIChatbotEngine | None = None


def get_chatbot_engine() -> AIChatbotEngine:
    """获取全局 AIChatbotEngine 单例"""
    global _chatbot_instance
    if _chatbot_instance is None:
        _chatbot_instance = AIChatbotEngine()
    return _chatbot_instance
