"""
i18n 国际化模块 — 100+ 中英翻译键

用法:
    from app.i18n import t, detect_lang

    # 在中间件中检测语言
    lang = detect_lang(request.headers.get("Accept-Language", ""))

    # 翻译
    message = t("画册不存在", lang)
"""

import re

# ============================================================
# 翻译字典: key -> {lang: translation}
# ============================================================
TRANSLATIONS: dict[str, dict[str, str]] = {
    # ── auth (认证) ──
    "该手机号已注册": {"zh": "该手机号已注册", "en": "This phone number is already registered"},
    "注册失败，请稍后再试": {"zh": "注册失败，请稍后再试", "en": "Registration failed, please try again later"},
    "创建 token 失败": {"zh": "创建 token 失败", "en": "Failed to create token"},
    "手机号或密码错误": {"zh": "手机号或密码错误", "en": "Invalid phone number or password"},
    "缺少 Authorization 头，请先登录": {
        "zh": "缺少 Authorization 头，请先登录",
        "en": "Missing Authorization header, please login first",
    },
    "Token 无效或已过期，请重新登录": {
        "zh": "Token 无效或已过期，请重新登录",
        "en": "Token invalid or expired, please login again",
    },
    "已退出登录": {"zh": "已退出登录", "en": "Logged out successfully"},
    # ── brochure (画册) ──
    "画册不存在": {"zh": "画册不存在", "en": "Brochure not found"},
    "画册创建成功": {"zh": "画册创建成功", "en": "Brochure created successfully"},
    "画册更新成功": {"zh": "画册更新成功", "en": "Brochure updated successfully"},
    "画册已删除": {"zh": "画册已删除", "en": "Brochure deleted successfully"},
    "该用户画册已存在": {"zh": "该用户画册已存在", "en": "A brochure already exists for this user"},
    "不能为其他用户创建画册": {"zh": "不能为其他用户创建画册", "en": "Cannot create brochure for other users"},
    "无权修改此画册": {"zh": "无权修改此画册", "en": "No permission to modify this brochure"},
    "无权删除此画册": {"zh": "无权删除此画册", "en": "No permission to delete this brochure"},
    " 的数字名片": {"zh": " 的数字名片", "en": "'s Digital Business Card"},
    # ── trust network (信任网络) ──
    "无权操作其他用户的信任网络": {
        "zh": "无权操作其他用户的信任网络",
        "en": "No permission to modify other users' trust network",
    },
    "被信任用户画册不存在": {"zh": "被信任用户画册不存在", "en": "Trusted user's brochure not found"},
    "添加信任关系失败": {"zh": "添加信任关系失败", "en": "Failed to add trust relationship"},
    "移除信任关系失败": {"zh": "移除信任关系失败", "en": "Failed to remove trust relationship"},
    "信任关系添加成功": {"zh": "信任关系添加成功", "en": "Trust relationship added successfully"},
    "信任关系已移除": {"zh": "信任关系已移除", "en": "Trust relationship removed successfully"},
    # ── match (匹配) ──
    "源用户画册不存在": {"zh": "源用户画册不存在", "en": "Source user's brochure not found"},
    "匹配完成": {"zh": "匹配完成", "en": "Matching completed"},
    # ── user (用户) ──
    "用户不存在": {"zh": "用户不存在", "en": "User not found"},
    # ── sync (同步) ──
    "同步完成": {"zh": "同步完成", "en": "Sync completed"},
    "链客宝AI桥接模块未加载，同步跳过": {
        "zh": "链客宝AI桥接模块未加载，同步跳过",
        "en": "Chainke bridge module not loaded, sync skipped",
    },
    "链客宝AI同步完成": {"zh": "链客宝AI同步完成", "en": "Chainke sync completed"},
    # ── batch import (批量导入) ──
    "导入列表不能为空": {"zh": "导入列表不能为空", "en": "Import list cannot be empty"},
    "写入数据库失败": {"zh": "写入数据库失败", "en": "Failed to write to database"},
    "成功导入": {"zh": "成功导入", "en": "Successfully imported"},
    "个用户，失败": {"zh": "个用户，失败", "en": " user(s), failed: "},
    # ── error (错误) ──
    "请求过于频繁，请稍后再试": {"zh": "请求过于频繁，请稍后再试", "en": "Too many requests, please try again later"},
    "内部服务器错误": {"zh": "内部服务器错误", "en": "Internal server error"},
    "资源未找到": {"zh": "资源未找到", "en": "Resource not found"},
    "请求参数错误": {"zh": "请求参数错误", "en": "Invalid request parameters"},
    "无权限访问": {"zh": "无权限访问", "en": "Access denied"},
    "服务暂不可用": {"zh": "服务暂不可用", "en": "Service temporarily unavailable"},
    "操作成功": {"zh": "操作成功", "en": "Operation successful"},
    # ── common (通用) ──
    "未知": {"zh": "未知", "en": "Unknown"},
    "暂无数据": {"zh": "暂无数据", "en": "No data"},
    # ── health (健康检查) ──
    "健康": {"zh": "健康", "en": "healthy"},
    "不健康": {"zh": "不健康", "en": "unhealthy"},
    # ── visitor (访客) ──
    "已被浏览": {"zh": "已被浏览", "en": "Visited"},
    "次": {"zh": "次", "en": " times"},
    # ── rate limit (限流) ──
    "限流触发": {"zh": "限流触发", "en": "Rate limit triggered"},
    # ── metrics (指标) ──
    "指标收集器状态正常": {"zh": "指标收集器状态正常", "en": "Metrics collector status normal"},
    "无指标数据": {"zh": "无指标数据", "en": "No metrics data"},
    # ── auth middleware (认证中间件) ──
    "缺少必要参数": {"zh": "缺少必要参数", "en": "Missing required parameters"},
    "手机号格式错误": {"zh": "手机号格式错误", "en": "Invalid phone number format"},
    "密码长度不足": {"zh": "密码长度不足", "en": "Password too short"},
    "姓名不能为空": {"zh": "姓名不能为空", "en": "Name cannot be empty"},
    # ── general HTTP (通用HTTP) ──
    "请求方法不允许": {"zh": "请求方法不允许", "en": "Method not allowed"},
    "请求实体过大": {"zh": "请求实体过大", "en": "Request entity too large"},
    "不支持的媒体类型": {"zh": "不支持的媒体类型", "en": "Unsupported media type"},
    # ── db (数据库) ──
    "数据库连接失败": {"zh": "数据库连接失败", "en": "Database connection failed"},
    "数据库查询失败": {"zh": "数据库查询失败", "en": "Database query failed"},
    "数据写入失败": {"zh": "数据写入失败", "en": "Data write failed"},
    # ── validation (校验) ──
    "字段格式不正确": {"zh": "字段格式不正确", "en": "Invalid field format"},
    "字段值超出范围": {"zh": "字段值超出范围", "en": "Field value out of range"},
    "字段长度超限": {"zh": "字段长度超限", "en": "Field length exceeded"},
    # ── API response messages (API响应消息) ──
    "数据加载完成": {"zh": "数据加载完成", "en": "Data loading complete"},
    "服务启动成功": {"zh": "服务启动成功", "en": "Service started successfully"},
    "服务已停止": {"zh": "服务已停止", "en": "Service stopped"},
    "正在处理": {"zh": "正在处理", "en": "Processing"},
    "处理完成": {"zh": "处理完成", "en": "Processing complete"},
    # ── search (搜索) ──
    "搜索成功": {"zh": "搜索成功", "en": "Search completed"},
    "搜索结果为空": {"zh": "搜索结果为空", "en": "No search results found"},
    "搜索关键词不能为空": {"zh": "搜索关键词不能为空", "en": "Search keyword cannot be empty"},
    # ── payment (支付) ──
    "支付成功": {"zh": "支付成功", "en": "Payment successful"},
    "支付失败": {"zh": "支付失败", "en": "Payment failed"},
    "支付取消": {"zh": "支付取消", "en": "Payment cancelled"},
    "订单不存在": {"zh": "订单不存在", "en": "Order not found"},
    "订单已过期": {"zh": "订单已过期", "en": "Order expired"},
    # ── notification (通知) ──
    "通知发送成功": {"zh": "通知发送成功", "en": "Notification sent successfully"},
    "通知发送失败": {"zh": "通知发送失败", "en": "Notification failed to send"},
    "无新通知": {"zh": "无新通知", "en": "No new notifications"},
    # ── upload (上传) ──
    "上传成功": {"zh": "上传成功", "en": "Upload successful"},
    "上传失败": {"zh": "上传失败", "en": "Upload failed"},
    "文件类型不支持": {"zh": "文件类型不支持", "en": "File type not supported"},
    "文件大小超限": {"zh": "文件大小超限", "en": "File size exceeded"},
    # ── cache (缓存) ──
    "缓存刷新成功": {"zh": "缓存刷新成功", "en": "Cache refreshed successfully"},
    # ── tag (标签) ──
    "标签不能为空": {"zh": "标签不能为空", "en": "Tag cannot be empty"},
    "标签已存在": {"zh": "标签已存在", "en": "Tag already exists"},
    # ── QR code (二维码) ──
    "二维码生成成功": {"zh": "二维码生成成功", "en": "QR code generated successfully"},
    # ── security (安全) ──
    "操作已记录": {"zh": "操作已记录", "en": "Operation logged"},
    "检测到异常访问": {"zh": "检测到异常访问", "en": "Abnormal access detected"},
    # ── system (系统) ──
    "系统维护中": {"zh": "系统维护中", "en": "System under maintenance"},
    "系统繁忙": {"zh": "系统繁忙", "en": "System busy"},
    "版本": {"zh": "版本", "en": "Version"},
    # ── enterprise (企业) ──
    "企业名称不能为空": {"zh": "企业名称不能为空", "en": "Company name cannot be empty"},
    "企业信息导入成功": {"zh": "企业信息导入成功", "en": "Enterprise info imported successfully"},
    # ── chainke (链客宝AI) ──
    "链客宝AI数据同步中": {"zh": "链客宝AI数据同步中", "en": "Syncing Chainke data"},
    "链客宝AI同步失败": {"zh": "链客宝AI同步失败", "en": "Chainke sync failed"},
    # ── profile (个人资料) ──
    "个人简介": {"zh": "个人简介", "en": "About"},
    "联系方式": {"zh": "联系方式", "en": "Contact"},
    "标签": {"zh": "标签", "en": "Tags"},
    "电话": {"zh": "电话", "en": "Phone"},
    "邮箱": {"zh": "邮箱", "en": "Email"},
    "微信": {"zh": "微信", "en": "WeChat"},
    # ── business card (名片) ──
    "AI数字名片": {"zh": "AI数字名片", "en": "AI Digital Business Card"},
    "扫描二维码查看名片": {"zh": "扫描二维码查看名片", "en": "Scan QR code to view business card"},
    "信任网络": {"zh": "信任网络", "en": "Trust Network"},
    "供需匹配": {"zh": "供需匹配", "en": "Supply-Demand Matching"},
}

