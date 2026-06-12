"""U3 템플릿 조립 백엔드 테스트.

계약:
- similarity_v2: 분해합 불변식(score == Σbreakdown.score, Σmax == 100),
  요인별 정답값(용도25/면적 밴드/평형 자카드/지역군/법규적합/footprint 수용)
- normalize_geometry/mass_dims: design_payload·shapes 양형 정규화 + bbox 역산 정답값
- assemble_from_reference: 균등 스케일 0.7~1.3 가드, 0/90° 회전 선택,
  층수 법규 클램프, summary 재계산(원본 복사 금지), validate 하드게이트
- 왕복: add_reference(geometry) → get_reference → assemble (jsonb 직렬화 라운드트립)

DB 비의존 — SQL 텍스트로 분기하는 가짜 세션(기존 test_design_v61_router 패턴).
"""

import io

import pytest

from app.services.cad import design_reference_service as svc
from app.services.cad.design_reference_geometry import (
    GeometryError,
    dxf_to_geometry,
    mass_dims,
    normalize_geometry,
    thumbnail_svg,
)
from app.services.cad.design_spec import DesignSpec
from app.services.cad.template_assembly_service import assemble_from_reference


# ── 공용 픽스처 헬퍼 ──

def _rect_payload(w_px: float, d_px: float, scale: float = 10.0,
                  floor_count: int | None = None) -> dict:
    """직사각형 1개(외곽 surface + 외벽 line) design_payload."""
    pts = [
        {"id": "pt-0", "x": 0, "y": 0},
        {"id": "pt-1", "x": w_px, "y": 0},
        {"id": "pt-2", "x": w_px, "y": d_px},
        {"id": "pt-3", "x": 0, "y": d_px},
    ]
    lines = [{"id": f"ln-{i}", "start_point_id": f"pt-{i}",
              "end_point_id": f"pt-{(i + 1) % 4}"} for i in range(4)]
    payload = {
        "points": pts, "lines": lines,
        "surfaces": [{"id": "pg-0", "point_ids": ["pt-0", "pt-1", "pt-2", "pt-3"]}],
        "scale": scale,
    }
    if floor_count:
        payload["floor_count"] = floor_count
    return payload


def _spec_400_2r(**kw) -> DesignSpec:
    """대지 400㎡·2종일반주거 기준 스펙(세트백 기본: 북3/남2/동1.5/서1.5)."""
    base = {"site_area_sqm": 400.0, "zone_code": "2R", "building_use": "공동주택",
            "target_unit_types": ["59A"]}
    base.update(kw)
    return DesignSpec(**base)


# ════════════════════════════════════════════════════════
# R3: similarity_v2
# ════════════════════════════════════════════════════════


