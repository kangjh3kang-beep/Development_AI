"""DesignBasis 정형 스키마(WP-E 세션2 · P9 Program·Constraint) 픽스처 — hard/soft·Unsat·회귀.

핵심 게이트(계획서 §4 WP-E 명기):
- ★"Hard 위반 산출 0": 임계값·지표가 있는 hard 제약 위반은 절대 통과(satisfied=True)로 새지 않는다
  (FN 방향 — '위반인데 통과' 적극 테스트).
- Unsat 사유 기계가독성: 어떤 hard 제약이 어떤 입력과 충돌했는지 구조(코드·지표·연산자·임계값·실제값)로 반환.
- soft 위반은 경고만(거부 아님) — satisfied=True 유지.
- program_items 파싱·options 하위호환·정직 미확정(threshold/지표 부재=unevaluated, 근거 없는 거부 금지).
- 세션1 리뷰 권고 4건 회귀(①docstring ②커밋후 ready ③hashtextextended ④normalize_fingerprint).

라이브 DB·엔진 없이 결정적으로 검증한다(순수 pydantic 평가 + 소스 텍스트 정적 검사).
"""
from __future__ import annotations

import inspect

import pytest

from app.services.cad import design_basis as db
from app.services.cad.design_basis import (
    ConstraintKind,
    DesignBasis,
    Operator,
    build_design_basis_from_options,
    build_program_items,
    extract_metrics_from_mass,
    should_reject,
)

# 확정 법정 한도(정본 get_legal_limits 형태 모사 — statutory_default=hard 인정 출처).
_LEGAL = {
    "max_far_percent": 250.0,
    "max_bcr_percent": 60.0,
    "max_height_m": 45.0,
    "limits_source": "statutory_default",
}


# ══════════════════════════════════════════════════════════════════════════
# 1) program_items 파싱
# ══════════════════════════════════════════════════════════════════════════

def test_program_items_from_unit_types_with_known_area():
    """unit_types → 타입별 program_item, 면적은 UNIT_TYPES 정본에서만(84A=84.0)."""
    items = build_program_items("공동주택", ["84A", "59A"], None)
    assert [i.use for i in items] == ["공동주택:84A", "공동주택:59A"]
    assert items[0].area_sqm == 84.0
    assert items[1].area_sqm == 59.0


def test_program_items_unknown_type_area_is_none_no_fabrication():
    """정본에 없는 타입 면적은 None(무날조 — 가짜 면적 생성 금지)."""
    items = build_program_items("공동주택", ["ZZZ99"], None)
    assert items[0].area_sqm is None


def test_program_items_priority_is_deterministic_descending():
    """우선순위는 목록 앞일수록 높다(결정적·설명가능)."""
    items = build_program_items("공동주택", ["84A", "59A", "39A"], None)
    assert items[0].priority > items[1].priority > items[2].priority


def test_program_items_single_when_no_unit_types():
    """unit_types 없으면 building_use 단일 항목(면적 미상 None)."""
    items = build_program_items("근린생활시설", None, None)
    assert len(items) == 1
    assert items[0].use == "근린생활시설"
    assert items[0].area_sqm is None


def test_program_counts_injected():
    """program_counts로 타입별 목표 수량을 주입할 수 있다."""
    items = build_program_items("공동주택", ["84A"], {"84A": 120})
    assert items[0].count == 120


# ══════════════════════════════════════════════════════════════════════════
# 2) hard 위반 거부(산출 0) + 구조화 Unsat 사유 — ★FN 방향(위반인데 통과) 적극 테스트
# ══════════════════════════════════════════════════════════════════════════

def test_hard_far_violation_rejected_not_passed():
    """★게이트 'Hard 위반 산출 0' — FAR 초과는 satisfied=False(절대 통과 안 됨)."""
    basis = build_design_basis_from_options(legal_limits=_LEGAL)
    ev = basis.evaluate({"far_pct": 300.0, "bcr_pct": 50.0, "num_floors": 10,
                         "building_footprint_sqm": 200.0, "building_height_m": 30.0})
    assert ev.satisfied is False
    codes = [u.constraint_code for u in ev.unsat_reasons]
    assert "legal_far_max" in codes


