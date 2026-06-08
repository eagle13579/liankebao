"""
审美评估系统 — UI 一致性检查器
================================
基于正则和规则检测 UI 元素一致性。

铁律六：只新增不覆盖，独立模块。
"""

import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================
# 检测规则库
# ============================================================

# 颜色使用规则
COLOR_RULES = {
    "primary_color_count": {"max": 3, "severity": "error", "message": "主色数量超过 {max} 个（当前 {current} 个）"},
    "color_contrast_ratio": {"min": 4.5, "severity": "error", "message": "文字/背景对比度低于 {min}:1"},
    "brand_color_consistency": {"severity": "warning", "message": "检测到非品牌色使用：{colors}"},
}

# 间距规则
SPACING_RULES = {
    "base_unit": 4,
    "scale": [4, 8, 12, 16, 20, 24, 32, 40, 48, 64],
    "severity": "warning",
    "message": "检测到非标间距值：{value}px（推荐使用 4px 基准缩放）",
}

# 字体规则
FONT_RULES = {
    "max_font_families": 3,
    "severity": "warning",
    "message": "字体族超过 {max} 个（当前 {current} 个）",
}

# 圆角规则
RADIUS_RULES = {
    "standard_values": [0, 2, 4, 6, 8, 12, 16],
    "severity": "warning",
    "message": "检测到非标准圆角值：{value}px",
}

# 图标规则
ICON_RULES = {
    "consistent_style": True,
    "severity": "warning",
    "message": "检测到多种图标风格混用（线框/填充/多色）",
}


@dataclass
class UIIssue:
    """UI 一致性问题"""
    rule_name: str
    severity: str  # error / warning / info
    message: str
    element: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class UICheckResult:
    """UI 检查结果"""
    passed: bool = False
    issues: list = field(default_factory=list)
    total_checks: int = 0
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    score: int = 100  # 百分制
    check_timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "total_checks": self.total_checks,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "score": self.score,
            "check_timestamp": self.check_timestamp,
            "issues": [i.to_dict() if isinstance(i, UIIssue) else i for i in self.issues],
        }


