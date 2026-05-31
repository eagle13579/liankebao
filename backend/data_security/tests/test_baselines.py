"""数据安全模块 — baselines 子目录结构验证测试"""

import json
import os

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BASELINES = os.path.join(_BASE, "baselines")


class TestBaselinesStructure:
    """验证 baselines/ 目录下的基线数据文件"""

    def test_baselines_dir_exists(self):
        assert os.path.isdir(_BASELINES)

    def test_baselines_has_json_files(self):
        files = [f for f in os.listdir(_BASELINES) if f.endswith(".json")]
        assert len(files) > 0, "baselines/ 目录应包含 JSON 文件"

    def test_baselines_json_valid(self):
        """验证所有 JSON 文件可解析"""
        files = [f for f in os.listdir(_BASELINES) if f.endswith(".json")]
        for fname in files:
            path = os.path.join(_BASELINES, fname)
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            assert isinstance(data, (dict, list)), f"{fname} 应为 JSON 对象/数组"

    def test_baselines_mod_tbl_json(self):
        """验证 mod.tbl.json 结构"""
        path = os.path.join(_BASELINES, "mod.tbl.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            assert isinstance(data, dict), "mod.tbl.json 应为对象"
