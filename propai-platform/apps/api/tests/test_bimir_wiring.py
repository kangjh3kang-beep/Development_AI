"""BimIR 실소비 배선 테스트 (WP-D 세션3 · P11) — 라우터 배선·폴백·provenance 일치·거부/스코프.

검증 축(세션3 게이트):
- provenance 일치(★이중 해시 발산 방지): BimIR design_input_hash == provenance compute_input_hash(mass),
  run_id == make_run_id(design_input_hash) — 두 해시 체계가 한 값으로 수렴.
- glb 배선(공용 헬퍼): glb_from_mass_with_bimir가 BimIR 경유로 glb를 내고, 실패 시 직접 경로로
  폴백한다(bimir_path 표기). 두 경로 glb는 구조 동등.
- 메타 additive: bimir_meta_from_mass·_bimir_meta_headers가 결정적·ASCII 안전 메타를 만든다.
- 거부/스코프(item4 판단 근거): cad_design_spec·design_ingest 기원 IR은 매스 기하가 없어
  IFC/glb/QTO 산출을 '명시 거부'하는 것이 정답임을 계약으로 고정(무음 퇴화·환각 차단).
"""

from __future__ import annotations

import pytest

from app.services.bim.bimir_adapters import (
    bimir_from_cad_design_spec,
    bimir_from_ingest_design_spec,
    bimir_from_mass,
    mass_from_bimir,
)
from app.services.bim.ifc_to_gltf_service import (
    _bimir_meta,
    bimir_meta_from_mass,
    bimir_meta_to_headers,
    glb_from_mass_with_bimir,
)
from app.services.cad.design_spec import DesignSpec as CadDesignSpec
from app.services.cad.provenance import compute_input_hash, make_run_id
from app.services.design_ingest.design_spec import DesignSpec as IngestDesignSpec


# ── 픽스처 ──
def _mass() -> dict:
    return {
        "building_width_m": 40.0,
        "building_depth_m": 20.0,
        "num_floors": 7,
        "floor_height_m": 3.0,
        "core_positions": [{"x": 20.0, "y": 10.0}],
        "core_size_m": 5.0,
        "corridor_width_m": 0.0,
        "windows_per_side": 0,
        "unit_width_m": 0.0,
        "unit_doors": False,
    }


def _cad_model():
    return bimir_from_cad_design_spec(
        CadDesignSpec(site_area_sqm=1000.0, zone_code="2R", building_use="공동주택", num_floors=5)
    )


def _ingest_model():
    return bimir_from_ingest_design_spec(
        IngestDesignSpec(source_format="dxf", drawing_type="평면도", title="테스트도면")
    )


def _real_ifcopenshell() -> bool:
    try:
        import ifcopenshell

        return hasattr(ifcopenshell, "file")
    except Exception:
        return False


def _has_pygltflib() -> bool:
    try:
        import pygltflib  # noqa: F401

        return True
    except Exception:
        return False


_glb_gate = pytest.mark.skipif(
    not (_real_ifcopenshell() and _has_pygltflib()), reason="ifcopenshell/pygltflib 미설치 — glb skip"
)


def _glb_signature(glb_bytes: bytes) -> dict:
    """glb → {그룹명: (정점수, 인덱스수)} 구조 서명(GlobalId 무관·기하 구조만)."""
    import pygltflib

    g = pygltflib.GLTF2.load_from_bytes(glb_bytes)
    sig: dict[str, tuple[int, int]] = {}
    for prim in g.meshes[0].primitives:
        name = g.materials[prim.material].name
        pos = g.accessors[prim.attributes.POSITION]
        idx = g.accessors[prim.indices]
        sig[name] = (pos.count, idx.count)
    return sig


# ═══════════════════════════ provenance 일치(★이중 해시 발산 방지) ═══════════════════════════
def test_provenance_input_hash_parity():
    # BimIR design_input_hash는 어댑터 내부에서 compute_input_hash(mass)로 파생 → 동일 값.
    mass = _mass()
    model = bimir_from_mass(mass)
    assert model.design_input_hash == compute_input_hash(mass)


def test_provenance_input_hash_parity_multiple_masses():
    # 여러 매스에서 일관 — 이중 해시 발산이 어떤 입력에서도 없음.
    for m in (
        {"building_width_m": 10.0, "building_depth_m": 10.0, "num_floors": 3, "floor_height_m": 3.0},
        {"building_width_m": 25.5, "building_depth_m": 12.0, "num_floors": 15, "floor_height_m": 2.8},
        {"building_width_m": 40.0, "building_depth_m": 20.0, "num_floors": 7, "floor_height_m": 3.0,
         "core_positions": [{"x": 20.0, "y": 10.0}], "core_size_m": 5.0},
    ):
        assert bimir_from_mass(m).design_input_hash == compute_input_hash(m)


