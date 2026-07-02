"""P2 구역 규칙(A-districts) — _rules_by_districts additive 규칙 TDD.

① 상수원보호구역(수도법 제7조 원칙 행위제한) PRECONDITION
② 군사기지·군사시설 보호구역(군사기지법 — 국방부 협의) CONDITIONAL
③ 문화재보호구역·역사문화환경보존지역(현상변경 허가) CONDITIONAL
④ 매장유산 유존지역·문화재 지표조사 대상(사업 전 지표조사) CONDITIONAL
⑤ 비오톱 1등급(서울 조례상 개발 불가 소지) PRECONDITION + 강한 경고
⑥ 급경사지 붕괴위험지역(급경사지법) CONDITIONAL
⑦ 성장관리계획구역(국계법 제75조의2·3 — 계획 부합 시 허가) CAUTION
⑧ 수변구역(한강수계법 등) PRECONDITION
⑨ 하천구역·소하천구역(점용허가) CONDITIONAL

+ 오탐 방어(비감지)·복수구역 랭크 병합·기존 규칙/게이트 무회귀.
"""
from app.services.zoning.special_parcel import _rules_by_districts, detect_special_parcel


def _base(districts: list[str]) -> dict:
    """일상 지목(대)·주거지역 — 구역 규칙만 발동하는 최소 입력."""
    return {"land_category": "대", "zone_type": "제2종일반주거지역",
            "special_districts": districts}


def _rules(districts: list[str], zone: str = "제2종일반주거지역") -> list[dict]:
    return _rules_by_districts(districts, zone)


def _pick(rules: list[dict], token: str, developability: str | None = None) -> list[dict]:
    out = [r for r in rules if token in r.get("category", "")]
    if developability is not None:
        out = [r for r in out if r.get("developability") == developability]
    return out


# ── ① 상수원보호구역 — 수도법 제7조 원칙 행위제한 → PRECONDITION ──

def test_water_source_protection_zone_precondition():
    rules = _rules(["상수원보호구역"])
    hits = _pick(rules, "상수원보호구역", "PRECONDITION")
    assert len(hits) == 1, "상수원보호구역은 PRECONDITION 신규 규칙이 정확히 1건 발동해야 함"
    f = hits[0]
    assert "water_source_protection" in f["legal_ref_keys"]
    assert any("수도법" in b for b in f["legal_basis"])
    assert any("관할" in s for s in f["implications"]), "관할 확인 고지 필수"
    # 기존 광역 규칙(CONDITIONAL)도 보존 — additive.
    assert _pick(rules, "상수원보호구역/수변구역", "CONDITIONAL"), "기존 규칙 불변(공존)"


def test_water_source_keyword_alone_no_new_rule():
    """오탐 방어: '상수원' 단독(구역명 미명시)은 기존 CONDITIONAL만, 신규 PRECONDITION 미발동."""
    rules = _rules(["상수원 상류 인접"])
    assert not _pick(rules, "", "PRECONDITION")
    assert _pick(rules, "상수원보호구역/수변구역", "CONDITIONAL"), "기존 규칙은 여전히 발동"


# ── ② 군사기지·군사시설 보호구역 — 국방부(관할부대) 협의 → CONDITIONAL ──

def test_military_base_protection_zone_conditional():
    rules = _rules(["군사기지 및 군사시설 보호구역"])
    hits = _pick(rules, "군사기지")
    assert len(hits) == 1
    f = hits[0]
    assert f["developability"] == "CONDITIONAL"
    assert "military_protection_zone" in f["legal_ref_keys"]
    assert any("군사기지 및 군사시설 보호법" in b for b in f["legal_basis"])
    assert any("관할" in s for s in f["implications"])
    # 게이트 병합: 기존 군사 규칙과 중복 발동해도 동급(CONDITIONAL)이라 게이트 불변.
    sp = detect_special_parcel(_base(["군사기지 및 군사시설 보호구역"]))
    assert sp["developability"] == "CONDITIONAL"


# ── ③ 문화재보호구역·역사문화환경보존지역 — 현상변경 허가 → CONDITIONAL ──

def test_cultural_heritage_env_zone_conditional():
    rules = _rules(["역사문화환경보존지역"])
    hits = _pick(rules, "역사문화환경보존지역")
    assert len(hits) == 1
    f = hits[0]
    assert f["developability"] == "CONDITIONAL"
    assert "cultural_heritage_env" in f["legal_ref_keys"]
    assert any("현상변경" in s for s in f["implications"])
    assert any("관할" in s for s in f["implications"])