def test_hard_far_exactly_at_limit_passes():
    """경계값(far=한도)은 위반 아님(<= 이므로 충족) — 오탐(FP) 방지."""
    basis = build_design_basis_from_options(legal_limits=_LEGAL)
    ev = basis.evaluate({"far_pct": 250.0, "bcr_pct": 50.0, "num_floors": 10,
                         "building_footprint_sqm": 200.0, "building_height_m": 30.0})
    assert ev.satisfied is True
    assert ev.unsat_reasons == []


def test_hard_bcr_and_height_violations_all_captured():
    """건폐율·높이 동시 초과는 각각 Unsat 사유로 잡힌다(놓침 0)."""
    basis = build_design_basis_from_options(legal_limits=_LEGAL)
    ev = basis.evaluate({"far_pct": 100.0, "bcr_pct": 80.0, "num_floors": 20,
                         "building_footprint_sqm": 200.0, "building_height_m": 60.0})
    codes = {u.constraint_code for u in ev.unsat_reasons}
    assert {"legal_bcr_max", "legal_height_max"} <= codes
    assert ev.satisfied is False


def test_physical_min_floor_violation_zone_independent():
    """물리 제약(최소 1층)은 법정과 무관하게 항상 hard — num_floors=0은 거부."""
    basis = build_design_basis_from_options(legal_limits=_LEGAL)
    ev = basis.evaluate({"far_pct": 100.0, "bcr_pct": 50.0, "num_floors": 0,
                         "building_footprint_sqm": 200.0})
    assert ev.satisfied is False
    assert "physical_min_floor" in {u.constraint_code for u in ev.unsat_reasons}


def test_physical_footprint_zero_rejected():
    """물리 제약(건축면적>0) — footprint 0은 거부(0-falsy가 아니라 실제 위반 판정)."""
    basis = build_design_basis_from_options(legal_limits=_LEGAL)
    ev = basis.evaluate({"num_floors": 5, "building_footprint_sqm": 0.0})
    assert ev.satisfied is False
    assert "physical_footprint_positive" in {u.constraint_code for u in ev.unsat_reasons}


def test_no_false_negative_across_scan():
    """★FN 스윕 — 여러 위반 조합에서 satisfied가 절대 True로 새지 않는다."""
    basis = build_design_basis_from_options(legal_limits=_LEGAL)
    violating_metrics = [
        {"far_pct": 251.0, "num_floors": 5, "building_footprint_sqm": 100.0},
        {"far_pct": 100.0, "bcr_pct": 60.01, "num_floors": 5, "building_footprint_sqm": 100.0},
        {"far_pct": 100.0, "bcr_pct": 50.0, "num_floors": 5, "building_footprint_sqm": 100.0,
         "building_height_m": 45.5},
    ]
    for m in violating_metrics:
        assert basis.evaluate(m).satisfied is False, f"위반 누락(FN): {m}"


# ══════════════════════════════════════════════════════════════════════════
# 3) Unsat 사유 기계가독성
# ══════════════════════════════════════════════════════════════════════════

def test_unsat_reason_is_machine_readable():
    """Unsat 사유는 기계가독 필드(코드·지표·연산자·임계값·실제값·유발입력)를 모두 담는다."""
    basis = build_design_basis_from_options(legal_limits=_LEGAL)
    ev = basis.evaluate({"far_pct": 300.0, "num_floors": 5, "building_footprint_sqm": 100.0})
    u = next(u for u in ev.unsat_reasons if u.constraint_code == "legal_far_max")
    assert u.metric == "far_pct"
    assert u.operator == Operator.LE
    assert u.threshold == 250.0
    assert u.actual == 300.0
    assert u.threshold_source == "statutory_default"
    assert u.input_refs == {"far_pct": 300.0}
    assert u.kind == ConstraintKind.HARD
    assert isinstance(u.message, str) and u.message


def test_evaluation_serializes_to_json_dict():
    """평가 결과는 model_dump(mode='json')로 직렬화되어 응답 부착이 가능하다."""
    basis = build_design_basis_from_options(legal_limits=_LEGAL)
    payload = basis.evaluate({"far_pct": 300.0, "num_floors": 5,
                              "building_footprint_sqm": 100.0}).model_dump(mode="json")
    assert payload["satisfied"] is False
    assert isinstance(payload["unsat_reasons"], list)
    assert payload["unsat_reasons"][0]["operator"] == "<="  # StrEnum → 문자열 직렬화


