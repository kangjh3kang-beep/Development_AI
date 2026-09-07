"""`/zoning/integrated-analysis` per_parcel 표면 — 미분석 표식이 여기서도 살아 나가는가.

★왜(2026-08-05 R3 H-2): 이 응답은 다필지 감지 결과를 그대로 싣지 않고 **자체 재조립본**이다.
  그래서 표식을 따로 실어야 하는데, 그 4줄을 지워도 저장소의 어떤 테스트도 깨지지 않았다
  (변이 생존). 프론트 "판정 불가(미분석)" 배지가 읽는 키라 빠지면 배지가 다시 굶는다.

  형제 표면(build_multi_parcel_report matrix)은 회귀락이 있었는데 이 표면만 없었다 —
  "두 표면에 실었다"는 주장의 절반만 잠겨 있던 셈이다.
"""
import pytest

from app.services.zoning.special_parcel import is_unanalyzed_parcel


@pytest.mark.asyncio
async def test_integrated_analysis_per_parcel_declares_status_both_ways():
    """라우터 응답의 per_parcel이 표식을 **양방향**으로 싣는다."""
    from routers.auto_zoning import IntegratedAnalysisRequest, integrated_analysis

    req = IntegratedAnalysisRequest(parcels=[
        {"address": "A", "area_sqm": 400.0, "zone_type": "제2종일반주거지역", "land_category": "대"},
        {"address": "B", "area_sqm": 600.0},
    ])
    out = await integrated_analysis(req)
    statuses = [p.get("analysis_status") for p in out["per_parcel"]]
    assert statuses == ["analyzed", "unanalyzed"], statuses
    # 부재(None)로 남지 않는다 — 부재는 "분석됨"과 "판정 안 함"을 구분하지 못한다.
    assert None not in statuses


def test_status_source_is_the_shared_predicate():
    """판정은 SSOT를 쓴다 — 라우터가 자체 규칙을 갖고 있으면 우회 경로에 적용되지 않는다."""
    assert is_unanalyzed_parcel({"area_sqm": 600.0}) is True
    assert is_unanalyzed_parcel({"area_sqm": 600.0, "zone_type": "제2종일반주거지역"}) is False


@pytest.mark.asyncio
async def test_premise_audit_declares_vacuous_axis_on_this_path():
    """★이 경로에서 **원리적으로 판별할 수 없는 관계**를 응답이 스스로 말한다.

    ★왜(2026-09-05): 종전엔 `{checked, registered, violations}` **3키만** 실었다.
      그러면 화면이 `6/6 · 위반 0` 을 «6종 전부 판별했다» 로 읽는데, 이 경로에서는
      최소 두 관계가 **원리적으로 어긋날 수 없다**:
        · count_conservation_parcels — 위임이 `parcels=enriched` 를 그대로 받아 양변이 같은 리스트
        · area_source_agreement     — 라우터가 `land_area_sqm=total_area` 를 **항상** 넘겨
                                       위임의 면적 재산정 분기가 스킵된다
      «침묵과 무결을 가른다» 가 이 고지의 존재 이유인데, 그 축이 없으면 정확히 반대가 된다.

    ★**simulator 의 목록을 복사하지 않는다** — 그쪽은 `path_invariance_zone` 을 공허로 적지만
      이 경로에서 그 관계는 **위임이 폴백했을 때 살아나는** 신호다. 조건에서 파생한다.
    """
    from routers.auto_zoning import IntegratedAnalysisRequest, integrated_analysis

    req = IntegratedAnalysisRequest(parcels=[
        {"address": "A", "area_sqm": 600.0, "zone_type": "제2종일반주거지역", "land_category": "대"},
        {"address": "B", "area_sqm": 400.0, "zone_type": "제2종일반주거지역", "land_category": "대"},
    ])
    out = await integrated_analysis(req)
    pa = (out.get("scenario") or {}).get("premise_audit")

    # ★공허 진리 가드 — 단언 **앞에** 대상 존재를 확정한다.
    #   위임이 실패해 감사 자체가 안 돌았으면 이 테스트는 다른 것을 재는 셈이다.
    assert isinstance(pa, dict), f"premise_audit 가 없다 — 이 단언은 공허해진다: {out.get('scenario')}"

    # ① 기존 세 키는 그대로다(회귀 아님).
    for k in ("checked", "registered", "violations"):
        assert k in pa, f"{k} 가 사라졌다"

    # ② ★새 축이 실린다 — **이름이 아니라 값**을 본다.
    assert "structurally_vacuous" in pa, "구조적 공허 축이 없다 — 화면이 판별력을 과대평가한다"
    vac = pa["structurally_vacuous"]
    assert isinstance(vac, list) and vac, f"비어 있으면 이 경로가 전부 판별한다는 주장이다: {vac!r}"

    # ③ ★두 모집단 — 원리적으로 못 가르는 것은 **들어 있고**, 살아 있는 신호는 **함부로 안 넣는다**.
    assert "count_conservation_parcels" in vac, vac
    assert "area_source_agreement" in vac, vac
    # path_invariance_zone 은 **조건부**다. simulator 값을 복사했다면 조건과 무관하게 늘 들어간다.
    basis = ((out.get("scenario") or {}).get("top3") or {}).get("zone_basis")
    if basis == "integrated_dominant":
        assert "path_invariance_zone" in vac, (basis, vac)
    else:
        assert "path_invariance_zone" not in vac, (
            f"zone_basis={basis!r} 인데 공허로 표기했다 — **살아 있는 감시기를 죽은 것으로 적었다**: {vac}"
        )


