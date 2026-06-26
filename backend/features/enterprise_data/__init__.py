"""
链客宝 - 企业数据 Feature
===========================
整合天眼查、企查查双源企业数据，提供统一的企业信息查询与合并能力。

能力矩阵：
┌──────────────────────┬─────────────────────────────────────────┐
│ 模块                  │ 能力                                    │
├──────────────────────┼─────────────────────────────────────────┤
│ tianyancha_adapter   │ 天眼查 API 适配器（企业信息查询）      │
│ qichacha_adapter     │ 企查查 API 适配器（信用/异常/知产）    │
│ merger               │ 双源数据合并引擎（统一企业画像）        │
│ pipeline_orchestrator│ 多源数据采集管道编排器（同步/调度）    │
│ pipeline_scheduler   │ Cron 风格调度器（纯 Python，零依赖）   │
└──────────────────────┴─────────────────────────────────────────┘

快速开始:
    from backend.features.enterprise_data import (
        TianyanchaAdapter,
        QichachaAdapter,
        EnterpriseDataMerger,
        PipelineOrchestrator,
        PipelineScheduler,
    )

    # 单源查询
    tyc = TianyanchaAdapter()
    info = tyc.get_basic_info("阿里巴巴")
    print(info.legal_person, info.reg_status)

    # 合并查询
    merger = EnterpriseDataMerger()
    profile = merger.merge("阿里巴巴")
    print(profile.legal_person, profile.risk_count)

    # 管道编排
    orch = PipelineOrchestrator()
    result = orch.sync_single_company("阿里巴巴")
    print(result['status'])

    # 定时调度
    sched = PipelineScheduler()
    sched.add_job("sync", orch.schedule_full_sync, interval_minutes=720)
    sched.start()
"""

from .tianyancha_adapter import (
    EnterpriseInfo,
    TianyanchaAdapter,
    create_adapter as create_tyc_adapter,
)
from .qichacha_adapter import (
    QichachaAdapter,
    create_adapter as create_qcc_adapter,
)
from .merger import (
    EnterpriseDataMerger,
    create_merger,
)
from .pipeline_orchestrator import (
    PipelineOrchestrator,
    create_orchestrator,
)
from .pipeline_scheduler import (
    PipelineScheduler,
    create_scheduler,
)

__all__ = [
    "EnterpriseInfo",
    "TianyanchaAdapter",
    "QichachaAdapter",
    "EnterpriseDataMerger",
    "PipelineOrchestrator",
    "PipelineScheduler",
    "create_tyc_adapter",
    "create_qcc_adapter",
    "create_merger",
    "create_orchestrator",
    "create_scheduler",
]

__version__ = "2.1.0"
__author__ = "薄鱼 (数据分析部, API对接专家) + 雍和 (市场部, 数据采集/渠道对接)"
