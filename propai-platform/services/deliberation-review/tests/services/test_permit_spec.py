"""INC-PD1 — 프로세스 스펙 계약·로더: 기본 스펙 로드·버전·applicability."""
from app.services.permit.spec_loader import applicable_stages, load_default_spec


def test_default_spec_loads_with_version_and_stages():
    spec = load_default_spec()
    assert spec.spec_id and spec.version              # 버전드(재현)
    assert any(s.stage_type == "본허가" for s in spec.stages)   # 건축허가 단계 존재
    # 각 단계 criteria_ref는 SSOT 참조(법정 수치 직접 보유 금지) — 한도 리터럴 없음
    for s in spec.stages:
        for c in s.criteria_refs:
            assert c.kind.value in ("QUANTITATIVE", "QUALITATIVE")
            if c.kind.value == "QUANTITATIVE":
                assert c.ssot_ref  # 한도는 SSOT에서 해석


def test_applicability_filters_by_dev_and_zone():
    spec = load_default_spec()
    # 경관심의는 일정 조건에서만 — applicability로 on/off(데이터 구동)
    base = applicable_stages(spec, dev_type="M06", use_zone="제2종일반주거지역")
    assert {s.stage_id for s in base} <= {s.stage_id for s in spec.stages}
    assert base, "최소 건축허가 단계는 항상 적용"
    # predecessors 위상정렬 — 의존 단계가 앞에
    order = [s.stage_id for s in base]
    for s in base:
        for p in s.predecessors:
            if p in order:
                assert order.index(p) < order.index(s.stage_id)
