"""
链客宝多租户自助注册 API 服务 v1
==============================
新客户在线注册 → 自动创建 workspace → 分配 API Key

端口: :8005
路由:
  POST /api/tenants/register   — 新租户注册
  GET  /api/tenants/{id}       — 查询租户信息
"""

import json
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── 配置 ──────────────────────────────────────────────────
HOST = "0.0.0.0"
PORT = 8005
DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tenant-portal", "tenants.db"
)


def _get_db():
    """获取数据库连接（自动建表）"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY,
            company_name TEXT NOT NULL,
            contact_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            api_key TEXT NOT NULL UNIQUE,
            workspace_id TEXT NOT NULL UNIQUE,
            workspace_status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def _generate_api_key() -> str:
    """生成 API Key: lk_ + 48位随机字符串"""
    return "lk_" + secrets.token_hex(24)


def _generate_workspace_id() -> str:
    """生成 workspace ID: ws_ + 8位随机字符串"""
    return "ws_" + secrets.token_hex(4)


def _hash_password(password: str) -> str:
    """简单密码哈希（生产环境应使用 bcrypt）"""
    import hashlib

    salt = "chainke_tenant_v1"
    return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()


def _verify_password(password: str, password_hash: str) -> bool:
    import hashlib

    salt = "chainke_tenant_v1"
    return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest() == password_hash


def _json_response(data, status=200):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return body, status, {"Content-Type": "application/json; charset=utf-8"}


class TenantAPIHandler(BaseHTTPRequestHandler):
    """租户 API 请求处理器"""

    def _send_response(self, body, status=200, headers=None):
        if headers is None:
            headers = {}
        headers.setdefault("Content-Type", "application/json; charset=utf-8")
        headers.setdefault("Access-Control-Allow-Origin", "*")
        headers.setdefault("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        headers.setdefault(
            "Access-Control-Allow-Headers", "Content-Type, Authorization"
        )

        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body if isinstance(body, bytes) else body.encode("utf-8"))

    def _read_body(self) -> dict:
        length = int(self.headers.get("content-length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _parse_path(self):
        """解析路径，返回 (resource, id_or_none)"""
        path = self.path.split("?")[0].rstrip("/")
        # /api/tenants/register
        if path == "/api/tenants/register":
            return ("register", None)
        # /api/tenants/{id}
        if path.startswith("/api/tenants/"):
            parts = path.split("/")
            if len(parts) >= 4:
                return ("tenant", parts[3])
        return (None, None)

    # ── 路由分发 ──────────────────────────────────────

    def do_OPTIONS(self):
        self._send_response(None, 204)

    def do_POST(self):
        resource, _ = self._parse_path()
        try:
            if resource == "register":
                self._handle_register()
            else:
                self._send_response(json.dumps({"error": "Not found"}).encode(), 404)
        except Exception as e:
            self._send_response(json.dumps({"error": str(e)}).encode(), 500)

    def do_GET(self):
        resource, id_val = self._parse_path()
        try:
            if resource == "tenant" and id_val:
                self._handle_get_tenant(id_val)
            else:
                self._send_response(json.dumps({"error": "Not found"}).encode(), 404)
        except Exception as e:
            self._send_response(json.dumps({"error": str(e)}).encode(), 500)

    # ── 业务逻辑 ──────────────────────────────────────

    def _handle_register(self):
        """POST /api/tenants/register — 新租户注册"""
        data = self._read_body()

        # 字段验证
        required = ["company_name", "contact_name", "email", "password"]
        for field in required:
            if not data.get(field) or not data[field].strip():
                self._send_response(
                    json.dumps({"error": f"缺少必填字段: {field}"}).encode(),
                    400,
                )
                return

        company_name = data["company_name"].strip()
        contact_name = data["contact_name"].strip()
        email = data["email"].strip().lower()
        password = data["password"]

        # 邮箱格式简单校验
        if "@" not in email or "." not in email:
            self._send_response(json.dumps({"error": "邮箱格式不正确"}).encode(), 400)
            return

        # 密码长度校验
        if len(password) < 6:
            self._send_response(json.dumps({"error": "密码至少6位"}).encode(), 400)
            return

        conn = _get_db()
        try:
            # 检查邮箱是否已注册
            existing = conn.execute(
                "SELECT id FROM tenants WHERE email = ?", (email,)
            ).fetchone()
            if existing:
                self._send_response(
                    json.dumps({"error": "该邮箱已注册，请直接登录"}).encode(), 409
                )
                return

            # 创建租户
            tenant_id = "tn_" + uuid.uuid4().hex[:12]
            api_key = _generate_api_key()
            workspace_id = _generate_workspace_id()
            password_hash = _hash_password(password)
            now = datetime.now(timezone.utc).isoformat()

            conn.execute(
                """INSERT INTO tenants
                   (id, company_name, contact_name, email, password_hash,
                    api_key, workspace_id, workspace_status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
                (
                    tenant_id,
                    company_name,
                    contact_name,
                    email,
                    password_hash,
                    api_key,
                    workspace_id,
                    now,
                    now,
                ),
            )
            conn.commit()

            # 返回注册成功信息（不返回密码哈希）
            result = {
                "success": True,
                "tenant": {
                    "id": tenant_id,
                    "company_name": company_name,
                    "contact_name": contact_name,
                    "email": email,
                    "api_key": api_key,
                    "workspace_id": workspace_id,
                    "workspace_status": "active",
                    "created_at": now,
                },
                "message": "注册成功！Workspace 已自动创建，API Key 已生成。",
            }
            self._send_response(json.dumps(result, ensure_ascii=False).encode(), 201)

        except sqlite3.IntegrityError as e:
            self._send_response(
                json.dumps({"error": f"注册失败: {str(e)}"}).encode(), 409
            )
        finally:
            conn.close()

    def _handle_get_tenant(self, tenant_id: str):
        """GET /api/tenants/{id} — 查询租户信息"""
        conn = _get_db()
        try:
            row = conn.execute(
                """SELECT id, company_name, contact_name, email,
                          api_key, workspace_id, workspace_status, created_at
                   FROM tenants WHERE id = ?""",
                (tenant_id,),
            ).fetchone()
            if not row:
                self._send_response(json.dumps({"error": "租户不存在"}).encode(), 404)
                return

            tenant = dict(row)
            self._send_response(
                json.dumps(
                    {"success": True, "tenant": tenant}, ensure_ascii=False
                ).encode()
            )
        finally:
            conn.close()

    def log_message(self, *a):
        pass


def start_server():
    print(f"🔑 链客宝租户注册 API 服务 :{PORT}")
    print(f"   📁 数据库: {DB_PATH}")
    print("   POST /api/tenants/register  — 新租户注册")
    print("   GET  /api/tenants/{id}     — 查询租户")
    HTTPServer((HOST, PORT), TenantAPIHandler).serve_forever()


if __name__ == "__main__":
    start_server()
