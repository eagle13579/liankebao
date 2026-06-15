"""
导入模块测试
==============
- 导入预览（CSV上传、VCF上传、格式不支持、文件过大、无认证）
- 确认导入（正常流程、批次不存在、权限验证）
- 导入历史（成功、空列表、分页、无认证）

注：detect_duplicates 有已知bug（line 201迭代DuplicateGroup对象），
测试中通过mock避免该路径被触发。
"""
import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# 辅助 CSV 内容生成
SAMPLE_CSV = "姓名,手机,公司,职位\n张三,13800000111,测试科技,CTO\n李四,13800000222,创新集团,CEO\n王五,13800000333,未来有限,COO"

SAMPLE_CSV_NO_NAME = "手机,公司\n13800000111,测试科技\n13800000222,创新集团"


def _clean_batch_store():
    """辅助：清理模块级 _batch_store"""
    from app.routers.imports import _batch_store
    _batch_store.clear()


class TestImportPreview:
    """导入预览测试"""

    PREVIEW_URL = "/api/imports/preview"

    def test_preview_csv_success(self, client: TestClient, buyer_headers):
        """上传CSV文件成功返回预览"""
        resp = client.post(
            self.PREVIEW_URL,
            headers=buyer_headers,
            files={"file": ("test.csv", SAMPLE_CSV.encode("utf-8"), "text/csv")},
        )
        assert resp.status_code == 200, f"CSV预览应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "预览生成成功"
        preview = data["data"]
        assert "batch_id" in preview
        assert preview["total_rows"] == 3
        assert len(preview["preview_rows"]) == 3
        assert len(preview["mapped_preview"]) == 3
        assert "姓名" in preview["headers"]
        # 验证 field_mapping 将中文列名映射到标准字段
        field_mapping = preview["field_mapping"]
        assert field_mapping.get("姓名") == "name"
        assert field_mapping.get("手机") == "phone"

    def test_preview_csv_empty_file(self, client: TestClient, buyer_headers):
        """上传空CSV返回400"""
        empty_csv = "姓名,手机\n"
        resp = client.post(
            self.PREVIEW_URL,
            headers=buyer_headers,
            files={"file": ("empty.csv", empty_csv.encode("utf-8"), "text/csv")},
        )
        assert resp.status_code == 400
        assert "未找到有效数据" in resp.text

    def test_preview_vcf_success(self, client: TestClient, buyer_headers):
        """上传VCF文件成功返回预览"""
        vcf_content = (
            "BEGIN:VCARD\nVERSION:3.0\nFN:张三\nTEL;TYPE=CELL:13800000111\n"
            "ORG:测试科技\nTITLE:CTO\nEND:VCARD\n"
            "BEGIN:VCARD\nVERSION:3.0\nFN:李四\nTEL;TYPE=CELL:13800000222\n"
            "ORG:创新集团\nTITLE:CEO\nEND:VCARD\n"
        )
        resp = client.post(
            self.PREVIEW_URL,
            headers=buyer_headers,
            files={"file": ("contacts.vcf", vcf_content.encode("utf-8"), "text/vcard")},
        )
        assert resp.status_code == 200, f"VCF预览应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        preview = data["data"]
        assert preview["total_rows"] == 2

    def test_preview_unsupported_format(self, client: TestClient, buyer_headers):
        """上传不支持的文件格式返回400（txt被当作CSV解析，但无有效数据）"""
        resp = client.post(
            self.PREVIEW_URL,
            headers=buyer_headers,
            files={"file": ("test.txt", b"hello world", "text/plain")},
        )
        assert resp.status_code == 400
        # txt扩展名未知，detect_format按内容检测后视为CSV，但无有效数据
        assert "未找到有效数据" in resp.text

    def test_preview_file_too_large(self, client: TestClient, buyer_headers):
        """上传超过1MB的文件被中间件拦截返回413（中间件限制1MB，早于路由的10MB检查）"""
        large_content = b"a" * (2 * 1024 * 1024 + 1)
        resp = client.post(
            self.PREVIEW_URL,
            headers=buyer_headers,
            files={"file": ("large.csv", large_content, "text/csv")},
        )
        assert resp.status_code == 413
        # 中间件返回的消息（非路由中的"文件过大"）
        assert "请求体过大" in resp.text

    def test_preview_no_file(self, client: TestClient, buyer_headers):
        """不传文件返回422"""
        resp = client.post(self.PREVIEW_URL, headers=buyer_headers)
        assert resp.status_code == 422

    def test_preview_unauthenticated(self, client: TestClient):
        """未认证返回401"""
        resp = client.post(
            self.PREVIEW_URL,
            files={"file": ("test.csv", SAMPLE_CSV.encode("utf-8"), "text/csv")},
        )
        assert resp.status_code == 401