def test_provenance_run_id_matches_make_run_id():
    mass = _mass()
    meta = bimir_meta_from_mass(mass)
    assert meta["run_id"] == make_run_id(compute_input_hash(mass))
    assert meta["run_id"].startswith("c2r_")
    assert meta["design_input_hash"] == compute_input_hash(mass)


def test_bimir_meta_deterministic_3x():
    # 같은 매스면 메타가 3회 바이트까지 동일(결정성).
    mass = _mass()
    metas = [bimir_meta_from_mass(mass) for _ in range(3)]
    assert metas[0] == metas[1] == metas[2]


def test_bimir_meta_ignores_transient_bookkeeping_keys():
    # ★결정성 봉합: '_' 접두 전이 부기 키(_cache_hit 등)는 정체 해시에 영향 없음.
    #   _resolve_mass가 캐시 미스=False·히트=True로 붙이는 _cache_hit가 해시를 갈라놓던 결함 고정.
    base = _mass()
    meta_clean = bimir_meta_from_mass(base)
    meta_miss = bimir_meta_from_mass({**base, "_cache_hit": False})
    meta_hit = bimir_meta_from_mass({**base, "_cache_hit": True, "_internal": "x"})
    assert meta_clean == meta_miss == meta_hit


def test_mass_for_ir_strips_underscore_keys_only():
    from app.services.bim.ifc_to_gltf_service import _mass_for_ir

    src = {"building_width_m": 40.0, "_cache_hit": True, "compliance": {"ok": 1}, "_x": 9}
    out = _mass_for_ir(src)
    assert out == {"building_width_m": 40.0, "compliance": {"ok": 1}}
    assert "_cache_hit" not in out and "_x" not in out
    assert src == {"building_width_m": 40.0, "_cache_hit": True, "compliance": {"ok": 1}, "_x": 9}  # 원본 불변


def test_bimir_meta_shape_and_element_count():
    mass = _mass()
    model = bimir_from_mass(mass)
    meta = _bimir_meta(model)
    assert set(meta.keys()) == {"bimir_version", "element_count", "design_input_hash", "run_id"}
    assert meta["bimir_version"] == model.ir_version
    assert meta["element_count"] == len(model.elements)
    assert meta["element_count"] > 0  # 매스는 최소 BUILDING+파생요소 다수


# ═══════════════════════════ 메타 → 응답 헤더(additive·ASCII 안전) ═══════════════════════════
def test_meta_headers_bimir_path():
    meta = {
        "bimir_version": "propai.bimir/1.0", "element_count": 42,
        "design_input_hash": "deadbeef" * 8, "run_id": "c2r_deadbeefdeadbeef",
        "bimir_path": True,
    }
    h = bimir_meta_to_headers(meta)
    assert h["X-BIMIR-Path"] == "bimir"
    assert h["X-BIMIR-Version"] == "propai.bimir/1.0"
    assert h["X-BIMIR-Element-Count"] == "42"
    assert h["X-BIMIR-Input-Hash"] == "deadbeef" * 8
    assert h["X-BIMIR-Run-Id"] == "c2r_deadbeefdeadbeef"
    # 모든 값 latin-1(HTTP 헤더) 안전.
    for v in h.values():
        v.encode("latin-1")


def test_meta_headers_fallback_path_omits_identity():
    # 폴백 메타는 정체 없음 → 경로 표기만(무날조 — 없는 해시 미생성).
    h = bimir_meta_to_headers({"bimir_path": False})
    assert h == {"X-BIMIR-Path": "fallback"}


# ═══════════════════════════ cost QTO 배선(라우터 스니펫 계약) ═══════════════════════════
def test_cost_qto_bimir_branch_numerically_identical_to_direct():
    # cost.py 라우터의 'bim' 분기(BimIR 경유)가 직접 경로와 항목·물량·금액까지 동일함을 고정.
    #   라우터가 W/Dd/nf/Hh를 그대로 BimIR 매스로 감싸므로 수치 계약 불변(세션2 게이트 재확인).
    from app.services.cost.geometry_qto import geometry_takeoff, geometry_takeoff_from_bimir

    W, Dd, nf, Hh, fb, st = 40.0, 20.0, 7, 3.0, 2, "SRC"
    direct = geometry_takeoff(
        width_m=W, depth_m=Dd, floors_above=nf, floors_below=fb,
        floor_height_m=Hh, structure_type=st,
    )
    via_bimir = geometry_takeoff_from_bimir(
        bimir_from_mass({
            "building_width_m": W, "building_depth_m": Dd,
            "num_floors": nf, "floor_height_m": Hh,
        }),
        floors_below=fb, structure_type=st,
    )
    assert via_bimir == direct  # 전체 dict 바이트 동일(항목·요약 전부)


