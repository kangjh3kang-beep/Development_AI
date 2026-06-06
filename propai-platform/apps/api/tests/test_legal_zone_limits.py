"""부지분석 할루시네이션 차단 — 법정 한도 SSOT + 하드 검증기 결정론 테스트.

LLM 미호출 경로(한도표·검증기)만 검증하므로 외부 API 없이 결정론적으로 재현된다.
핵심 회귀: 자연녹지(법정 건폐율20%·용적률100%)에 용적률200%/건폐율60%가 산출되던
할루시네이션을 적발(fail/warn)하는지 증명한다.
"""

from app.services.verification.range_rules import run_range_checks
from app.services.zoning.legal_zone_limits import (
    applicable_limits_for,
    check_against_legal,
    legal_limits_for,
    normalize_zone_name,
)


# ── SSOT 한도표 ──
def test_legal_limits_natural_green():
    limits = legal_limits_for("자연녹지지역")
    assert limits is not None
    assert limits["max_bcr_pct"] == 20
    assert limits["max_far_pct"] == 100
    assert "제84" in limits["legal_basis"]


def test_legal_limits_first_general_residential():
    limits = legal_limits_for("제1종일반주거지역")
    assert limits["max_bcr_pct"] == 60
    assert limits["max_far_pct"] == 200


def test_normalize_zone_name_with_spaces():
    assert normalize_zone_name("자연 녹지 지역") == "자연녹지지역"
    assert normalize_zone_name("") is None
    assert normalize_zone_name(None) is None


# ── check_against_legal: 직접 한도 대조 ──
def test_check_natural_green_far_200_flagged():
    # 라이브 사고 재현: 자연녹지 용적률 200% → 법정 100% 초과 → high
    issues = check_against_legal("자연녹지지역", far_pct=200)
    assert len(issues) == 1
    assert issues[0]["severity"] == "high"
    assert "법정한도초과" == issues[0]["type"]
    assert "100%" in issues[0]["note"]


def test_check_natural_green_bcr_60_flagged():
    issues = check_against_legal("자연녹지지역", bcr_pct=60)
    assert any(i["severity"] == "high" and "건폐율" in i["claim"] for i in issues)


def test_check_natural_green_far_100_passes():
    assert check_against_legal("자연녹지지역", far_pct=100, bcr_pct=20) == []


def test_check_first_general_far_200_passes():
    # 1종일반 법정 용적률 200% → 정상(법정 内)
    assert check_against_legal("제1종일반주거지역", far_pct=200) == []


def test_check_first_general_far_250_flagged():
    # 1종일반 법정 200% → 250%는 초과
    issues = check_against_legal("제1종일반주거지역", far_pct=250)
    assert len(issues) == 1
    assert issues[0]["severity"] == "high"


def test_check_unknown_zone_no_flag():
    # 미매칭 용도지역은 법정상한 미상 → 빈 결과(일반 범위규칙에 위임)
    assert check_against_legal("우주정거장지역", far_pct=9999) == []


def test_tolerance_rounding():
    # 반올림 오차(0.5%p 이내)는 통과
    assert check_against_legal("자연녹지지역", far_pct=100.3) == []


# ── run_range_checks 통합: 검증기가 zone_type을 읽어 법정대조 ──
def test_range_checks_natural_green_far_200():
    source = {"zone_type": "자연녹지지역", "land_area_sqm": 1520}
    output = {"effective_far_pct": 200, "effective_bcr_pct": 60}
    issues = run_range_checks("site", source, output)
    high = [i for i in issues if i["severity"] == "high"]
    # 용적률·건폐율 둘 다 법정초과 → high 2건
    assert len(high) >= 2
    assert any("용적률 200%" in i["claim"] for i in high)
    assert any("건폐율 60%" in i["claim"] for i in high)


def test_range_checks_natural_green_legal_values_clean():
    source = {"zone_type": "자연녹지지역", "land_area_sqm": 1520}
    output = {"effective_far_pct": 100, "effective_bcr_pct": 20}
    issues = run_range_checks("site", source, output)
    assert [i for i in issues if i["severity"] == "high"] == []


def test_range_checks_first_general_200_clean():
    source = {"zone_type": "제1종일반주거지역"}
    output = {"effective_far_pct": 200, "effective_bcr_pct": 60}
    issues = run_range_checks("site", source, output)
    assert [i for i in issues if i["severity"] == "high"] == []


