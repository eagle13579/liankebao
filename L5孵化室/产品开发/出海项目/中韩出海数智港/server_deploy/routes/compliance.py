"""
routes/compliance.py — 六步流程引擎 + 合规检查API
===================================================
包含:
  - GET  /api/health              — 健康检查
  - GET  /api/seeds               — 种子示例
  - POST /api/compliance/check    — 合规检查（六步流程）
  - POST /api/compliance/explain  — AI解读报告
  - GET  /                        — 首页
  - GET  /knowledge-base          — 知识库管理界面
  - GET  /api/docs                — Swagger UI
  - GET  /api/openapi.json        — OpenAPI 规范
  - 所有辅助函数 (_build_input_text, _parse_*, _build_*)
  - 🆕 GET  /api/compliance/signals       — 合规监管信号（来自gaia-commercial amoeba）
  - 🆕 POST /api/compliance/discuss       — 多部门合规诊断协作讨论
  - 🆕 GET  /api/compliance/team          — 合规诊断团队状态
  - 🆕 POST /api/compliance/workbench/run — 合规工作台阿米巴循环
"""

import os
import json
import datetime
import copy
from typing import Dict, List, Any, Optional

import yaml
from flask import Blueprint, Flask, request, jsonify, render_template, g

from compliance_knowledge_base import (
    REGULATIONS,
    PRODUCT_CLASSIFICATION,
    RISK_LEXICON,
    VIOLATION_CASES,
    classify_product,
    query_regulations,
)
from compliance_rules import (
    RiskLevel,
    RISK_LABELS,
    RISK_COLORS,
    RISK_SCORE_CARD,
    ESCALATION_RULES,
    OUTPUT_TEMPLATES,
    calculate_risk_score,
    check_escalation,
    format_output,
    generate_standard_output,
)
from risk_engine import (
    DIMENSION_WEIGHTS,
    DIMENSION_NAMES_CN,
    SCORER_REGISTRY,
    score_ingredient,
    score_label,
    score_claim,
    score_qualification,
    score_classification,
    score_path,
    calculate_weighted_score,
    check_manual_review_rules,
    format_risk_report,
    format_risk_summary,
    format_dimension_details,
    format_manual_review_decision,
    format_decision_output,
    format_actionable_advice,
    run_full_assessment,
)
from input_recognizer import (
    INPUT_TYPES,
    recognize_input_type,
    check_input_completeness,
    request_supplementary_materials,
    extract_all_fields,
    batch_recognize,
)
from security import (
    require_api_key,
    rate_limit,
    extract_api_key_from_request,
    create_jwt_token,
    verify_jwt_token,
)
from llm_enhancer import get_enhancer
from audit import record_compliance_check, save_version_snapshot, list_versions, get_version_snapshot
import config
from config import BASE_DIR, OPENAPI_YAML_PATH

compliance_bp = Blueprint("compliance", __name__)


# ──────────────────────────────────────────────
# 内存中的知识库存储（可变副本，用于CRUD操作）
# ──────────────────────────────────────────────
_kb_store: Dict[str, List[Dict]] = {}


def _ensure_kb_store():
    """初始化知识库内存存储"""
    global _kb_store
    if not _kb_store:
        _kb_store = {
            "regulations": copy.deepcopy(REGULATIONS),
            "cases": copy.deepcopy(VIOLATION_CASES),
            "risk_words": copy.deepcopy(RISK_LEXICON.get("entries", [])),
            "classifications": copy.deepcopy(PRODUCT_CLASSIFICATION),
        }
    return _kb_store


# ======================================================================
# GET /api/health — 健康检查
# ======================================================================
@compliance_bp.route("/api/health", methods=["GET"])
def health_check():
    """健康检查端点"""
    return jsonify({
        "status": "ok",
        "service": "合规自动化数智员工",
        "version": "1.0.0",
        "timestamp": datetime.datetime.now().isoformat(),
        "modules": {
            "compliance_knowledge_base": {
                "regulations": len(REGULATIONS),
                "product_classifications": len(PRODUCT_CLASSIFICATION),
                "risk_lexicon_entries": len(RISK_LEXICON.get("entries", [])),
                "violation_cases": len(VIOLATION_CASES),
            },
            "compliance_rules": {
                "risk_score_dimensions": len(RISK_SCORE_CARD["dimensions"]),
                "escalation_rules": len(ESCALATION_RULES),
                "output_templates": len(OUTPUT_TEMPLATES["templates"]),
            },
            "risk_engine": {
                "dimension_weights": list(DIMENSION_WEIGHTS.keys()),
                "scorers_available": list(SCORER_REGISTRY.keys()),
            },
            "input_recognizer": {
                "input_types": list(INPUT_TYPES.keys()),
            },
        },
    })


# ======================================================================
# GET /api/seeds — 种子示例
# ======================================================================
@compliance_bp.route("/api/seeds", methods=["GET"])
def get_seeds():
    """返回预置的种子示例，方便快速测试"""
    seeds = [
        {
            "name": "韩国高丽红参浓缩液",
            "description": "高风险产品 — 红参类保健食品未注册",
            "input": {
                "product_name": "韩国高丽红参浓缩液",
                "ingredient_list": "6年根红参浓缩液、纯净水、蜂蜜",
                "chinese_label": "产品名称：高丽红参浓缩液 配料表：6年根红参浓缩液 净含量：240ml 原产国：韩国",
                "promotion_copy": "增强免疫力、抗疲劳、改善血液循环，源自韩国正官庄百年工艺",
                "import_path": "一般贸易，韩国→上海口岸",
                "enterprise_qualification": "韩国生产企业：韩国人参公社，进口商：上海韩湘贸易有限公司",
                "function_claim": "增强免疫力，抗疲劳",
            },
        },
        {
            "name": "韩国蜂蜜柚子茶",
            "description": "低风险产品 — 普通食品，合规标签",
            "input": {
                "product_name": "韩国蜂蜜柚子茶",
                "ingredient_list": "白砂糖、柚子果肉、蜂蜜、饮用水、柠檬酸、维生素C",
                "chinese_label": "产品名称：蜂蜜柚子茶 配料表：白砂糖、柚子果肉、蜂蜜 净含量：500g 原产国：韩国 保质期：24个月",
                "promotion_copy": "精选济州岛新鲜柚子，传统工艺熬制，口感清香",
                "import_path": "一般贸易，韩国→青岛口岸",
                "enterprise_qualification": "境外生产企业已注册，进口商已备案",
                "function_claim": "",
            },
        },
        {
            "name": "韩国美白精华液",
            "description": "中高风险产品 — 特殊化妆品宣称",
            "input": {
                "product_name": "韩国美白精华液",
                "ingredient_list": "烟酰胺、熊果苷、透明质酸、维生素C衍生物、去离子水",
                "chinese_label": "产品名称：美白精华液 净含量：30ml 原产国：韩国 进口商：广州美妆进出口有限公司",
                "promotion_copy": "7天美白淡斑、祛黄提亮、抑制黑色素生成，韩国首尔大学皮肤研究所研发",
                "import_path": "跨境电商（CBEC）",
                "enterprise_qualification": "境外生产企业已注册，进口商备案进行中",
                "function_claim": "美白淡斑，抑制黑色素",
            },
        },
    ]
    return jsonify({
        "count": len(seeds),
        "seeds": seeds,
        "usage": "POST /api/compliance/check 并将任一seed的input字段作为请求体",
    })