# ═══════════════════════════ glb 배선(공용 헬퍼)·폴백 ═══════════════════════════
@_glb_gate
def test_glb_from_mass_with_bimir_success_meta_and_bytes():
    mass = _mass()
    glb, meta = glb_from_mass_with_bimir(mass, project_name="EQ")
    assert meta["bimir_path"] is True
    assert meta["design_input_hash"] == compute_input_hash(mass)
    assert meta["element_count"] == len(bimir_from_mass(mass).elements)
    # 유효한 glb(파싱 성공·mesh 존재).
    import pygltflib

    g = pygltflib.GLTF2.load_from_bytes(glb)
    assert len(g.meshes) >= 1


@_glb_gate
def test_glb_from_mass_with_bimir_structural_equivalence():
    from app.services.bim.ifc_generator_service import build_ifc_from_mass
    from app.services.bim.ifc_to_gltf_service import ifc_bytes_to_glb

    mass = _mass()
    glb_helper, _ = glb_from_mass_with_bimir(mass, project_name="EQ")
    glb_direct = ifc_bytes_to_glb(build_ifc_from_mass(mass, project_name="EQ"))
    # 헬퍼(BimIR 경유) glb == 직접 경로 glb 구조 동등(그룹·정점수·인덱스수).
    assert _glb_signature(glb_helper) == _glb_signature(glb_direct)


@_glb_gate
def test_glb_from_mass_with_bimir_fallback_on_failure(monkeypatch):
    # BimIR 경로가 실패하면 직접 경로로 폴백(무회귀) — bimir_path=False, 여전히 유효 glb.
    def _boom(*a, **k):
        raise RuntimeError("BimIR 경로 강제 실패(테스트)")

    monkeypatch.setattr(
        "app.services.bim.ifc_to_gltf_service.build_gltf_from_bimir", _boom
    )
    mass = _mass()
    glb, meta = glb_from_mass_with_bimir(mass, project_name="EQ")
    assert meta == {"bimir_path": False}
    # 폴백 glb도 직접 경로와 구조 동등.
    from app.services.bim.ifc_generator_service import build_ifc_from_mass
    from app.services.bim.ifc_to_gltf_service import ifc_bytes_to_glb

    glb_direct = ifc_bytes_to_glb(build_ifc_from_mass(mass, project_name="EQ"))
    assert _glb_signature(glb) == _glb_signature(glb_direct)


# ═══════════════════════════ 거부/스코프(item4 — cad/ingest 기원 IR) ═══════════════════════════
def test_reject_cad_ir_across_all_consumers():
    # cad_design_spec 기원 IR은 IFC/glb/QTO 전 소비처에서 명시 거부(무음 퇴화 금지).
    from app.services.bim.ifc_generator_service import build_ifc_from_bimir
    from app.services.bim.ifc_to_gltf_service import build_gltf_from_bimir
    from app.services.cost.geometry_qto import geometry_takeoff_from_bimir

    cad = _cad_model()
    with pytest.raises(ValueError):
        build_ifc_from_bimir(cad)
    with pytest.raises(ValueError):
        build_gltf_from_bimir(cad)
    with pytest.raises(ValueError):
        geometry_takeoff_from_bimir(cad)


def test_reject_ingest_ir_across_all_consumers():
    # design_ingest 기원 IR도 동일하게 전 소비처 거부(2D 파싱 결과 — 3D 압출 기하 없음).
    from app.services.bim.ifc_generator_service import build_ifc_from_bimir
    from app.services.bim.ifc_to_gltf_service import build_gltf_from_bimir
    from app.services.cost.geometry_qto import geometry_takeoff_from_bimir

    ing = _ingest_model()
    with pytest.raises(ValueError):
        build_ifc_from_bimir(ing)
    with pytest.raises(ValueError):
        build_gltf_from_bimir(ing)
    with pytest.raises(ValueError):
        geometry_takeoff_from_bimir(ing)


def test_scope_out_rationale_cad_ir_has_no_mass_geometry():
    # ★거부가 정답인 근거(스코프아웃 문서화): cad 기원 IR은 '의도'만 담아 매스 기하(폭·깊이)가 없다.
    #   IFC/glb는 폭·깊이·층수 없이는 산출 불가 → 거부가 정직(무날조). 어댑터 확장(의도→기하)은
    #   커널(AutoDesignEngine)이 이미 담당하며 그 산출 매스가 mass_geometry 경로로 흐른다.
    cad = _cad_model()
    assert cad.source_kind == "cad_design_spec"
    restored = mass_from_bimir(cad)
    assert "building_width_m" not in restored
    assert "building_depth_m" not in restored


def test_scope_out_rationale_ingest_ir_has_no_mass_geometry():
    # design_ingest 기원 IR도 매스 기하가 없다(룸 면적·레이어만) → IFC 압출 불가 → 거부 정직.
    ing = _ingest_model()
    assert ing.source_kind == "design_ingest"
    restored = mass_from_bimir(ing)
    assert "building_width_m" not in restored
    assert "building_depth_m" not in restored
