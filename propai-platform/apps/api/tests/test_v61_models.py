"""v61 DB 모델 + 시드 데이터 테스트."""

import pytest
from datetime import datetime, date


class TestV61DesignModels:
    """설계 도메인 6개 모델 클래스 존재 + 필드 검증."""

    def test_design_stage_creation(self):
        from apps.api.database.models.v61_design import DesignStage
        obj = DesignStage(stage_no=1, stage_name="계획설계", stage_status="active")
        assert obj.stage_no == 1
        assert obj.stage_name == "계획설계"
        assert hasattr(obj, "project_id")
        assert hasattr(obj, "completion_pct")

    def test_drawing_creation(self):
        from apps.api.database.models.v61_design import Drawing
        obj = Drawing()
        obj.drawing_code = "B-01"
        obj.drawing_type = "배치도"
        obj.drawing_name = "배치도 v1"
        obj.ai_generated = True
        assert obj.drawing_code == "B-01"
        assert obj.ai_generated is True
        assert hasattr(obj, "svg_content")
        assert hasattr(obj, "vector_data")

    def test_drawing_layer_creation(self):
        from apps.api.database.models.v61_design import DrawingLayer
        obj = DrawingLayer()
        obj.layer_name = "A-WALL"
        obj.layer_color = "#000000"
        obj.layer_weight = 0.50
        obj.layer_visible = True
        assert obj.layer_name == "A-WALL"
        assert obj.layer_visible is True

    def test_drawing_edit_history_creation(self):
        from apps.api.database.models.v61_design import DrawingEditHistory
        obj = DrawingEditHistory(edit_type="ADD", element_type="LINE", layer_name="A-WALL")
        assert obj.edit_type == "ADD"
        assert hasattr(obj, "before_data")
        assert hasattr(obj, "after_data")

    def test_permit_document_set_creation(self):
        from apps.api.database.models.v61_design import PermitDocumentSet
        obj = PermitDocumentSet()
        obj.doc_code = "A-01"
        obj.doc_category = "A"
        obj.doc_name = "건축계획서 (개요)"
        obj.is_required = True
        obj.is_completed = False
        assert obj.doc_code == "A-01"
        assert obj.is_required is True
        assert obj.is_completed is False

    def test_design_alternative_creation(self):
        from apps.api.database.models.v61_design import DesignAlternative
        obj = DesignAlternative()
        obj.alt_no = 1
        obj.alt_name = "대안A"
        obj.floor_area_ratio = 249.9
        obj.is_selected = False
        assert obj.alt_no == 1
        assert obj.is_selected is False
        assert hasattr(obj, "mc_win_rate")

    def test_design_tablenames(self):
        from apps.api.database.models.v61_design import (
            DesignStage, Drawing, DrawingLayer,
            DrawingEditHistory, PermitDocumentSet, DesignAlternative,
        )
        assert DesignStage.__tablename__ == "design_stages"
        assert Drawing.__tablename__ == "drawings"
        assert DrawingLayer.__tablename__ == "drawing_layers"
        assert DrawingEditHistory.__tablename__ == "drawing_edit_histories"
        assert PermitDocumentSet.__tablename__ == "permit_document_sets"
        assert DesignAlternative.__tablename__ == "design_alternatives"


class TestV61CostModels:
    """공사비 도메인 7개 모델 클래스 존재 + 필드 검증."""

    def test_cost_work_type_creation(self):
        from app.models.v61_cost import CostWorkType
        obj = CostWorkType(work_code="A01", work_name="철근콘크리트공사", work_category="건축")
        assert obj.work_code == "A01"

    def test_material_unit_price_creation(self):
        from app.models.v61_cost import MaterialUnitPrice
        obj = MaterialUnitPrice()
        obj.material_code = "RC-001"
        obj.material_name = "레미콘 25-240-15"
        obj.unit = "m³"
        obj.material_price = 82000
        obj.price_basis_year = 2026
        assert obj.price_basis_year == 2026

    def test_bim_quantity_creation(self):
        from app.models.v61_cost import BimQuantity
        obj = BimQuantity()
        obj.ifc_object_type = "IfcWall"
        obj.work_code = "A01"
        obj.quantity = 125.5
        obj.unit = "m³"
        obj.extraction_method = "AI_AUTO"
        obj.verified = False
        assert obj.extraction_method == "AI_AUTO"
        assert obj.verified is False

    def test_cost_calculation_sheet_creation(self):
        from app.models.v61_cost import CostCalculationSheet
        obj = CostCalculationSheet(work_category="건축", direct_material_cost=1_000_000_000)
        assert obj.work_category == "건축"
        assert hasattr(obj, "industrial_acc_ins")
        assert hasattr(obj, "total_project_cost")

    def test_progress_billing_creation(self):
        from app.models.v61_cost import ProgressBilling
        obj = ProgressBilling(billing_no=1, planned_value=500_000_000, earned_value=450_000_000,
                              actual_cost=480_000_000, evm_spi=0.90, evm_cpi=0.94)
        assert obj.evm_spi == 0.90

    def test_legal_rate_history_creation(self):
        from app.models.v61_cost import LegalRateHistory
        obj = LegalRateHistory(rate_category="산재보험_건설업", rate_value=0.035,
                               effective_from=date(2026, 1, 1))
        assert obj.rate_category == "산재보험_건설업"

    def test_standard_price_update_creation(self):
        from app.models.v61_cost import StandardPriceUpdate
        obj = StandardPriceUpdate()
        obj.price_period = "2026H1"
        obj.update_type = "품셈"
        obj.processed = False
        assert obj.processed is False

    def test_cost_tablenames(self):
        from app.models.v61_cost import (
            CostWorkType, MaterialUnitPrice, BimQuantity,
            CostCalculationSheet, ProgressBilling, LegalRateHistory, StandardPriceUpdate,
        )
        assert CostWorkType.__tablename__ == "cost_work_types"
        assert MaterialUnitPrice.__tablename__ == "material_unit_prices"
        assert BimQuantity.__tablename__ == "bim_quantities"
        assert CostCalculationSheet.__tablename__ == "cost_calculation_sheets"
        assert ProgressBilling.__tablename__ == "progress_billings"
        assert LegalRateHistory.__tablename__ == "legal_rate_histories"
        assert StandardPriceUpdate.__tablename__ == "standard_price_updates"


class TestV61SeedData:
    """시드 데이터 함수 검증."""

    def test_legal_rates_2026_count(self):
        from app.services.seed.v61_seed_data import seed_legal_rates_2026
        rates = seed_legal_rates_2026()
        assert len(rates) == 12
        categories = {r["rate_category"] for r in rates}
        assert "산재보험_건설업" in categories
        assert "부가가치세" in categories

    def test_standard_prices_count(self):
        from app.services.seed.v61_seed_data import seed_standard_prices_2026
        prices = seed_standard_prices_2026()
        assert len(prices) >= 29
        codes = {p["material_code"] for p in prices}
        assert "RC-001" in codes
        assert "TMP-003" in codes

    def test_permit_documents_count(self):
        from app.services.seed.v61_seed_data import seed_permit_documents
        docs = seed_permit_documents()
        assert len(docs) == 37
        categories = [d["doc_category"] for d in docs]
        assert categories.count("A") == 5
        assert categories.count("B") == 20

    def test_work_types_hierarchy(self):
        from app.services.seed.v61_seed_data import seed_work_types
        types = seed_work_types()
        assert len(types) >= 24
        top = [t for t in types if t["work_level"] == 0]
        assert len(top) == 5
        subs = [t for t in types if t["work_level"] == 1]
        assert all(s["parent_code"] is not None for s in subs)