def test_range_checks_zone_in_nested_payload():
    # 중첩 페이로드에서도 zone_type을 깊이탐색
    source = {"site": {"zoning": {"zone_type": "자연녹지지역"}}}
    output = {"effective_far": {"effective_far_pct": 200}}
    issues = run_range_checks("site", source, output)
    assert any(i["severity"] == "high" for i in issues)


# ── 인센티브 완화 인지(basis-aware) 3단 판정 ──
def test_basis_natural_green_200_no_basis_stays_high():
    # 자연녹지 200% 근거없음 → high(fail) 유지(원 사고 재현 방지)
    issues = check_against_legal("자연녹지지역", far_pct=200, has_basis=False)
    assert len(issues) == 1
    assert issues[0]["severity"] == "high"


def test_basis_natural_green_200_with_basis_non_incentive_zone_warn():
    # 자연녹지 200%(법정100×2) + 근거 → 인센티브 비대상 + sanity초과 → warn(fail 아님)
    issues = check_against_legal("자연녹지지역", far_pct=200, has_basis=True)
    assert len(issues) == 1
    assert issues[0]["severity"] == "warn"
    assert issues[0]["severity"] != "high"


def test_basis_natural_green_payload_keyword_donation():
    # 페이로드에 "기부채납 30%" 키워드 → 근거 인정. 자연녹지 200%는 sanity로 warn.
    payload = {"notes": "기부채납 30% 적용 가능"}
    issues = check_against_legal("자연녹지지역", far_pct=200, payload=payload)
    assert issues[0]["severity"] == "warn"


def test_basis_first_general_200_passes():
    # 1종일반 200% → 법정内 pass(근거 무관)
    assert check_against_legal("제1종일반주거지역", far_pct=200, has_basis=False) == []
    assert check_against_legal("제1종일반주거지역", far_pct=200, has_basis=True) == []


def test_basis_junjugeo_600_no_basis_high():
    # 준주거 600%(법정500 초과) 근거없음 → high
    issues = check_against_legal("준주거지역", far_pct=600, has_basis=False)
    assert len(issues) == 1
    assert issues[0]["severity"] == "high"


def test_basis_junjugeo_600_district_plan_basis_info():
    # 준주거 600% + "지구단위계획 상한용적률" 근거 → info(정당, fail 아님, sanity 内)
    payload = {"zoning": {"detail": "지구단위계획 상한용적률 적용"}}
    issues = check_against_legal("준주거지역", far_pct=600, payload=payload)
    assert len(issues) == 1
    assert issues[0]["severity"] == "info"
    assert issues[0]["severity"] != "high"


def test_basis_third_general_350_no_basis_high():
    # 3종 350%(법정300 초과) 근거없음 → high
    issues = check_against_legal("제3종일반주거지역", far_pct=350, has_basis=False)
    assert len(issues) == 1
    assert issues[0]["severity"] == "high"


def test_basis_third_general_350_public_rental_info():
    # 3종 350% + "공공임대 건립" 근거 → info(정당)
    payload = {"plan": "공공임대 건립으로 용적률 완화"}
    issues = check_against_legal("제3종일반주거지역", far_pct=350, payload=payload)
    assert len(issues) == 1
    assert issues[0]["severity"] == "info"


def test_basis_relaxation_structured_field():
    # 구조화 필드(완화율)로도 근거 인정
    payload = {"local_ordinance": {"relaxation_ratio_pct": 20}}
    issues = check_against_legal("제3종일반주거지역", far_pct=350, payload=payload)
    assert issues[0]["severity"] == "info"


def test_basis_run_range_checks_with_basis_info():
    # run_range_checks 경유: 페이로드에 역세권 근거 → info(준주거 600%)
    source = {"zone_type": "준주거지역", "notes": "역세권 활성화 시프트 대상"}
    output = {"effective_far_pct": 600}
    issues = run_range_checks("site", source, output)
    far_issues = [i for i in issues if "용적률" in i["claim"]]
    assert far_issues and far_issues[0]["severity"] == "info"
    assert not any(i["severity"] == "high" for i in far_issues)


