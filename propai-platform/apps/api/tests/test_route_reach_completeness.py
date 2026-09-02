"""**완성도 = (확정 소비 + 의도적 비노출) / 전체.** 100% ⇔ 설명되지 않은 라우트 0.

## 왜 이 축이 필요한가

`test_orphan_routes_ratchet.py` 는 **악화를 막는다**(고아가 늘면 실패). 훌륭하지만
**개선을 강제하지 않는다** — 기준선이 132 인 채로 영원히 초록일 수 있다.
그리고 그 132 안에는 **프론트가 부르면 안 되는 라우트**가 섞여 있어
**100% 가 원리적으로 도달 불가**했다(`route_exposure_policy.py` 참조).

이 파일은 **분모를 정직하게** 만들고 **진척을 숫자로 보이게** 한다:

    완성도 = (확정 소비 + 의도적 비노출) / 전체 라우트
    미분류 = 확정 고아 − 의도적 비노출     ← 이것이 0 이면 100%

★**「고아 0」이 목표가 아니다.** 목표는 **「설명되지 않은 라우트 0」** 이다 —
모든 라우트가 *소비되거나* *왜 소비되지 않는지 적혀 있거나* 둘 중 하나.

## 이 락이 스스로 썩지 않게

- **면제는 사유 필수**(dict 값) · **죽은 면제는 실패**
- **완성도 하한 래칫** — 오늘 측정치 아래로 내려가면 실패(악화 방지)
- ★**면제가 은신처가 되지 않게**: 면제 수 자체에 상한을 둔다. 면제로 100% 를 만드는 것은
  **측정을 이기는 것**이지 완성이 아니다.
- **공허한 초록 방지**: 분모가 비정상적으로 작으면 `ScannerDeadError`(≠`AssertionError`).
"""

from __future__ import annotations

import os
import sys

import pytest

# tests/ → apps/api/tests 기준으로 propai-platform/scripts 를 찾는다(기존 래칫과 같은 방식).
_SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts"))
sys.path.insert(0, _SCRIPTS)
sys.path.insert(0, os.path.dirname(__file__))

import orphan_routes as orx  # noqa: E402
from route_exposure_policy import (  # noqa: E402
    INTENTIONALLY_UNEXPOSED,
    exempt_paths,
)

#: ★오늘 측정한 하한. 이 아래로 내려가면 **악화**다.
#:   측정: 2026-08-27 · origin/main 77ea4b5f · 라우트 550 · 소비 414 · 고아 132 · 판정불가 4
COMPLETENESS_FLOOR_PCT = 75.0

#: ★면제 상한 — 면제로 완성도를 올리는 것은 **측정을 이기는 것**이다.
#:   전체의 이 비율을 넘으면 실패시켜 "면제 남발"을 막는다.
MAX_EXEMPT_PCT = 5.0


class ScannerDeadError(RuntimeError):
    """도구가 죽었다 — **위반이 아니다.** `AssertionError` 와 다른 예외로 던진다."""


def _measure() -> dict[str, int | float]:
    confirmed, undecided = orx.classify()
    total = len(orx.backend_routes()) if hasattr(orx, "backend_routes") else 0
    if not total:
        # 도구 내부 이름이 바뀌었을 수 있다 — 합으로 복원한다.
        total = len(confirmed) + len(undecided) + _consumed_fallback(confirmed, undecided)
    if total < 100:
        raise ScannerDeadError(
            f"라우트 총계가 {total} 로 비정상적으로 작다 — 추출기가 죽었다(위반 아님)."
        )
    # ★도구 튜플은 (path, method, file) 다 — 순서를 틀리면 method 를 경로로 센다
    #   (첫 판에서 그렇게 틀렸고, **이 파일의 죽은-면제 락이 그것을 잡았다**).
    orphan_paths = {path for path, _m, _f in confirmed}
    exempt = exempt_paths()
    unexplained = sorted(orphan_paths - exempt)
    consumed = total - len(confirmed) - len(undecided)
    explained = consumed + len(orphan_paths & exempt)
    return {
        "total": total,
        "consumed": consumed,
        "orphan": len(confirmed),
        "undecided": len(undecided),
        "exempt_hit": len(orphan_paths & exempt),
        "unexplained": len(unexplained),
        "pct": round(100.0 * explained / total, 2),
        "_unexplained_list": unexplained,  # type: ignore[dict-item]
    }


