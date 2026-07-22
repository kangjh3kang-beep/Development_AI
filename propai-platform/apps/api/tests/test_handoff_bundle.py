"""Stage Handoff bundle 계약 테스트 (W2-3, v4.0 [단계 인계계약] 실용 1차).

검증 축:
 (a) seal()/verify_for_consumption() 왕복 — 정상 소비.
 (b) checksum 변조(★hard) — payload를 봉인 이후 직접 mutate하면 항상 거부.
 (c) BLOCKED/만료/미허용 schema_version 거부(soft — 예외 타입으로만 구분, 호출부가 흡수 여부 결정).
 (d) CONDITIONAL conditions 보존(seal→to_dict→bundle_from_dict 왕복에서도 유지).
 (e) submission_bundle manifest → HandoffBundle 어댑터 상호운용(동일 checksum 알고리즘).
 (f) project_pipeline 대표 1경로(site_analysis→design) 배선 — 정상 통과 + 변조 시 hard 차단
     + 소비측 하위호환(번들 없이도 동작) + R2 봉합 3종:
       - MEDIUM-1: 소비대상(state.site_to_design 라이브 객체) ↔ 봉인 스냅샷 드리프트 대조(soft).
       - MEDIUM-2: decision=BLOCKED 가 실제 프로덕션 경로(E7 assumed_defaults)에서 방출됨을
         합성 seal() 이 아니라 _run_site_analysis 실배선으로 검증 + soft 흡수 확인.
       - LOW-1: 번들 부재/형식손상 시 handoff_unverified 표식(무음 우회 금지 — 감사성).
"""
from __future__ import annotations

import copy

import pytest

from app.services.provenance.handoff_bundle import (
    CURRENT_SCHEMA_VERSION,
    HandoffBlockedDecisionError,
    HandoffBundle,
    HandoffBundleRejectedError,
    HandoffChecksumMismatchError,
    HandoffDecision,
    HandoffExpiredError,
    HandoffSchemaVersionError,
    bundle_from_dict,
    compute_payload_checksum,
    decision_from_gate_result,
    from_submission_bundle_manifest,
    seal,
)

# ══════════════════════════════════════════════════════════════════════════
# (a) seal()/verify_for_consumption() 왕복
# ══════════════════════════════════════════════════════════════════════════


def test_seal_produces_bundle_with_uuid_and_checksum():
    bundle = seal(producer="site_analysis", payload={"zone_type": "제2종일반주거지역", "max_far": 200.0})
    assert bundle.bundle_id  # uuid4 hex 발급
    assert len(bundle.bundle_id) == 32
    assert bundle.producer == "site_analysis"
    assert bundle.decision == HandoffDecision.PASS.value
    assert bundle.schema_version == CURRENT_SCHEMA_VERSION
    assert bundle.payload == {"zone_type": "제2종일반주거지역", "max_far": 200.0}
    assert len(bundle.payload_checksum) == 64  # sha256 hex


def test_verify_for_consumption_passes_for_untampered_bundle():
    bundle = seal(producer="design", payload={"total_gfa_sqm": 1000.0})
    bundle.verify_for_consumption()  # 예외 없이 통과


def test_seal_snapshots_payload_deepcopy_not_affected_by_later_mutation():
    """호출부가 seal() 이후 원본 dict를 계속 수정해도(흔한 재사용 패턴) 스냅샷은 불변."""
    original = {"max_far": 200.0}
    bundle = seal(producer="site_analysis", payload=original)
    original["max_far"] = 999.0  # 원본 나중에 수정
    assert bundle.payload["max_far"] == 200.0  # 스냅샷은 봉인 시점 값 유지
    bundle.verify_for_consumption()  # 여전히 정상 통과


def test_compute_payload_checksum_matches_seal_checksum_for_same_payload():
    """compute_payload_checksum()은 seal() 내부 알고리즘과 동일 — 소비대상 드리프트 대조의 전제."""
    payload = {"zone_type": "제2종일반주거지역", "max_far": 200.0}
    bundle = seal(producer="site_analysis", payload=payload)
    assert compute_payload_checksum(payload) == bundle.payload_checksum


def test_compute_payload_checksum_differs_for_different_payload():
    assert compute_payload_checksum({"a": 1}) != compute_payload_checksum({"a": 2})


