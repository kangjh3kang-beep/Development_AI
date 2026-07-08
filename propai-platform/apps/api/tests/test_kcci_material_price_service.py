"""KCCIMaterialPriceService 단위 테스트 (W3-1).

라우터(routers/cost_intelligence.py)와 app/services/cost/boq_builder.py에
실배선된 시장단가(SSOT) 서비스의 순수 로직 경로(코드 해석·가격모델·별칭매칭)와
DB 의존 경로(이력 적재·스냅샷·프로젝트 비용 추정)를 FakeSession으로 검증한다.
"""

import math
import os
import sys
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.kcci_material_price_service import (
    _MATERIAL_LIBRARY,
    KCCIMaterialPriceService,
)

TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
PROJECT_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")
ALL_CODES = list(_MATERIAL_LIBRARY.keys())


# ── FakeSession ──────────────────────────────


class FakeResult:
    def __init__(self, rows=None, scalar=None):
        self._rows = list(rows or [])
        self._scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def scalar_one_or_none(self):
        return self._scalar


class FakeSession:
    """execute 응답 큐 기반 AsyncSession 대역(항목이 callable이면 세션을 넘겨 지연 평가)."""

    def __init__(self, results=None):
        self.results = list(results or [])
        self.added = []
        self.commits = 0

    async def execute(self, stmt):
        if self.results:
            item = self.results.pop(0)
            return item(self) if callable(item) else item
        return FakeResult()

    async def scalar(self, stmt):
        result = await self.execute(stmt)
        return result.scalar_one_or_none()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


def _make_service(results=None, api_key=""):
    db = FakeSession(results=results)
    service = KCCIMaterialPriceService(db)
    # 환경 의존 제거: 시뮬레이션 소스명 고정
    service.settings = SimpleNamespace(kcci_api_key=api_key)
    return db, service


def _takeoff_row(item_name, *, item_code="X-01", category="general", material_spec=None, quantity=1.0):
    return SimpleNamespace(
        item_code=item_code,
        item_name=item_name,
        category=category,
        material_spec=material_spec,
        quantity=quantity,
    )


# ── 순수 로직: 코드/기간/소스명 ──────────────────────────────


class TestResolveAndHelpers:
    def test_자재코드_미지정시_전체_라이브러리(self):
        assert KCCIMaterialPriceService._resolve_material_codes(None) == ALL_CODES
        assert KCCIMaterialPriceService._resolve_material_codes([]) == ALL_CODES

    def test_자재코드_유효분만_필터링(self):
        resolved = KCCIMaterialPriceService._resolve_material_codes(
            ["rebar_sd400_d13", "no_such_code", "gypsum_board"]
        )
        assert resolved == ["rebar_sd400_d13", "gypsum_board"]

    def test_전부_무효코드면_전체로_확장된다(self):
        # 관찰: 무효 코드만 요청해도 에러 대신 전체 자재로 조용히 확장된다(현행 폴백 계약).
        assert KCCIMaterialPriceService._resolve_material_codes(["nope"]) == ALL_CODES

    def test_개월수_계산_경계값(self):
        mb = KCCIMaterialPriceService._months_between
        assert mb(datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 31, tzinfo=UTC)) == 0
        assert mb(datetime(2024, 12, 1, tzinfo=UTC), datetime(2025, 1, 1, tzinfo=UTC)) == 1
        assert mb(datetime(2025, 1, 1, tzinfo=UTC), datetime(2024, 12, 1, tzinfo=UTC)) == -1
        assert mb(datetime(2024, 1, 1, tzinfo=UTC), datetime(2026, 7, 1, tzinfo=UTC)) == 30

    def test_소스명은_API키_유무로_구분(self):
        assert KCCIMaterialPriceService._source_name("") == "kcci-simulated"
        assert KCCIMaterialPriceService._source_name("real-key") == "kcci-live-ready"

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "무날조 위반 후보: kcci_api_key가 설정되면 source_name이 'kcci-live-ready'로"
            " 표기되지만, 모듈에 KCCI 실API 호출 경로(httpx/aiohttp 등)가 전혀 없어"
            " 키 유무와 무관하게 동일한 합성 가격모델(_calc_material_price)이 저장된다."
            " 합성 데이터가 라이브 시세로 오인될 수 있음 — 서비스 수정 대상."
            " (이 서비스는 시장단가 SSOT로서 D4 market_unit_price의 출처)"
        ),
    )
    def test_live_소스명은_실제_API_호출경로를_전제해야_함(self):
        import inspect

        import apps.api.services.kcci_material_price_service as mod

        source = inspect.getsource(mod)
        assert ("httpx" in source) or ("aiohttp" in source) or ("requests" in source)


# ── 순수 로직: 가격모델 ──────────────────────────────


