"""임야(산지) 공식 산림데이터 게이트(E1) 검증.

★배경(레드팀 P1-2): 임목본수도·경사도는 인허가급 데이터가 아니다. 산림청 공식 조사데이터
(산지구분·평균경사도·입목축적 등)가 없으면 산지전용 확정 판단이 불가하므로, 임야 필지는
'확정 설계'를 내지 않고 '참고용 예비안(NEEDS_OFFICIAL_SURVEY)'으로만 강등돼야 한다.

이 테스트는 임야 지목이 NEEDS_OFFICIAL_SURVEY로 판정되고, 게이트가 TENTATIVE(참고안)로
환원되며, 정직-실패 문구와 forest_facts(전부 미상=None)가 붙는지 확인한다.
"""
from app.services.zoning.special_parcel import (
    _RANK,
    GATE_TENTATIVE_DEVELOPABILITY,
    _rule_by_land_category,
    detect_multi_parcel,
    detect_special_parcel,
    gate_decision,
    tentative_marker,
)

# 정직-실패 마커(적어도 하나는 포함돼야 임야 필지가 '확정 아님·참고안·공식조사'로 고지된 것).
_HONEST_SURVEY_MARKERS = ("확정 아님", "참고", "공식")


def test_forest_land_category_needs_official_survey():
    """(a) 임야/산림 지목 → developability==NEEDS_OFFICIAL_SURVEY, official_survey_required True,
    forest_facts에 정량 필드가 전부 미상(None)으로 존재."""
    for cat in ("임야", "산림", "임야(산지)"):
        rule = _rule_by_land_category(cat)
        assert rule is not None, f"{cat} 규칙이 감지되지 않음"
        assert rule["developability"] == "NEEDS_OFFICIAL_SURVEY", f"{cat}: {rule['developability']}"
        # 공식조사 필요·확정 차단 신호.
        assert rule["official_survey_required"] is True
        assert rule["blocking_unknown"] is True
        # forest_facts — E3가 채울 정량 필드가 현재는 전부 None(무날조).
        facts = rule["forest_facts"]
        assert isinstance(facts, dict)
        expected_keys = {
            "보전산지_여부", "산지구분", "평균경사도_pct", "표고비율_pct",
            "입목축적_per_ha", "관할평균_입목축적_per_ha", "임상", "official_data_source",
        }
        assert set(facts.keys()) == expected_keys, f"forest_facts 키 불일치: {facts.keys()}"
        assert all(v is None for v in facts.values()), "forest_facts 정량 필드는 아직 전부 미상(None)이어야 함"
        # 산림조사 관련 선행요건이 확장됐는지.
        prereqs = " ".join(rule["permit_prerequisites"])
        assert "산림조사서" in prereqs and "대체산림자원조성비" in prereqs
        # legal_ref_keys는 forest_conversion 유지.
        assert rule["legal_ref_keys"] == ["forest_conversion"]


def test_gate_decision_forest_is_tentative():
    """(b) gate_decision("NEEDS_OFFICIAL_SURVEY", None) == "TENTATIVE"(참고안 — BLOCK도 PASS도 아님)."""
    assert gate_decision("NEEDS_OFFICIAL_SURVEY", None) == "TENTATIVE"
    # 소문자/공백 정규화도 안전.
    assert gate_decision(" needs_official_survey ", None) == "TENTATIVE"
    # 대조군: 확정 개발부지가 아님을 명시(PASS 아님).
    assert gate_decision("POSSIBLE", "YES") == "PASS"


def test_tentative_marker_forest_survey_text():
    """(c) tentative_marker("NEEDS_OFFICIAL_SURVEY", None) → 공식 산림조사 필요 정직 문구."""
    msg = tentative_marker("NEEDS_OFFICIAL_SURVEY", None)
    assert "공식 산림데이터" in msg
    assert "산림조사서" in msg
    assert "확정" in msg  # 확정 아님을 명시
    # 산지구분·경사도·입목축적 정량 항목이 문구에 언급되는지(정직 고지).
    assert "평균경사도" in msg and "입목축적" in msg


