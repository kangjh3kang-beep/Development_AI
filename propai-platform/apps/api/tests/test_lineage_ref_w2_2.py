"""필드수준 계보 계약(W2-2, v4.0 [필드수준 계보]) 테스트.

검증 축:
 (a) LineageRef 계약 — source_kind 정규화(불법값→UNKNOWN)·traced 파생·fact_status 검증·
     to_dict/lineage_from_dict 왕복.
 (b) Evidence.lineage 하위호환 — 기존 호출부(lineage 미지정)는 그대로 동작, 값 채워 넣기도 가능.
 (c) 대표 1경로(실효FAR) 끝-끝 연결 — land_adapter 가 far_basis_detail+ordinance 를 받으면
     법정범위(RULE)·조례값(STATIC_CACHE)·최종근거(CALC) 3종 Evidence 를 lineage 채운 상태로
     생성한다(정적캐시 케이스). far_basis_detail 이 없으면(기존 호출부) 조용히 생략(무회귀).
 (d) publish_gate UNTRACED soft 경고 — claim_type=FACT/CALCULATION 인데 lineage 미채움(None
     또는 traced=False)은 항상 warnings(soft, 승인등급 무관) — 채워진 경로는 경고 없음.
"""
from __future__ import annotations

import pytest

from app.services.provenance.fact_status import FactStatus
from app.services.provenance.lineage_ref import LineageRef, lineage_from_dict
from app.services.report.render import build_report_model_from_land
from app.services.report.render.model import Evidence, EvidenceBlock, ReportMeta, ReportModel, Section
from app.services.report.render.publish_gate import check_publishable

# ══════════════════════════════════════════════════════════════════════════
# (a) LineageRef 계약
# ══════════════════════════════════════════════════════════════════════════


def test_lineage_ref_default_is_unknown_and_untraced():
    ref = LineageRef()
    assert ref.source_kind == "UNKNOWN"
    assert ref.traced is False


@pytest.mark.parametrize("kind", ["SNAPSHOT", "STATIC_CACHE", "CALC", "RULE", "USER_INPUT"])
def test_lineage_ref_known_kinds_are_traced(kind):
    ref = LineageRef(source_kind=kind)
    assert ref.source_kind == kind
    assert ref.traced is True


def test_lineage_ref_unknown_kind_string_untraced():
    ref = LineageRef(source_kind="UNKNOWN")
    assert ref.traced is False


def test_lineage_ref_normalizes_illegal_source_kind_to_unknown_not_raise():
    """★UNKNOWN 은 조기거부가 아니라 정직 하강 — 점진 채택 계약(claim_type=None 과 동형)."""
    ref = LineageRef(source_kind="NOT_A_REAL_KIND")
    assert ref.source_kind == "UNKNOWN"
    assert ref.traced is False


def test_lineage_ref_case_insensitive_normalization():
    ref = LineageRef(source_kind="static_cache")
    assert ref.source_kind == "STATIC_CACHE"
    assert ref.traced is True


def test_lineage_ref_rejects_illegal_fact_status():
    with pytest.raises(ValueError):
        LineageRef(source_kind="CALC", fact_status="NOT_A_REAL_STATUS")


@pytest.mark.parametrize("status", [s.value for s in FactStatus])
def test_lineage_ref_accepts_all_valid_fact_statuses(status):
    ref = LineageRef(source_kind="CALC", fact_status=status)
    assert ref.fact_status == status


def test_lineage_ref_to_dict_round_trip():
    ref = LineageRef(
        source_kind="STATIC_CACHE", fact_status="STALE", basis="정적캐시(원문 재대조 권장)",
        snapshot_fingerprint=None,
    )
    d = ref.to_dict()
    assert d == {
        "source_kind": "STATIC_CACHE", "snapshot_fingerprint": None,
        "fact_status": "STALE", "basis": "정적캐시(원문 재대조 권장)", "traced": True,
    }
    restored = lineage_from_dict(d)
    assert restored is not None
    assert restored.source_kind == "STATIC_CACHE"
    assert restored.traced is True


def test_lineage_from_dict_non_dict_input_returns_none():
    assert lineage_from_dict(None) is None
    assert lineage_from_dict("garbage") is None  # type: ignore[arg-type]


def test_lineage_from_dict_illegal_fact_status_returns_none_not_raise():
    """역직렬화는 감사 조회 경로라 형식이 안 맞으면 예외 대신 None(날조 금지·무중단)."""
    assert lineage_from_dict({"source_kind": "CALC", "fact_status": "GARBAGE"}) is None


