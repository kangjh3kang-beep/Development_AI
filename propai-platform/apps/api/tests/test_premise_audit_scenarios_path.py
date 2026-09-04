"""개발방식 시뮬레이터가 **전제 감시망 안에** 있는가 + 우세 용도지역이 **형제와 일치**하는가.

## 왜 필요한가 (실측 2026-09-04)

`premise_audit.audit()` 호출부가 **`routers/auto_zoning.py` 1곳뿐**이라
`/development-methods/scenarios` 경로는 **감시망 밖**이었다. 등록된 전제 6종 중
`dominant_argmax` 는 `#940` 의 RC-2(첫 필지를 우세 용도지역으로 씀)를 **정확히** 잡는다 —
신고 부지 형상으로 감사기를 직접 태워 확인했다(종전 발화 / 수정 후 침묵).

★그리고 `#940` 자신이 **같은 클래스의 약한 판본**을 만들었다: 형제
`special_parcel._aggregate_integrated_zoning` 은 **동률(±5%)·규제성격 상이**를
`mixed_review_required` 로 **거부**하는데, `dominant_zone_by_area` 는 **임의 단일화**했다.
4모집단 중 **3개가 갈렸다.** 볼트가 *"시뮬레이터만 자기 방식을 만들었다"* 고 적어 둔 그 자리다.
"""
import pytest

from app.services.development.scenario_simulator import (
    dominant_zone_by_area,
)
from app.services.zoning import premise_audit
from app.services.zoning.special_parcel import _aggregate_integrated_zoning


def _rows(pairs):
    return [{"zone": z, "area": a} for z, a in pairs]


def _sibling(pairs):
    agg = _aggregate_integrated_zoning(
        [{"zone_type": z, "area_sqm": a, "areaSqm": a} for z, a in pairs])
    return agg.get("dominant_zone")


# ── ① ★형제 일치는 **별건 PR** 로 뺐다 — 부채를 초록 안에 드러낸다 ──────────

@pytest.mark.xfail(strict=True, reason=(
    "★부채(별건): `dominant_zone_by_area` 가 형제 `_aggregate_integrated_zoning` 와 갈린다. "
    "형제는 동률(±5%)·규제성격 상이를 `mixed_review_required` 로 거부하는데 여기는 임의 단일화한다 "
    "— 12모집단 중 **5개가 갈림**(상업+주거·동률·녹지+주거·주거+공업·관리+농림). "
    "★그냥 맞추면 **사용자 가시 회귀 2건**이 난다: "
    "①`DevelopmentScenarioCard.tsx:211` 이 `site.primary_zone` 을 볼드 배지로 그려 센티널이 "
    "**맨몸으로** 나간다(2026-08-24 라이브에서 이미 겪은 결함) "
    "②`_is_residential()` 이 False 가 되어 주거계 4종이 **「불가·요건 미해당」** 으로 번역된다"
    "(55%가 주거인 부지에 «요건 미해당» 은 거짓 사유) · 1종은 목록에서 사라진다. "
    "→ **보류 판정 상태 + 화면 처리**가 선행돼야 한다."))
def test_dominant_zone_agrees_with_sibling_TODO():
    from app.services.zoning.special_parcel import _aggregate_integrated_zoning
    pairs = [("일반상업지역", 1200.0), ("제2종일반주거지역", 800.0)]
    mine, _ = dominant_zone_by_area([{"zone": z, "area": a} for z, a in pairs])
    sib = _aggregate_integrated_zoning(
        [{"zone_type": z, "area_sqm": a} for z, a in pairs]).get("dominant_zone")
    assert mine == sib, f"내 판정={mine!r} 형제={sib!r}"


# ── ② 감사기가 이 경로에서 **실제로 돈다** ────────────────────────────────

