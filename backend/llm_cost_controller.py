"""LLM Cost Controller 存根 — 零依赖轻量级Token消耗监控（占位实现）"""


class CostController:
    """轻量级 Token 消耗监控控制器（存根）"""

    def __init__(self):
        self._total_tokens = 0
        self._total_cost = 0.0

    def record(self, tokens: int, model: str = "unknown") -> None:
        """记录 Token 消耗"""
        self._total_tokens += tokens
        # 按简单费率估算成本
        rates = {
            "gpt-4": 0.03,
            "gpt-3.5-turbo": 0.002,
            "deepseek": 0.001,
            "unknown": 0.01,
        }
        rate = rates.get(model, rates["unknown"])
        self._total_cost += (tokens / 1000) * rate

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    @property
    def total_cost(self) -> float:
        return round(self._total_cost, 6)

    def reset(self) -> None:
        self._total_tokens = 0
        self._total_cost = 0.0


_instance = None


def get_cost_controller() -> CostController:
    """获取全局 CostController 单例"""
    global _instance
    if _instance is None:
        _instance = CostController()
    return _instance
