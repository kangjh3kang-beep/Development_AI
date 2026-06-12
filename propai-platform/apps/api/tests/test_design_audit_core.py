"""설계심사 코어(U5 — DA-1~DA-3) 테스트.

- DA-1: 한국어 라벨 정규식 폴백(원문 인용 동반·미매칭 null·평→㎡ 환산), PDF graceful.
- DA-2: 출처 병합(user>ifc>brief) + 5% 괴리 conflicts, 도형 검증 패스스루.
- DA-3: AuditFinding 정규화(레지스트리 근거만), overall 결정론 산정,
        엔진 실패 graceful(skipped), 사례비교 결합(모킹).
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
        assert set(result["engines"]) == set(ENGINE_NAMES)
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