def test_rank_contains_needs_official_survey():
    """(d) _RANK에 새 값이 잠정(=CONDITIONAL와 동일 값 2)으로 존재. 기존 값 불변."""
    assert "NEEDS_OFFICIAL_SURVEY" in _RANK
    assert _RANK["NEEDS_OFFICIAL_SURVEY"] == _RANK["CONDITIONAL"] == 2
    # 기존 등급 값은 그대로.
    assert _RANK["POSSIBLE"] == 0 and _RANK["BLOCKED"] == 4 and _RANK["PRECONDITION"] == 3


# ──────────────────────────────────────────────────────────────────────────
# 2차 수정(E1 회귀) 검증 — 하드코딩 개발가능성 튜플이 NEEDS_OFFICIAL_SURVEY를 놓쳐,
#   임야 필지(resolvable="YES")에 "개발 가능합니다"/"표준 절차로 해결 가능" 안심 문구가
#   붙던 회귀를 막는다. caveat·honest·다필지 disclosure가 SSOT 멤버십으로 판정되는지 확인.
#   (아래 테스트들은 수정 前 코드에선 실패한다: 약한 else 문구에 "가능합니다"가 들어갔으므로.)
# ──────────────────────────────────────────────────────────────────────────


def test_detect_special_parcel_forest_caveat_honest_are_tentative():
    """단일 임야 필지 → development_caveat·honest_disclosure가 '개발 가능합니다'로 오고지되지 않고,
    '확정 아님/참고/공식 산림조사 필요' 정직 문구를 담는다(레드팀 지적 회귀 차단)."""
    r = detect_special_parcel({"land_category": "임야", "zone_type": "계획관리지역"})
    assert r is not None
    assert r["developability"] == "NEEDS_OFFICIAL_SURVEY"
    assert r["resolvable"] == "YES"  # 임야는 resolvable=YES라 하드코딩 else로 새던 지점.
    caveat = r["development_caveat"]
    honest = r["honest_disclosure"]
    # 안심 문구 금지: "가능합니다"가 들어가면 게이트(참고안)와 모순.
    assert "가능합니다" not in caveat, f"caveat가 여전히 '가능합니다'를 포함: {caveat}"
    assert "가능합니다" not in honest, f"honest가 여전히 '가능합니다'를 포함: {honest}"
    # 정직-실패 마커 포함(확정 아님 / 참고 / 공식).
    assert any(m in caveat for m in _HONEST_SURVEY_MARKERS), caveat
    assert any(m in honest for m in _HONEST_SURVEY_MARKERS), honest
    # 산림 특화 정직 문구가 실제로 실려 있는지(공식 산림데이터·산림조사서).
    assert "산림조사서" in honest and "공식 산림데이터" in honest


def test_detect_special_parcel_conditional_not_regressed():
    """대조군: 농지(CONDITIONAL 성격, resolvable=YES) 등 다른 특이 케이스는 여전히 잠정
    정직 문구를 받아야 한다(2차 수정이 기존 케이스를 퇴행시키지 않음)."""
    r = detect_special_parcel({"land_category": "답", "zone_type": "계획관리지역"})
    if r is not None:  # 농지 규칙이 감지되면
        honest = r["honest_disclosure"]
        # 잠정 등급이면 '확정 아님/잠재/조건' 톤이 유지되고 안심 단정이 없어야 한다.
        if r["developability"] in GATE_TENTATIVE_DEVELOPABILITY:
            assert "가능합니다" not in honest, honest


def test_detect_multi_parcel_forest_disclosure_is_tentative():
    """다필지 세트에 임야가 섞이면(임야는 resolvable=YES) 사업 게이트가 잠정으로 남고,
    disclosure가 '표준 절차로 해결 가능'이 아니라 '확정 아님·공식조사' 정직 고지를 준다."""
    m = detect_multi_parcel([
        {"land_category": "임야", "zone_type": "계획관리지역"},
        {"land_category": "대", "zone_type": "제2종일반주거지역"},
    ])
    assert m["developability"] == "NEEDS_OFFICIAL_SURVEY"
    disclosure = m["honest_disclosure"]
    assert "해결 가능" not in disclosure, f"다필지 disclosure가 여전히 '해결 가능': {disclosure}"
    assert any(mk in disclosure for mk in _HONEST_SURVEY_MARKERS), disclosure
    # 권고에 공식 산림데이터 확보 안내가 실려야 한다.
    assert "산림조사서" in m["recommendation"] or "공식 산림데이터" in m["recommendation"]


