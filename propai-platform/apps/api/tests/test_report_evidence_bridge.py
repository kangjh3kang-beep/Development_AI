"""evidence_bridge + 어댑터 EvidenceBlock 배선 테스트(evidence dead-path 해소 검증).

검증 축:
(1) 브리지 단위 — 표준 계약(evidence[]/legal_refs[]) → Evidence 매핑, ★verified URL 만 통과,
    pending 은 링크 없이 법령명 텍스트만(날조 금지), 실데이터 없으면 None(빈 블록 금지).
(2) 어댑터 통합 — appraisal/persona/pipeline/design_audit 도메인 결과에 계약 데이터가 실제
    있을 때만 EvidenceBlock 이 정본 모델에 들어가고, 없으면 섹션 자체가 생략된다(정직).
"""

from __future__ import annotations

from app.services.report.render.evidence_bridge import evidence_block_from_contract
from app.services.report.render.model import EvidenceBlock

# 레지스트리 레코드 표본(get_legal_refs 출력 형태 그대로 — verified / pending 각 1건)
_REF_VERIFIED = {
    "key": "far_limit",
    "law_name": "국토의 계획 및 이용에 관한 법률 시행령",
    "article": "제85조",
    "title": "용도지역 안에서의 용적률",
    "url": "https://law.go.kr/법령/국토의계획및이용에관한법률시행령",
    "url_status": "verified",
}
_REF_PENDING = {
    "key": "ordinance_far",
    "law_name": "용인시 도시계획 조례",
    "article": "",
    "title": "용적률(지자체별)",
    "url": "",
    "url_status": "pending",
}


# ── (1) 브리지 단위 ──────────────────────────────────────────────────


def test_bridge_maps_full_contract_with_verified_link_only():
    """풀 계약 → Evidence 매핑: 라벨+값 합성·basis 통과·verified URL 만 legal_link."""
    block = evidence_block_from_contract({
        "evidence": [
            {"label": "법정 용적률 상한", "value": "250%",
             "basis": "제2종일반주거지역 · 국토계획법 시행령 제85조", "legal_ref_key": "far_limit"},
            {"label": "조례 적용 용적률", "value": "200%",
             "basis": "용인시 도시계획 조례(실효값)", "legal_ref_key": "ordinance_far"},
        ],
        "legal_refs": [_REF_VERIFIED, _REF_PENDING],
    })
    assert isinstance(block, EvidenceBlock)
    assert len(block.items) == 2  # 레코드 2건 모두 evidence 항목에 소비 → 별도 법령행 없음
    first, second = block.items
    assert first.value == "법정 용적률 상한: 250%"
    assert first.basis == "제2종일반주거지역 · 국토계획법 시행령 제85조"
    assert first.legal_link == _REF_VERIFIED["url"]  # verified → 그대로 통과
    # pending 레코드는 링크 없이 법령명 텍스트만(source 폴백) — URL 날조 금지
    assert second.legal_link is None
    assert second.source == "용인시 도시계획 조례"


def test_bridge_confidence_passthrough_no_estimation():
    """confidence 는 계약 값 그대로 — 없으면 None(기본값 주입 금지)."""
    block = evidence_block_from_contract({
        "evidence": [
            {"label": "교차검증 신뢰도", "value": 0.82, "confidence": "high"},
            {"label": "채택 단가", "value": "1,234,000원/㎡"},
        ],
    })
    assert block is not None
    assert block.items[0].confidence == "high"
    assert block.items[1].confidence is None
    # 비문자열 value 는 fmt_value 규칙으로 문자열화(0.82 → '0.8')
    assert block.items[0].value.startswith("교차검증 신뢰도: ")


def test_bridge_standalone_legal_refs_array():
    """단독 legal_refs 배열 → 법령 1행씩(verified 만 링크). 중복 키는 1회만."""
    block = evidence_block_from_contract([_REF_VERIFIED, dict(_REF_VERIFIED), _REF_PENDING])
    assert block is not None
    assert len(block.items) == 2  # far_limit 중복 제거
    by_value = {it.value: it for it in block.items}
    v = by_value["국토의 계획 및 이용에 관한 법률 시행령 제85조"]
    assert v.legal_link == _REF_VERIFIED["url"]
    p = by_value["용인시 도시계획 조례"]
    assert p.legal_link is None  # pending → 텍스트만