def test_basis_run_range_checks_no_basis_high():
    # run_range_checks 경유: 근거 없으면 3종 350% → high
    source = {"zone_type": "제3종일반주거지역"}
    output = {"effective_far_pct": 350}
    issues = run_range_checks("site", source, output)
    assert any(i["severity"] == "high" and "용적률" in i["claim"] for i in issues)


# ── 계층 산정(법정범위 → 조례 → 도시군관리계획 → 인센티브) ──
def test_legal_limits_far_range_natural_green():
    # 자연녹지: 법정 용적률 '범위' 50~100%(시행령 제85조).
    limits = legal_limits_for("자연녹지지역")
    assert limits["min_far_pct"] == 50
    assert limits["max_far_pct"] == 100


def test_applicable_limits_legal_range_only_when_no_ordinance():
    # 조례·계획 미보유 → 법정범위 반환 + 조례확인필요(False).
    a = applicable_limits_for("자연녹지지역")
    assert a["legal_min_far_pct"] == 50
    assert a["legal_max_far_pct"] == 100
    assert a["applied_far_pct"] == 100  # 기준은 법정범위 max
    assert a["ordinance_confirmed"] is False
    assert "법정범위" in a["sources"]


def test_applicable_limits_ordinance_value_becomes_applied():
    # 조례 적용값(자연녹지 80%, 법정범위 内) → 적용 법정값으로 반영.
    reg = {"local_ordinance": {"effective_far": 80, "source": "지자체 조례"}}
    a = applicable_limits_for("자연녹지지역", regulation_payload=reg)
    assert a["ordinance_far_pct"] == 80
    assert a["applied_far_pct"] == 80
    assert a["ordinance_confirmed"] is True


def test_applicable_limits_plan_ceiling_overrides():
    # 도시·군관리계획/지구단위계획 상한용적률이 있으면 최우선(법정상한 초과 정당).
    plan = {"districts": [{"district_name": "지구단위계획구역", "plan_far_pct": 200}]}
    a = applicable_limits_for("자연녹지지역", plan_payload=plan)
    assert a["plan_far_pct"] == 200
    assert a["applied_far_pct"] == 200


# ── 검증기: 조례값·계획상한 반영(정당한 상향 오적발 방지 / 무근거 적발 유지) ──
def test_check_natural_green_far_100_within_range_clean():
    # 자연녹지 용적률 100%(법정범위 내) → clean.
    assert check_against_legal("자연녹지지역", far_pct=100) == []


def test_check_natural_green_far_80_ordinance_clean():
    # 자연녹지 80%(조례값 가정) → clean(법정범위 내, 초과 아님 → 빈 결과).
    reg = {"ordinance_far_pct": 80}
    assert check_against_legal("자연녹지지역", far_pct=80, regulation_payload=reg) == []


def test_check_natural_green_far_200_no_basis_high():
    # 자연녹지 200% 무근거 → high(할루시네이션 유지).
    issues = check_against_legal("자연녹지지역", far_pct=200)
    assert issues and issues[0]["severity"] == "high"


def test_check_natural_green_far_200_with_plan_ceiling_info():
    # 자연녹지 200% + 도시·군관리계획/지구단위계획 상한 200% → info(정당, high 아님).
    plan = {"districts": [{"district_name": "지구단위계획구역", "plan_far_pct": 200}]}
    issues = check_against_legal("자연녹지지역", far_pct=200, plan_payload=plan)
    assert len(issues) == 1
    assert issues[0]["severity"] == "info"
    assert issues[0]["severity"] != "high"


def test_check_junjugeo_600_plan_basis_info():
    # 준주거 600% + 지구단위계획 상한 600% → info(정당).
    plan = {"plan_far_pct": 600, "name": "지구단위계획"}
    issues = check_against_legal("준주거지역", far_pct=600, plan_payload=plan)
    assert len(issues) == 1
    assert issues[0]["severity"] == "info"


def test_check_junjugeo_600_no_basis_high():
    # 준주거 600% 무근거 → high.
    issues = check_against_legal("준주거지역", far_pct=600)
    assert issues and issues[0]["severity"] == "high"