class TestSimilarityV2:

    FULL_REF = {
        "building_use": "공동주택", "zone_code": "2R", "area_sqm": 400.0,
        "unit_types": ["59A", "84A"], "floors": 5,
        "summary_json": {"bcr_percent": 50.0, "far_percent": 180.0,
                         "building_area_sqm": 200.0},
    }

    def test_breakdown_sum_invariant(self):
        """분해합 불변식 — score == Σbreakdown.score, Σmax == 100, 0 ≤ score ≤ max."""
        cases = [
            dict(building_use="공동주택", zone_code="2R", area_sqm=400.0,
                 unit_types=["59A", "84A"]),
            dict(building_use="업무시설", zone_code="GC", area_sqm=900.0,
                 unit_types=[]),
            dict(building_use=None, zone_code=None, area_sqm=None, unit_types=[]),
            dict(building_use="공동주택", zone_code="1R", area_sqm=120.0,
                 unit_types=["39A"], setback_m=5.0),
        ]
        for kw in cases:
            score, breakdown = svc.similarity_v2(self.FULL_REF, **kw)
            assert score == round(sum(b["score"] for b in breakdown), 1)
            assert sum(b["max"] for b in breakdown) == 100
            for b in breakdown:
                assert 0.0 <= b["score"] <= b["max"]
                assert b["basis"]  # 근거 문자열 필수(가짜 무근거 점수 금지)

    def test_perfect_match_is_100(self):
        score, breakdown = svc.similarity_v2(
            self.FULL_REF, building_use="공동주택", zone_code="2R",
            area_sqm=400.0, unit_types=["59A", "84A"])
        assert score == 100.0
        by = {b["factor"]: b["score"] for b in breakdown}
        assert by == {"용도": 25.0, "면적": 20.0, "평형": 15.0, "지역군": 10.0,
                      "법규적합": 20.0, "footprint수용": 10.0}

    def test_area_band_outside_zero(self):
        """대지비 0.7~1.3 밖 → 면적 0점."""
        _, breakdown = svc.similarity_v2(
            self.FULL_REF, building_use="공동주택", zone_code="2R",
            area_sqm=250.0, unit_types=["59A"])  # ratio 1.6
        area = next(b for b in breakdown if b["factor"] == "면적")
        assert area["score"] == 0.0

    def test_zone_group_partial(self):
        """동일 지역군(2R↔3R) → 5점, 정확 일치 → 10점."""
        _, b_same = svc.similarity_v2(self.FULL_REF, building_use=None,
                                      zone_code="2R", area_sqm=None, unit_types=[])
        _, b_group = svc.similarity_v2(self.FULL_REF, building_use=None,
                                       zone_code="3R", area_sqm=None, unit_types=[])
        assert next(b["score"] for b in b_same if b["factor"] == "지역군") == 10.0
        assert next(b["score"] for b in b_group if b["factor"] == "지역군") == 5.0

    def test_legal_fit_against_ssot(self):
        """법규적합 — legal_limits_for SSOT 대비 ref BCR/FAR/층수 부적합이면 0점."""
        bad_ref = {**self.FULL_REF, "floors": 20,
                   "summary_json": {"bcr_percent": 70.0, "far_percent": 250.0,
                                    "building_area_sqm": 200.0}}
        # 1R: BCR 60%·FAR 200%·높이 20m → 3개 체크 모두 NG
        _, breakdown = svc.similarity_v2(bad_ref, building_use=None, zone_code="1R",
                                         area_sqm=None, unit_types=[])
        legal = next(b for b in breakdown if b["factor"] == "법규적합")
        assert legal["score"] == 0.0
        assert "NG" in legal["basis"]

    def test_footprint_capacity_with_setback(self):
        """setback 반영 수용한도(side-2s)² 초과분은 비례 감점."""
        _, breakdown = svc.similarity_v2(
            self.FULL_REF, building_use=None, zone_code="2R",
            area_sqm=400.0, unit_types=[], setback_m=5.0)
        # side 20m, 세트백 5m → 유효 10×10=100㎡ < ref 건축면적 200㎡ → 10×100/200=5.0
        fp = next(b for b in breakdown if b["factor"] == "footprint수용")
        assert fp["score"] == 5.0

    def test_no_data_factors_zero(self):
        """zone_code·summary 없으면 법규적합/footprint/지역군 0점(가짜 가점 금지)."""
        bare_ref = {"building_use": "공동주택", "area_sqm": 400.0, "unit_types": []}
        score, breakdown = svc.similarity_v2(bare_ref, building_use="공동주택",
                                             zone_code=None, area_sqm=400.0,
                                             unit_types=[])
        by = {b["factor"]: b["score"] for b in breakdown}
        assert by["지역군"] == 0.0
        assert by["법규적합"] == 0.0
        assert by["footprint수용"] == 0.0
        assert score == 45.0  # 용도25 + 면적20


# ════════════════════════════════════════════════════════
# R2: normalize_geometry / mass_dims / thumbnail / DXF
# ════════════════════════════════════════════════════════


class TestGeometryNormalize:

    def test_design_payload_form(self):
        g = normalize_geometry(_rect_payload(100, 80, floor_count=5))
        assert g["scale_px_per_m"] == 10.0
        assert g["bbox"] == {"min_x": 0.0, "min_y": 0.0, "max_x": 100.0, "max_y": 80.0,
                             "width_m": 10.0, "height_m": 8.0}
        assert len(g["points"]) == 4 and len(g["lines"]) == 4 and len(g["surfaces"]) == 1
        assert g["floor_count"] == 5

    def test_rescale_to_standard(self):
        """입력 scale 20px/m → 표준 10px/m로 좌표 환산(실세계 치수 보존)."""
        g = normalize_geometry(_rect_payload(200, 160, scale=20.0))
        assert g["bbox"]["width_m"] == 10.0
        assert g["bbox"]["height_m"] == 8.0
        assert g["bbox"]["max_x"] == 100.0  # 200px@20 → 100px@10

    def test_shapes_form_meters(self):
        g = normalize_geometry({"shapes": [
            {"points": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 8},
                        {"x": 0, "y": 8}], "closed": True},
        ], "unit": "m"})
        assert g["bbox"]["width_m"] == 10.0 and g["bbox"]["height_m"] == 8.0
        assert len(g["surfaces"]) == 1 and len(g["lines"]) == 4

    def test_idempotent_roundtrip(self):
        """표준형 재입력 시 동일 결과(멱등)."""
        g1 = normalize_geometry(_rect_payload(100, 80))
        g2 = normalize_geometry(g1)
        assert g2 == g1

    def test_empty_raises(self):
        with pytest.raises(GeometryError):
            normalize_geometry({})
        with pytest.raises(GeometryError):
            normalize_geometry({"points": []})

    def test_mass_dims_from_bbox(self):
        dims = mass_dims(normalize_geometry(_rect_payload(100, 80)))
        assert dims == {"building_width_m": 10.0, "building_depth_m": 8.0,
                        "building_footprint_sqm": 80.0}

    def test_thumbnail_svg(self):
        pytest.importorskip("svgwrite", reason="svgwrite 미설치 — 썸네일 테스트 스킵")
        svg = thumbnail_svg(normalize_geometry(_rect_payload(100, 80)))
        assert svg is not None and "<svg" in svg
        assert len(svg.encode("utf-8")) <= 50 * 1024


