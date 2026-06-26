"""链客宝 · 数据安全核心模块 (Data Security Core)

七层隔离安全架构，包含：
  - core/       : 核心加密/脱敏/审计逻辑 (Sanitizer, Contract, DWG, AnomalyScorer)
  - wolf/       : 红队/安全对抗 (Data Attack Engine)
  - gate3/      : Gate3 CLI Validator
  - quarantine/ : 检疫区管理器 (Quarantine Manager)
  - tests/      : 单元测试

迁移信息：从旧版链客宝 data_security 迁移至 chainke-full
保持七层隔离逻辑不变，适配 FastAPI + SQLAlchemy 2.0 + Pydantic v2 环境
"""

__version__ = "2.1.0"
