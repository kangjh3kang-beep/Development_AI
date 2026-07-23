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
    should_apply_structural_cap,
    structural_cap_for,
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
    assert issues[0]["type"] == "법정한도초과"
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
    # ★결함 고정 교정(2026-07-23, QA 레인A): 종전엔 이 단언이 applied_far_pct==100으로
    #   "구조상한 누락" 버그를 정답으로 고정하고 있었다. 자연녹지는 건폐율 20%(법정)×
    #   층수상한 4층(국토계획법 시행령 별표17 두문) = 80%가 법정범위(100%)보다 낮은 실질
    #   상한이라 applicable_limits_for의 4번째 계층(구조상한)이 적용되면 80이 맞다
    #   (design-audit 4엔진 반사실 재현: far_applied=100·max_far=100 → PASS로 과대낙관,
    #   max_far=80이면 critical 정상 적발 — precheck_service.calc_effective_far가 이미
    #   같은 80을 산출해온 정답 기준선과 동치).
    a = applicable_limits_for("자연녹지지역")
    assert a["legal_min_far_pct"] == 50
    assert a["legal_max_far_pct"] == 100
    assert a["applied_far_pct"] == 80  # 구조상한(건폐 20%×4층) 바인딩 — 법정범위 100 아님
    assert a["structural_cap_pct"] == 80
    assert a["floor_cap"] == 4
    assert "구조상한" in a["far_source"]
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
    # ★R1 리뷰 R2 원복(2026-07-23, HIGH-1): 이 테스트 이름 자체가 계약이다("계획상한이
    #   override 한다"). QA 레인A 1차 수정에서 이 단언을 80(구조상한이 계획을 덮음)으로
    #   역전시킨 것은 계약 파괴였다 — 리뷰어 실증(자연녹지+계획상한 200%+설계 150% → main
    #   PASS, 역전판 FAIL) + 법령 논리(건폐율 20% 그대로에 계획이 용적률 200%를 부여했다면
    #   그 처분은 논리필연적으로 10층을 전제 — 국토계획법 §52③·시행령 §46이 지구단위계획으로
    #   §76(별표 두문 층수제한 포함) 완화를 허용)로 REVISE·원복. 계획상한 존재 시 구조상한은
    #   바인딩하지 않되(applied_far_pct==200 그대로), 은폐 금지 원칙상 structural_cap_pct·
    #   floor_cap은 계속 채워지고 far_source에 완화 전제 근거를 명시한다(아래 대조 테스트
    #   test_applicable_limits_no_plan_structural_cap_still_binds가 "계획 없으면 구조상한이
    #   여전히 바인딩된다"는 대칭 계약을 고정한다).
    plan = {"districts": [{"district_name": "지구단위계획구역", "plan_far_pct": 200}]}
    a = applicable_limits_for("자연녹지지역", plan_payload=plan)
    assert a["plan_far_pct"] == 200
    assert a["applied_far_pct"] == 200  # 계획상한이 최종 적용값(구조상한에 덮이지 않음)
    # 은폐 금지 — 구조상한 수치·근거는 계속 노출(소비처가 참고할 수 있게).
    assert a["structural_cap_pct"] == 80
    assert a["floor_cap"] == 4
    assert "지구단위계획" in a["far_source"]
    assert "완화" in a["far_source"]  # 구조상한 대비 완화 전제임을 은폐 없이 명시


def test_applicable_limits_no_plan_structural_cap_still_binds():
    """대조 계약(HIGH-1과 대칭): 계획상한이 '없으면' 구조상한은 여전히 정상 바인딩된다 —
    plan_relaxed 판정 자체가 무너진 게 아니라 '계획상한이 있을 때만' 완화로 간주함을 고정."""
    a = applicable_limits_for("자연녹지지역")  # plan_payload 없음
    assert a.get("plan_far_pct") is None
    assert a["applied_far_pct"] == 80  # 구조상한(건폐 20%×4층) 바인딩 — 계획상한 없음


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


