"""등기 열람의 두 결함을 잠근다 — 라우트 부재(404)와 원인 오분류.

2026-08-12 프로덕션 라이브 진단으로 드러난 것:

1. **탈출구가 404였다.** 프론트 `RegistryUploadModal` 이 `POST /registry/get-one` 을
   부르는데(2026-07-24 `588ea8ed`) 백엔드에 그 라우트가 **한 번도 없었다**.
   서비스 함수 `RegistryService.get_one(pdf_input=...)` 은 PDF 파서 분기까지 구현돼
   있었으니 **문만 없던 셈**이다. 그리고 조회 실패 메시지가 바로 그 기능을 쓰라고
   안내했다 — 주 경로가 막혔을 때의 탈출구가 함께 막혀 있었다.

2. **원인이 뭉개졌다.** 하이픈은 `[C0000-002] 입력하신 검색조건에 대한 결과가 없습니다`
   라고 답했는데, 사용자에게는 `not_configured` + "API 미설정 또는 장애 발생" 으로
   전달됐다. 자격증명이 멀쩡한데 **시스템 장애로 오인**하게 만들었고, 진짜 단서
   (주소·검색 결과)를 잃게 했다.

★두 검사 모두 **두 모집단을 가른다** — 미설정(정말 키가 없음)과 조회 실패(키는 있는데
상류가 거절)를 다른 입력으로 태워, 한쪽만 통과하는 상태를 잡는다.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.registry import registry_service as rs


def _http_req():
    """slowapi 리미터가 요구하는 **실제** starlette Request.

    ★유료 라우트(`/get-one` 등)에 `@limiter.limit(ai_limiter)` 를 붙이면서 핸들러 첫 인자가
      `request: Request` 가 됐다. 이 테스트는 HTTP 층을 우회해 핸들러를 직접 부르므로
      최소 스코프의 진짜 Request 를 만들어 넘긴다(가짜 객체는 slowapi 가 거부한다).
    ★TestClient 경유로 바꾸지 않는 이유: 리미터가 20/분이라 **레이트리밋 때문에 빨개지는**
      플래키가 생긴다 — 원인 오분류를 보려는 테스트가 엉뚱한 이유로 실패하면 진단이 흐려진다.
    """
    from starlette.requests import Request as _R

    return _R({
        "type": "http", "method": "POST", "path": "/",
        "headers": [], "client": ("127.0.0.1", 0), "query_string": b"",
    })


def _routes() -> set[str]:
    from routers.registry import router

    return {getattr(r, "path", "") for r in router.routes}


def test_비상_PDF_업로드_라우트가_존재한다() -> None:
    """프론트가 부르는 경로가 실제로 열려 있어야 한다.

    ★"서비스 함수가 있다" 는 도달을 뜻하지 않는다 — 3주간 404였던 이유가 정확히 그것이다.
    """
    # ★라우터는 prefix 를 포함해 등록된다(`/registry/get-one`). 접미 비교로 표기 차이를 흡수한다 —
    #   첫 판은 `/get-one` 을 기대해 **코드가 맞는데 테스트가 빨갰다**(위양성).
    paths = _routes()
    assert any(p.endswith("/get-one") for p in paths), (
        f"POST /registry/get-one 라우트가 없다 — 프론트 RegistryUploadModal 이 부르는 경로다. "
        f"현재 경로: {sorted(paths)}"
    )


def test_라우트_목록이_비어있지_않다() -> None:
    """공허진리 가드 — 라우터를 못 읽으면 위 검사가 무의미하게 통과할 수 있다."""
    paths = _routes()
    assert len(paths) >= 8, f"등기 라우트를 {len(paths)}개만 찾았다 — 수집이 실패했을 수 있다: {paths}"


class _StubCfg(dict):
    pass


@pytest.mark.asyncio
async def test_미설정과_조회실패를_다른_상태로_구분한다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★두 모집단을 가른다: 키 없음(not_configured) vs 키는 있는데 상류 거절(provider_error).

    종전에는 **둘 다** `not_configured` 였다. 그래서 "미설정 또는 장애" 라는 한 문장이
    두 경우를 덮었고, 사용자는 자기 주소가 문제인지 시스템이 죽었는지 알 수 없었다.
    """
    monkeypatch.setattr(rs, "_config", lambda: {"provider": "hyphen", "url": "", "key": ""})

    # ── 모집단 A: 자격증명 없음 → not_configured
    import app.services.registry.hyphen_client as hc
    import app.services.registry.tilko_client as tc

    monkeypatch.setattr(hc, "hyphen_ready", lambda: False)
    monkeypatch.setattr(tc, "tilko_ready", lambda: False)
    a = await rs.RegistryService().get_one(address="서울특별시 강남구 역삼동 737")
    assert a["status"] == "not_configured", a
    assert "미설정" in a["message"], a["message"]
    # ★어느 키가 없는지까지 남아야 관리자가 무엇을 설정할지 안다 — 총평만으로는 못 고친다.
    by = {x["provider"]: x for x in a.get("attempts") or []}
    assert set(by) == {"hyphen", "tilko"}, a.get("attempts")
    assert all(x["status"] == "not_configured" for x in by.values()), by
    assert "HYPHEN_HKEY" in (by["hyphen"].get("message") or ""), by["hyphen"]
    assert "TILKO_API_KEY" in (by["tilko"].get("message") or ""), by["tilko"]

    # ── 모집단 B: 자격증명 있음 + 상류가 "결과 없음" → provider_error + 그 사유 전달
    monkeypatch.setattr(hc, "hyphen_ready", lambda: True)

    async def _probe() -> dict[str, Any]:
        return {"access": "ok"}

    async def _by_addr(**_kw: Any) -> dict[str, Any]:
        return {
            "status": "no_match",
            "message": "[C0000-002] 입력하신 검색조건에 대한 결과가 없습니다. 주소확인 후 다시 시도 해 주십시오.",
        }

    monkeypatch.setattr(hc, "probe_api_access", _probe)
    monkeypatch.setattr(hc, "fetch_registry_by_address", _by_addr)

    b = await rs.RegistryService().get_one(address="서울특별시 강남구 역삼동 737")

    assert b["status"] == "provider_error", (
        f"자격증명이 있는데 조회만 실패한 경우를 not_configured 로 뭉개면 안 된다: {b}"
    )
    assert "C0000-002" in b["message"], (
        f"상류가 말한 사유가 사용자 메시지에 실려야 한다: {b['message']}"
    )
    # ★탈출구 안내는 이 PR 의 핵심이다 — 주 경로가 막혔을 때 사용자가 갈 곳을 알려야 한다
    #   (그 탈출구가 3주간 404였고, 실패 메시지는 그걸 쓰라고 안내하고 있었다).
    assert "비상 등기부 PDF 직접 업로드" in b["message"], b["message"]
    assert "비상 등기부 PDF 직접 업로드" in a["message"], a["message"]
    att = [x for x in b.get("attempts") or [] if x.get("provider") == "hyphen"]
    assert att, f"어느 프로바이더가 왜 실패했는지 구조화 필드로도 남아야 한다: {b.get('attempts')}"
    # ★사유 필드까지 본다 — provider 만 보면 status 줄을 지워도 초록이었다(기계 변이 생존).
    assert att[0]["status"] == "no_match", f"상류 상태가 그대로 실려야 한다: {att[0]}"
    assert "C0000-002" in (att[0].get("message") or ""), att[0]

    # ★두 모집단이 실제로 다른 값을 낸다(차가 0이면 잠금이 아니다).
    assert a["status"] != b["status"], "두 경우가 같은 상태를 내면 이 검사는 공허하다"


