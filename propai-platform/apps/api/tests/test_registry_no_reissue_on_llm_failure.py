"""이미 발급받은 등기부는 **다시 발급하지 않는다** — 민원캐시 재차감 차단.

【실측이 만든 요구 — 2026-08-24】
분석 캐시(`_cache_success`)는 **성공만** 저장한다. LLM 해석이 실패하면 캐시 미스가 되고
다음 시도가 `RegistryService.get_one()` 을 다시 부른다. 그 층에는 캐시가 없다
(`registry_service.py` 에 cache 참조 0건 — 실측). 즉 **등기부가 다시 발급되고 선불 잔액이
다시 차감된다.** 사용자에게는 1,200원을 안 받지만(`analysis_charged` 가 막는다)
**벤더 민원캐시는 탄다** — 실제로 잔액이 말라 발급이 전면 중단된 적이 있다.

`app/core/charge_idempotency.py` 는 자기 근거로 *"읽기는 기존 캐시가 흡수하므로 외부 발급이
다시 나가지도 않는다"* 고 적어 두었다. **실패 경로에서 그 전제가 깨져 있었다.**

【이 스위트가 세는 것】
문구가 아니라 **발급 호출 횟수**다. 돈이 걸린 것은 그것뿐이다.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.services.registry import registry_analysis_service as svc


@pytest_asyncio.fixture
async def addr():
    """★테스트마다 **다른 필지 주소**를 쓰고, 끝나면 남긴 행을 지운다.

    캐시 키는 주소에서 파생되고 이 저장소의 캐시는 **인메모리 + DB 영속** 두 층이다.
    같은 주소를 쓰면 앞 테스트(또는 **앞선 실행**)가 DB 에 심어 둔 행을 읽어 첫 호출부터
    캐시 적중이 나고, "발급 0회"가 성공처럼 보인다 — 실제로 그렇게 한 번 속았다.
    창을 비우는 것으로는 부족하고 **키 자체를 격리**해야 한다.

    ★정리는 **teardown 에서 무조건**. 본문 끝에 두면 실패한 테스트가 잔재를 남기고,
      그 잔재가 다음 실행의 캐시 적중이 되어 "발급 0회"를 거짓으로 만든다.
    ★동기 픽스처로 두면 안 된다 — 실행 중 루프 안에서 teardown 이 돌아 정리가 조용히
      건너뛰어졌다(실측: 잔재 20행). 같은 루프에서 await 한다.
    """
    a = f"테스트시 테스트동 {uuid.uuid4().hex[:12]}"
    yield a
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await db.execute(
                text("DELETE FROM registry_analysis_cache WHERE key LIKE :p"), {"p": f"%{a}%"})
            await db.commit()
    except Exception:  # noqa: BLE001 — DB 없는 환경에서는 할 일이 없다
        pass


@pytest.fixture(autouse=True)
def _clean_caches(monkeypatch):
    """프로세스 전역 캐시를 매 테스트마다 비운다(다른 테스트의 잔재가 결과를 뒤집는다)."""
    svc._ANALYZE_CACHE.clear()
    svc._SOURCE_CACHE.clear()
    # DB 캐시는 이 테스트 환경에 없다 — 조회/저장이 예외를 삼키고 None 을 준다(무영향).
    yield
    svc._ANALYZE_CACHE.clear()
    svc._SOURCE_CACHE.clear()


class _Counter:
    """발급 호출 횟수를 센다. 반환은 항상 '성공한 발급'."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def get_one(self, **kw):
        self.calls.append(kw)
        return {
            "status": "ok",
            "registry_text": "【갑구】소유자 홍길동\n【을구】근저당권설정 채권최고액 금120,000,000원",
            "origin": "hyphen",
            "owner": "홍길동",
            "has_pdf": True,
        }


@pytest.fixture
def issuance(monkeypatch):
    c = _Counter()

    class _FakeService:
        def __init__(self, *a, **k):
            pass

        async def get_one(self, **kw):
            return await c.get_one(**kw)

    monkeypatch.setattr(
        "app.services.registry.registry_service.RegistryService", _FakeService, raising=True
    )
    # 공부 조회는 이 테스트의 대상이 아니다 — 고정값으로 고정해 잡음을 없앤다.
    monkeypatch.setattr(svc.RegistryAnalysisService, "_land_info",
                        lambda self, a, p: _async_value({"pnu": "1111"}), raising=True)
    return c


def _async_value(v):
    async def _c():
        return v
    return _c()


def _llm_always_fails(monkeypatch):
    async def _fail(self, address, registry):
        return {
            "generated": False,
            "summary": "분석 불가",
            "safety_grade": "주의",
            "failure_reason": "JSONDecodeError: Unterminated string",
        }
    monkeypatch.setattr(svc.RegistryAnalysisService, "_llm", _fail, raising=True)