# ── provenance 정직성: 법정상한 폴백을 조례 확정으로 오표기 금지(용인 자연녹지 회귀) ──
def test_applicable_limits_statutory_fallback_not_confirmed():
    # ★핵심 회귀: ordinance_service 3차 폴백(source='법정상한', ordinance_far=None,
    #   effective_far=법정 100)을 조례값으로 오인 채택하지 않는다.
    #   → ordinance_confirmed=False, effective_far=100 표시는 유지, far_source 정직.
    reg = {
        "local_ordinance": {
            "ordinance_far": None,
            "ordinance_bcr": None,
            "effective_far": 100,
            "effective_bcr": 20,
            "source": "법정상한",
        }
    }
    a = applicable_limits_for("자연녹지지역", regulation_payload=reg)
    assert a["ordinance_confirmed"] is False
    assert a.get("ordinance_far_pct") is None  # 조례값으로 승격 금지
    # ★결함 고정 교정(2026-07-23, QA 레인A): 조례 미확정 폴백이라도 구조상한(건폐 20%×4층=80%)
    #   은 법정상한(100%)과 무관하게 여전히 적용되는 물리적 상한이다 — "법정상한 유지" 문구가
    #   뜻하는 건 "조례를 신뢰하지 않는다"이지 "구조상한을 무시한다"가 아니다.
    assert a["applied_far_pct"] == 80  # 구조상한 바인딩(수치는 법정상한이 아닌 실질상한)
    assert "구조상한" in a["far_source"]
    # ★R1 리뷰 MEDIUM-2 복원(2026-07-23): #157 정직표기 가드 — 조례 미확정임을 far_source에서도
    #   계속 드러내야 한다(단언 부재 상태로 방치하면 이 문구가 조용히 사라져도 스위트가 그린).
    assert "조례 확인 필요" in a["far_source"]


def test_extract_ordinance_far_ignores_effective_only_without_source():
    # effective_far만 있고 조례 출처(조례/법제처/ELIS)·명시적 ordinance_far가 없으면 미채택.
    from app.services.zoning.legal_zone_limits import _extract_ordinance_far
    r = _extract_ordinance_far(
        {"local_ordinance": {"effective_far": 100, "source": "법정상한"}}
    )
    assert r["ord_far"] is None


def test_extract_ordinance_far_zone_limits_effective_only_not_confirmed():
    # zone_limits 형태: effective_far_pct만으론 조례 확정 아님(명시 ordinance_far_pct 필요).
    from app.services.zoning.legal_zone_limits import _extract_ordinance_far
    r = _extract_ordinance_far({"zone_limits": {"effective_far_pct": 100}})
    assert r["ord_far"] is None


def test_calc_effective_far_statutory_fallback_marks_recheck():
    # 법정상한 폴백(용인) → ordinance_confirmed=False·조례확인필요=True, effective 200 유지.
    # ★제1종일반주거지역(층수상한 없음)으로 검증 — 자연녹지는 구조상한(건폐×층수) 계층이
    # 별도로 개입해 이 provenance(recheck_recommended) 라벨링 테스트와 무관하게 값이
    # 바뀌므로(아래 test_natural_green_effective_far_capped_by_floor_limit에서 별도 검증),
    # 이 테스트는 층수 제한이 없는 zone으로 두 관심사를 분리한다.
    from app.services.land_intelligence.far_tier_service import calc_effective_far
    base = {
        "zone_type": "제1종일반주거지역",
        "zone_limits": {},
        "local_ordinance": {
            "ordinance_far": None,
            "ordinance_bcr": None,
            "effective_far": 200,
            "effective_bcr": 60,
            "source": "법정상한",
            "recheck_recommended": True,
        },
    }
    sec = calc_effective_far(base, "제1종일반주거지역", land_area=1000)
    assert sec["ordinance_confirmed"] is False
    assert sec["effective_far_pct"] == 200  # 수치 유지
    assert sec["far_basis_detail"]["조례확인필요"] is True
    assert "법정상한" in sec["far_basis"]


def test_calc_effective_far_real_ordinance_stays_confirmed():
    # ★과다강등 금지: 서울 자연녹지 실제 조례(far=50, 정적캐시) → confirmed=True·effective 50.
    from app.services.land_intelligence.far_tier_service import calc_effective_far
    base = {
        "zone_type": "자연녹지지역",
        "zone_limits": {},
        "local_ordinance": {
            "ordinance_far": 50,
            "ordinance_bcr": 20,
            "effective_far": 50,
            "effective_bcr": 20,
            "source": "지자체 조례(정적캐시)",
        },
    }
    sec = calc_effective_far(base, "자연녹지지역", land_area=1000)
    assert sec["ordinance_confirmed"] is True
    assert sec["effective_far_pct"] == 50
    assert sec["far_basis_detail"]["조례확인필요"] is False