class TestDxfToGeometry:

    def _dxf_bytes(self, build) -> bytes:
        ezdxf = pytest.importorskip("ezdxf", reason="ezdxf 미설치 — DXF 테스트 스킵")
        doc = ezdxf.new("R2010")
        build(doc.modelspace())
        buf = io.StringIO()
        doc.write(buf)
        return buf.getvalue().encode("utf-8")

    def test_closed_lwpolyline_to_surface(self):
        data = self._dxf_bytes(
            lambda msp: msp.add_lwpolyline([(0, 0), (10, 0), (10, 8), (0, 8)], close=True))
        g = dxf_to_geometry(data)
        assert g["bbox"]["width_m"] == 10.0 and g["bbox"]["height_m"] == 8.0
        assert len(g["surfaces"]) == 1
        assert mass_dims(g)["building_footprint_sqm"] == 80.0

    def test_invalid_bytes_raise(self):
        pytest.importorskip("ezdxf", reason="ezdxf 미설치 — DXF 테스트 스킵")
        with pytest.raises(GeometryError):
            dxf_to_geometry(b"not a dxf file at all")

    def test_empty_modelspace_raises(self):
        data = self._dxf_bytes(lambda msp: None)
        with pytest.raises(GeometryError):
            dxf_to_geometry(data)


# ════════════════════════════════════════════════════════
# R4: assemble_from_reference — 스케일/회전/클램프/게이트 정답값
# ════════════════════════════════════════════════════════