# ══════════════════════════════════════════════════════════════════════════
# (b) Evidence.lineage 하위호환
# ══════════════════════════════════════════════════════════════════════════


def test_evidence_without_lineage_defaults_to_none():
    ev = Evidence(value="용적률 250%")
    assert ev.lineage is None


def test_evidence_with_lineage_dict_stores_as_is():
    ref = LineageRef(source_kind="CALC", fact_status="DERIVED", basis="법정/조례 최소값")
    ev = Evidence(value="실효 용적률 200%", claim_type="CALCULATION", lineage=ref.to_dict())
    assert ev.lineage["source_kind"] == "CALC"
    assert ev.lineage["traced"] is True


def test_evidence_asdict_serialization_includes_lineage_field():
    """dataclasses.asdict 경로(JSON 우회 채널 _model_to_json 이 사용)가 lineage 를 그대로 담는다."""
    import dataclasses

    ref = LineageRef(source_kind="RULE", basis="시행령 조문")
    ev = Evidence(value="법정 용적률 200%", claim_type="FACT", lineage=ref.to_dict())
    d = dataclasses.asdict(ev)
    assert d["lineage"]["source_kind"] == "RULE"
    assert d["lineage"]["traced"] is True


# ══════════════════════════════════════════════════════════════════════════
# (c) 대표 1경로(실효FAR) 끝-끝 연결 — land_adapter
# ══════════════════════════════════════════════════════════════════════════


def _far_basis_detail(*, ordinance_confirmed: bool = True) -> dict:
    """calc_effective_far()가 실제로 반환하는 far_basis_detail 형태(실측 구조 미러)."""
    return {
        "법정범위": {"min_far_pct": 100, "max_far_pct": 250, "max_bcr_pct": 60},
        "조례값": (
            {"far_pct": 200, "bcr_pct": 60, "confirmed": True} if ordinance_confirmed else None
        ),
        "계획상한": None,
        "인센티브": None,
        "최종근거": "실효 용적률은 법정상한(250%)과 조례(200%) 중 낮은 값인 200%가 적용됩니다",
        "데이터출처": ["지자체 조례(정적캐시)"],
        "조례확인필요": not ordinance_confirmed,
    }


def _land_report_data_with_far_lineage(*, ordinance_source: str = "지자체 조례(정적캐시)") -> dict:
    return {
        "project_name": "테스트 토지분석(W2-2)",
        "parcels": [
            {
                "jibun": "용인시 1-1", "area_sqm": 500, "zone_type": "제2종일반주거지역",
                "bcr_pct": 60, "far_pct": 200, "jimok": "대", "official_price_per_sqm": 1_000_000,
                "parcel_case": "land", "status": "ok",
                "far_basis_detail": _far_basis_detail(),
                "ordinance": {
                    "source": ordinance_source,
                    "provenance": {
                        "disclaimer": "정적 캐시(2025~2026 기준) — 조례 개정 가능, "
                                      "'재분석'으로 실시간 재확인 권장.",
                    },
                },
            },
        ],
    }


def _find_far_lineage_block(model: ReportModel) -> EvidenceBlock | None:
    for sec in model.sections:
        if sec.title.startswith("4."):
            for block in sec.blocks:
                if getattr(block, "kind", None) == "evidence" and "계보" in (block.title or ""):
                    return block
    return None


def test_land_adapter_builds_far_lineage_evidence_for_static_cache_ordinance():
    model = build_report_model_from_land(_land_report_data_with_far_lineage())
    block = _find_far_lineage_block(model)
    assert block is not None, "far_basis_detail 이 있으면 계보 EvidenceBlock 이 생성돼야 한다"

    by_kind = {ev.lineage["source_kind"]: ev for ev in block.items}
    assert by_kind["RULE"].claim_type == "FACT"
    assert by_kind["RULE"].lineage["traced"] is True

    assert by_kind["STATIC_CACHE"].claim_type == "FACT"
    assert by_kind["STATIC_CACHE"].lineage["traced"] is True
    assert by_kind["STATIC_CACHE"].lineage["fact_status"] == "STALE"
    assert "재확인" in by_kind["STATIC_CACHE"].lineage["basis"]

    assert by_kind["CALC"].claim_type == "CALCULATION"
    assert by_kind["CALC"].lineage["traced"] is True
    assert by_kind["CALC"].lineage["fact_status"] == "DERIVED"