@pytest.mark.asyncio
async def test_premise_audit_failure_path_declares_itself():
    """★★**감사가 가장 필요한 순간에 화면이 침묵하지 않는다** — 실패 경로도 같은 키를 남긴다.

    종전엔 위임(`auto_recommend_top3`)이 터지면 `except` 가 시나리오만 degrade 하고
    `premise_audit` **키를 아예 안 만들었다.** 프론트 렌더러는 `undefined` 를 `"clean"`(무렌더)로
    분류하므로 **「전제 감사가 깨끗하다」와 구별 불가**했다.

    ★스키마는 형제(`scenario_simulator.py` 의 감사 실패 갈래)와 같은 모양이어야 한다 —
      성공/실패가 같은 키에 다른 스키마면 소비처가 `["violations"]` 에서 KeyError 를 맞는다.
    """
    from app.services.feasibility import feasibility_service_v2 as fs2
    from routers.auto_zoning import IntegratedAnalysisRequest, integrated_analysis

    async def _boom(*a, **k):
        raise RuntimeError("delegation exploded")

    # ★라우터가 **함수 안에서** import 하므로 라우터 모듈 속성을 패치해도 안 통한다
    #   (초판이 그렇게 짰다가 AttributeError 로 실패했다 — 이 락이 내 전제를 잡았다).
    #   원본 클래스의 메서드를 갈아 끼운다.
    orig = fs2.FeasibilityServiceV2.auto_recommend_top3
    fs2.FeasibilityServiceV2.auto_recommend_top3 = _boom
    try:
        req = IntegratedAnalysisRequest(parcels=[
            {"address": "A", "area_sqm": 600.0, "zone_type": "제2종일반주거지역", "land_category": "대"},
            {"address": "B", "area_sqm": 400.0, "zone_type": "제2종일반주거지역", "land_category": "대"},
        ])
        out = await integrated_analysis(req)
    finally:
        fs2.FeasibilityServiceV2.auto_recommend_top3 = orig

    scenario = out.get("scenario") or {}
    pa = scenario.get("premise_audit")
    # ★핵심 — 키가 **존재한다**. 종전엔 여기가 None 이었고 화면은 그것을 「깨끗함」으로 그렸다.
    assert isinstance(pa, dict), f"실패 경로에 premise_audit 가 없다: {scenario!r}"
    # ★그리고 **자기를 실패로 구별한다**(존재만으로는 부족하다 — 값이 실려야 한다).
    assert pa.get("reason") == "audit_failed", pa
    assert pa.get("checked") == 0, pa
    assert pa.get("violations") == [], pa
    assert pa.get("detail"), "사유가 비면 조사자가 원인을 알 수 없다"