@pytest.mark.asyncio
async def test_키가_있는데_입력이_부족하면_미설정이라_말하지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★`attempts` 가 비면 판정이 뒤집힌다 — 리뷰가 잡은 구멍.

    `configured_any` 는 **`attempts` 로부터 파생**된다. 그래서 어떤 경로가 아무 것도
    남기지 않으면(=`attempts == []`), 키가 멀쩡해도 `not_configured` 로 떨어져
    관리자에게 **"키를 설정하라"** 는 오진을 낸다.

    여기서 태우는 경로: provider=tilko · 키 있음 · 입력은 `pnu` 뿐(주소·고유번호 없음).
    종전 코드에는 이 경우의 `else` 가 아예 없었다.
    """
    import app.services.registry.hyphen_client as hc
    import app.services.registry.tilko_client as tc

    monkeypatch.setattr(rs, "_config", lambda: {"provider": "tilko", "url": "", "key": ""})
    monkeypatch.setattr(hc, "hyphen_ready", lambda: False)
    monkeypatch.setattr(tc, "tilko_ready", lambda: True)

    out = await rs.RegistryService().get_one(pnu="1168010100107370000")

    assert out["status"] != "not_configured", (
        f"키가 설정돼 있는데 '미설정' 이라 답한다 — attempts 가 비어 판정이 뒤집혔다: {out}"
    )
    # ★hyphen 경로의 같은 입력은 `bad_request` 다(위 조기반환). 프로바이더에 따라 상태가
    #   갈리면 재시도·알림 로직이 잘못 걸린다 — **상류는 호출조차 되지 않았다**.
    assert out["status"] == "bad_request", (
        f"입력이 모자란 것을 '프로바이더 오류' 로 부르면 안 된다: {out['status']}"
    )
    assert out.get("attempts"), f"어느 프로바이더에서 왜 멈췄는지 기록이 없다: {out}"
    assert "미설정" not in out["message"], out["message"]
    # 상태만 잠그면 안내 문구 분기가 무잠금이다(기계 변이가 그 생존을 드러냈다).
    assert "주소 또는 부동산 고유번호가 필요합니다" in out["message"], out["message"]
    assert "PNU" in (out["attempts"][0].get("message") or ""), out["attempts"]


@pytest.mark.asyncio
async def test_하이픈_경로의_조기반환도_attempts를_싣는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """형제 분기다 — tilko 쪽만 고치고 hyphen 쪽을 놓치는 미스윕을 막는다."""
    import app.services.registry.hyphen_client as hc

    monkeypatch.setattr(rs, "_config", lambda: {"provider": "hyphen", "url": "", "key": ""})
    monkeypatch.setattr(hc, "hyphen_ready", lambda: True)

    async def _probe() -> dict[str, Any]:
        return {"access": "ok"}

    monkeypatch.setattr(hc, "probe_api_access", _probe)

    out = await rs.RegistryService().get_one(pnu="1168010100107370000")

    assert out["status"] == "bad_request", out
    assert "attempts" in out, f"조기반환에 attempts 키가 없다 — 소비처가 구분을 못 한다: {out}"
    # 사용자가 **무엇을 해야 하는지**가 이 문장에 있다 — 상태 코드만 잠그면 안내가 비어도 초록이다.
    assert "주소" in out["message"] and "고유번호" in out["message"], out["message"]


@pytest.mark.asyncio
async def test_커스텀_URL_실패도_사유가_응답에_실린다(monkeypatch: pytest.MonkeyPatch) -> None:
    """세 프로바이더를 **같은 규칙**으로 싣는다 — 커스텀만 로그로 새면 같은 결함이 남는다."""
    import httpx

    import app.services.registry.hyphen_client as hc
    import app.services.registry.tilko_client as tc

    monkeypatch.setattr(rs, "_config",
                        lambda: {"provider": "custom", "url": "https://example.invalid/reg", "key": "k"})
    monkeypatch.setattr(hc, "hyphen_ready", lambda: False)
    monkeypatch.setattr(tc, "tilko_ready", lambda: False)

    class _Boom:
        def __init__(self, *a: Any, **k: Any) -> None:
            pass

        async def __aenter__(self) -> _Boom:
            return self

        async def __aexit__(self, *a: Any) -> None:
            return None

        async def post(self, *a: Any, **k: Any) -> Any:
            raise RuntimeError("커스텀 등기 API 502")

    monkeypatch.setattr(httpx, "AsyncClient", _Boom)

    out = await rs.RegistryService().get_one(address="서울특별시 강남구 역삼동 737")

    cus = [x for x in out.get("attempts") or [] if x.get("provider") == "custom"]
    assert cus, f"커스텀 실패가 attempts 에 없다 — 사유가 로그로만 새고 사용자에겐 안 간다: {out.get('attempts')}"
    assert cus[0]["status"] == "provider_error", cus[0]
    assert "502" in out["message"], f"상류 사유가 메시지에 실려야 한다: {out['message']}"


@pytest.mark.asyncio
async def test_라우트가_모든_입력을_서비스에_그대로_넘긴다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★배선 락 — 프론트가 보낸 값이 서비스까지 도달하는지.

    기계 변이가 `pnu=`·`address=`·`unique_no=`·`pdf_input=` 줄삭제의 생존을 드러냈다.
    한 줄만 지워도 사용자는 "왜 내가 넣은 동/호가 무시되지" 를 겪는다.
    """
    import routers.registry as rr

    seen: dict[str, Any] = {}

    class _Svc:
        async def get_one(self, **kw: Any) -> dict[str, Any]:
            seen.update(kw)
            return {"status": "ok", "origin": "hyphen"}

    async def _no_charge(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr(rr, "RegistryService", _Svc)
    monkeypatch.setattr(rr, "_charge_registry_issue", _no_charge)

    class _U:
        user_id = "u1"
        # ★`CurrentUser` 계약에는 tenant_id 도 있다 — 스텁이 실제보다 좁으면 그 필드를
        #   쓰는 코드가 테스트에서만 터진다(형제 파일에서 같은 누락이 함께 났다).
        tenant_id = "t1"

    await rr.registry_get_one(_http_req(), {
        "pnu": "1168010100107370000", "address": "서울특별시 강남구 역삼동 737",
        "pin": "1101-2012-009048", "realty_type": "1", "dong": "101", "ho": "1502",
    }, current_user=_U())

    assert seen["pnu"] == "1168010100107370000"
    assert seen["address"] == "서울특별시 강남구 역삼동 737"
    # `pin` 은 `unique_no` 의 별칭이다 — 별칭 경로가 끊기면 프론트 일부가 조용히 실패한다.
    assert seen["unique_no"] == "1101-2012-009048"
    assert seen["realty_type"] == "1" and seen["dong"] == "101" and seen["ho"] == "1502"
    # PDF 미첨부 시 None 이어야 한다(빈 문자열이면 파서 분기로 잘못 들어간다).
    assert not seen.get("pdf_input")


@pytest.mark.asyncio
async def test_자격증명_거부는_forbidden_사유를_그대로_싣는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """`probe` 가 거부를 말한 경우 — 그 문장이 사용자에게 도달해야 한다."""
    import app.services.registry.hyphen_client as hc
    import app.services.registry.tilko_client as tc

    monkeypatch.setattr(rs, "_config", lambda: {"provider": "hyphen", "url": "", "key": ""})
    monkeypatch.setattr(hc, "hyphen_ready", lambda: True)
    monkeypatch.setattr(tc, "tilko_ready", lambda: False)

    async def _probe() -> dict[str, Any]:
        return {"access": "forbidden", "message": "하이픈 인증 실패 (HDM009)"}

    monkeypatch.setattr(hc, "probe_api_access", _probe)

    out = await rs.RegistryService().get_one(address="서울특별시 강남구 역삼동 737")
    att = [x for x in out["attempts"] if x.get("provider") == "hyphen"]
    assert att and att[0]["status"] == "forbidden", out["attempts"]
    assert "HDM009" in (att[0].get("message") or ""), att[0]
    assert "HDM009" in out["message"], out["message"]


@pytest.mark.asyncio
async def test_틸코_고유번호_조회_실패도_사유가_실린다(monkeypatch: pytest.MonkeyPatch) -> None:
    """형제 분기 — hyphen 쪽만 잠그고 tilko 쪽을 놓치는 미스윕을 막는다."""
    import app.services.registry.hyphen_client as hc
    import app.services.registry.tilko_client as tc

    monkeypatch.setattr(rs, "_config", lambda: {"provider": "tilko", "url": "", "key": ""})
    monkeypatch.setattr(hc, "hyphen_ready", lambda: False)
    monkeypatch.setattr(tc, "tilko_ready", lambda: True)

    async def _fetch(**_kw: Any) -> dict[str, Any]:
        return {"ok": False, "status": "iros_login_failed", "message": "IROS 로그인 실패"}

    # ★서비스는 `fetch_realty_registry` 를 **별칭으로 임포트**한다(`as fetch_tilko_registry`).
    #   별칭 이름으로 패치하면 존재하지 않는 속성이라 AttributeError 다 — 원래 이름을 패치한다.
    monkeypatch.setattr(tc, "fetch_realty_registry", _fetch)

    out = await rs.RegistryService().get_one(unique_no="1101-2012-009048")
    att = [x for x in out["attempts"] if x.get("provider") == "tilko"]
    assert att and att[0]["status"] == "iros_login_failed", out["attempts"]
    assert "IROS 로그인 실패" in out["message"], out["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("search", "fetch", "want_status", "want_msg"), [
    # 주소검색 자체가 무결과 — 이 사유가 사용자에게 도달해야 한다
    ({"ok": False, "status": "no_match", "message": "틸코 주소검색 결과 없음"}, None,
     "no_match", "틸코 주소검색 결과 없음"),
    # 주소검색은 됐는데 열람이 실패 — 형제 분기다
    ({"ok": True, "items": [{"unique_no": "11012012009048", "gubun": "토지"}]},
     {"ok": False, "status": "iros_pay_failed", "message": "전자결제 실패"},
     "iros_pay_failed", "전자결제 실패"),
])
async def test_틸코_주소경로_두_실패지점이_각각_사유를_싣는다(
    monkeypatch: pytest.MonkeyPatch, search: Any, fetch: Any, want_status: str, want_msg: str,
) -> None:
    """★같은 프로바이더 안에서도 실패 지점이 둘이다(검색 / 열람). 한쪽만 잠그면 다른 쪽이 샌다."""
    import app.services.registry.hyphen_client as hc
    import app.services.registry.tilko_client as tc

    monkeypatch.setattr(rs, "_config", lambda: {"provider": "tilko", "url": "", "key": ""})
    monkeypatch.setattr(hc, "hyphen_ready", lambda: False)
    monkeypatch.setattr(tc, "tilko_ready", lambda: True)

    async def _search(_addr: str, **_kw: Any) -> dict[str, Any]:
        return search

    async def _fetch(**_kw: Any) -> dict[str, Any]:
        return fetch or {}

    monkeypatch.setattr(tc, "search_unique_no", _search)
    monkeypatch.setattr(tc, "fetch_realty_registry", _fetch)

    out = await rs.RegistryService().get_one(address="서울특별시 강남구 역삼동 737")
    att = [x for x in out["attempts"] if x.get("provider") == "tilko"]
    assert att and att[0]["status"] == want_status, out["attempts"]
    assert want_msg in (att[0].get("message") or ""), att[0]
    assert want_msg in out["message"], out["message"]


