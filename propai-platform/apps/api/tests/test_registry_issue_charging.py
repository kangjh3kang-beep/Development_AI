"""등기 발급 과금이 **성공한 건수만** 청구하는지 잠근다 — 실제 돈이 걸린 분기다.

2026-08-12 실측으로 드러난 결함:

    진단으로 `/registry/bulk` 를 4회 호출 → **전부 실패**
    그런데 원장에 `service_fee -1200` 이 **4건**(23:16~23:18) · 합계 4,800원

원인은 판정이 **블랙리스트**였다는 것이다:

    _issue_failed(result) -> status in ("unavailable","error","failed")

등기 조회의 실제 실패 상태는 `not_configured`·`provider_error`·`no_match`·
`bad_request`·`forbidden` 이라 **하나도 걸리지 않았고**, 실패가 전부 "성공" 으로 읽혔다.

★블랙리스트가 위험한 구조적 이유: **새 실패 상태를 추가하는 사람이 돈 가드를 함께
고쳐야 한다는 것을 모른다.** 실제로 같은 PR 이 `provider_error` 를 새로 만들면서 이 가드를
갱신하지 않았다. 화이트리스트는 "성공을 증명하지 못하면 과금하지 않는다" 라 기본값이 안전하다.

★그래서 이 파일은 **실패 상태를 전수로** 태운다 — 목록에 없는 새 상태가 생겨도
"ok 가 아니면 과금 안 함" 이라는 성질로 자동 보호된다.
"""

from __future__ import annotations

from typing import Any

import pytest

from routers.registry import issued_count


# ★정직하게: 이건 **손수 열거한 표본**이지 코드에서 파생시킨 전수가 아니다.
#   첫 판에는 주석에 "코드에서 파생" 이라고 썼는데 거짓이었고, 실제로 둘을 빠뜨렸다 —
#   `registry_pdf_parser.py:65` 의 `parse_failed`, `tilko_client.py:203` 의 `need_unique_no`.
#   (CLAUDE.md §C-11 — 면역을 거짓 주장하지 마라.)
#   전수 보증은 아래 `test_ok가_아닌_어떤_상태도_과금하지_않는다` 가 담당한다.
def _http_req():
    """slowapi 리미터가 요구하는 **실제** starlette Request.

    ★유료 라우트에 `@limiter.limit(ai_limiter)` 를 붙이면서 핸들러 첫 인자가
      `request: Request` 가 됐다. 이 테스트들은 HTTP 층을 우회해 핸들러를 직접 부르므로
      최소 스코프로 진짜 Request 를 만들어 넘긴다(가짜 객체는 slowapi 가 거부한다).
    ★TestClient 경유로 바꾸지 않는 이유: 리미터가 20/분이라 테스트 수가 늘면
      **레이트리밋 때문에 빨개지는** 플래키가 생긴다 — 과금 판정을 보려는 테스트가
      엉뚱한 이유로 실패하면 진단이 흐려진다.
    """
    from starlette.requests import Request as _R

    return _R({
        "type": "http", "method": "POST", "path": "/",
        "headers": [], "client": ("127.0.0.1", 0), "query_string": b"",
    })

FAILURE_STATUSES = ("not_configured", "provider_error", "no_match", "bad_request", "forbidden",
                    "unavailable", "error", "failed", "parse_failed", "need_unique_no")


@pytest.mark.parametrize("status", FAILURE_STATUSES)


def test_실패는_한_건도_과금하지_않는다(status: str) -> None:
    assert issued_count({"status": status, "message": "…"}) == 0, (
        f"status={status!r} 가 과금 대상으로 읽힌다 — 실패한 조회에 돈이 청구된다"
    )


@pytest.mark.parametrize("status", ["", "zzz", "OK_", "okay", "OK ", "성공", "ok2"])
def test_ok가_아닌_어떤_상태도_과금하지_않는다(status: str) -> None:
    """★목록이 아니라 **성질**로 잠근다 — 새 실패 상태가 생겨도 자동으로 보호된다.

    발급 근거(`origin`)까지 붙여 놓고도 0이어야 한다: 상태가 `ok` 가 아니면 과금하지 않는다.
    """
    assert issued_count({"status": status, "origin": "hyphen", "has_pdf": True}) == 0, (
        f"status={status!r} 가 성공으로 읽힌다"
    )