# ══════════════════════════════════════════════════════════════════════════
# 4) soft 위반 경고 통과(거부 아님)
# ══════════════════════════════════════════════════════════════════════════

def test_soft_target_violation_warns_but_satisfied():
    """soft(목표) 위반은 경고만 — satisfied는 True(산출 허용)."""
    basis = build_design_basis_from_options(legal_limits=_LEGAL, target_far_percent=200.0)
    ev = basis.evaluate({"far_pct": 240.0, "bcr_pct": 50.0, "num_floors": 10,
                         "building_footprint_sqm": 200.0, "building_height_m": 30.0})
    assert ev.satisfied is True  # 법정(250)은 충족, 목표(200)만 초과
    assert "target_far" in {w.constraint_code for w in ev.soft_warnings}
    assert should_reject(ev) is False  # 거부 아님


def test_fallback_default_legal_is_soft_not_hard():
    """★정직 미확정 — 미지정 용도지역(fallback_default) 법정 한도는 hard로 확정 안 함(soft 강등)."""
    legal = {"max_far_percent": 250.0, "limits_source": "fallback_default"}
    basis = build_design_basis_from_options(legal_limits=legal)
    hard_codes = {c.code for c in basis.hard_constraints}
    soft_codes = {c.code for c in basis.soft_constraints}
    assert "legal_far_max" not in hard_codes  # 근거 미확정 → hard 아님(근거 없는 거부 금지)
    assert "legal_far_max" in soft_codes
    # 그럼에도 far 999는 soft 경고로는 잡힌다(정직 표기).
    ev = basis.evaluate({"far_pct": 999.0, "num_floors": 5, "building_footprint_sqm": 100.0})
    assert ev.satisfied is True  # 물리만 hard, far는 soft → 거부 아님
    assert "legal_far_max" in {w.constraint_code for w in ev.soft_warnings}


# ══════════════════════════════════════════════════════════════════════════
# 5) 정직 미확정(unevaluated) — 근거 없는 거부 금지
# ══════════════════════════════════════════════════════════════════════════

def test_missing_metric_is_unevaluated_not_violation():
    """대상 지표가 매스에 없으면 위반이 아니라 '평가 못 함'(정직 — 근거 없는 거부 금지)."""
    basis = build_design_basis_from_options(legal_limits=_LEGAL)
    ev = basis.evaluate({"num_floors": 5, "building_footprint_sqm": 100.0})  # far/bcr/height 없음
    assert ev.satisfied is True  # 평가 못 한 hard는 거부 근거가 되지 않는다
    assert "legal_far_max" in ev.unevaluated
    assert ev.fully_evaluated is False


def test_none_threshold_constraint_is_unevaluated():
    """임계값 None 제약은 평가 생략(unevaluated) — 위반/충족으로 단정 안 함."""
    basis = DesignBasis(hard_constraints=[db.Constraint(
        code="unknown_cap", kind=ConstraintKind.HARD, metric="far_pct",
        operator=Operator.LE, threshold=None, threshold_source="unspecified")])
    ev = basis.evaluate({"far_pct": 9999.0})
    assert ev.satisfied is True
    assert "unknown_cap" in ev.unevaluated


def test_options_backward_compat_empty_still_valid():
    """options 하위호환 — 법정·목표 미제공이면 물리 hard만 있는 유효 basis(빈 입력 무크래시)."""
    basis = build_design_basis_from_options()
    assert {c.code for c in basis.hard_constraints} == {
        "physical_min_floor", "physical_footprint_positive"}
    assert basis.soft_constraints == []
    # 정상 매스는 통과.
    assert basis.evaluate({"num_floors": 5, "building_footprint_sqm": 100.0}).satisfied is True


# ══════════════════════════════════════════════════════════════════════════
# 6) 결정성 + 헬퍼
# ══════════════════════════════════════════════════════════════════════════

