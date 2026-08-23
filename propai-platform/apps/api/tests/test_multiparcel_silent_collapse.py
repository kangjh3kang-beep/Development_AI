"""다필지가 **조용히 단필지로 축약**된다 (2026-08-23 · 사용자 신고).

★사용자 신고: *"다필지 입력 시 단필지만 분석하는 오류가 계속 발생"*.
  라이브(propai-v002723)에서 `build_integrated_context` 를 직접 태워 **완전 재현**했다:

    A) 2필지 · 면적 2/2 → parcel_count=2 · total=30,182   ✔ 정상
    B) 2필지 · 면적 1/2 → **parcel_count=1** · total=29,167(단필지 결과) + 경고 있음
    C) 2필지 · 면적 0/2 → **None** → 소비처가 단일 경로 폴백 · **경고조차 없음**

★근본: `items = [q for ... if (q.get("area_sqm") or 0) > 0]` 로 면적 없는 필지를 버리고,
  남은 게 없으면 `if not items: return None`. 이 return 에는 **로그조차 없다**
  (`logger.warning("통합집계 실패…")` 는 try 안의 except 라 이 경로를 안 탄다).
  게다가 `_area_missing`(몇 필지가 왜 빠졌는지)을 **이미 계산해 놓고 그 자리에서 버린다**.

★그리고 `None` 은 "통합 불필요(단일필지)"와 "다필지인데 통합 실패"를 **구분하지 않는다** —
  그래서 소비처 7곳 중 6곳이 조용히 단필지로 떨어진다(고지하는 곳은 design_ingest 뿐).

★이 PR 의 범위: **침묵을 깬다**(로그+영속 계측). 계약(`None` 반환)은 **바꾸지 않는다** —
  소비처가 truthy 체크를 하고 있어 dict 를 내면 다른 경로를 타 회귀가 된다.
  소비처 화면 고지는 **다음 단계**(별건).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402

from app.services.land_intelligence import comprehensive_analysis_service as cas  # noqa: E402

A1 = {"address": "경기도 오산시 수청동 569", "area_sqm": 29167.0, "zone_type": "제3종일반주거지역"}
A2 = {"address": "경기도 오산시 내삼미동 741", "area_sqm": 1015.0, "zone_type": "자연녹지지역"}
NO_AREA = {"address": "경기도 오산시 내삼미동 741"}


#   ※로그(문구·인자·`if _normalized:` 가드) 변이 생존은 **의도된 미잠금**이다 —
#     사람이 읽는 진단 메시지이지 계약이 아니다. 계약은 위 영속 관측(payload)이다.


@pytest.fixture
def observed(monkeypatch):
    events: list[tuple[str, dict]] = []
    from app.services.growth import capture_service

    monkeypatch.setattr(capture_service, "record_event",
                        lambda et, props=None: events.append((et, props or {})))
    return events


def _collapse(events):
    return [e for e in events if e[0] == cas.MULTIPARCEL_COLLAPSE_EVENT]


@pytest.mark.asyncio
async def test_C_전필지_면적미확보는_침묵하지_않는다(observed):
    """★가장 큰 구멍 — 종전엔 로그·계측·고지가 **전부** 없었다."""
    r = await cas.build_integrated_context([NO_AREA, {"address": "경기도 오산시 수청동 569"}])
    assert r is None, "계약 유지: 여전히 None 을 낸다(소비처 무회귀)"

    obs = _collapse(observed)
    assert obs, "입력이 다필지였는데 통합 불가 — 그 사실이 어디에도 안 남았다"
    event_type, props = obs[0]
    # ★상수값 = 프로덕션 조회 키(바뀌면 대시보드·쿼리가 조용히 빈다)
    assert event_type == "multiparcel_collapse_observation"
    # ★analyzer 가 COALESCE(route, service) 로 **실제 읽는** 컬럼이다
    assert props["service"] == "integrated_context"
    assert props["surface"] == "api"
    payload = props["payload"]
    assert payload["input_count"] == 2
    assert payload["usable_count"] == 0
    assert payload["missing_count"] == 2
    assert payload["collapsed"] is True


@pytest.mark.asyncio
async def test_B_부분축약도_남긴다_분자(observed):
    """2필지 넣었는데 1필지로 집계되면 그것도 축약이다(사용자가 겪는 그 증상)."""
    r = await cas.build_integrated_context([A1, NO_AREA])
    assert r is not None and r.get("parcel_count") == 1   # 전제: 실제로 축약된다

    obs = _collapse(observed)
    assert obs, "부분 축약이 계측되지 않으면 빈도를 못 잰다"
    payload = obs[0][1]["payload"]
    assert payload["input_count"] == 2
    assert payload["usable_count"] == 1
    assert payload["collapsed"] is True


@pytest.mark.asyncio
async def test_A_축약이_없으면_collapsed_False_분모(observed):
    """★A와 B/C가 갈리는 지점 — 분모가 없으면 '몇 번 중 몇 번'을 못 센다."""
    r = await cas.build_integrated_context([A1, A2])
    assert r is not None and r.get("parcel_count") == 2   # 전제: 정상 통합

    obs = _collapse(observed)
    assert obs
    assert obs[0][1]["payload"]["collapsed"] is False
    assert obs[0][1]["payload"]["usable_count"] == 2


@pytest.mark.asyncio
async def test_D_단일필지는_축약이_아니다_위양성방지(observed):
    """1필지 입력은 원래 통합 대상이 아니다 — 이걸 축약으로 신고하면 지표가 죽는다."""
    r = await cas.build_integrated_context([A1])
    assert r is not None
    obs = _collapse(observed)
    assert obs and obs[0][1]["payload"]["collapsed"] is False


@pytest.mark.asyncio
async def test_E_F4a_자동토글_신호를_만들지_않는다(observed):
    await cas.build_integrated_context([NO_AREA, NO_AREA])
    for event_type, props in observed:
        assert event_type != "verify_result"
        assert "severity" not in props
        assert "recommended_action" not in props
