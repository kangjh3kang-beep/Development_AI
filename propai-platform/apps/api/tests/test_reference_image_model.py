import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from apps.api.database.models.reference_image import ReferenceImage


def _cols(m): return {c.name for c in m.__table__.columns}

class TestReferenceImage:
    def test_table_name(self):
        assert ReferenceImage.__tablename__ == "reference_images"
    def test_required_cols(self):
        assert {"id","tenant_id","project_id","image_url","source_type","is_active"}.issubset(_cols(ReferenceImage))
    def test_analysis_cols(self):
        assert {"width","height","aspect_ratio","brightness","contrast"}.issubset(_cols(ReferenceImage))
    def test_source_type_default(self):
        assert ReferenceImage.__table__.columns["source_type"].default.arg == "upload"
    def test_is_active_default(self):
        assert ReferenceImage.__table__.columns["is_active"].default.arg is True

if __name__ == "__main__": pytest.main([__file__, "-v", "--tb=short"])