def test_evaluation_deterministic_float_noise_insensitive():
    """미세 부동소수(250.0000001 vs 250.0)는 6자리 반올림으로 같은 판정(결정성)."""
    basis = build_design_basis_from_options(legal_limits=_LEGAL)
    ev = basis.evaluate({"far_pct": 250.0000001, "num_floors": 5, "building_footprint_sqm": 100.0})
    assert ev.satisfied is True  # 노이즈는 위반으로 보지 않는다


def test_extract_metrics_only_present_numeric_keys():
    """매스에서 존재·숫자변환 가능한 지표만 뽑는다(무날조 — 없는 키 생성 안 함)."""
    m = extract_metrics_from_mass({"far_pct": "250", "bcr_pct": None, "num_floors": 8, "junk": "x"})
    assert m == {"far_pct": 250.0, "num_floors": 8.0}


def test_should_reject_only_on_evaluated_hard_violation():
    """거부는 '평가된 hard 위반'에만 True — unevaluated만으로는 절대 거부 안 함."""
    basis = build_design_basis_from_options(legal_limits=_LEGAL)
    only_uneval = basis.evaluate({"num_floors": 5, "building_footprint_sqm": 100.0})
    assert should_reject(only_uneval) is False
    real_violation = basis.evaluate({"far_pct": 999.0, "num_floors": 5, "building_footprint_sqm": 100.0})
    assert should_reject(real_violation) is True


# ══════════════════════════════════════════════════════════════════════════
# 7) 세션1 리뷰 권고 4건 회귀
# ══════════════════════════════════════════════════════════════════════════

def test_rec1_geometry_hash_docstring_warns_surface_hashes_for_render_dedup():
    """권고① — compute_anchor_geometry_hash docstring이 'geometry_hash≠enriched 정체·렌더 dedup은
    surface_hashes' 를 명시한다."""
    from app.services.cad import design_run_store as store

    doc = store.compute_anchor_geometry_hash.__doc__ or ""
    assert "surface_hashes" in doc
    assert "렌더" in doc and "dedup" in doc


def test_rec2_schema_ready_set_after_commit_both_files():
    """권고② — 두 파일(_ensure_schema)이 'await db.commit()' 후에 _SCHEMA_READY=True를 세팅한다."""
    from app.services.basis import site_basis_service as sbsvc
    from app.services.cad import design_run_store as store

    for mod_fn in (store._ensure_schema, sbsvc._ensure_schema):
        src = inspect.getsource(mod_fn)
        assert "await db.commit()" in src
        assert src.index("await db.commit()") < src.index("_SCHEMA_READY = True")


def test_rec3_advisory_lock_uses_hashtextextended_64bit():
    """권고③ — save_drawing advisory lock에 hashtextextended(64bit) 신키가 존재한다.

    ★분리 리뷰 MEDIUM(전환기 레이스 봉합) 반영: 신키 단독 전환이 아니라, 배포 전환창(블루그린
    신·구 파드 혼재) 동안은 구키(hashtext 32bit)도 **고정 순서(구키 먼저)**로 함께 획득해야
    상호배제가 깨지지 않는다 — 그래서 이제는 hashtext(::bigint)가 '제거'가 아니라 '선행 유지'다
    (차기 릴리스에서 전 파드 신키 롤아웃 완료 후 제거 예정). 실행 순서는
    test_dual_advisory_lock_old_key_before_new_key_both_before_max_version이 fake DB로 고정 검증.
    """
    from app.routers import design_v61

    src = inspect.getsource(design_v61.save_drawing)
    assert "hashtextextended(:lk, 0)" in src  # 신키(64bit) 존재
    assert "hashtext(:lk)::bigint" in src  # 구키(32bit) 과도기 유지(전환창 상호배제 방어)
    # 소스 텍스트 순서로도 구키 선언이 신키보다 먼저 나온다(가독성상 실행 순서와 일치 — 이중 방어).
    assert src.index("hashtext(:lk)::bigint") < src.index("hashtextextended(:lk, 0)")


def test_rec4_geometry_hash_int_float_insensitive():
    """권고④ — compute_anchor_geometry_hash 입력에 normalize_fingerprint 적용(int/float 불변)."""
    from app.services.cad import design_run_store as store

    a_float = {"building_width_m": 30.0, "building_depth_m": 12.0, "num_floors": 8, "floor_height_m": 3.0}
    a_int = {"building_width_m": 30, "building_depth_m": 12, "num_floors": 8, "floor_height_m": 3}
    assert store.compute_anchor_geometry_hash(a_float) == store.compute_anchor_geometry_hash(a_int)
    assert "normalize_fingerprint" in inspect.getsource(store.compute_anchor_geometry_hash)


