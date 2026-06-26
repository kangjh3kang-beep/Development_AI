"""C2R 렌더 브리프 합성 테스트 — 인벨로프 재사용·필드 완전성·근거계약·결정론.

외부 키 없이 전부 통과해야 한다(순수 결정론 합성).
"""

from app.services.c2r.render_brief import synthesize_brief
from app.services.c2r.think_before import evaluate
from app.services.site_score.solar_envelope_service import compute_buildable_envelope


def _sample_parcel(zone: str = "제2종일반주거지역") -> dict:
    return {
        "address": "서울특별시 강남구 역삼동 123-45",
        "pnu": "1168010100101230045",
        "zone_type": zone,
        "zone_source": "vworld_land_info",
        "zone_limits": {"max_bcr_pct": 60, "max_far_pct": 250, "max_height_m": None,
                        "max_floors": None},
        "land_area_sqm": 660.0,
        "coordinates": {"lat": 37.5, "lon": 127.03},
        "warnings": [],
    }


def _sample_envelope(zone: str = "제2종일반주거지역") -> dict:
    # ★기존 primitive 재사용 — 가짜 인벨로프를 만들지 않는다.
    return compute_buildable_envelope(
        land_area_sqm=660.0, zone=zone,
        bcr_limit_pct=60, far_limit_pct=250, latitude=37.5,
    )


REQUIRED_KEYS = [
    "role", "site_context", "envelope_constraints", "program", "design_language",
    "materials", "environment", "camera", "assumptions", "accuracy_guards",
    "negative", "success_criteria", "output",
]


def test_brief_has_all_required_fields():
    brief = synthesize_brief(
        parcel=_sample_parcel(), envelope=_sample_envelope(),
        program={"building_use": "공동주택", "scale": "중층"},
    )
    for key in REQUIRED_KEYS:
        assert key in brief, f"브리프에 필수 키 누락: {key}"
    assert isinstance(brief["assumptions"], list)
    assert isinstance(brief["accuracy_guards"], list)
    assert isinstance(brief["negative"], list)
    assert isinstance(brief["success_criteria"], list)


def test_envelope_constraints_carry_evidence_contract():
    """건폐율/용적률/높이/공지 제약에 basis/source/confidence가 붙는다(근거계약)."""
    brief = synthesize_brief(parcel=_sample_parcel(), envelope=_sample_envelope())
    ec = brief["envelope_constraints"]
    for field in ("building_coverage_ratio_pct", "floor_area_ratio_pct",
                  "max_height_m", "max_floors", "open_space_setback_m"):
        assert field in ec
        c = ec[field]
        assert "value" in c and "basis" in c and "source" in c and "confidence" in c
    # 건폐율은 인벨로프(60%)에서 그대로 와야 한다(가짜값 아님).
    assert ec["building_coverage_ratio_pct"]["value"] == 60.0


def test_brief_reuses_envelope_values_not_fabricated():
    """브리프 program의 층수/연면적은 인벨로프 산출값을 그대로 재사용한다."""
    env = _sample_envelope()
    brief = synthesize_brief(parcel=_sample_parcel(), envelope=env)
    assert brief["program"]["target_floors"] == env.get("max_floors")
    expected_gfa = env.get("effective_gfa_sqm") or env.get("envelope_gfa_sqm")
    assert brief["program"]["gfa_sqm"] == expected_gfa


def test_karpathy_guards_present():
    """Karpathy 4원칙이 accuracy_guards/negative/success_criteria에 반영된다."""
    brief = synthesize_brief(parcel=_sample_parcel(), envelope=_sample_envelope())
    guards_text = " ".join(brief["accuracy_guards"])
    neg_text = " ".join(brief["negative"])
    # Surgical: 대지경계/스카이라인 보존
    assert "대지경계" in guards_text or "스카이라인" in guards_text
    # Simplicity: 요청 외 장식 금지
    assert "장식" in neg_text or "조경" in neg_text
    # Goal-Driven: 성공 기준 존재
    assert len(brief["success_criteria"]) >= 1


def test_brief_is_deterministic():
    """같은 입력이면 같은 브리프(결정론)."""
    p, e = _sample_parcel(), _sample_envelope()
    b1 = synthesize_brief(parcel=p, envelope=e, program={"building_use": "공동주택"})
    b2 = synthesize_brief(parcel=p, envelope=e, program={"building_use": "공동주택"})
    assert b1 == b2


def test_missing_area_honest_in_assumptions():
    """대지면적 미확보 시 가짜값 없이 가정에 정직 표기."""
    parcel = _sample_parcel()
    parcel["land_area_sqm"] = None
    env = {"error": "대지면적 미확보", "applies_north_light": None}
    brief = synthesize_brief(parcel=parcel, envelope=env)
    joined = " ".join(brief["assumptions"])
    assert "면적" in joined


def test_footprint_fallback_when_envelope_lacks_bcr_footprint():
    """인벨로프에 bcr_footprint_sqm 가 없으면 대지면적×건폐율로 폴백(비-정북일조 용도지역)."""
    parcel = _sample_parcel()  # land_area 660, max_bcr 60
    # bcr_footprint_sqm 없이 bcr_pct 만 있는 인벨로프(비-정북일조 분기 모사)
    env = {"bcr_pct": 60.0, "max_floors": 10, "envelope_gfa_sqm": 1650.0}
    brief = synthesize_brief(parcel=parcel, envelope=env)
    # 660 × 0.60 = 396.0 (가짜가 아닌 산출 폴백)
    assert brief["program"]["footprint_sqm"] == 396.0


def test_footprint_none_when_truly_unknown():
    """면적·건폐율 모두 미상이면 가짜값 없이 None(정직)."""
    parcel = _sample_parcel()
    parcel["land_area_sqm"] = None
    parcel["zone_limits"] = {}
    env = {"max_floors": 5}
    brief = synthesize_brief(parcel=parcel, envelope=env)
    assert brief["program"]["footprint_sqm"] is None


def test_requested_floors_exceeding_envelope_blocks_think_before():
    """사용자 요청 층수가 인벨로프 상한을 초과하면 Think-Before가 진행을 차단(모순)."""
    env = _sample_envelope()
    max_floors = env.get("max_floors")
    brief = synthesize_brief(
        parcel=_sample_parcel(), envelope=env,
        program={"building_use": "공동주택", "target_floors": (max_floors or 5) + 20},
    )
    # 요청 층수가 envelope 와 분리되어 브리프에 반영
    assert brief["program"]["target_floors"] == (max_floors or 5) + 20
    verdict = evaluate(brief)
    assert verdict["proceed"] is False
    assert any("층수" in q for q in verdict["open_questions"])
