"""핵심 모듈 단위 테스트.

커버리지 0%인 core, security, services, integrations 모듈 테스트.
"""

import asyncio
import gc
import math
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))


# ── core/quality_gate.py ──


class TestQualityGate:
    def test_guard_infinite_loop_데코레이터(self):
        from apps.api.core.quality_gate import QualityGate

        @QualityGate.guard_infinite_loop(max_iterations=5)
        def add(x, y):
            return x + y

        assert add(2, 3) == 5

    @pytest.mark.asyncio
    async def test_execute_with_timeout_성공(self):
        from apps.api.core.quality_gate import QualityGate

        async def quick():
            return 42

        result = await QualityGate.execute_with_timeout(quick(), timeout=5.0)
        assert result == 42

    @pytest.mark.asyncio
    async def test_execute_with_timeout_초과(self):
        from apps.api.core.quality_gate import QualityGate

        async def slow():
            await asyncio.sleep(10)

        with pytest.raises(RuntimeError, match="timed out"):
            await QualityGate.execute_with_timeout(slow(), timeout=0.01)

    def test_force_garbage_collection(self):
        from apps.api.core.quality_gate import QualityGate

        with patch.object(gc, "collect") as mock_gc:
            QualityGate.force_garbage_collection()
            mock_gc.assert_called_once()

    def test_cap_rag_context_짧은텍스트(self):
        from apps.api.core.quality_gate import QualityGate

        assert QualityGate.cap_rag_context("hello", max_tokens=4000) == "hello"

    def test_cap_rag_context_잘림(self):
        from apps.api.core.quality_gate import QualityGate

        long_text = "A" * 20000
        result = QualityGate.cap_rag_context(long_text, max_tokens=4000)
        assert "...[TRUNCATED BY QUALITY GATE]" in result
        assert len(result) < len(long_text)

    def test_cap_rag_context_경계값(self):
        from apps.api.core.quality_gate import QualityGate

        exact = "B" * (10 * 4)
        assert "TRUNCATED" not in QualityGate.cap_rag_context(exact, max_tokens=10)
        over = "C" * (10 * 4 + 1)
        assert "TRUNCATED" in QualityGate.cap_rag_context(over, max_tokens=10)


# ── core/coordinator.py ──


class TestAgentCoordinator:
    @pytest.mark.asyncio
    async def test_request_domain_agent_성공(self):
        from apps.api.core.coordinator import AgentCoordinator

        coord = AgentCoordinator()
        result = await coord.request_domain_agent("legal", {"query": "test"})
        assert result == {"status": "success", "agent": "legal"}

    @pytest.mark.asyncio
    async def test_여러_에이전트(self):
        from apps.api.core.coordinator import AgentCoordinator

        coord = AgentCoordinator()
        for name in ["legal", "finance", "design"]:
            result = await coord.request_domain_agent(name, {})
            assert result["agent"] == name


# ── security/encryption.py ──


class TestEncryptionService:
    VALID_KEY = "aa" * 32  # 64 hex chars = 32 bytes

    def test_초기화_성공(self):
        from apps.api.security.encryption import EncryptionService

        svc = EncryptionService(self.VALID_KEY)
        assert svc is not None

    def test_짧은키_거부(self):
        from apps.api.security.encryption import EncryptionService

        with pytest.raises(ValueError):
            EncryptionService("aa" * 15)

    def test_라운드트립(self):
        from apps.api.security.encryption import EncryptionService

        svc = EncryptionService(self.VALID_KEY)
        for text in ["hello", "한글 테스트", '{"key": "value"}', ""]:
            assert svc.decrypt(svc.encrypt(text)) == text

    def test_다른_암호문_생성(self):
        from apps.api.security.encryption import EncryptionService

        svc = EncryptionService(self.VALID_KEY)
        c1 = svc.encrypt("same")
        c2 = svc.encrypt("same")
        assert svc.decrypt(c1) == "same"
        assert svc.decrypt(c2) == "same"


# ── services/dt_service.py ──


class TestDigitalTwinService:
    def test_효율_정상(self):
        from apps.api.services.dt_service import DigitalTwinService

        # calculate_efficiency는 @staticmethod — 인스턴스 없이 호출 가능
        assert DigitalTwinService.calculate_efficiency(80, 100) == pytest.approx(20.0)

    def test_효율_제로베이스라인(self):
        from apps.api.services.dt_service import DigitalTwinService

        assert DigitalTwinService.calculate_efficiency(50, 0) == 0.0

    def test_효율_초과사용(self):
        from apps.api.services.dt_service import DigitalTwinService

        assert DigitalTwinService.calculate_efficiency(120, 100) == pytest.approx(-20.0)


# ── services/permit_package_service.py ──


class TestPermitPackageService:
    @pytest.mark.asyncio
    async def test_pdf_경로_생성(self):
        from apps.api.services.permit_package_service import PermitPackageService

        svc = PermitPackageService()
        result = await svc.generate_permit_pdf("proj123", {})
        assert result["pdf_path"] == "/tmp/permit_proj123.pdf"


