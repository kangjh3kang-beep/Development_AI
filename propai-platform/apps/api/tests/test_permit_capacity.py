"""심의엔진 PermitProcessResult → SpecialistAgent 정규화(_map_permit_response) 단위테스트.

★검증 초점(실결과화): 엔진이 산출한 매스 용량검증(capacity)·정량 계측(measures)·단계 완결성
(stage_status)·예상 쟁점(issues)이 finding/summary에 표면화되는지 확인한다. 이전 매핑은 단계
부합도(basis/links)만 옮기고 capacity·measures를 누락 → 설계 핵심 산출(규모 적정성)이 보이지
않았다. 실엔진·DB 없이 결정론 매핑만 검증(수치 생성 없음, 표면화만).

기존 basis/links(설명가능성 전파, EX2)가 회귀 없이 유지되는지도 함께 검증한다.
"""

from __future__ import annotations

from app.services.agents.registry import _CAPACITY_KEYS, _map_permit_response


def _stage_with_capacity() -> dict:
    """capacity(매스 용량검증)+measures(정량 계측)+issues+status+legal_basis를 모두 가진 대표 단계.

    엔진 계약(CapacityEnvelope·StageResult·CriterionResult) 실측 키를 그대로 모사한다.
    proposed_gfa_sqm이 있으므로 conformance_basis 주석이 부착되어야 한다.
    """
    return {
        "stage_id": "massing", "name": "매스 용량검증",
        "status": "DONE", "conformance": "부합", "verification_status": "NEEDS_REVIEW",
        "issues": ["정북일조 완화 미반영(추가 제약 별도)"],
        "criteria": [
            {
                "criterion_id": "far", "kind": "ratio",
                "measured": 199.5, "limit": 200.0, "conformance": "부합", "grade": "A",
                # legal_basis가 있으면 basis/links(설명가능성 전파)가 채워져야 한다.
                "legal_basis": [{"law": "국토의 계획 및 이용에 관한 법률", "article": "제78조",
                                 "summary": "용적률 한도"}],
            },
        ],
        "capacity": {
            "plot_area_sqm": 1000.0, "far_pct": 200.0, "bcr_pct": 60.0,
            "max_gfa_sqm": 2000.0, "max_footprint_sqm": 600.0,
            "proposed_gfa_sqm": 1900.0, "margin_sqm": 100.0,
            "conformance": "부합", "caveat": "SSOT 한도 기반 최대 캐파",
            "legal_basis": [{"law": "국토의 계획 및 이용에 관한 법률", "article": "제78조"}],
            # _CAPACITY_KEYS에 없는 잉여 키 — 결과에 새어나오면 안 된다(필터링 검증용).
            "internal_debug": "leak-me-not",
        },
    }


def _stage_without_capacity() -> dict:
    """capacity 없는 단계 — capacity 키가 결과에 없어야(graceful, 날조 금지)."""
    return {
        "stage_id": "intake", "name": "접수 요건",
        "status": "NEEDS_INPUT", "conformance": "HELD",
        "verification_status": "BLOCKED",
        "criteria": [],  # legal_basis 없음 → basis/links 빈 리스트
    }


def test_capacity_surfaced_filtered_and_conformance_basis():
    """capacity가 finding에 표면화되고 _CAPACITY_KEYS로 필터링 + proposed_gfa 있으면 conformance_basis 부착."""
    res = {"spec_id": "permit-v1", "run_id": "run-1",
           "overall_conformance": "부합", "overall_verification": "NEEDS_REVIEW",
           "overall_outcome": "가능",
           "stages": [_stage_with_capacity()]}
    out = _map_permit_response(res)
    f = out["findings"][0]

    cap = f.get("capacity")
    assert cap is not None, "capacity가 finding에 표면화되어야 한다"
    # _CAPACITY_KEYS + legal_basis + conformance_basis만 존재(잉여 키 누출 금지).
    assert "internal_debug" not in cap, "_CAPACITY_KEYS 외 잉여 키는 필터링되어야 한다"
    for k in _CAPACITY_KEYS:
        assert k in cap, f"capacity에 {k} 키가 있어야 한다"
    assert cap["proposed_gfa_sqm"] == 1900.0
    assert cap["margin_sqm"] == 100.0
    assert cap["legal_basis"], "capacity legal_basis가 전파되어야 한다"
    # proposed_gfa_sqm이 있으므로 부합 판정 기준 주석 부착.
    assert "conformance_basis" in cap
    assert "SSOT" in cap["conformance_basis"]


