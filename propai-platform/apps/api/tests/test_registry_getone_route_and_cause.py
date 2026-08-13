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

    assert any(x.get("provider") == "custom" for x in out.get("attempts") or []), (
        f"커스텀 실패가 attempts 에 없다 — 사유가 로그로만 새고 사용자에겐 안 간다: {out.get('attempts')}"
    )
    assert "502" in out["message"], f"상류 사유가 메시지에 실려야 한다: {out['message']}"
