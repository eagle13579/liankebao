#!/usr/bin/env python3
"""
链客宝AI API SDK 生成器
================================
从 FastAPI OpenAPI Schema 自动生成 TypeScript SDK。

使用方法:
  python scripts/generate_api_sdk.py
  python scripts/generate_api_sdk.py --url http://localhost:8001/openapi.json
  python scripts/generate_api_sdk.py --cache backend/openapi_cache.json

输出: src/api/generated.ts
"""

import json
import os
import re
import sys
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

# ===== 配置 =====
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DEFAULT_CACHE = os.path.join(PROJECT_DIR, "backend", "openapi_cache.json")
DEFAULT_OUTPUT = os.path.join(PROJECT_DIR, "src", "api", "generated.ts")
DEFAULT_URL = "http://localhost:8001/openapi.json"

# ===== 类型映射（OpenAPI → TypeScript）=====
TYPE_MAP: Dict[str, str] = {
    "string": "string",
    "integer": "number",
    "number": "number",
    "boolean": "boolean",
    "object": "Record<string, any>",
    "array": "any[]",
}

# ===== 需要生成友好函数名的端点 =====
FRIENDLY_ENDPOINTS: Dict[str, Dict[str, str]] = {
    # Auth
    "POST /api/auth/login": "login",
    "POST /api/auth/register": "register",
    "GET /api/auth/me": "getCurrentUser",
    "POST /api/auth/refresh": "refreshToken",
    "POST /api/auth/logout": "logout",
    "POST /api/auth/wechat-login": "wechatLogin",
    # Products
    "GET /api/products": "getProducts",
    "GET /api/products/{product_id}": "getProduct",
    "POST /api/products": "createProduct",
    "PUT /api/products/{product_id}": "updateProduct",
    "DELETE /api/products/{product_id}": "deleteProduct",
    # Orders
    "GET /api/orders": "getOrders",
    "POST /api/orders": "createOrder",
    "GET /api/orders/{order_id}": "getOrder",
    "PUT /api/orders/{order_id}/status": "updateOrderStatus",
    # Business Cards
    "POST /api/card/scan": "scanCard",
    "POST /api/card/generate": "generateCard",
    "GET /api/card": "listCards",
    "GET /api/card/{id}": "getCard",
    "DELETE /api/card/{id}": "deleteCard",
    "GET /api/card/token/{token}": "getCardByToken",
    "POST /api/card/{id}/match": "matchCard",
    # Search
    "GET /api/search": "search",
    "GET /api/search/vector": "vectorSearch",
    "GET /api/search/categories": "getSearchCategories",
    "GET /api/search/suggestions": "getSearchSuggestions",
    # BI
    "GET /api/bi/overview": "getOverview",
    "GET /api/bi/revenue": "getRevenue",
    "GET /api/bi/top-products": "getTopProducts",
    "GET /api/bi/user-growth": "getUserGrowth",
    "GET /api/bi/card-stats": "getCardStats",
    # Promoter
    "GET /api/promoter/earnings": "getEarnings",
    "POST /api/promoter/withdraw": "withdraw",
    "GET /api/promoter/withdrawals": "getWithdrawals",
    # Admin
    "GET /api/admin/dashboard": "getDashboard",
    "GET /api/admin/users": "getAdminUsers",
    "PATCH /api/admin/users/{user_id}/role": "updateUserRole",
    "GET /api/admin/products": "getAdminProducts",
    "PUT /api/admin/products/{product_id}/review": "reviewProduct",
    "GET /api/admin/withdrawals": "getAdminWithdrawals",
    "PUT /api/admin/withdrawals/{withdrawal_id}/review": "reviewWithdrawal",
    # Imports
    "POST /api/imports/preview": "importPreview",
    "POST /api/imports/confirm": "importConfirm",
    "GET /api/imports/history": "getImportHistory",
    # Contacts
    "GET /api/contacts": "getContacts",
    "POST /api/contacts": "createContact",
    "GET /api/contacts/{contact_id}": "getContact",
    "PUT /api/contacts/{contact_id}": "updateContact",
    "DELETE /api/contacts/{contact_id}": "deleteContact",
    # Activities
    "GET /api/activities": "getActivities",
    "POST /api/activities": "createActivity",
    # Needs
    "GET /api/needs": "getNeeds",
    "POST /api/needs": "createNeed",
    "PUT /api/needs/{need_id}": "updateNeed",
    "DELETE /api/needs/{need_id}": "deleteNeed",
    # Notifications
    "GET /api/notifications": "getNotifications",
    # Payment
    "POST /api/payment/wxpay/unified-order": "wxpayUnifiedOrder",
    "GET /api/payment/wxpay/query/{order_no}": "wxpayQueryOrder",
    "GET /api/payment/config": "getPaymentConfig",
    # Recharge
    "GET /api/recharge/balance": "getRechargeBalance",
    "POST /api/recharge/precreate": "createRechargePrecreate",
    "GET /api/recharge/query/{order_no}": "queryRechargeOrder",
    "GET /api/recharge/list": "getRechargeList",
    "GET /api/recharge/balance-logs": "getBalanceLogs",
    # Banners
    "GET /api/banners": "getBanners",
    "GET /banners": "getPublicBanners",
    # Users
    "GET /api/users/{user_id}/brief": "getUserBrief",
    # System
    "GET /api/system/log-level": "getLogLevel",
    "PUT /api/system/log-level": "setLogLevel",
    "GET /api/system/cost/usage": "getCostUsage",
    "GET /api/system/cost/breakdown": "getCostBreakdown",
    "GET /api/system/cost/models": "getCostModels",
    # Health
    "GET /health": "healthCheck",
    "GET /health/live": "healthLiveness",
    "GET /health/ready": "healthReadiness",
}