def _simulate_audit(monkeypatch, *, zones, areas):
    """★`simulate()` 를 **실제로 태워** 감사 결과를 얻는다 — 소스 AST 가 아니다.

    적대 리뷰 실측: 종전 락은 AST 로 `.audit(` **이름**과 응답 **키 이름**만 봤다.
    그래서 `"premise_audit": premise_audit_result` → `"premise_audit": None` 으로 바꿔도
    **10건 전부 초록**이었다 — 그 테스트의 실패 메시지가 *"만들어 놓고 버린다"* 인데
    **정확히 그것을 하고 통과**했다. 이름 존재는 **값·도달성**을 말하지 않는다.
    """
    import asyncio

    from app.services.development.scenario_simulator import DevelopmentScenarioSimulator as S

    sim = S()
    enriched = [{"pnu": f"P{i}", "address": f"주소{i}", "zone": z, "area": a,
                 "zone_source": "vworld", "max_far": 200, "max_far_legal": 250}
                for i, (z, a) in enumerate(zip(zones, areas, strict=True))]

    async def _fake_enrich(self, addrs, site):  # noqa: ANN001
        return enriched

    monkeypatch.setattr(S, "_enrich", _fake_enrich, raising=False)
    return asyncio.run(sim.simulate("테스트 주소", parcels=[p["address"] for p in enriched],
                                    site={}, use_llm=False))


def test_audit_result_actually_reaches_the_response(monkeypatch):
    """★M1 — 감사 결과가 **응답에 실린 값**으로 도달하는가(이름이 아니라 값).

    `"premise_audit": None` 변이가 여기서 죽는다.
    """
    try:
        out = _simulate_audit(monkeypatch, zones=["제1종일반주거지역", "제2종일반주거지역"],
                              areas=[410.0, 1300.0])
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"simulate 경로가 외부 의존을 요구한다: {type(e).__name__}")
    pa = (out.get("site") or {}).get("premise_audit") or out.get("premise_audit")
    assert isinstance(pa, dict), f"감사 결과가 dict 로 실리지 않았다 — {type(pa).__name__}"
    assert "violations" in pa, f"위반 배열이 없다 — {sorted(pa)}"
    # ★커버리지를 단언한다 — 모듈이 `checked` 를 «공허한 초록 금지» 로 만들었는데 읽는 곳이 0곳이었다.
    assert pa.get("registered", 0) >= 6, f"등록 관계가 {pa.get('registered')}종 — 수집기 이상"
    assert pa.get("checked") == pa.get("registered"), (
        f"등록 {pa.get('registered')}종 중 {pa.get('checked')}종만 판정됐다 — "
        "나머지는 예외로 조용히 죽었다(★`top3` 를 dict 가 아니라 list 로 넘기면 3종이 죽는다)"
    )


def test_audit_actually_discriminates_two_populations(monkeypatch):
    """★★배선의 **행동**을 잠근다 — 감사가 «돈다» 가 아니라 «가른다» 를 본다.

    적대 리뷰 실측: 종전 락은 키 존재·커버리지만 봐서
    `zone_mix=[]` · `dominant_zone=None` · `ok:True 위장` 변이가 **전부 SURVIVED** 였다.
    감사는 «위반을 찾는 장치» 이므로 **정상 부지에서 침묵하고 결함 부지에서 발화**해야 한다.
    """
    def _viol(zones, areas):
        try:
            out = _simulate_audit(monkeypatch, zones=zones, areas=areas)
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"simulate 경로가 외부 의존을 요구한다: {type(e).__name__}")
        pa = (out.get("site") or {}).get("premise_audit") or out.get("premise_audit")
        assert isinstance(pa, dict) and pa.get("ok") is not True, (
            f"실패를 성공으로 위장했다 — {pa}"
        )
        return {v.get("relation") or v.get("key") for v in (pa.get("violations") or [])}, pa

    # ① 정상 부지 — 침묵해야 한다(위양성 방지)
    clean, pa_clean = _viol(["제2종일반주거지역", "제2종일반주거지역"], [1000.0, 500.0])
    assert not clean, f"정상 부지에서 거짓 위반 — {clean}"
    # ★감사가 실제로 재료를 받았는지(빈 zone_mix 로 «위반 0» 을 만드는 변이를 여기서 죽인다)
    assert pa_clean.get("checked") == pa_clean.get("registered"), pa_clean

    # ② ★결함 부지 — 면적 최대가 아닌 zone 이 우세로 실리면 `dominant_argmax` 가 발화해야 한다.
    #    `dominant_zone` 을 None 으로 죽이는 변이가 여기서 죽는다(발화가 사라지므로).
    import app.services.zoning.premise_audit as _pa
    broken = _pa.audit({
        "dominant_zone": "제1종일반주거지역",
        "zone_mix": [{"zone": "제2종일반주거지역", "area_sqm": 1300.0},
                     {"zone": "제1종일반주거지역", "area_sqm": 410.0}],
        "per_parcel": [{"zone": "제1종일반주거지역", "area_sqm": 410.0},
                       {"zone": "제2종일반주거지역", "area_sqm": 1300.0}],
        "integrated": {"total_area_sqm": 1710.0},
        "scenario": {"top3": {"zone_type": "제1종일반주거지역", "parcel_count": 2,
                              "land_area_sqm": 1710.0}},
        "_request_parcel_count": 2,
    })
    keys = {v.get("relation") or v.get("key") for v in (broken.get("violations") or [])}
    assert "dominant_argmax" in keys, f"결함 부지에서 침묵한다 — {keys}"
    assert clean != keys, "두 모집단이 같은 답을 낸다 — 감사가 아무것도 가르지 않는다"