class UIChecker:
    """
    UI 一致性检查器。
    基于规则库检测颜色、间距、字体、圆角、图标等维度的一致性。
    """

    def __init__(self):
        logger.info("UIChecker 初始化")

    def _check_colors(self, design_data: dict) -> list:
        """检查颜色一致性"""
        issues = []
        colors = design_data.get("colors", [])
        brand_colors = design_data.get("brand_colors", [])

        # 主色数量
        if len(colors) > COLOR_RULES["primary_color_count"]["max"]:
            msg = COLOR_RULES["primary_color_count"]["message"].format(
                max=COLOR_RULES["primary_color_count"]["max"],
                current=len(colors),
            )
            issues.append(UIIssue(
                rule_name="color_count",
                severity="error",
                message=msg,
                element="全局颜色",
            ))

        # 品牌色一致性
        if brand_colors:
            non_brand = [c for c in colors if c not in brand_colors]
            if non_brand and len(non_brand) > len(brand_colors):
                msg = COLOR_RULES["brand_color_consistency"]["message"].format(
                    colors=", ".join(non_brand[:5])
                )
                issues.append(UIIssue(
                    rule_name="brand_color_consistency",
                    severity="warning",
                    message=msg,
                    element="颜色面板",
                ))

        return issues

    def _check_spacing(self, design_data: dict) -> list:
        """检查间距一致性"""
        issues = []
        spacings = design_data.get("spacings", [])
        scale = SPACING_RULES["scale"]

        for value in spacings:
            if value not in scale and value % SPACING_RULES["base_unit"] != 0:
                msg = SPACING_RULES["message"].format(value=value)
                issues.append(UIIssue(
                    rule_name="spacing_consistency",
                    severity="warning",
                    message=msg,
                    element=f"间距 {value}px",
                ))

        return issues

    def _check_fonts(self, design_data: dict) -> list:
        """检查字体一致性"""
        issues = []
        fonts = design_data.get("fonts", [])

        if len(fonts) > FONT_RULES["max_font_families"]:
            msg = FONT_RULES["message"].format(
                max=FONT_RULES["max_font_families"],
                current=len(fonts),
            )
            issues.append(UIIssue(
                rule_name="font_family_count",
                severity="warning",
                message=msg,
                element="字体面板",
            ))

        return issues

    def _check_radius(self, design_data: dict) -> list:
        """检查圆角一致性"""
        issues = []
        radii = design_data.get("border_radii", [])
        standard = RADIUS_RULES["standard_values"]

        for value in radii:
            if value not in standard:
                msg = RADIUS_RULES["message"].format(value=value)
                issues.append(UIIssue(
                    rule_name="border_radius_consistency",
                    severity="warning",
                    message=msg,
                    element=f"圆角 {value}px",
                ))

        return issues

    def _check_icons(self, design_data: dict) -> list:
        """检查图标风格一致性"""
        issues = []
        icon_styles = design_data.get("icon_styles", [])

        if len(set(icon_styles)) > 1:
            issues.append(UIIssue(
                rule_name="icon_style_consistency",
                severity="warning",
                message=ICON_RULES["message"],
                element="图标集",
            ))

        return issues

    def check(self, design_data: dict) -> UICheckResult:
        """
        执行 UI 一致性检查。

        Args:
            design_data: 设计数据字典，包含 colors, spacings, fonts, border_radii, icon_styles 等字段

        Returns:
            UICheckResult: 检查结果
        """
        all_issues = []
        all_issues.extend(self._check_colors(design_data))
        all_issues.extend(self._check_spacing(design_data))
        all_issues.extend(self._check_fonts(design_data))
        all_issues.extend(self._check_radius(design_data))
        all_issues.extend(self._check_icons(design_data))

        total = len(all_issues)
        errors = sum(1 for i in all_issues if i.severity == "error")
        warnings = sum(1 for i in all_issues if i.severity == "warning")
        infos = sum(1 for i in all_issues if i.severity == "info")

        # 评分：100 分起，每个 error 扣 15，每个 warning 扣 5
        score = max(0, 100 - errors * 15 - warnings * 5)
        passed = errors == 0 and score >= 60

        result = UICheckResult(
            passed=passed,
            issues=all_issues,
            total_checks=total,
            error_count=errors,
            warning_count=warnings,
            info_count=infos,
            score=score,
            check_timestamp=datetime.utcnow().isoformat() + "Z",
        )

        logger.info(f"UI 一致性检查完成: {result.passed=}, {result.score=}, "
                     f"errors={errors}, warnings={warnings}")
        return result


# ============================================================
# 烟雾测试
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=" * 60)
    print("🧪 UIChecker 烟雾测试")
    print("=" * 60)

    checker = UIChecker()

    # 测试1: 完美设计
    perfect = {
        "colors": ["#1A73E8", "#FFFFFF"],
        "brand_colors": ["#1A73E8", "#FFFFFF"],
        "spacings": [4, 8, 12, 16, 24],
        "fonts": ["Inter", "PingFang SC"],
        "border_radii": [4, 8],
        "icon_styles": ["outline"],
    }
    result = checker.check(perfect)
    assert result.passed, "测试1失败：完美设计应通过"
    print(f"✅ 测试1 完美设计: passed={result.passed}, score={result.score}")

    # 测试2: 有问题的设计
    messy = {
        "colors": ["#1A73E8", "#FF0000", "#00FF00", "#0000FF", "#FFA500"],
        "brand_colors": ["#1A73E8", "#FFFFFF"],
        "spacings": [4, 7, 8, 13, 24],
        "fonts": ["Inter", "PingFang SC", "Roboto", "Noto Sans"],
        "border_radii": [4, 3, 8, 10],
        "icon_styles": ["outline", "filled", "multicolor"],
    }
    result_messy = checker.check(messy)
    assert not result_messy.passed or result_messy.score < 100, "测试2失败：混乱设计应发现问题"
    print(f"✅ 测试2 混乱设计: passed={result_messy.passed}, score={result_messy.score}, "
          f"issues={result_messy.total_checks}")

    # 测试3: 评分计算
    assert 0 <= result_messy.score <= 100, "测试3失败：评分应在 0-100 之间"
    print(f"✅ 测试3 评分范围: score={result_messy.score} (在 0-100 范围内)")

    # 测试4: 空设计
    empty = {}
    result_empty = checker.check(empty)
    assert result_empty.score == 100, "测试4失败：空设计应得 100 分"
    print(f"✅ 测试4 空设计: score={result_empty.score}")

    print(f"\n🎉 所有烟雾测试通过!\n")