def test_cultural_heritage_protection_zone_detected():
    rules = _rules(["문화재보호구역"])
    assert _pick(rules, "문화재보호구역·역사문화환경보존지역")
    # 기존 통합 규칙(문화재/역사문화환경)도 보존.
    assert _pick(rules, "문화재보호구역/역사문화환경 보존지역", "CONDITIONAL")


# ── ④ 매장유산 유존지역·지표조사 대상 → CONDITIONAL ──

def test_buried_heritage_zone_conditional():
    rules = _rules(["매장유산 유존지역"])
    hits = _pick(rules, "매장유산")
    assert len(hits) == 1
    f = hits[0]
    assert f["developability"] == "CONDITIONAL"
    assert "buried_heritage" in f["legal_ref_keys"]
    assert any("지표조사" in s for s in f["implications"])
    assert any("관할" in s for s in f["implications"])


# ── ⑤ 비오톱 1등급 — 서울 조례상 개발 불가 소지 → PRECONDITION + 강한 경고 ──

def test_biotope_grade1_precondition_with_strong_warning():
    rules = _rules(["비오톱1등급"])
    hits = _pick(rules, "비오톱")
    assert len(hits) == 1
    f = hits[0]
    assert f["developability"] == "PRECONDITION"
    assert "biotope_grade1" in f["legal_ref_keys"]
    assert any("불가능할 소지" in s for s in f["implications"]), "강한 경고 문구 필수"
    assert any("조례" in b for b in f["legal_basis"])
    assert any("관할" in s for s in f["implications"])


def test_biotope_grade1_spaced_variant_detected():
    assert _pick(_rules(["비오톱 1등급 토지"]), "비오톱")


def test_biotope_grade2_not_detected():
    """오탐 방어: 2등급 이하는 미발동(1등급 명시에만 발동)."""
    assert not _pick(_rules(["비오톱2등급"]), "비오톱")
    assert not _pick(_rules(["비오톱 2등급"]), "비오톱")


# ── ⑥ 급경사지 붕괴위험지역 → CONDITIONAL ──

def test_steep_slope_hazard_zone_conditional():
    rules = _rules(["급경사지 붕괴위험지역"])
    hits = _pick(rules, "급경사지")
    assert len(hits) == 1
    f = hits[0]
    assert f["developability"] == "CONDITIONAL"
    assert "steep_slope_disaster" in f["legal_ref_keys"]
    assert any("급경사지 재해예방" in b for b in f["legal_basis"])
    assert any("관할" in s for s in f["implications"])


# ── ⑦ 성장관리계획구역 — 계획 부합 시 허가(완화 혜택 병존) → CAUTION ──

def test_growth_management_zone_caution_with_honest_benefit_note():
    rules = _rules(["성장관리계획구역"])
    hits = _pick(rules, "성장관리")
    assert len(hits) == 1
    f = hits[0]
    assert f["developability"] == "CAUTION"
    assert "growth_management_zone" in f["legal_ref_keys"]
    assert any("제75조의2" in b for b in f["legal_basis"])
    # 정직 안내: 제한뿐 아니라 완화 혜택 존재도 안내.
    assert any("완화" in s for s in f["implications"])
    assert any("관할" in s for s in f["implications"])


# ── ⑧ 수변구역 — 한강수계법 등 원칙 행위제한 → PRECONDITION ──

def test_riparian_zone_precondition():
    rules = _rules(["수변구역"])
    hits = [r for r in rules if r.get("developability") == "PRECONDITION"]
    assert len(hits) == 1
    f = hits[0]
    assert "수변구역" in f["category"]
    assert "riparian_zone" in f["legal_ref_keys"]
    assert any("한강수계" in b for b in f["legal_basis"])
    assert any("관할" in s for s in f["implications"])
    # 기존 광역 규칙(수변 → CONDITIONAL)도 공존.
    assert _pick(rules, "상수원보호구역/수변구역", "CONDITIONAL")


# ── ⑨ 하천구역·소하천구역 — 점용허가 → CONDITIONAL ──

def test_river_zone_conditional_occupation_permit():
    rules = _rules(["하천구역"])
    hits = _pick(rules, "하천구역")
    assert len(hits) == 1
    f = hits[0]
    assert f["developability"] == "CONDITIONAL"
    assert "river_occupation" in f["legal_ref_keys"]
    assert any("하천법" in b for b in f["legal_basis"])
    assert any("점용" in s for s in f["implications"])
    assert any("관할" in s for s in f["implications"])