# ── 전역스윕(리뷰 should_fix#1): path-3(limits.far/bcr trio) 동일 버그클래스 회귀 ──
def test_extract_ordinance_far_limits_trio_fallback_not_confirmed():
    # RegulationAnalysisService._limits.trio 생산 페이로드: ordinance 부재 시
    # effective = ordinance(None) or legal 로 법정값이 effective에 채워짐(용인과 동일 클래스).
    # → 명시적 ordinance 없으면 조례값으로 오인 채택 금지.
    from app.services.zoning.legal_zone_limits import _extract_ordinance_far
    r = _extract_ordinance_far({"limits": {"far": {"legal": 100, "ordinance": None, "effective": 100}}})
    assert r["ord_far"] is None


def test_applicable_limits_limits_trio_fallback_not_confirmed():
    payload = {"limits": {"far": {"legal": 100, "ordinance": None, "effective": 100}}}
    a = applicable_limits_for("자연녹지지역", regulation_payload=payload)
    assert a["ordinance_confirmed"] is False
    assert a.get("ordinance_far_pct") is None
    # ★결함 고정 교정(2026-07-23, QA 레인A): 조례 미확정 폴백이라도 구조상한(건폐 20%×4층=80%)
    #   은 여전히 적용되는 물리적 상한이다(위 test_applicable_limits_statutory_fallback_not_
    #   confirmed와 동일 사유 — 같은 버그클래스의 다른 경로).
    assert a["applied_far_pct"] == 80  # 구조상한 바인딩
    assert "구조상한" in a["far_source"]
    # ★R1 리뷰 MEDIUM-2 복원(2026-07-23): 위 statutory_fallback 테스트와 동일 사유.
    assert "조례 확인 필요" in a["far_source"]


def test_applicable_limits_limits_trio_explicit_ordinance_confirmed():
    # ★과다강등 금지: 명시적 ordinance 값이 있으면(실조례) 여전히 confirmed=True.
    payload = {"limits": {"far": {"legal": 100, "ordinance": 50, "effective": 50}}}
    a = applicable_limits_for("자연녹지지역", regulation_payload=payload)
    assert a["ordinance_confirmed"] is True
    assert a["applied_far_pct"] == 50
    assert a["ordinance_far_pct"] == 50


def test_design_audit_orchestrator_limits_trio_fallback_honest():
    # design_audit_orchestrator가 applicable_limits_for를 직접 소비하는 2차 표면 —
    # limits.far trio 폴백(조례 미확정)이 여기서도 false-confirm 없이 정직 전파되는지 확인.
    payload = {"limits": {"far": {"legal": 100, "ordinance": None, "effective": 100}}}
    a = applicable_limits_for("자연녹지지역", regulation_payload=payload)
    assert a["ordinance_confirmed"] is False


def test_far_tier_recheck_recommended_from_provenance_subdict():
    # 리뷰 should_fix#2: recheck_recommended는 ordinance["provenance"] 하위에 실린다
    # (top-level 읽기는 dead-branch였음). far_basis가 실제로 정직 라벨로 전환되는지 확인.
    # ★층수상한 없는 zone(제1종일반주거)로 검증 — 구조상한 계층과 관심사 분리(위 statutory
    # fallback 테스트와 동일 사유).
    from app.services.land_intelligence.far_tier_service import calc_effective_far
    base = {
        "zone_type": "제1종일반주거지역",
        "zone_limits": {},
        "local_ordinance": {
            "ordinance_far": None,
            "ordinance_bcr": None,
            "effective_far": 200,
            "effective_bcr": 60,
            "source": "법정상한",
            "provenance": {"recheck_recommended": True, "confidence": 0.60},
        },
    }
    sec = calc_effective_far(base, "제1종일반주거지역", land_area=1000)
    assert sec["ordinance_confirmed"] is False
    assert "법정상한" in sec["far_basis"]
    assert sec["far_basis_detail"]["조례확인필요"] is True