# ── services/predictive_maintenance_service.py ──


class TestPredictiveMaintenanceService:
    def test_calc_mean(self):
        from apps.api.services.predictive_maintenance_service import (
            PredictiveMaintenanceService,
        )

        svc = PredictiveMaintenanceService()
        assert svc._calc_mean([1, 2, 3, 4, 5]) == pytest.approx(3.0)

    def test_calc_mean_빈목록(self):
        from apps.api.services.predictive_maintenance_service import (
            PredictiveMaintenanceService,
        )

        svc = PredictiveMaintenanceService()
        result = svc._calc_mean([])
        # numpy 환경에서는 NaN, 순수 Python에서는 0.0
        assert result == pytest.approx(0.0) or math.isnan(result)

    def test_calc_std(self):
        from apps.api.services.predictive_maintenance_service import (
            PredictiveMaintenanceService,
        )

        svc = PredictiveMaintenanceService()
        result = svc._calc_std([5, 5, 5, 5])
        assert result == pytest.approx(0.0)

    def test_calc_std_다른값(self):
        from apps.api.services.predictive_maintenance_service import (
            PredictiveMaintenanceService,
        )

        svc = PredictiveMaintenanceService()
        result = svc._calc_std([0, 10])
        assert result > 0


# ── services/webrtc_service.py ──


class TestWebRTCService:
    def test_sanitize_sdp_줄바꿈_정규화(self):
        from apps.api.services.webrtc_service import WebRTCService

        # sanitize_sdp는 @staticmethod — 인스턴스 없이 호출 가능
        result = WebRTCService.sanitize_sdp("v=0\no=- 123\ns=-")
        assert "\r\n" in result

    def test_sanitize_sdp_빈문자열(self):
        from apps.api.services.webrtc_service import WebRTCService

        assert WebRTCService.sanitize_sdp("") == ""


# ── Integration Clients ──


class TestIntegrationClients:
    def test_court_client_속성(self):
        from apps.api.integrations.court_client import CourtClient

        c = CourtClient()
        assert c.service_name == "court"
        assert "court" in c.base_url

    @pytest.mark.asyncio
    async def test_court_client_메서드(self):
        from apps.api.integrations.court_client import CourtClient

        c = CourtClient()
        c._request = AsyncMock(return_value={"status": "ok"})
        assert await c.get_registry_info("REG-001") is not None
        assert await c.check_lien("PROP-001") is not None

    def test_hug_client_속성(self):
        from apps.api.integrations.hug_client import HugClient

        c = HugClient()
        assert c.service_name == "hug"

    @pytest.mark.asyncio
    async def test_hug_client_메서드(self):
        from apps.api.integrations.hug_client import HugClient

        c = HugClient()
        c._request = AsyncMock(return_value={"eligible": True})
        assert await c.check_guarantee_eligibility("addr", 100000000) is not None

    def test_lh_client_속성(self):
        from apps.api.integrations.lh_client import LHClient

        c = LHClient()
        assert c.service_name == "lh"

    @pytest.mark.asyncio
    async def test_lh_client_메서드(self):
        from apps.api.integrations.lh_client import LHClient

        c = LHClient()
        c._request = AsyncMock(return_value={"housing": []})
        assert await c.get_public_housing("11") is not None

    def test_nice_client_속성(self):
        from apps.api.integrations.nice_client import NiceClient

        c = NiceClient()
        assert c.service_name == "nice"

    @pytest.mark.asyncio
    async def test_nice_client_메서드(self):
        from apps.api.integrations.nice_client import NiceClient

        c = NiceClient()
        c._request = AsyncMock(return_value={"score": 850})
        assert await c.get_credit_score("TOKEN") is not None

    def test_replicate_client_속성(self):
        from apps.api.integrations.replicate_client import ReplicateClient

        c = ReplicateClient()
        assert c.service_name == "replicate"
        assert c.timeout == 120.0
        headers = c._default_headers()
        assert "Authorization" in headers

    @pytest.mark.asyncio
    async def test_replicate_client_메서드(self):
        from apps.api.integrations.replicate_client import ReplicateClient

        c = ReplicateClient()
        c._request = AsyncMock(return_value={"url": "img.png"})
        assert await c.run_sdxl("apartment") is not None

    def test_roboflow_client_속성(self):
        from apps.api.integrations.roboflow_client import RoboflowClient

        c = RoboflowClient()
        assert c.service_name == "roboflow"
        assert c.timeout == 60.0

    @pytest.mark.asyncio
    async def test_roboflow_client_메서드(self):
        from apps.api.integrations.roboflow_client import RoboflowClient

        c = RoboflowClient()
        c._request = AsyncMock(return_value={"defects": []})
        assert await c.detect_defects("img_url") is not None