def test_scenario_gate_membership_surfaces_forest_disclosure():
    """scenario_simulator(라인~333)의 게이트 판정 재현 — 임야 special_gate가 SSOT 멤버십
    (GATE_TENTATIVE_DEVELOPABILITY)에 걸려 최상위 honest_disclosure가 노출돼야 한다.
    수정 前 하드코딩 튜플('CONDITIONAL','PRECONDITION','CAUTION')은 이를 놓쳐 노출 안 됐다."""
    sg = detect_special_parcel({"land_category": "임야", "zone_type": "계획관리지역"})
    dev = sg.get("developability")
    # 2차 수정된 노출 조건(SSOT 멤버십 + CAUTION).
    surfaces = bool(sg and (dev in GATE_TENTATIVE_DEVELOPABILITY or dev == "CAUTION"))
    assert surfaces, f"임야 게이트가 최상위 disclosure를 노출하지 못함: developability={dev}"
    # 수정 前 하드코딩 튜플이었다면 놓쳤을 것(회귀 근거).
    assert dev not in ("CONDITIONAL", "PRECONDITION", "CAUTION"), (
        "이 테스트는 NEEDS_OFFICIAL_SURVEY가 옛 튜플에 없었음을 전제로 한다"
    )
    # 노출되는 disclosure가 정직-실패 문구인지.
    assert any(mk in sg["honest_disclosure"] for mk in _HONEST_SURVEY_MARKERS)


# ──────────────────────────────────────────────────────────────────────────
# T1(경사도 고아 데이터 배선)·T3(임목축적 150% 비교)·T4(부담금 고지) — E-gate 배선 검증.
#   ★비협상 원칙: 어떤 관측데이터(DEM·산림청 커넥터)가 주입돼도 developability
#   (NEEDS_OFFICIAL_SURVEY)·official_survey_required는 절대 완화되지 않는다(예비판정 필드만 가산).
# ──────────────────────────────────────────────────────────────────────────
import math  # noqa: E402

_FOREST_INPUT = {"land_category": "임야", "zone_type": "계획관리지역"}


def _deg_to_pct(deg: float) -> float:
    return math.tan(math.radians(deg)) * 100.0


def _forest_factor(r: dict) -> dict:
    return next(f for f in r["factors"] if isinstance(f.get("forest_facts"), dict))


