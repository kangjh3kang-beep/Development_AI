"""§4-B 참조설계 피드백루프 — 엔진 종횡비 편향 + 힌트 도출(서비스).

핵심: 합성 경로(AutoDesignEngine.generate)가 유사 사례의 기하(종횡비)를 참조
입력으로 받아 매스를 편향한다(결정론·법규 준수 불변·additive). 우선순위는
명시 massing_kind > 참조 비례 > auto(대지비율). reference_mass 미지정 시 기존
동작 완전 불변(하위호환).

서비스(derive_reference_mass_hint): find_similar→has_geometry 후보→get_reference
→mass_dims로 종횡비 추출. 기하 결측/정규화 실패/치수 무효 사례는 건너뛰어 다음 후보로
재탐색(footprint 수용도는 similarity_v2 순위에 반영). 없으면 used=False+정직 사유(가짜
추천 금지). 라우터 어댑터(_reference_hint): use_references=False면 DB 미개방, 조회 실패는
500이 아닌 used=False+사유로 정직 흡수(핵심 설계는 200 유지).
"""

import pytest

from app.services.cad import design_reference_service as svc
from app.services.cad.auto_design_engine import (
    AutoDesignEngineService,
    SiteInput,
)
from app.services.cad.design_reference_geometry import normalize_geometry


@pytest.fixture()
def engine():
    return AutoDesignEngineService()


# 형상이 시각 클램프에 걸리지 않고 실제로 매스를 구동하도록 충분히 큰 정방형 대지.
def _square_input(**kw) -> SiteInput:
    base = dict(
        site_area_sqm=4000,
        zone_code="2R",
        building_use="공동주택",
        target_unit_types=["84A"],
        floor_height_m=3.0,
    )
    base.update(kw)
    return SiteInput(**base)


def _ref_hint(aspect: float, **kw) -> dict:
    """참조 기하 힌트(종횡비=전면/깊이) — 라우터가 도출해 엔진에 주입하는 형태."""
    base = {
        "aspect": aspect,
        "ref_id": "ref-1",
        "title": "참조 84형 판상",
        "similarity": 88.0,
        "source": "design_reference",
        "basis": "유사 사례 기하 비례 주입",
    }
    base.update(kw)
    return base