def test_bridge_resolves_keys_via_standard_builder():
    """legal_ref_keys 는 표준 빌더(evidence_contract.build_legal_refs)로 해석(재구현 0)."""
    block = evidence_block_from_contract({"legal_ref_keys": ["far_limit"]})
    assert block is not None and len(block.items) == 1
    item = block.items[0]
    assert "제85조" in item.value
    # URL 은 레지스트리 출력만 — 있으면 https(신뢰호스트), 없으면 None(조립 금지)
    assert item.legal_link is None or item.legal_link.startswith("https://")


def test_bridge_returns_none_when_no_real_data():
    """실데이터 부재(빈/None/라벨 없는 항목만) → None(빈 블록·가짜값 금지)."""
    assert evidence_block_from_contract(None) is None
    assert evidence_block_from_contract({}) is None
    assert evidence_block_from_contract({"evidence": [], "legal_refs": []}) is None
    assert evidence_block_from_contract({"evidence": [{"value": "라벨 없음"}]}) is None
    assert evidence_block_from_contract("문자열") is None


# ── (2) 어댑터 통합 ──────────────────────────────────────────────────


def _evidence_sections(model):
    """모델 안에서 EvidenceBlock 을 포함한 (섹션, 블록) 목록을 걷어온다."""
    found = []
    for sec in model.sections:
        for blk in sec.blocks:
            if isinstance(blk, EvidenceBlock):
                found.append((sec, blk))
    return found


def test_appraisal_adapter_attaches_evidence_block():
    """탁상감정 result['evidence'](표준 풀 계약) → '7. 산출 근거·법령 링크' 섹션 부착."""
    from app.services.report.render import build_report_model_from_appraisal, render_report

    result = {
        "appraised_price_per_sqm": 1_200_000,
        "appraised_total_won": 600_000_000,
        "area_sqm": 500,
        "confidence": 0.8,
        "range_per_sqm": {"low": 1_100_000, "high": 1_300_000},
        "methods": [{"method": "공시지가기준법", "unit_price": 1_200_000, "rationale": "공시지가×보정"}],
        "evidence": {
            "evidence": [
                {"label": "채택 단가", "value": "1,200,000원/㎡", "basis": "공시지가기준법 가중"},
            ],
            "legal_refs": [_REF_VERIFIED],
            "provenance": [],
            "trust": None,
        },
    }
    model = build_report_model_from_appraisal(result, address="용인시 처인구 123")
    hits = _evidence_sections(model)
    assert len(hits) == 1
    sec, blk = hits[0]
    assert sec.title == "7. 산출 근거·법령 링크"
    assert any(it.value == "채택 단가: 1,200,000원/㎡" for it in blk.items)
    assert any(it.legal_link == _REF_VERIFIED["url"] for it in blk.items)
    # 실제 렌더까지 통과(dead-path 재발 방지 — 모델에만 있고 렌더에서 깨지면 무의미)
    data, _mime, ext = render_report(model, "pdf")
    assert ext == "pdf" and data[:4] == b"%PDF"


def test_appraisal_adapter_omits_section_without_contract():
    """계약 데이터 없는 탁상감정 결과 → 근거 섹션 자체 생략(빈 블록 금지)."""
    from app.services.report.render import build_report_model_from_appraisal

    model = build_report_model_from_appraisal(
        {"appraised_price_per_sqm": 1_000_000, "methods": []}, address="")
    assert _evidence_sections(model) == []
    assert all("산출 근거" not in s.title for s in model.sections)


def test_persona_adapter_attaches_evidence_block():
    """페르소나 verification.evidence_block(표준 풀 계약) → '산출 근거·법령 링크' 섹션."""
    from app.services.report.render import build_report_model_from_persona

    report = {
        "persona_key": "urban_planner",
        "address": "용인시 처인구 123",
        "status": "ok",
        "artifacts": {"zone_limits": {"far": {"legal": 250}, "bcr": {"legal": 60}}},
        "verification": {
            "evidence_block": {
                "evidence": [
                    {"label": "법정 용적률 상한", "value": "250%",
                     "basis": "용도지역 국가 법정상한(국토계획법 시행령)", "legal_ref_key": "far_limit"},
                ],
                "legal_refs": [_REF_VERIFIED],
                "provenance": [],
                "trust": None,
            },
        },
    }
    model = build_report_model_from_persona(report, "urban_planner")
    hits = _evidence_sections(model)
    assert len(hits) == 1
    sec, blk = hits[0]
    assert sec.title == "산출 근거·법령 링크"
    assert blk.items[0].value == "법정 용적률 상한: 250%"
    assert blk.items[0].legal_link == _REF_VERIFIED["url"]