def test_성공이지만_발급근거가_없으면_과금하지_않는다() -> None:
    """`status=ok` 만으로는 부족하다 — 어디서 무엇을 받았는지가 있어야 발급이다."""
    assert issued_count({"status": "ok"}) == 0


def test_프로바이더_발급은_과금한다() -> None:
    assert issued_count({"status": "ok", "origin": "hyphen"}) == 1
    assert issued_count({"status": "ok", "origin": "tilko", "has_pdf": True}) == 1


def test_PDF_업로드_파싱은_과금하지_않는다() -> None:
    """외부 발급이 없다 — 사용자가 이미 가진 문서를 읽어 줄 뿐이다."""
    assert issued_count({"status": "ok", "origin": "pdf_upload", "has_pdf": True}) == 0


def test_일괄조회는_성공한_건수만_센다() -> None:
    """★요청 필지 수가 아니라 **발급된 수**다.

    종전에는 `times=len(items)` 로 요청 수만큼 과금해, 10필지 중 1건만 발급돼도
    10건이 청구될 수 있었다.
    """
    bulk = {
        "configured": True,
        "count": 3,
        "results": [
            {"status": "ok", "origin": "hyphen"},
            {"status": "provider_error", "message": "[C0000-002] …"},
            {"status": "not_configured"},
        ],
    }
    assert issued_count(bulk) == 1

    # ★두 모집단을 가른다 — 전부 실패면 0, 전부 성공이면 3.
    all_fail = {"results": [{"status": "provider_error"} for _ in range(3)]}
    all_ok = {"results": [{"status": "ok", "origin": "hyphen"} for _ in range(3)]}
    assert issued_count(all_fail) == 0
    assert issued_count(all_ok) == 3
    assert issued_count(all_fail) != issued_count(all_ok), "차가 0이면 잠금이 아니다"


# ── 캐시 적중(2026-08-15) — **같은 결함 클래스의 두 번째 발생** ───────────────
# ★`RegistryAnalysisService.analyze()` 는 캐시 적중 시 `{**cached, "cached": True}` 를 돌려준다.
#   `status` 는 `"ok"`, `origin` 도 원본 그대로라 **발급 성공과 구별되지 않는다**.
#   `analysis_charged` 는 `cached` 를 보고 건너뛰었는데 `issued_count` 는 **보지 않았다** —
#   같은 파일, 같은 결함 클래스가 두 번째로 났다(2026-08-12 는 블랙리스트 실패판정이었다).
#   실측: 같은 20필지로 `/registry/survey/strategy` 를 두 번 부르면 외부 발급 0건인데
#   두 번째에 24,000원이 청구됐다. 캐시는 DB 영속·세션 공유라 다른 세션에서도 터진다.

def test_캐시_적중은_한_건도_과금하지_않는다() -> None:
    """★캐시 = 외부 발급 없음. `status:"ok"`·`origin:"hyphen"` 이어도 0 이어야 한다."""
    cached = {"status": "ok", "origin": "hyphen", "data": {"x": 1}, "cached": True}
    assert issued_count(cached) == 0, "캐시 적중에 발급료가 재청구된다(외부 발급 0건)"

    # ★두 모집단을 가른다 — 같은 응답에서 `cached` 만 뗀 것은 **1** 이다(차가 0이면 잠금이 아니다).
    fresh = {k: v for k, v in cached.items() if k != "cached"}
    assert issued_count(fresh) == 1
    assert issued_count(cached) != issued_count(fresh)


def test_일괄응답의_캐시_건만_빠지고_신규는_과금된다() -> None:
    """★일괄에서도 **건 단위**로 갈린다 — 통째로 0 이 되거나 통째로 세면 둘 다 틀렸다."""
    bulk = {"results": [
        {"status": "ok", "origin": "hyphen"},                 # 신규 발급 → 1
        {"status": "ok", "origin": "hyphen", "cached": True},  # 캐시 → 0
        {"status": "ok", "origin": "tilko", "cached": True},   # 캐시 → 0
    ]}
    assert issued_count(bulk) == 1, f"캐시 2건이 함께 청구됐다: {issued_count(bulk)}"