# ============================================================
# 语言检测
# ============================================================


def detect_lang(accept_language: str = "") -> str:
    """从 Accept-Language 请求头检测首选语言

    Args:
        accept_language: Accept-Language 请求头的值

    Returns:
        "zh" 或 "en"
    """
    if not accept_language:
        return "zh"

    # 解析 Accept-Language，按 q 权重排序
    languages = re.findall(r"([a-z]{2})(?:-[A-Z]{2})?(?:\s*;\s*q\s*=\s*([0-9.]+))?", accept_language)

    if not languages:
        # 尝试只取前两个字符
        first = accept_language.strip()[:2].lower()
        if first == "en":
            return "en"
        return "zh"

    # 按权重降序排列
    def get_weight(lang_entry):
        lang, weight = lang_entry
        return float(weight) if weight else 1.0

    languages.sort(key=get_weight, reverse=True)

    for lang, _ in languages:
        if lang in ("zh", "en"):
            return lang

    return "zh"


# ============================================================
# 翻译函数
# ============================================================


def t(key: str, lang: str = "zh") -> str:
    """翻译函数

    Args:
        key: 翻译键（中文原文）
        lang: 目标语言 ("zh" 或 "en")

    Returns:
        翻译后的字符串，未找到时返回原键
    """
    entry = TRANSLATIONS.get(key)
    if entry is None:
        return key
    return entry.get(lang, entry.get("zh", key))


def _(key: str, lang: str = "zh") -> str:
    """简写翻译函数，用法与 t() 相同

    Args:
        key: 翻译键
        lang: 目标语言

    Returns:
        翻译后的字符串
    """
    return t(key, lang)


# ============================================================
# 支持的语言列表
# ============================================================
SUPPORTED_LANGUAGES = ["zh", "en"]
SUPPORTED_LANGUAGES_DISPLAY = {
    "zh": "中文",
    "en": "English",
}