def test_persona_adapter_omits_without_contract():
    """evidence_block 미부착 페르소나 결과 → 근거 섹션 생략(정직)."""
    from app.services.report.render import build_report_model_from_persona

    model = build_report_model_from_persona(
        {"persona_key": "constructor", "artifacts": {}, "verification": {}}, "constructor")
    assert _evidence_sections(model) == []


def test_pipeline_adapter_attaches_site_evidence():
    """stages.site_analysis.data 의 evidence[]/legal_refs[] → 입지분석(섹션2)에 부착."""
    from app.services.report.render import build_report_model_from_pipeline

    pipeline_result = {
        "address": "용인시 처인구 123",
        "stages": {
            "site_analysis": {
                "stage": "site_analysis",
                "data": {
                    "zone_type": "제2종일반주거지역",
                    "max_far": 250,
                    "evidence": [
                        {"label": "법정 용적률 상한", "value": "250%",
                         "basis": "제2종일반주거지역 · 국토계획법 시행령 제85조",
                         "legal_ref_key": "far_limit"},
                    ],
                    "legal_refs": [_REF_VERIFIED],
                },
            },
        },
    }
    model = build_report_model_from_pipeline(pipeline_result)
    hits = _evidence_sections(model)
    assert len(hits) == 1
    sec, blk = hits[0]
    assert sec.section_no == 2  # 입지 분석 섹션
    assert blk.title == "산출 근거·법령 링크"
    assert blk.items[0].legal_link == _REF_VERIFIED["url"]


def test_pipeline_adapter_omits_for_assumed_defaults():
    """가정값 부지(evidence/legal_refs 빈 배열) → 근거 섹션 미부착(가짜 부지에 법령링크 금지)."""
    from app.services.report.render import build_report_model_from_pipeline

    model = build_report_model_from_pipeline({
        "address": "",
        "stages": {"site_analysis": {"stage": "site_analysis",
                                     "data": {"evidence": [], "legal_refs": []}}},
    })
    assert _evidence_sections(model) == []


def test_design_audit_adapter_attaches_cited_legal_refs():
    """finding 이 실제 들고 있는 레지스트리 레코드 → 'S8. 인용 법령 근거·링크' 섹션."""
    from app.services.report.render import build_report_model_from_design_audit

    audit = {
        "id": "a1",
        "overall": {"grade": "normal"},
        "findings": [
            {"check_id": "LAW-FAR", "engine": "rules", "status": "warn",
             "legal_refs": [_REF_VERIFIED]},
            {"check_id": "LAW-ORD", "engine": "rules", "status": "info",
             "legal_refs": [_REF_PENDING]},
        ],
    }
    model = build_report_model_from_design_audit(audit)
    hits = _evidence_sections(model)
    assert len(hits) == 1
    sec, blk = hits[0]
    assert sec.title == "S8. 인용 법령 근거·링크"
    links = {it.value: it.legal_link for it in blk.items}
    assert links["국토의 계획 및 이용에 관한 법률 시행령 제85조"] == _REF_VERIFIED["url"]
    assert links["용인시 도시계획 조례"] is None  # pending → 텍스트만(링크 날조 금지)


def test_design_audit_adapter_omits_without_refs():
    """법령 근거 없는 심사 → S8 섹션 생략(정직)."""
    from app.services.report.render import build_report_model_from_design_audit

    model = build_report_model_from_design_audit({
        "id": "a2", "overall": {}, "findings": [
            {"check_id": "ENG-01", "engine": "rules", "status": "pass"},
        ],
    })
    assert _evidence_sections(model) == []


def test_land_adapter_attaches_only_when_contract_present():
    """토지보고서 — data 에 표준 계약이 있을 때만 부착, 없으면 생략(현 생산자는 미전달)."""
    from app.services.report.render import build_report_model_from_land

    base = {"project_name": "테스트", "parcels": [
        {"jibun": "123-1", "area_sqm": 500, "zone_type": "제2종일반주거지역",
         "bcr_pct": 60, "far_pct": 200, "parcel_case": "land", "status": "ok"},
    ]}
    # 계약 없음(현재 /land-report 생산자 상태) → 근거 섹션 생략
    assert _evidence_sections(build_report_model_from_land(dict(base))) == []
    # 계약 존재 → 종합의견 다음 번호로 부착
    with_contract = dict(base)
    with_contract["legal_refs"] = [_REF_VERIFIED]
    model = build_report_model_from_land(with_contract)
    hits = _evidence_sections(model)
    assert len(hits) == 1
    assert hits[0][0].title == "6. 산출 근거·법령 링크"  # 집합건물 없음 → 종합의견 5 → 근거 6
    assert hits[0][1].items[0].legal_link == _REF_VERIFIED["url"]
