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

【★2026-08-20 — 기준선이 **둘**로 갈렸다】
도구가 양방향으로 틀렸다(과대·과소). 자세한 것은 `scripts/orphan_routes.py` 독스트링.
  · `orphan_routes_baseline.txt`  = **확정 고아**(124)
  · `orphan_routes_undecided.txt` = **판정 불가**(13, 동적 세그먼트)
판정 불가를 고아로 세면 **없는 결함을 만들고**, 소비로 세면 **진짜 고아를 숨긴다**.
그래서 어느 쪽으로도 흡수하지 않고 **자기 파일에서 양방향 래칫**으로 잠근다 —
줄어도(=결론이 났는데 기록 안 함) 늘어도(=새 동적 자리) 여기서 드러난다.
"""
from __future__ import annotations

import os
import sys

# tests/ → apps/api/tests 기준으로 propai-platform/scripts 를 찾는다(3단계 상위).
_SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts"))
sys.path.insert(0, _SCRIPTS)

_BASELINE = os.path.join(os.path.dirname(__file__), "orphan_routes_baseline.txt")
_UNDECIDED = os.path.join(os.path.dirname(__file__), "orphan_routes_undecided.txt")


def _load(path: str) -> set[str]:
    """`#` 주석줄은 무시한다 — 수치가 움직인 **사유를 파일 안에** 남기기 위한 것이다."""
    with open(path, encoding="utf-8") as f:
        return {ln.strip() for ln in f if ln.strip() and not ln.lstrip().startswith("#")}


def _load_baseline() -> set[str]:
    return _load(_BASELINE)


def test_배선안된_라우트가_늘어나지_않는다():
    from orphan_routes import orphans  # type: ignore[import-not-found]

    current = {f for f, _m, _p in orphans()}
    baseline = _load_baseline()

    # ★공허한 초록 방지 — 조회기가 죽으면 current 가 비고 "새 고아 0"이 참이 된다.
    # ★이 하한은 **파일 파손·조회기 사망 탐지용**이다. 배선을 갚아 정당하게 내려가면
    #   막지 말고 이 숫자를 낮춰라(부채 상환을 벌하지 않는다).
    assert len(baseline) > 50, "기준선이 비정상적으로 작다 — 파일이 깨졌는지 확인하라"
    assert len(current) > 0, "소비처 0 이 한 건도 없다 — 조회기가 죽었을 가능성이 높다"

    added = sorted(current - baseline)
    assert not added, (
        "새 라우트를 만들고 화면에 붙이지 않았다 — 기능이 존재하지만 아무도 못 쓴다:\n"
        + "\n".join(f"  {r}" for r in added)
        + "\n→ 프론트에 배선하거나, 백엔드 내부용이면 기준선에 추가하고 **사유를 커밋에 남겨라**."
    )


def test_판정불가가_양방향으로_잠긴다():
    """★판정 불가를 고아·소비 어느 쪽으로도 조용히 흡수하지 못하게 한다."""
    from orphan_routes import undecided_routes  # type: ignore[import-not-found]

    current = {f for f, _m, _p in undecided_routes()}
    baseline = _load(_UNDECIDED)

    # ★공허한 초록 방지 — 분류기가 죽어 전부 빈 집합이면 두 차집합이 모두 참이 된다.
    # ★파손 탐지용 하한 — 정당하게 결론이 나 줄어들면 이 숫자를 낮춰라.
    assert len(baseline) > 5, "판정 불가 기준선이 비었다 — 파일이 깨졌는지 확인하라"
    assert len(current) > 0, "판정 불가가 0건 — 동적 세그먼트 분류기가 죽었을 가능성이 높다"

    added = sorted(current - baseline)
    removed = sorted(baseline - current)
    assert not added, (
        "마지막 세그먼트를 동적으로 부르는 새 자리가 생겼다 — 이 라우트들이 실제로 불리는지"
        " **호출부를 열어** 확인하고 결론을 파일에 남겨라(고아면 기준선으로, 소비면 삭제):\n"
        + "\n".join(f"  {r}" for r in added)
    )
    assert not removed, (
        "판정 불가였던 라우트가 사라졌다 — 결론이 났으면 파일에서 지우고 **사유를 커밋에 남겨라**."
        " 조용히 사라지면 진짜 고아가 숨는다:\n" + "\n".join(f"  {r}" for r in removed)
    )


def test_두_기준선은_서로소다():
    """★같은 라우트가 양쪽에 있으면 한쪽 래칫이 반드시 거짓말을 한다."""
    both = _load_baseline() & _load(_UNDECIDED)
    assert not both, f"확정 고아와 판정 불가에 동시에 있다: {sorted(both)}"


def test_기준선이_줄면_알려준다():
    """★부채를 갚았는데 기준선을 안 줄이면 그 라우트가 다시 고아가 될 수 있다."""
    from orphan_routes import orphans  # type: ignore[import-not-found]

    current = {f for f, _m, _p in orphans()}
    removed = sorted(_load_baseline() - current)
    assert not removed, (
        "배선이 끝난 라우트가 기준선에 남아 있다 — 기준선에서 지워라(다시 고아가 되는 것을 막는다):\n"
        + "\n".join(f"  {r}" for r in removed)
    )