# ══════════════════════════════════════════════════════════════════════════
# (b) checksum 변조 — ★hard, 항상 거부
# ══════════════════════════════════════════════════════════════════════════


def test_checksum_mismatch_after_direct_payload_mutation_is_hard_rejected():
    """봉인된 bundle.payload 자체를 직접 mutate하면(변조 재현) checksum 불일치로 잡힌다."""
    bundle = seal(producer="site_analysis", payload={"max_far": 200.0})
    bundle.payload["max_far"] = 9999.0  # ★변조 재현(외부에서 스냅샷을 직접 건드림)
    with pytest.raises(HandoffChecksumMismatchError):
        bundle.verify_for_consumption()


def test_checksum_mismatch_error_reports_both_checksums():
    bundle = seal(producer="site_analysis", payload={"a": 1})
    bundle.payload["a"] = 2
    with pytest.raises(HandoffChecksumMismatchError) as exc_info:
        bundle.verify_for_consumption()
    err = exc_info.value
    assert err.expected_checksum == bundle.payload_checksum
    assert err.actual_checksum != bundle.payload_checksum
    assert err.bundle_id == bundle.bundle_id


def test_checksum_check_runs_before_decision_check():
    """checksum이 어긋나면(payload 신뢰 불가) decision=BLOCKED 여부보다 먼저 checksum 오류가 난다."""
    bundle = seal(producer="x", payload={"a": 1}, decision=HandoffDecision.BLOCKED.value)
    bundle.payload["a"] = 2
    with pytest.raises(HandoffChecksumMismatchError):
        bundle.verify_for_consumption()


# ══════════════════════════════════════════════════════════════════════════
# (c) BLOCKED/만료/schema_version 거부 — soft(예외 타입으로만 구분)
# ══════════════════════════════════════════════════════════════════════════


def test_blocked_decision_rejected():
    bundle = seal(producer="design", payload={}, decision=HandoffDecision.BLOCKED.value)
    with pytest.raises(HandoffBlockedDecisionError):
        bundle.verify_for_consumption()


def test_blocked_decision_error_is_subclass_of_common_base():
    """호출부가 폭넓게 HandoffBundleRejectedError 로 soft 흡수할 수 있어야 한다."""
    bundle = seal(producer="design", payload={}, decision=HandoffDecision.BLOCKED.value)
    with pytest.raises(HandoffBundleRejectedError):
        bundle.verify_for_consumption()


def test_expired_bundle_rejected():
    bundle = seal(producer="design", payload={}, expiry="2020-01-01T00:00:00+00:00")
    with pytest.raises(HandoffExpiredError):
        bundle.verify_for_consumption(now="2026-07-22T00:00:00+00:00")


def test_not_yet_expired_bundle_passes():
    bundle = seal(producer="design", payload={}, expiry="2099-01-01T00:00:00+00:00")
    bundle.verify_for_consumption(now="2026-07-22T00:00:00+00:00")  # 통과


def test_no_expiry_never_rejected_on_time():
    bundle = seal(producer="design", payload={})
    assert bundle.expiry is None
    bundle.verify_for_consumption(now="2099-01-01T00:00:00+00:00")  # 무제한 — 통과


def test_unallowed_schema_version_rejected():
    bundle = seal(producer="design", payload={}, schema_version="propai.handoff_bundle/0.1")
    with pytest.raises(HandoffSchemaVersionError):
        bundle.verify_for_consumption(allowed_schema_versions={CURRENT_SCHEMA_VERSION})


def test_allowed_schema_version_passes():
    bundle = seal(producer="design", payload={})
    bundle.verify_for_consumption(allowed_schema_versions={CURRENT_SCHEMA_VERSION})


def test_schema_version_check_skipped_when_allowlist_not_given():
    """allowed_schema_versions 미지정(None)이면 어떤 schema_version 이든 통과(옵트인 검사)."""
    bundle = seal(producer="design", payload={}, schema_version="anything/9.9")
    bundle.verify_for_consumption()  # allowlist 없음 — 통과


def test_illegal_decision_value_rejected_at_construction():
    """decision 값 자체의 무결성 — HandoffBundle 생성 시점에 즉시 거부(정직 하강 아님)."""
    with pytest.raises(ValueError):
        HandoffBundle(
            bundle_id="x", producer="p", created_at="t", payload_checksum="c",
            payload={}, decision="NOT_A_REAL_DECISION",
        )