def _llm_always_ok(monkeypatch):
    async def _ok(self, address, registry):
        return {"generated": True, "summary": "정상", "safety_grade": "안전",
                "ownership": {"current_owner": "홍길동"}}
    monkeypatch.setattr(svc.RegistryAnalysisService, "_llm", _ok, raising=True)


@pytest.mark.asyncio
class TestNoReissue:
    async def test_전제_발급기가_실제로_불린다(self, issuance, monkeypatch, addr):
        """대조군 — 카운터가 올라갈 수 있음을 먼저 증명한다(0건이 부재가 아님을 가른다)."""
        _llm_always_fails(monkeypatch)
        await svc.RegistryAnalysisService().analyze(address=addr)
        assert len(issuance.calls) == 1

    async def test_핵심_해석이_실패해도_두_번째_시도는_재발급하지_않는다(self, issuance, monkeypatch, addr):
        _llm_always_fails(monkeypatch)
        s = svc.RegistryAnalysisService()
        first = await s.analyze(address=addr)
        second = await s.analyze(address=addr)

        assert len(issuance.calls) == 1, (
            f"등기부가 {len(issuance.calls)}번 발급됐다 — 재시도마다 민원캐시가 차감된다"
        )
        # 자가치유는 그대로 — 해석은 다시 돌았고, 결과도 여전히 실패로 정직하게 나온다.
        assert first["ai"]["generated"] is False
        assert second["ai"]["generated"] is False
        assert second["ai"]["failure_reason"]

    async def test_핵심_재사용_사실과_발급시각을_응답에_싣는다(self, issuance, monkeypatch, addr):
        _llm_always_fails(monkeypatch)
        s = svc.RegistryAnalysisService()
        first = await s.analyze(address=addr)
        second = await s.analyze(address=addr)

        assert not (first.get("fetched") or {}).get("reused_issue")
        assert (second.get("fetched") or {}).get("reused_issue") is True
        assert (second.get("fetched") or {}).get("issued_at"), "언제 발급분인지 말하지 않는다"

    async def test_핵심_해석이_회복되면_재발급_없이_성공한다(self, issuance, monkeypatch, addr):
        """자가치유의 핵심 — 저장된 발급본으로 해석만 다시 돌린다."""
        _llm_always_fails(monkeypatch)
        s = svc.RegistryAnalysisService()
        await s.analyze(address=addr)
        _llm_always_ok(monkeypatch)
        healed = await s.analyze(address=addr)

        assert len(issuance.calls) == 1
        assert healed["ai"]["generated"] is True
        assert healed["status"] == "ok"

    async def test_다른_필지는_당연히_새로_발급한다(self, issuance, monkeypatch, addr):
        """대조군 — 캐시가 필지를 뭉개면 남의 등기부를 보여 주게 된다."""
        _llm_always_fails(monkeypatch)
        s = svc.RegistryAnalysisService()
        await s.analyze(address=addr)
        await s.analyze(address=addr + " 다른필지")
        assert len(issuance.calls) == 2

    async def test_동_호가_다르면_다른_물건이다(self, issuance, monkeypatch, addr):
        _llm_always_fails(monkeypatch)
        s = svc.RegistryAnalysisService()
        await s.analyze(address=addr, realty_type="1", dong="101", ho="101")
        await s.analyze(address=addr, realty_type="1", dong="101", ho="102")
        assert len(issuance.calls) == 2

    async def test_핵심_force_reissue_는_캐시를_건너뛰고_새로_발급한다(self, issuance, monkeypatch, addr):
        """굳어붙지 않게 하는 탈출구 — 없으면 쓸모없는 발급본에 7일간 갇힌다."""
        _llm_always_fails(monkeypatch)
        s = svc.RegistryAnalysisService()
        await s.analyze(address=addr)
        await s.analyze(address=addr, force_reissue=True)
        assert len(issuance.calls) == 2

    async def test_발급_자체가_실패하면_보관하지_않는다(self, monkeypatch, addr):
        """받은 게 없으면 재시도가 새로 발급하는 것이 옳다(빈 결과를 굳히지 않는다)."""
        calls = []

        class _Failing:
            def __init__(self, *a, **k):
                pass

            async def get_one(self, **kw):
                calls.append(kw)
                return {"status": "error", "message": "민원캐시 잔액이 부족합니다"}

        monkeypatch.setattr(
            "app.services.registry.registry_service.RegistryService", _Failing, raising=True
        )
        monkeypatch.setattr(svc.RegistryAnalysisService, "_land_info",
                            lambda self, a, p: _async_value(None), raising=True)
        s = svc.RegistryAnalysisService()
        r1 = await s.analyze(address=addr)
        await s.analyze(address=addr)
        assert len(calls) == 2
        assert r1["status"] == "error"
        assert "잔액" in (r1.get("message") or "")
