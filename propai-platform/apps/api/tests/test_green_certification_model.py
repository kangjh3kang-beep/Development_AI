import os, sys, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from apps.api.database.models.green_certification import GreenCertification

def _cols(m): return {c.name for c in m.__table__.columns}

class TestGreenCertification:
    def test_table_name(self):
        assert GreenCertification.__tablename__ == "green_certifications"
    def test_required_cols(self):
        assert {"id","tenant_id","project_id","cert_type","total_score","grade"}.issubset(_cols(GreenCertification))
    def test_cert_cols(self):
        assert {"category_scores_json","is_compliant","evaluated_at"}.issubset(_cols(GreenCertification))
    def test_is_compliant_default(self):
        assert GreenCertification.__table__.columns["is_compliant"].default.arg is False
    def test_timestamp_cols(self):
        assert {"created_at","updated_at"}.issubset(_cols(GreenCertification))

if __name__ == "__main__": pytest.main([__file__, "-v", "--tb=short"])