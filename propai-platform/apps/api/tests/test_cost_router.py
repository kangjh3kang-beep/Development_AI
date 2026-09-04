"""v61 공사비 라우터 테스트 — 경량 TestClient (전체 앱 비의존)."""

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.cost import router
from app.services.auth.auth_service import get_current_user


class _User:
    """get_current_user 의존성 override용 스텁(실 JWT·DB 불요)."""

    id = "00000000-0000-0000-0000-000000000001"
    tenant_id = "00000000-0000-0000-0000-000000000002"
    role = "user"
    is_active = True


_app = FastAPI()
_app.include_router(router)
# P0-4 보안: cost 라우터는 라우터 레벨 Depends(get_current_user)로 전 라우트 인증 강제.
# 테스트는 실 JWT·DB 없이 인증된 사용자를 주입(의존성 override)해 라우트 동작을 검증한다.
_app.dependency_overrides[get_current_user] = lambda: _User()
client = TestClient(_app)

PROJECT_ID = "test-project-cost"

IFC_ELEMENTS = [
    {"element_type": "IfcWall", "quantity": 100, "global_id": "w1",
     "name": "외벽", "unit": "m3"},
    {"element_type": "IfcSlab", "quantity": 200, "global_id": "s1",
     "name": "슬래브", "unit": "m3"},
    {"element_type": "IfcDoor", "quantity": 50, "global_id": "d1",
     "name": "현관문", "unit": "set"},
]

COST_ITEMS = [
    {"work_code": "A01", "item_name": "콘크리트", "spec": "25-240",
     "unit": "m3", "quantity": 500, "mat_unit": 82000,
     "labor_unit": 45000, "exp_unit": 15000},
    {"work_code": "A05", "item_name": "창호", "spec": "AL",
     "unit": "set", "quantity": 200, "mat_unit": 350000,
     "labor_unit": 80000, "exp_unit": 20000},
]


class TestUploadIFC:

    def test_upload_ifc(self):
        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/upload-ifc", json={
            "elements": IFC_ELEMENTS,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["item_count"] > 0
        assert len(data["unique_work_codes"]) > 0


class TestCalculateCost:

    def test_calculate(self):
        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/calculate", json={
            "items": COST_ITEMS,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_project_cost"] > 0
        assert data["item_count"] == 2
        assert data["project_id"] == PROJECT_ID

    def test_calculate_with_custom_rates(self):
        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/calculate", json={
            "items": COST_ITEMS,
            "rates": {
                "indirect_labor_rate": 0.15,
                "industrial_accident": 0.04,
                "employment_insurance": 0.01,
                "health_insurance_emp": 0.04,
                "national_pension_emp": 0.05,
                "long_term_care": 0.005,
                "retirement_fund": 0.025,
                "safety_health": 0.025,
                "env_preserve": 0.002,
                "general_mgmt": 0.06,
                "profit": 0.15,
                "vat": 0.10,
            },
        })
        assert resp.status_code == 200