def test_range_checks_natural_green_far_200_plan_payload_info():
    # run_range_checks 경유: special_districts에 지구단위계획 상한 → info(정당).
    source = {
        "zone_type": "자연녹지지역",
        "special_districts": [{"district_name": "지구단위계획구역", "plan_far_pct": 200}],
    }
    output = {"effective_far_pct": 200}
    issues = run_range_checks("site", source, output)
    far_issues = [i for i in issues if "용적률" in i["claim"]]
    assert far_issues and far_issues[0]["severity"] == "info"
    assert not any(i["severity"] == "high" for i in far_issues)


def test_far_basis_detail_meta_present():
    # _calc_effective_far far_basis_detail에 법정범위·데이터출처가 담기는지(조례 미보유).
    from app.services.land_intelligence.comprehensive_analysis_service import (
        ComprehensiveAnalysisService,
    )
    svc = ComprehensiveAnalysisService()
    base = {"zone_type": "자연녹지지역", "zone_limits": {}}
    sec = svc._calc_effective_far(base, "자연녹지지역", land_area=1000)
    detail = sec["far_basis_detail"]
    assert detail["법정범위"]["min_far_pct"] == 50
    assert detail["법정범위"]["max_far_pct"] == 100
    assert detail["데이터출처"]
    assert sec["ordinance_confirmed"] is False
    assert detail["조례확인필요"] is True


def test_far_basis_detail_ordinance_confirmed():
    # 조례 적용값(local_ordinance) 주입 시 far_basis_detail.조례값·ordinance_confirmed 반영.
    from app.services.land_intelligence.comprehensive_analysis_service import (
        ComprehensiveAnalysisService,
    )
    svc = ComprehensiveAnalysisService()
    base = {
        "zone_type": "자연녹지지역",
        "zone_limits": {},
        "local_ordinance": {"effective_far": 80, "effective_bcr": 20, "source": "지자체 조례"},
    }
    sec = svc._calc_effective_far(base, "자연녹지지역", land_area=1000)
    assert sec["ordinance_confirmed"] is True
    assert sec["far_basis_detail"]["조례값"] is not None
    assert sec["far_basis_detail"]["조례값"]["far_pct"] == 80


# ════════════════════════════════════════════════════════════════════
# 종상향/종변경 잠재력(upzoning) — 현행/잠재 2계층 분리 검증
# ════════════════════════════════════════════════════════════════════
from app.services.zoning.upzoning_potential import UpzoningPotentialAnalyzer


def test_upzoning_natural_green_sufficient_area_scenarios():
    # 자연녹지(충분면적) → 종상향 시나리오 산출, target=일반주거, expected_far=목표지역 범위.
    a = UpzoningPotentialAnalyzer()
    r = a.analyze("자연녹지지역", land_area_sqm=20000, sigungu="서울특별시 강남구")
    assert r["scenarios"], "충분면적 자연녹지는 종상향 시나리오가 있어야 함"
    s = r["scenarios"][0]
    assert s["target_zone"] in ("제1종일반주거지역", "제2종일반주거지역")
    assert s["expected_far_pct_high"] is not None and s["expected_far_pct_high"] > 100
    assert s["is_estimate"] is True
    assert s["legal_basis"]
    assert s["feasibility"] in ("상", "중", "하")
    # 면적 충족 → 최소 1건은 가능성 '상'
    assert any(x["feasibility"] == "상" for x in r["scenarios"])
    assert r["potential_far_range"] is not None
    assert "예상치" in r["disclaimer"]


def test_upzoning_target_far_from_ordinance_resolver():
    # 목표 용도지역 조례 용적률 resolver 주입 → expected_far가 조례 기준으로 도출.
    from app.services.land_intelligence.ordinance_service import ORDINANCE_CACHE

    def resolver(sigungu: str, zone_type: str):
        for sido, block in ORDINANCE_CACHE.items():
            if sigungu and (sigungu in sido or sido in sigungu):
                z = block.get(zone_type)
                if z and z.get("far"):
                    return float(z["far"])
        return None

    a = UpzoningPotentialAnalyzer()
    r = a.analyze(
        "자연녹지지역", land_area_sqm=20000, sigungu="서울특별시",
        ordinance_far_resolver=resolver,
    )
    s = r["scenarios"][0]
    # 서울 1종일반 조례 150% → min(150, 법정상한200)=150.
    assert s["target_zone"] == "제1종일반주거지역"
    assert s["expected_far_pct_high"] == 150
    assert "조례" in s["expected_far_source"]