class TestEngineReferenceMassBias:
    """compute_optimal_mass가 reference_mass 종횡비로 매스를 편향한다(결정론)."""

    def test_wide_reference_makes_building_wider_than_deep(self, engine):
        """전면이 넓은 참조(aspect 2.5) → 합성 매스가 폭>깊이로 편향(정방형 auto와 구분)."""
        auto = engine.generate(_square_input()).summary
        ref = engine.generate(_square_input(reference_mass=_ref_hint(2.5))).summary
        # auto는 정방형 대지에서 거의 정사각(폭≈깊이), 참조는 뚜렷이 폭>깊이.
        auto_ratio = auto["building_width_m"] / auto["building_depth_m"]
        ref_ratio = ref["building_width_m"] / ref["building_depth_m"]
        assert ref_ratio > 1.5
        assert ref_ratio > auto_ratio
        assert ref["building_width_m"] > ref["building_depth_m"]

    def test_reference_keeps_compliance(self, engine):
        """참조 편향 후에도 법규 준수(all_pass)·건폐율 한도 이내 유지."""
        result = engine.generate(_square_input(reference_mass=_ref_hint(2.5)))
        assert result.compliance["all_pass"] is True
        assert result.summary["bcr_percent"] <= result.summary.get("max_bcr_pct", 60) + 0.01 \
            or result.summary["bcr_percent"] <= 60.01

    def test_reference_provenance_in_summary(self, engine):
        """적용 시 summary.reference 프로비넌스 가산(정직 — ref_id/title/used)."""
        summary = engine.generate(_square_input(reference_mass=_ref_hint(2.5))).summary
        assert summary["reference"]["used"] is True
        assert summary["reference"]["ref_id"] == "ref-1"
        assert summary["reference"]["title"] == "참조 84형 판상"

    def test_clamped_aspect_is_honestly_reported(self, engine):
        """종횡비가 대지 유효치로 클램프되면 실현 종횡비·clamped=True를 정직 표기.

        정방형 4000㎡에서 aspect 2.5는 폭이 eff_w를 넘어 클램프 → 실현<2.5. provenance는
        목표 aspect는 보존하되 applied_aspect(실현)·clamped로 '부분 적용'을 정직 고지한다.
        """
        summary = engine.generate(_square_input(reference_mass=_ref_hint(2.5))).summary
        ref = summary["reference"]
        assert ref["used"] is True
        assert ref["aspect"] == 2.5  # 요청(목표) 종횡비는 그대로 보존
        realized = summary["building_width_m"] / summary["building_depth_m"]
        assert ref["applied_aspect"] == pytest.approx(round(realized, 3), abs=0.02)
        assert ref["applied_aspect"] < ref["aspect"]  # 클램프로 실현<목표
        assert ref["clamped"] is True

    def test_realizable_aspect_reports_not_clamped(self, engine):
        """대지 내 실현 가능한 종횡비(1.2)는 clamped=False·applied_aspect≈요청(과장 없음)."""
        summary = engine.generate(_square_input(reference_mass=_ref_hint(1.2))).summary
        ref = summary["reference"]
        assert ref["clamped"] is False
        assert ref["applied_aspect"] == pytest.approx(1.2, abs=0.05)

    def test_deep_reference_makes_building_deeper_than_wide(self, engine):
        """깊이가 큰 참조(aspect 0.5) → 합성 매스가 깊이>폭으로 편향(대칭 케이스)."""
        ref = engine.generate(_square_input(reference_mass=_ref_hint(0.5))).summary
        assert ref["building_depth_m"] > ref["building_width_m"]
        assert ref["reference"]["used"] is True

    def test_explicit_massing_kind_wins_over_reference(self, engine):
        """명시 massing_kind(tower)가 참조 비례보다 우선 — 참조는 미적용(정직 표기)."""
        summary = engine.generate(
            _square_input(massing_kind="tower", reference_mass=_ref_hint(3.0))
        ).summary
        assert summary["massing_kind"] == "tower"
        assert summary["massing_label"] == "타워형"
        assert summary["reference"]["used"] is False  # 명시 형상 우선

    def test_no_reference_is_backward_compatible(self, engine):
        """reference_mass 미지정 → summary에 reference 키 없음(기존 동작 완전 불변)."""
        summary = engine.generate(_square_input()).summary
        assert "reference" not in summary
        assert summary["massing_kind"] == "auto"

    def test_invalid_aspect_falls_back_to_auto(self, engine):
        """종횡비 0/음수 등 무효 힌트 → auto 동작(예외·가짜값 없음, 정직)."""
        auto = engine.generate(_square_input()).summary
        bad = engine.generate(_square_input(reference_mass=_ref_hint(0.0))).summary
        assert bad["building_width_m"] == auto["building_width_m"]
        assert bad["building_depth_m"] == auto["building_depth_m"]
        assert bad["reference"]["used"] is False


# ════════════════════════════════════════════════════════
# 서비스: derive_reference_mass_hint (find_similar → 기하 → 종횡비)
# ════════════════════════════════════════════════════════


def _rect_payload(w_px: float, d_px: float) -> dict:
    """직사각형 1개 design_payload(scale 10 → bbox width_m=w_px/10, height_m=d_px/10)."""
    pts = [{"id": "pt-0", "x": 0, "y": 0}, {"id": "pt-1", "x": w_px, "y": 0},
           {"id": "pt-2", "x": w_px, "y": d_px}, {"id": "pt-3", "x": 0, "y": d_px}]
    return {
        "points": pts,
        "lines": [{"id": f"ln-{i}", "start_point_id": f"pt-{i}",
                   "end_point_id": f"pt-{(i + 1) % 4}"} for i in range(4)],
        "surfaces": [{"id": "pg-0", "point_ids": ["pt-0", "pt-1", "pt-2", "pt-3"]}],
        "scale": 10.0,
    }


class _MultiRefSession:
    """design_references 다중 행 가짜 비동기 세션(저장→find_similar/get_reference 왕복).

    test_template_assembly._FakeRefSession은 단일 행 — 본 케이스는 후보 순회·건너뛰기
    검증을 위해 다중 행이 필요해 별도 구현(SQL 텍스트 분기로 INSERT/목록/단건조회 라우팅).
    """

    def __init__(self):
        self.rows: list[dict] = []  # 삽입 파라미터 dict 목록

    @staticmethod
    def _row16(p: dict) -> tuple:
        return (p["i"], p["t"], p["bu"], p["z"], p["a"], p["tu"], p["f"], p["ut"],
                p["url"], p["ft"], p["s"], p["n"], None, p["gs"], p["th"],
                p["gj"] is not None)

    def _row20(self, p: dict) -> tuple:
        return self._row16(p) + (p["gj"], p["dsj"], p["smj"], p["dvi"])

    async def execute(self, statement, params=None):  # noqa: ANN001
        sql = str(statement).lower().strip()
        if sql.startswith(("create", "alter")):
            return _FakeResult()
        if "insert into design_references" in sql:
            self.rows.append(params)
            return _FakeResult()
        if "from design_references" in sql and "where id" in sql:
            match = next((r for r in self.rows if r["i"] == params["i"]), None)
            return _FakeResult(row=self._row20(match) if match else None)
        if "from design_references" in sql and "order by created_at" in sql:
            return _FakeResult(rows=[self._row16(r) for r in reversed(self.rows)])
        return _FakeResult()

    async def commit(self):
        return None