class TestCostUseLlmGate:
    """T3: use_llm 게이트 — 기본 false는 CostInterpreter(LLM) 0호출, true는 과금 게이트 적용."""

    def test_calculate_use_llm_false_never_calls_interpreter(self, monkeypatch):
        calls = {"n": 0}

        class _Boom:
            def __init__(self):
                calls["n"] += 1

            async def generate_interpretation(self, _payload):
                return {}

        monkeypatch.setattr(
            "app.services.ai.cost_interpreter.CostInterpreter", _Boom, raising=False,
        )
        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/calculate", json={"items": COST_ITEMS})
        assert resp.status_code == 200
        assert calls["n"] == 0
        assert resp.json().get("ai_cost_analysis") is None

    def test_calculate_use_llm_true_invokes_interpreter(self, monkeypatch):
        calls = {"n": 0}

        class _Fake:
            def __init__(self):
                calls["n"] += 1

            async def generate_interpretation(self, _payload):
                return {"cost_analysis": "요약"}

        monkeypatch.setattr(
            "app.services.ai.cost_interpreter.CostInterpreter", _Fake, raising=False,
        )
        resp = client.post(
            f"/api/v1/cost/{PROJECT_ID}/calculate",
            json={"items": COST_ITEMS, "use_llm": True},
        )
        assert resp.status_code == 200
        assert calls["n"] == 1
        assert resp.json().get("ai_cost_analysis") == "요약"

    def test_calculate_use_llm_true_quota_402(self, monkeypatch):
        async def blocked(db, uid):
            return True

        async def not_team_over(db, uid):
            return False

        monkeypatch.setattr("app.core.billing_deps.get_current_user_id", lambda: "u1")
        monkeypatch.setattr("app.core.billing_deps.billing_service.is_blocked", blocked, raising=False)
        monkeypatch.setattr(
            "app.core.billing_deps.billing_service.team_limit_exceeded", not_team_over, raising=False,
        )
        resp = client.post(
            f"/api/v1/cost/{PROJECT_ID}/calculate",
            json={"items": COST_ITEMS, "use_llm": True},
        )
        assert resp.status_code == 402

    def test_boq_use_llm_true_quota_402(self, monkeypatch):
        async def blocked(db, uid):
            return True

        async def not_team_over(db, uid):
            return False

        monkeypatch.setattr("app.core.billing_deps.get_current_user_id", lambda: "u1")
        monkeypatch.setattr("app.core.billing_deps.billing_service.is_blocked", blocked, raising=False)
        monkeypatch.setattr(
            "app.core.billing_deps.billing_service.team_limit_exceeded", not_team_over, raising=False,
        )
        resp = client.post(
            f"/api/v1/cost/{PROJECT_ID}/boq",
            json={"total_gfa_sqm": 3000.0, "persist": False, "use_llm": True},
        )
        assert resp.status_code == 402


class TestSeniorQsConsultation:
    """P3: with_senior opt-in — /calculate·/estimate-overview 시니어 적산(QS) 자문 배선."""

    def test_calculate_with_senior_default_false_omits_consultation(self):
        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/calculate", json={"items": COST_ITEMS})
        assert resp.status_code == 200
        assert "senior_consultation" not in resp.json()

    def test_calculate_with_senior_true_flags_general_mgmt_over_cap(self):
        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/calculate", json={
            "items": COST_ITEMS,
            "rates": {
                "indirect_labor_rate": 0.1440, "industrial_accident": 0.0350,
                "employment_insurance": 0.0090, "health_insurance_emp": 0.03595,
                "national_pension_emp": 0.04750, "long_term_care": 0.004724,
                "retirement_fund": 0.02100, "safety_health": 0.02070,
                "env_preserve": 0.00160,
                "general_mgmt": 0.08,  # 법정 상한(6%) 초과 → BLOCK 기대
                "profit": 0.15, "vat": 0.10,
            },
            "with_senior": True,
        })
        assert resp.status_code == 200
        sc = resp.json()["senior_consultation"]
        assert sc["verdict"] == "BLOCK"
        ev = {e["rule_id"]: e for e in sc["evaluations"]}
        assert ev["qs.general_mgmt_cap"]["verdict"] == "BLOCK"
        assert ev["qs.profit_cap"]["verdict"] == "PASS"

    def test_estimate_overview_with_senior_default_false_omits_consultation(self):
        resp = client.post(
            "/api/v1/cost/estimate-overview",
            json={"building_type": "apartment", "total_gfa_sqm": 3000.0,
                  "floor_count_above": 10, "floor_count_below": 1, "structure_type": "RC"},
        )
        assert resp.status_code == 200
        assert "senior_consultation" not in resp.json()

    def test_estimate_overview_with_senior_true_attaches_consultation(self):
        resp = client.post(
            "/api/v1/cost/estimate-overview",
            json={"building_type": "apartment", "total_gfa_sqm": 3000.0,
                  "floor_count_above": 10, "floor_count_below": 1, "structure_type": "RC",
                  "with_senior": True},
        )
        assert resp.status_code == 200
        sc = resp.json()["senior_consultation"]
        assert sc is not None
        assert sc["verdict"] != "unavailable"
        assert sc["consultations"][0]["agent_key"] == "senior_quantity_surveyor"


class TestMonteCarlo:

    def test_monte_carlo(self):
        calc_resp = client.post(f"/api/v1/cost/{PROJECT_ID}/calculate", json={
            "items": COST_ITEMS,
        })
        base = calc_resp.json()

        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/monte-carlo", json={
            "base_result": base,
            "iterations": 1000,
            "seed": 42,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["p10"] <= data["p50"] <= data["p90"]