def test_발급과_분석_판정이_캐시를_같은_방식으로_본다() -> None:
    """★두 판정이 갈라져 있었다 — 한쪽만 고치면 다음 사람이 반대쪽을 또 놓친다.
    네 모집단(신규ok·캐시ok·실패·빈값)에서 **둘의 판단이 일치**하는지 못박는다."""
    from routers.registry import analysis_charged

    fresh_ok = {"status": "ok", "origin": "hyphen", "ai": {"grade": "A"}}
    cached_ok = {**fresh_ok, "cached": True}
    failed = {"status": "provider_error", "origin": "hyphen", "ai": None}
    empty: dict[str, Any] = {}

    assert (issued_count(fresh_ok), analysis_charged(fresh_ok)) == (1, True)
    assert (issued_count(cached_ok), analysis_charged(cached_ok)) == (0, False)
    assert (issued_count(failed), analysis_charged(failed)) == (0, False)
    assert (issued_count(empty), analysis_charged(empty)) == (0, False)


@pytest.mark.asyncio
async def test_집행_함수도_캐시에는_한_푼도_쓰지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★판정이 아니라 **집행**을 태운다 — 실제로 `charge_service` 가 불리는지 본다.
    (판정만 잠그면 `_charge_registry_issue` 가 판정을 무시하는 변이가 생존한다.)"""
    from routers.registry import _charge_registry_analysis, _charge_registry_issue

    charged = _spy_billing(monkeypatch)
    cached = {"status": "ok", "origin": "hyphen", "ai": {"grade": "A"}, "cached": True}
    await _charge_registry_issue("u1", cached, times=1)
    await _charge_registry_analysis("u1", cached)
    assert charged == [], f"캐시 적중에 {len(charged)}건이 청구됐다: {charged}"

    # ★대조군 — 캐시 표시만 떼면 발급·분석 각 1건이 나간다(차가 0이면 잠금이 아니다).
    fresh = {k: v for k, v in cached.items() if k != "cached"}
    await _charge_registry_issue("u1", fresh, times=1)
    await _charge_registry_analysis("u1", fresh)
    assert charged == ["registry_issue", "registry_analysis"], charged


@pytest.mark.asyncio
async def test_라우트가_실패결과를_과금통로에_그대로_넘긴다(monkeypatch: pytest.MonkeyPatch) -> None:
    """라우트가 **실패 결과를** 과금 통로로 넘기는지까지만 본다.

    ★정직하게: 과금 함수는 여기서 스파이로 대체되므로 **과금 층은 실행되지 않는다**.
    "실패면 돈이 안 나간다" 의 실제 잠금은 아래 `test_집행_함수가_...` 가 담당한다
    (첫 판에는 이 테스트 이름이 "과금을 부르지 않는다" 였는데 단언은 "불렀다" 였다 —
    다음 사람이 이름만 보고 집행 층이 잠겼다고 오독한다).
    """
    import routers.registry as rr

    calls: list[Any] = []

    async def _spy(user_id: Any, result: Any, times: Any = None) -> None:
        calls.append((result or {}).get("status"))

    class _Svc:
        async def get_one(self, **_kw: Any) -> dict[str, Any]:
            return {"status": "provider_error", "message": "[C0000-002] 결과가 없습니다"}

    monkeypatch.setattr(rr, "_charge_registry_issue", _spy)
    monkeypatch.setattr(rr, "RegistryService", _Svc)

    class _U:
        user_id = "u1"
        # ★`CurrentUser` 는 tenant_id 도 갖는다 — 스텁이 실제 계약보다 좁으면,
        #   그 필드를 쓰는 코드가 테스트에서만 터진다(스텁이 실제 층을 우회하는 형태).
        tenant_id = "t1"

    out = await rr.registry_get_one(_http_req(), {"address": "서울특별시 강남구 역삼동 737"}, current_user=_U())
    assert out["status"] == "provider_error"
    # 과금 함수는 호출되되(단일 통로), 그 안에서 0건으로 판정돼야 한다.
    assert calls == ["provider_error"], calls


# ── 판정이 아니라 **집행**을 태운다 ─────────────────────────────────────────
# ★리뷰가 잡은 구멍: `issued_count`(순수 판정)만 잠그고, 그것을 소비해 **실제로 돈을 쓰는**
#   `_charge_registry_issue` 본문은 어떤 테스트도 실행하지 않았다. 이 함수를 언급하던 두
#   테스트는 **둘 다 monkeypatch 로 치워버렸다** — CLAUDE.md §A-1 "스텁이 검증 대상 층을
#   우회" 그 자체다. 그래서 `min` 을 `max` 로 뒤집는 1글자 변이(=10필지 요청 중 1건 성공에
#   12,000원 청구)가 28건 전부 초록인 채 생존했다.

class _FakeSession:
    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *a: Any) -> None:
        return None


def _spy_billing(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """`billing_service.charge_service` **자체**를 세는 스파이를 심는다."""
    import app.core.database as db

    # ★`app.services.billing` 은 패키지고 `billing_service` 는 그 안의 **모듈**이다
    #   (`charge_service` 는 그 모듈의 함수). 패키지 속성으로 접근하면 AttributeError 다 —
    #   실제로 첫 판에서 그렇게 틀렸고, 테스트가 빨개져서 알았다.
    from app.services.billing import billing_service as billing_mod

    charged: list[str] = []

    async def _charge(_db: Any, _uid: Any, code: str) -> dict[str, Any]:
        charged.append(code)
        return {"charged": True, "code": code}

    monkeypatch.setattr(db, "async_session_factory", lambda: _FakeSession())
    monkeypatch.setattr(billing_mod, "charge_service", _charge)
    return charged


@pytest.mark.asyncio
async def test_집행_함수가_실패에는_한_푼도_쓰지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    from routers.registry import _charge_registry_issue

    charged = _spy_billing(monkeypatch)
    await _charge_registry_issue("u1", {"status": "provider_error", "message": "[C0000-002]"}, times=1)
    assert charged == [], f"실패한 조회에 {len(charged)}건이 청구됐다"


@pytest.mark.asyncio
async def test_집행_함수가_성공_한_건에_한_번만_청구한다(monkeypatch: pytest.MonkeyPatch) -> None:
    from routers.registry import _charge_registry_issue

    charged = _spy_billing(monkeypatch)
    await _charge_registry_issue("u1", {"status": "ok", "origin": "hyphen"}, times=1)
    assert charged == ["registry_issue"], charged


@pytest.mark.asyncio
async def test_일괄_10요청_1성공은_한_번만_청구한다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★`min` 을 `max` 로 뒤집으면 여기서 죽는다 — 요청 수(10)만큼 청구되기 때문이다.

    실제로 겪은 사고의 형태다: 요청 필지 수만큼 청구하면 10필지 중 1건만 발급돼도
    12,000원이 나간다(정상 1,200원).
    """
    from routers.registry import _charge_registry_issue

    charged = _spy_billing(monkeypatch)
    bulk = {"results": [{"status": "ok", "origin": "hyphen"}]
                       + [{"status": "provider_error"} for _ in range(9)]}
    await _charge_registry_issue("u1", bulk, times=10)
    assert charged == ["registry_issue"], (
        f"발급 1건인데 {len(charged)}건이 청구됐다 — 요청 수만큼 청구하는 회귀다"
    )


