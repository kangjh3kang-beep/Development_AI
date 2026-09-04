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
from app.services.registry import registry_service as rsvc


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
    svc._FAILURE_MEMO.clear()
    rsvc._ISSUE_CACHE.clear()
    # DB 캐시는 이 테스트 환경에 없다 — 조회/저장이 예외를 삼키고 None 을 준다(무영향).
    yield
    svc._ANALYZE_CACHE.clear()
    svc._SOURCE_CACHE.clear()
    svc._FAILURE_MEMO.clear()
    rsvc._ISSUE_CACHE.clear()


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


@pytest.mark.asyncio
class TestIssuanceLayerReuse:
    """★유료 길목(`RegistryService.get_one`) 자체의 재사용 — 형제 스윕에서 나왔다.

    위층(분석 서비스)에만 재사용을 넣으면 **`/registry/bulk` 가 남는다**. 그 경로는 필지마다
    `get_one` 을 그대로 부르고 캐시가 없어, 일괄 조회를 두 번 누르면 두 번 과금된다
    (`registry_service.bulk` 실측). 그래서 길목 하나에 넣어 모든 호출부가 따라오게 했다.
    """

    @pytest.fixture
    def counted(self, monkeypatch):
        calls: list[dict] = []

        async def _fake(self, **kw):
            calls.append(kw)
            return {"status": "ok", "registry_text": "【갑구】소유자 홍길동", "origin": "hyphen"}

        monkeypatch.setattr(rsvc.RegistryService, "_issue_uncached", _fake, raising=True)
        return calls

    async def test_전제_발급기가_불린다(self, counted, addr):
        await rsvc.RegistryService().get_one(address=addr)
        assert len(counted) == 1

    async def test_핵심_같은_물건은_두_번_발급하지_않는다(self, counted, addr):
        s = rsvc.RegistryService()
        await s.get_one(address=addr)
        second = await s.get_one(address=addr)
        assert len(counted) == 1, f"발급이 {len(counted)}번 나갔다 — 민원캐시가 두 번 차감된다"
        assert second["reused_issue"] is True

    async def test_핵심_bulk_재실행이_재발급하지_않는다(self, counted, addr):
        s = rsvc.RegistryService()
        items = [{"address": f"{addr} {i}"} for i in range(3)]
        await s.bulk(items)
        await s.bulk(items)
        assert len(counted) == 3, f"일괄 조회 2회에 발급이 {len(counted)}번 나갔다(3이어야 한다)"

    async def test_동_호가_다르면_다른_물건이다(self, counted, addr):
        s = rsvc.RegistryService()
        await s.get_one(address=addr, realty_type="1", dong="101", ho="101")
        await s.get_one(address=addr, realty_type="1", dong="101", ho="102")
        assert len(counted) == 2

    async def test_force_reissue_는_새로_발급한다(self, counted, addr):
        s = rsvc.RegistryService()
        await s.get_one(address=addr)
        await s.get_one(address=addr, force_reissue=True)
        assert len(counted) == 2

    async def test_발급_실패는_보관하지_않는다(self, monkeypatch, addr):
        calls: list[dict] = []

        async def _fail(self, **kw):
            calls.append(kw)
            return {"status": "error", "message": "민원캐시 잔액이 부족합니다"}

        monkeypatch.setattr(rsvc.RegistryService, "_issue_uncached", _fail, raising=True)
        s = rsvc.RegistryService()
        await s.get_one(address=addr)
        await s.get_one(address=addr)
        assert len(calls) == 2

    async def test_업로드_PDF_경로는_캐시를_타지_않는다(self, monkeypatch, addr):
        """사용자가 올린 파일은 **무과금**이다 — 캐시로 묶으면 다른 파일이 옛 결과를 받는다."""
        calls: list[dict] = []

        async def _fake(self, **kw):
            calls.append(kw)
            return {"status": "ok", "registry_text": "업로드본"}

        monkeypatch.setattr(rsvc.RegistryService, "_issue_uncached", _fake, raising=True)
        s = rsvc.RegistryService()
        await s.get_one(address=addr, pdf_input=b"%PDF-1")
        await s.get_one(address=addr, pdf_input=b"%PDF-2")
        assert len(calls) == 2