class TestBilling:

    def test_create_billing(self):
        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/billing/create", json={
            "billing_no": 1,
            "period_from": "2026-01-01",
            "period_to": "2026-03-31",
            "planned_value": 1000000000,
            "earned_value": 900000000,
            "actual_cost": 950000000,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["evm_spi"] == 0.9
        assert data["evm_cpi"] > 0

    def test_billing_summary(self):
        resp = client.get(f"/api/v1/cost/{PROJECT_ID}/billing/summary")
        assert resp.status_code == 200


class TestBillingRegisterD2:
    """D2 기성 등록(POST /{pid}/billing) — 청구기간 계약(period_from/period_to) 회귀 고정.

    감사 실증 결함: 프론트가 백엔드 모델에 없는 `period` 단일 필드로 전송
    → 필드가 optional 이라 422 없이 Pydantic 이 조용히 버려 기간이 NULL 로 영속.
    프론트는 이제 월 입력("2026-06")에서 period_from/period_to 를 파생해 보낸다.
    """

    def _post(self, body: dict):
        """영속 계층(register_billing)을 모킹하고 라우터 계약만 검증한다."""
        with patch(
            "app.services.cost.billing_service.register_billing",
            new=AsyncMock(return_value={
                "ok": True, "claim_id": 1,
                "ledger_hash": None, "anomalies_triggered": [],
            }),
        ) as mock_reg:
            resp = client.post(f"/api/v1/cost/{PROJECT_ID}/billing", json=body)
        return resp, mock_reg

    def test_period_range_reaches_persistence(self):
        """period_from/period_to 가 영속 호출까지 그대로 전달된다(기간 저장 확인)."""
        resp, mock_reg = self._post({
            "round": 1, "work_type": "골조",
            "contract_amount": 5_000_000_000, "claimed_amount": 500_000_000,
            "progress_pct": 10,
            "period_from": "2026-06-01", "period_to": "2026-06-30",
        })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        kwargs = mock_reg.call_args.kwargs
        assert kwargs["period_from"] == "2026-06-01"
        assert kwargs["period_to"] == "2026-06-30"
        assert kwargs["billing_no"] == 1

    def test_legacy_period_field_is_silently_dropped(self):
        """(결함 문서화) 모델에 없는 `period` 단일 필드는 무음 드롭 → 기간 None.

        이 동작이 프론트가 반드시 period_from/period_to 로 보내야 하는 이유다.
        """
        resp, mock_reg = self._post({
            "round": 2, "work_type": "골조",
            "contract_amount": 5_000_000_000, "claimed_amount": 500_000_000,
            "progress_pct": 20,
            "period": "2026-06",  # 잘못된 구계약 필드 — Pydantic extra 무시
        })
        assert resp.status_code == 200
        kwargs = mock_reg.call_args.kwargs
        assert kwargs["period_from"] is None
        assert kwargs["period_to"] is None


class TestFeasibility:

    def test_cost_to_feasibility(self):
        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/feasibility", json={
            "total_project_cost": 10000000000,
            "total_revenue": 15000000000,
            "project_months": 36,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["profit_rate_pct"] > 0
        assert data["gross_profit"] == 5000000000