def test_land_adapter_marks_moleg_live_ordinance_as_untraced_unknown():
    """★스파이크 결론: 법제처 실시간 조회는 아직 SourceSnapshot 미연동 — 정직하게 UNKNOWN."""
    model = build_report_model_from_land(
        _land_report_data_with_far_lineage(ordinance_source="법제처API"))
    block = _find_far_lineage_block(model)
    assert block is not None
    by_kind = {ev.lineage["source_kind"]: ev for ev in block.items}
    assert by_kind["UNKNOWN"].lineage["traced"] is False


def test_land_adapter_without_far_basis_detail_omits_lineage_block_honestly():
    """기존 호출부(far_basis_detail 미제공)는 계보 블록을 생성하지 않는다(무회귀·정직 — 지어내지 않음)."""
    data = {
        "project_name": "테스트 토지분석",
        "parcels": [
            {"jibun": "용인시 1-1", "area_sqm": 500, "zone_type": "제2종일반주거지역",
             "bcr_pct": 60, "far_pct": 200, "jimok": "대", "official_price_per_sqm": 1_000_000,
             "parcel_case": "land", "status": "ok"},
        ],
    }
    model = build_report_model_from_land(data)
    assert _find_far_lineage_block(model) is None


# ══════════════════════════════════════════════════════════════════════════
# (d) publish_gate UNTRACED soft 경고
# ══════════════════════════════════════════════════════════════════════════


def _model_with_evidence(*items: Evidence, approval_state: str = "DRAFT") -> ReportModel:
    return ReportModel(
        meta=ReportMeta(title="테스트 보고서", approval_state=approval_state),
        sections=[Section(title="본문", blocks=[EvidenceBlock(items=list(items))])],
    )


@pytest.mark.parametrize("claim_type", ["FACT", "CALCULATION"])
def test_untraced_lineage_none_triggers_soft_warning(claim_type):
    model = _model_with_evidence(Evidence(value="용적률 200%", claim_type=claim_type, lineage=None))
    result = check_publishable(model)
    assert result.ok, "UNTRACED 는 항상 soft — 절대 발행을 막지 않는다"
    assert any(v.code == "UNTRACED_LINEAGE" for v in result.warnings)
    assert not any(v.code == "UNTRACED_LINEAGE" for v in result.violations)


def test_untraced_lineage_filled_traced_produces_no_warning():
    ref = LineageRef(source_kind="CALC", fact_status="DERIVED", basis="법정/조례 최소값")
    model = _model_with_evidence(
        Evidence(value="실효 용적률 200%", claim_type="CALCULATION", lineage=ref.to_dict()))
    result = check_publishable(model)
    assert result.ok
    assert not any(v.code == "UNTRACED_LINEAGE" for v in result.warnings)


def test_untraced_lineage_filled_but_unknown_kind_still_warns():
    """traced=False(source_kind=UNKNOWN)로 채워졌어도 미추적은 미추적 — 경고 대상."""
    ref = LineageRef(source_kind="UNKNOWN", basis="법제처 실시간 조회(스냅샷 미연동)")
    model = _model_with_evidence(
        Evidence(value="조례 용적률 200%", claim_type="FACT", lineage=ref.to_dict()))
    result = check_publishable(model)
    assert result.ok
    assert any(v.code == "UNTRACED_LINEAGE" for v in result.warnings)


def test_untraced_lineage_skips_evidence_without_fact_or_calculation_claim_type():
    """claim_type=ASSUMPTION/INTERPRETATION/RECOMMENDATION/None 은 UNTRACED 검사 대상이 아니다."""
    for claim_type in ("ASSUMPTION", "INTERPRETATION", "RECOMMENDATION", None):
        model = _model_with_evidence(Evidence(value="근거", claim_type=claim_type, lineage=None))
        result = check_publishable(model)
        assert not any(v.code == "UNTRACED_LINEAGE" for v in result.warnings), claim_type


def test_untraced_lineage_is_soft_even_at_expert_reviewed_approval_state():
    """★핵심: UNTRACED 는 forbidden_word/assumption 규칙과 달리 승인등급으로 hard 승격되지
    않는다(1차 — 어댑터 채택률 확보 전까지는 항상 soft, docstring 명시된 후속 과제)."""
    model = _model_with_evidence(
        Evidence(value="용적률 200%", claim_type="FACT", lineage=None),
        approval_state="EXPERT_REVIEWED",
    )
    result = check_publishable(model)
    assert result.ok, "UNTRACED 는 EXPERT_REVIEWED 에서도 hard 로 승격되면 안 된다(무회귀)"
    assert any(v.code == "UNTRACED_LINEAGE" for v in result.warnings)
    assert not any(v.code == "UNTRACED_LINEAGE" for v in result.violations)