def test_measures_stage_status_issues_surfaced():
    """measures(정량 계측)·stage_status(완결성)·issues(예상 쟁점)가 표면화되어야 한다."""
    res = {"stages": [_stage_with_capacity()]}
    f = _map_permit_response(res)["findings"][0]

    assert f["stage_status"] == "DONE", "stage_status(완결성)가 무음 없이 전파되어야 한다"
    assert f.get("issues") == ["정북일조 완화 미반영(추가 제약 별도)"], "issues가 표면화되어야 한다"
    measures = f.get("measures")
    assert measures, "measures(정량 계측)가 표면화되어야 한다"
    m = measures[0]
    assert m["criterion"] == "far"
    assert m["measured"] == 199.5
    assert m["limit"] == 200.0
    assert m["conformance"] == "부합"
    assert m["grade"] == "A"


def test_basis_links_preserved_no_regression():
    """★회귀 방지: 기존 basis(법령·조항·요지)+links(1차출처 URL)가 여전히 finding에 동반되어야 한다."""
    res = {"stages": [_stage_with_capacity()]}
    f = _map_permit_response(res)["findings"][0]

    assert "basis" in f, "basis(설명가능성)가 유지되어야 한다"
    assert "links" in f, "links(1차출처)가 유지되어야 한다"
    # legal_basis가 있으므로 basis에 최소 1건이 집계되어야 한다.
    assert f["basis"], "legal_basis가 있으면 basis가 채워져야 한다"
    assert f["basis"][0]["law"] == "국토의 계획 및 이용에 관한 법률"
    assert f["basis"][0]["article"] == "제78조"


def test_summary_capacity_hoisted_and_core_fields_preserved():
    """capacity 브리프가 summary["capacity"]로 hoist되고, 기존 summary 핵심 필드가 보존되어야 한다."""
    res = {"spec_id": "permit-v1", "run_id": "run-1",
           "overall_conformance": "부합", "overall_verification": "NEEDS_REVIEW",
           "overall_outcome": "가능",
           "stages": [_stage_with_capacity()]}
    summary = _map_permit_response(res)["summary"]

    assert summary["available"] is True
    # ★기존 summary 필드 회귀 방지.
    assert summary["spec_id"] == "permit-v1"
    assert summary["run_id"] == "run-1"
    assert summary["overall_conformance"] == "부합"
    assert summary["overall_verification"] == "NEEDS_REVIEW"
    assert summary["overall_outcome"] == "가능"
    # ★capacity hoist.
    assert "capacity" in summary, "capacity 브리프가 summary로 hoist되어야 한다"
    assert summary["capacity"]["proposed_gfa_sqm"] == 1900.0


def test_stage_without_capacity_is_graceful():
    """capacity 없는 단계 → capacity 키 부재(날조 없음). summary에도 capacity hoist 없음."""
    res = {"stages": [_stage_without_capacity()]}
    out = _map_permit_response(res)
    f = out["findings"][0]

    assert "capacity" not in f, "capacity 미산출 단계엔 capacity 키가 없어야 한다(graceful)"
    assert f["stage_status"] == "NEEDS_INPUT"
    # measures는 criteria가 비어 있으면 부재(빈 계측 미부착).
    assert "measures" not in f
    # issues 없음 → issues 키 부재(빈 리스트 미부착).
    assert "issues" not in f
    # capacity 보유 단계가 없으므로 summary에도 capacity hoist 없음.
    assert "capacity" not in out["summary"]
    # 그래도 basis/links는 항상 동반(빈 리스트로라도).
    assert f["basis"] == []
    assert f["links"] == []


# ─────────────────────────────────────────────────────────────────────────────
# ★엔진 호출 횟수 회귀 방지(HIGH) — Decision Brief use_llm=True 시 net ≤ 2 엔진콜.
#
# 배경(회귀): 이전 델타는 use_llm=True 에서 엔진-디스패치 도메인을 둘(심의→/permit/process,
#   설계→/design/process) 추가했고, 그 위에 기존 _run_deliberation_engine(/api/v1/analyze)까지
#   호출해 엔진 콜이 main 1 → delta 3 으로 뛰었다(지연·과금 3배·같은 부지 이중 심의).
# 엔진 계약(검증됨): capacity(계획 GFA vs 법정 최대 연면적)는 오직 /design/process(run_design_process
#   →capacity_envelope)만 산출한다. /permit/process(심의)는 capacity 미부착이며 그 심의는
#   _run_deliberation_engine(/analyze)의 verdict 와 같은 부지 이중 심의(중복)다.
# 고정 계약(이 테스트가 잠그는 것): use_llm=True 브리프의 '엔진-디스패치 도메인'은 설계 1개만(심의 없음),
#   거기에 verdict 위임 1콜 → net 정확히 2. 심의(/permit/process) 이중 심의는 배선하지 않는다.
#   이 테스트는 3중 디스패치(회귀) 코드에서 반드시 FAIL(설계+심의=2 도메인 → net 3)하고, 수정 후 PASS 한다.
# ─────────────────────────────────────────────────────────────────────────────

