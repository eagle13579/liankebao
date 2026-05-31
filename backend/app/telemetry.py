"""
OpenTelemetry 全链路追踪模块
=============================
链客宝 APM 可观测性核心 — 符合 OpenTelemetry 规范

功能:
- FastAPI 自动请求追踪 (FastAPIInstrumentor)
- SQLAlchemy 数据库查询追踪
- 自定义业务 Span（支付/名片生成/匹配/搜索）
- 多后端导出：控制台(调试) / Jaeger / Grafana Tempo / 阿里云ARMS

环境变量:
    OTEL_EXPORTER_OTLP_ENDPOINT   — OTLP gRPC 端点 (默认: None → console)
    OTEL_EXPORTER_OTLP_HEADERS    — 认证头 (如 "Authorization=Bearer xxx")
    OTEL_SERVICE_VERSION          — 服务版本 (默认: 1.0.0)
    OTEL_SERVICE_NAME             — 服务名 (默认: chainke-backend)
    OTEL_TRACES_SAMPLER           — 采样器 (parentbased_traceidratio)
    OTEL_TRACES_SAMPLER_ARG       — 采样率 (默认: 1.0 = 100%)

使用示例:
    from app.telemetry import tracer, init_telemetry, close_telemetry
    with tracer.start_as_current_span("my_business_op") as span:
        span.set_attribute("key", "value")
"""

import logging
import os

logger = logging.getLogger(__name__)

# ============================================================
# 全局 tracer 引用（惰性初始化，供业务模块 import）
# ============================================================
_tracer = None
_tracer_provider = None
_instrumentors = []


def get_tracer():
    """获取全局 tracer 实例"""
    global _tracer
    if _tracer is None:
        from opentelemetry import trace

        _tracer = trace.get_tracer(__name__)
    return _tracer


tracer = get_tracer()  # 模块级，业务代码直接 from app.telemetry import tracer


# ============================================================
# 初始化
# ============================================================
def init_telemetry():
    """
    初始化 OpenTelemetry SDK

    根据环境变量 OTEL_EXPORTER_OTLP_ENDPOINT 判断导出目标:
    - 未设置或无端点 → 控制台导出 (ConsoleSpanExporter, 调试模式)
    - 设置端点 → OTLP gRPC 导出 (Jaeger / Tempo / ARMS)
    """
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    global _tracer_provider, _tracer

    service_name = os.environ.get("OTEL_SERVICE_NAME", "chainke-backend")
    service_version = os.environ.get("OTEL_SERVICE_VERSION", "1.0.0")
    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()

    # 构建资源属性
    resource = Resource.create(
        attributes={
            "service.name": service_name,
            "service.version": service_version,
            "deployment.environment": os.environ.get("ENV", os.environ.get("APP_ENV", "development")),
        }
    )

    # 创建 TracerProvider
    provider = TracerProvider(resource=resource)

    if otlp_endpoint:
        # ===== OTLP 远程导出模式 =====
        logger.info(f"OpenTelemetry OTLP 导出已启用 → {otlp_endpoint}")
        _init_otlp_exporter(provider)
    else:
        # ===== 控制台调试模式 =====
        logger.info("OpenTelemetry 控制台导出模式 (调试) — 设置 OTEL_EXPORTER_OTLP_ENDPOINT 启用远程导出")
        console_exporter = ConsoleSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(console_exporter))

    # 设置全局 TraceProvider
    trace.set_tracer_provider(provider)
    _tracer_provider = provider

    # 刷新模块级 tracer
    _tracer = trace.get_tracer(__name__)

    # 注册自动 instrumentors
    _register_instrumentors(provider)

    logger.info(f"OpenTelemetry 已初始化: service={service_name}, version={service_version}")
    return provider


def _init_otlp_exporter(provider):
    """配置 OTLP gRPC 导出器"""
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    otlp_headers = os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "").strip()

    kwargs = {"endpoint": otlp_endpoint}
    if otlp_headers:
        kwargs["headers"] = otlp_headers

    exporter = OTLPSpanExporter(**kwargs)
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)


def _register_instrumentors(provider):
    """注册自动 instrumentors"""
    global _instrumentors

    # -- FastAPI 自动追踪 --
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        _instrumentors.append(("fastapi", FastAPIInstrumentor))
        logger.debug("FastAPIInstrumentor 已注册")
    except ImportError as e:
        logger.warning(f"FastAPIInstrumentor 不可用: {e}")

    # -- SQLAlchemy 数据库追踪 --
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        _instrumentors.append(("sqlalchemy", SQLAlchemyInstrumentor))
        logger.debug("SQLAlchemyInstrumentor 已注册")
    except ImportError as e:
        logger.warning(f"SQLAlchemyInstrumentor 不可用: {e}")


def instrument_fastapi(app):
    """
    在 FastAPI app 实例上挂载 FastAPIInstrumentor

    须在 app 创建后、路由注册前或后调用均可。
    推荐在 main.py 中 app = FastAPI(...) 之后调用。
    """
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
    logger.info("FastAPIInstrumentor 已挂载到 app")


def instrument_sqlalchemy(engine):
    """
    在 SQLAlchemy engine 上挂载 SQLAlchemyInstrumentor

    调用时机: engine 创建后立即挂载。
    若 engine 在 database.py 中创建，在 database.py 末尾调用本函数。
    """
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    SQLAlchemyInstrumentor().instrument(engine=engine)
    logger.info("SQLAlchemyInstrumentor 已挂载到 engine")


# ============================================================
# 关闭
# ============================================================
def close_telemetry():
    """关闭 OpenTelemetry SDK，刷新所有未导出的 Span"""
    global _tracer_provider

    if _tracer_provider is not None:
        try:
            _tracer_provider.shutdown()
            logger.info("OpenTelemetry SDK 已关闭")
        except Exception as e:
            logger.warning(f"OpenTelemetry 关闭异常: {e}")


# ============================================================
# 辅助: 在任意路由函数内创建自定义 Span
# ============================================================
def span_from_headers(headers: dict) -> object:
    """
    从 HTTP 请求头中提取远程上下文（用于跨服务传播）

    用法:
        from app.telemetry import span_from_headers
        ctx = span_from_headers(dict(request.headers))
        with tracer.start_as_current_span("op", context=ctx):
            ...
    """
    from opentelemetry.trace.propagation import tracecontext

    carrier = {}
    for key, value in headers.items():
        if key.lower().startswith("traceparent") or key.lower().startswith("tracestate"):
            carrier[key.lower()] = value

    ctx = tracecontext.TraceContextTextMapPropagator().extract(carrier=carrier)
    return ctx
