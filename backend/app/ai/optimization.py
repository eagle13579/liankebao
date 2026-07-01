"""AI 名片优化分析 — 完整度/关键词覆盖/专业度评分"""


class OptimizationAnalyzer:
    """名片优化分析器

    分析维度：
    - 完整度评分：名片信息填写完整程度
    - 关键词覆盖：行业关键词覆盖情况
    - 专业度评分：文案质量和专业程度
    """

    # ── 基础字段权重 ────────────────────────────────────────────────────

    FIELD_WEIGHTS = {
        "name": 20,
        "position": 15,
        "company": 15,
        "phone": 12,
        "email": 10,
        "wechat": 10,
        "address": 5,
        "website": 5,
        "cover_image": 8,
    }

    MINIMAL_FIELDS = {"name", "position", "company"}
    CONTACT_FIELDS = {"phone", "email", "wechat"}

    @staticmethod
    def analyze_completeness(fields: dict) -> dict:
        """分析名片完整度

        Args:
            fields: 名片字段字典

        Returns:
            {
                "score": float,        # 完整度评分 [0, 100]
                "total_weight": int,   # 总权重
                "filled_weight": int,  # 已填写权重
                "filled_fields": int,  # 已填字段数
                "total_fields": int,   # 总字段数
                "missing_fields": list, # 缺失的重要字段
                "level": str,          # 完整度等级 (优秀|良好|一般|待完善)
            }
        """
        total_weight = sum(OptimizationAnalyzer.FIELD_WEIGHTS.values())
        filled_weight = 0
        filled_count = 0
        missing = []

        for field, weight in OptimizationAnalyzer.FIELD_WEIGHTS.items():
            value = fields.get(field)
            if value and str(value).strip():
                filled_weight += weight
                filled_count += 1
            else:
                missing.append(field)

        # 给额外字段加分（如 intro, skills 等）
        extra_fields = {"intro", "skills", "industry", "description"}
        for field in extra_fields:
            value = fields.get(field)
            if value and str(value).strip():
                filled_weight += 5
                filled_count += 1

        score = min(100, round((filled_weight / total_weight) * 100, 1))

        if score >= 85:
            level = "优秀"
        elif score >= 65:
            level = "良好"
        elif score >= 45:
            level = "一般"
        else:
            level = "待完善"

        return {
            "score": score,
            "total_weight": total_weight,
            "filled_weight": filled_weight,
            "filled_fields": filled_count,
            "total_fields": len(OptimizationAnalyzer.FIELD_WEIGHTS),
            "missing_fields": missing,
            "level": level,
        }

    @staticmethod
    def _get_industry_keywords(industry: str) -> list[str]:
        """根据行业返回推荐关键词列表"""
        keywords_map = {
            "互联网": ["产品经理", "全栈开发", "数据分析", "用户体验", "敏捷开发"],
            "金融": ["投资", "风险管理", "理财规划", "资产配置", "金融科技"],
            "教育": ["课程设计", "教学管理", "在线教育", "培训", "学术研究"],
            "医疗": ["临床", "健康管理", "医学研究", "医疗服务", "制药"],
            "制造业": ["供应链", "生产管理", "质量控制", "精益生产", "智能制造"],
            "房地产": ["地产开发", "市场营销", "项目管理", "商业地产", "物业管理"],
            "咨询": ["战略规划", "管理咨询", "数据分析", "组织变革", "市场研究"],
            "法律": ["法律顾问", "合规", "知识产权", "合同管理", "诉讼"],
            "人力资源": ["招聘", "人才发展", "绩效管理", "薪酬福利", "组织发展"],
            "市场营销": ["品牌营销", "数字营销", "内容运营", "社交媒体", "广告投放"],
            "销售": ["客户关系", "商务拓展", "大客户", "渠道管理", "销售策略"],
            "设计": ["UI/UX", "视觉设计", "品牌设计", "交互设计", "平面设计"],
        }
        for key, keywords in keywords_map.items():
            if key in industry:
                return keywords
        return ["专业服务", "行业经验", "客户关系", "项目管理", "团队协作"]

    @staticmethod
    def analyze_keyword_coverage(fields: dict, industry: str = "") -> dict:
        """分析关键词覆盖

        Args:
            fields: 名片字段字典
            industry: 行业名称

        Returns:
            {
                "score": float,          # 关键词覆盖评分 [0, 100]
                "matched_keywords": list, # 已覆盖的关键词
                "suggested_keywords": list, # 建议补充的关键词
                "total_keywords": int,    # 行业推荐关键词总数
                "coverage_rate": float,   # 覆盖率
            }
        """
        if not industry:
            # 尝试从字段中推断行业
            company = fields.get("company", "")
            intro = fields.get("intro", "")
            description = fields.get("description", "")
            industry = company  # 用公司名做简单匹配

        recommended = OptimizationAnalyzer._get_industry_keywords(industry)

        # 收集所有已填字段文本
        all_text = ""
        for v in fields.values():
            if v and isinstance(v, str):
                all_text += v.lower() + " "

        matched = []
        for kw in recommended:
            if kw.lower() in all_text:
                matched.append(kw)

        total = len(recommended)
        matched_count = len(matched)
        coverage_rate = round(matched_count / total, 2) if total > 0 else 0
        score = min(100, round(coverage_rate * 100))

        suggested = [kw for kw in recommended if kw not in matched]

        return {
            "score": score,
            "matched_keywords": matched,
            "suggested_keywords": suggested[:5],  # 最多推荐5个
            "total_keywords": total,
            "coverage_rate": coverage_rate,
        }

    @staticmethod
    def analyze_professionalism(fields: dict) -> dict:
        """分析名片专业度

        Args:
            fields: 名片字段字典

        Returns:
            {
                "score": float,           # 专业度评分 [0, 100]
                "issues": list[dict],     # 发现的问题 [{field, issue, severity}]
                "suggestions": list[str], # 改进建议
            }
        """
        issues = []
        suggestions = []

        # 检查必填字段
        for field in OptimizationAnalyzer.MINIMAL_FIELDS:
            value = fields.get(field, "")
            if not value or not str(value).strip():
                issues.append(
                    {
                        "field": field,
                        "issue": f"缺少{field}",
                        "severity": "high",
                    }
                )

        # 检查名称格式
        name = fields.get("name", "")
        if name and len(name) < 2:
            issues.append(
                {
                    "field": "name",
                    "issue": "姓名过短，建议填写全名",
                    "severity": "low",
                }
            )

        # 检查联系方式
        contact_filled = sum(
            1 for f in OptimizationAnalyzer.CONTACT_FIELDS if fields.get(f) and str(fields.get(f, "")).strip()
        )
        if contact_filled == 0:
            issues.append(
                {
                    "field": "contact",
                    "issue": "未填写任何联系方式，严重影响可信度",
                    "severity": "high",
                }
            )
        elif contact_filled == 1:
            suggestions.append("建议至少补充一种备选联系方式（邮箱或微信），方便客户多渠道联系您")

        # 检查电话号码格式
        phone = fields.get("phone", "")
        if phone:
            import re

            if not re.match(r"^1[3-9]\d{9}$", phone):
                issues.append(
                    {
                        "field": "phone",
                        "issue": "手机号格式不规范，建议填写11位中国大陆手机号",
                        "severity": "medium",
                    }
                )

        # 检查邮箱格式
        email = fields.get("email", "")
        if email and "@" not in email:
            issues.append(
                {
                    "field": "email",
                    "issue": "邮箱格式似乎不正确，缺少 @ 符号",
                    "severity": "medium",
                }
            )

        # 检查职位和公司的完整性
        position = fields.get("position", "")
        company = fields.get("company", "")
        if position and company:
            suggestions.append("您的职位和公司信息完整，建议在个人简介中进一步说明专业方向")

        # 检查是否有简介/介绍
        intro = fields.get("intro", "")
        description = fields.get("description", "")
        if not intro and not description:
            suggestions.append("增加一段个人简介或服务介绍，能让对方更快了解您的专业价值")

        # 计算评分
        score = 80  # 基础分
        for issue in issues:
            if issue["severity"] == "high":
                score -= 15
            elif issue["severity"] == "medium":
                score -= 8
            else:
                score -= 3
        score = max(0, min(100, score))

        # 额外加分项
        if fields.get("website"):
            score += 3
        if fields.get("cover_image"):
            score += 4
        if fields.get("intro"):
            score += 5
        if fields.get("skills"):
            score += 3

        score = min(100, score)

        return {
            "score": score,
            "issues": issues,
            "suggestions": suggestions,
        }

    @staticmethod
    async def get_optimization_suggestions(
        brochure_id: int,
        fields: dict,
        industry: str = "",
        api_key: str | None = None,
    ) -> dict:
        """获取综合优化建议

        Args:
            brochure_id: 画册 ID
            fields: 名片字段字典
            industry: 行业名称
            api_key: DeepSeek API Key

        Returns:
            {
                "brochure_id": int,
                "completeness": dict,
                "keyword_coverage": dict,
                "professionalism": dict,
                "overall_score": float,
                "top_priorities": list[str],
            }
        """
        completeness = OptimizationAnalyzer.analyze_completeness(fields)
        keyword = OptimizationAnalyzer.analyze_keyword_coverage(fields, industry)
        professionalism = OptimizationAnalyzer.analyze_professionalism(fields)

        overall = round(
            completeness["score"] * 0.35 + keyword["score"] * 0.30 + professionalism["score"] * 0.35,
            1,
        )

        # 生成优先级建议
        top_priorities = []

        if completeness["level"] in ("待完善", "一般"):
            missing_names = {
                "name": "姓名",
                "position": "职位",
                "company": "公司",
                "phone": "手机号",
                "email": "邮箱",
                "wechat": "微信号",
            }
            missing_labels = [missing_names.get(f, f) for f in completeness["missing_fields"][:3]]
            if missing_labels:
                top_priorities.append(f"补充基本信息：{'、'.join(missing_labels)}")

        if keyword["score"] < 60 and keyword["suggested_keywords"]:
            top_priorities.append(
                f"优化关键词覆盖：建议在简介中融入「{'」「'.join(keyword['suggested_keywords'][:3])}」等术语"
            )

        if professionalism["issues"]:
            severity_map = {"high": "高优先级", "medium": "中等", "low": "低"}
            for issue in professionalism["issues"][:2]:
                sev = severity_map.get(issue["severity"], "")
                top_priorities.append(f"[{sev}] {issue['issue']}")

        if professionalism["suggestions"]:
            top_priorities.extend(professionalism["suggestions"][:2])

        if not top_priorities:
            top_priorities.append("名片信息已较完善，继续保持！")

        return {
            "brochure_id": brochure_id,
            "completeness": completeness,
            "keyword_coverage": keyword,
            "professionalism": professionalism,
            "overall_score": overall,
            "top_priorities": top_priorities,
        }