def test_upzoning_small_parcel_low_feasibility():
    # 소형 자연녹지(면적 미달) → 면적요건 미달로 feasibility '하'.
    a = UpzoningPotentialAnalyzer()
    r = a.analyze("자연녹지지역", land_area_sqm=300)
    assert r["scenarios"]
    assert all(s["feasibility"] == "하" for s in r["scenarios"])
    assert any("미달" in s["feasibility_reason"] for s in r["scenarios"])


def test_upzoning_unmapped_zone_no_scenarios():
    # 정형 경로 미매핑 용도지역(농림) → 시나리오 없음(예상치 미산출, 단정 금지).
    a = UpzoningPotentialAnalyzer()
    r = a.analyze("농림지역", land_area_sqm=20000)
    assert r["scenarios"] == []
    assert r["potential_far_range"] is None
    assert "확인" in r["summary"]


def test_upzoning_regulation_blocker_lowers_feasibility():
    # 규제구역(개발제한) → 종상향 제약 → feasibility 하향, caveat에 해제 선행 명시.
    a = UpzoningPotentialAnalyzer()
    base = a.analyze("자연녹지지역", land_area_sqm=20000)
    blocked = a.analyze("자연녹지지역", land_area_sqm=20000, special_districts=["개발제한구역"])
    # 동일 면적인데 블로커가 있으면 최상위 가능성이 같거나 더 낮아야 함.
    rank = {"상": 0, "중": 1, "하": 2}
    assert rank[blocked["scenarios"][0]["feasibility"]] >= rank[base["scenarios"][0]["feasibility"]]
    assert any("규제구역" in c for s in blocked["scenarios"] for c in s["caveats"])


# ── ★검증기 정합: 현행/잠재 2계층 분리 ──
def test_verifier_upzoning_expected_far_not_flagged_current():
    # 종상향 잠재 expected_far(목표 250%)는 현행 위법수치로 오적발되지 않아야 함.
    source = {
        "zone_type": "자연녹지지역",
        "effective_far_pct": 100,  # 현행 실효(정상, 법정 内)
        "upzoning": {
            "current_zone": "자연녹지지역",
            "scenarios": [
                {
                    "path": "도시개발사업(도시개발법)",
                    "target_zone": "제2종일반주거지역",
                    "expected_far_pct_low": 100,
                    "expected_far_pct_high": 250,
                    "feasibility": "상",
                    "legal_basis": "도시개발법 · 국토계획법",
                    "is_estimate": True,
                    "marker": "potential_upzoning_scenario",
                }
            ],
            "potential_far_range": {"min_pct": 250, "max_pct": 250},
            "marker": "potential_upzoning_scenario",
        },
    }
    output = {"effective_far_pct": 100}
    issues = run_range_checks("site", source, output)
    # 현행 100%는 법정 内 → 법정초과 high 없음.
    assert not any(i.get("type") == "법정한도초과" and i["severity"] == "high" for i in issues)


def test_verifier_current_baseless_far_still_high_despite_upzoning():
    # ★핵심: 현행 200%(무근거)는 종상향 섹션이 있어도 여전히 high로 적발.
    # (잠재 시나리오의 완화근거 키워드가 현행 판정을 오염시키면 안 됨.)
    source = {
        "zone_type": "자연녹지지역",
        "effective_far_pct": 200,  # 현행 무근거 초과(법정 100%)
        "upzoning": {
            "current_zone": "자연녹지지역",
            "scenarios": [
                {
                    "path": "지구단위계획 수립",
                    "target_zone": "제2종일반주거지역",
                    "expected_far_pct_high": 250,
                    "feasibility": "상",
                    "legal_basis": "국토계획법 제52조(지구단위계획) · 종상향 · 역세권 활성화",
                    "is_estimate": True,
                    "marker": "potential_upzoning_scenario",
                }
            ],
            "marker": "potential_upzoning_scenario",
        },
    }
    output = {"effective_far_pct": 200}
    issues = run_range_checks("site", source, output)
    far_issues = [i for i in issues if i.get("type") == "법정한도초과" and "용적률" in i["claim"]]
    assert far_issues, "현행 200%는 종상향 섹션과 무관하게 적발되어야 함"
    assert far_issues[0]["severity"] == "high", "잠재 시나리오 키워드가 현행 판정을 오염시키면 안 됨"