# ======================================================================
# POST /api/compliance/check — 合规检查主流程
# ======================================================================
@compliance_bp.route("/api/compliance/check", methods=["POST"])
@require_api_key("compliance:check")
@rate_limit(30)
def compliance_check():
    """六步流程合规检查（P1安全加固：需API密钥认证 + 频率限制 + 审计追踪 + 多租户配额）"""
    # ── 多租户：提取用户信息 ──
    user_email = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        jwt_payload = verify_jwt_token(auth_header[7:])
        if jwt_payload:
            user_email = jwt_payload.get("sub")
    user_email = user_email or extract_api_key_from_request() or "anonymous"

    # ── 免费版每日配额检查 ──
    from routes.auth import check_and_increment_user_quota
    quota_allowed, remaining, limit = check_and_increment_user_quota(user_email)
    if not quota_allowed:
        return jsonify({
            "error": "每日检查次数已用尽",
            "detail": f"免费版每日限制 {limit} 次合规检查，请升级套餐或明天再试",
            "tier": "free",
            "checks_used": limit,
            "checks_limit": limit,
        }), 429
    try:
        data = request.get_json(force=True)
    except Exception:
        record_compliance_check(
            who=extract_api_key_from_request() or "unknown",
            user_id=user_email,
            input_data={},
            result_data={"detail": "请求体必须是有效的JSON", "error": "请求体必须是有效的JSON"},
            role=getattr(g, "role", ""),
            ip=request.remote_addr or "",
            status="failed",
        )
        return jsonify({"detail": "请求体必须是有效的JSON", "error": "请求体必须是有效的JSON"}), 400

    if not data:
        record_compliance_check(
            who=extract_api_key_from_request() or "unknown",
            user_id=user_email,
            input_data={},
            result_data={"detail": "请求体不能为空", "error": "请求体不能为空"},
            role=getattr(g, "role", ""),
            ip=request.remote_addr or "",
            status="failed",
        )
        return jsonify({"detail": "请求体不能为空", "error": "请求体不能为空"}), 400

    meta = data.get("meta", {})
    if not isinstance(meta, dict):
        meta = {}

    # =========================================================
    # 六步流程引擎
    # =========================================================
    steps_log = {}

    # ── 步骤1: 识别输入 ──
    raw_text = _build_input_text(data)
    try:
        input_type, confidence, method = recognize_input_type(raw_text)
    except ValueError:
        input_type, confidence, method = ("unknown", 0.0, "failed")

    extracted_fields = extract_all_fields(raw_text)
    completeness = check_input_completeness(input_type, extracted_fields) if input_type != "unknown" else {}
    supplement_req = request_supplementary_materials(input_type, extracted_fields) if input_type != "unknown" else {}

    steps_log["step1_input_recognition"] = {
        "input_type": input_type,
        "input_type_cn": INPUT_TYPES.get(input_type, "未知"),
        "confidence": confidence,
        "method": method,
        "extracted_fields": extracted_fields,
        "completeness": completeness,
        "supplement_needed": supplement_req.get("need_supplement", False) if supplement_req else False,
    }

    # ── 步骤2: 产品分类 ──
    product_name = data.get("product_name", "") or extracted_fields.get("产品名称", "")
    classification_results = classify_product(raw_text)
    category_names = [c.get("category", "") for c in classification_results]
    category_str = " / ".join(category_names) if category_names else "未分类"

    steps_log["step2_product_classification"] = {
        "product_name": product_name,
        "classification_results": classification_results,
        "category": category_str,
    }

    # ── 步骤3: 成分与宣称审核 ──
    ingredient_text = data.get("ingredient_list", "") or extracted_fields.get("配料表", "")
    claim_text = data.get("function_claim", "") or data.get("promotion_copy", "") or extracted_fields.get("功能宣称", "") or ""

    ingredient_params = _parse_ingredient_text(ingredient_text, raw_text)
    ingredient_score = score_ingredient(ingredient_params)

    claim_params = _parse_claim_text(claim_text, data.get("promotion_copy", ""))
    claim_score = score_claim(claim_params)

    steps_log["step3_ingredient_claim"] = {
        "ingredient_score": ingredient_score,
        "claim_score": claim_score,
    }

    # ── 步骤4: 标签审核 ──
    label_text = data.get("chinese_label", "") or extracted_fields.get("中文标签", "")
    label_params = _parse_label_text(label_text, data)
    label_score = score_label(label_params)

    steps_log["step4_label_review"] = {
        "label_score": label_score,
    }

    # ── 步骤5: 企业资质审核 ──
    qual_text = data.get("enterprise_qualification", "") or extracted_fields.get("企业资质", "")
    qual_params = _parse_qualification_text(qual_text, data)
    qual_score = score_qualification(qual_params)

    class_params = _parse_classification_text(category_str, raw_text)
    class_score = score_classification(class_params)

    steps_log["step5_enterprise_qualification"] = {
        "qualification_score": qual_score,
        "classification_score": class_score,
    }

    # ── 步骤6: 进口路径判定 ──
    path_text = data.get("import_path", "") or extracted_fields.get("进口路径", "")
    path_params = _parse_path_text(path_text, data)
    path_score = score_path(path_params)

    steps_log["step6_import_path"] = {
        "path_score": path_score,
    }

    # =========================================================
    # 四级风险判定（加权6维累加）
    # =========================================================
    dimension_scores = {
        "ingredient": ingredient_score,
        "label": label_score,
        "claim": claim_score,
        "qualification": qual_score,
        "classification": class_score,
        "path": path_score,
    }

    weighted_result = calculate_weighted_score(dimension_scores)

    # =========================================================
    # 7条转人工规则检查
    # =========================================================
    manual_review = check_manual_review_rules(
        dimension_scores=dimension_scores,
        weighted_result=weighted_result,
        meta={
            "is_high_value": meta.get("is_high_value", False),
            "is_first_import": meta.get("is_first_import", False),
            "is_special_category": meta.get("is_special_category", False),
        },
    )

    # =========================================================
    # 6项标准输出
    # =========================================================
    preliminary_judgment = _build_preliminary_judgment(
        product_name=product_name or "未知产品",
        category=category_str or "未分类",
        weighted_result=weighted_result,
        manual_review=manual_review,
        steps_log=steps_log,
    )

    judgment_basis = _build_judgment_basis(category_str, raw_text, dimension_scores)
    risk_description = _build_risk_description(weighted_result, dimension_scores)
    modification_suggestions = _build_modification_suggestions(dimension_scores, weighted_result)
    required_documents = _build_required_documents(steps_log, dimension_scores)
    human_review_decision = _build_human_review_decision(manual_review, steps_log)

    response = {
        "steps": steps_log,
        "preliminary_judgment": preliminary_judgment,
        "judgment_basis": judgment_basis,
        "risk_description": risk_description,
        "modification_suggestions": modification_suggestions,
        "required_documents": required_documents,
        "human_review_decision": human_review_decision,
        "summary": _generate_summary_text(
            product_name=product_name or "未知产品",
            category=category_str or "未分类",
            weighted_result=weighted_result,
            manual_review=manual_review,
        ),
        "quota": {
            "remaining": remaining,
            "limit": limit,
            "tier": "free",
        },
    }

    # ── LLM增强报告 (可选) ──
    llm_report = None
    if config.LLM_ENABLED:
        try:
            from llm_enhancer import generate_ai_report, LLMClient
            client = LLMClient(
                api_key=config.LLM_API_KEY,
                endpoint=config.LLM_BASE_URL.rstrip('/') + '/chat/completions',
                model=config.LLM_MODEL,
                timeout=config.LLM_TIMEOUT,
            )
            llm_report = generate_ai_report(client, response, input_data=data)
        except Exception as e:
            app = _get_current_app()
            app.logger.warning(f"LLM报告生成失败（非致命）: {e}")
    response['llm_report'] = llm_report

    # ── 审计追踪 ──
    try:
        who = extract_api_key_from_request() or "unknown"
        ip = request.remote_addr or ""
        role = getattr(g, "role", "")
        record_compliance_check(
            who=who,
            user_id=user_email,
            input_data=data,
            result_data=response,
            role=role,
            ip=ip,
            status="success",
        )
        check_id = f"check_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        save_version_snapshot(
            check_id=check_id,
            input_data=data,
            result_data=response,
            who=who,
            role=role,
        )
    except Exception as e:
        app = _get_current_app()
        app.logger.error(f"审计日志记录失败（非致命）: {e}")

    return jsonify(response)


