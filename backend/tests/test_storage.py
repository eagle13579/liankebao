"""
链客宝 — 文件存储模块测试
==========================
测试覆盖:
  1. StorageBackend 抽象基类不可实例化
  2. LocalStorage 上传/删除/get_url
  3. AliyunOSSStorage 配置缺失时 fallback 行为
  4. validate_file 类型检查 (允许/拒绝)
  5. validate_file 大小限制
  6. generate_storage_path 路径安全
  7. 路由 POST /api/storage/upload (集成)
  8. 路由 GET /api/storage/{path} (集成)
  9. 路由 DELETE /api/storage/{path} (集成)
"""

import io
import os
import sys
import json
import tempfile
import shutil
from pathlib import Path

# 确保项目根目录 (backend/) 在 sys.path
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _project_root)

from app.storage_service import (
    StorageBackend,
    LocalStorage,
    AliyunOSSStorage,
    validate_file,
    generate_storage_path,
    get_storage_backend,
    ALLOWED_CONTENT_TYPES,
    MAX_FILE_SIZE,
)


# ===================================================================
# Helper
# ===================================================================

def _make_binary_file(content: bytes = b"test content") -> io.BytesIO:
    return io.BytesIO(content)


# ===================================================================
# TC1: 抽象基类不可实例化
# ===================================================================

def test_abstract_base_class():
    """TC1: StorageBackend 抽象基类不能直接实例化"""
    try:
        StorageBackend()  # noqa
        assert False, "Should have raised TypeError"
    except TypeError as e:
        assert "abstract" in str(e).lower() or "Can't instantiate" in str(e)
        print(f"  ✓ TC1: 抽象基类不可实例化 → {e}")


# ===================================================================
# TC2: LocalStorage 上传 / 删除 / get_url
# ===================================================================

def test_local_storage_upload():
    """TC2.1: LocalStorage.upload — 上传文件并返回 URL"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = LocalStorage(base_dir=tmpdir)
        path = "test/hello.txt"
        url = store.upload(_make_binary_file(b"hello world"), path)
        assert url == f"/api/storage/file/{path}"
        # 验证文件确实写入
        abs_path = store._abs_path(path)
        assert abs_path.exists(), "文件应存在于磁盘"
        assert abs_path.read_bytes() == b"hello world"
        print(f"  ✓ TC2.1: LocalStorage.upload → {url}")


def test_local_storage_delete():
    """TC2.2: LocalStorage.delete — 删除已存在文件返回 True"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = LocalStorage(base_dir=tmpdir)
        path = "tmp/file.txt"
        store.upload(_make_binary_file(b"delete me"), path)
        assert store.delete(path) is True
        assert not store._abs_path(path).exists()
        print("  ✓ TC2.2: LocalStorage.delete (存在) → True")


def test_local_storage_delete_missing():
    """TC2.3: LocalStorage.delete — 删除不存在的文件返回 False"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = LocalStorage(base_dir=tmpdir)
        assert store.delete("nonexistent/file.txt") is False
        print("  ✓ TC2.3: LocalStorage.delete (不存在) → False")


def test_local_storage_get_url():
    """TC2.4: LocalStorage.get_url"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = LocalStorage(base_dir=tmpdir)
        url = store.get_url("images/avatar.png")
        assert url == "/api/storage/file/images/avatar.png"
        print(f"  ✓ TC2.4: LocalStorage.get_url → {url}")


