"""지연 버스트 판정 — **동시성**이 공통 경로를 가른다.

## 왜 이 락이 필요한가 (2026-08-27 실측)

하루 최소 **5회**의 ~10분 지연 버스트가 났고, **두 세션이 라이브로 못 봤다.**
가장 심한 것(`/api/v1/zoning/parcel-boundaries` **69,503ms** @07:05Z)은
아무도 안 보고 지나갔다 — 우연히 로그인을 시도한 시각에만 알아챘기 때문이다.

★`/health` 는 **그 순간**만 말한다. 지나간 버스트를 못 되짚는다.
`platform_events` 5분 버킷은 **사후 판정이 된다** — 그래서 계기판에 넣는다.

## 픽스처는 **실측값**이다 (지어낸 수가 아니다)

아래 두 버킷은 동료 세션(`development-ai-ae`)이 라이브에서 전수로 뽑은 값이다.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "monitor"))

from latency_burst_probe import (  # noqa: E402
    BURST_MIN_N,
    BURST_P95_MS,
    MULTI_ROUTE_MIN,
    classify_buckets,
)


def _b(hh: int, mm: int) -> datetime:
    return datetime(2026, 8, 27, hh, mm)


#: ★실측 — 07:05Z 버스트(5개 라우트 동시). 최대 69,503ms.
_REAL_0705 = [
    (_b(7, 5), "/api/v1/analysis-ledger/history", 20, 19396.0),
    (_b(7, 5), "/api/v1/zoning/parcel-boundaries", 20, 69503.0),
    (_b(7, 5), "/api/v1/auth/me", 20, 19227.0),
    (_b(7, 5), "/api/v1/store/projects", 20, 20248.0),
    (_b(7, 5), "/ai/status", 20, 2369.0),
]

#: ★실측 — 08:05Z 는 login **단독** 스파이크였다(다른 라우트는 조용).
_REAL_0805 = [(_b(8, 5), "/api/v1/auth/login", 27, 6707.0)]


def test_simultaneous_routes_are_flagged_as_common_path():
    """★핵심 판정 — 여러 라우트가 **같은 버킷**에 걸리면 공통 경로 의심."""
    out = classify_buckets(_REAL_0705)
    assert len(out) == 1
    bucket, count, worst, kind = out[0]
    assert count == 5
    assert worst == 69503.0, "최대 p95 가 소실됐다 — 가장 심한 것을 놓친다"
    assert kind == "multi_route"


def test_single_route_spike_is_not_called_a_common_path():
    """★음성 모집단 — 한 라우트만 느린 것을 공통 경로라 부르면 **위양성**이다.

    이게 없으면 "전부 multi_route 로 찍는" 구현도 위 테스트를 통과한다.
    """
    out = classify_buckets(_REAL_0805)
    assert len(out) == 1
    _b0, count, worst, kind = out[0]
    assert count == 1
    assert worst == 6707.0
    assert kind == "single_route"


def test_both_populations_in_one_run_are_kept_apart():
    """두 사건이 **한 실행에** 들어와도 섞이지 않는다(버킷이 판정 단위)."""
    out = classify_buckets(_REAL_0705 + _REAL_0805)
    kinds = {b.strftime("%H:%M"): k for b, _c, _p, k in out}
    assert kinds == {"07:05": "multi_route", "08:05": "single_route"}, kinds


@pytest.mark.parametrize("n_routes,expected", [
    (MULTI_ROUTE_MIN - 1, "single_route"),   # 경계 바로 아래
    (MULTI_ROUTE_MIN, "multi_route"),        # 경계
])
def test_multi_route_threshold_partitions_at_the_boundary(n_routes, expected):
    """★경계를 **양쪽으로** 건다 — 한쪽만 걸면 반대 방향이 무제한이 된다."""
    rows = [(_b(9, 0), f"/r{i}", 10, 9000.0) for i in range(n_routes)]
    assert classify_buckets(rows)[0][3] == expected


def test_thresholds_are_literals_not_self_referential():
    """★자기 상수 단언 금지 — 상수를 바꿔도 통과하는 락은 장식이다."""
    assert BURST_P95_MS == 5000
    assert BURST_MIN_N == 3
    assert MULTI_ROUTE_MIN == 3


def test_worst_p95_survives_across_routes_in_a_bucket():
    """가장 심한 값이 **버킷 대표**로 남는가 — 평균으로 뭉개면 69초가 사라진다."""
    rows = [(_b(7, 5), "/slow", 20, 69503.0), (_b(7, 5), "/mild", 20, 5100.0),
            (_b(7, 5), "/mild2", 20, 5200.0)]
    assert classify_buckets(rows)[0][2] == 69503.0


def test_empty_input_yields_no_bursts_not_a_crash():
    assert classify_buckets([]) == []


def test_probe_module_does_not_touch_db_on_import():
    """★임포트만으로 DB 에 붙으면 이 락 자체가 CI 에서 죽는다(형제 프로브와 같은 규율)."""
    src = (Path(__file__).resolve().parents[3] / "scripts" / "monitor"
           / "latency_burst_probe.py").read_text(encoding="utf-8")
    assert "from app.core.database import AsyncSessionLocal" in src
    # 그 임포트가 **함수 안**에 있어야 한다(모듈 최상위면 임포트 시 붙는다)
    top_level = [ln for ln in src.splitlines() if ln.startswith("from app.")]
    assert not top_level, f"DB 임포트가 모듈 최상위에 있다: {top_level}"
