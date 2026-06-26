"""
链客宝 - 管道包
==============

子模块:
- realtime_sync: 实时增量同步管道（轮询+变更检测+自动重编码）
- minute_indexer: 分钟级增量索引服务 (InMemoryIndex + 自动更新)
"""

from .realtime_sync import (
    RealtimeSyncPipeline,
    SyncStatus,
    DEFAULT_CHECK_INTERVAL,
    DEFAULT_LATENCY_THRESHOLD,
)
from .minute_indexer import (
    InMemoryIndex,
    MinuteIndexer,
    IndexEntry,
    IndexerStatus,
)

__all__ = [
    "RealtimeSyncPipeline",
    "SyncStatus",
    "DEFAULT_CHECK_INTERVAL",
    "DEFAULT_LATENCY_THRESHOLD",
    "InMemoryIndex",
    "MinuteIndexer",
    "IndexEntry",
    "IndexerStatus",
]