class TestPriceModel:
    def test_기준앵커_2024_01은_성장분_없이_주기항만_반영(self):
        config = _MATERIAL_LIBRARY["ready_mix_concrete"]
        anchor = datetime(2024, 1, 1, tzinfo=UTC)
        price = KCCIMaterialPriceService._calc_material_price(
            base_price=float(config["base_price_krw"]),
            annual_growth_ratio=float(config["annual_growth_ratio"]),
            volatility=float(config["volatility"]),
            phase=float(config["phase"]),
            snapshot_at=anchor,
        )
        expected = round(
            float(config["base_price_krw"])
            * (1 + float(config["volatility"]) * math.sin(float(config["phase"]) * 0.85)),
            2,
        )
        assert price == expected

    def test_가격모델_결정론과_연성장_추세(self):
        kwargs = dict(
            base_price=100000.0,
            annual_growth_ratio=0.06,
            volatility=0.01,
            phase=0.0,
        )
        at_2024 = KCCIMaterialPriceService._calc_material_price(
            **kwargs, snapshot_at=datetime(2024, 6, 1, tzinfo=UTC)
        )
        again = KCCIMaterialPriceService._calc_material_price(
            **kwargs, snapshot_at=datetime(2024, 6, 1, tzinfo=UTC)
        )
        at_2026 = KCCIMaterialPriceService._calc_material_price(
            **kwargs, snapshot_at=datetime(2026, 6, 1, tzinfo=UTC)
        )
        assert at_2024 == again  # 동일 입력 → 동일 출력(결정론)
        # 연 6% 성장 vs ±1% 변동성 → 2년 뒤 가격이 반드시 커야 한다
        assert at_2026 > at_2024

    def test_단가계산_필드와_1월의_전월처리(self):
        code = "rebar_sd400_d13"
        config = _MATERIAL_LIBRARY[code]
        snapshot = datetime(2026, 1, 1, tzinfo=UTC)
        result = KCCIMaterialPriceService._calc_unit_price(code, snapshot)
        assert set(result) == {
            "unit_price_krw",
            "price_index",
            "mom_change_ratio",
            "yoy_change_ratio",
        }
        assert result["price_index"] == round(
            result["unit_price_krw"] / float(config["base_price_krw"]) * 100, 2
        )
        # 1월 스냅샷의 전월은 전년도 12월이어야 한다
        prev_dec = KCCIMaterialPriceService._calc_material_price(
            base_price=float(config["base_price_krw"]),
            annual_growth_ratio=float(config["annual_growth_ratio"]),
            volatility=float(config["volatility"]),
            phase=float(config["phase"]),
            snapshot_at=datetime(2025, 12, 1, tzinfo=UTC),
        )
        assert result["mom_change_ratio"] == round(
            (result["unit_price_krw"] - prev_dec) / prev_dec, 4
        )


# ── 순수 로직: 별칭 매칭 ──────────────────────────────


class TestMatchMaterialCode:
    def test_한글_및_영문_별칭_매칭(self):
        match = KCCIMaterialPriceService._match_material_code
        assert match(_takeoff_row("레미콘 타설")) == "ready_mix_concrete"
        assert match(_takeoff_row("배근", material_spec="SD400 철근")) == "rebar_sd400_d13"
        assert match(_takeoff_row("창호공사", category="유리")) == "glass_lowe_panel"
        assert match(_takeoff_row("석고보드 설치")) == "gypsum_board"

    def test_매칭실패시_None(self):
        assert KCCIMaterialPriceService._match_material_code(_takeoff_row("타일 마감")) is None

    def test_별칭_중복시_라이브러리_선순위_자재로_매칭된다(self):
        # 관찰(현행 동작 고정): 'structural steel frame'은 h_beam_steel의
        # 별칭('steel frame')보다 rebar의 별칭('steel')이 먼저 부분일치해
        # rebar_sd400_d13으로 귀속된다. 별칭 우선순위/최장일치 부재 — 오귀속 위험.
        row = _takeoff_row("structural steel frame")
        assert KCCIMaterialPriceService._match_material_code(row) == "rebar_sd400_d13"


# ── DB 의존 경로: 비용 추정 ──────────────────────────────


class TestEstimateProjectCosts:
    async def test_물량산출_행이_있으면_수량x단가_합산(self):
        latest_rows = {
            "ready_mix_concrete": SimpleNamespace(unit_price_krw=100_000.0),
            "rebar_sd400_d13": SimpleNamespace(unit_price_krw=800_000.0),
        }
        quantity_rows = [
            _takeoff_row("레미콘 25-240", quantity=10.0),
            _takeoff_row("레미콘 펌프카", quantity=2.5),
            _takeoff_row("타일 마감", quantity=99.0),  # 미매칭 → 무시
        ]
        db, service = _make_service(results=[FakeResult(rows=quantity_rows)])
        estimates = await service._estimate_project_costs(
            tenant_id=TENANT_ID, project_id=PROJECT_ID, latest_rows=latest_rows
        )
        assert estimates["ready_mix_concrete"] == 1_250_000.0  # (10 + 2.5) * 100,000
        assert estimates["rebar_sd400_d13"] is None  # 물량 0 → 추정 없음(정직 폴백)

    async def test_물량없고_프로젝트_면적있으면_면적기반_추정(self):
        latest_rows = {"ready_mix_concrete": SimpleNamespace(unit_price_krw=100_000.0)}
        project = SimpleNamespace(total_area_sqm=1_000.0)
        db, service = _make_service(
            results=[FakeResult(rows=[]), FakeResult(scalar=project)]
        )
        estimates = await service._estimate_project_costs(
            tenant_id=TENANT_ID, project_id=PROJECT_ID, latest_rows=latest_rows
        )
        # 1,000㎡ * 0.42 m3/㎡ * 100,000원 = 42,000,000
        assert estimates["ready_mix_concrete"] == 42_000_000.0

    async def test_프로젝트_미지정시_전부_None_DB미조회(self):
        db, service = _make_service(results=[FakeResult(rows=[])])
        estimates = await service._estimate_project_costs(
            tenant_id=TENANT_ID,
            project_id=None,
            latest_rows={"gypsum_board": SimpleNamespace(unit_price_krw=1.0)},
        )
        assert estimates == {"gypsum_board": None}
        assert len(db.results) == 1  # 큐 미소비 = DB 조회 없음