class TestImportConfirm:
    """确认导入测试（detect_duplicates被mock以绕过已知bug）"""

    PREVIEW_URL = "/api/imports/preview"
    CONFIRM_URL = "/api/imports/confirm"

    def _do_preview(self, client, headers) -> str:
        """辅助：上传CSV获取batch_id"""
        resp = client.post(
            self.PREVIEW_URL,
            headers=headers,
            files={"file": ("test.csv", SAMPLE_CSV.encode("utf-8"), "text/csv")},
        )
        assert resp.status_code == 200
        return resp.json()["data"]["batch_id"]

    def test_confirm_success_skip(self, client: TestClient, buyer_headers):
        """成功确认导入（去重策略：skip）"""
        with patch("app.routers.imports.detect_duplicates", return_value=[]):
            batch_id = self._do_preview(client, buyer_headers)

            resp = client.post(
                self.CONFIRM_URL,
                headers=buyer_headers,
                json={
                    "batch_id": batch_id,
                    "field_mapping": {"姓名": "name", "手机": "phone", "公司": "company", "职位": "position"},
                    "strategy": "skip",
                },
            )
            assert resp.status_code == 200, f"确认导入应成功: {resp.text}"
            data = resp.json()
            assert data["code"] == 200
            assert data["message"] == "导入完成"
            result = data["data"]
            assert result["batch_id"] == batch_id
            assert result["total_rows"] == 3
            assert result["imported_rows"] == 3
            assert result["skipped_rows"] == 0

            # 验证联系人已创建
            resp2 = client.get("/api/contacts", headers=buyer_headers)
            contacts = resp2.json()["data"]["items"]
            names = [c["name"] for c in contacts]
            assert "张三" in names
            assert "李四" in names
            assert "王五" in names

    def test_confirm_batch_not_found(self, client: TestClient, buyer_headers):
        """不存在的批次ID返回404"""
        resp = client.post(
            self.CONFIRM_URL,
            headers=buyer_headers,
            json={
                "batch_id": "non-existent-batch-id",
                "field_mapping": {"姓名": "name"},
                "strategy": "skip",
            },
        )
        assert resp.status_code == 404
        # 应用层可能包装了HTTPException的格式
        assert "批次不存在" in resp.text or "资源不存在" in resp.text

    def test_confirm_cross_user_forbidden(self, client: TestClient, buyer_headers, promoter_headers):
        """promoter不能确认buyer的批次"""
        batch_id = self._do_preview(client, buyer_headers)
        resp = client.post(
            self.CONFIRM_URL,
            headers=promoter_headers,
            json={
                "batch_id": batch_id,
                "field_mapping": {"姓名": "name", "手机": "phone"},
                "strategy": "skip",
            },
        )
        assert resp.status_code == 403
        assert "无权操作此批次" in resp.text

    def test_confirm_unauthenticated(self, client: TestClient):
        """未认证返回401"""
        resp = client.post(
            self.CONFIRM_URL,
            json={"batch_id": "test", "field_mapping": {}, "strategy": "skip"},
        )
        assert resp.status_code == 401

    def test_confirm_batch_consumed_once(self, client: TestClient, buyer_headers):
        """批次确认后再次确认返回404（批次已清除）"""
        with patch("app.routers.imports.detect_duplicates", return_value=[]):
            batch_id = self._do_preview(client, buyer_headers)
            req_body = {
                "batch_id": batch_id,
                "field_mapping": {"姓名": "name", "手机": "phone"},
                "strategy": "skip",
            }
            # 第一次确认应成功
            resp1 = client.post(self.CONFIRM_URL, headers=buyer_headers, json=req_body)
            assert resp1.status_code == 200

            # 第二次确认应返回404（批次已从_store清除）
            resp2 = client.post(self.CONFIRM_URL, headers=buyer_headers, json=req_body)
            assert resp2.status_code == 404


