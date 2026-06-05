"""链客宝 → AI匹配引擎 HTTP调用适配层

替换: from matching_engine import MatchEngine
改用: requests.post("http://localhost:5090/api/v1/match", ...)

使用方法:
    from app.services.matching_client import MatchingClient
    client = MatchingClient()
    results = client.match(product_data, need_data, user_id=123)
"""
import os, json, logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    logger.warning("requests not installed, matching client disabled")


class MatchingClient:
    """AI匹配引擎HTTP客户端"""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.base_url = base_url or os.environ.get(
            "MATCHING_ENGINE_URL", "http://localhost:5090"
        )
        self.api_key = api_key or os.environ.get(
            "MATCHING_ENGINE_API_KEY", "dev-key-change-in-production"
        )
        self._headers = {"X-API-Key": self.api_key, "Content-Type": "application/json"}
        self._timeout = int(os.environ.get("MATCHING_ENGINE_TIMEOUT", "5"))

    def match(self, product: dict, need: dict, top_k: int = 10, user_id: Optional[int] = None) -> list:
        """调用匹配引擎"""
        if not HAS_REQUESTS:
            logger.error("requests not installed, cannot call matching engine")
            return []

        payload = {"product": product, "need": need, "top_k": top_k}
        if user_id:
            payload["user_id"] = str(user_id)

        try:
            resp = requests.post(
                f"{self.base_url}/api/v1/match",
                json=payload,
                headers=self._headers,
                timeout=self._timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("data", [])
            else:
                logger.error(f"Match API error: {resp.status_code} {resp.text[:200]}")
                return []
        except requests.Timeout:
            logger.error(f"Matching engine timeout ({self._timeout}s)")
            return []
        except requests.ConnectionError:
            logger.error(f"Cannot connect to matching engine at {self.base_url}")
            return []
        except Exception as e:
            logger.error(f"Match API failed: {e}")
            return []

    def feedback(self, product_id: int, action: str, user_id: Optional[int] = None) -> bool:
        """记录反馈"""
        if not HAS_REQUESTS:
            return False
        try:
            payload = {"product_id": product_id, "action": action}
            if user_id:
                payload["user_id"] = str(user_id)
            resp = requests.post(
                f"{self.base_url}/api/v1/feedback",
                json=payload,
                headers=self._headers,
                timeout=self._timeout,
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Feedback failed: {e}")
            return False

    def health(self) -> dict:
        """健康检查"""
        if not HAS_REQUESTS:
            return {"status": "error", "message": "requests not installed"}
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=3)
            return resp.json() if resp.status_code == 200 else {"status": "error"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