class _FakeResult:
    def __init__(self, row=None, rows=None):
        self._row = row
        self._rows = rows if rows is not None else ([] if row is None else [row])

    def first(self):
        return self._row

    def all(self):
        return self._rows


async def _seed(db, *, title, area, geometry=None, raw_geometry=None, floors=5,
                building_use="공동주택", zone_code="2R", unit_types=("59A", "84A")):
    """사례 1건 시드. raw_geometry는 normalize 미경유 원본 주입(손상/무효 기하 테스트용 —
    has_geometry=True이지만 derive 루프 안에서 정규화/치수 검사로 건너뛰는 경로 검증)."""
    gj = raw_geometry if raw_geometry is not None else (
        normalize_geometry(geometry) if geometry else None)
    return await svc.add_reference(
        db, user_id="u-1", title=title, building_use=building_use, zone_code=zone_code,
        area_sqm=area, total_units=40, floors=floors, unit_types=list(unit_types),
        file_url=None, file_type=None, source="platform", note=None,
        geometry_json=gj,
        summary_json={"bcr_percent": 50.0, "far_percent": 180.0, "building_area_sqm": 200.0},
        geometry_source="platform" if gj is not None else None,
    )


# 손상/무효 기하(has_geometry=True이지만 치수 무효) — 단일점이라 bbox 0×0 → mass_dims 0.
_DEGENERATE_GEOMETRY = {"points": [{"id": "p", "x": 5, "y": 5}], "lines": [], "surfaces": []}


class TestDeriveReferenceMassHint:
    """find_similar 결과에서 기하 보유 최상위 사례의 종횡비를 힌트로 도출."""

    async def test_derives_aspect_from_top_geometry_reference(self):
        """기하 보유 유사 사례 → 종횡비(전면/깊이) 힌트 도출(used=True)."""
        db = _MultiRefSession()
        await _seed(db, title="60×24 판상", area=400, geometry=_rect_payload(600, 240))
        out = await svc.derive_reference_mass_hint(
            db, site_area_sqm=400.0, zone_code="2R", building_use="공동주택",
            unit_types=["59A", "84A"])
        assert out["used"] is True
        assert out["hint"]["aspect"] == pytest.approx(2.5, abs=0.05)
        assert out["hint"]["ref_id"] == out["ref"]["id"]
        assert out["hint"]["source"] == "design_reference"

    async def test_skips_reference_without_geometry(self):
        """기하 없는 사례는 건너뛰고 다음 후보(기하 보유)를 사용(재탐색)."""
        db = _MultiRefSession()
        await _seed(db, title="메타만(기하 없음)", area=400, geometry=None)
        await _seed(db, title="기하 보유", area=380, geometry=_rect_payload(500, 250))
        out = await svc.derive_reference_mass_hint(
            db, site_area_sqm=400.0, zone_code="2R", building_use="공동주택",
            unit_types=["59A", "84A"])
        assert out["used"] is True
        assert out["ref"]["title"] == "기하 보유"
        assert out["hint"]["aspect"] == pytest.approx(2.0, abs=0.05)

    async def test_no_geometry_anywhere_is_honest_unused(self):
        """기하 보유 사례가 전무 → used=False + 정직 사유(가짜 추천 금지)."""
        db = _MultiRefSession()
        await _seed(db, title="메타만", area=400, geometry=None)
        out = await svc.derive_reference_mass_hint(
            db, site_area_sqm=400.0, zone_code="2R", building_use="공동주택",
            unit_types=["59A", "84A"])
        assert out["used"] is False
        assert out["hint"] is None
        assert out["note"]  # 사유 문자열 필수

    async def test_empty_library_is_honest_unused(self):
        """라이브러리 비어있음 → used=False(예외 없이 정직 표기)."""
        db = _MultiRefSession()
        out = await svc.derive_reference_mass_hint(
            db, site_area_sqm=400.0, zone_code="2R", building_use="공동주택",
            unit_types=["59A", "84A"])
        assert out["used"] is False
        assert out["hint"] is None

    async def test_skips_invalid_geometry_in_loop_then_uses_next(self):
        """has_geometry=True지만 치수 무효인 사례는 루프 안에서 건너뛰고 다음 유효 후보 사용.

        (test_skips_reference_without_geometry는 has_geometry=False 사전제외만 탐 —
        이쪽은 후보로 들어온 뒤 정규화/치수 검사로 in-loop skip되는 경로를 검증.)
        """
        db = _MultiRefSession()
        await _seed(db, title="손상 기하", area=400, raw_geometry=_DEGENERATE_GEOMETRY)
        await _seed(db, title="유효 기하", area=395, geometry=_rect_payload(600, 240))
        out = await svc.derive_reference_mass_hint(
            db, site_area_sqm=400.0, zone_code="2R", building_use="공동주택",
            unit_types=["59A", "84A"])
        assert out["used"] is True
        assert out["ref"]["title"] == "유효 기하"
        assert "건너뜀" in out["note"]  # skipped 카운터 반영(정직)

    async def test_all_geometry_invalid_is_honest_unused(self):
        """기하 보유 후보가 전부 치수 무효 → used=False + '모두 무효' 정직 사유."""
        db = _MultiRefSession()
        await _seed(db, title="손상만", area=400, raw_geometry=_DEGENERATE_GEOMETRY)
        out = await svc.derive_reference_mass_hint(
            db, site_area_sqm=400.0, zone_code="2R", building_use="공동주택",
            unit_types=["59A", "84A"])
        assert out["used"] is False
        assert out["hint"] is None
        assert "무효" in out["note"]


