#!/bin/sh
# =============================================================================
# 链客宝 — Docker 健康检查脚本
# 验证 Nginx + uvicorn 均正常运行
# =============================================================================

# 检查 uvicorn 是否响应
python -c "
import urllib.request
try:
    resp = urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=5)
    assert resp.status == 200, f'Status: {resp.status}'
    print('[Health] uvicorn OK')
except Exception as e:
    print(f'[Health] uvicorn FAIL: {e}')
    exit(1)
"

# 检查 Nginx 是否响应
python -c "
import urllib.request
try:
    resp = urllib.request.urlopen('http://127.0.0.1:80/', timeout=5)
    # 200 或 304 都算正常（前端 index.html 或 SPA fallback）
    assert resp.status in (200, 304), f'Status: {resp.status}'
    print('[Health] nginx OK')
except Exception as e:
    print(f'[Health] nginx FAIL: {e}')
    exit(1)
"
