"""arq 워커 설정 단위 테스트.

apps/worker/main.py의 WorkerSettings 구조 및 태스크 소스 코드 패턴 검증.
"""

from pathlib import Path

# 워커 소스를 직접 읽음 (import 시 Redis/DB 의존성 회피)
_WORKER_BASE = Path(__file__).resolve().parents[2] / "apps" / "worker"
_MAIN_SOURCE = (_WORKER_BASE / "main.py").read_text(encoding="utf-8")

_TASKS_BASE = _WORKER_BASE / "tasks"
_WEBHOOK_SOURCE = (_TASKS_BASE / "webhook_dispatch.py").read_text(encoding="utf-8")
_MLOPS_SOURCE = (_TASKS_BASE / "mlops.py").read_text(encoding="utf-8")
_REPORT_SOURCE = (_TASKS_BASE / "generate_report_pdf.py").read_text(encoding="utf-8")


class TestWorkerSettings:
    """WorkerSettings 구조 검증."""

    def test_redis_settings_in_source(self) -> None:
        """redis_settings가 정의되어 있다."""
        assert "redis_settings" in _MAIN_SOURCE

    def test_redis_from_dsn(self) -> None:
        """RedisSettings.from_dsn을 사용한다."""
        assert "RedisSettings.from_dsn" in _MAIN_SOURCE

    def test_functions_list(self) -> None:
        """functions 목록에 핵심 태스크가 등록되어 있다."""
        assert "functions" in _MAIN_SOURCE
        assert "embed_regulations" in _MAIN_SOURCE
        assert "retrain_avm_model" in _MAIN_SOURCE
        assert "generate_report_pdf" in _MAIN_SOURCE
        assert "dispatch_webhook" in _MAIN_SOURCE

    def test_embed_regulations_registered(self) -> None:
        """embed_regulations 래퍼가 등록되어 있다."""
        assert "embed_regulations" in _MAIN_SOURCE

    def test_parse_large_ifc_registered(self) -> None:
        """parse_large_ifc 래퍼가 등록되어 있다."""
        assert "parse_large_ifc" in _MAIN_SOURCE

    def test_generate_floor_plan_registered(self) -> None:
        """generate_floor_plan 래퍼가 등록되어 있다."""
        assert "generate_floor_plan" in _MAIN_SOURCE

    def test_dispatch_webhook_registered(self) -> None:
        """dispatch_webhook 래퍼가 등록되어 있다."""
        assert "dispatch_webhook" in _MAIN_SOURCE

    def test_max_jobs(self) -> None:
        """max_jobs가 설정되어 있다."""
        assert "max_jobs" in _MAIN_SOURCE

    def test_job_timeout(self) -> None:
        """job_timeout이 설정되어 있다."""
        assert "job_timeout" in _MAIN_SOURCE

    def test_cron_jobs(self) -> None:
        """cron_jobs가 설정되어 있다."""
        assert "cron_jobs" in _MAIN_SOURCE

    def test_on_startup(self) -> None:
        """on_startup 라이프사이클이 정의되어 있다."""
        assert "on_startup" in _MAIN_SOURCE

    def test_on_shutdown(self) -> None:
        """on_shutdown 라이프사이클이 정의되어 있다."""
        assert "on_shutdown" in _MAIN_SOURCE

    def test_retrain_cron_schedule(self) -> None:
        """재학습이 새벽 2시에 스케줄되어 있다."""
        assert "hour=2" in _MAIN_SOURCE


class TestWebhookDispatchTask:
    """웹훅 발송 태스크 소스 패턴 검증."""

    def test_uses_webhook_service(self) -> None:
        """WebhookService를 사용한다."""
        assert "WebhookService" in _WEBHOOK_SOURCE

    def test_accepts_ctx(self) -> None:
        """ctx 매개변수를 받는다 (arq 규약)."""
        assert "ctx: dict" in _WEBHOOK_SOURCE

    def test_dispatches_event(self) -> None:
        """dispatch_event를 호출한다."""
        assert "dispatch_event" in _WEBHOOK_SOURCE

    def test_uses_async_session_local(self) -> None:
        """AsyncSessionLocal을 사용한다 (async_session_factory 아님)."""
        assert "AsyncSessionLocal" in _WEBHOOK_SOURCE
        assert "async_session_factory" not in _WEBHOOK_SOURCE


class TestMLOpsTask:
    """AVM 모델 재학습 태스크 소스 패턴 검증."""

    def test_uses_mlflow(self) -> None:
        """MLflow를 사용한다."""
        assert "mlflow" in _MLOPS_SOURCE

    def test_uses_xgboost(self) -> None:
        """XGBoost를 사용한다."""
        assert "xgb.XGBRegressor" in _MLOPS_SOURCE

    def test_logs_mape(self) -> None:
        """MAPE 메트릭을 기록한다."""
        assert "mape" in _MLOPS_SOURCE

    def test_registers_model(self) -> None:
        """MLflow에 모델을 등록한다."""
        assert "registered_model_name" in _MLOPS_SOURCE

    def test_uses_molit_client(self) -> None:
        """MolitClient로 실거래 데이터를 수집한다."""
        assert "MolitClient" in _MLOPS_SOURCE


class TestReportPdfTask:
    """PDF 보고서 생성 태스크 소스 패턴 검증."""

    def test_uses_reportlab(self) -> None:
        """ReportLab을 사용한다."""
        assert "reportlab" in _REPORT_SOURCE

    def test_uses_minio(self) -> None:
        """MinIO를 사용한다."""
        assert "Minio" in _REPORT_SOURCE

    def test_uses_korean_font(self) -> None:
        """나눔고딕 한글 폰트를 사용한다."""
        assert "NanumGothic" in _REPORT_SOURCE

    def test_creates_structured_pdf(self) -> None:
        """SimpleDocTemplate으로 구조화된 PDF를 생성한다."""
        assert "SimpleDocTemplate" in _REPORT_SOURCE