# ════════════════════════════════════════════════════════════════════
# 구조상한(건폐율×층수) — 자연/생산녹지 등 층수제한 zone의 실효 용적률 과대표시 확정버그 수정
# ════════════════════════════════════════════════════════════════════
def test_natural_green_effective_far_capped_by_structural_floor_limit():
    """★확정버그 수정: 자연녹지 법정 용적률 100%는 층수 제한(4층 이하) 때문에
    건폐 20%×4층=80%가 실질 상한이다 — effective_far_pct는 100이 아니라 80이어야 한다."""
    from app.services.land_intelligence.far_tier_service import calc_effective_far

    sec = calc_effective_far({}, "자연녹지지역", land_area=1000)
    assert sec["national_far_pct"] == 100.0  # 법정상한(표시값)은 불변
    assert sec["effective_bcr_pct"] == 20.0
    assert sec["structural_cap_pct"] == 80.0
    assert sec["floor_cap"] == 4
    assert sec["floor_cap_basis"] and "별표17" in sec["floor_cap_basis"]
    assert sec["effective_far_pct"] == 80.0  # 구조상한 적용(과대표시 수정)
    assert sec["far_basis"] == "구조상한(건폐율×층수)"


def test_natural_green_ordinance_below_structural_cap_unaffected():
    """조례 실효값(50%)이 구조상한(80%)보다 이미 낮으면 구조상한이 바인딩되지 않는다(무회귀)."""
    from app.services.land_intelligence.far_tier_service import calc_effective_far

    base = {
        "zone_type": "자연녹지지역",
        "zone_limits": {},
        "local_ordinance": {
            "ordinance_far": 50, "ordinance_bcr": 20,
            "effective_far": 50, "effective_bcr": 20,
            "source": "지자체 조례(정적캐시)",
        },
    }
    sec = calc_effective_far(base, "자연녹지지역", land_area=1000)
    assert sec["effective_far_pct"] == 50  # 조례값 그대로(구조상한 미적용)
    assert sec["structural_cap_pct"] == 80.0  # 참고치는 여전히 노출(additive)
    assert sec["far_basis"] != "구조상한(건폐율×층수)"


def test_zone_without_floor_cap_structural_fields_are_none():
    """층수상한이 없는 용도지역(제1종일반주거)은 structural_cap_pct 등이 전부 None(기존값 불변)."""
    from app.services.land_intelligence.far_tier_service import calc_effective_far

    sec = calc_effective_far({}, "제1종일반주거지역", land_area=1000)
    assert sec["structural_cap_pct"] is None
    assert sec["floor_cap"] is None
    assert sec["floor_cap_basis"] is None
    assert sec["effective_far_pct"] == 200.0  # 기존 법정상한 그대로


def test_far_optimization_scenarios_do_not_exceed_structural_cap():
    """far_optimization(1-B) 인센티브 시나리오도 구조상한(80%)을 넘지 않는다."""
    from app.services.land_intelligence.far_tier_service import calc_effective_far

    sec = calc_effective_far({}, "자연녹지지역", land_area=1000)
    scenarios = sec["far_optimization"]["scenarios"]
    assert scenarios
    assert all(s["achieved_far"] <= 80.0 + 0.5 for s in scenarios)
    assert sec["far_optimization"]["cap_far"] <= 80.0 + 0.5


def test_hotpath_guard_passes_for_structural_capped_effective_far():
    """check_against_legal(80<100) — 구조상한 적용치는 법정초과 가드에 걸리지 않는다."""
    issues = check_against_legal("자연녹지지역", far_pct=80.0, bcr_pct=20.0)
    assert issues == []


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


# ══════════════════════════════════════════════════════════════════════════
# ── R1 리뷰 R2 봉합(2026-07-23) ──
# HIGH-2: BCR 단위오염(비율↔퍼센트)·법정초과값이 구조상한을 붕괴/왜곡시키지 않는지 확인.
# ══════════════════════════════════════════════════════════════════════════
def test_structural_cap_for_rejects_bcr_ratio_unit_contamination():
    """★리뷰어 실증 재현(HIGH-2): 조례 BCR을 퍼센트(20) 대신 비율(0.2)로 오입력하면
    0.2×4층=0.8%로 구조상한이 붕괴해 모든 설계가 부적합·매출이 사실상 0이 된다. 실제
    건폐율 값은 항상 퍼센트로 전달되며 국내 건축법규상 1% 미만 건폐율 용도지역은 없다
    (ZONE_LIMITS 최소값 20) — 1.0 미만 입력은 정직하게 미산정한다(붕괴 방지)."""
    cap, floor_cap, basis = structural_cap_for("자연녹지지역", 0.2)
    assert cap is None
    assert floor_cap is None
    assert basis is None


def test_structural_cap_for_rejects_non_positive_bcr():
    """None·0·음수 건폐율도 동일하게 정직 미산정(구조상한을 0 또는 음수로 계산하지 않음)."""
    assert structural_cap_for("자연녹지지역", 0) == (None, None, None)
    assert structural_cap_for("자연녹지지역", -5.0) == (None, None, None)
    assert structural_cap_for("자연녹지지역", None) == (None, None, None)


