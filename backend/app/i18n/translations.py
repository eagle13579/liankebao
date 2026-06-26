"""
多语言翻译字典 & Translator 类
===============================
支持：中文 (zh), 韩语 (ko), 英语 (en)
默认：中文
"""

from typing import Any, Optional

# ===================================================================
# 翻译字典 — 每个语言至少 30 个 key
# 覆盖：导航 / 按钮 / 表单 / 提示 / 错误 / 匹配相关
# ===================================================================

TRANSLATIONS: dict[str, dict[str, str]] = {
    # ──────────── 中文 (默认) ────────────
    "zh": {
        # 导航
        "nav_home": "首页",
        "nav_profile": "个人中心",
        "nav_matching": "匹配中心",
        "nav_messages": "消息",
        "nav_settings": "设置",
        "nav_help": "帮助中心",
        "nav_logout": "退出登录",
        "nav_dashboard": "控制台",
        "nav_discover": "发现",
        "nav_notifications": "通知",
        # 按钮
        "btn_submit": "提交",
        "btn_cancel": "取消",
        "btn_save": "保存",
        "btn_delete": "删除",
        "btn_edit": "编辑",
        "btn_search": "搜索",
        "btn_upload": "上传",
        "btn_download": "下载",
        "btn_confirm": "确认",
        "btn_retry": "重试",
        # 表单
        "form_name": "姓名",
        "form_email": "邮箱",
        "form_phone": "手机号",
        "form_company": "公司名称",
        "form_industry": "行业",
        "form_description": "描述",
        "form_required": "此项为必填",
        "form_invalid_email": "请输入有效的邮箱地址",
        "form_invalid_phone": "请输入有效的手机号码",
        "form_min_length": "至少需要 {n} 个字符",
        # 提示
        "prompt_loading": "加载中...",
        "prompt_success": "操作成功",
        "prompt_failed": "操作失败",
        "prompt_no_data": "暂无数据",
        "prompt_confirm_delete": "确定要删除吗？此操作不可恢复。",
        # 错误
        "error_network": "网络异常，请稍后重试",
        "error_server": "服务器内部错误",
        "error_unauthorized": "未授权，请先登录",
        "error_forbidden": "无权访问此资源",
        "error_not_found": "请求的资源不存在",
        "error_timeout": "请求超时",
        "error_validation": "参数校验失败",
        "error_too_many_requests": "请求过于频繁，请稍后再试",
        # 匹配相关
        "match_title": "为您推荐的最佳匹配",
        "match_score": "匹配度",
        "match_industry": "行业匹配",
        "match_location": "地区匹配",
        "match_interests": "兴趣匹配",
        "match_no_result": "暂未找到匹配对象",
        "match_view_detail": "查看详情",
        "match_start_chat": "开始沟通",
        "match_add_favorite": "收藏",
        "match_remove_favorite": "取消收藏",
    },
    # ──────────── 韩语 ────────────
    "ko": {
        # Navigation
        "nav_home": "홈",
        "nav_profile": "마이페이지",
        "nav_matching": "매칭 센터",
        "nav_messages": "메시지",
        "nav_settings": "설정",
        "nav_help": "도움말",
        "nav_logout": "로그아웃",
        "nav_dashboard": "대시보드",
        "nav_discover": "발견",
        "nav_notifications": "알림",
        # Buttons
        "btn_submit": "제출",
        "btn_cancel": "취소",
        "btn_save": "저장",
        "btn_delete": "삭제",
        "btn_edit": "편집",
        "btn_search": "검색",
        "btn_upload": "업로드",
        "btn_download": "다운로드",
        "btn_confirm": "확인",
        "btn_retry": "재시도",
        # Forms
        "form_name": "이름",
        "form_email": "이메일",
        "form_phone": "휴대폰 번호",
        "form_company": "회사명",
        "form_industry": "업종",
        "form_description": "설명",
        "form_required": "필수 입력 항목입니다",
        "form_invalid_email": "유효한 이메일 주소를 입력하세요",
        "form_invalid_phone": "유효한 휴대폰 번호를 입력하세요",
        "form_min_length": "최소 {n}자 이상 입력하세요",
        # Prompts
        "prompt_loading": "로딩 중...",
        "prompt_success": "작업 성공",
        "prompt_failed": "작업 실패",
        "prompt_no_data": "데이터가 없습니다",
        "prompt_confirm_delete": "삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.",
        # Errors
        "error_network": "네트워크 오류가 발생했습니다. 나중에 다시 시도하세요",
        "error_server": "서버 내부 오류",
        "error_unauthorized": "인증되지 않았습니다. 로그인해 주세요",
        "error_forbidden": "이 리소스에 접근할 권한이 없습니다",
        "error_not_found": "요청한 리소스를 찾을 수 없습니다",
        "error_timeout": "요청 시간이 초과되었습니다",
        "error_validation": "매개변수 검증 실패",
        "error_too_many_requests": "요청이 너무 많습니다. 잠시 후 다시 시도하세요",
        # Matching
        "match_title": "추천 최적 매칭",
        "match_score": "매칭율",
        "match_industry": "업종 매칭",
        "match_location": "지역 매칭",
        "match_interests": "관심사 매칭",
        "match_no_result": "매칭 대상을 찾을 수 없습니다",
        "match_view_detail": "상세 보기",
        "match_start_chat": "대화 시작",
        "match_add_favorite": "즐겨찾기",
        "match_remove_favorite": "즐겨찾기 해제",
    },
    # ──────────── 英语 ────────────
    "en": {
        # Navigation
        "nav_home": "Home",
        "nav_profile": "Profile",
        "nav_matching": "Matching Center",
        "nav_messages": "Messages",
        "nav_settings": "Settings",
        "nav_help": "Help Center",
        "nav_logout": "Log Out",
        "nav_dashboard": "Dashboard",
        "nav_discover": "Discover",
        "nav_notifications": "Notifications",
        # Buttons
        "btn_submit": "Submit",
        "btn_cancel": "Cancel",
        "btn_save": "Save",
        "btn_delete": "Delete",
        "btn_edit": "Edit",
        "btn_search": "Search",
        "btn_upload": "Upload",
        "btn_download": "Download",
        "btn_confirm": "Confirm",
        "btn_retry": "Retry",
        # Forms
        "form_name": "Name",
        "form_email": "Email",
        "form_phone": "Phone Number",
        "form_company": "Company Name",
        "form_industry": "Industry",
        "form_description": "Description",
        "form_required": "This field is required",
        "form_invalid_email": "Please enter a valid email address",
        "form_invalid_phone": "Please enter a valid phone number",
        "form_min_length": "At least {n} characters required",
        # Prompts
        "prompt_loading": "Loading...",
        "prompt_success": "Operation successful",
        "prompt_failed": "Operation failed",
        "prompt_no_data": "No data available",
        "prompt_confirm_delete": "Are you sure you want to delete? This action cannot be undone.",
        # Errors
        "error_network": "Network error, please try again later",
        "error_server": "Internal server error",
        "error_unauthorized": "Unauthorized, please log in first",
        "error_forbidden": "You do not have permission to access this resource",
        "error_not_found": "Requested resource not found",
        "error_timeout": "Request timed out",
        "error_validation": "Parameter validation failed",
        "error_too_many_requests": "Too many requests, please try again later",
        # Matching
        "match_title": "Best Matches for You",
        "match_score": "Match Score",
        "match_industry": "Industry Match",
        "match_location": "Location Match",
        "match_interests": "Interest Match",
        "match_no_result": "No matching results found",
        "match_view_detail": "View Details",
        "match_start_chat": "Start Chat",
        "match_add_favorite": "Add to Favorites",
        "match_remove_favorite": "Remove from Favorites",
    },
}