@pytest.mark.asyncio
class TestDeterministicFailureIsNotRePurchased:
    """★같은 실패를 **다시 사지 않는다** — 등기 재발급 누수와 같은 얼굴, 축만 다르다(LLM 토큰).

    실패한 분석은 캐시하지 않는다(자가치유). 그 설계는 **결정론적** 실패에서 대가를 치른다 —
    같은 문서가 같은 이유로 계속 실패하는데 **볼 때마다 LLM 을 다시 산다.**
    긴 등기부의 응답 절단(`parse`)이 실측 사례다.

    ★일시 실패는 **절대 기억하지 않는다**(타임아웃·과부하·잔액). 기억하면 회복을 막는다.
    """

    @pytest.fixture
    def llm_calls(self, monkeypatch):
        calls: list[str] = []
        return calls

    def _fail_with(self, monkeypatch, calls, exc_factory):
        async def _fail(self, address, registry):
            calls.append(address or "")
            from app.services.ai.llm_failure import classify_failure, failure_reason
            e = exc_factory()
            return {
                "generated": False, "summary": "분석 불가", "safety_grade": "주의",
                "failure_reason": failure_reason(e),
                "failure_class": classify_failure(e),
            }
        monkeypatch.setattr(svc.RegistryAnalysisService, "_llm", _fail, raising=True)

    async def test_핵심_결정론적_실패는_LLM_을_다시_사지_않는다(self, issuance, monkeypatch, addr, llm_calls):
        import json as _json
        self._fail_with(monkeypatch, llm_calls,
                        lambda: _json.JSONDecodeError("Unterminated string", "{", 1))
        s = svc.RegistryAnalysisService()
        first = await s.analyze(address=addr)
        second = await s.analyze(address=addr)

        assert len(llm_calls) == 1, f"LLM 을 {len(llm_calls)}번 샀다 — 같은 실패에 매번 토큰을 태운다"
        assert first["ai"]["generated"] is False
        assert second["ai"]["generated"] is False
        # ★시도하지 않았음을 밝힌다 — 안 하고 한 척하면 그 자체가 거짓이다.
        assert second["ai"].get("remembered_failure") is True
        assert not first["ai"].get("remembered_failure")

    async def test_핵심_일시적_실패는_기억하지_않는다_회복을_막지_않게(self, issuance, monkeypatch, addr, llm_calls):
        self._fail_with(monkeypatch, llm_calls, lambda: TimeoutError("timed out"))
        s = svc.RegistryAnalysisService()
        await s.analyze(address=addr)
        await s.analyze(address=addr)
        assert len(llm_calls) == 2, "일시 실패를 기억하면 회복해도 영영 재시도되지 않는다"

    async def test_핵심_회복되면_성공한다_기억이_길을_막지_않는다(self, issuance, monkeypatch, addr, llm_calls):
        self._fail_with(monkeypatch, llm_calls, lambda: TimeoutError("timed out"))
        s = svc.RegistryAnalysisService()
        await s.analyze(address=addr)

        async def _ok(self, address, registry):
            llm_calls.append(address or "")
            return {"generated": True, "summary": "정상", "safety_grade": "안전"}
        monkeypatch.setattr(svc.RegistryAnalysisService, "_llm", _ok, raising=True)
        healed = await s.analyze(address=addr)
        assert healed["ai"]["generated"] is True

    async def test_force_reissue_는_기억도_건너뛴다(self, issuance, monkeypatch, addr, llm_calls):
        import json as _json
        self._fail_with(monkeypatch, llm_calls,
                        lambda: _json.JSONDecodeError("Unterminated string", "{", 1))
        s = svc.RegistryAnalysisService()
        await s.analyze(address=addr)
        await s.analyze(address=addr, force_reissue=True)
        assert len(llm_calls) == 2, "기억에 갇히면 근본을 고쳐도 사용자가 못 빠져나온다"

    async def test_대조군_다른_필지는_따로_기억한다(self, issuance, monkeypatch, addr, llm_calls):
        import json as _json
        self._fail_with(monkeypatch, llm_calls,
                        lambda: _json.JSONDecodeError("Unterminated string", "{", 1))
        s = svc.RegistryAnalysisService()
        await s.analyze(address=addr)
        await s.analyze(address=addr + " 다른필지")
        assert len(llm_calls) == 2
