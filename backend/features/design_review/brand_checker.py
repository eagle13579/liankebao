"""
审美评估系统 — 品牌一致性检查器
==================================
检查 AI 数字名片的品牌一致性，包括 Logo、配色、字体、语调等维度。

铁律六：只新增不覆盖，独立模块。
"""

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================
# 品牌检查规则
# ============================================================

BRAND_RULES = {
    "logo_required": {"severity": "error", "message": "品牌 Logo 缺失"},
    "logo_min_size": {"value": 48, "severity": "warning", "message": "Logo 尺寸过小（最小 {min}px，当前 {current}px）"},
    "color_alignment": {"max_deviation": 2, "severity": "error", "message": "品牌色偏差过大：{colors}"},
    "font_consistency": {"severity": "warning", "message": "检测到非品牌字体：{fonts}"},
    "tone_alignment": {"severity": "warning", "message": "语调与品牌风格不一致：检测到 {tone}，期望 {expected}"},
    "tagline_present": {"severity": "info", "message": "建议添加品牌 Slogan / Tagline"},
}


@dataclass
class BrandIssue:
    """品牌一致性问题"""
    rule_name: str
    severity: str  # error / warning / info
    message: str
    element: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BrandCheckResult:
    """品牌检查结果"""
    passed: bool = False
    issues: list = field(default_factory=list)
    total_checks: int = 0
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    brand_score: int = 100  # 百分制
    check_timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "total_checks": self.total_checks,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "brand_score": self.brand_score,
            "check_timestamp": self.check_timestamp,
            "issues": [i.to_dict() if isinstance(i, BrandIssue) else i for i in self.issues],
        }


@dataclass
class BrandProfile:
    """品牌档案"""
    name: str
    primary_color: str
    secondary_color: str
    font_families: list
    tone: str  # professional / friendly / innovative / luxury / etc.
    has_logo: bool = True
    tagline: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class BrandChecker:
    """
    品牌一致性检查器。
    检查设计是否符合品牌规范。
    """

    def __init__(self, brand_profile: Optional[BrandProfile] = None):
        self.brand_profile = brand_profile or BrandProfile(
            name="链客宝",
            primary_color="#1A73E8",
            secondary_color="#FFFFFF",
            font_families=["Inter", "PingFang SC"],
            tone="professional",
            has_logo=True,
            tagline="链接商业价值",
        )
        logger.info(f"BrandChecker 初始化: {self.brand_profile.name}")

    def _check_logo(self, design_data: dict) -> list:
        """检查 Logo"""
        issues = []
        logo = design_data.get("logo", {})

        if not logo.get("present", False):
            issues.append(BrandIssue(
                rule_name="logo_required",
                severity="error",
                message=BRAND_RULES["logo_required"]["message"],
                element="Logo",
            ))
        else:
            logo_size = logo.get("size", 0)
            min_size = BRAND_RULES["logo_min_size"]["value"]
            if logo_size < min_size:
                msg = BRAND_RULES["logo_min_size"]["message"].format(
                    min=min_size,
                    current=logo_size,
                )
                issues.append(BrandIssue(
                    rule_name="logo_min_size",
                    severity="warning",
                    message=msg,
                    element="Logo",
                ))

        return issues

    def _check_colors(self, design_data: dict) -> list:
        """检查颜色一致性"""
        issues = []
        used_colors = design_data.get("colors", [])
        brand_primary = self.brand_profile.primary_color.lower()
        brand_secondary = self.brand_profile.secondary_color.lower()

        non_brand = [c for c in used_colors if c.lower() not in (brand_primary, brand_secondary)]
        max_dev = BRAND_RULES["color_alignment"]["max_deviation"]

        if len(non_brand) > max_dev:
            msg = BRAND_RULES["color_alignment"]["message"].format(
                colors=", ".join(non_brand[:5])
            )
            issues.append(BrandIssue(
                rule_name="color_alignment",
                severity="error",
                message=msg,
                element="品牌色",
            ))

        return issues

    def _check_fonts(self, design_data: dict) -> list:
        """检查字体一致性"""
        issues = []
        used_fonts = design_data.get("fonts", [])
        brand_fonts = [f.lower() for f in self.brand_profile.font_families]

        non_brand = [f for f in used_fonts if f.lower() not in brand_fonts]
        if non_brand:
            msg = BRAND_RULES["font_consistency"]["message"].format(
                fonts=", ".join(non_brand[:3])
            )
            issues.append(BrandIssue(
                rule_name="font_consistency",
                severity="warning",
                message=msg,
                element="字体",
            ))

        return issues

    def _check_tone(self, design_data: dict) -> list:
        """检查语调一致性"""
        issues = []
        detected_tone = design_data.get("tone", "")
        expected_tone = self.brand_profile.tone

        if detected_tone and detected_tone != expected_tone:
            msg = BRAND_RULES["tone_alignment"]["message"].format(
                tone=detected_tone,
                expected=expected_tone,
            )
            issues.append(BrandIssue(
                rule_name="tone_alignment",
                severity="warning",
                message=msg,
                element="语调",
            ))

        return issues

    def _check_tagline(self, design_data: dict) -> list:
        """检查 Tagline"""
        issues = []
        has_tagline = design_data.get("has_tagline", False)

        if not has_tagline:
            issues.append(BrandIssue(
                rule_name="tagline_present",
                severity="info",
                message=BRAND_RULES["tagline_present"]["message"],
                element="Tagline",
            ))

        return issues

    def check_brand(self, design_data: dict) -> BrandCheckResult:
        """
        执行品牌一致性检查。

        Args:
            design_data: 设计数据字典，包含 logo, colors, fonts, tone, has_tagline 等字段

        Returns:
            BrandCheckResult: 检查结果
        """
        all_issues = []
        all_issues.extend(self._check_logo(design_data))
        all_issues.extend(self._check_colors(design_data))
        all_issues.extend(self._check_fonts(design_data))
        all_issues.extend(self._check_tone(design_data))
        all_issues.extend(self._check_tagline(design_data))

        total = len(all_issues)
        errors = sum(1 for i in all_issues if i.severity == "error")
        warnings = sum(1 for i in all_issues if i.severity == "warning")
        infos = sum(1 for i in all_issues if i.severity == "info")

        # 评分：100 分起，每个 error 扣 20，每个 warning 扣 5
        brand_score = max(0, 100 - errors * 20 - warnings * 5)
        passed = errors == 0

        result = BrandCheckResult(
            passed=passed,
            issues=all_issues,
            total_checks=total,
            error_count=errors,
            warning_count=warnings,
            info_count=infos,
            brand_score=brand_score,
            check_timestamp=datetime.utcnow().isoformat() + "Z",
        )

        logger.info(f"品牌一致性检查完成: {result.passed=}, brand_score={result.brand_score}, "
                     f"errors={errors}, warnings={warnings}")
        return result


