"""용인시 조례 캐시 원문 정합 회귀앵커 (백로그④).

근거: 용인시 도시계획 조례(2024-05-10 개정판 원문 실측 — 2026-07-22 확인)
  · 건폐율 = 제50조 제1항 / 용적률 = 제55조 제1항.
★역사적 함정 고정: "용인 자연녹지 조례=80%"라는 과거 기록은 구조상한(건폐 20%×4층=80%)과의
  혼동이었다. 조례 원문상 자연녹지 용적률은 100%(제55조 16호)다. 누군가 80을 캐시에 넣으면
  이 테스트가 막는다(날조 방지). 실효 80%는 조례가 아니라 구조상한 min 적용의 결과다.
"""
from __future__ import annotations

from app.services.land_intelligence.far_tier_service import calc_effective_far
from app.services.land_intelligence.ordinance_service import ORDINANCE_CACHE


def test_yongin_natural_green_cache_is_100_not_80():
    """자연녹지 조례 = 건폐 20·용적 100 (제50조16호·제55조16호). 80 등재는 날조."""
    entry = ORDINANCE_CACHE["용인시"]["자연녹지지역"]
    assert entry == {"bcr": 20, "far": 100}


def test_yongin_residential_zones_match_ordinance_text():
    """주거 3종은 원문(200/240/290) — 종전 과소 등재(150/200/250) 재발 방지."""
    y = ORDINANCE_CACHE["용인시"]
    assert y["제1종일반주거지역"] == {"bcr": 60, "far": 200}
    assert y["제2종일반주거지역"] == {"bcr": 60, "far": 240}
    assert y["제3종일반주거지역"] == {"bcr": 50, "far": 290}


def test_yongin_green_management_zones_present():
    """녹지·관리 계열 6종 등재(제50조·제55조 14~19호) — 조례 미해석 폴백('확인 필요') 해소."""
    y = ORDINANCE_CACHE["용인시"]
    assert y["보전녹지지역"]["far"] == 70
    assert y["생산녹지지역"]["far"] == 100
    assert y["보전관리지역"]["far"] == 80
    assert y["생산관리지역"]["far"] == 80
    assert y["계획관리지역"] == {"bcr": 40, "far": 100}


def test_yongin_natural_green_effective_far_still_80_by_structural_cap():
    """조례 100 등재 후에도 실효는 구조상한 80이 min으로 유지 — 무회귀(신봉동 라이브 확증값)."""
    out = calc_effective_far(
        {
            "local_ordinance": {
                "effective_far": 100.0, "effective_bcr": 20.0,
                "source": "지자체 조례(정적캐시)",
            },
            "zone_limits": {},
        },
        zone_type="자연녹지지역", land_area=1520.0,
    )
    assert out["structural_cap_pct"] == 80.0
    assert out["effective_far_pct"] == 80.0  # min(법정100, 조례100, 구조상한80)