# ══════════════════════════════════════════════════════════════════════════
# (d) CONDITIONAL conditions 보존
# ══════════════════════════════════════════════════════════════════════════


def test_conditional_decision_preserves_conditions_through_seal():
    bundle = seal(
        producer="site_analysis", payload={"max_far": 0.0},
        decision=HandoffDecision.CONDITIONAL.value,
        conditions=["max_far 미산정(0.0 센티널)"],
    )
    assert bundle.decision == HandoffDecision.CONDITIONAL.value
    assert bundle.conditions == ["max_far 미산정(0.0 센티널)"]
    bundle.verify_for_consumption()  # CONDITIONAL 은 소비 자체를 막지 않는다(soft 축)


def test_conditional_conditions_survive_to_dict_and_bundle_from_dict_round_trip():
    bundle = seal(
        producer="site_analysis", payload={"a": 1},
        decision=HandoffDecision.CONDITIONAL.value,
        conditions=["c1", "c2"],
    )
    restored = bundle_from_dict(bundle.to_dict())
    assert restored is not None
    assert restored.decision == HandoffDecision.CONDITIONAL.value
    assert restored.conditions == ["c1", "c2"]
    restored.verify_for_consumption()  # 왕복 후에도 checksum 유효


def test_bundle_from_dict_rejects_non_dict_input():
    assert bundle_from_dict(None) is None
    assert bundle_from_dict("garbage") is None  # type: ignore[arg-type]


def test_bundle_from_dict_returns_none_on_illegal_decision():
    """역직렬화 경로도 형식 불일치는 예외 대신 None(날조 금지 — lineage_from_dict 동형)."""
    d = seal(producer="p", payload={}).to_dict()
    d["decision"] = "GARBAGE"
    assert bundle_from_dict(d) is None


def test_decision_from_gate_result_maps_to_handoff_vocabulary():
    assert decision_from_gate_result(ok=False) == HandoffDecision.BLOCKED.value
    assert decision_from_gate_result(ok=True, has_warnings=True) == HandoffDecision.CONDITIONAL.value
    assert decision_from_gate_result(ok=True, has_warnings=False) == HandoffDecision.PASS.value


# ══════════════════════════════════════════════════════════════════════════
# (e) submission_bundle manifest → HandoffBundle 어댑터 상호운용
# ══════════════════════════════════════════════════════════════════════════


def _all_required_svgs() -> dict[str, str]:
    from app.services.cad.sheet_frame import required_sheet_codes

    return {code: f"<svg>{code}</svg>" for code in required_sheet_codes()}


def test_from_submission_bundle_manifest_reuses_bundle_hash_as_checksum():
    from app.services.report.submission_bundle import build_submission_bundle

    _zip_bytes, manifest = build_submission_bundle(
        project_id="p1", project_name="테스트", drawings_svg=_all_required_svgs(),
    )
    bundle = from_submission_bundle_manifest(manifest)
    assert bundle.producer == "submission_bundle"
    assert bundle.payload_checksum == manifest["bundle_hash"]
    assert bundle.decision == HandoffDecision.PASS.value
    # ★상호운용 핵심: 이 모듈이 독자적으로 재계산한 checksum도 manifest의 bundle_hash와
    # 정확히 같아야 한다(알고리즘 동일성 — verify_for_consumption 이 그대로 통과해야 함).
    bundle.verify_for_consumption()


def test_from_submission_bundle_manifest_without_bundle_hash_raises():
    with pytest.raises(ValueError):
        from_submission_bundle_manifest({"project_id": "p1"})


def test_from_submission_bundle_manifest_tampered_manifest_detected_by_verify():
    """submission_bundle의 매니페스트를 어댑터 변환 후 변조하면 이 모듈도 checksum 불일치로 잡는다."""
    from app.services.report.submission_bundle import build_submission_bundle

    _zip_bytes, manifest = build_submission_bundle(
        project_id="p1", project_name="테스트", drawings_svg=_all_required_svgs(),
    )
    bundle = from_submission_bundle_manifest(manifest)
    tampered_payload = copy.deepcopy(bundle.payload)
    tampered_payload["project_name"] = "위조된이름"
    tampered = HandoffBundle(
        bundle_id=bundle.bundle_id, producer=bundle.producer, created_at=bundle.created_at,
        payload_checksum=bundle.payload_checksum, payload=tampered_payload,
    )
    with pytest.raises(HandoffChecksumMismatchError):
        tampered.verify_for_consumption()