# ============================================================
# 烟雾测试
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=" * 60)
    print("🧪 BrandChecker 烟雾测试")
    print("=" * 60)

    checker = BrandChecker()

    # 测试1: 完美品牌设计
    perfect = {
        "logo": {"present": True, "size": 128},
        "colors": ["#1A73E8", "#FFFFFF"],
        "fonts": ["Inter", "PingFang SC"],
        "tone": "professional",
        "has_tagline": True,
    }
    result = checker.check_brand(perfect)
    assert result.passed, "测试1失败：完美品牌设计应通过"
    print(f"✅ 测试1 完美品牌: passed={result.passed}, score={result.brand_score}")

    # 测试2: Logo 缺失
    no_logo = {"logo": {"present": False}, "colors": ["#1A73E8"], "fonts": ["Inter"], "tone": "professional", "has_tagline": True}
    result_nl = checker.check_brand(no_logo)
    assert not result_nl.passed, "测试2失败：Logo 缺失应不通过"
    print(f"✅ 测试2 Logo缺失: passed={result_nl.passed}, errors={result_nl.error_count}")

    # 测试3: 语调不匹配
    wrong_tone = {
        "logo": {"present": True, "size": 64},
        "colors": ["#1A73E8"],
        "fonts": ["Inter"],
        "tone": "casual",
        "has_tagline": True,
    }
    result_wt = checker.check_brand(wrong_tone)
    assert result_wt.warning_count > 0, "测试3失败：语调不匹配应发出警告"
    print(f"✅ 测试3 语调不匹配: warnings={result_wt.warning_count}")

    # 测试4: 自定义品牌档案
    custom_profile = BrandProfile(
        name="测试品牌",
        primary_color="#FF6600",
        secondary_color="#000000",
        font_families=["CustomFont"],
        tone="innovative",
        has_logo=True,
        tagline="测试用",
    )
    custom_checker = BrandChecker(brand_profile=custom_profile)
    data = {
        "logo": {"present": True, "size": 48},
        "colors": ["#FF6600", "#000000"],
        "fonts": ["CustomFont"],
        "tone": "innovative",
        "has_tagline": True,
    }
    result_custom = custom_checker.check_brand(data)
    assert result_custom.passed, "测试4失败：自定义品牌应通过"
    print(f"✅ 测试4 自定义品牌: passed={result_custom.passed}, score={result_custom.brand_score}")

    print(f"\n🎉 所有烟雾测试通过!\n")