def _consumed_fallback(confirmed, undecided) -> int:  # pragma: no cover - 방어
    raise ScannerDeadError("라우트 총계를 읽을 수 없다 — orphan_routes 인터페이스가 바뀌었다.")


def test_tool_is_alive() -> None:
    """★공허한 초록 방지 + 양성 대조군."""
    m = _measure()
    assert m["total"] >= 100, f"라우트 총계 비정상: {m['total']}"
    assert m["consumed"] > 0, "확정 소비가 0 — 조회기가 죽었을 가능성이 높다"
    assert m["orphan"] > 0, "확정 고아가 0 — 분류기가 죽었을 가능성이 높다"


def test_completeness_does_not_regress() -> None:
    """완성도 = (소비 + 의도적 비노출) / 전체. 하한 아래로 내려가면 실패."""
    m = _measure()
    assert m["pct"] >= COMPLETENESS_FLOOR_PCT, (
        f"라우트 완성도 {m['pct']}% < 하한 {COMPLETENESS_FLOOR_PCT}%. "
        f"(전체 {m['total']} · 소비 {m['consumed']} · 면제 {m['exempt_hit']} · "
        f"미분류 {m['unexplained']} · 판정불가 {m['undecided']})"
    )


def test_exemption_is_not_a_hiding_place() -> None:
    """★면제로 완성도를 올리는 것은 **측정을 이기는 것**이지 완성이 아니다."""
    m = _measure()
    pct = 100.0 * len(INTENTIONALLY_UNEXPOSED) / m["total"]
    assert pct <= MAX_EXEMPT_PCT, (
        f"의도적 비노출이 전체의 {pct:.1f}% ({len(INTENTIONALLY_UNEXPOSED)}건) — "
        f"상한 {MAX_EXEMPT_PCT}% 초과. 면제가 미배선의 은신처가 되고 있지 않은지 보라."
    )


def test_no_dead_exemption() -> None:
    """★죽은 면제는 실패 — 사라진 라우트를 면제하면 다음 사람이 속는다."""
    confirmed, undecided = orx.classify()
    live_orphans = {path for path, _m, _f in confirmed}
    live_undecided = {path for path, _m, _f in undecided}
    # 소비로 바뀐 것도 면제에 남아 있으면 죽은 면제다 → 전체 라우트에서 확인.
    dead = sorted(p for p in exempt_paths() if p not in (live_orphans | live_undecided))
    assert not dead, (
        f"더 이상 고아가 아닌데 면제에 남아 있는 라우트: {dead}. "
        "소비되기 시작했거나 삭제됐다 — route_exposure_policy 에서 지워라."
    )


def test_every_exemption_has_a_real_reason() -> None:
    """사유 없는 면제는 면제가 아니라 침묵이다."""
    weak = sorted(p for p, why in INTENTIONALLY_UNEXPOSED.items() if len(why.strip()) < 15)
    assert not weak, f"사유가 비었거나 너무 짧은 면제: {weak}"
    # ★"아직 안 붙였다"는 면제 사유가 아니다 — 그건 고아로 남겨 래칫이 줄이게 한다.
    postponed = sorted(
        p for p, why in INTENTIONALLY_UNEXPOSED.items()
        if any(k in why for k in ("아직", "나중", "추후", "TODO", "예정"))
    )
    assert not postponed, (
        f"미배선을 면제로 숨기고 있다: {postponed}. "
        "면제 사유는 **붙이면 안 되는 이유**여야 한다 — 미룸은 고아로 남겨라."
    )


def test_report_current_completeness(capsys: pytest.CaptureFixture[str]) -> None:
    """진척을 숫자로 남긴다(실패하지 않는다 — 다음 사람이 추세를 보게)."""
    m = _measure()
    with capsys.disabled():
        print(
            f"\n  [라우트 완성도] {m['pct']}%  "
            f"= (소비 {m['consumed']} + 면제 {m['exempt_hit']}) / {m['total']}"
            f"  · 미분류 {m['unexplained']} · 판정불가 {m['undecided']}"
        )
    assert m["pct"] <= 100.0