def test_local_storage_path_traversal():
    """TC2.5: LocalStorage 路径穿越防护"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = LocalStorage(base_dir=tmpdir)
        try:
            store._abs_path("../../etc/passwd")
            assert False, "路径穿越应被拒绝"
        except ValueError:
            print("  ✓ TC2.5: LocalStorage 路径穿越防护生效")


# ===================================================================
# TC3: AliyunOSSStorage 配置缺失
# ===================================================================

def test_oss_fallback():
    """TC3: AliyunOSSStorage 缺少配置时 available=False"""
    # 清除 OSS 环境变量
    for k in ["OSS_ACCESS_KEY_ID", "OSS_ACCESS_KEY_SECRET", "OSS_BUCKET", "OSS_ENDPOINT"]:
        os.environ.pop(k, None)

    oss = AliyunOSSStorage()
    assert oss.available is False, "缺少配置时 available 应为 False"
    print("  ✓ TC3: OSS 缺少配置 → available=False")


def test_get_storage_backend_fallback():
    """TC3.1: get_storage_backend 在 OSS 不可用时返回 LocalStorage"""
    for k in ["OSS_ACCESS_KEY_ID", "OSS_ACCESS_KEY_SECRET", "OSS_BUCKET", "OSS_ENDPOINT"]:
        os.environ.pop(k, None)

    backend = get_storage_backend()
    assert isinstance(backend, LocalStorage), "应 fallback 到 LocalStorage"
    print("  ✓ TC3.1: get_storage_backend fallback → LocalStorage")


# ===================================================================
# TC4: validate_file 类型检查
# ===================================================================

def test_validate_file_allowed():
    """TC4.1: 允许的文件类型通过校验"""
    for ct in ["image/jpeg", "image/png", "application/pdf"]:
        try:
            validate_file(ct, "test.jpg", 1024)
        except ValueError:
            assert False, f"应允许 {ct}"
    print("  ✓ TC4.1: 允许的文件类型通过校验")


def test_validate_file_denied():
    """TC4.2: 不允许的文件类型拒绝"""
    denied = ["application/zip", "video/mp4", "application/x-msdownload"]
    for ct in denied:
        try:
            validate_file(ct, "test.zip", 1024)
            assert False, f"应拒绝 {ct}"
        except ValueError:
            pass
    print("  ✓ TC4.2: 不允许的文件类型被拒绝")


def test_validate_file_size_exceeded():
    """TC4.3: 文件大小超限报错"""
    try:
        validate_file("image/jpeg", "big.jpg", MAX_FILE_SIZE + 1)
        assert False, "应拒绝超限文件"
    except ValueError as e:
        assert "超过限制" in str(e)
        print(f"  ✓ TC4.3: 文件大小超限 → {e}")


# ===================================================================
# TC5: generate_storage_path
# ===================================================================

def test_generate_storage_path():
    """TC5: 生成安全的存储路径"""
    path = generate_storage_path("my photo.jpg", subdir="user_avatars")
    assert path.startswith("user_avatars/")
    assert path.endswith(".jpg")
    assert "my photo" not in path  # 原始文件名不应保留
    print(f"  ✓ TC5: generate_storage_path → {path}")


def test_generate_storage_path_no_subdir():
    """TC5.1: 无子目录时返回平级路径"""
    path = generate_storage_path("document.pdf")
    assert "/" not in path
    assert path.endswith(".pdf")
    assert len(path) == 16 + 4  # 16 hex chars + .pdf
    print(f"  ✓ TC5.1: generate_storage_path (无子目录) → {path}")


# ===================================================================
# TC6: 集成测试 — FastAPI 路由
# ===================================================================

def test_upload_endpoint():
    """TC6: POST /api/storage/upload — 文件上传集成测试"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    # 创建一个合法的测试文件
    file_content = b"fake image content"
    response = client.post(
        "/api/storage/upload",
        files={"file": ("test_image.png", file_content, "image/png")},
        data={"subdir": ""},
    )
    assert response.status_code == 201, f"上传应返回 201，实际: {response.status_code} {response.text}"
    data = response.json()
    assert "url" in data
    assert "path" in data
    assert data["path"].endswith(".png")
    print(f"  ✓ TC6: POST /api/storage/upload → {data['path']}")


def test_upload_invalid_type():
    """TC6.1: POST /api/storage/upload — 非法文件类型报 422"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    response = client.post(
        "/api/storage/upload",
        files={"file": ("virus.exe", b"bad content", "application/x-msdownload")},
    )
    assert response.status_code == 422, f"非法类型应返回 422，实际: {response.status_code}"
    print(f"  ✓ TC6.1: POST /api/storage/upload 非法类型 → 422")


def test_upload_exceed_size():
    """TC6.2: POST /api/storage/upload — 超限文件报 422"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    big_content = b"x" * (MAX_FILE_SIZE + 1)
    response = client.post(
        "/api/storage/upload",
        files={"file": ("big.jpg", big_content, "image/jpeg")},
    )
    assert response.status_code == 422, f"超限文件应返回 422，实际: {response.status_code}"
    print(f"  ✓ TC6.2: POST /api/storage/upload 超限 → 422")


def test_get_url_endpoint():
    """TC7: GET /api/storage/{path} — 获取文件 URL"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/storage/test/some_image.png")
    assert response.status_code == 200, f"应返回 200，实际: {response.status_code}"
    data = response.json()
    assert "url" in data
    assert "path" in data
    print(f"  ✓ TC7: GET /api/storage/test.png → {data['url']}")


def test_delete_endpoint():
    """TC8: DELETE /api/storage/{path} — 删除文件"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    # 先上传再删除
    response = client.post(
        "/api/storage/upload",
        files={"file": ("del_test.png", b"delete me", "image/png")},
    )
    assert response.status_code == 201
    path = response.json()["path"]

    # 删除
    del_resp = client.delete(f"/api/storage/{path}")
    assert del_resp.status_code == 200, f"删除应返回 200，实际: {del_resp.status_code}"
    assert del_resp.json()["success"] is True
    print(f"  ✓ TC8: DELETE /api/storage/{path} → success")


def test_delete_nonexistent():
    """TC8.1: DELETE 不存在文件返回 404"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    response = client.delete("/api/storage/nonexistent_file.xyz")
    assert response.status_code == 404
    print("  ✓ TC8.1: DELETE 不存在文件 → 404")


# ===================================================================
# Main
# ===================================================================

if __name__ == "__main__":
    print("=" * 50)
    print("链客宝 — 文件存储模块测试")
    print("=" * 50)

    tests = [
        test_abstract_base_class,
        test_local_storage_upload,
        test_local_storage_delete,
        test_local_storage_delete_missing,
        test_local_storage_get_url,
        test_local_storage_path_traversal,
        test_oss_fallback,
        test_get_storage_backend_fallback,
        test_validate_file_allowed,
        test_validate_file_denied,
        test_validate_file_size_exceeded,
        test_generate_storage_path,
        test_generate_storage_path_no_subdir,
        test_upload_endpoint,
        test_upload_invalid_type,
        test_upload_exceed_size,
        test_get_url_endpoint,
        test_delete_endpoint,
        test_delete_nonexistent,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ✗ {test.__name__}: FAILED — {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print()
    print("=" * 50)
    print(f"结果: {passed} 通过, {failed} 失败, 共 {len(tests)} 测试用例")
    print("=" * 50)
    sys.exit(1 if failed > 0 else 0)
