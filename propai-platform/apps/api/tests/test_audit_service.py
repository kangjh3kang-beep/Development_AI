"""감사 추적 서비스 테스트."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAuditEntry:
    """AuditEntry 테스트."""

    def test_entry_creation(self):
        from app.services.audit.audit_service import AuditEntry

        entry = AuditEntry(
            action="CREATE", user_id="u1",
            resource_type="project", resource_id="p1",
        )
        assert entry.action == "CREATE"
        assert entry.user_id == "u1"
        assert len(entry.entry_hash) == 64

    def test_entry_to_dict(self):
        from app.services.audit.audit_service import AuditEntry

        entry = AuditEntry(
            action="UPDATE", user_id="u2",
            resource_type="contract", resource_id="c1",
            changes={"status": "active"},
        )
        d = entry.to_dict()
        assert d["action"] == "UPDATE"
        assert d["changes"] == {"status": "active"}
        assert "entry_hash" in d

    def test_entry_hash_unique_per_instance(self):
        from app.services.audit.audit_service import AuditEntry

        e1 = AuditEntry(action="READ", user_id="u1", resource_type="x", resource_id="y")
        e2 = AuditEntry(action="READ", user_id="u1", resource_type="x", resource_id="y")
        assert e1.entry_hash != e2.entry_hash


class TestAuditTrailService:
    """AuditTrailService 테스트."""

    def test_log_creates_entry(self):
        from app.services.audit.audit_service import AuditTrailService

        svc = AuditTrailService()
        entry = svc.log("CREATE", "u1", "project", "p1")
        assert svc.total_entries == 1
        assert entry.action == "CREATE"

    def test_hash_chain_integrity(self):
        from app.services.audit.audit_service import AuditTrailService

        svc = AuditTrailService()
        svc.log("CREATE", "u1", "project", "p1")
        svc.log("UPDATE", "u1", "project", "p1", changes={"name": "new"})
        svc.log("DELETE", "u2", "project", "p1")
        assert svc.verify_chain() is True

    def test_empty_chain_is_valid(self):
        from app.services.audit.audit_service import AuditTrailService

        svc = AuditTrailService()
        assert svc.verify_chain() is True

    def test_filter_by_action(self):
        from app.services.audit.audit_service import AuditTrailService

        svc = AuditTrailService()
        svc.log("CREATE", "u1", "project", "p1")
        svc.log("READ", "u2", "project", "p1")
        svc.log("CREATE", "u1", "contract", "c1")
        result = svc.get_entries(action="CREATE")
        assert len(result) == 2

    def test_filter_by_resource_type(self):
        from app.services.audit.audit_service import AuditTrailService

        svc = AuditTrailService()
        svc.log("CREATE", "u1", "project", "p1")
        svc.log("CREATE", "u1", "contract", "c1")
        result = svc.get_entries(resource_type="contract")
        assert len(result) == 1

    def test_filter_by_user_id(self):
        from app.services.audit.audit_service import AuditTrailService

        svc = AuditTrailService()
        svc.log("CREATE", "u1", "project", "p1")
        svc.log("CREATE", "u2", "project", "p2")
        result = svc.get_entries(user_id="u1")
        assert len(result) == 1

    def test_get_entry_by_id(self):
        from app.services.audit.audit_service import AuditTrailService

        svc = AuditTrailService()
        entry = svc.log("CREATE", "u1", "project", "p1")
        found = svc.get_entry_by_id(entry.id)
        assert found is not None
        assert found.id == entry.id

    def test_get_entry_by_id_not_found(self):
        from app.services.audit.audit_service import AuditTrailService

        svc = AuditTrailService()
        assert svc.get_entry_by_id("nonexistent") is None

    def test_last_hash_updates(self):
        from app.services.audit.audit_service import AuditTrailService

        svc = AuditTrailService()
        assert svc.last_hash == ""
        e1 = svc.log("CREATE", "u1", "project", "p1")
        assert svc.last_hash == e1.entry_hash
        e2 = svc.log("UPDATE", "u1", "project", "p1")
        assert svc.last_hash == e2.entry_hash
