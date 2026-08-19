"""배선 안 된 라우트가 **늘어나지 않게** 잠근다(래칫).

【왜 래칫인가】현재 소비처 0 이 123 건이다. 전부 결함은 아니다 — 정당한 백엔드 내부용이 섞인다.
그래서 **0 을 요구하지 않는다**(요구하면 정당한 라우트를 지우게 만들거나, 테스트를 끄게 된다).
대신 **새로 생기는 것만** 막는다: 새 라우트를 만들면서 화면에 안 붙이면 여기서 드러난다.

【이 저장소가 이 결함으로 데인 이력】
  · P2 매입전략 — 백엔드 배포됐는데 프론트 소비처 0(2026-08-16 인계서가 미결로 남김)
  · 종합 부지분석 — 라우트 live 인데 생성허브·랜딩 어디에도 진입 카드 없음
  · AVM 항공영상 — Next 라우트가 백엔드에 가려져 404, 실패는 "생략됩니다"로 위장

【기준선을 줄이는 것이 목표다】
`orphan_routes_baseline.txt` 에서 항목을 **지우면** 그 라우트는 다시 고아가 될 수 없다.
배선하거나 삭제한 뒤 기준선에서 빼라 — 그게 이 부채를 갚는 방법이다.
"""
from __future__ import annotations

import os
import sys

# tests/ → apps/api/tests 기준으로 propai-platform/scripts 를 찾는다(3단계 상위).
_SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts"))
sys.path.insert(0, _SCRIPTS)

_BASELINE = os.path.join(os.path.dirname(__file__), "orphan_routes_baseline.txt")


def _load_baseline() -> set[str]:
    with open(_BASELINE, encoding="utf-8") as f:
        return {ln.strip() for ln in f if ln.strip()}


def test_배선안된_라우트가_늘어나지_않는다():
    from orphan_routes import orphans  # type: ignore[import-not-found]

    current = {f for f, _m, _p in orphans()}
    baseline = _load_baseline()

    # ★공허한 초록 방지 — 조회기가 죽으면 current 가 비고 "새 고아 0"이 참이 된다.
    assert len(baseline) > 50, "기준선이 비정상적으로 작다 — 파일이 깨졌는지 확인하라"
    assert len(current) > 0, "소비처 0 이 한 건도 없다 — 조회기가 죽었을 가능성이 높다"

    added = sorted(current - baseline)
    assert not added, (
        "새 라우트를 만들고 화면에 붙이지 않았다 — 기능이 존재하지만 아무도 못 쓴다:\n"
        + "\n".join(f"  {r}" for r in added)
        + "\n→ 프론트에 배선하거나, 백엔드 내부용이면 기준선에 추가하고 **사유를 커밋에 남겨라**."
    )


def test_기준선이_줄면_알려준다():
    """★부채를 갚았는데 기준선을 안 줄이면 그 라우트가 다시 고아가 될 수 있다."""
    from orphan_routes import orphans  # type: ignore[import-not-found]

    current = {f for f, _m, _p in orphans()}
    removed = sorted(_load_baseline() - current)
    assert not removed, (
        "배선이 끝난 라우트가 기준선에 남아 있다 — 기준선에서 지워라(다시 고아가 되는 것을 막는다):\n"
        + "\n".join(f"  {r}" for r in removed)
    )
