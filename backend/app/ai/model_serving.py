"""
模型推理层 — ModelServingClient
- 本地 MLX 模型推理 (mac mini:192.168.1.233:8000)
- HuggingFace API 推理
- batch_inference 批量推理
- 降级到 sentence-transformers 本地嵌入
"""

import logging
import time
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)


class ModelServingClient:
    """模型推理客户端，支持 MLX / HuggingFace / sentence-transformers 三层降级。"""

    def __init__(
        self,
        mlx_base_url: str = "http://192.168.1.233:8000",
        hf_api_token: Optional[str] = None,
        hf_model_id: str = "sentence-transformers/all-MiniLM-L6-v2",
        st_model_name: str = "all-MiniLM-L6-v2",
        timeout: int = 10,
    ):
        self.mlx_base_url = mlx_base_url.rstrip("/")
        self.hf_api_token = hf_api_token
        self.hf_model_id = hf_model_id
        self.st_model_name = st_model_name
        self.timeout = timeout
        self._st_model = None  # lazy load

    # ── MLX 本地模型 ──────────────────────────────────────────

    def _infer_mlx(self, texts: List[str]) -> Optional[List[List[float]]]:
        """调用本地 MLX 推理服务 (vLLM / llama.cpp 兼容格式)。"""
        try:
            resp = requests.post(
                f"{self.mlx_base_url}/v1/embeddings",
                json={"input": texts, "model": "default"},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            # 兼容多种返回格式
            if "data" in data:
                embeddings = [d["embedding"] for d in sorted(data["data"], key=lambda x: x["index"])]
                return embeddings
            if "embeddings" in data:
                return data["embeddings"]
            logger.warning("MLX 返回格式未知: %s", list(data.keys()))
            return None
        except Exception as e:
            logger.warning("MLX 推理失败 (%s)，尝试降级", e)
            return None

    # ── HuggingFace API ──────────────────────────────────────

    def _infer_hf(self, texts: List[str]) -> Optional[List[List[float]]]:
        """调用 HuggingFace Inference API。"""
        if not self.hf_api_token:
            logger.warning("未配置 HuggingFace API Token，跳过")
            return None
        try:
            headers = {"Authorization": f"Bearer {self.hf_api_token}"}
            payload = {"inputs": texts, "options": {"wait_for_model": True}}
            resp = requests.post(
                f"https://api-inference.huggingface.co/pipeline/feature-extraction/{self.hf_model_id}",
                headers=headers,
                json=payload,
                timeout=self.timeout * 2,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                return data
            return None
        except Exception as e:
            logger.warning("HuggingFace API 推理失败 (%s)，尝试降级", e)
            return None

    # ── 本地 sentence-transformers ────────────────────────────

    def _infer_st(self, texts: List[str]) -> List[List[float]]:
        """本地 sentence-transformers 嵌入（最终降级）。"""
        if self._st_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._st_model = SentenceTransformer(self.st_model_name)
                logger.info("加载 sentence-transformers 模型: %s", self.st_model_name)
            except ImportError:
                logger.error("sentence-transformers 未安装，无法降级")
                raise
        embeddings = self._st_model.encode(texts, show_progress_bar=False)
        return embeddings.tolist()

    # ── 公共接口 ──────────────────────────────────────────────

    def inference(self, text: str) -> List[float]:
        """单条文本 → embedding。自动降级。"""
        embeddings = self.batch_inference([text])
        return embeddings[0]

    def batch_inference(self, texts: List[str]) -> List[List[float]]:
        """批量文本 → embeddings。自动降级 MLX → HF → sentence-transformers。"""
        if not texts:
            return []

        # 1) MLX
        result = self._infer_mlx(texts)
        if result is not None:
            return result

        # 2) HuggingFace API
        result = self._infer_hf(texts)
        if result is not None:
            return result

        # 3) sentence-transformers 本地
        logger.info("降级到 sentence-transformers 本地推理")
        return self._infer_st(texts)

    def health_check(self) -> dict:
        """检查各后端健康状态。"""
        status = {"mlx": False, "hf": False, "st": False}

        # MLX
        try:
            r = requests.get(f"{self.mlx_base_url}/health", timeout=3)
            status["mlx"] = r.ok
        except Exception:
            status["mlx"] = False

        # HF
        if self.hf_api_token:
            status["hf"] = True  # 仅验证 token 存在

        # ST
        try:
            from sentence_transformers import SentenceTransformer
            status["st"] = True
        except ImportError:
            status["st"] = False

        return status