def test_small_river_zone_detected():
    assert _pick(_rules(["소하천구역"]), "하천구역·소하천구역")


def test_river_zone_resolution_paths_are_occupation_not_disposal():
    """하천구역 해결경로는 점용허가(용도폐지·불용처분 아님) — 지목 '하천' BLOCKED 경로와 구분."""
    sp = detect_special_parcel(_base(["하천구역"]))
    f = next(x for x in sp["factors"] if "하천구역" in x["category"])
    assert any("점용" in p for p in f["resolution_paths"])
    assert not any("용도폐지" in p for p in f["resolution_paths"])


# ── 복수구역 랭크 병합 — 종합 게이트 = 최댓값(_RANK) ──

def test_multi_district_gate_merges_to_max_rank():
    sp = detect_special_parcel(_base(["성장관리계획구역", "하천구역", "상수원보호구역"]))
    assert sp["is_special"] is True
    # CAUTION(성장관리) < CONDITIONAL(하천구역) < PRECONDITION(상수원보호구역) → PRECONDITION.
    assert sp["developability"] == "PRECONDITION"
    cats = " ".join(f["category"] for f in sp["factors"])
    assert "성장관리" in cats and "하천구역" in cats and "상수원보호구역" in cats


def test_caution_only_district_keeps_caution_gate():
    sp = detect_special_parcel(_base(["성장관리계획구역"]))
    assert sp["developability"] == "CAUTION"


# ── 기존 규칙·게이트 무회귀 ──

def test_no_districts_no_detection():
    assert _rules([], "제2종일반주거지역") == []
    assert detect_special_parcel(_base([])) is None


def test_greenbelt_still_blocked():
    rules = _rules(["개발제한구역"])
    assert _pick(rules, "개발제한구역", "BLOCKED")
    sp = detect_special_parcel(_base(["개발제한구역"]))
    assert sp["developability"] == "BLOCKED"
    assert sp["resolvable"] == "NO"


def test_legacy_military_and_heritage_rules_unchanged():
    """기존 광역 키워드 규칙 4종의 category·등급이 그대로 보존되는지."""
    rules = _rules(["군사시설", "문화재", "상수원", "수질보전"])
    assert _pick(rules, "군사시설보호구역", "CONDITIONAL")
    assert _pick(rules, "문화재보호구역/역사문화환경 보존지역", "CONDITIONAL")
    assert _pick(rules, "상수원보호구역/수변구역", "CONDITIONAL")


def test_river_land_category_still_blocked_with_disposal_paths():
    """지목 '하천'(공공용지) 경로 무회귀 — BLOCKED + 용도폐지 해결경로 유지."""
    sp = detect_special_parcel({"land_category": "하천", "zone_type": "제2종일반주거지역",
                                "special_districts": []})
    assert sp["developability"] == "BLOCKED"
    f = next(x for x in sp["factors"] if "공공·기반시설" in x["category"])
    assert any("용도폐지" in p for p in f["resolution_paths"])


def test_new_rules_all_have_conservative_disclosure_fields():
    """신규 9종 전부 — legal_basis·permit_prerequisites·관할확인 고지 동반(설명가능성 기본)."""
    blobs = ["상수원보호구역", "군사기지 보호구역", "문화재보호구역", "매장유산 유존지역",
             "비오톱1등급", "급경사지 붕괴위험지역", "성장관리계획구역", "수변구역", "하천구역"]
    tokens = ["상수원보호구역(", "군사기지", "역사문화환경보존지역(", "매장유산",
              "비오톱", "급경사지", "성장관리", "수변구역(", "하천구역·소하천구역"]
    for blob, token in zip(blobs, tokens, strict=True):
        rules = _rules([blob])
        hits = [r for r in rules if token in r.get("category", "")]
        assert hits, f"{blob} 신규 규칙 미발동"
        f = hits[0]
        assert f.get("legal_basis"), f"{blob}: legal_basis 누락"
        assert f.get("legal_ref_keys"), f"{blob}: legal_ref_keys 누락"
        assert f.get("permit_prerequisites"), f"{blob}: permit_prerequisites 누락"
        assert any("관할" in s for s in f["implications"]), f"{blob}: 관할 확인 고지 누락"