# ══════════════════════════════════════════════════════════════════════════
# 8) ★HIGH 회귀 — Hard escape 봉합(제1종전용주거 높이10m 한도 재현·분리 리뷰 반영)
# ══════════════════════════════════════════════════════════════════════════
# 재현: building_height_m 키가 매스에 없으면(예: 명시치수 분기는 파생 전에 이 키가 없었다)
# legal_height_max가 unevaluated로 새어 satisfied=True 무음 통과했다. extract_metrics_from_mass가
# num_floors×floor_height_m/building_width_m×building_depth_m으로 파생해야 이 구멍이 막힌다.

def test_extract_metrics_derives_height_from_floors_and_floor_height():
    """★HIGH — building_height_m 부재 + num_floors·floor_height_m 존재 → 곱으로 파생."""
    m = extract_metrics_from_mass({"num_floors": 60, "floor_height_m": 3.0})
    assert m["building_height_m"] == 180.0


def test_extract_metrics_derives_footprint_from_width_and_depth():
    """★HIGH — building_footprint_sqm 부재 + width·depth 존재 → 곱으로 파생."""
    m = extract_metrics_from_mass({"building_width_m": 100.0, "building_depth_m": 100.0})
    assert m["building_footprint_sqm"] == 10000.0


def test_extract_metrics_does_not_override_explicit_height_or_footprint():
    """명시적으로 존재하는 값은 파생으로 덮어쓰지 않는다(원본 우선)."""
    m = extract_metrics_from_mass({
        "building_height_m": 33.3, "num_floors": 60, "floor_height_m": 3.0,
        "building_footprint_sqm": 55.5, "building_width_m": 100.0, "building_depth_m": 100.0,
    })
    assert m["building_height_m"] == 33.3
    assert m["building_footprint_sqm"] == 55.5


def test_extract_metrics_does_not_fabricate_far_bcr_without_land_area():
    """★무날조 — far_pct·bcr_pct는 대지면적이 이 dict 범위 밖이라 파생하지 않는다(정직 미확정 유지)."""
    m = extract_metrics_from_mass({"num_floors": 60, "floor_height_m": 3.0})
    assert "far_pct" not in m
    assert "bcr_pct" not in m


def test_hard_escape_height_violation_caught_via_derivation():
    """★분리 리뷰 재현 케이스(정형 평가 레벨) — 제1종전용주거 높이10m 한도 + 60층×3m(=180m)는
    building_height_m 키가 없어도 파생을 통해 legal_height_max 위반으로 잡혀야 한다(거부 방향)."""
    legal = {"max_height_m": 10.0, "limits_source": "statutory_default"}
    basis = build_design_basis_from_options(legal_limits=legal)
    metrics = extract_metrics_from_mass({"num_floors": 60, "floor_height_m": 3.0,
                                         "building_width_m": 100.0, "building_depth_m": 100.0})
    ev = basis.evaluate(metrics)
    assert ev.satisfied is False
    assert "legal_height_max" in {u.constraint_code for u in ev.unsat_reasons}
    height_unsat = next(u for u in ev.unsat_reasons if u.constraint_code == "legal_height_max")
    assert height_unsat.actual == 180.0
    assert height_unsat.threshold == 10.0


@pytest.mark.asyncio
async def test_wiring_enforce_rejects_height_escape_explicit_dims(monkeypatch):
    """★분리 리뷰 정확 재현(배선 전 구간·E2E) — 제1종전용주거지역 + 100×100×60층 명시치수
    요청은 ENFORCE 시 generate_bim_model이 422로 거부하고 legal_height_max를 unsat으로 반환한다
    (수정 전에는 building_height_m 키 부재로 satisfied=True 무음 통과했다)."""
    from fastapi import HTTPException

    from app.core.config import settings
    from app.routers.design_v61 import BimGenerateRequest, generate_bim_model

    monkeypatch.setattr(settings, "DESIGN_BASIS_ENFORCE", True, raising=False)
    req = BimGenerateRequest(
        building_width_m=100, building_depth_m=100, floor_count=60,
        zone_code="제1종전용주거지역", building_use="단독주택",
    )
    with pytest.raises(HTTPException) as exc:
        await generate_bim_model("wpe2-height-escape", req)
    assert exc.value.status_code == 422
    codes = [u["constraint_code"] for u in exc.value.detail["unsat_reasons"]]
    assert "legal_height_max" in codes


