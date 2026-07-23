"""설계심사 코어(U5 — DA-1~DA-3) 테스트.

- DA-1: 한국어 라벨 정규식 폴백(원문 인용 동반·미매칭 null·평→㎡ 환산), PDF graceful.
- DA-2: 출처 병합(user>ifc>brief) + 5% 괴리 conflicts, 도형 검증 패스스루.
- DA-3: AuditFinding 정규화(레지스트리 근거만), overall 결정론 산정,
        엔진 실패 graceful(skipped), 사례비교 결합(모킹).
- UP3: run() 라우터 계약 어댑터(audit 위임·verdict 영문 별칭·IFC 병합),
        grammar 섹션(rooms 제공 시 경계·개구·연결성 — None이면 skipped).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.services.design_audit.brief_extractor import (  # noqa: E402
    BRIEF_FIELDS,
    extract_brief,
    extract_text_from_pdf,
    parse_brief_rule_based,
)
from app.services.design_audit.design_audit_orchestrator import (  # noqa: E402
    ENGINE_NAMES,
    VERDICT_EN_ALIASES,
    DesignAuditOrchestrator,
    make_finding,
)
from app.services.design_audit.geometry_adapter import (  # noqa: E402
    design_payload_from_shapes,
    merge_params,
)

ZONE = "제2종일반주거지역"  # 법정 한도: 건폐율 60% / 용적률 250%

_FINDING_KEYS = {"check_id", "engine", "status", "current", "limit", "legal_refs", "improvement"}


def _clean_params(**overrides):
    """적합(전 엔진 pass) 시나리오 파라미터 — 모든 한도·정합 내."""
    params = {
        "land_area_sqm": 500.0,
        "bcr_pct": 48.0,
        "far_pct": 160.0,
        "building_height_m": 12.0,
        "floors_above": 4,
        "units": 10,
        "avg_unit_area_sqm": 60.0,
        "total_floor_area_sqm": 800.0,
        "building_area_sqm": 240.0,
        "parking": 12,
        "building_use": "공동주택",
    }
    params.update(overrides)
    return params


def _square_shapes():
    """50px(=5m) 정사각 1개면 — 벽체경간(6m)·건폐율·용적률 전부 한도 내."""
    return {
        "points": [
            {"id": "p1", "x": 0, "y": 0},
            {"id": "p2", "x": 50, "y": 0},
            {"id": "p3", "x": 50, "y": 50},
            {"id": "p4", "x": 0, "y": 50},
        ],
        "lines": [{"id": "l1", "start_point_id": "p1", "end_point_id": "p2"}],
        "surfaces": [{"id": "s1", "point_ids": ["p1", "p2", "p3", "p4"]}],
        "floor_count": 4,
        "building_height_m": 12.0,
        "scale": 10.0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# AuditFinding 정규화 (make_finding)
# ─────────────────────────────────────────────────────────────────────────────
class TestFindingNormalization:
    def test_finding_schema_keys(self):
        """AuditFinding은 check_id/engine/status/current/limit/legal_refs/improvement 단일 스키마."""
        f = make_finding("x", "rules8", "pass", current=1, limit=2, improvement="없음")
        assert _FINDING_KEYS.issubset(f.keys())
        assert f["status"] == "pass"
        assert f["legal_refs"] == []

    def test_legal_refs_registry_only(self):
        """legal_refs는 레지스트리 출력만 — 미존재 키는 자동 제외(할루시네이션 링크 금지)."""
        f = make_finding(
            "x", "design_review", "fail",
            legal_ref_keys=["bldg_far", "nonexistent_key_xyz"],
        )
        assert len(f["legal_refs"]) == 1
        ref = f["legal_refs"][0]
        assert ref["key"] == "bldg_far"
        assert ref["url"].startswith("https://www.law.go.kr")
        assert ref["url_status"] == "verified"

    def test_unknown_keys_only_yield_empty(self):
        f = make_finding("x", "permit", "fail", legal_ref_keys=["made_up_key"])
        assert f["legal_refs"] == []

    def test_ordinance_key_with_sigungu(self):
        """조례 키는 sigungu 치환 + 자치법규 딥링크(verified)로 승격."""
        f = make_finding("x", "incentives", "info",
                         legal_ref_keys=["ordinance_far"], sigungu="강남구")
        assert len(f["legal_refs"]) == 1
        ref = f["legal_refs"][0]
        assert "강남구" in ref["law_name"]
        assert ref["url_status"] == "verified"


# ─────────────────────────────────────────────────────────────────────────────
# DA-2: merge_params (user > ifc > brief, 5%+ 괴리 conflicts)
# ─────────────────────────────────────────────────────────────────────────────
class TestMergeParams:
    def test_priority_user_over_ifc_over_brief(self):
        result = merge_params(
            user={"far_pct": 250.0},
            ifc={"far_pct": 230.0, "total_floor_area_sqm": 1200.0},
            brief={"far_pct": {"value": 240.0, "quote": "용적률 240%", "confidence": 0.5}},
        )
        assert result["params"]["far_pct"] == 250.0
        assert result["param_sources"]["far_pct"] == "user"
        assert result["param_sources"]["total_floor_area_sqm"] == "ifc"
        assert result["priority"] == "user > ifc > brief"

    def test_conflict_recorded_at_5pct_deviation(self):
        """user 250 vs ifc 230 → 상대 8% 괴리 → conflicts 기록(채택값은 user 유지)."""
        result = merge_params(user={"far_pct": 250.0}, ifc={"far_pct": 230.0})
        assert len(result["conflicts"]) == 1
        c = result["conflicts"][0]
        assert c["key"] == "far_pct"
        assert c["chosen_source"] == "user"
        assert c["chosen_value"] == 250.0
        assert c["deviation_pct"] == pytest.approx(8.0)

    def test_no_conflict_below_threshold(self):
        """0.8% 괴리(<5%)는 conflicts 미기록."""
        result = merge_params(
            user={"far_pct": 250.0},
            brief={"far_pct": {"value": 248.0, "quote": None, "confidence": None}},
        )
        assert result["conflicts"] == []
        assert result["params"]["far_pct"] == 250.0

    def test_brief_only_value_unwrapped(self):
        result = merge_params(
            brief={"units": {"value": 100, "quote": "100세대", "confidence": 0.5}}
        )
        assert result["params"]["units"] == 100
        assert result["param_sources"]["units"] == "brief"
        assert result["conflicts"] == []

    def test_empty_inputs(self):
        result = merge_params()
        assert result["params"] == {}
        assert result["conflicts"] == []


# ─────────────────────────────────────────────────────────────────────────────
# DA-1: 한국어 라벨 정규식 폴백 + PDF graceful
# ─────────────────────────────────────────────────────────────────────────────
SAMPLE_BRIEF = """\
건축개요
1. 대지면적 : 1,000㎡
2. 용도지역 : 제2종일반주거지역
3. 건폐율 : 59.5 %
4. 용적률 : 249.5 %
5. 규모 : 지상 15층 / 지하 2층
6. 세대수 : 120세대
7. 주차대수 : 150대
8. 주용도 : 공동주택
"""


class TestBriefRuleFallback:
    def test_korean_labels_extracted_with_quotes(self):
        fields = parse_brief_rule_based(SAMPLE_BRIEF)
        assert fields["land_area_sqm"]["value"] == pytest.approx(1000.0)
        assert "대지면적" in fields["land_area_sqm"]["quote"]
        assert fields["bcr_pct"]["value"] == pytest.approx(59.5)
        assert fields["far_pct"]["value"] == pytest.approx(249.5)
        assert fields["floors_above"]["value"] == 15
        assert fields["floors_below"]["value"] == 2
        assert fields["units"]["value"] == 120
        assert fields["parking"]["value"] == 150
        assert fields["zone_type"]["value"] == "제2종일반주거지역"
        assert fields["building_use"]["value"] == "공동주택"

    def test_missing_field_is_null_not_fabricated(self):
        """원문에 없는 필드(높이)는 None — 임의 수치 날조 금지."""
        fields = parse_brief_rule_based(SAMPLE_BRIEF)
        assert fields["building_height_m"] is None
        assert set(fields.keys()) == set(BRIEF_FIELDS)

    def test_pyeong_converted_to_sqm(self):
        """평 표기는 1평=3.3058㎡ 결정적 환산(원문은 quote에 보존)."""
        fields = parse_brief_rule_based("대지면적 : 500평")
        assert fields["land_area_sqm"]["value"] == pytest.approx(1652.9)
        assert "500평" in fields["land_area_sqm"]["quote"]

    async def test_extract_brief_rule_source_without_llm(self):
        result = await extract_brief(SAMPLE_BRIEF, use_llm=False)
        assert result["source"] == "rule"
        assert result["fields"]["far_pct"]["value"] == pytest.approx(249.5)

    async def test_extract_brief_empty_text(self):
        result = await extract_brief("   ")
        assert result["source"] == "empty"
        assert all(v is None for v in result["fields"].values())

    def test_pdf_extract_graceful_on_invalid_bytes(self):
        """손상 PDF/라이브러리 부재 모두 빈 텍스트 + 정직한 note(예외 미전파)."""
        result = extract_text_from_pdf(b"not a pdf at all")
        assert result["text"] == ""
        assert result["note"]


# ─────────────────────────────────────────────────────────────────────────────
# DA-2: 도형 검증 패스스루
# ─────────────────────────────────────────────────────────────────────────────
class TestShapesPassthrough:
    def test_valid_shapes_pass_through(self):
        result = design_payload_from_shapes(_square_shapes())
        assert result["valid"] is True
        design = result["design"]
        assert len(design["points"]) == 4
        assert len(design["surfaces"]) == 1
        assert design["floor_count"] == 4
        assert design["scale"] == 10.0

    def test_invalid_point_dropped_with_issue(self):
        shapes = _square_shapes()
        shapes["points"].append({"id": "bad"})  # x/y 결손
        result = design_payload_from_shapes(shapes)
        assert result["valid"] is True
        assert len(result["design"]["points"]) == 4
        assert any("point 무효" in issue for issue in result["issues"])

    def test_no_surfaces_invalid(self):
        shapes = _square_shapes()
        shapes["surfaces"] = []
        result = design_payload_from_shapes(shapes)
        assert result["valid"] is False
        assert result["design"] is None

    def test_none_payload(self):
        result = design_payload_from_shapes(None)
        assert result["valid"] is False
        assert result["issues"]


# ─────────────────────────────────────────────────────────────────────────────
# DA-3: 오케스트레이터 — overall 결정론·엔진 실패 graceful·사례비교 결합
# ─────────────────────────────────────────────────────────────────────────────
class TestOrchestratorOverall:
    async def test_clean_design_verdict_pass(self):
        """전 한도 내 설계 + 유효 기하 → fail/warning 0 → '적합'."""
        result = await DesignAuditOrchestrator().audit(
            _clean_params(), zone_type=ZONE, shapes=_square_shapes()
        )
        assert result["overall"]["verdict"] == "적합"
        counts = result["overall"]["counts"]
        assert counts.get("fail", 0) == 0
        assert counts.get("warning", 0) == 0
        # 8엔진(ENGINE_NAMES) + 9번째 bl_rules(피난·방화 BL-007) 위임 엔진 — 전부 ok.
        # (소규모 설계는 피난 특별규정 해당없음→info, 엔진 실행 자체는 성공=ok)
        assert set(result["engines"]) == set(ENGINE_NAMES) | {"bl_rules"}
        assert all(v == "ok" for v in result["engines"].values())
        # 조례 실효한도 선행 산정(법정 250/60) + 레지스트리 근거.
        assert result["limits"]["applied_far_pct"] == 250.0
        assert result["limits"]["applied_bcr_pct"] == 60.0
        assert result["limits"]["legal_refs"]
        # 기하 8룰 위반 없음(pass) 정규화 확인.
        rules8 = [f for f in result["findings"] if f["engine"] == "rules8"]
        assert rules8 and rules8[0]["status"] == "pass"
        # S7 효율 지표: 전용률 = 10세대×60㎡ / 800㎡ = 75%.
        eff = result["sections"]["efficiency_metrics"]
        assert eff["efficiency_pct"] == pytest.approx(75.0)
        assert eff["core_ratio_pct"] is None  # 코어면적 미입력 — None(정직)

    async def test_far_exceed_verdict_fail(self):
        """용적률 320% > 실효 250% → design_review fail → '부적합'(결정론)."""
        params = _clean_params(
            land_area_sqm=660.0, far_pct=320.0, building_height_m=45.0,
            floors_above=15, units=100, parking=120,
            total_floor_area_sqm=2112.0, building_area_sqm=None,
            avg_unit_area_sqm=None,
        )
        result = await DesignAuditOrchestrator().audit(params, zone_type=ZONE)
        assert result["overall"]["verdict"] == "부적합"
        fails = [f for f in result["findings"] if f["status"] == "fail"]
        assert any(f["engine"] == "design_review" for f in fails)
        far_fail = next(f for f in fails if f["engine"] == "design_review")
        assert far_fail["current"] == 320.0
        assert far_fail["limit"] == 250.0
        assert far_fail["improvement"]  # 시정안 동반
        assert far_fail["legal_refs"] and far_fail["legal_refs"][0]["url"].startswith(
            "https://www.law.go.kr"
        )
        # 기하 미제공 → rules8은 skipped로 정직 표기.
        rules8 = [f for f in result["findings"] if f["engine"] == "rules8"]
        assert rules8 and rules8[0]["status"] == "skipped"

    async def test_warning_only_verdict_conditional(self):
        """fail 없이 warning(주차 미입력 등)만 → '조건부적합'(결정론)."""
        params = _clean_params(
            land_area_sqm=660.0, far_pct=240.0, bcr_pct=59.0,
            building_height_m=45.0, floors_above=15, units=100,
            total_floor_area_sqm=1584.0, building_area_sqm=None,
            avg_unit_area_sqm=None, parking=None,
        )
        result = await DesignAuditOrchestrator().audit(params, zone_type=ZONE)
        assert result["overall"]["verdict"] == "조건부적합"
        counts = result["overall"]["counts"]
        assert counts.get("fail", 0) == 0
        assert counts.get("warning", 0) >= 1
        parking = next(f for f in result["findings"] if f["engine"] == "parking")
        assert parking["status"] == "warning"
        assert parking["current"] == "미입력"
        assert any(r["key"] == "parking_min" for r in parking["legal_refs"])

    async def test_plan_bcr_relaxation_respected_by_design_review(self):
        """★R1 리뷰 R2b 신규 HIGH(2026-07-23) — 리뷰어 실증 재현: 자연녹지지역 + 지구단위계획
        건폐율 40%(법정 20% 완화) + 설계 건폐율 35% → design_review는 '적합'이어야 한다.
        R2의 결함(applied_bcr_pct 자체를 법정 20%로 클램프)이면 '건폐율_초과'(limit=20.0)로
        오판된다 — 계획 완화가 표시·한도값에 그대로 반영되는지, 구조상한 수치는 은폐 없이
        계속 노출되는지(구조상한 계산 입력만 제한됐다는 증거) 오케스트레이터 직접 실행으로
        확인한다."""
        params = _clean_params(
            land_area_sqm=1000.0, bcr_pct=35.0, far_pct=70.0,
            building_height_m=12.0, floors_above=4, units=6,
            avg_unit_area_sqm=60.0, total_floor_area_sqm=700.0,
            building_area_sqm=350.0, parking=6,
        )
        plan_payload = {
            "districts": [
                {"district_name": "지구단위계획구역", "plan_far_pct": 100.0, "plan_bcr_pct": 40.0}
            ]
        }
        result = await DesignAuditOrchestrator().audit(
            params, zone_type="자연녹지지역", plan_payload=plan_payload,
        )
        assert result["limits"]["applied_bcr_pct"] == 40.0  # 계획 완화 존중(20으로 안 깎임)
        assert result["limits"]["structural_cap_pct"] == 80.0  # 계산 입력만 제한(은폐 없음)
        design_review = [f for f in result["findings"] if f["engine"] == "design_review"]
        assert design_review and design_review[0]["status"] == "pass", (
            f"계획 건폐율 완화가 무효화됨(오판 재발): {design_review}"
        )
        assert not any(
            f["engine"] == "design_review" and f["status"] == "fail"
            for f in result["findings"]
        )

    async def test_sections_present(self):
        """리포트 결합용 sections: s1_samples·s4_incentives·efficiency_metrics 원자료."""
        result = await DesignAuditOrchestrator().audit(_clean_params(), zone_type=ZONE)
        sections = result["sections"]
        assert "efficiency_metrics" in sections
        assert "s4_incentives" in sections
        assert "s1_samples" in sections  # PNU 미제공 → available=False로 정직 표기
        assert sections["s1_samples"]["available"] is False
        s4 = sections["s4_incentives"]
        assert "donation_simulation" in s4 and "upzoning" in s4
        assert s4["upzoning"].get("marker") == "potential_upzoning_scenario"
        # 인센티브는 예상치(info) — 종합판정에 미반영.
        incentive = next(f for f in result["findings"] if f["engine"] == "incentives")
        assert incentive["status"] == "info"

    async def test_bl_rules_evacuation_engine(self):
        """9번째 엔진 bl_rules — 정본 building_code_rules(BL-007) 위임으로 피난·방화 surface.

        5층 이상/층당 200㎡ 초과 → 직통계단·방화구획 확인 필요. ★R2 리뷰 확정방침: BL-007의
        WARNING은 "요건 존재·확정 위반 아님"이며 사실상 모든 중규모 건물(5층 이상)에서 발화
        하므로 status=info(판정 미반영)로 사상한다 — verdict를 지배하면 현실의 거의 모든 건물이
        '적합' 도달 불가(헤드라인 회귀)가 되기 때문. 검사 자체는 findings에 정직 surface된다
        (improvement에 "설계도서에서 확인 필요" 문구 유지). UI가 광고하던 '피난·방화 체크'가
        실제로 검사되는지 확인(광고-실검사 정합)하되, 종합판정을 왜곡하지 않는지도 확인.
        """
        params = _clean_params(
            floors_above=15, total_floor_area_sqm=6000.0, building_height_m=45.0,
        )
        result = await DesignAuditOrchestrator().audit(params, zone_type=ZONE)
        assert result["engines"]["bl_rules"] == "ok"
        bl = next(f for f in result["findings"] if f["engine"] == "bl_rules")
        assert bl["check_id"] == "bl_fire_escape"
        assert bl["status"] == "info"  # 판정 미반영 — 요건 존재·설계도서 확인 필요(확정 위반 아님)
        assert "확인 필요" in (bl["improvement"] or "")
        assert bl["legal_refs"]  # 건축법 시행령 §34/§46 근거 부착
        assert "bl_rules" in result["sections"]

    def test_bl_rules_warning_never_counted_toward_verdict(self):
        """핵심 회귀 방지(직접 유닛 테스트 — 다른 엔진의 무관한 임계값 간섭 배제).

        _run_bl_rules는 동기 메서드라 오케스트레이터 전체를 돌리지 않고 직접 호출해
        WARNING→info 사상만을 격리 검증한다(overall verdict 조합은 change_risk 등
        floors_above 임계값이 겹치는 무관한 엔진에 좌우돼 취약한 e2e 조건이 된다).
        """
        orchestrator = DesignAuditOrchestrator()
        # floor_count>=5 → needs_dual_stair=True → BuildingCodeRuleEngine이 WARNING을 낸다.
        bl = orchestrator._run_bl_rules(
            {"floors_above": 15, "total_floor_area_sqm": 6000.0}, ZONE
        )
        assert bl["status"] == "ok"
        finding = bl["findings"][0]
        assert finding["check_id"] == "bl_fire_escape"
        # ★R2 확정방침: STATUS_WARNING이 아닌 STATUS_INFO(counts.warning에 미가산 → verdict 미지배).
        assert finding["status"] == "info"
        assert finding["status"] != "warning"

    async def test_bl_rules_skipped_without_data(self):
        """층수·연면적·층당면적 전무 → bl_rules는 skipped(임의값 강행 금지·정직)."""
        params = _clean_params(
            floors_above=None, total_floor_area_sqm=None,
            building_area_sqm=None, avg_unit_area_sqm=None, units=None,
        )
        result = await DesignAuditOrchestrator().audit(params, zone_type=ZONE)
        assert result["engines"]["bl_rules"] == "skipped"
        bl = next(f for f in result["findings"] if f["engine"] == "bl_rules")
        assert bl["status"] == "skipped"


# ─────────────────────────────────────────────────────────────────────────────
# 레인C(P0) — 입력 배선 복구: sigungu 종상향 relay·special_districts 미수집 정직화
# ─────────────────────────────────────────────────────────────────────────────
class TestSigunguUpzoningRelay:
    """근본원인: _run_incentives가 오케스트레이터 보유 sigungu를 calc_upzoning의 base
    (regulation_payload)에 병합하지 않아 목표 용도지역 조례 resolver가 영구 미발동했다
    (요약문 "약 200~200%" 붕괴). audit()이 sigungu=None으로 이미 호출 중이던(레지스트리 조회
    스킵) 경로를 sigungu 명시 전달만으로 조례값(용인시 제2종일반주거=240%)으로 갈리게 함을
    실제 값 대조(반사실)로 검증한다 — 두 테스트는 짝이다(단정문 회귀 감지용)."""

    async def test_sigungu_relay_activates_ordinance_resolver(self):
        result = await DesignAuditOrchestrator().audit(
            _clean_params(land_area_sqm=6000.0),
            zone_type="제1종일반주거지역", sigungu="용인시",
        )
        upzoning = result["sections"]["s4_incentives"]["upzoning"]
        redev = next(s for s in upzoning["scenarios"] if s["path_key"] == "정비사업")
        assert redev["target_zone"] == "제2종일반주거지역"
        # 용인시 조례 240% ≠ 법정상한 250% — resolver가 실제로 발동한 증거(단순 문구뿐 아님).
        assert redev["expected_far_pct_high"] == 240
        assert redev["expected_far_source"] == "지자체 도시계획조례(목표지역)"

    async def test_sigungu_absent_falls_back_to_legal_range(self):
        """대조군(반사실) — sigungu 미제공 시 종전처럼 법정범위 붕괴(회귀 시 위 테스트와 갈라짐)."""
        result = await DesignAuditOrchestrator().audit(
            _clean_params(land_area_sqm=6000.0),
            zone_type="제1종일반주거지역", sigungu=None,
        )
        upzoning = result["sections"]["s4_incentives"]["upzoning"]
        redev = next(s for s in upzoning["scenarios"] if s["path_key"] == "정비사업")
        assert redev["expected_far_pct_high"] == 250
        assert redev["expected_far_source"] == "국토계획법 시행령 법정 범위(목표지역 조례 확인 필요)"

    async def test_sigungu_relay_does_not_override_explicit_regulation_payload_sigungu(self):
        """명시값 우선 — regulation_payload.local_ordinance.sigungu가 이미 있으면 오케스트레이터
        보유 sigungu로 덮어쓰지 않는다(무날조 원칙: 명시값 보존)."""
        payload = {"local_ordinance": {"sigungu": "서울특별시"}}
        result = await DesignAuditOrchestrator().audit(
            _clean_params(land_area_sqm=6000.0),
            zone_type="제1종일반주거지역", sigungu="용인시", regulation_payload=payload,
        )
        upzoning = result["sections"]["s4_incentives"]["upzoning"]
        redev = next(s for s in upzoning["scenarios"] if s["path_key"] == "정비사업")
        # 서울특별시 조례(제2종일반주거=200) 채택 — 용인시(240) 값으로 덮이지 않아야 함.
        assert redev["expected_far_pct_high"] == 200

    async def test_special_districts_absent_yields_honest_data_gap_and_rfi(self):
        """pnu도 address도 없어 서버측 조회 자체가 시도되지 않는 경우 — upzoning.data_gaps
        + RFI 방출(무음 가정 금지, W3-6)."""
        result = await DesignAuditOrchestrator().audit(
            _clean_params(), zone_type=ZONE, sigungu="서울특별시", pnu=None, address=None,
        )
        s4 = result["sections"]["s4_incentives"]
        data_gaps = s4["upzoning"]["data_gaps"]
        assert data_gaps and "규제구역" in data_gaps[0] and "미수집" in data_gaps[0]
        rfi = s4.get("rfi_register")
        assert rfi is not None
        assert rfi["item_count"] == 1
        assert rfi["items"][0]["missing_what"].startswith("규제구역")
        assert rfi["items"][0]["subject_ref"] == "field=upzoning.special_districts"

    async def test_special_districts_present_empty_list_no_data_gap(self):
        """확인 결과 규제구역 없음([])은 '미수집'과 달리 data_gaps를 남기지 않는다(과탐지 방지)."""
        payload = {"local_ordinance": {}, "special_districts": []}
        result = await DesignAuditOrchestrator().audit(
            _clean_params(), zone_type=ZONE, sigungu="서울특별시", regulation_payload=payload,
        )
        s4 = result["sections"]["s4_incentives"]
        assert s4["upzoning"]["data_gaps"] == []
        assert "rfi_register" not in s4

    async def test_special_districts_fetched_server_side_by_pnu(self, monkeypatch):
        """R2 MEDIUM 봉합 — pnu만으로 서버가 VWorldService.get_land_use_plan을 직접 호출해
        special_districts를 조달한다(프론트 릴레이 불필요·실원천 배선). 실제로 개발제한구역이
        blocked_reasons에 반영됨을 확인(오탐 없는 진짜 규제구역 반영)."""
        async def fake_get_land_use_plan(_self, pnu):
            assert pnu == "4159010500100010000"
            return [{"district_name": "개발제한구역"}, {"district_name": "도시지역"}]

        import app.services.external_api.vworld_service as vw
        monkeypatch.setattr(vw.VWorldService, "get_land_use_plan", fake_get_land_use_plan)

        result = await DesignAuditOrchestrator().audit(
            _clean_params(land_area_sqm=20000.0), zone_type="자연녹지지역", sigungu="용인시",
            pnu="4159010500100010000",
        )
        s4 = result["sections"]["s4_incentives"]
        assert s4["upzoning"]["data_gaps"] == []  # 조회 성공 — 미수집 아님
        assert "rfi_register" not in s4
        scenarios = s4["upzoning"]["scenarios"]
        assert scenarios
        assert all("개발제한" in " ".join(s["blocked_reasons"]) for s in scenarios)

    async def test_special_districts_fetch_failure_falls_back_to_data_gap(self, monkeypatch):
        """VWorld 조회 실패(예외)는 미수집으로 정직 폴백(무중단 — 인센티브 산출 자체는 계속됨)."""
        async def boom(_self, pnu):
            raise RuntimeError("vworld down")

        import app.services.external_api.vworld_service as vw
        monkeypatch.setattr(vw.VWorldService, "get_land_use_plan", boom)

        result = await DesignAuditOrchestrator().audit(
            _clean_params(), zone_type=ZONE, sigungu="서울특별시", pnu="1111010100",
        )
        s4 = result["sections"]["s4_incentives"]
        assert s4["upzoning"]["data_gaps"], "조회 실패는 미수집으로 폴백해야 함"

    async def test_special_districts_explicit_payload_wins_over_server_fetch(self, monkeypatch):
        """명시값 우선 — regulation_payload.special_districts가 이미 있으면 pnu가 있어도
        서버측 조회로 덮어쓰지 않는다(무날조 원칙: 명시값 보존, sigungu와 동형 계약)."""
        called = False

        async def fake_get_land_use_plan(_self, pnu):
            nonlocal called
            called = True
            return [{"district_name": "개발제한구역"}]

        import app.services.external_api.vworld_service as vw
        monkeypatch.setattr(vw.VWorldService, "get_land_use_plan", fake_get_land_use_plan)

        payload = {"local_ordinance": {}, "special_districts": []}
        result = await DesignAuditOrchestrator().audit(
            _clean_params(), zone_type=ZONE, sigungu="서울특별시",
            regulation_payload=payload, pnu="1111010100",
        )
        assert not called, "명시값(빈 리스트 포함)이 있으면 서버측 조회를 시도하면 안 됨"
        s4 = result["sections"]["s4_incentives"]
        assert s4["upzoning"]["data_gaps"] == []

    # ── R1 재지적(HIGH) 봉합 — get_land_use_plan의 None(하드 실패)을 `or []`로 뭉개
    #    무음 폴백을 이 배선점에서 재도입했던 결함. 4케이스(A 실값·B 빈 리스트 확인완료·
    #    C 예외·D pnu 없음) 전부를 이 오케스트레이터 레벨에서 직접 검증한다.
    async def test_special_districts_case_b_confirmed_empty_via_none_sentinel_no_data_gap(
        self, monkeypatch,
    ):
        """케이스 B — get_land_use_plan이 진짜 []를 반환(확인완료·규제 없음)하면 data_gaps가
        뜨지 않는다(None과 구분 — []는 미수집이 아니다)."""
        async def fake_get_land_use_plan(_self, pnu):
            return []

        import app.services.external_api.vworld_service as vw
        monkeypatch.setattr(vw.VWorldService, "get_land_use_plan", fake_get_land_use_plan)

        result = await DesignAuditOrchestrator().audit(
            _clean_params(), zone_type=ZONE, sigungu="서울특별시", pnu="1111010100",
        )
        s4 = result["sections"]["s4_incentives"]
        assert s4["upzoning"]["data_gaps"] == []
        assert "rfi_register" not in s4

    async def test_special_districts_hard_failure_none_sentinel_yields_data_gap(self, monkeypatch):
        """★HIGH 회귀 앵커 — get_land_use_plan이 None(하드 실패: 키 미설정/HTTP 실패)을
        반환하면 `districts_raw or []`처럼 뭉개지 않고 data_gaps + RFI가 정직하게 발화해야
        한다(R1이 지적한 무음 폴백 재발 지점). 이 테스트는 _run_incentives가
        `if districts_raw is not None` 대신 `districts_raw or []`로 되돌아가면 즉시 FAIL한다
        (실제로 되돌려 확인함 — 봉합 커밋 보고 참조)."""
        async def fake_get_land_use_plan(_self, pnu):
            return None  # get_land_use_plan의 하드 실패 시그널(키 미설정/HTTP 실패)

        import app.services.external_api.vworld_service as vw
        monkeypatch.setattr(vw.VWorldService, "get_land_use_plan", fake_get_land_use_plan)

        result = await DesignAuditOrchestrator().audit(
            _clean_params(), zone_type=ZONE, sigungu="서울특별시", pnu="1111010100",
        )
        s4 = result["sections"]["s4_incentives"]
        data_gaps = s4["upzoning"]["data_gaps"]
        assert data_gaps and "미수집" in data_gaps[0], (
            "get_land_use_plan()=None(하드 실패)이 '확인완료·규제없음'으로 둔갑함 — 무음 폴백 재발"
        )
        rfi = s4.get("rfi_register")
        assert rfi is not None and rfi["item_count"] == 1


class TestOrchestratorGraceful:
    async def test_engine_failure_marked_skipped(self, monkeypatch):
        """엔진 1개가 예외를 던져도 전체는 진행 — failed 표기 + skipped finding(정직)."""
        orchestrator = DesignAuditOrchestrator()

        async def boom(*args, **kwargs):
            raise RuntimeError("의도된 테스트 실패")

        monkeypatch.setattr(orchestrator, "_run_design_review", boom)
        result = await orchestrator.audit(_clean_params(), zone_type=ZONE)

        assert result["engines"]["design_review"] == "failed"
        skipped = [f for f in result["findings"]
                   if f["engine"] == "design_review" and f["status"] == "skipped"]
        assert skipped and "엔진 실행 실패" in skipped[0]["note"]
        # 나머지 엔진은 정상 수행.
        others = {k: v for k, v in result["engines"].items() if k != "design_review"}
        assert all(v == "ok" for v in others.values())
        assert result["overall"]["verdict"] in ("적합", "조건부적합", "부적합", "판정불가")

    async def test_unknown_zone_engines_skip_honestly(self):
        """용도지역 미상 → 한도 의존 엔진은 skipped(허위 한도 생성 금지)."""
        result = await DesignAuditOrchestrator().audit(_clean_params(), zone_type=None)
        assert result["limits"] is None
        for engine in ("design_review", "permit", "incentives", "solar_envelope"):
            findings = [f for f in result["findings"] if f["engine"] == engine]
            assert findings and findings[0]["status"] == "skipped"


class _FakeCaseService:
    """PermitCaseService 호환 모킹 — 외부 API 없이 고정 사례 통계 반환."""

    async def get_nearby_cases(self, pnu, kind="arch", limit=50):
        from app.schemas.permit_case import PermitCaseResponse, PermitCaseSummary

        summary = PermitCaseSummary(
            count=12,
            far_p25=180.0, far_p50=220.0, far_p75=240.0,
            bcr_p25=45.0, bcr_p50=52.0, bcr_p75=58.0,
            main_use_top3=["공동주택"], recent_24m_count=4,
        )
        return PermitCaseResponse(cases=[], summary=summary, total=12, note=None)


class TestCaseCompareIntegration:
    async def test_nearby_cases_joined_via_mock(self):
        """사례비교 결합: get_nearby_cases→summarize→compare_with_nearby_cases 파이프라인."""
        params = _clean_params(far_pct=250.0, bcr_pct=55.0)
        orchestrator = DesignAuditOrchestrator(case_service=_FakeCaseService())
        result = await orchestrator.audit(
            params, zone_type=ZONE, pnu="1168010100100010000"
        )

        assert result["engines"]["case_compare"] == "ok"
        s1 = result["sections"]["s1_samples"]
        assert s1["available"] is True
        assert s1["total"] == 12
        comparison = s1["comparison"]
        assert comparison["sample_count"] == 12
        assert comparison["far_position"]["band"] == "above_p75"  # 250 > p75 240
        assert comparison["vs_median_far_pp"] == pytest.approx(30.0)  # 250 − p50 220

        finding = next(f for f in result["findings"] if f["engine"] == "case_compare")
        assert finding["check_id"] == "nearby_case_position"
        assert finding["status"] == "info"
        assert finding["improvement"]  # 비교 요약 note 동반

    async def test_no_pnu_skips_case_compare(self):
        result = await DesignAuditOrchestrator(case_service=_FakeCaseService()).audit(
            _clean_params(), zone_type=ZONE
        )
        finding = next(f for f in result["findings"] if f["engine"] == "case_compare")
        assert finding["status"] == "skipped"


# ─────────────────────────────────────────────────────────────────────────────
# UP3: run() 라우터 계약 어댑터 — audit() 위임·verdict 영문 별칭·IFC 병합
# ─────────────────────────────────────────────────────────────────────────────
def _grammar_rooms_clean():
    """현관+거실 2실 타일링 — 문법 경고 0(현관-거실 open·현관문 북측·거실 남측창)."""
    return [
        {"name": "현관", "x": 0.0, "y": 0.0, "w": 1.5, "h": 3.0},
        {"name": "거실", "x": 1.5, "y": 0.0, "w": 3.6, "h": 3.0},
    ]


def _grammar_rooms_with_warning():
    """침실2가 복도 없이 거실에만 접함 — 1실 1문(wall 승격) 경고 발생."""
    return _grammar_rooms_clean() + [
        {"name": "침실2", "x": 5.1, "y": 0.0, "w": 3.0, "h": 3.0},
    ]


class TestRunAdapter:
    async def test_run_delegates_site_geometry_rooms_to_audit(self, monkeypatch):
        """run()은 site 분해(zone_type·sigungu·address·pnu)·geometry→shapes·rooms 그대로 audit 위임."""
        orchestrator = DesignAuditOrchestrator()
        captured = {}

        async def fake_audit(params, **kwargs):
            captured["params"] = params
            captured.update(kwargs)
            return {"overall": {"verdict": "적합"}, "findings": []}

        monkeypatch.setattr(orchestrator, "audit", fake_audit)
        shapes = _square_shapes()
        rooms = _grammar_rooms_clean()
        result = await orchestrator.run(
            None,
            site={
                "zone_type": ZONE, "sigungu": "강남구",
                "address": "서울 강남구 역삼동", "pnu": "1168010100100010000",
            },
            params={"far_pct": 200.0},
            geometry=shapes,
            rooms=rooms,
        )
        assert captured["params"] == {"far_pct": 200.0}
        assert captured["zone_type"] == ZONE
        assert captured["sigungu"] == "강남구"
        assert captured["address"] == "서울 강남구 역삼동"
        assert captured["pnu"] == "1168010100100010000"
        assert captured["shapes"] is shapes
        assert captured["rooms"] is rooms
        assert result["overall"]["verdict_en"] == "pass"

    async def test_run_verdict_en_aliases(self, monkeypatch):
        """영문 별칭: 부적합→fail·조건부적합→conditional·적합→pass·판정불가→None(한국어 불변)."""
        assert VERDICT_EN_ALIASES == {"부적합": "fail", "조건부적합": "conditional", "적합": "pass"}
        orchestrator = DesignAuditOrchestrator()
        for korean, english in (
            ("부적합", "fail"), ("조건부적합", "conditional"),
            ("적합", "pass"), ("판정불가", None),
        ):
            async def fake_audit(params, _v=korean, **kwargs):
                return {"overall": {"verdict": _v}, "findings": []}

            monkeypatch.setattr(orchestrator, "audit", fake_audit)
            result = await orchestrator.run(None, site={}, params={})
            assert result["overall"]["verdict"] == korean
            assert result["overall"]["verdict_en"] == english

    async def test_run_real_path_matches_audit_contract(self):
        """라이브 503 버그 수정 핵심: run() 실호출이 audit()와 동일 결정론 결과."""
        result = await DesignAuditOrchestrator().run(
            None,
            site={"zone_type": ZONE},
            params=_clean_params(),
            geometry=_square_shapes(),
        )
        assert result["overall"]["verdict"] == "적합"
        assert result["overall"]["verdict_en"] == "pass"
        assert set(ENGINE_NAMES).issubset(result["engines"])
        assert result["findings"]
        # 기존 응답 키 무파손(additive) — 라우터가 소비하는 키 유지.
        for key in ("schema_version", "limits", "sections", "params_used", "overall"):
            assert key in result

    async def test_run_zone_code_fallback_when_zone_type_absent(self, monkeypatch):
        """결함1 봉합: site.zone_type 부재 시 zone_code로 폴백(용도지역 엔진 미도달 방지)."""
        orchestrator = DesignAuditOrchestrator()
        captured = {}

        async def fake_audit(params, **kwargs):
            captured.update(kwargs)
            return {"overall": {"verdict": "적합"}, "findings": []}

        monkeypatch.setattr(orchestrator, "audit", fake_audit)
        await orchestrator.run(None, site={"zone_code": ZONE}, params={})
        assert captured["zone_type"] == ZONE

        # zone_type이 실려 있으면 zone_type 우선(zone_code 무시).
        captured.clear()
        await orchestrator.run(
            None, site={"zone_type": "준주거지역", "zone_code": ZONE}, params={}
        )
        assert captured["zone_type"] == "준주거지역"

    async def test_run_land_area_falls_back_to_site_when_absent_or_zero(self, monkeypatch):
        """R2 리뷰 LOW-1: 0㎡은 값 없음과 동치 — falsy 통일 가드로 site 값 폴백."""
        orchestrator = DesignAuditOrchestrator()
        captured = {}

        async def fake_audit(params, **kwargs):
            captured["params"] = params
            return {"overall": {"verdict": "적합"}, "findings": []}

        monkeypatch.setattr(orchestrator, "audit", fake_audit)

        # params 미제공 → site 값으로 보강.
        await orchestrator.run(
            None, site={"land_area_sqm": 500.0}, params={}
        )
        assert captured["params"]["land_area_sqm"] == 500.0

        # params.land_area_sqm=0(무의미값) → site 값으로 폴백(과거엔 0이 "명시값"으로 오인돼
        # site 통합값을 덮어쓰지 못했다).
        await orchestrator.run(
            None, site={"land_area_sqm": 500.0}, params={"land_area_sqm": 0}
        )
        assert captured["params"]["land_area_sqm"] == 500.0

        # params에 실값이 있으면 명시값 우선(site로 덮어쓰기 금지 — 무날조 원칙 유지).
        await orchestrator.run(
            None, site={"land_area_sqm": 500.0}, params={"land_area_sqm": 650.0}
        )
        assert captured["params"]["land_area_sqm"] == 650.0

    async def test_run_regulation_payload_passed_through(self, monkeypatch):
        """결함1 봉합: site.regulation_payload가 audit()으로 배선(조례계층 실효한도 산정용)."""
        orchestrator = DesignAuditOrchestrator()
        captured = {}

        async def fake_audit(params, **kwargs):
            captured.update(kwargs)
            return {"overall": {"verdict": "적합"}, "findings": []}

        monkeypatch.setattr(orchestrator, "audit", fake_audit)
        payload = {"local_ordinance": {"ordinance_far": 220.0, "source": "지자체 조례"}}
        await orchestrator.run(
            None, site={"zone_type": ZONE, "regulation_payload": payload}, params={}
        )
        assert captured["regulation_payload"] is payload

    async def test_run_regulation_payload_applies_ordinance_limit_e2e(self):
        """결함1 봉합 라이브검증: regulation_payload가 실제 applicable_limits_for에 도달해
        조례값이 법정한도 대신 적용됨을 audit() 모킹 없이 확인(배선 그 자체를 검증)."""
        payload = {"local_ordinance": {"ordinance_far": 220.0, "source": "지자체 조례"}}
        result = await DesignAuditOrchestrator().run(
            None, site={"zone_type": ZONE, "regulation_payload": payload}, params={}
        )
        assert result["limits"]["applied_far_pct"] == 220.0
        assert result["limits"]["ordinance_confirmed"] is True

    async def test_run_merges_ifc_params_user_first(self, monkeypatch):
        """ifc_file_url 제공 시 params_from_ifc→merge_params(user>ifc) 병합 + 출처 표면화."""
        import app.services.design_audit.geometry_adapter as ga

        async def fake_params_from_ifc(db, project_id, tenant_id, file_url):
            assert file_url == "minio://bim/test.ifc"
            return {
                "available": True,
                "params": {"total_floor_area_sqm": 900.0},
                "source": "bim_ifc", "ifc_version": "IFC4", "raw": None,
                "note": "연면적은 IfcSlab 합 근사",
            }

        monkeypatch.setattr(ga, "params_from_ifc", fake_params_from_ifc)
        result = await DesignAuditOrchestrator().run(
            None,
            site={"zone_type": ZONE},
            params={"far_pct": 160.0, "bcr_pct": 48.0, "land_area_sqm": 500.0},
            ifc_file_url="minio://bim/test.ifc",
        )
        assert result["params_used"]["total_floor_area_sqm"] == 900.0  # IFC 병합
        assert result["params_used"]["far_pct"] == 160.0               # user 우선 유지
        merge = result["param_merge"]
        assert merge["param_sources"]["total_floor_area_sqm"] == "ifc"
        assert merge["param_sources"]["far_pct"] == "user"
        assert merge["ifc_available"] is True


# ─────────────────────────────────────────────────────────────────────────────
# UP3: grammar 섹션 — rooms 제공 시 경계·개구·연결성, None이면 skipped
# ─────────────────────────────────────────────────────────────────────────────
class TestGrammarSection:
    async def test_rooms_none_grammar_skipped(self):
        """rooms 미제공 → grammar skipped(정직) — 기존 8엔진 상태·판정 무파손."""
        result = await DesignAuditOrchestrator().audit(_clean_params(), zone_type=ZONE)
        assert result["sections"]["grammar"]["skipped"] is True
        assert "grammar" not in result["engines"]
        assert not [f for f in result["findings"] if f["engine"] == "grammar"]
        assert result["overall"]["verdict"] == "적합"

    async def test_rooms_clean_grammar_pass(self):
        """경고 없는 타일링 → grammar pass 1건 + sections.grammar 적재(판정 불변)."""
        result = await DesignAuditOrchestrator().audit(
            _clean_params(), zone_type=ZONE, rooms=_grammar_rooms_clean()
        )
        assert result["engines"]["grammar"] == "ok"
        grammar = result["sections"]["grammar"]
        assert grammar["skipped"] is False
        assert grammar["grammar_warnings"] == []
        assert grammar["boundaries"] and grammar["openings"]
        # LDK 오픈플랜: 현관-거실 경계는 open(arch_grammar BOUNDARY_RULES).
        opens = [b for b in grammar["boundaries"] if b["kind"] == "open" and b.get("room_b")]
        assert any({b["room_a"], b["room_b"]} == {"현관", "거실"} for b in opens)
        # 개구: 현관 방화문(entrance) + 거실 남측 채광창.
        assert any(
            o["kind"] == "door" and o["subtype"] == "entrance" and o["fire_rated"]
            for o in grammar["openings"]
        )
        assert any(o["kind"] == "window" and o["room"] == "거실" for o in grammar["openings"])
        finding = next(f for f in result["findings"] if f["engine"] == "grammar")
        assert finding["status"] == "pass"
        assert result["overall"]["verdict"] == "적합"  # grammar pass — 판정 불변

    async def test_grammar_warning_makes_conditional(self):
        """1실 1문 승격 경고 → grammar warning → 조건부적합(기존 결정론 규칙 반영)."""
        result = await DesignAuditOrchestrator().audit(
            _clean_params(), zone_type=ZONE, rooms=_grammar_rooms_with_warning()
        )
        assert result["engines"]["grammar"] == "ok"
        warnings = [
            f for f in result["findings"]
            if f["engine"] == "grammar" and f["status"] == "warning"
        ]
        assert warnings
        assert _FINDING_KEYS.issubset(warnings[0].keys())  # AuditFinding 단일 스키마
        assert warnings[0]["improvement"]  # KB 경고 message 동반
        assert result["sections"]["grammar"]["grammar_warnings"]
        assert result["overall"]["verdict"] == "조건부적합"

    async def test_invalid_rooms_grammar_skipped_not_crash(self):
        """좌표 결손 rooms → grammar skipped(정직) — 예외 미전파·판정 미반영."""
        result = await DesignAuditOrchestrator().audit(
            _clean_params(), zone_type=ZONE, rooms=[{"name": "거실"}]
        )
        assert result["engines"]["grammar"] == "failed"
        finding = next(f for f in result["findings"] if f["engine"] == "grammar")
        assert finding["status"] == "skipped"
        assert "미산출" in finding["note"]
        assert result["overall"]["verdict"] == "적합"  # skipped는 판정 미반영


# ─────────────────────────────────────────────────────────────────────────────
# QA 레인B — change_risk 죽은 엔진 부활(문자열 floors_above/units가 TypeError로
# 죽어 예외가 삼켜지고 'skipped'로 위장 표시되던 결함, 라이브 재현)
# ─────────────────────────────────────────────────────────────────────────────
class TestChangeRiskStringParamRevival:

    async def test_string_floors_and_units_do_not_crash_change_risk(self):
        """★실측 재현: floors_above='5'(brief 추출값 — 문자열)가 design_change_predictor의
        `floors >= 5` 비교에서 'str' vs 'int' TypeError로 죽어 change_risk가 skipped로
        위장 표시되던 결함(routers/design_audit.py:740-745 흡수 지점 + 여기 이중 안전 봉합)."""
        orchestrator = DesignAuditOrchestrator()
        params = _clean_params(floors_above="5", units="20")
        result = await orchestrator._run_change_risk(params, ZONE)
        finding = result["findings"][0]
        assert finding["engine"] == "change_risk"
        assert finding["check_id"] == "design_change_risk"
        assert finding["status"] != "skipped"

    async def test_change_risk_engine_ok_in_full_audit_with_string_params(self):
        """오케스트레이터 전체 실행 — change_risk가 'failed'로 죽지 않고 'ok'로 완주.

        parking도 200대로 맞춰 다른 엔진은 전부 pass 시켜(격리) change_risk 단독 warning이
        overall.verdict에 정확히 반영되는지까지 계약으로 확인한다(★R1 MEDIUM④ — 이전에
        `assert overall.verdict == "적합"`을 근거 없이 지웠다는 지적을 받아 복구하되, 실측
        검증 결과에 맞게 '조건부적합'으로 교정했다: change_risk가 문자열 때문에 skipped로
        위장되면 warning이 통계에서 빠져 overall이 '적합'으로 거짓 상향될 수 있었다 — 그
        가려짐이 재발하지 않는지가 이 가드의 실제 의미다).
        """
        params = _clean_params(
            floors_above="16", units="200", parking="200",
        )  # 특별피난계단·부대복리 경고 유도, parking은 맞춰 pass(격리)
        result = await DesignAuditOrchestrator().audit(params, zone_type=ZONE)
        assert result["engines"]["change_risk"] == "ok"
        cr = next(f for f in result["findings"] if f["engine"] == "change_risk")
        assert cr["status"] != "skipped"
        # 문자열 층수·세대수도 실제 예측 산술에 반영돼 경고가 뜬다(16층·200세대 → 승강기·특별피난 등).
        assert cr["status"] == "warning"
        # change_risk의 warning이 은폐되지 않고 overall(warning만 존재 → 조건부적합)에 반영된다.
        assert result["overall"]["verdict"] == "조건부적합"
        assert result["overall"]["counts"].get("fail", 0) == 0

    async def test_int_preserved_not_float_display(self):
        """★R1 MEDIUM① — floors_above="16"이 change_risk design dict에서 int 16으로 보존되고
        (일반 _num()을 썼다면 float 16.0이 돼 "16.0층"으로 표시 회귀했을 것) finding·risks
        텍스트도 "16.0층"이 아니라 "16층"으로 나온다."""
        import json as _json

        orchestrator = DesignAuditOrchestrator()
        params = _clean_params(floors_above="16", units="200")
        result = await orchestrator._run_change_risk(params, ZONE)
        section = result["section"][1]
        dumped = _json.dumps(section, ensure_ascii=False, default=str)
        assert "16.0층" not in dumped
        assert "16층" in dumped


# ─────────────────────────────────────────────────────────────────────────────
# QA 레인B R2(R1 HIGH-1) — rules8/solar_envelope 룰 활성 플래그(엔진 실행 여부가 아니라
# 해당 룰이 실제로 판정 가능했는지). 세트백 0m·높이 무제한 하드코딩이 "판정 완료"로
# 오인되지 않도록 라우터 미검사 각주 교정이 참조하는 명시 플래그.
# ─────────────────────────────────────────────────────────────────────────────
class TestRules8ActivationFlags:

    async def test_setback_evaluated_always_false(self):
        """min_setback_m=0.0(SSOT 부재 하드코딩) — 검증기가 이격거리 위반을 원천적으로 낼 수
        없으므로 setback_evaluated는 실제 데이터 경로가 생기기 전까지 상시 False."""
        orch = DesignAuditOrchestrator()
        result = await orch._run_rules8(
            _clean_params(), _square_shapes(),
            applied_bcr=60.0, applied_far=250.0, max_height=100.0, sigungu=None,
        )
        section = result["section"][1]
        assert section["setback_evaluated"] is False

    async def test_height_rule_active_true_with_real_max_height(self):
        """실측 max_height가 주어지면 height_rule_active=True — '높이제한_준수' 차감 대상."""
        orch = DesignAuditOrchestrator()
        result = await orch._run_rules8(
            _clean_params(), _square_shapes(),
            applied_bcr=60.0, applied_far=250.0, max_height=100.0, sigungu=None,
        )
        section = result["section"][1]
        assert section["height_rule_active"] is True

    async def test_height_rule_active_false_when_max_height_none(self):
        """★리뷰어 실증 — 높이 무제한(max_height=None)이면 검증기가 inf로 대체돼 위반이
        안 나지만(violations에 height 타입 없음), 이것이 '높이를 실제로 판정했다'를
        의미하지 않는다 — height_rule_active=False로 정직 표기."""
        orch = DesignAuditOrchestrator()
        result = await orch._run_rules8(
            _clean_params(), _square_shapes(),
            applied_bcr=60.0, applied_far=250.0, max_height=None, sigungu=None,
        )
        section = result["section"][1]
        assert section["height_rule_active"] is False
        assert all(v["type"] != "height" for v in section["violations"])


class TestSolarEnvelopeActivationFlag:

    async def test_height_evaluated_false_without_height_input(self):
        """★리뷰어 실증 — 높이 미입력이면 solar_envelope가 trivial PASS(현재="높이 미입력")를
        내지만 실제 인벨로프 판정이 아니다 — height_evaluated=False로 정직 표기."""
        orch = DesignAuditOrchestrator()
        params = _clean_params()
        params.pop("building_height_m")
        result = await orch._run_solar(
            params, ZONE, applied_bcr=60.0, applied_far=250.0, sigungu=None,
        )
        finding = result["findings"][0]
        section = result["section"][1]
        assert finding["current"] == "높이 미입력"
        assert section["height_evaluated"] is False

    async def test_height_evaluated_true_with_applicable_zone_and_height(self):
        """정북일조 적용 zone + 높이 입력 둘 다 있으면 height_evaluated=True — '일조권_준수'
        차감 대상이 되는 유일한 경로."""
        orch = DesignAuditOrchestrator()
        result = await orch._run_solar(
            _clean_params(), ZONE, applied_bcr=60.0, applied_far=250.0, sigungu=None,
        )
        section = result["section"][1]
        assert bool(section["envelope"].get("applies_north_light")) is True
        assert section["height_evaluated"] is True


class TestFiniteFloatGuard:
    """R1 HIGH-2 — finite_float 공용 가드(오케스트레이터 _num·라우터 _coerce_numeric 공유 코어)."""

    def test_nan_and_inf_rejected(self):
        from app.services.design_audit.numeric import finite_float

        assert finite_float("nan") is None
        assert finite_float("inf") is None
        assert finite_float("-inf") is None
        assert finite_float(float("nan")) is None

    def test_finite_values_pass_through(self):
        from app.services.design_audit.numeric import finite_float

        assert finite_float("16") == 16.0
        assert finite_float(3.5) == 3.5
        assert finite_float(True) is None  # bool은 숫자로 취급하지 않는다
        assert finite_float("abc") is None