# ══════════════════════════════════════════════════════════════════════════
# (f) project_pipeline 대표 1경로(site_analysis→design) 배선
#
# ★오프라인·결정적 원칙(test_project_pipeline_usable_propagation.py·test_project_pipeline_
# rerun.py 선례 동형): _run_site_analysis 전체를 실행하되 site_data 에 zone_type+조례값을
# 직접 주입하고 LandInfoService.collect_comprehensive 만 monkeypatch로 대역해 외부
# 네트워크(VWorld/MOLIT 등)를 우회한다 — pipeline.run() 전체 호출(단계 전 실행) 대신 단계
# 함수(_run_site_analysis/_run_design)를 직접 호출해 결정적·고속으로 검증한다.
# ══════════════════════════════════════════════════════════════════════════

# asyncio_mode="auto" (pyproject) — async 테스트 함수는 마커 없이 자동 수집된다.


def _fresh_state(project_id: str = "t-w2-3"):
    from app.services.pipeline.project_pipeline import PipelineStage, PipelineState, StageResult

    state = PipelineState(project_id=project_id, address="서울특별시 강남구 역삼동 736")
    for stage in PipelineStage:
        state.stages[stage.value] = StageResult(stage=stage)
    return state


@pytest.fixture
def _stub_land_info(monkeypatch):
    """LandInfoService.collect_comprehensive 를 빈 dict 로 대역(무네트워크 — 위 원칙 참고)."""
    from app.services.land_intelligence.land_info_service import LandInfoService

    async def _empty(self, address):  # noqa: ANN001, ARG001
        return {}

    monkeypatch.setattr(LandInfoService, "collect_comprehensive", _empty)


_SITE_DATA = {
    "zone_type": "제2종일반주거지역",
    "land_area_sqm": 500.0,
    "ordinance_bcr": 60.0,
    "ordinance_far": 200.0,
    "ordinance_source": "test",
    "official_land_price": 3_000_000.0,
}


async def test_pipeline_site_analysis_seals_handoff_bundle(_stub_land_info):
    """_run_site_analysis 가 site_to_design 과 함께 HandoffBundle 을 봉인한다."""
    from app.services.pipeline.project_pipeline import ProjectPipeline

    pipeline = ProjectPipeline()
    state = _fresh_state()
    await pipeline._run_site_analysis(state, {"site_data": dict(_SITE_DATA)})

    assert state.site_to_design is not None
    assert state.site_to_design_bundle is not None
    assert state.site_to_design_bundle["producer"] == "site_analysis"
    assert state.site_to_design_bundle["decision"] in (
        HandoffDecision.PASS.value, HandoffDecision.CONDITIONAL.value,
    )
    assert len(state.site_to_design_bundle["payload_checksum"]) == 64


async def test_pipeline_normal_handoff_design_stage_has_no_warning(_stub_land_info):
    """정상 통과 — 번들이 유효하면 design 단계 데이터에 soft 표식 3종이 전혀 없다."""
    from app.services.pipeline.project_pipeline import ProjectPipeline

    pipeline = ProjectPipeline()
    state = _fresh_state()
    await pipeline._run_site_analysis(state, {"site_data": dict(_SITE_DATA)})
    await pipeline._run_design(state, {})

    design_data = state.stages["design"].data
    assert "handoff_bundle_warning" not in design_data
    assert "handoff_payload_drift" not in design_data
    assert "handoff_unverified" not in design_data
    assert design_data.get("total_gfa_sqm", 0) > 0


async def test_pipeline_tampered_handoff_bundle_hard_blocks_design_stage(_stub_land_info):
    """★변조 차단 — site_to_design_bundle.payload 를 직접 훼손하면 _run_design 이
    HandoffChecksumMismatchError 를 던진다(무결성 위반은 soft 로 흡수되지 않는다 —
    실제 ProjectPipeline.run() 루프에서는 이 예외가 stage_result.status=FAILED 로 이어진다)."""
    from app.services.pipeline.project_pipeline import ProjectPipeline

    pipeline = ProjectPipeline()
    state = _fresh_state()
    await pipeline._run_site_analysis(state, {"site_data": dict(_SITE_DATA)})
    assert state.site_to_design_bundle is not None

    # ★변조 재현: 봉인된 번들의 payload 스냅샷을 직접 훼손.
    state.site_to_design_bundle["payload"]["max_far"] = -999.0

    with pytest.raises(HandoffChecksumMismatchError):
        await pipeline._run_design(state, {})