class TestAssembleFromReference:

    def _ref(self, payload: dict, floors: int | None = 5, **extra) -> dict:
        return {"id": "ref-1", "title": "사례", "building_use": "공동주택",
                "zone_code": "2R", "area_sqm": 380.0, "floors": floors,
                "source": "platform", "geometry_source": "platform",
                "geometry_json": payload, **extra}

    def test_scale_guard_clamps_to_1_3(self):
        """ref 10×8m → 대지 400㎡(유효 17×15m): 필요 스케일 1.7 → 가드 1.3 클램프."""
        result = assemble_from_reference(self._ref(_rect_payload(100, 80)), _spec_400_2r())
        scale = next(a for a in result["adaptations"] if a["type"] == "scale")
        assert scale["value"] == 1.3 and scale["clamped"] is True
        assert scale["raw"] == pytest.approx(1.7, abs=1e-3)
        s = result["summary"]
        # 변환 치수 재계산 정답값: 13.0×10.4m
        assert s["building_area_sqm"] == 135.2
        assert s["num_floors"] == 5
        assert s["total_floor_area_sqm"] == 676.0
        assert s["bcr_percent"] == 33.8
        assert s["far_percent"] == 169.0
        assert s["source"] == "template_assembly" and s["reference_id"] == "ref-1"
        assert result["passed"] is True
        # 회전 없음(0°가 더 큰 스케일 허용)
        assert not any(a["type"] == "rotate" for a in result["adaptations"])

    def test_payload_points_transformed(self):
        """세트백 오프셋(서1.5m→15px, 북3m→30px) + 스케일 1.3 좌표 정답값."""
        result = assemble_from_reference(self._ref(_rect_payload(100, 80)), _spec_400_2r())
        pts = {p["id"]: p for p in result["design_payload"]["points"]}
        assert (pts["pt-0"]["x"], pts["pt-0"]["y"]) == (15.0, 30.0)
        assert (pts["pt-2"]["x"], pts["pt-2"]["y"]) == (145.0, 134.0)
        assert result["design_payload"]["scale"] == 10.0
        assert result["design_payload"]["floor_count"] == 5
        assert len(result["design_payload"]["surfaces"]) == 1

    def test_rotation_90_selected(self):
        """ref 8×16m는 유효 17×15m에 90° 회전이 더 큰 스케일 허용 → 회전 선택."""
        result = assemble_from_reference(
            self._ref(_rect_payload(80, 160), floors=3), _spec_400_2r())
        rotate = next(a for a in result["adaptations"] if a["type"] == "rotate")
        assert rotate["value"] == 90
        scale = next(a for a in result["adaptations"] if a["type"] == "scale")
        assert scale["value"] == pytest.approx(1.0625, abs=1e-3)
        assert scale["clamped"] is False
        s = result["summary"]
        assert s["building_area_sqm"] == pytest.approx(144.5, abs=0.01)  # 17.0×8.5
        assert s["num_floors"] == 3
        assert result["passed"] is True
        # 회전 변환 좌표: (0,0) → (15.0, 115.0) (회전 후 스케일·오프셋)
        pts = {p["id"]: p for p in result["design_payload"]["points"]}
        assert (pts["pt-0"]["x"], pts["pt-0"]["y"]) == (15.0, 115.0)

    def test_floors_clamped_by_far(self):
        """ref 30층 요청 → FAR 한도(800㎡/135.2㎡=5층)로 클램프."""
        result = assemble_from_reference(
            self._ref(_rect_payload(100, 80), floors=30), _spec_400_2r())
        clamp = next(a for a in result["adaptations"] if a["type"] == "floors_clamp")
        assert clamp["raw"] == 30 and clamp["value"] == 5
        assert result["summary"]["num_floors"] == 5
        assert result["passed"] is True

    def test_floor_count_fallback_from_geometry(self):
        """ref.floors 없으면 geometry.floor_count 사용."""
        result = assemble_from_reference(
            self._ref(_rect_payload(100, 80, floor_count=4), floors=None), _spec_400_2r())
        assert result["summary"]["num_floors"] == 4

    def test_validation_gate_blocks_bcr_violation(self):
        """ref 30×30m → 필요 스케일 0.5 < 0.7 가드 → 클램프 후 건폐율 초과 → passed=False."""
        result = assemble_from_reference(
            self._ref(_rect_payload(300, 300), floors=2), _spec_400_2r())
        scale = next(a for a in result["adaptations"] if a["type"] == "scale")
        assert scale["value"] == 0.7 and scale["clamped"] is True
        assert result["summary"]["building_area_sqm"] == 441.0  # 21×21m
        assert result["summary"]["bcr_percent"] == 110.25
        assert result["passed"] is False
        fields = [v["field"] for v in result["violations"] if v["severity"] == "error"]
        assert "bcr_pct" in fields

    def test_summary_not_copied_from_reference(self):
        """원본 summary_json이 있어도 복사하지 않고 변환 치수로 재계산."""
        fake_summary = {"bcr_percent": 1.0, "far_percent": 1.0, "total_units": 9999}
        result = assemble_from_reference(
            self._ref(_rect_payload(100, 80), summary_json=fake_summary), _spec_400_2r())
        assert result["summary"]["bcr_percent"] == 33.8  # 재계산값(원본 1.0 아님)
        assert result["summary"]["total_units"] != 9999

    def test_missing_geometry_raises(self):
        with pytest.raises(ValueError):
            assemble_from_reference(self._ref(_rect_payload(100, 80)) | {"geometry_json": None},
                                    _spec_400_2r())


# ════════════════════════════════════════════════════════
# R1 왕복: add_reference(geometry) → get_reference → assemble
# ════════════════════════════════════════════════════════


class _FakeResult:
    def __init__(self, row=None, rows=None):
        self._row = row
        self._rows = rows or ([] if row is None else [row])

    def first(self):
        return self._row

    def all(self):
        return self._rows


class _FakeRefSession:
    """design_references SQL 텍스트로 분기하는 가짜 비동기 세션(저장→조회 왕복)."""

    def __init__(self):
        self.inserted = None

    def _row_from_insert(self):
        p = self.inserted
        return (p["i"], p["t"], p["bu"], p["z"], p["a"], p["tu"], p["f"], p["ut"],
                p["url"], p["ft"], p["s"], p["n"], None,  # created_at
                p["gs"], p["th"], p["gj"] is not None,    # _COLS 추가 3컬럼
                p["gj"], p["dsj"], p["smj"], p["dvi"])    # _FULL_COLS 추가 4컬럼

    async def execute(self, statement, params=None):  # noqa: ANN001
        sql = str(statement).lower().strip()
        if sql.startswith(("create", "alter")):
            return _FakeResult()
        if "insert into design_references" in sql:
            self.inserted = params
            return _FakeResult()
        if "from design_references" in sql and "where id" in sql:
            row = self._row_from_insert() if self.inserted else None
            return _FakeResult(row=row)
        if "from design_references" in sql and "order by created_at" in sql:
            rows = [self._row_from_insert()[:16]] if self.inserted else []
            return _FakeResult(rows=rows)
        return _FakeResult()

    async def commit(self):
        return None