def load_openapi_schema(
    url: Optional[str] = None, cache_path: Optional[str] = None
) -> Dict:
    """从 URL 或缓存文件加载 OpenAPI Schema"""
    # 优先从 URL 加载
    if url:
        try:
            print(f"[INFO] 从 {url} 获取 OpenAPI Schema...")
            resp = urllib.request.urlopen(url, timeout=10)
            schema = json.loads(resp.read())
            print(f"[INFO] 成功获取 OpenAPI Schema ({len(json.dumps(schema))} bytes)")
            return schema
        except Exception as e:
            print(f"[WARN] 从 URL 获取失败: {e}")

    # 从缓存文件加载
    cache = cache_path or DEFAULT_CACHE
    if os.path.exists(cache):
        print(f"[INFO] 从缓存文件 {cache} 加载 OpenAPI Schema...")
        with open(cache, "r", encoding="utf-8") as f:
            schema = json.load(f)
        print(f"[INFO] 成功加载 OpenAPI Schema ({len(json.dumps(schema))} bytes)")
        return schema

    raise RuntimeError(
        f"无法加载 OpenAPI Schema。请确保后端运行在 {url or DEFAULT_URL}，"
        f"或提供缓存文件路径。"
    )


def _openapi_type_to_ts(openapi_type: str, schema_obj: Dict) -> str:
    """将 OpenAPI 类型转换为 TypeScript 类型"""
    if "$ref" in schema_obj:
        ref = schema_obj["$ref"]
        name = ref.split("/")[-1]
        return name

    type_name = schema_obj.get("type", "string")
    if type_name == "array":
        items = schema_obj.get("items", {})
        item_type = _openapi_type_to_ts(items.get("type", "string"), items)
        return f"{item_type}[]"
    if type_name == "object":
        if "additionalProperties" in schema_obj:
            val_type = _openapi_type_to_ts(
                schema_obj["additionalProperties"].get("type", "string"),
                schema_obj["additionalProperties"],
            )
            return f"Record<string, {val_type}>"
        return "Record<string, any>"

    # Handle anyOf / oneOf
    if "anyOf" in schema_obj:
        types = []
        for opt in schema_obj["anyOf"]:
            if opt.get("type") == "null":
                continue
            t = _openapi_type_to_ts(opt.get("type", "string"), opt)
            types.append(t)
        if not types:
            return "any"
        return " | ".join(types)

    return TYPE_MAP.get(type_name, "any")


def _make_optional(ts_type: str, nullable: bool = False) -> str:
    """添加 optional 包装"""
    if nullable and not ts_type.endswith("undefined"):
        return f"{ts_type} | null"
    return ts_type


