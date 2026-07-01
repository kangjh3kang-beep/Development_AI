"""강화 헬스체크 + Prometheus + 구조화 로깅 테스트."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── HealthCheckService ──────────────────────────────────────

class TestHealthCheckService:
    """HealthCheckService 테스트."""

    @pytest.mark.asyncio
    async def test_check_all_healthy(self):
        from app.core.health import HealthCheckService
        svc = HealthCheckService()
        result = await svc.check_all()
        assert result["status"] == "healthy"
        assert result["component_count"] == 3

    @pytest.mark.asyncio
    async def test_check_database(self):
        from app.core.health import HealthCheckService
        svc = HealthCheckService()
        result = await svc.check_component("database")
        assert result is not None
        assert result["status"] == "healthy"
        assert result["name"] == "database"

    @pytest.mark.asyncio
    async def test_check_redis(self):
        from app.core.health import HealthCheckService
        svc = HealthCheckService()
        result = await svc.check_component("redis")
        assert result is not None
        assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_check_unknown_component(self):
        from app.core.health import HealthCheckService
        svc = HealthCheckService()
        result = await svc.check_component("nonexistent")
        assert result is None

    def test_registered_checks(self):
        from app.core.health import HealthCheckService
        svc = HealthCheckService()
        checks = svc.registered_checks
        assert "database" in checks
        assert "redis" in checks
        assert "external_api" in checks

    @pytest.mark.asyncio
    async def test_custom_check_registration(self):
        from app.core.health import ComponentHealth, ComponentStatus, HealthCheckService
        svc = HealthCheckService()
        async def custom_check():
            return ComponentHealth(name="custom", status=ComponentStatus.HEALTHY, message="OK")
        svc.register_check("custom", custom_check)
        result = await svc.check_component("custom")
        assert result["status"] == "healthy"


# ── PrometheusMetrics ───────────────────────────────────────

class TestPrometheusMetrics:
    """PrometheusMetrics 테스트."""

    def test_initial_state(self):
        from app.core.prometheus import PrometheusMetrics
        pm = PrometheusMetrics()
        assert pm.total_requests == 0
        assert pm.total_errors == 0
        assert pm.active_connections == 0

    def test_record_request(self):
        from app.core.prometheus import PrometheusMetrics
        pm = PrometheusMetrics()
        pm.record_request("GET", "/api/v1/test", 200, 0.05)
        assert pm.total_requests == 1
        assert pm.total_errors == 0

    def test_record_error(self):
        from app.core.prometheus import PrometheusMetrics
        pm = PrometheusMetrics()
        pm.record_request("POST", "/api/v1/fail", 500, 1.0)
        assert pm.total_errors == 1

    def test_connections_gauge(self):
        from app.core.prometheus import PrometheusMetrics
        pm = PrometheusMetrics()
        pm.inc_connections()
        pm.inc_connections()
        assert pm.active_connections == 2
        pm.dec_connections()
        assert pm.active_connections == 1

    def test_custom_gauge(self):
        from app.core.prometheus import PrometheusMetrics
        pm = PrometheusMetrics()
        pm.set_gauge("queue_size", 42.0)
        assert pm.get_gauge("queue_size") == 42.0

    def test_get_metrics_format(self):
        from app.core.prometheus import PrometheusMetrics
        pm = PrometheusMetrics(namespace="test")
        pm.record_request("GET", "/health", 200, 0.01)
        text = pm.get_metrics()
        assert "test_http_requests_total" in text
        assert "test_active_connections" in text

    def test_latency_stats(self):
        from app.core.prometheus import PrometheusMetrics
        pm = PrometheusMetrics()
        pm.record_request("GET", "/api", 200, 0.1)
        pm.record_request("GET", "/api", 200, 0.2)
        stats = pm.get_latency_stats("GET", "/api", 200)
        assert stats["count"] == 2
        assert stats["avg"] > 0

    def test_reset(self):
        from app.core.prometheus import PrometheusMetrics
        pm = PrometheusMetrics()
        pm.record_request("GET", "/x", 200, 0.01)
        pm.reset()
        assert pm.total_requests == 0

    def test_summary(self):
        from app.core.prometheus import PrometheusMetrics
        pm = PrometheusMetrics()
        pm.record_request("GET", "/a", 200, 0.01)
        summary = pm.get_summary()
        assert summary["total_requests"] == 1
        assert "unique_endpoints" in summary


# ── StructuredLogger ────────────────────────────────────────

class TestStructuredLogger:
    """StructuredLogger 테스트."""

    def test_info_log(self):
        from app.core.structured_logging import StructuredLogger
        logger = StructuredLogger()
        entry = logger.info("테스트 메시지")
        assert entry is not None
        assert entry["level"] == "INFO"
        assert entry["message"] == "테스트 메시지"

    def test_debug_filtered_by_default(self):
        from app.core.structured_logging import StructuredLogger
        logger = StructuredLogger(min_level="INFO")
        entry = logger.debug("디버그 메시지")
        assert entry is None

    def test_error_log(self):
        from app.core.structured_logging import StructuredLogger
        logger = StructuredLogger()
        entry = logger.error("에러 발생", code=500)
        assert entry["level"] == "ERROR"
        assert entry["code"] == 500

    def test_bind_context(self):
        from app.core.structured_logging import StructuredLogger
        logger = StructuredLogger()
        logger.bind(request_id="req-123", tenant_id="t-001")
        entry = logger.info("바인딩 테스트")
        assert entry["request_id"] == "req-123"
        assert entry["tenant_id"] == "t-001"

    def test_unbind_context(self):
        from app.core.structured_logging import StructuredLogger
        logger = StructuredLogger()
        logger.bind(key="value")
        logger.unbind("key")
        entry = logger.info("언바인딩 후")
        assert "key" not in entry

    def test_log_request(self):
        from app.core.structured_logging import StructuredLogger
        logger = StructuredLogger()
        entry = logger.log_request("GET", "/api/v1/test", 200, 15.5)
        assert entry["method"] == "GET"
        assert entry["status_code"] == 200
        assert entry["duration_ms"] == 15.5

    def test_to_json(self):
        import json

        from app.core.structured_logging import StructuredLogger
        logger = StructuredLogger()
        entry = logger.info("JSON 테스트")
        json_str = logger.to_json(entry)
        parsed = json.loads(json_str)
        assert parsed["message"] == "JSON 테스트"

    def test_entry_count(self):
        from app.core.structured_logging import StructuredLogger
        logger = StructuredLogger()
        logger.info("하나")
        logger.warning("둘")
        assert logger.entry_count == 2

    def test_get_entries_by_level(self):
        from app.core.structured_logging import StructuredLogger
        logger = StructuredLogger()
        logger.info("인포")
        logger.error("에러")
        errors = logger.get_entries_by_level("ERROR")
        assert len(errors) == 1

    def test_generate_request_id(self):
        from app.core.structured_logging import StructuredLogger
        rid = StructuredLogger.generate_request_id()
        assert rid.startswith("req-")
        assert len(rid) == 16


# ── CSRF ────────────────────────────────────────────────────

class TestCSRFProtection:
    """CSRF 보호 테스트."""

    def test_generate_token(self):
        from app.core.csrf import CSRFProtection
        csrf = CSRFProtection()
        token = csrf.generate_token()
        assert len(token.split(".")) == 3

    def test_validate_valid_token(self):
        from app.core.csrf import CSRFProtection
        csrf = CSRFProtection()
        token = csrf.generate_token()
        assert csrf.validate_token(token) is True

    def test_validate_invalid_token(self):
        from app.core.csrf import CSRFProtection
        csrf = CSRFProtection()
        assert csrf.validate_token("invalid.token.data") is False

    def test_validate_tampered_token(self):
        from app.core.csrf import CSRFProtection
        csrf = CSRFProtection()
        token = csrf.generate_token()
        parts = token.split(".")
        parts[0] = "tampered" + parts[0][8:]
        tampered = ".".join(parts)
        assert csrf.validate_token(tampered) is False

    def test_double_submit_valid(self):
        from app.core.csrf import CSRFProtection
        csrf = CSRFProtection()
        token = csrf.generate_token()
        assert csrf.validate_double_submit(token, token) is True

    def test_double_submit_mismatch(self):
        from app.core.csrf import CSRFProtection
        csrf = CSRFProtection()
        token1 = csrf.generate_token()
        token2 = csrf.generate_token()
        assert csrf.validate_double_submit(token1, token2) is False

    def test_double_submit_missing(self):
        from app.core.csrf import CSRFProtection
        csrf = CSRFProtection()
        token = csrf.generate_token()
        assert csrf.validate_double_submit(None, token) is False
        assert csrf.validate_double_submit(token, None) is False

    def test_cookie_config(self):
        from app.core.csrf import CSRFProtection
        csrf = CSRFProtection()
        config = csrf.cookie_config
        assert config["samesite"] == "strict"
        assert config["secure"] is True


# ── API Versioning ──────────────────────────────────────────

class TestAPIVersionRouter:
    """API 버전 라우터 테스트."""

    def test_latest_redirect(self):
        from app.core.api_versioning import APIVersionRouter
        router = APIVersionRouter()
        target, should = router.resolve_path("/api/latest/projects")
        assert should is True
        assert target == "/api/v2/projects"

    def test_no_redirect_v1(self):
        from app.core.api_versioning import APIVersionRouter
        router = APIVersionRouter()
        target, should = router.resolve_path("/api/v1/projects")
        assert should is False

    def test_version_info(self):
        from app.core.api_versioning import APIVersionRouter
        router = APIVersionRouter()
        info = router.get_version_info()
        assert info["latest"] == "v2"
        assert "v1" in info["supported"]

    def test_v1_is_deprecated(self):
        from app.core.api_versioning import APIVersionRouter
        router = APIVersionRouter()
        assert router.is_deprecated("v1") is True
        assert router.is_deprecated("v2") is False

    def test_custom_latest_version(self):
        from app.core.api_versioning import APIVersionRouter
        router = APIVersionRouter(latest_version="v3")
        target, should = router.resolve_path("/api/latest/test")
        assert target == "/api/v3/test"