# ── 권리분석 과금(같은 파일 30줄 아래에 살아 있던 동일 결함) ────────────────

def test_분석이_없는_응답은_과금하지_않는다() -> None:
    from routers.registry import analysis_charged

    # 등기부 미확보 — 토지정보만 주고 `ai: None`(registry_analysis_service.py:391,403)
    assert analysis_charged({"status": "not_available", "origin": "none", "ai": None}) is False
    assert analysis_charged({"status": "empty", "origin": "hyphen", "ai": None}) is False
    # 캐시 적중 = 신규 분석 없음
    assert analysis_charged({"status": "ok", "ai": {"grade": "A"}, "cached": True}) is False


def test_분석이_실제로_나오면_과금한다() -> None:
    from routers.registry import analysis_charged

    ok = {"status": "ok", "origin": "hyphen", "ai": {"grade": "A", "risks": []}}
    assert analysis_charged(ok) is True
    # ★두 모집단이 실제로 다른 값을 낸다(차가 0이면 잠금이 아니다).
    assert analysis_charged(ok) != analysis_charged({**ok, "ai": None})


@pytest.mark.asyncio
async def test_분석_집행도_실패에는_쓰지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    from routers.registry import _charge_registry_analysis

    charged = _spy_billing(monkeypatch)
    await _charge_registry_analysis("u1", {"status": "not_available", "ai": None})
    assert charged == [], f"AI 분석이 0인 응답에 {len(charged)}건이 청구됐다"

    await _charge_registry_analysis("u1", {"status": "ok", "ai": {"grade": "A"}})
    assert charged == ["registry_analysis"], charged