class TestTerrainSlopeWiring:
    """T1 — SRTM DEM terrain_facts 주입 + 예비판정(조례값 우선, 없으면 별표4 25도)."""

    def test_no_terrain_identical_to_current(self):
        """terrain/forest 미제공 → 현행과 완전 동일(회귀 0). 예비판정 필드도 미부착."""
        plain = detect_special_parcel(dict(_FOREST_INPUT))
        kw = detect_special_parcel(dict(_FOREST_INPUT), terrain_facts=None,
                                   forest_data=None, slope_criteria=None)
        assert plain == kw
        assert "forest_preliminary_assessment" not in plain
        f = _forest_factor(plain)
        assert "preliminary_assessment" not in f
        # forest_facts 정량 필드는 여전히 전부 미상(None) — 무날조.
        assert all(f["forest_facts"][k] is None for k in (
            "평균경사도_pct", "입목축적_per_ha", "관할평균_입목축적_per_ha", "산지구분"))

    def test_dem_18deg_default_criteria_preliminary_fit(self):
        """DEM 18°(≈32.5%) vs 국가기준 25°(tan25°≈46.6%) → '예비 적합 가능성'."""
        dem = round(_deg_to_pct(18.0), 2)
        r = detect_special_parcel(dict(_FOREST_INPUT), terrain_facts={
            "평균경사도_pct": dem, "최대경사도_pct": 55.0, "source": "SRTM30_DEM"})
        f = _forest_factor(r)
        # forest_facts에 값 주입 + source/정확도한계 명기(설명가능성).
        assert f["forest_facts"]["평균경사도_pct"] == dem
        assert f["forest_facts"]["경사도_source"] == "SRTM30_DEM"
        assert "공식 평균경사도조사서 아님" in f["forest_facts"]["경사도_정확도한계"]
        slope = f["preliminary_assessment"]["slope"]
        assert "예비 적합" in slope["judgment"]
        assert slope["criteria_deg"] == 25.0
        assert abs(slope["criteria_pct"] - _deg_to_pct(25.0)) < 0.1  # tan(25°)≈46.6%
        assert "별표4" in slope["criteria_source"]
        # %↔도 변환 명시(tan) + 산식 동반(설명가능성).
        assert "tan" in slope["formula"]
        assert any("조례" in c for c in slope["caveats"])  # 지자체 조례 별도 확인
        assert any("공식 평균경사도조사서 아님" in lim for lim in slope["limitations"])
        assert slope["legal_ref_keys"] == ["forest_permit_criteria"]

    def test_dem_boundary_band_requires_official_survey(self):
        """기준×0.8 < DEM ≤ 기준 → '경계 — 공식조사 필수'."""
        r = detect_special_parcel(dict(_FOREST_INPUT),
                                  terrain_facts={"평균경사도_pct": 40.0, "source": "SRTM30_DEM"})
        slope = _forest_factor(r)["preliminary_assessment"]["slope"]
        assert "경계" in slope["judgment"] and "공식조사" in slope["judgment"]

    def test_dem_35deg_preliminary_exceed(self):
        """DEM 35°(≈70.0%) > 기준 46.6% → '예비 초과'(대체부지 검토 권고)."""
        r = detect_special_parcel(dict(_FOREST_INPUT), terrain_facts={
            "평균경사도_pct": round(_deg_to_pct(35.0), 2), "source": "SRTM30_DEM"})
        slope = _forest_factor(r)["preliminary_assessment"]["slope"]
        assert "예비 초과" in slope["judgment"] and "대체부지" in slope["judgment"]

    def test_ordinance_slope_criteria_takes_precedence(self):
        """조례값(T2 resolve_slope_criteria 계약) 제공 시 국가기준 25° 대신 조례 기준 적용."""
        dem = round(_deg_to_pct(18.0), 2)  # 32.49% — 조례 17.5°(31.53%)는 초과, 25°면 적합.
        r = detect_special_parcel(
            dict(_FOREST_INPUT),
            terrain_facts={"평균경사도_pct": dem, "source": "SRTM30_DEM"},
            slope_criteria={"slope_deg": 17.5, "ordinance_name": "OO군 도시계획조례",
                            "verified": "api_parsed"})
        slope = _forest_factor(r)["preliminary_assessment"]["slope"]
        assert slope["criteria_deg"] == 17.5
        assert "OO군 도시계획조례" in slope["criteria_source"]
        assert "예비 초과" in slope["judgment"]

    def test_terrain_on_non_forest_parcel_is_noop(self):
        """임야가 아닌 특이부지에 terrain_facts를 줘도 아무 변화 없음(과주입 방지)."""
        base = {"land_category": "학교용지", "zone_type": "일반상업지역"}
        plain = detect_special_parcel(dict(base))
        with_terrain = detect_special_parcel(dict(base), terrain_facts={
            "평균경사도_pct": 70.0, "source": "SRTM30_DEM"})
        assert plain == with_terrain


