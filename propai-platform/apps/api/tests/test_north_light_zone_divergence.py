"""정북일조 **적용 판정**의 저장소 내 발산 현황 박제(2026-07-31).

★왜 이 테스트가 있나: 같은 법조문(건축법 §61) 적용 판정이 저장소에 여러 벌 있고 실제로
  **서로 다른 답**을 낸다. W3-b에서 지정 SSOT(`common.sunlight_setback.north_light_applies`)를
  세우고 `site_layout_service`만 전환했다 — 나머지는 전환하면 그 기능의 출력이 바뀌어
  별건 판단이 필요하기 때문이다.

  그런데 **무표시 부분 전환은 은폐된 발산**이다(리뷰어 지적). 다음 사람이 "SSOT가 있으니
  일관되겠지"라고 믿는 것을 막기 위해, 지금의 발산을 **명시적으로 박제**한다.

★이 테스트가 실패하면: 누군가 소비처를 전환했거나 키워드를 바꾼 것이다. **기대값을 그냥
  맞추지 말고**, 전환이 의도된 것인지 확인한 뒤 이 표를 갱신하라(발산이 사라졌다면 그게
  목표 상태이므로 이 파일을 지우면 된다).
"""
from __future__ import annotations

import pytest

from app.services.cad.massing_strategy import _NORTH_LIGHT_ZONE_KEYWORDS as MASSING_KW
from app.services.common.sunlight_setback import north_light_applies as ssot
from app.services.site_score.solar_envelope_service import _NORTH_LIGHT_ZONES as SOLAR_KW


def _massing(z: str) -> bool:
    return any(k in (z or "") for k in MASSING_KW)


def _solar(z: str) -> bool:
    return any(k in (z or "") for k in SOLAR_KW)


# (용도지역, SSOT, massing_strategy, solar_envelope) — 현재 사실을 그대로 적는다.
# ★R3 지적 수용: 1차 박제가 발산 11행 중 **5행만** 담아 "은폐된 발산을 드러낸다"는 이 파일의
#   존재 이유와 어긋났다(정직을 위한 파일이 사실을 절반만 말했다). 전수로 옮긴다.
_SNAPSHOT = [
    # ── 일치 구간(정상) ──
    ("제2종일반주거지역", True, True, True),
    ("제1종전용주거지역", True, True, True),
    ("일반주거지역", True, True, True),
    ("전용주거지역", True, True, True),
    ("일반상업지역", False, False, False),
    ("준주거지역", False, False, False),
    ("자연녹지지역", False, False, False),
    ("", False, False, False),
    # ── ★발산 A: 엔진 **코드형**을 SSOT만 인식한다 ──────────────────────────────
    #   프론트가 `zoneType`에 `zoneCode`를 넣는 경로가 여러 곳이라 실제로 도달한다.
    ("1R", True, False, False),
    ("2R", True, False, False),
    ("3R", True, False, False),
    ("1r", True, False, False),
    ("2r", True, False, False),
    ("3r", True, False, False),
    # ── ★발산 B: "종"만으로 참이 되는 느슨한 키워드(비주거 오판) ─────────────────
    #   SSOT는 '주거'를 요구한다. 지도에 법적 금지구역을 칠하는 판정이라 오탐 비용이 크다.
    ("제1종", False, True, True),
    ("제2종", False, True, True),
    ("제3종", False, True, True),
    ("제2종근린생활시설", False, True, True),
    ("제2종지구단위계획구역", False, True, True),
]


@pytest.mark.parametrize("zone,expect_ssot,expect_massing,expect_solar", _SNAPSHOT)
def test_zone_applicability_divergence_snapshot(zone, expect_ssot, expect_massing, expect_solar):
    assert ssot(zone) is expect_ssot, f"SSOT 판정이 바뀌었다: {zone}"
    assert _massing(zone) is expect_massing, f"massing_strategy 판정이 바뀌었다: {zone}"
    assert _solar(zone) is expect_solar, f"solar_envelope 판정이 바뀌었다: {zone}"


def test_divergence_is_documented_not_accidental():
    """발산이 **존재한다**는 사실 자체를 박제 — 0이 되면 이 파일을 지우라는 신호다."""
    diverging = [z for z, a, b, c in _SNAPSHOT if not (a is b is c)]
    assert diverging, (
        "발산이 사라졌다 — 소비처가 SSOT로 수렴한 것으로 보인다. "
        "확인 후 이 스냅샷 테스트를 삭제하라(목표 상태 도달)."
    )
    assert len(diverging) == 11, f"발산 항목 수가 바뀌었다(현재 {len(diverging)}): {diverging}"