class TestExportExcel:
    """T4: 영속 BOQ 실데이터 기반 내보내기 — 가짜 샘플(E01 유령코드 등) 금지."""

    def test_export_excel_no_estimate_returns_404(self):
        """영속 BOQ가 없으면 가짜 샘플 대신 404로 정직 응답한다."""
        with patch(
            "app.services.cost.cost_estimate_repository.list_estimates",
            new_callable=AsyncMock, return_value=[],
        ):
            resp = client.get(f"/api/v1/cost/{PROJECT_ID}/export-excel")
        assert resp.status_code == 404

    def test_export_excel_uses_persisted_boq(self):
        """estimate_id 미지정 시 최신 영속 BOQ의 실 항목으로 Excel을 생성한다(E01 유령코드 없음)."""
        fake_estimate = {
            "estimate_id": "est-1", "project_id": PROJECT_ID,
            "building_type": "apartment", "structure_type": "RC", "total_gfa_sqm": 1000.0,
            "summary": {"direct": 1_000_000, "indirect": 200_000, "total": 1_200_000,
                        "confidence_grade": "B"},
            "badges": {}, "qto_source": "derived", "created_at": "2026-01-01",
            "items": [
                {"code": "A01-03", "name": "콘크리트", "work_type": "철근콘크리트공사",
                 "quantity": 500.0, "unit": "m3", "unit_price": 247000.0, "amount": 123_500_000.0,
                 "price_source": "fallback", "price_basis_year": 2026, "qto_source": "derived",
                 "market_unit_price": None, "actual_unit_price": None},
            ],
        }
        with (
            patch(
                "app.services.cost.cost_estimate_repository.list_estimates",
                new_callable=AsyncMock, return_value=[{"estimate_id": "est-1"}],
            ),
            patch(
                "app.services.cost.cost_estimate_repository.get_estimate",
                new_callable=AsyncMock, return_value=fake_estimate,
            ),
        ):
            resp = client.get(f"/api/v1/cost/{PROJECT_ID}/export-excel")
        assert resp.status_code == 200
        ct = resp.headers["content-type"]
        assert "csv" in ct or "spreadsheet" in ct
        # ★독립리뷰 MEDIUM 반영: 본문을 실제로 열어 영속 항목 코드가 들어있고
        #   과거 하드코딩 샘플의 유령코드(E01)가 없음을 잠근다 — 상태코드만으로는
        #   샘플 회귀를 못 잡는다.
        body = resp.content.decode("utf-8-sig", errors="ignore") if "csv" in ct else ""
        if body:
            assert "A01-03" in body
            assert "E01" not in body


class TestWorkBreakdownAdditive:
    """P2 T2/T4: 공종분류 SSOT(wb_code/wb_name) + 단가 3분해 additive 노출 — 기존 키 불변."""

    def test_estimate_overview_items_have_wb_code(self):
        resp = client.post(
            "/api/v1/cost/estimate-overview",
            json={"building_type": "apartment", "total_gfa_sqm": 3000.0,
                  "floor_count_above": 10, "floor_count_below": 1, "structure_type": "RC"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 8  # 표준 8공종(01~08) 불변
        by_name = {it["name"]: it for it in items}
        assert by_name["레미콘 타설"]["wb_code"] == "WB04"
        assert by_name["레미콘 타설"]["wb_name"] == "골조공사(RC·철골)"
        # 기존 키(가짜값 없이) 그대로 유지 — additive 계약 확인.
        assert "unit_cost_won" in by_name["레미콘 타설"]

    def test_boq_items_have_wb_code(self):
        resp = client.post(
            f"/api/v1/cost/{PROJECT_ID}/boq",
            json={"total_gfa_sqm": 3000.0, "persist": False, "use_llm": False},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        by_code = {it["code"]: it for it in items}
        assert by_code["01-콘크리트"]["wb_code"] == "WB04"
        assert by_code["07-기계설비"]["wb_code"] == "WB10"
        assert by_code["08-전기설비"]["wb_code"] == "WB11"

    def test_unit_prices_items_have_mat_labor_exp_decomposition(self):
        resp = client.get("/api/v1/cost/unit-prices")
        assert resp.status_code == 200
        items = resp.json()["items"]
        by_code = {it["code"]: it for it in items}
        concrete = by_code["concrete"]
        # repository.get_prices()가 이미 반환하던 값 — 라우트에서 노출만(additive).
        assert concrete["mat_unit"] == 85_000
        assert concrete["labor_unit"] == 35_000
        assert concrete["exp_unit"] == 12_000
        assert concrete["mat_unit"] + concrete["labor_unit"] + concrete["exp_unit"] == concrete["standard"]


# ── P4 T1/T2: 절감 시나리오 Top-N · 설계변경 예측공사비 라우트 계약 ──

BASE_SPEC = {
    "building_type": "apartment", "total_gfa_sqm": 30000.0,
    "floor_count_above": 20, "floor_count_below": 2, "structure_type": "RC",
}


class TestAlternativesExtracted:
    """T1 전제: alternatives_engine 추출 후에도 /alternatives 응답 계약이 무회귀인지 확인."""

    def test_alternatives_basic_delta(self):
        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/alternatives", json={
            "base_params": BASE_SPEC,
            "variants": [{"label": "GFA -10%", "overrides": {"total_gfa_sqm": 27000.0}}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["base"]["total"] > 0
        v = data["variants"][0]
        assert v["label"] == "GFA -10%"
        assert v["delta"] < 0  # 연면적 축소 → 원가 감소
        assert v["delta_pct"] == -10.0
        assert "affected_work_types" in v  # 기존 계약 키 무손상

    def test_alternatives_rejects_zero_gfa(self):
        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/alternatives", json={
            "base_params": {"total_gfa_sqm": 0}, "variants": [],
        })
        assert resp.status_code == 422


class TestSavingScenariosRoute:
    """P4 T1 — POST /{pid}/saving-scenarios 라우트 계약."""

    def test_saving_scenarios_ranked_and_capped(self):
        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/saving-scenarios", json={
            "base_params": BASE_SPEC, "top_n": 3,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["project_id"] == PROJECT_ID
        assert data["evaluated_count"] <= 10  # 후보 캡
        candidates = data["candidates"]
        assert len(candidates) <= 3  # top_n 존중
        # 절감액(음수 delta) 내림차순 — savings 큰 순으로 정렬돼야 함.
        savings = [c["savings"] for c in candidates]
        assert savings == sorted(savings, reverse=True)
        for c in candidates:
            assert c["savings"] > 0  # 절감 후보만 포함(비절감 필터링)
            assert c["delta"] < 0
            assert "tradeoff" in c and c["tradeoff"]

    def test_saving_scenarios_rejects_zero_gfa(self):
        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/saving-scenarios", json={
            "base_params": {"total_gfa_sqm": 0},
        })
        assert resp.status_code == 422