class TestForestStockingWiring:
    """T3 — 산림청 커넥터 forest_data 주입 + 별표4 150% 비교(둘 다 확보 시에만)."""

    _DATA = {"입목축적_per_ha": 120.0, "관할평균_입목축적_per_ha": 100.0,
             "산지구분": "준보전산지", "source": "data.forest.go.kr"}

    def test_stocking_120pct_preliminary_fit(self):
        r = detect_special_parcel(dict(_FOREST_INPUT), forest_data=dict(self._DATA))
        f = _forest_factor(r)
        # forest_facts 주입(설명가능성 — 출처 동반).
        assert f["forest_facts"]["입목축적_per_ha"] == 120.0
        assert f["forest_facts"]["관할평균_입목축적_per_ha"] == 100.0
        assert f["forest_facts"]["산지구분"] == "준보전산지"
        assert f["forest_facts"]["official_data_source"] == "data.forest.go.kr"
        st = f["preliminary_assessment"]["stocking"]
        assert st["입목축적_비율_pct"] == 120.0
        assert "예비 적합" in st["judgment"]
        assert any("산지관리법 시행령" in b and "별표4" in b for b in st["legal_basis"])
        assert st["legal_ref_keys"] == ["forest_permit_criteria"]

    def test_stocking_160pct_preliminary_exceed(self):
        data = dict(self._DATA, 입목축적_per_ha=160.0)
        r = detect_special_parcel(dict(_FOREST_INPUT), forest_data=data)
        st = _forest_factor(r)["preliminary_assessment"]["stocking"]
        assert st["입목축적_비율_pct"] == 160.0
        assert "예비 초과" in st["judgment"]

    def test_stocking_skipped_when_stock_negative(self):
        """★결함 재현(P1) — 음수 입목축적(-10)은 비율 -10%로 '예비 적합'을 날조하면 안 됨.

        비정상 관측값(음수)은 판정을 생략(skip)하고 사유를 남겨야 한다(무날조·정직게이트).
        """
        data = dict(self._DATA, 입목축적_per_ha=-10.0)
        r = detect_special_parcel(dict(_FOREST_INPUT), forest_data=data)
        pa = _forest_factor(r)["preliminary_assessment"]
        assert pa["stocking"] is None, f"음수 stock인데 판정이 생성됨: {pa['stocking']}"
        assert "음수" in pa["stocking_skip_reason"]
        assert "생략" in pa["stocking_skip_reason"]

    def test_stocking_skipped_when_average_missing(self):
        """관할평균 미확보 → 비교 skip + 사유(비율 날조 금지)."""
        data = {"입목축적_per_ha": 120.0, "관할평균_입목축적_per_ha": None,
                "산지구분": None, "source": "data.forest.go.kr"}
        r = detect_special_parcel(dict(_FOREST_INPUT), forest_data=data)
        pa = _forest_factor(r)["preliminary_assessment"]
        assert pa["stocking"] is None
        assert "관할평균" in pa["stocking_skip_reason"]


class TestGatePreservationInvariant:
    """★비협상 — 어떤 관측데이터 조합에서도 developability·게이트 등급 절대 불변."""

    def test_developability_never_relaxed_by_observations(self):
        plain = detect_special_parcel(dict(_FOREST_INPUT))
        combos = [
            {"terrain_facts": {"평균경사도_pct": 5.0, "source": "SRTM30_DEM"}},   # 매우 완만해도
            {"terrain_facts": {"평균경사도_pct": 70.0, "source": "SRTM30_DEM"}},  # 급경사여도
            {"forest_data": {"입목축적_per_ha": 50.0, "관할평균_입목축적_per_ha": 100.0,
                             "산지구분": "준보전산지", "source": "x"}},
            {"terrain_facts": {"평균경사도_pct": 10.0, "source": "SRTM30_DEM"},
             "forest_data": {"입목축적_per_ha": 80.0, "관할평균_입목축적_per_ha": 100.0,
                             "산지구분": "준보전산지", "source": "x"}},
        ]
        for kw in combos:
            r = detect_special_parcel(dict(_FOREST_INPUT), **kw)
            assert r["developability"] == "NEEDS_OFFICIAL_SURVEY", kw
            assert r["severity_label"] == plain["severity_label"]
            assert r["resolvable"] == plain["resolvable"]
            f = _forest_factor(r)
            assert f["developability"] == "NEEDS_OFFICIAL_SURVEY"
            assert f["official_survey_required"] is True
            assert f["blocking_unknown"] is True
            assert gate_decision(r["developability"], r["resolvable"]) == "TENTATIVE"
            # 예비판정 disclaimer가 '확정 아님'을 명시.
            assert "확정" in f["preliminary_assessment"]["disclaimer"]

    def test_rank_table_unchanged_by_wiring(self):
        # 기존 등급값 절대 불변(0/1/2/3/4). WP-A(접도 access_basis)가 추가한
        #   REQUIRES_AUTHORITY_CONFIRMATION은 CONDITIONAL와 동일한 '잠정' 값 2로만 가산된다
        #   (NEEDS_OFFICIAL_SURVEY와 동일 패턴 — 기존 값 변경·완화 없음).
        assert _RANK == {"POSSIBLE": 0, "CAUTION": 1, "CONDITIONAL": 2,
                         "NEEDS_OFFICIAL_SURVEY": 2, "REQUIRES_AUTHORITY_CONFIRMATION": 2,
                         "PRECONDITION": 3, "BLOCKED": 4}
        # 기존 값이 하나도 변하지 않았음을 명시 재확인(불변식 보존).
        assert _RANK["POSSIBLE"] == 0 and _RANK["CAUTION"] == 1 and _RANK["CONDITIONAL"] == 2
        assert _RANK["NEEDS_OFFICIAL_SURVEY"] == 2 and _RANK["PRECONDITION"] == 3 and _RANK["BLOCKED"] == 4
        assert _RANK["REQUIRES_AUTHORITY_CONFIRMATION"] == _RANK["CONDITIONAL"]