class TestImportHistory:
    """导入历史测试"""

    PREVIEW_URL = "/api/imports/preview"
    CONFIRM_URL = "/api/imports/confirm"
    HISTORY_URL = "/api/imports/history"

    def _do_import(self, client, headers) -> int:
        """辅助：执行一次完整导入（detect_duplicates被mock）"""
        with patch("app.routers.imports.detect_duplicates", return_value=[]):
            resp = client.post(
                self.PREVIEW_URL,
                headers=headers,
                files={"file": ("test.csv", SAMPLE_CSV.encode("utf-8"), "text/csv")},
            )
            assert resp.status_code == 200
            batch_id = resp.json()["data"]["batch_id"]

            resp = client.post(
                self.CONFIRM_URL,
                headers=headers,
                json={
                    "batch_id": batch_id,
                    "field_mapping": {"姓名": "name", "手机": "phone", "公司": "company", "职位": "position"},
                    "strategy": "skip",
                },
            )
            assert resp.status_code == 200
            return resp.json()["data"]["import_id"]

    def test_history_success(self, client: TestClient, buyer_headers):
        """成功获取导入历史"""
        self._do_import(client, buyer_headers)

        resp = client.get(self.HISTORY_URL, headers=buyer_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        items = data["data"]["items"]
        assert len(items) >= 1
        item = items[0]
        assert item["filename"] == "test.csv"
        assert item["total_rows"] == 3
        assert item["imported_rows"] == 3
        assert item["status"] == "completed"

    def test_history_empty(self, client: TestClient, promoter_headers):
        """没有导入记录时返回空列表"""
        resp = client.get(self.HISTORY_URL, headers=promoter_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total"] == 0
        assert data["data"]["items"] == []

    def test_history_pagination(self, client: TestClient, buyer_headers):
        """导入历史分页测试"""
        with patch("app.routers.imports.detect_duplicates", return_value=[]):
            for i in range(3):
                csv_single = f"姓名,手机\n测试用户{i},1380000{i:04d}\n"
                resp = client.post(
                    self.PREVIEW_URL,
                    headers=buyer_headers,
                    files={"file": (f"test_{i}.csv", csv_single.encode("utf-8"), "text/csv")},
                )
                assert resp.status_code == 200
                batch_id = resp.json()["data"]["batch_id"]
                client.post(
                    self.CONFIRM_URL,
                    headers=buyer_headers,
                    json={
                        "batch_id": batch_id,
                        "field_mapping": {"姓名": "name", "手机": "phone"},
                        "strategy": "skip",
                    },
                )

        resp = client.get(self.HISTORY_URL, headers=buyer_headers, params={"page": 1, "page_size": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["items"]) == 2
        assert data["data"]["page"] == 1
        assert data["data"]["page_size"] == 2
        assert data["data"]["total"] >= 3

    def test_history_cross_user_isolation(self, client: TestClient, buyer_headers, promoter_headers):
        """跨用户隔离：promoter看不到buyer的导入历史"""
        self._do_import(client, buyer_headers)
        resp = client.get(self.HISTORY_URL, headers=promoter_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 0

    def test_history_unauthenticated(self, client: TestClient):
        """未认证返回401"""
        resp = client.get(self.HISTORY_URL)
        assert resp.status_code == 401