def _parse_schema_properties(schema_obj: Dict, schemas: Dict) -> Dict[str, str]:
    """递归解析 schema 属性"""
    if "$ref" in schema_obj:
        ref = schema_obj["$ref"]
        name = ref.split("/")[-1]
        return _parse_schema_properties(schemas.get(name, {}), schemas)

    # allOf: 合并多个 schema
    if "allOf" in schema_obj:
        combined: Dict[str, Any] = {}
        for sub in schema_obj["allOf"]:
            combined.update(_parse_schema_properties(sub, schemas))
        return combined

    properties = {}
    for prop_name, prop_schema in schema_obj.get("properties", {}).items():
        # 检查是否 required
        required_list = schema_obj.get("required", [])
        is_required = prop_name in required_list

        # 获取类型
        ts_type = _openapi_type_to_ts(prop_schema.get("type", "string"), prop_schema)

        # 检查 nullable
        nullable = False
        if "anyOf" in prop_schema:
            for opt in prop_schema["anyOf"]:
                if opt.get("type") == "null":
                    nullable = True
                    break

        if not is_required or nullable:
            if not ts_type.endswith(" | undefined"):
                if nullable:
                    ts_type += " | null"
                if not is_required and not ts_type.endswith(" | undefined"):
                    ts_type += " | undefined"

        properties[prop_name] = ts_type

    return properties


def _resolve_schema_name(schema_obj: Dict, schemas: Dict) -> str:
    """解析 schema 引用的名称"""
    if "$ref" in schema_obj:
        return schema_obj["$ref"].split("/")[-1]
    if "allOf" in schema_obj:
        for sub in schema_obj["allOf"]:
            if "$ref" in sub:
                return sub["$ref"].split("/")[-1]
    return "any"


def _get_response_data_schema(response_schema: Dict, schemas: Dict) -> Optional[Dict]:
    """从 ApiResponse 响应中提取 data 字段的 schema"""
    schema_name = _resolve_schema_name(response_schema, schemas)
    if not schema_name or schema_name not in schemas:
        return None

    schema_obj = schemas[schema_name]
    data_prop = schema_obj.get("properties", {}).get("data", {})
    if "$ref" in data_prop:
        data_ref = data_prop["$ref"].split("/")[-1]
        if data_ref in schemas:
            return schemas[data_ref]
    if "anyOf" in data_prop:
        for opt in data_prop["anyOf"]:
            if "$ref" in opt:
                data_ref = opt["$ref"].split("/")[-1]
                if data_ref in schemas:
                    return schemas[data_ref]
    return None


def _get_endpoint_key(method: str, path: str) -> str:
    """获取端点的唯一键（用于查找友好函数名）"""
    return f"{method.upper()} {path}"


def _path_to_ts_params(path: str) -> List[Tuple[str, str, bool]]:
    """提取路径参数并返回 (name, ts_type, optional)"""
    params = re.findall(r"\{(\w+)\}", path)
    return [(p, "string | number", False) for p in params]


def _to_pascal_case(name: str) -> str:
    """转换为 PascalCase"""
    parts = re.split(r"[_\s-]+", name)
    return "".join(p.capitalize() for p in parts if p)


