"""AI 名片写作助手 — 调用 DeepSeek API 生成名片文案"""

from app.config import settings


class WritingAssistant:
    """名片文案生成助手

    用途：
    - bio: 个人简介
    - company: 公司介绍
    - recommendation: 推荐语
    - slogan: 名片标语
    """

    # ── 系统提示词模板 ──────────────────────────────────────────────────

    SYSTEM_PROMPTS = {
        "bio": "你是一个专业的个人简介写作助手。根据用户提供的姓名、职位、公司和行业信息，"
        "生成一段简洁有力、突出个人专业亮点的中文简介（80字以内）。",
        "company": "你是一个专业的公司介绍写作助手。根据公司名称、行业和业务描述，"
        "生成一段精炼、专业的中文公司介绍（100字以内），突出公司核心优势。",
        "recommendation": "你是一个专业的推荐语写作助手。根据推荐人信息、关系背景和亮点，"
        "生成一段真诚、有说服力的中文推荐语（60字以内），用于名片展示。",
        "slogan": "你是一个专业的品牌标语写作助手。根据个人信息和职业背景，"
        "生成一句简短有力、易于记住的中文个人品牌标语（15字以内）。",
    }

    @staticmethod
    def _build_user_prompt(purpose: str, **kwargs) -> str:
        """根据用途构建用户提示词"""
        if purpose == "bio":
            name = kwargs.get("name", "")
            position = kwargs.get("position", "")
            company = kwargs.get("company", "")
            industry = kwargs.get("industry", "")
            skills = kwargs.get("skills", "")
            parts = []
            if name:
                parts.append(f"姓名：{name}")
            if position:
                parts.append(f"职位：{position}")
            if company:
                parts.append(f"公司：{company}")
            if industry:
                parts.append(f"行业：{industry}")
            if skills:
                parts.append(f"技能/专长：{skills}")
            return "请为以下个人信息生成一段中文个人简介（80字以内）：\n\n" + "\n".join(parts)

        elif purpose == "company":
            company_name = kwargs.get("company_name", "")
            industry = kwargs.get("industry", "")
            description = kwargs.get("description", "")
            highlights = kwargs.get("highlights", "")
            parts = []
            if company_name:
                parts.append(f"公司名称：{company_name}")
            if industry:
                parts.append(f"行业领域：{industry}")
            if description:
                parts.append(f"业务描述：{description}")
            if highlights:
                parts.append(f"核心优势：{highlights}")
            return "请为以下企业信息生成一段中文公司介绍（100字以内）：\n\n" + "\n".join(parts)

        elif purpose == "recommendation":
            name = kwargs.get("name", "")
            relationship = kwargs.get("relationship", "")
            highlights = kwargs.get("highlights", "")
            parts = []
            if name:
                parts.append(f"被推荐人：{name}")
            if relationship:
                parts.append(f"关系背景：{relationship}")
            if highlights:
                parts.append(f"推荐亮点：{highlights}")
            return "请根据以下信息生成一段中文推荐语（60字以内）：\n\n" + "\n".join(parts)

        elif purpose == "slogan":
            name = kwargs.get("name", "")
            position = kwargs.get("position", "")
            company = kwargs.get("company", "")
            core_value = kwargs.get("core_value", "")
            parts = []
            if name:
                parts.append(f"姓名：{name}")
            if position:
                parts.append(f"职位：{position}")
            if company:
                parts.append(f"公司：{company}")
            if core_value:
                parts.append(f"核心价值：{core_value}")
            return "请根据以下信息生成一句中文个人品牌标语（15字以内）：\n\n" + "\n".join(parts)

        return "请生成一段简单的自我介绍。"

    @staticmethod
    async def generate(
        purpose: str,
        api_key: str | None = None,
        **kwargs,
    ) -> str:
        """调用 DeepSeek API 生成文案

        Args:
            purpose: 文案用途 (bio|company|recommendation|slogan)
            api_key: DeepSeek API Key（默认使用配置中的 key）
            **kwargs: 根据用途传递对应参数

        Returns:
            生成的文案文本
        """
        api_key = api_key or settings.DEEPSEEK_API_KEY
        if not api_key:
            return "【文案生成需要配置 DEEPSEEK_API_KEY】"

        system_prompt = WritingAssistant.SYSTEM_PROMPTS.get(
            purpose,
            "你是一个专业文案写作助手。",
        )
        user_prompt = WritingAssistant._build_user_prompt(purpose, **kwargs)

        import httpx

        from app.middleware.metrics import track_ai_inference

        async with httpx.AsyncClient(timeout=30) as client:
            with track_ai_inference(model_name="deepseek-chat"):
                try:
                    resp = await client.post(
                        settings.DEEPSEEK_API_URL,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": "deepseek-chat",
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                            "max_tokens": 300,
                            "temperature": 0.7,
                        },
                    )
                    result = resp.json()
                    return result["choices"][0]["message"]["content"].strip()
                except Exception as e:
                    return f"【文案生成失败: {str(e)}】"

    @staticmethod
    async def generate_all(
        fields: dict,
        api_key: str | None = None,
    ) -> dict:
        """一次性生成全部文案

        Args:
            fields: 名片字段字典，支持：
                - name, position, company, industry, skills
                - company_name, description, highlights
                - relationship, core_value
            api_key: DeepSeek API Key

        Returns:
            {"bio": str, "company": str, "recommendation": str, "slogan": str}
        """

        tasks = {
            "bio": WritingAssistant.generate(
                "bio",
                api_key=api_key,
                name=fields.get("name", ""),
                position=fields.get("position", ""),
                company=fields.get("company", ""),
                industry=fields.get("industry", ""),
                skills=fields.get("skills", ""),
            ),
            "company": WritingAssistant.generate(
                "company",
                api_key=api_key,
                company_name=fields.get("company_name") or fields.get("company", ""),
                industry=fields.get("industry", ""),
                description=fields.get("description", ""),
                highlights=fields.get("highlights", ""),
            ),
            "recommendation": WritingAssistant.generate(
                "recommendation",
                api_key=api_key,
                name=fields.get("name", ""),
                relationship=fields.get("relationship", ""),
                highlights=fields.get("highlights", ""),
            ),
            "slogan": WritingAssistant.generate(
                "slogan",
                api_key=api_key,
                name=fields.get("name", ""),
                position=fields.get("position", ""),
                company=fields.get("company", ""),
                core_value=fields.get("core_value", ""),
            ),
        }

        results = {}
        for key, task in tasks.items():
            results[key] = await task

        return results