def test_structural_cap_for_rejects_bcr_exceeding_legal_max():
    """법정 건폐율 상한(자연녹지 20%)을 초과하는 오염값(예: 90%)도 미산정 — 구조상한이
    법정초과 입력으로 부풀려져 실제보다 관대해지는 왜곡을 막는다."""
    cap, floor_cap, basis = structural_cap_for("자연녹지지역", 90.0)
    assert cap is None
    assert floor_cap is None
    assert basis is None


def test_applicable_limits_bcr_unit_contamination_does_not_collapse_far():
    """통합경로 재현: 조례 건폐율이 0.2(비율, 20%의 오입력)로 들어와도 applied_far_pct가
    0.8%로 붕괴하지 않는다 — 구조상한 산정 자체를 건너뛰고 법정 계층값(100%)을 유지한다."""
    reg = {"local_ordinance": {"effective_bcr": 0.2, "source": "지자체 조례"}}
    a = applicable_limits_for("자연녹지지역", regulation_payload=reg)
    assert a["applied_bcr_pct"] == 0.2  # 오염값 자체는 그대로 노출(은폐 금지)
    assert a["structural_cap_pct"] is None  # 오염값으로 구조상한 미산정(정직)
    assert a["applied_far_pct"] == 100  # 0.8%로 붕괴하지 않고 법정범위 유지
    # ★R1 리뷰 LOW#1(2026-07-23): 게이트가 조용히 미산정으로 복귀할 때 소비처가 판별할
    # 신호(far_source/sources)를 남긴다(무날조 — 정상 "층수제한 없음" 케이스와 구분).
    assert "구조상한 미산정" in a["far_source"]
    assert any("구조상한 미산정" in s for s in a["sources"])


def test_applicable_limits_plan_bcr_relaxation_not_clamped_but_cap_input_is():
    """★R1 리뷰 R2b 신규 HIGH(2026-07-23): 지구단위계획이 건폐율을 완화(법정 20%→40%)해도
    표시·한도값(applied_bcr_pct)은 계획값 그대로여야 한다 — R2가 이 값 자체를 법정상한으로
    클램프해 계획의 건폐율 완화를 무효화했다(리뷰어 실증: 자연녹지+계획 40%+설계 35% →
    main 적합, R2 결함판은 '건폐율_초과'로 오판). 구조상한 '계산 입력'만 법정 상한(20%)
    이내로 제한되어 structural_cap_pct=80(=20%×4층)이어야 한다 — 표시값·계산입력의 분리를
    동시에 고정(한쪽만 확인하면 재발 가능)."""
    plan = {"districts": [{"district_name": "지구단위계획구역", "plan_far_pct": 100, "plan_bcr_pct": 40}]}
    a = applicable_limits_for("자연녹지지역", plan_payload=plan)
    assert a["plan_bcr_pct"] == 40
    assert a["applied_bcr_pct"] == 40  # 계획 완화 존중(법정 20%로 안 깎임 — R2 회귀 방지)
    assert a["structural_cap_pct"] == 80  # 계산 입력만 법정 20% 이내로 제한(20×4층=80)
    assert a["floor_cap"] == 4


# ══════════════════════════════════════════════════════════════════════════
# HIGH-1 공용 술어(should_apply_structural_cap) 단위 테스트 — legal_zone_limits.py·
# far_tier_service.py 양쪽이 공유하는 판정 로직 자체를 직접 고정.
# ══════════════════════════════════════════════════════════════════════════
def test_should_apply_structural_cap_binds_when_no_plan():
    assert should_apply_structural_cap(80.0, 100.0, plan_relaxed=False) is True


def test_should_apply_structural_cap_does_not_bind_when_plan_relaxed():
    assert should_apply_structural_cap(80.0, 200.0, plan_relaxed=True) is False


def test_should_apply_structural_cap_false_when_cap_not_lower():
    # 구조상한이 적용값보다 낮지 않으면(같거나 큼) 애초에 바인딩 대상이 아님.
    assert should_apply_structural_cap(80.0, 80.0, plan_relaxed=False) is False
    assert should_apply_structural_cap(None, 100.0, plan_relaxed=False) is False
    assert should_apply_structural_cap(80.0, None, plan_relaxed=False) is False