class TestChangeForecastRoute:
    """P4 T2 — POST /{pid}/change-forecast 라우트 계약."""

    def test_mc_band_always_present_without_risks(self):
        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/change-forecast", json={
            "base_params": BASE_SPEC,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        band = data["mc_band"]
        assert band["p10"] <= band["p50"] <= band["p90"]
        assert data["scenarios"] == []
        assert data["data_gaps"] == []

    def test_risk_scenarios_and_honest_skip(self):
        risks = [
            {"category": "법규초과", "item": "건폐율 초과", "severity": "high", "est_impact": "약 +5%"},
            {"category": "누락", "item": "승강기 설치 확인 필요", "severity": "info", "est_impact": None},
        ]
        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/change-forecast", json={
            "base_params": BASE_SPEC, "risks": risks,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["scenarios"]) == 1
        scen = data["scenarios"][0]
        assert scen["risk_item"] == "건폐율 초과"
        assert scen["wb_targets"] == ["WB04"]
        assert scen["delta_low"] == scen["delta_high"] > 0  # 단일 수치(약 +5%)
        # 매핑 없는 리스크(정성 경고만)는 조용히 사라지지 않고 data_gaps에 정직 표면화.
        assert any("승강기 설치 확인 필요" in g for g in data["data_gaps"])

    def test_rejects_zero_gfa(self):
        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/change-forecast", json={
            "base_params": {"total_gfa_sqm": 0},
        })
        assert resp.status_code == 422


class TestBoqBacktestWiring:
    """W3-3(P9) — /boq persist=True 시 back-test 예측 스냅샷(record_estimate) 기록 배선."""

    def test_persist_true면_record_estimate_호출(self):
        fake_saved = {"ok": True, "estimate_id": "est-bt-1"}
        with (
            patch(
                "app.services.cost.cost_estimate_repository.save_estimate",
                new_callable=AsyncMock, return_value=fake_saved,
            ),
            patch(
                "app.services.cost.backtest.record_estimate",
                new_callable=AsyncMock, return_value={"ok": True},
            ) as mock_record,
        ):
            resp = client.post(
                f"/api/v1/cost/{PROJECT_ID}/boq",
                json={"total_gfa_sqm": 3000.0, "persist": True},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["estimate_id"] == "est-bt-1"
        mock_record.assert_awaited_once()
        _, kwargs = mock_record.call_args
        assert kwargs["estimate_id"] == "est-bt-1"
        assert kwargs["predicted_total_won"] == data["summary"]["total"]

    def test_persist_false면_record_estimate_미호출(self):
        with patch(
            "app.services.cost.backtest.record_estimate",
            new_callable=AsyncMock, return_value={"ok": True},
        ) as mock_record:
            resp = client.post(
                f"/api/v1/cost/{PROJECT_ID}/boq",
                json={"total_gfa_sqm": 3000.0, "persist": False},
            )
        assert resp.status_code == 200
        mock_record.assert_not_awaited()