class TestConversionChargeDisclosure:
    """T4 — 농지/임야 게이트에 부담금 존재 고지 + verified legal_ref 연결(C·A 산출 소비)."""

    def test_farmland_charge_notice_and_refs(self):
        r = detect_special_parcel({"land_category": "전", "zone_type": "계획관리지역"})
        f = next(x for x in r["factors"] if x["category"].startswith("농지"))
        cn = f["charge_notice"]
        assert cn["charge_name"] == "농지보전부담금"
        assert "farmland_preservation_charge" in f["legal_ref_keys"]
        verified = {x["key"] for x in f["legal_refs"] if x["url_status"] == "verified"}
        assert "farmland_preservation_charge" in verified
        assert "farmland_conversion" in verified  # 기존 키 보존(가산만)
        assert "농지보전부담금" in r["honest_disclosure"]
        # 공시지가 미제공 → 추정액 미산출(무날조) + 사유.
        assert cn["estimate"] is None and cn["estimate_note"]

    def test_forest_charge_notice_and_refs(self):
        r = detect_special_parcel(dict(_FOREST_INPUT))
        f = _forest_factor(r)
        cn = f["charge_notice"]
        assert cn["charge_name"] == "대체산림자원조성비"
        assert "forest_replacement_charge" in f["legal_ref_keys"]
        verified = {x["key"] for x in f["legal_refs"] if x["url_status"] == "verified"}
        assert "forest_replacement_charge" in verified
        assert "forest_conversion" in verified  # 기존 키 보존
        assert "대체산림자원조성비" in r["honest_disclosure"]
        assert cn["estimate"] is None  # 고시 단가·공시지가 미주입 — 무날조

    def test_farmland_charge_estimate_via_bridge(self):
        """공시지가·면적 확보 시 C(land_conversion_charges) 브리지로 추정액 산출(10만원/㎡×1000㎡→3,000만원)."""
        r = detect_special_parcel({"land_category": "전", "zone_type": "제2종일반주거지역",
                                   "area_sqm": 1000, "official_land_price_per_m2": 100000})
        f = next(x for x in r["factors"] if x["category"].startswith("농지"))
        est = f["charge_notice"]["estimate"]
        assert est is not None
        assert est["amount_won"] == 30_000_000
        assert est["confidence"] == "estimated"

    def test_charge_disclosure_keeps_existing_honest_markers(self):
        """부담금 고지 가산 후에도 기존 정직-실패 문구(산림조사서·확정아님)는 보존."""
        r = detect_special_parcel(dict(_FOREST_INPUT))
        honest = r["honest_disclosure"]
        assert "산림조사서" in honest and "공식 산림데이터" in honest
        assert "가능합니다" not in honest