# ════════════════════════════════════════════════════════
# 라우터 어댑터: _reference_hint (DB 미개방·실패 정직 흡수·실세션 배선)
# ════════════════════════════════════════════════════════


class _AsyncCtx:
    """async with AsyncSessionLocal() as db 모사 — 지정 db를 yield."""

    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *exc):
        return False


class TestReferenceHintAdapter:
    """drawing._reference_hint 본체 — monkeypatch로 우회하지 않고 직접 검증."""

    async def test_opt_out_returns_none_without_opening_db(self, monkeypatch):
        """use_references=False → None 반환 + AsyncSessionLocal 미호출(불변규칙4: DB 미접근)."""
        import apps.api.database.session as session_mod
        from apps.api.routers import drawing

        opened = {"n": 0}

        def _boom(*a, **k):
            opened["n"] += 1
            raise AssertionError("use_references=False인데 DB 세션을 열었음")

        monkeypatch.setattr(session_mod, "AsyncSessionLocal", _boom)
        out = await drawing._reference_hint(
            False, site_area_sqm=400.0, zone_code="2R",
            building_use="공동주택", unit_types=["84A"])
        assert out is None
        assert opened["n"] == 0

    async def test_lookup_failure_is_absorbed_honestly(self, monkeypatch):
        """조회 실패(예외) → 전파하지 않고 used=False + 사유에 예외 포함(침묵 금지)."""
        import apps.api.database.session as session_mod
        from app.services.cad import design_reference_service as ref_svc
        from apps.api.routers import drawing

        monkeypatch.setattr(session_mod, "AsyncSessionLocal", lambda: _AsyncCtx(object()))

        async def _raise(*a, **k):
            raise RuntimeError("connection refused")

        monkeypatch.setattr(ref_svc, "derive_reference_mass_hint", _raise)
        out = await drawing._reference_hint(
            True, site_area_sqm=400.0, zone_code="2R",
            building_use="공동주택", unit_types=["84A"])
        assert out["used"] is False
        assert out["hint"] is None
        assert "조회 실패" in out["note"] and "connection refused" in out["note"]

    async def test_success_wires_real_session_and_derive(self, monkeypatch):
        """use_references=True → 실제 세션 개방 + derive 호출 배선이 동작(가짜 dict 우회 아님)."""
        import apps.api.database.session as session_mod
        from apps.api.routers import drawing

        db = _MultiRefSession()
        await _seed(db, title="60×24 판상", area=400, geometry=_rect_payload(600, 240))
        monkeypatch.setattr(session_mod, "AsyncSessionLocal", lambda: _AsyncCtx(db))
        out = await drawing._reference_hint(
            True, site_area_sqm=400.0, zone_code="2R",
            building_use="공동주택", unit_types=["59A", "84A"])
        assert out["used"] is True
        assert out["hint"]["aspect"] == pytest.approx(2.5, abs=0.05)
