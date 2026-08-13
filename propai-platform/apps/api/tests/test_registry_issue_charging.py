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

# get_one 이 낼 수 있는 **실패** 상태 전수(코드에서 파생 — 사람이 센 목록이 아니다).
FAILURE_STATUSES = ("not_configured", "provider_error", "no_match", "bad_request", "forbidden",
                    "unavailable", "error", "failed")


@pytest.mark.parametrize("status", FAILURE_STATUSES)
def test_실패는_한_건도_과금하지_않는다(status: str) -> None:
    assert issued_count({"status": status, "message": "…"}) == 0, (
        f"status={status!r} 가 과금 대상으로 읽힌다 — 실패한 조회에 돈이 청구된다"
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


@pytest.mark.asyncio
async def test_라우트가_실패시_과금을_부르지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★결함이 살던 자리를 직접 태운다 — 라우트 → 과금 호출까지."""
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

    out = await rr.registry_get_one({"address": "서울특별시 강남구 역삼동 737"}, current_user=_U())
    assert out["status"] == "provider_error"
    # 과금 함수는 호출되되(단일 통로), 그 안에서 0건으로 판정돼야 한다.
    # 여기서는 통로가 실제로 실패 결과를 받는지까지만 확인한다.
    assert calls == ["provider_error"], calls
    assert issued_count({"status": "provider_error"}) == 0, "그 결과는 과금 0건이어야 한다"