class TestRoundTrip:

    async def test_save_get_assemble(self):
        """저장(직렬화) → get(역직렬화) → 조립 — jsonb 라운드트립에 기하 보존."""
        db = _FakeRefSession()
        geometry = normalize_geometry(_rect_payload(100, 80))
        saved = await svc.add_reference(
            db, user_id="u-1", title="84형 판상 사례", building_use="공동주택",
            zone_code="2R", area_sqm=380.0, total_units=40, floors=5,
            unit_types=["59A", "84A"], file_url=None, file_type=None,
            source="platform", note=None,
            geometry_json=geometry, design_spec_json={"zone_code": "2R"},
            summary_json={"bcr_percent": 50.0, "building_area_sqm": 80.0},
            geometry_source="platform", thumbnail_svg=None,
        )
        assert saved["ok"] is True
        # INSERT는 jsonb를 문자열로 직렬화(가짜 세션이 그대로 보존 — DB 동작 모사)
        assert isinstance(db.inserted["gj"], str)

        ref = await svc.get_reference(db, saved["id"])
        assert ref is not None
        assert ref["has_geometry"] is True
        assert ref["geometry_source"] == "platform"
        assert ref["geometry_json"] == geometry  # 직렬화 왕복 무손실
        assert ref["summary_json"]["bcr_percent"] == 50.0

        result = assemble_from_reference(ref, _spec_400_2r())
        assert result["passed"] is True
        assert result["summary"]["building_area_sqm"] == 135.2
        assert result["reference"]["id"] == saved["id"]

    async def test_set_geometry_then_get(self):
        """메타만 저장 → set_geometry 부착 → get_reference 반영."""
        db = _FakeRefSession()
        saved = await svc.add_reference(
            db, user_id="u-1", title="메타만", building_use="공동주택",
            zone_code="2R", area_sqm=380.0, total_units=None, floors=5,
            unit_types=[], file_url=None, file_type=None, source="manual", note=None,
        )
        ref = await svc.get_reference(db, saved["id"])
        assert ref["has_geometry"] is False and ref["geometry_json"] is None

        # set_geometry는 UPDATE — 가짜 세션 단순화를 위해 INSERT 파라미터에 병합
        geometry = normalize_geometry(_rect_payload(100, 80))
        await svc.set_geometry(db, saved["id"], geometry_json=geometry,
                               geometry_source="dxf", thumbnail_svg=None)
        import json as _json
        db.inserted["gj"] = _json.dumps(geometry, ensure_ascii=False)
        db.inserted["gs"] = "dxf"
        ref2 = await svc.get_reference(db, saved["id"])
        assert ref2["has_geometry"] is True
        assert ref2["geometry_json"] == geometry

    async def test_find_similar_additive_fields(self):
        """find_similar — 기존 similarity 유지 + similarity_v2/breakdown additive."""
        db = _FakeRefSession()
        await svc.add_reference(
            db, user_id="u-1", title="사례", building_use="공동주택",
            zone_code="2R", area_sqm=400.0, total_units=40, floors=5,
            unit_types=["59A"], file_url=None, file_type=None,
            source="platform", note=None,
            geometry_json=normalize_geometry(_rect_payload(100, 80)),
            geometry_source="platform",
        )
        # 하위호환 경로(zone_code 미지정): 기존 similarity 정렬 + additive 필드
        items = await svc.find_similar(db, building_use="공동주택", area_sqm=400.0,
                                       unit_types=["59A"], k=5)
        assert items and items[0]["similarity"] == 100
        assert "similarity_v2" in items[0] and "similarity_breakdown" in items[0]
        # v2 경로(zone_code 지정): v2 점수·분해합 불변식
        items2 = await svc.find_similar(db, building_use="공동주택", area_sqm=400.0,
                                        unit_types=["59A"], k=5, zone_code="2R")
        assert items2
        top = items2[0]
        assert top["similarity_v2"] == round(
            sum(b["score"] for b in top["similarity_breakdown"]), 1)