def generate_ts_sdk(schema: Dict) -> str:
    """生成 TypeScript SDK 源码"""
    schemas = schema.get("components", {}).get("schemas", {})
    paths = schema.get("paths", {})

    # ===== 收集所有需要的数据类型 =====
    all_types: Dict[str, Dict[str, str]] = {}
    for schema_name, schema_obj in schemas.items():
        # Skip HTTP validation schemas
        if schema_name in ("HTTPValidationError", "ValidationError", "Body_*"):
            continue
        if schema_name.startswith("Body_"):
            continue

        properties = _parse_schema_properties(schema_obj, schemas)
        if properties:
            all_types[schema_name] = properties

    # ===== 收集端点信息 =====
    endpoints: List[Dict] = []
    used_types: set = set()

    for path, methods in paths.items():
        for method, detail in methods.items():
            if not detail.get("operationId"):
                continue

            ep = {
                "path": path,
                "method": method.upper(),
                "operation_id": detail.get("operationId", ""),
                "summary": detail.get("summary", ""),
                "description": detail.get("description", ""),
                "request_body": None,
                "path_params": _path_to_ts_params(path),
                "query_params": [],
                "response_type": "any",
                "needs_auth": bool(detail.get("security")),
            }

            # --- Request Body ---
            req_body = detail.get("requestBody", {})
            if req_body:
                content = req_body.get("content", {})
                json_content = content.get("application/json", {})
                schema_ref = json_content.get("schema", {})
                if schema_ref:
                    ep["request_body"] = _resolve_schema_name(schema_ref, schemas)
                    if ep["request_body"] in all_types:
                        used_types.add(ep["request_body"])

            # --- Query Parameters ---
            for param in detail.get("parameters", []):
                if param.get("in") == "query":
                    param_schema = param.get("schema", {})
                    ts_type = _openapi_type_to_ts(
                        param_schema.get("type", "string"), param_schema
                    )
                    is_required = param.get("required", False)
                    default = param_schema.get("default")
                    ep["query_params"].append(
                        {
                            "name": param["name"],
                            "type": ts_type,
                            "required": is_required,
                            "default": default,
                        }
                    )

            # --- Response Type (从 data 字段提取) ---
            responses = detail.get("responses", {})
            ok_response = responses.get("200", {})
            response_content = ok_response.get("content", {})
            response_json = response_content.get("application/json", {})
            response_schema = response_json.get("schema", {})

            if response_schema:
                data_schema = _get_response_data_schema(response_schema, schemas)
                if data_schema:
                    # 尝试找到对应的 schema name
                    for s_name, s_obj in schemas.items():
                        if s_obj is data_schema or (
                            "$ref" in response_schema
                            and response_schema["$ref"].endswith(f"/{s_name}")
                        ):
                            ep["response_type"] = s_name
                            used_types.add(s_name)
                            break
                    else:
                        # 解析内联 data schema
                        props = _parse_schema_properties(data_schema, schemas)
                        if props:
                            # 生成匿名类型
                            op_name = detail.get("operationId", "anonymous")
                            type_name = (
                                _to_pascal_case(op_name.replace("_", " ")) + "Response"
                            )
                            all_types[type_name] = props
                            ep["response_type"] = type_name
                            used_types.add(type_name)

            endpoints.append(ep)

    # ===== 构建 SDK 源码 =====
    lines: List[str] = [
        "// ============================================================",
        "// 链客宝AI API SDK — 由 scripts/generate_api_sdk.py 自动生成",
        "// 生成时间: " + __import__("datetime").datetime.now().isoformat(),
        "// ============================================================",
        "",
        'import { api } from "./client";',
        "",
        "// ============================================================",
        "// 数据类型",
        "// ============================================================",
    ]

    # --- 输出 TypeScript 类型 ---
    for type_name in sorted(all_types.keys()):
        if type_name.startswith("Body_"):
            continue
        if type_name in ("HTTPValidationError", "ValidationError"):
            continue

        props = all_types[type_name]
        lines.append("")
        lines.append(f"export interface {type_name} {{")
        for prop_name, prop_type in sorted(props.items()):
            ts_name = prop_name if not prop_name.startswith("_") else f'"{prop_name}"'
            lines.append(f"  {ts_name}: {prop_type};")
        lines.append("}")

    # --- 生成针对含分页字段的类型添加 Paginated 包装 ---
    lines.append("")
    lines.append("// ============================================================")
    lines.append("// 分页响应包装")
    lines.append("// ============================================================")
    lines.append("")
    lines.append("export interface PaginatedResponse<T> {")
    lines.append("  total: number;")
    lines.append("  page: number;")
    lines.append("  page_size: number;")
    lines.append("  items: T[];")
    lines.append("}")

    # ===== API 函数 =====
    lines.append("")
    lines.append("// ============================================================")
    lines.append("// API 函数")
    lines.append("// ============================================================")

    # 辅助：生成 API 响应包装类型
    lines.append("")
    lines.append("export interface ApiResult<T> {")
    lines.append("  code: number;")
    lines.append("  message: string;")
    lines.append("  data?: T;")
    lines.append("}")

    for ep in endpoints:
        key = _get_endpoint_key(ep["method"], ep["path"])
        func_name = FRIENDLY_ENDPOINTS.get(key)

        if not func_name:
            continue

        lines.append("")
        lines.append("/**")
        if ep.get("summary"):
            lines.append(f" * {ep['summary']}")
        if ep.get("description"):
            # 只取第一行
            desc_first = ep["description"].split("\n")[0].strip()
            lines.append(f" * {desc_first}")
        lines.append(f" * {ep['method']} {ep['path']}")
        lines.append(" */")

        # 构建参数
        params: List[str] = []
        param_docs: List[str] = []

        # 路径参数
        for p_name, p_type, _ in ep["path_params"]:
            params.append(f"{p_name}: {p_type}")
            param_docs.append(f" * @param {p_name} - 路径参数")

        # Query 参数
        optional_query_params = []
        for qp in ep["query_params"]:
            ts_type = qp["type"]
            if not qp["required"]:
                ts_type += " | undefined"
                optional_query_params.append(qp)
            else:
                params.append(f"{qp['name']}: {ts_type}")
            param_docs.append(f" * @param {qp['name']} - {qp.get('type', '')}")

        # Request body
        req_body_type = ep.get("request_body")
        if req_body_type:
            params.append(f"data: {req_body_type}")
            param_docs.append(" * @param data - 请求体")

        # 可选 query params 放到对象参数中
        if optional_query_params:
            query_type_name = func_name[0].upper() + func_name[1:] + "Params"
            lines.append(f"export interface {query_type_name} {{")
            for qp in optional_query_params:
                ts_type = qp["type"]
                if not qp["required"]:
                    ts_type += " | undefined"
                lines.append(f"  {qp['name']}?: {ts_type};")
            lines.append("}")
            lines.append("")
            params.append(f"params?: {query_type_name}")

        # 函数签名
        response_type = ep.get("response_type", "any")
        params_str = ", ".join(params)

        lines.append(
            f"export async function {func_name}({params_str}): Promise<ApiResult<{response_type}>> {{"
        )

        # 构建 URL
        ts_path = ep["path"]
        # 替换路径参数
        for p_name, _, _ in ep["path_params"]:
            ts_path = ts_path.replace(f"{{{p_name}}}", f"${{{p_name}}}")

        # 只添加必需的 query 参数到 path
        has_required_query = any(qp.get("required") for qp in ep["query_params"])

        # 构建 URL
        lines.append(f"  let path: string = `{ts_path}`;")

        # 处理 query 参数（必需的拼到path，可选的从 params 对象取）
        required_query = [qp for qp in ep["query_params"] if qp.get("required")]
        if required_query:
            qs_expr = "&".join(
                f"{qp['name']}=${{{qp['name']}}}" for qp in required_query
            )
            lines.append(f"  path += `?{qs_expr}`;")

        if optional_query_params:
            qs_parts = []
            for qp in optional_query_params:
                qs_parts.append(
                    f"    (params?.{qp['name']} !== undefined ? `{qp['name']}=${{params!.{qp['name']}}}` : '')"
                )
            lines.append("  const queryParts = [")
            lines.append(",\n".join(qs_parts))
            lines.append("  ].filter(Boolean);")
            lines.append("  if (queryParts.length > 0) {")
            lines.append(
                "    path += (path.includes('?') ? '&' : '?') + queryParts.join('&');"
            )
            lines.append("  }")

        # 发送请求
        method_lower = ep["method"].lower()
        if method_lower == "get":
            lines.append(f"  return api.get<{response_type}>(path);")
        elif method_lower == "post":
            body_arg = "data" if req_body_type else "undefined"
            lines.append(f"  return api.post<{response_type}>(path, {body_arg});")
        elif method_lower == "put":
            body_arg = "data" if req_body_type else "undefined"
            lines.append(f"  return api.put<{response_type}>(path, {body_arg});")
        elif method_lower == "patch":
            lines.append(
                f"  return api.request<{response_type}>(path, {{ method: 'PATCH', body: JSON.stringify(data) }});"
            )
        elif method_lower == "delete":
            lines.append(
                f"  return api.request<{response_type}>(path, {{ method: 'DELETE' }});"
            )

        lines.append("}")

    # ===== 命名空间导出 =====
    lines.append("")
    lines.append("// ============================================================")
    lines.append("// 分组命名空间导出")
    lines.append("// ============================================================")
    lines.append("")

    groups = {
        "auth": [
            "login",
            "register",
            "getCurrentUser",
            "refreshToken",
            "logout",
            "wechatLogin",
        ],
        "products": [
            "getProducts",
            "getProduct",
            "createProduct",
            "updateProduct",
            "deleteProduct",
        ],
        "orders": ["getOrders", "createOrder", "getOrder", "updateOrderStatus"],
        "cards": [
            "scanCard",
            "generateCard",
            "listCards",
            "getCard",
            "deleteCard",
            "getCardByToken",
            "matchCard",
        ],
        "search": [
            "search",
            "vectorSearch",
            "getSearchCategories",
            "getSearchSuggestions",
        ],
        "bi": [
            "getOverview",
            "getRevenue",
            "getTopProducts",
            "getUserGrowth",
            "getCardStats",
        ],
        "admin": [
            "getDashboard",
            "getAdminUsers",
            "updateUserRole",
            "getAdminProducts",
            "reviewProduct",
            "getAdminWithdrawals",
            "reviewWithdrawal",
        ],
        "contacts": [
            "getContacts",
            "createContact",
            "getContact",
            "updateContact",
            "deleteContact",
        ],
        "activities": ["getActivities", "createActivity"],
        "needs": ["getNeeds", "createNeed", "updateNeed", "deleteNeed"],
        "promoter": ["getEarnings", "withdraw", "getWithdrawals"],
        "imports": ["importPreview", "importConfirm", "getImportHistory"],
        "payment": ["wxpayUnifiedOrder", "wxpayQueryOrder", "getPaymentConfig"],
        "recharge": [
            "getRechargeBalance",
            "createRechargePrecreate",
            "queryRechargeOrder",
            "getRechargeList",
            "getBalanceLogs",
        ],
        "system": [
            "getLogLevel",
            "setLogLevel",
            "getCostUsage",
            "getCostBreakdown",
            "getCostModels",
        ],
        "notifications": ["getNotifications"],
        "health": ["healthCheck", "healthLiveness", "healthReadiness"],
    }

    for group_name, funcs in groups.items():
        lines.append(f"export const {group_name}Api = {{")
        for fn in funcs:
            lines.append(f"  {fn},")
        lines.append("};")
        lines.append("")

    return "\n".join(lines)