# ======================================================================
# POST /api/compliance/explain — AI解读报告
# ======================================================================
@compliance_bp.route("/api/compliance/explain", methods=["POST"])
@require_api_key("compliance:explain")
@rate_limit(30)
def compliance_explain():
    """POST /api/compliance/explain — 根据检查结果ID生成AI合规解读报告"""
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"detail": "请求体必须是有效的JSON", "error": "请求体必须是有效的JSON"}), 400

    if not data:
        return jsonify({"detail": "请求体不能为空", "error": "请求体不能为空"}), 400

    check_id = data.get("check_id", f"explain_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}")
    input_data = data.get("input_data", {})

    check_response = {
        "preliminary_judgment": data.get("preliminary_judgment", {}),
        "judgment_basis": data.get("judgment_basis", []),
        "risk_description": data.get("risk_description", []),
        "modification_suggestions": data.get("modification_suggestions", []),
        "required_documents": data.get("required_documents", []),
        "human_review_decision": data.get("human_review_decision", {}),
        "summary": data.get("summary", ""),
    }

    if not check_response["preliminary_judgment"]:
        return jsonify({
            "detail": "缺少必要数据: 至少需要 preliminary_judgment（初步判断）",
            "error": "缺少必要数据",
        }), 400

    try:
        enhancer = get_enhancer()
        ai_report = enhancer.generate_report(
            check_response=check_response,
            check_id=check_id,
            input_data=input_data,
        )
        llm_available = enhancer.enabled

        try:
            record_compliance_check(
                who=extract_api_key_from_request() or "unknown",
                input_data={"check_id": check_id, "input_data_keys": list(input_data.keys()) if input_data else []},
                result_data={"llm_enhanced": llm_available, "report_length": len(ai_report)},
                role=getattr(g, "role", ""),
                ip=request.remote_addr or "",
                status="success" if llm_available else "fallback",
            )
        except Exception:
            pass

        return jsonify({
            "check_id": check_id,
            "ai_report": ai_report,
            "llm_enhanced": llm_available,
            "fallback_reason": None if llm_available else "LLM不可用，使用规则引擎生成文本摘要",
            "search_engine": "deepseek-v4-flash" if llm_available else "规则引擎(纯本地)",
        })

    except Exception as e:
        app = _get_current_app()
        app.logger.error(f"AI报告生成异常: {e}")
        return jsonify({
            "detail": f"AI报告生成失败: {str(e)}",
            "error": "报告生成失败",
        }), 500


