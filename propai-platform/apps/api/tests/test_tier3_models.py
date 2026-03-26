"""Tier 3 신규 DB 모델 단위 테스트.

T3-4: DesignVersion, FinancingStructure, QuantityTakeoff 모델의
테이블명, 필수 컬럼, 공통 필드를 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.database.models.design_version import DesignVersion
from apps.api.database.models.financing_structure import FinancingStructure
from apps.api.database.models.quantity_takeoff import QuantityTakeoff


ALL_MODELS = [DesignVersion, FinancingStructure, QuantityTakeoff]


def _get_column_names(model_cls) -> set[str]:
    """모델의 컬럼 이름 집합을 반환한다."""
    return {c.name for c in model_cls.__table__.columns}


# ──────────────────────────────────────────────
# DesignVersion
# ──────────────────────────────────────────────


class TestDesignVersion:
    """DesignVersion 모델을 검증한다."""

    def test_design_version_테이블명(self):
        """테이블 이름은 'design_versions'이다."""
        assert DesignVersion.__tablename__ == "design_versions"

    def test_design_version_필수_컬럼(self):
        """필수 컬럼이 모두 존재해야 한다."""
        cols = _get_column_names(DesignVersion)
        required = {"id", "tenant_id", "project_id", "version_number", "design_type"}
        assert required.issubset(cols)


# ──────────────────────────────────────────────
# FinancingStructure
# ──────────────────────────────────────────────


class TestFinancingStructure:
    """FinancingStructure 모델을 검증한다."""

    def test_financing_structure_테이블명(self):
        """테이블 이름은 'financing_structures'이다."""
        assert FinancingStructure.__tablename__ == "financing_structures"

    def test_financing_structure_비율_컬럼(self):
        """자기자본/타인자본/메자닌 비율 컬럼이 존재해야 한다."""
        cols = _get_column_names(FinancingStructure)
        ratio_cols = {"equity_ratio", "debt_ratio", "mezzanine_ratio"}
        assert ratio_cols.issubset(cols)


# ──────────────────────────────────────────────
# QuantityTakeoff
# ──────────────────────────────────────────────


class TestQuantityTakeoff:
    """QuantityTakeoff 모델을 검증한다."""

    def test_quantity_takeoff_테이블명(self):
        """테이블 이름은 'quantity_takeoffs'이다."""
        assert QuantityTakeoff.__tablename__ == "quantity_takeoffs"

    def test_quantity_takeoff_필수_컬럼(self):
        """필수 컬럼이 모두 존재해야 한다."""
        cols = _get_column_names(QuantityTakeoff)
        required = {"id", "tenant_id", "project_id", "item_code", "item_name", "quantity", "unit"}
        assert required.issubset(cols)


# ──────────────────────────────────────────────
# 공통 검증
# ──────────────────────────────────────────────


class TestCommonFields:
    """모든 Tier 3 모델의 공통 필드를 검증한다."""

    @pytest.mark.parametrize("model_cls", ALL_MODELS)
    def test_모든_모델_id_존재(self, model_cls):
        """모든 모델에 id 컬럼이 존재해야 한다."""
        cols = _get_column_names(model_cls)
        assert "id" in cols

    @pytest.mark.parametrize("model_cls", ALL_MODELS)
    def test_모든_모델_tenant_id_존재(self, model_cls):
        """모든 모델에 tenant_id 컬럼이 존재해야 한다."""
        cols = _get_column_names(model_cls)
        assert "tenant_id" in cols

    @pytest.mark.parametrize("model_cls", ALL_MODELS)
    def test_모든_모델_created_at_존재(self, model_cls):
        """모든 모델에 created_at 컬럼이 존재해야 한다."""
        cols = _get_column_names(model_cls)
        assert "created_at" in cols
