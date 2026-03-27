"""OpenTelemetry 분산 추적 초기화 모듈.

TracerProvider + OTLP Exporter + FastAPI auto-instrumentation을 구성한다.
Jaeger/OTel Collector가 접근 불가능한 환경에서는 graceful하게 건너뛴다.
"""

import structlog

logger = structlog.get_logger(__name__)


def init_tracing(
    service_name: str = "propai-api",
    otlp_endpoint: str = "http://localhost:4318",
    sample_rate: float = 1.0,
) -> bool:
    """OpenTelemetry TracerProvider를 초기화한다.

    Returns:
        True: 초기화 성공
        False: 초기화 건너뜀 (패키지 미설치 등)
    """
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
    except ImportError:
        logger.info("opentelemetry 패키지 미설치 — 분산 추적 비활성화")
        return False

    try:
        resource = Resource.create({"service.name": service_name})
        sampler = TraceIdRatioBased(sample_rate)
        provider = TracerProvider(resource=resource, sampler=sampler)

        exporter = OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces")
        provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)
        logger.info("OpenTelemetry 초기화 완료", service=service_name, endpoint=otlp_endpoint, sample_rate=sample_rate)
        return True
    except Exception as e:
        logger.warning("OpenTelemetry 초기화 실패 — 분산 추적 비활성화", error=str(e))
        return False


def instrument_fastapi(app) -> bool:
    """FastAPI 앱에 자동 계측을 적용한다."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
        logger.info("FastAPI 자동 계측 활성화")
        return True
    except ImportError:
        logger.info("fastapi instrumentation 패키지 미설치 — 건너뜀")
        return False
    except Exception as e:
        logger.warning("FastAPI 계측 실패", error=str(e))
        return False