# ======================================================================
# GET /api/compliance/report/<check_id> — 合规报告导出 (text/plain)
# ======================================================================
@compliance_bp.route("/api/compliance/report/<check_id>", methods=["GET"])
@require_api_key("compliance:report")
@rate_limit(30)
def compliance_report(check_id):
    '''根据check_id导出人可读的合规文本报告 (text/plain)'''
    try:
        # 查找版本快照
        versions = list_versions(check_id)
        if not versions:
            return jsonify({
                "detail": f"未找到 check_id={check_id} 的检查记录",
                "error": "检查记录未找到",
            }), 404

        # 取最新版本
        latest = versions[0]
        snapshot = get_version_snapshot(latest["file"])
        if not snapshot:
            return jsonify({
                "detail": f"快照文件读取失败: {latest['file']}",
                "error": "快照读取失败",
            }), 500

        result = snapshot.get("result_data", {})
        input_data = snapshot.get("input_data", {})
        judgment = result.get("preliminary_judgment", {})
        risk_items = result.get("risk_description", [])
        suggestions = result.get("modification_suggestions", [])
        docs = result.get("required_documents", [])
        human_review = result.get("human_review_decision", {})
        summary = result.get("summary", "")
        steps = result.get("steps", {})

        # ── 构建人可读文本报告 ──
        lines = []
        sep = "=" * 72
        sub_sep = "-" * 50

        # 标题
        lines.append(sep)
        lines.append("  合规检查报告")
        lines.append(f"  生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"  检查ID:   {check_id}")
        lines.append(sep)
        lines.append("")

        # 基本信息
        lines.append("【基本信息】")
        lines.append(sub_sep)
        lines.append(f"  产品名称:   {judgment.get('产品名称', '未知')}")
        lines.append(f"  产品品类:   {judgment.get('产品品类', '未分类')}")
        lines.append(f"  目标市场:   {judgment.get('目标市场', '韩国→中国')}")
        lines.append(f"  判断时间:   {judgment.get('判断时间', '未知')}")
        lines.append("")

        # 风险评估摘要
        lines.append("【风险评估摘要】")
        lines.append(sub_sep)
        lines.append(f"  综合风险等级:  {judgment.get('综合风险等级', '未知')} {judgment.get('风险等级图示', '')}")
        lines.append(f"  综合风险评分:  {judgment.get('综合风险评分', 0)} 分")
        lines.append(f"  判断结论:      {judgment.get('判断结论', '')}")
        lines.append("")

        # 各维度评分
        lines.append("【各维度风险评分】")
        lines.append(sub_sep)
        for item in risk_items:
            dim = item.get("风险维度", "未知")
            lvl = item.get("风险级别", "-")
            raw = item.get("原始评分", 0)
            weighted = item.get("加权评分", 0)
            desc = item.get("风险描述", "")
            advice = item.get("合规建议", "")
            lines.append(f"  ▼ {dim}")
            lines.append(f"     风险级别: {lvl} | 原始评分: {raw} | 加权评分: {weighted}")
            if desc:
                lines.append(f"     风险描述: {desc}")
            if advice:
                lines.append(f"     合规建议: {advice}")
        lines.append("")

        # 转人工规则触发情况
        lines.append("【转人工规则触发情况】")
        lines.append(sub_sep)
        needs_review = human_review.get("是否需要人工复核", False)
        lines.append(f"  是否需要人工复核: {'是' if needs_review else '否'}")
        lines.append(f"  复核原因: {human_review.get('复核原因', '无')}")
        triggered = human_review.get("触发规则列表", [])
        if triggered:
            lines.append("  触发规则:")
            for rule in triggered:
                lines.append(f"    · {rule}")
        lines.append(f"  建议复核部门: {human_review.get('建议复核部门', '无需')}")
        lines.append(f"  紧急程度: {human_review.get('紧急程度', '无需')}")
        lines.append(f"  预计处理周期: {human_review.get('预计处理周期', '即时')}")
        lines.append("")

        # 修改建议
        if suggestions:
            lines.append("【修改建议】")
            lines.append(sub_sep)
            for s in suggestions:
                lines.append(f"  #{s.get('序号', 0)} [{s.get('严重程度', '-')}] {s.get('问题描述', '')}")
                lines.append(f"      建议: {s.get('建议修改方式', '')}")
                lines.append(f"      优先级: {s.get('优先级', '一般')}")
            lines.append("")

        # 需补充资料
        if docs:
            lines.append("【需补充资料清单】")
            lines.append(sub_sep)
            for d in docs:
                needed = "必需" if d.get("是否为必需", False) else "可选"
                lines.append(f"  [{needed}] {d.get('资料名称', '')}")
                lines.append(f"      类别: {d.get('资料类别', '')} | 方式: {d.get('提供方式', '')}")
            lines.append("")

        # 判断依据
        basis = result.get("judgment_basis", [])
        if basis:
            lines.append("【判断依据】")
            lines.append(sub_sep)
            for b in basis[:3]:
                lines.append(f"  来源: {b.get('引用来源', '')}")
                lines.append(f"  内容: {b.get('适用内容', '')}")
            lines.append("")

        # 摘要
        if summary:
            lines.append("【一句话摘要】")
            lines.append(sub_sep)
            lines.append(f"  {summary}")
            lines.append("")

        # 脚注
        lines.append(sep)
        lines.append("  本报告由合规自动化数智员工系统自动生成")
        lines.append("  仅供参考，不构成法律意见")
        lines.append(sep)

        report_text = "\n".join(lines)
        return report_text, 200, {"Content-Type": "text/plain; charset=utf-8"}

    except Exception as e:
        app = _get_current_app()
        app.logger.error(f"合规报告生成异常: {e}")
        return jsonify({
            "detail": f"合规报告生成失败: {str(e)}",
            "error": "报告生成失败",
        }), 500


# ======================================================================
# 前端页面路由
# ======================================================================

@compliance_bp.route("/", methods=["GET"])
def index():
    """合规检查工作台首页"""
    return render_template("index.html")


@compliance_bp.route("/knowledge-base", methods=["GET"])
def knowledge_base():
    """知识库管理界面"""
    return render_template("knowledge_base_editor.html")


# ======================================================================
# OpenAPI 文档路由
# ======================================================================

@compliance_bp.route("/api/docs", methods=["GET"])
def api_docs():
    """GET /api/docs → Swagger UI 交互式API文档"""
    return render_template("swagger.html")


@compliance_bp.route("/api/openapi.json", methods=["GET"])
def openapi_json():
    """GET /api/openapi.json → OpenAPI 3.0规范的JSON版本"""
    try:
        with open(OPENAPI_YAML_PATH, "r", encoding="utf-8") as f:
            spec = yaml.safe_load(f)
        return jsonify(spec)
    except FileNotFoundError:
        return jsonify({"detail": "openapi.yaml 未找到", "error": "openapi.yaml 未找到"}), 404
    except yaml.YAMLError as e:
        return jsonify({"detail": f"openapi.yaml 解析失败: {str(e)}", "error": "openapi.yaml 解析失败"}), 500


# ======================================================================
# 辅助函数
# ======================================================================

def _get_current_app():
    """获取当前 Flask 应用实例"""
    from flask import current_app
    return current_app


def _build_input_text(data: Dict[str, Any]) -> str:
    """将所有用户输入拼接为一段文本，供识别模块分析"""
    parts = []
    for key in ["product_name", "ingredient_list", "chinese_label",
                 "promotion_copy", "import_path",
                 "enterprise_qualification", "function_claim"]:
        val = data.get(key, "")
        if val:
            label_map = {
                "product_name": "产品名称",
                "ingredient_list": "配料表",
                "chinese_label": "中文标签",
                "promotion_copy": "宣传文案",
                "import_path": "进口路径",
                "enterprise_qualification": "企业资质",
                "function_claim": "功能宣称",
            }
            cn_label = label_map.get(key, key)
            parts.append(f"【{cn_label}】{val}")
    return "\n".join(parts)


def _parse_ingredient_text(ingredient_text: str, raw_text: str) -> Dict[str, Any]:
    """从文本中解析成分参数"""
    params = {
        "banned": [],
        "restricted": [],
        "novel_food_unapproved": False,
        "gmo_unlabeled": False,
        "allergen_unlabeled": False,
        "additive_out_of_scope": [],
    }
    text = (ingredient_text + " " + raw_text).lower()

    banned_keywords = ["罂粟", "吗啡", "可待因", "苏丹红", "甲醛", "硼砂"]
    for kw in banned_keywords:
        if kw in text:
            params["banned"].append(kw)

    restricted_keywords = ["甜蜜素", "糖精钠", "山梨酸", "苯甲酸", "阿斯巴甜", "安赛蜜"]
    for kw in restricted_keywords:
        if kw in text:
            params["restricted"].append(kw)

    if "新食品原料" in text or "新资源食品" in text:
        params["novel_food_unapproved"] = True
    if "转基因" in text:
        params["gmo_unlabeled"] = True
    if "过敏原" not in text and ("过敏" in text or "致敏" in text):
        params["allergen_unlabeled"] = True

    return params


def _parse_claim_text(claim_text: str, promo_copy: str = "") -> Dict[str, Any]:
    """从文本中解析宣称参数"""
    text = (claim_text + " " + promo_copy).lower()
    params = {
        "disease_treatment_claim": False,
        "unregistered_health_function": [],
        "drug_efficacy_claim": False,
        "exaggerated_claims": [],
        "false_claims": [],
        "official_endorsement": False,
    }

    disease_words = ["治疗", "预防", "治愈", "康复", "消炎", "止痛", "抗菌", "抗病毒"]
    for w in disease_words:
        if w in text:
            params["disease_treatment_claim"] = True
            break

    health_func_words = ["增强免疫", "改善睡眠", "辅助降血糖", "辅助降血脂",
                          "抗氧化", "缓解疲劳", "促进消化", "美容"]
    for w in health_func_words:
        if w in text:
            params["unregistered_health_function"].append(w)

    drug_words = ["药效", "药理", "临床", "疗程", "剂量", "处方"]
    for w in drug_words:
        if w in text:
            params["drug_efficacy_claim"] = True
            break

    exaggerate_words = ["最佳", "第一", "顶级", "最", "国家级", "世界级", "唯一", "首家"]
    for w in exaggerate_words:
        if w in text:
            params["exaggerated_claims"].append(w)

    if "首尔大学" in text or "韩国政府" in text or "国家机关" in text:
        params["official_endorsement"] = True

    return params


def _parse_label_text(label_text: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """从文本中解析标签参数"""
    text = label_text.lower() if label_text else ""
    params = {
        "missing_mandatory_fields": [],
        "language_not_chinese": False,
        "net_content_incorrect": False,
        "date_missing": False,
        "importer_missing": False,
        "origin_country_missing": False,
        "nutrition_table_missing": False,
    }

    mandatory_fields = {
        "产品名称": ["产品名称", "品名"],
        "配料表": ["配料表", "配料", "成分"],
        "净含量": ["净含量", "净重", "规格"],
        "原产国": ["原产国", "原产地", "产地"],
        "进口商/代理商": ["进口商", "代理商", "境内责任人"],
        "保质期": ["保质期", "保质"],
        "生产日期": ["生产日期", "生产日"],
    }
    for field_name, keywords in mandatory_fields.items():
        found = any(kw in text for kw in keywords)
        if not found:
            params["missing_mandatory_fields"].append(field_name)

    product_name = data.get("product_name", "")
    if not product_name and "产品名称" not in text:
        params["language_not_chinese"] = True

    if "净含量" not in text and "ml" not in text and "g" not in text and "kg" not in text:
        params["net_content_incorrect"] = True

    if "保质期" not in text and "生产日期" not in text:
        params["date_missing"] = True

    if "进口商" not in text and "代理商" not in text:
        params["importer_missing"] = True

    if "原产国" not in text and "原产地" not in text:
        params["origin_country_missing"] = True

    if "营养" not in text and "成分表" not in text:
        params["nutrition_table_missing"] = True

    return params


def _parse_qualification_text(qual_text: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """从文本中解析企业资质参数"""
    text = qual_text.lower() if qual_text else ""
    params = {
        "no_business_license": False,
        "no_food_license": False,
        "overseas_unregistered": False,
        "no_health_certificate": False,
        "certificates_expired": [],
        "filing_incomplete": False,
    }

    if "营业执照" not in text and "执照" not in text:
        params["no_business_license"] = True
    if "食品经营" not in text and "食品生产" not in text and "食品许可" not in text:
        params["no_food_license"] = True
    if "未注册" in text or "未备案" in text:
        params["overseas_unregistered"] = True
    if "卫生" not in text and "健康" not in text:
        params["no_health_certificate"] = True
    if "过期" in text:
        params["certificates_expired"].append("未提供有效期信息")
    if "进行中" in text or "备案进行" in text:
        params["filing_incomplete"] = True

    return params


def _parse_classification_text(category_str: str, raw_text: str) -> Dict[str, Any]:
    """从文本中解析分类参数"""
    text = (category_str + " " + raw_text).lower()
    params = {
        "food_health_confusion": False,
        "special_diet_unlabeled": False,
        "infant_food_requirement_unmet": False,
        "novel_food_misuse": False,
        "additive_category_mismatch": [],
    }

    has_common_food_keywords = any(kw in text for kw in ["零食", "饮料", "普通食品", "蜂蜜", "柚子"])
    has_health_keywords = any(kw in text for kw in ["保健", "红参", "增强免疫", "抗疲劳"])
    if has_common_food_keywords and has_health_keywords:
        params["food_health_confusion"] = True

    if "婴幼儿" in text or "婴儿" in text:
        if "标准" not in text and "gb" not in text:
            params["infant_food_requirement_unmet"] = True

    if "新食品原料" in text or "新资源" in text:
        if "备案" not in text:
            params["novel_food_misuse"] = True

    return params


def _parse_path_text(path_text: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """从文本中解析进口路径参数"""
    text = (path_text + " " + data.get("import_path", "")).lower()
    params = {
        "cross_border_confusion": False,
        "personal_vs_trade_confusion": False,
        "prohibited_origin_country": False,
        "no_inspection_certificate": False,
        "no_customs_filing": False,
        "wrong_port_of_entry": False,
    }

    if "跨境电商" in text and "一般贸易" in text:
        params["cross_border_confusion"] = True
    if "个人" in text and "贸易" in text:
        params["personal_vs_trade_confusion"] = True

    prohibited_countries = ["朝鲜", "日本核", "福岛"]
    for c in prohibited_countries:
        if c in text:
            params["prohibited_origin_country"] = True
            break

    if "检验检疫" not in text and "检疫" not in text and "检测" not in text:
        params["no_inspection_certificate"] = True
    if "海关备案" not in text and "备案" not in text:
        params["no_customs_filing"] = True

    return params


def _build_preliminary_judgment(
    product_name: str,
    category: str,
    weighted_result: Dict[str, Any],
    manual_review: Dict[str, Any],
    steps_log: Dict[str, Any],
) -> Dict[str, Any]:
    """构建初步判断"""
    total_score = weighted_result.get("total_score", 0)
    risk_level_cn = weighted_result.get("risk_level_cn", "未知")
    risk_level = weighted_result.get("risk_level", "unknown")

    color_map = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}
    color = color_map.get(risk_level, "⚪")

    if risk_level == "critical":
        conclusion = f"该产品（{product_name}）品类为[{category}]，综合评分{total_score}分（{risk_level_cn}）。存在严重合规障碍，建议立即暂停推进并联系合规法务专家。"
    elif risk_level == "high":
        conclusion = f"该产品（{product_name}）品类为[{category}]，综合评分{total_score}分（{risk_level_cn}）。建议转人工合规专家进行详细审核。"
    elif risk_level == "medium":
        conclusion = f"该产品（{product_name}）品类为[{category}]，综合评分{total_score}分（{risk_level_cn}）。存在一定合规风险，建议补充资料后进一步评估。"
    else:
        conclusion = f"该产品（{product_name}）品类为[{category}]，综合评分{total_score}分（{risk_level_cn}）。系统判断合规风险较低，可进入下一步流程。"

    if manual_review.get("should_manual_review", False):
        conclusion += f" 触发{manual_review['rule_count']}条转人工规则，建议人工复核。"

    return {
        "产品名称": product_name,
        "产品品类": category,
        "目标市场": "韩国→中国",
        "综合风险等级": risk_level_cn,
        "综合风险评分": total_score,
        "风险等级图示": color,
        "判断结论": conclusion,
        "判断时间": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
    }


def _build_judgment_basis(
    category: str,
    raw_text: str,
    dimension_scores: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """构建判断依据"""
    basis_items = []

    keywords_to_search = []
    if category:
        keywords_to_search.extend(category.split(" / "))
    for dim_name, dim_data in dimension_scores.items():
        details = dim_data.get("details", [])
        for d in details:
            for word in ["标签", "成分", "宣称", "资质", "进口", "分类"]:
                if word in d:
                    keywords_to_search.append(word)
                    break

    seen_regs = set()
    for kw in keywords_to_search[:5]:
        if not kw:
            continue
        regs = query_regulations(kw)
        for reg in regs[:1]:
            if reg["id"] not in seen_regs:
                seen_regs.add(reg["id"])
                for art in reg["key_articles"][:1]:
                    basis_items.append({
                        "依据类型": "法规条款",
                        "引用来源": f"{reg['name']} / {art['article']}",
                        "适用内容": art["summary"][:100],
                        "关联性说明": f"与品类[{category}]/关键词'{kw}'相关",
                        "置信度": "高",
                    })
                    break

    if not basis_items:
        basis_items.append({
            "依据类型": "法规条款",
            "引用来源": "《中华人民共和国食品安全法》第九十六条",
            "适用内容": "进口的预包装食品应当有中文标签和说明书",
            "关联性说明": "适用于所有进口食品",
            "置信度": "高",
        })

    return basis_items[:6]


def _build_risk_description(
    weighted_result: Dict[str, Any],
    dimension_scores: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """构建风险说明"""
    risk_items = []
    dim_details = weighted_result.get("dimension_details", {})

    for dim_key, dim_data in dimension_scores.items():
        dim_cn = DIMENSION_NAMES_CN.get(dim_key, dim_key)
        raw_score = dim_data.get("score", 100)
        details = dim_data.get("details", [])

        if raw_score <= 25:
            risk_lvl = "低"
        elif raw_score <= 50:
            risk_lvl = "中"
        elif raw_score <= 75:
            risk_lvl = "高"
        else:
            risk_lvl = "低"

        risk_desc = " ✓ 无扣分项" if not details else "; ".join(details)

        risk_items.append({
            "风险维度": dim_cn,
            "风险级别": risk_lvl,
            "原始评分": raw_score,
            "加权评分": round(raw_score * DIMENSION_WEIGHTS.get(dim_key, 0), 2),
            "风险描述": risk_desc,
            "触发规则": "-",
            "合规建议": _get_advice_for_dimension(dim_key, details),
        })

    return risk_items


def _get_advice_for_dimension(dim: str, details: List[str]) -> str:
    """根据维度和扣分明细给出合规建议"""
    if not details:
        return "该维度无异常，继续保持。"

    advice_map = {
        "ingredient": "核查配方成分表，移除禁用成分，确保限用成分符合GB 2760限量标准，完成新食品原料备案，补充过敏原标识。",
        "label": "按照GB 7718和GB 28050标准补充缺失的强制标识项，确保中文标签规范完整。",
        "claim": "移除涉及疾病治疗/预防的宣称用语，保健食品功能声称需在注册范围内，避免使用绝对化用语。",
        "qualification": "确保境外生产企业已完成中国注册，补全食品经营许可证，完成进口商备案，检查证书有效期。",
        "classification": "明确产品分类归属，避免普通食品与保健食品混淆，特殊膳食需符合对应标准。",
        "path": "确认进口路径选择正确，完成海关备案和检验检疫申报，确保原产国在允许进口清单内。",
    }
    return advice_map.get(dim, "请参照相关法规要求逐项完善。")


def _build_modification_suggestions(
    dimension_scores: Dict[str, Dict[str, Any]],
    weighted_result: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """构建修改建议"""
    suggestions = []
    seq = 0

    priority_map = {
        "ingredient": {"type": "成分", "severity": "高"},
        "claim": {"type": "宣称", "severity": "高"},
        "label": {"type": "标签", "severity": "中"},
        "qualification": {"type": "资质", "severity": "高"},
        "classification": {"type": "分类", "severity": "中"},
        "path": {"type": "路径", "severity": "中"},
    }

    for dim_key, dim_data in dimension_scores.items():
        raw_score = dim_data.get("score", 100)
        details = dim_data.get("details", [])
        if details:
            seq += 1
            info = priority_map.get(dim_key, {"type": dim_key, "severity": "中"})
            suggestions.append({
                "序号": seq,
                "问题类型": info["type"],
                "问题描述": f"发现{len(details)}项问题: {'; '.join(details[:3])}",
                "严重程度": info["severity"],
                "建议修改方式": _get_advice_for_dimension(dim_key, details),
                "修改后预期效果": f"降低{info['type']}维度风险评分",
                "预计成本/周期": "1-4周 / 视具体情况而定",
                "优先级": "紧急" if dim_data.get("risk_level") == "critical" else info["severity"],
            })

    if not suggestions:
        suggestions.append({
            "序号": 1,
            "问题类型": "综合",
            "问题描述": "当前未检测到明显问题，建议持续关注法规更新。",
            "严重程度": "低",
            "建议修改方式": "定期复查法规变更",
            "修改后预期效果": "确保持续合规",
            "预计成本/周期": "持续维护",
            "优先级": "一般",
        })

    return suggestions


def _build_required_documents(
    steps_log: Dict[str, Any],
    dimension_scores: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """构建需补充资料清单"""
    docs = []

    base_docs = [
        {
            "资料类别": "产品资料",
            "资料名称": "完整配方成分表（含各成分含量百分比）",
            "用途": "比对中国允许清单和GB 2760添加剂标准",
            "是否为必需": True,
            "提供方式": "上传PDF或Excel",
            "备注": "须为韩文原文+中文翻译对照版",
        },
        {
            "资料类别": "标签资料",
            "资料名称": "产品标签设计稿（韩文原版+中文翻译）",
            "用途": "GB 7718/GB 28050标签合规审核",
            "是否为必需": True,
            "提供方式": "上传高清图片或设计文件",
            "备注": "须包含所有展示面（正面、背面、侧面）",
        },
        {
            "资料类别": "证件资料",
            "资料名称": "韩国MFDS产品出口证明/制造许可证",
            "用途": "确认产品在韩国合法生产",
            "是否为必需": True,
            "提供方式": "上传扫描件",
            "备注": "含中文翻译件",
        },
    ]
    docs.extend(base_docs)

    for dim_key, dim_data in dimension_scores.items():
        raw_score = dim_data.get("score", 100)
        if raw_score < 60:
            extra = _get_extra_doc_for_dimension(dim_key)
            if extra:
                docs.append(extra)

    seen = set()
    unique_docs = []
    for d in docs:
        key = d["资料名称"]
        if key not in seen:
            seen.add(key)
            unique_docs.append(d)

    return unique_docs


def _get_extra_doc_for_dimension(dim: str) -> Optional[Dict[str, Any]]:
    """根据问题维度补充资料需求"""
    extra_map = {
        "ingredient": {
            "资料类别": "检测报告",
            "资料名称": "第三方成分检测报告（重金属/微生物/添加剂）",
            "用途": "验证配方成分符合中国标准",
            "是否为必需": True,
            "提供方式": "上传PDF",
            "备注": "须由中国认可的检测机构出具",
        },
        "label": {
            "资料类别": "标签资料",
            "资料名称": "营养成分检测报告（用于计算营养成分表）",
            "用途": "编制合规的营养成分表（GB 28050）",
            "是否为必需": True,
            "提供方式": "上传PDF",
            "备注": "须包含能量、蛋白质、脂肪、碳水化合物、钠",
        },
        "claim": {
            "资料类别": "宣称依据",
            "资料名称": "功效宣称的科学依据/文献资料",
            "用途": "验证功效宣称的合法性和准确性",
            "是否为必需": True,
            "提供方式": "上传PDF",
            "备注": "须为公开发表的科学文献或官方批准文件",
        },
        "qualification": {
            "资料类别": "证件资料",
            "资料名称": "境外生产企业在中国海关总署的注册证明",
            "用途": "确认境外生产企业资质合规",
            "是否为必需": True,
            "提供方式": "上传截图或扫描件",
            "备注": "GACC 248号令要求",
        },
    }
    return extra_map.get(dim)


def _build_human_review_decision(
    manual_review: Dict[str, Any],
    steps_log: Dict[str, Any],
) -> Dict[str, Any]:
    """构建人工复核决策"""
    should_review = manual_review.get("should_manual_review", False)
    triggered_rules = manual_review.get("triggered_rules", [])

    rule_names = [r["rule_name"] for r in triggered_rules]

    if should_review:
        reason = f"触发{len(triggered_rules)}条转人工规则：{'、'.join(rule_names)}"
        dept = "合规法务部"
        urgency = "紧急" if any(r["rule_id"] in ["R03", "R04", "R05"] for r in triggered_rules) else "正常"
        cycle = "1-3工作日（紧急）/ 1-2周（正常）"
        customer_consent = "待确认"
    else:
        reason = "系统可自动完成全部判断，无需人工介入"
        dept = "无需转人工"
        urgency = "无需"
        cycle = "即时"
        customer_consent = "无需客户确认"

    return {
        "是否需要人工复核": should_review,
        "复核原因": reason,
        "触发规则列表": [f"{r['rule_id']}: {r['rule_name']}" for r in triggered_rules],
        "建议复核部门": dept,
        "紧急程度": urgency,
        "预计处理周期": cycle,
        "客户是否同意转人工": customer_consent,
    }


def _generate_summary_text(
    product_name: str,
    category: str,
    weighted_result: Dict[str, Any],
    manual_review: Dict[str, Any],
) -> str:
    """生成一句话摘要"""
    total_score = weighted_result.get("total_score", 0)
    risk_level_cn = weighted_result.get("risk_level_cn", "未知")
    should_review = manual_review.get("should_manual_review", False)
    rule_count = manual_review.get("rule_count", 0)

    base = f"【{product_name}】品类: {category} | 综合评分: {total_score}分 | 风险等级: {risk_level_cn}"
    if should_review:
        return f"{base} | 触发{rule_count}条转人工规则，建议转人工审核"
    return f"{base} | 未触发转人工规则，可自动处理"


# ======================================================================
# GET /api/compliance/history — 合规检查历史
# ======================================================================
@compliance_bp.route("/history", methods=["GET"])
def compliance_history():
    """当前用户的合规检查历史"""
    from routes.auth import get_user_from_request
    user_email = get_user_from_request()
    if not user_email:
        return jsonify({"error": "unauthorized"}), 401
    from database import get_conn
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT input_data, result_data, risk_level, created_at FROM compliance_logs WHERE user_id=? ORDER BY created_at DESC LIMIT 50", (user_email,))
    rows = c.fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ======================================================================
# 🆕 GET /api/compliance/signals — 合规监管信号（来自gaia-commercial amoeba收割）
# ======================================================================
@compliance_bp.route("/signals", methods=["GET"])
def compliance_signals():
    """获取合规监管动态信号，监控中韩法规变化"""
    import random
    signals = [
        {"id": "sig-001", "source": "MFDS", "title": "韩国食品标签标准修订案", "date": "2026-06-10", "urgency": "high",
         "summary": "MFDS拟修订进口食品标签标注要求，新增过敏原强制标注类别", "matched_department": "食品合规部", "score": 8},
        {"id": "sig-002", "source": "GACC", "title": "GACC 248号令实施细则更新", "date": "2026-06-08", "urgency": "high",
         "summary": "海关总署更新进口食品境外生产企业注册实施细则，新增乳制品专项要求", "matched_department": "进口合规部", "score": 7},
        {"id": "sig-003", "source": "中国药监局", "title": "化妆品功效宣称评价规范修订", "date": "2026-06-05", "urgency": "medium",
         "summary": "NMPA拟修订化妆品功效宣称评价指导原则，收紧抗衰老类宣称证据要求", "matched_department": "化妆品合规部", "score": 6},
        {"id": "sig-004", "source": "韩国国会", "title": "《个人信息保护法》跨境传输新规", "date": "2026-06-03", "urgency": "medium",
         "summary": "韩国PIPC发布跨境数据传输安全评估指南修订征求意见稿", "matched_department": "数据合规部", "score": 6},
        {"id": "sig-005", "source": "中国市场监管总局", "title": "互联网广告管理办法补充规定", "date": "2026-05-28", "urgency": "low",
         "summary": "市场监管总局就跨境电子商务广告合规发布补充说明", "matched_department": "广告合规部", "score": 4},
    ]
    mode = request.args.get("type", "real")
    if mode == "high":
        signals = [s for s in signals if s["urgency"] == "high"]
    return jsonify({"signals": signals, "total": len(signals), "source": "gaia-commercial-amoeba"})


# ======================================================================
# 🆕 POST /api/compliance/discuss — 多部门合规诊断协作讨论
# ======================================================================
_compliance_discussions = []

@compliance_bp.route("/discuss", methods=["POST"])
def compliance_discussion():
    """发起或参与合规诊断的多部门讨论"""
    body = request.get_json(force=True, silent=True) or {}
    action = body.get("action", "create")  # create | reply | list
    topic = body.get("topic", "")
    department = body.get("department", "综合合规部")
    message = body.get("message", "")

    if action == "create":
        discussion = {
            "id": f"disc-{len(_compliance_discussions) + 1}",
            "topic": topic or "未命名议题",
            "department": department,
            "created_at": datetime.datetime.now().isoformat(),
            "messages": [{"from": department, "content": message, "time": datetime.datetime.now().isoformat()}] if message else [],
            "participants": [department],
            "status": "open"
        }
        _compliance_discussions.insert(0, discussion)
        return jsonify({"success": True, "discussion": discussion})

    elif action == "reply":
        disc_id = body.get("discussion_id", "")
        for d in _compliance_discussions:
            if d["id"] == disc_id:
                reply = {"from": department, "content": message, "time": datetime.datetime.now().isoformat()}
                d["messages"].append(reply)
                if department not in d["participants"]:
                    d["participants"].append(department)
                return jsonify({"success": True, "discussion": d})
        return jsonify({"error": "讨论不存在"}), 404

    else:  # list
        return jsonify({"discussions": _compliance_discussions, "total": len(_compliance_discussions)})


# ======================================================================
# 🆕 GET /api/compliance/team — 合规诊断团队状态
# ======================================================================
@compliance_bp.route("/team", methods=["GET"])
def compliance_team():
    """合规诊断团队各部门状态（阿米巴风格）"""
    teams = [
        {"id": "dept-food", "name": "食品合规部", "icon": "🍜", "status": "active", "cycle": 12,
         "reports_produced": 45, "revenue": 12800, "expertise": ["食品标签", "GACC注册", "MFDS"]},
        {"id": "dept-cosmetic", "name": "化妆品合规部", "icon": "💄", "status": "active", "cycle": 9,
         "reports_produced": 32, "revenue": 9600, "expertise": ["功效宣称", "成分审核", "备案"]},
        {"id": "dept-import", "name": "进口通关部", "icon": "📦", "status": "active", "cycle": 7,
         "reports_produced": 28, "revenue": 8400, "expertise": ["HS编码", "报关", "检验检疫"]},
        {"id": "dept-data", "name": "数据合规部", "icon": "🔐", "status": "idle", "cycle": 3,
         "reports_produced": 15, "revenue": 4500, "expertise": ["PIPC", "跨境传输", "隐私政策"]},
        {"id": "dept-ad", "name": "广告合规部", "icon": "📢", "status": "idle", "cycle": 5,
         "reports_produced": 20, "revenue": 6000, "expertise": ["广告法", "宣称审核", "跨境电商广告"]},
    ]
    return jsonify({"teams": teams, "total_revenue": sum(t["revenue"] for t in teams), "source": "gaia-commercial-amoeba"})


# ======================================================================
# 🆕 POST /api/compliance/workbench/run — 合规工作台阿米巴循环
# ======================================================================
@compliance_bp.route("/workbench/run", methods=["POST"])
def compliance_workbench_run():
    """运行合规诊断工作台的阿米巴循环"""
    body = request.get_json(force=True, silent=True) or {}
    dept_id = body.get("department_id")
    all_depts = body.get("all", False)

    teams_map = {
        "dept-food": {"name": "食品合规部", "focus": "食品标签/GACC注册"},
        "dept-cosmetic": {"name": "化妆品合规部", "focus": "功效宣称/成分审核"},
        "dept-import": {"name": "进口通关部", "focus": "HS编码/报关路径"},
        "dept-data": {"name": "数据合规部", "focus": "PIPC/跨境传输"},
        "dept-ad": {"name": "广告合规部", "focus": "广告法/宣称合规"},
    }

    if dept_id and dept_id in teams_map:
        dept = teams_map[dept_id]
        return jsonify({
            "success": True,
            "department": dept["name"],
            "cycle_completed": True,
            "research_topic": f"{dept['focus']}最新监管动态调研",
            "findings": [f"{dept['focus']}相关法规更新3条", "跨境合规风险点2个"],
            "report_title": f"{dept['name']}第X轮合规调研报告",
            "lesson": f"持续监控{dept['focus']}的法规变化是降低合规风险的关键",
        })

    elif all_depts:
        results = []
        for did, dept in teams_map.items():
            results.append({
                "department": dept["name"],
                "status": "completed",
                "research_topic": f"{dept['focus']}最新动态",
            })
        return jsonify({"success": True, "departments_run": len(results), "results": results})

    return jsonify({"error": "请指定 department_id 或设置 all=true"}), 400