async def test_pipeline_design_stage_backward_compatible_without_bundle():
    """소비측 하위호환 — site_to_design_bundle 이 없어도(레거시/미배선 경로) design 단계가
    번들 검증 없이 기존 dict(SiteToDesignPayload) 기반으로 정상 동작한다.

    ★R1 LOW-1 봉합: 무음 우회가 아니라 handoff_unverified 표식으로 "미검증 소비"임을
    남긴다("검증통과"와 구분 — 감사 가능성)."""
    from app.services.pipeline.project_pipeline import ProjectPipeline, SiteToDesignPayload

    pipeline = ProjectPipeline()
    state = _fresh_state()
    state.site_to_design = SiteToDesignPayload(
        zone_type="제2종일반주거지역", max_bcr=60.0, max_far=200.0, land_area_sqm=500.0,
    )
    assert state.site_to_design_bundle is None

    await pipeline._run_design(state, {})  # 예외 없이 통과 — 번들 부재는 완전 무해

    design_data = state.stages["design"].data
    assert "handoff_bundle_warning" not in design_data
    assert "handoff_unverified" in design_data
    assert design_data.get("total_gfa_sqm") == pytest.approx(500.0 * (200.0 / 100))


async def test_pipeline_design_marks_unverified_when_bundle_dict_malformed(_stub_land_info):
    """★R1 LOW-1 봉합(malformed 경로) — site_to_design_bundle 이 있지만 형식이 손상돼
    bundle_from_dict() 가 None 을 반환하면(예: decision 값 자체가 불법) 검증을 생략하고
    handoff_unverified 로 남긴다(무음 우회 금지)."""
    from app.services.pipeline.project_pipeline import ProjectPipeline

    pipeline = ProjectPipeline()
    state = _fresh_state()
    await pipeline._run_site_analysis(state, {"site_data": dict(_SITE_DATA)})
    assert state.site_to_design_bundle is not None

    # ★형식 손상 재현: decision 을 계약 밖 값으로 훼손 — bundle_from_dict() 가 None 반환.
    state.site_to_design_bundle["decision"] = "NOT_A_REAL_DECISION"

    await pipeline._run_design(state, {})  # 예외 없이 통과(soft)

    design_data = state.stages["design"].data
    assert "handoff_unverified" in design_data
    assert "malformed" in design_data["handoff_unverified"] or "손상" in design_data["handoff_unverified"]


async def test_pipeline_consumer_drift_detected_when_live_object_diverges_from_sealed_snapshot(
    _stub_land_info,
):
    """★R1 MEDIUM-1 봉합 — 리뷰어 실증 재현: bundle.payload(봉인 스냅샷)가 아니라 실제
    소비대상인 state.site_to_design(라이브 객체) 자체를 직접 변조하면, verify_for_
    consumption() 자체(번들 내부 자기무결성)는 통과하지만, 소비 직전 재직렬화 대조가
    드리프트를 soft 로 잡아낸다(★hard 미승격 근거: 스파이크 결과 seal()~소비 사이 구간에
    site_to_design 을 정당하게 재대입하는 코드 경로가 없음을 확인했으나, 운영에서 그런
    경로가 실제로 없다는 것이 확증되기 전까지는 hard 승격을 보류한다 — W2-2 UNTRACED와
    동일 전략)."""
    from app.services.pipeline.project_pipeline import ProjectPipeline

    pipeline = ProjectPipeline()
    state = _fresh_state()
    await pipeline._run_site_analysis(state, {"site_data": dict(_SITE_DATA)})

    # ★리뷰어 실증 재현: 번들(state.site_to_design_bundle)이 아니라 라이브 소비 객체 자체를 변조.
    state.site_to_design.max_far = 800.0

    await pipeline._run_design(state, {})  # 예외 없이 통과(soft) — 하지만 드리프트 표식이 남는다

    design_data = state.stages["design"].data
    assert "handoff_payload_drift" in design_data
    assert "handoff_bundle_warning" not in design_data  # bundle 자체(내부)는 무결
    assert "handoff_unverified" not in design_data  # 검증은 수행됨(미검증 아님)