import asyncio

from app.services.agents import specialist_dispatch
from app.services.land_intelligence.decision_brief_service import DecisionBriefService

# 엔진에 실호출을 내는(외부 /process·/analyze) 도메인 키 — zoning/permit 등 결정론 로컬 도구는 제외.
_ENGINE_DISPATCH_DOMAINS = {"심의", "설계"}


def test_decision_brief_engine_call_count_capped_no_redundant_deliberation(monkeypatch):
    """use_llm=True Decision Brief 의 '엔진 호출 횟수'가 ≤ 2(verdict 1 + capacity 1)로 고정되고,
    중복 심의(/permit/process) 이중 조회가 사라졌는지 잠근다(회귀 방지).

    실 엔진 호출 지점 두 곳을 모두 seam 으로 가로채 카운트한다:
      1) run_specialist_domains(domains=...) — 넘어온 domains 중 엔진-디스패치 도메인(심의/설계) 개수.
      2) _run_deliberation_engine — verdict 위임 1콜.
    두 seam 을 patch 하므로 외부 네트워크·DB 없이 결정론적으로 호출 그래프만 검증한다.
    """
    captured_domains: dict[str, dict] = {}
    deliberation_calls: list[int] = []

    async def _fake_run_specialist_domains(domains, **_ctx):
        # 넘어온 도메인 스펙 그대로 캡처(엔진-디스패치 도메인 집합 판별용). 실제 디스패치는 하지 않는다.
        captured_domains.update(domains)
        return []

    async def _fake_run_deliberation_engine(self, site_raw, tenant_id):
        deliberation_calls.append(1)
        return {"domain": "deliberation", "status": "ok", "verdict": "가능"}

    # ★run_specialist_domains 는 _run_specialists 안에서 지역 import 되므로 source 모듈에 patch.
    monkeypatch.setattr(specialist_dispatch, "run_specialist_domains",
                        _fake_run_specialist_domains)
    monkeypatch.setattr(DecisionBriefService, "_run_deliberation_engine",
                        _fake_run_deliberation_engine)

    # 결정론 도메인(zoning/permit) 입력이 서게 zone_type 을 준 부지 raw. capacity 입력(면적·용적률)도 공급.
    site_raw = {
        "zone_type": "제2종일반주거지역",
        "pnu": "1", "land_area_sqm": 1000.0,
        "effective_far": {"effective_far_pct": 200.0},
        "supply_areas": [{"total_gfa_sqm": 2000.0, "applied_far_pct": 200.0, "permit_complexity": 1}],
    }
    permit_raw = {"recommendations": [{"development_type": "M06"}]}

    svc = DecisionBriefService()
    out = asyncio.run(svc._run_specialists(
        site_raw=site_raw, reg_raw={}, permit_raw=permit_raw,
        tenant_id=None, project_id=None, address="서울시 강남구 역삼동 1",
        use_llm=True,
    ))
    assert isinstance(out, list)

    # ── 엔진-디스패치 도메인(심의/설계) 개수 = 엔진 process 콜 수 ──
    engine_domains = _ENGINE_DISPATCH_DOMAINS & set(captured_domains.keys())
    # 설계(capacity)는 유지, 심의(/permit/process 이중 심의)는 제거되어야 한다.
    assert "설계" in engine_domains, "capacity 산출용 설계(/design/process) 도메인은 유지되어야 한다"
    assert "심의" not in engine_domains, (
        "중복 심의(/permit/process)는 _run_deliberation_engine(/analyze)과 같은 부지 이중 심의라 제거되어야 한다")

    # ── 총 엔진 호출 = process 콜(엔진 도메인) + verdict 위임(1) ──
    total_engine_calls = len(engine_domains) + len(deliberation_calls)
    assert len(deliberation_calls) == 1, "verdict 위임(_run_deliberation_engine)은 정확히 1회여야 한다"
    assert total_engine_calls <= 2, (
        f"엔진 호출은 net ≤ 2(verdict 1 + capacity 1)여야 한다. 실제={total_engine_calls} "
        f"(엔진도메인={sorted(engine_domains)}, verdict={len(deliberation_calls)}) — 3중 디스패치 회귀")
    assert total_engine_calls == 2, (
        f"정상 경로는 정확히 2콜(설계 capacity 1 + verdict 1)이어야 한다. 실제={total_engine_calls}")