# ── DB 의존 경로: 이력 적재/스냅샷 ──────────────────────────────


class TestHistoryAndSnapshot:
    async def test_refresh_snapshot_빈이력이면_5자재x6개월_적재_후_스냅샷(self):
        def _rows_from_added(session):
            rows = sorted(session.added, key=lambda r: r.snapshot_at, reverse=True)
            rows = sorted(rows, key=lambda r: r.material_code)
            return FakeResult(rows=rows)

        db, service = _make_service(results=[FakeResult(rows=[]), _rows_from_added])
        snapshot = await service.refresh_snapshot(
            tenant_id=TENANT_ID,
            project_id=None,
            material_codes=None,
            region_code="KR",
        )
        assert len(db.added) == len(ALL_CODES) * 6  # 30행 시딩
        assert db.commits == 1
        assert all(row.source_name == "kcci-simulated" for row in db.added)
        assert snapshot["region_code"] == "KR"
        assert snapshot["as_of"] is not None
        assert [item["material_code"] for item in snapshot["items"]] == ALL_CODES
        for item in snapshot["items"]:
            assert item["current_unit_price_krw"] > 0
            assert item["estimated_project_cost_krw"] is None  # 프로젝트 미지정
            assert len(item["history"]) == 6
            # 이력은 과거→현재 오름차순
            times = [point["snapshot_at"] for point in item["history"]]
            assert times == sorted(times)

    async def test_ensure_history_기존이력_완비시_재적재_안함(self):
        now = datetime.now(UTC)
        anchors = []
        year, month = now.year, now.month
        for _ in range(6):
            anchors.append(datetime(year, month, 1, tzinfo=UTC))
            year, month = (year - 1, 12) if month == 1 else (year, month - 1)
        existing = [
            SimpleNamespace(material_code="gypsum_board", snapshot_at=anchor)
            for anchor in anchors
        ]
        db, service = _make_service(results=[FakeResult(rows=existing)])
        await service._ensure_history(
            tenant_id=TENANT_ID, material_codes=["gypsum_board"], region_code="KR"
        )
        assert db.added == []  # 멱등: 신규 적재 없음
        assert db.commits == 0

    async def test_스냅샷_경보등급_경계값(self):
        def _price_row(code, mom, yoy):
            config = _MATERIAL_LIBRARY[code]
            return SimpleNamespace(
                material_code=code,
                material_name=str(config["name"]),
                category=str(config["category"]),
                unit=str(config["unit"]),
                unit_price_krw=1000.0,
                price_index=100.0,
                mom_change_ratio=mom,
                yoy_change_ratio=yoy,
                snapshot_at=datetime(2026, 7, 1, tzinfo=UTC),
                source_name="kcci-simulated",
            )

        rows = [
            _price_row("ready_mix_concrete", 0.0349, 0.1199),  # 경계 직전 → normal
            _price_row("rebar_sd400_d13", 0.035, 0.0),  # mom 경계 → elevated
            _price_row("h_beam_steel", 0.055, 0.0),  # mom 경계 → critical
            _price_row("glass_lowe_panel", 0.0, 0.18),  # yoy 경계 → critical
        ]
        codes = [row.material_code for row in rows]
        db, service = _make_service(results=[FakeResult(rows=rows)])
        snapshot = await service._build_snapshot(
            tenant_id=TENANT_ID,
            project_id=None,
            region_code="KR",
            material_codes=codes,
        )
        levels = {item["material_code"]: item["alert_level"] for item in snapshot["items"]}
        assert levels == {
            "ready_mix_concrete": "normal",
            "rebar_sd400_d13": "elevated",
            "h_beam_steel": "critical",
            "glass_lowe_panel": "critical",
        }
        alert_codes = {alert["material_code"] for alert in snapshot["alerts"]}
        assert alert_codes == {"rebar_sd400_d13", "h_beam_steel", "glass_lowe_panel"}
        critical_alert = next(
            alert for alert in snapshot["alerts"] if alert["material_code"] == "h_beam_steel"
        )
        assert critical_alert["severity"] == "critical"
        assert "5.5%" in critical_alert["detail"]
