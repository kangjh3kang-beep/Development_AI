"""대지 규제 카드 — 토지특성 파싱 + 토지이용계획 통합 + 파이프라인 자동수집."""
from datetime import date

from app.adapters.regulation.vworld_landchar import VworldLandCharSource
from app.contracts.analysis import AnalysisInput
from app.services.land.land_card import collect_land_card
from app.services.pipeline.analysis_pipeline import run_analysis

_PNU = "1111010100100010000"


class _Resp:
    def __init__(self, data):
        self._d = data

    def raise_for_status(self):  # noqa: D102
        ...

    def json(self):
        return self._d


def _char():
    return _Resp({"landCharacteristicss": {"field": [{
        "lndcgrCodeNm": "대", "tpgrphHgCodeNm": "완경사", "roadSideCodeNm": "소로한면",
        "prposArea1Nm": "제1종일반주거지역", "ladUseSittnNm": "연립",
        "pblntfPclnd": "5150000", "stdrYear": "2024"}]}})


def _zones(*names):
    return _Resp({"landUses": {"field": [{"prposAreaDstrcCodeNm": n} for n in names]}})


def test_landchar_parses(monkeypatch):
    monkeypatch.setenv("VWORLD_API_KEY", "test-key")
    import httpx
    monkeypatch.setattr(httpx, "get", lambda url, params=None, headers=None, timeout=None: _char())
    d = VworldLandCharSource().fetch(_PNU, "2024")
    assert d["jimok"] == "대" and d["use_zone"] == "제1종일반주거지역"
    assert d["road_contact"] == "소로한면" and d["land_price"] == 5150000.0


def test_land_card_combines(monkeypatch):
    monkeypatch.setenv("VWORLD_API_KEY", "test-key")
    import httpx

    def _get(url, params=None, headers=None, timeout=None):
        if "getLandCharacteristics" in url:
            return _char()
        return _zones("제1종일반주거지역", "최고고도지구", "자연경관지구")

    monkeypatch.setattr(httpx, "get", _get)
    card = collect_land_card(_PNU, "2024")
    assert card.jimok == "대" and card.land_price == 5150000.0
    assert "최고고도지구" in card.use_zones_all and len(card.use_zones_all) == 3
    assert set(card.sources) == {"vworld_landchar", "vworld_landuse"}


def test_land_card_partial(monkeypatch):
    # 토지특성만, 토지이용 결손 → 카드 생성되되 notes 표면화.
    monkeypatch.setenv("VWORLD_API_KEY", "test-key")
    import httpx

    def _get(url, params=None, headers=None, timeout=None):
        if "getLandCharacteristics" in url:
            return _char()
        return _Resp({"landUses": {"field": []}})

    monkeypatch.setattr(httpx, "get", _get)
    card = collect_land_card(_PNU, "2024")
    assert card.jimok == "대"
    # 키 설정됨 + 조회 결과 없음 → '결과 없음(장애/결손 미상)'으로 구분 표면화(무규제 단정 금지).
    assert any("토지이용계획" in n and "결과 없음" in n for n in card.notes)


def test_pipeline_land_card(monkeypatch):
    monkeypatch.setenv("VWORLD_API_KEY", "test-key")
    import httpx

    def _get(url, params=None, headers=None, timeout=None):
        if "getLandCharacteristics" in url:
            return _char()
        return _zones("제1종일반주거지역")

    monkeypatch.setattr(httpx, "get", _get)
    r = run_analysis(AnalysisInput(pnu=_PNU, application_date=date(2026, 1, 1),
                                   collect_land_card=True, land_year="2024"))
    assert r.land_card is not None
    assert r.land_card.use_zone == "제1종일반주거지역"
    assert r.land_card.land_price == 5150000.0


def test_land_card_with_building(monkeypatch):
    monkeypatch.setenv("VWORLD_API_KEY", "test-key")
    import httpx

    def _get(url, params=None, headers=None, timeout=None):
        if "getLandCharacteristics" in url:
            return _char()
        if "getBuildingUse" in url:
            return _Resp({"response": {"totalCount": "1"}, "buildingUses": {"field": [
                {"buldTotar": "4686.15", "mainPrposCodeNm": "공동주택",
                 "groundFloorCo": "3", "undgrndFloorCo": "2", "strctCodeNm": "철근콘크리트구조"}]}})
        return _zones("제1종일반주거지역")

    monkeypatch.setattr(httpx, "get", _get)
    card = collect_land_card(_PNU, "2024")
    assert card.existing_building["total_floor_area"] == 4686.15
    assert card.existing_building["main_purpose"] == "공동주택"
    assert card.existing_building["underground_floors"] == 2
    assert "vworld_building" in card.sources


def test_building_no_construction(monkeypatch):
    # totalCount 0 → 나대지 추정(None).
    monkeypatch.setenv("VWORLD_API_KEY", "test-key")
    from app.adapters.regulation.vworld_building import VworldBuildingSource
    import httpx
    monkeypatch.setattr(httpx, "get", lambda url, params=None, headers=None, timeout=None:
                        _Resp({"response": {"totalCount": "0"}}))
    assert VworldBuildingSource().existing_building(_PNU) is None


def test_pipeline_no_land_card_by_default():
    r = run_analysis(AnalysisInput(pnu=_PNU, application_date=date(2026, 1, 1)))
    assert r.land_card is None  # 기본 off