# 支持的语言列表
AVAILABLE_LANGUAGES = sorted(TRANSLATIONS.keys())  # ["en", "ko", "zh"]


class Translator:
    """多语言翻译器

    用法:
        t = Translator("ko")
        msg = t.t("form_min_length", n=10)
        # → "최소 10자 이상 입력하세요"
    """

    def __init__(self, lang: str = "zh"):
        self._lang = lang if lang in TRANSLATIONS else "zh"

    # ── 公开方法 ──────────────────────────────────────────────────

    def t(self, key: str, **kwargs: Any) -> str:
        """翻译 key，支持 {name} 变量替换"""
        lang_dict = TRANSLATIONS.get(self._lang, TRANSLATIONS["zh"])
        text = lang_dict.get(key)
        if text is None:
            # 回退到中文
            text = TRANSLATIONS["zh"].get(key, key)
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, ValueError):
                pass
        return text

    def set_lang(self, lang: str) -> None:
        """切换语言"""
        if lang in TRANSLATIONS:
            self._lang = lang

    def get_lang(self) -> str:
        """获取当前语言"""
        return self._lang

    @staticmethod
    def available_languages() -> list[str]:
        """所有可用语言代码列表"""
        return list(AVAILABLE_LANGUAGES)

    @staticmethod
    def get_translations(lang: str = "zh") -> dict[str, str]:
        """获取指定语言的完整翻译字典"""
        if lang in TRANSLATIONS:
            return dict(TRANSLATIONS[lang])
        return dict(TRANSLATIONS["zh"])