def validate_ts_syntax(output_path: str) -> bool:
    """使用 tsc 检查 TypeScript 语法"""
    import subprocess

    try:
        result = subprocess.run(
            ["npx", "tsc", "--noEmit", "--strict", "--lib", "es2020,dom", output_path],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=PROJECT_DIR,
        )
        if result.returncode == 0:
            print("[OK] TypeScript 语法检查通过")
            return True
        else:
            print("[WARN] TypeScript 语法检查有警告:")
            for line in result.stdout.split("\n") + result.stderr.split("\n"):
                if line.strip():
                    print(f"  {line.strip()}")
            return False
    except FileNotFoundError:
        print("[WARN] tsc 未找到，跳过语法检查")
        return True
    except Exception as e:
        print(f"[WARN] 语法检查失败: {e}")
        return True


def main():
    import argparse

    parser = argparse.ArgumentParser(description="链客宝AI API SDK 生成器")
    parser.add_argument(
        "--url",
        default=None,
        help=f"OpenAPI Schema URL (默认: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--cache",
        default=None,
        help=f"缓存文件路径 (默认: {DEFAULT_CACHE})",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"输出路径 (默认: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--skip-validate",
        action="store_true",
        help="跳过 TypeScript 语法验证",
    )
    parser.add_argument(
        "--save-cache",
        action="store_true",
        help="将获取的 schema 保存到缓存文件",
    )

    args = parser.parse_args()

    try:
        # 加载 schema
        schema = load_openapi_schema(url=args.url, cache_path=args.cache)

        # 可选：保存缓存
        if args.save_cache and args.url:
            cache_path = args.cache or DEFAULT_CACHE
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(schema, f, ensure_ascii=False, indent=2)
            print(f"[INFO] Schema 已缓存到 {cache_path}")

        # 生成 SDK
        print("[INFO] 生成 TypeScript SDK...")
        ts_code = generate_ts_sdk(schema)

        # 确保输出目录存在
        output_dir = os.path.dirname(args.output)
        os.makedirs(output_dir, exist_ok=True)

        # 写入文件
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(ts_code)

        line_count = ts_code.count("\n") + 1
        print(f"[INFO] SDK 已生成到 {args.output} ({line_count} 行)")

        # 语法验证
        if not args.skip_validate:
            validate_ts_syntax(args.output)

        print("[DONE] SDK 生成完成")

    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