@pytest.fixture
def _stub_full_offline(monkeypatch):
    """AutoZoningService/OrdinanceService/LandInfoService 전부 빈 폴백 + AI noop.

    site_data 에 zone_type 을 아예 주지 않아 _fetch_real_site_data 의 E7 assumed_defaults
    경로(외부수집 전면 실패 → zone_type 등 전부 가정치)를 결정적으로 재현한다
    (test_project_pipeline_rerun._patch_offline 과 동형 — 무네트워크·고속)."""
    from app.services.land_intelligence import land_info_service as lis
    from app.services.land_intelligence import ordinance_service as ords
    from app.services.pipeline.project_pipeline import ProjectPipeline
    from app.services.zoning import auto_zoning_service as azs

    async def _empty_comprehensive(self, address, pnu=None):  # noqa: ANN001, ARG001
        return {}

    async def _empty_zoning(self, address):  # noqa: ANN001, ARG001
        return {}

    async def _fallback_ordinance(self, address, zone_type):  # noqa: ANN001, ARG001
        return {"ordinance_bcr": None, "ordinance_far": None, "source": "법정상한"}

    async def _noop_site_ai(self, state):  # noqa: ANN001, ARG001
        return None

    monkeypatch.setattr(lis.LandInfoService, "collect_comprehensive", _empty_comprehensive)
    monkeypatch.setattr(azs.AutoZoningService, "analyze_by_address", _empty_zoning)
    monkeypatch.setattr(ords.OrdinanceService, "get_ordinance_limits", _fallback_ordinance)
    monkeypatch.setattr(ProjectPipeline, "_attach_site_ai", _noop_site_ai)


async def test_pipeline_site_analysis_emits_blocked_decision_when_assumed_defaults(
    _stub_full_offline,
):
    """★R1 MEDIUM-2 봉합(soft 실배선) — 외부수집 전면 실패로 E7 assumed_defaults 경로(zone_type
    등 전부 가정치)에 실제로 빠지면 seal() 이 decision=BLOCKED 를 방출한다(합성 seal() 호출이
    아니라 _run_site_analysis 실제 배선 경로에서 검증 — BLOCKED soft 분기가 사문이 아님을 증명)."""
    from app.services.pipeline.project_pipeline import ProjectPipeline

    pipeline = ProjectPipeline()
    state = _fresh_state()
    await pipeline._run_site_analysis(state, {})  # site_data 없음 → 전면 가정치 경로

    assert state.stages["site_analysis"].data.get("data_quality") == "assumed_defaults"
    assert state.site_to_design_bundle is not None
    assert state.site_to_design_bundle["decision"] == HandoffDecision.BLOCKED.value
    # ★기존 정직 표식(assumed_fields) 그대로 재사용 — 장식적 문구 새로 짓지 않음.
    assert state.site_to_design_bundle["conditions"] == state.stages["site_analysis"].data.get(
        "assumed_fields"
    )


async def test_pipeline_design_stage_soft_absorbs_blocked_handoff(_stub_full_offline):
    """BLOCKED 번들을 소비해도(soft) 파이프라인은 계속 진행하고 design 단계 data 에
    handoff_bundle_warning 표식만 남긴다(하드 차단 아님 — BLOCKED soft 경로의 실제 도달 확인)."""
    from app.services.pipeline.project_pipeline import ProjectPipeline

    pipeline = ProjectPipeline()
    state = _fresh_state()
    await pipeline._run_site_analysis(state, {})
    assert state.site_to_design_bundle["decision"] == HandoffDecision.BLOCKED.value

    await pipeline._run_design(state, {})  # 예외 없이 통과(soft)

    design_data = state.stages["design"].data
    assert "BLOCKED" in design_data.get("handoff_bundle_warning", "")
    assert "handoff_unverified" not in design_data  # 검증은 수행됨(BLOCKED 로 판정됐을 뿐)
    assert design_data.get("total_gfa_sqm", 0) > 0  # 파이프라인 자체는 무중단