@pytest.mark.asyncio
async def test_wiring_shadow_mode_does_not_reject_height_escape(monkeypatch):
    """기본 shadow(DESIGN_BASIS_ENFORCE=False)에서는 동일 위반 패턴도 거부되지 않는다(무회귀).

    ★테스트 성능: shadow 경로는 reject로 조기 반환하지 않고 build_ifc_from_mass까지 완주하므로
    치수를 소형(4층·12×9)으로 줄인다 — 60층·100×100(13만 엔티티) IFC 생성은 실측 ~1분45초로
    테스트 스위트에 부적합. 4층·12×9(=height 12m)도 10m 한도를 여전히 위반해 동일 escape
    패턴을 검증한다(엔진 실행시간만 절약 — 위반 여부·파생 로직은 치수와 무관).
    ★응답 스키마는 design_basis/basis_evaluation을 아직 외부 echo하지 않으므로(이번 세션 스코프
    밖), 위반이 '내부적으로' 잡혔는지는 _resolve_mass를 직접 호출해 검증하고, generate_bim_model
    호출은 '거부하지 않는다(예외 0)'만 확인한다 — 두 축을 분리해 각각 정확히 검증."""
    from app.core.config import settings
    from app.routers.design_v61 import BimGenerateRequest, _resolve_mass, generate_bim_model

    req = BimGenerateRequest(
        building_width_m=12, building_depth_m=9, floor_count=4,
        zone_code="제1종전용주거지역", building_use="단독주택",
    )
    # 내부 위반 감지 확인(빠름 — IFC 생성 없이 매스만 산출).
    mass = _resolve_mass(req)
    assert mass["basis_evaluation"]["satisfied"] is False
    assert "legal_height_max" in {u["constraint_code"] for u in mass["basis_evaluation"]["unsat_reasons"]}

    monkeypatch.setattr(settings, "DESIGN_BASIS_ENFORCE", False, raising=False)
    result = await generate_bim_model("wpe2-height-escape-shadow", req)
    assert isinstance(result, dict)  # 정상 응답(거부 없음) — 기존 동작 100% 보존


# ══════════════════════════════════════════════════════════════════════════
# 9) 소비 배선(design_v61) — 부착·enforce 결정
# ══════════════════════════════════════════════════════════════════════════

def test_wiring_attach_design_basis_adds_machine_readable_evaluation():
    """_attach_design_basis가 매스에 design_basis·basis_evaluation을 additive 부착(예외격리·무회귀)."""
    from app.routers.design_v61 import BimGenerateRequest, _attach_design_basis

    # num_floors=0 물리 위반(법정 무관 hard) — 부착·판정이 기계가독으로 남는지 확인.
    mass: dict[str, object] = {"num_floors": 0, "building_footprint_sqm": 0.0, "far_pct": 100.0}
    req = BimGenerateRequest(building_use="공동주택", zone_code="2R")
    _attach_design_basis(mass, req)
    assert "design_basis" in mass and "basis_evaluation" in mass
    ev: dict = mass["basis_evaluation"]  # type: ignore[assignment]
    assert ev["satisfied"] is False  # 물리 위반은 산출 0 방향으로 잡힌다
    assert any(u["constraint_code"] == "physical_min_floor" for u in ev["unsat_reasons"])


def test_wiring_enforce_flag_default_false_no_regression(monkeypatch):
    """DESIGN_BASIS_ENFORCE 기본 False(그림자·무회귀) — enforce 판정 헬퍼가 그를 반영한다."""
    from app.routers import design_v61

    assert design_v61._design_basis_enforce_enabled() is False
    from app.core.config import settings

    monkeypatch.setattr(settings, "DESIGN_BASIS_ENFORCE", True, raising=False)
    assert design_v61._design_basis_enforce_enabled() is True