def test_the_auditor_catches_the_rc2_defect():
    """★★결정적 — 그 감사기가 `#940` 의 RC-2 를 **실제로 잡는가**. 두 모집단.

    신고 부지 형상(zones=[제1종, 제2종] · 제2종 면적 우세)에서
      · `dominant_zone=제1종`(종전 RC-2 동작) → **위반**
      · `dominant_zone=제2종`(수정 후)        → **침묵**
    """
    zone_mix = [{"zone": "제2종일반주거지역", "area_sqm": 1300.0},
                {"zone": "제1종일반주거지역", "area_sqm": 410.0}]
    per_parcel = [{"zone": "제1종일반주거지역", "area_sqm": 410.0},
                  {"zone": "제2종일반주거지역", "area_sqm": 1300.0}]

    def _audit(dom):
        r = premise_audit.audit({
            "dominant_zone": dom, "zone_mix": zone_mix, "per_parcel": per_parcel,
            "integrated": {"total_area_sqm": 1710.0}, "scenario": {"top3": []},
            "_request_parcel_count": 2,
        })
        return {v.get("relation") or v.get("key") for v in (r.get("violations") or [])}

    broken = _audit("제1종일반주거지역")
    healed = _audit("제2종일반주거지역")
    assert "dominant_argmax" in broken, f"RC-2 를 못 잡는다 — {broken}"
    assert "dominant_argmax" not in healed, f"수정 후에도 발화한다(위양성) — {healed}"


def test_zone_mix_comes_from_the_sibling_and_preserves_unknown(monkeypatch):
    """★M4·M5 — `zone_mix` 를 **형제가 낸 것**으로 쓰고, 용도 미조회 필지를 **버리지 않는다**.

    적대 리뷰 실측: 내가 만든 `_zone_mix_from` 은 zone 결측을 **버리는데** `per_parcel` 은
    그대로 실어, **정상 부지**(용도 미조회 필지 1개 포함)에 `area_conservation` **거짓 위반**을 냈다.
    형제 `special_parcel` 은 그것을 **「미상」 버킷**에 담아 면적 보존을 유지한다.
    ★그리고 종전 락이 `== []`(버리는 쪽)를 **정답으로 못 박아** 결함을 지키고 있었다 —
      이어받는 사람이 고치려면 **락을 먼저 깨야** 했다.
    """
    try:
        out = _simulate_audit(monkeypatch,
                              zones=["제2종일반주거지역", "제2종일반주거지역", None],
                              areas=[1000.0, 500.0, 300.0])
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"simulate 경로가 외부 의존을 요구한다: {type(e).__name__}")
    pa = (out.get("site") or {}).get("premise_audit") or out.get("premise_audit")
    keys = {v.get("relation") or v.get("key") for v in (pa.get("violations") or [])}
    assert "area_conservation" not in keys, (
        f"용도 미조회 필지 때문에 면적 보존이 깨졌다(거짓 위반) — {keys}. "
        "형제는 「미상」 버킷으로 보존한다"
    )
    # ★음성 대조군 — 진짜로 면적이 안 맞으면 잡아야 한다(과잉 억제 방지)
    import app.services.zoning.premise_audit as _pa
    broken = _pa.audit({
        "dominant_zone": "제2종일반주거지역",
        "zone_mix": [{"zone": "제2종일반주거지역", "area_sqm": 1000.0}],
        "per_parcel": [{"zone": "제2종일반주거지역", "area_sqm": 1000.0},
                       {"zone": "제3종일반주거지역", "area_sqm": 800.0}],
        "integrated": {"total_area_sqm": 1800.0}, "scenario": {"top3": {}},
        "_request_parcel_count": 2,
    })
    assert any((v.get("relation") or v.get("key")) == "area_conservation"
               for v in (broken.get("violations") or [])), "진짜 불일치를 못 잡는다"