@pytest.mark.asyncio
async def test_라우트가_PDF_업로드와_고유번호_직접입력도_넘긴다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★위 배선 락의 사각 — `pdf_input` 이 항상 None 이고 `unique_no` 를 `pin` 으로만 태우면
    그 두 줄을 망가뜨려도 초록이다(기계 변이가 실증). 두 값이 **실제로 흐르는** 케이스를 만든다.
    """
    import routers.registry as rr

    seen: dict[str, Any] = {}
    charged: list[Any] = []

    class _Svc:
        async def get_one(self, **kw: Any) -> dict[str, Any]:
            seen.update(kw)
            return {"status": "ok", "origin": "pdf_upload", "has_pdf": True}

    async def _charge(*a: Any, **k: Any) -> None:
        charged.append(a)

    monkeypatch.setattr(rr, "RegistryService", _Svc)
    monkeypatch.setattr(rr, "_charge_registry_issue", _charge)

    class _U:
        user_id = "u1"
        # ★`CurrentUser` 계약에는 tenant_id 도 있다 — 스텁이 실제보다 좁으면 그 필드를
        #   쓰는 코드가 테스트에서만 터진다(형제 파일에서 같은 누락이 함께 났다).
        tenant_id = "t1"

    await rr.registry_get_one(_http_req(), {
        "unique_no": "1146-2009-000054", "pdf_input": "data:application/pdf;base64,JVBER",
    }, current_user=_U())

    assert seen["unique_no"] == "1146-2009-000054", seen
    assert seen["pdf_input"] == "data:application/pdf;base64,JVBER", seen
    # PDF 업로드는 외부 발급이 아니다 — 과금 통로를 아예 타지 않는다.
    assert charged == [], "PDF 업로드 파싱에 발급 과금이 걸렸다"