@pytest.mark.asyncio
async def test_잡_완료_시점에만_분석_과금이_일어난다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★H2 수정 **그 자체**를 태운다 — 과금을 제출 시점에서 완료 시점으로 옮긴 배선.

    기계 변이가 이 배선(`owner = ...` · `if owner:`)의 생존을 드러냈다: 고친 자리에
    락이 없으면 다음 사람이 되돌려도 아무도 모른다.
    """
    import routers.registry as rr

    charged = _spy_billing(monkeypatch)

    class _Svc:
        result: dict[str, Any] = {}

        async def analyze(self, **_kw: Any) -> dict[str, Any]:
            return type(self).result

    import app.services.registry.registry_analysis_service as ras

    monkeypatch.setattr(ras, "RegistryAnalysisService", _Svc)
    await rr._REGISTRY_STORE.put("job-1", {"status": "pending", "user_id": "u1"}, 60)

    # ── 모집단 A: 등기부 미확보(ai None) → 한 푼도 안 나간다
    _Svc.result = {"status": "not_available", "origin": "none", "ai": None}
    await rr._run_registry_job("job-1", {})
    assert charged == [], f"분석이 0인데 {len(charged)}건 청구됐다"

    # ── 모집단 B: 분석 성공 → 1건
    _Svc.result = {"status": "ok", "origin": "hyphen", "ai": {"grade": "A"}}
    await rr._run_registry_job("job-1", {})
    assert charged == ["registry_analysis"], charged


@pytest.mark.asyncio
async def test_분석_라우트가_분석없는_결과에_과금하지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """라우트 → 판정 → 과금까지 한 줄로 태운다(프로덕션에서 돈이 새던 자리)."""
    import app.services.registry.registry_analysis_service as ras
    import routers.registry as rr

    charged = _spy_billing(monkeypatch)

    class _Svc:
        result: dict[str, Any] = {}

        async def analyze(self, **_kw: Any) -> dict[str, Any]:
            return dict(type(self).result)

    monkeypatch.setattr(ras, "RegistryAnalysisService", _Svc)

    class _U:
        user_id = "u1"
        # ★`CurrentUser` 는 tenant_id 도 갖는다 — 스텁이 실제 계약보다 좁으면,
        #   그 필드를 쓰는 코드가 테스트에서만 터진다(스텁이 실제 층을 우회하는 형태).
        tenant_id = "t1"

    class _Req:
        address = "서울특별시 강남구 역삼동 737"
        pnu = None
        registry_text = None
        realty_type = None
        dong = None
        ho = None
        land_hint = None
        # ★스텁도 계약이다 — 실제 요청 모델에 필드가 늘면 여기도 따라와야 한다.
        #   좁은 스텁은 "그 필드를 쓰는 코드가 테스트에서만 터지는" 형태를 만든다.
        force_reissue = False

    _Svc.result = {"status": "not_available", "ai": None}
    out = await rr.registry_analyze(_http_req(), _Req(), current_user=_U())
    assert charged == [], f"AI 분석이 없는 응답에 {len(charged)}건 청구됐다: {out.get('status')}"
    assert "service_charge" not in out, "과금하지 않았는데 과금 필드를 달면 안 된다"

    _Svc.result = {"status": "ok", "ai": {"grade": "A"}}
    out = await rr.registry_analyze(_http_req(), _Req(), current_user=_U())
    assert charged == ["registry_analysis"], charged
    assert out.get("service_charge"), f"과금 결과가 응답에 실려야 한다: {out}"
