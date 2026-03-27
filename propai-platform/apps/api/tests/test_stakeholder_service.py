import os, sys, uuid, pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.stakeholder_service import StakeholderService

TENANT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
PROJECT_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
STAKEHOLDER_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _mock_stakeholder(**overrides):
    m = MagicMock()
    m.id = overrides.get("id", STAKEHOLDER_ID)
    m.tenant_id = overrides.get("tenant_id", TENANT_ID)
    m.project_id = overrides.get("project_id", PROJECT_ID)
    m.name = overrides.get("name", "Hong Gildong")
    m.role = overrides.get("role", "developer")
    m.organization = overrides.get("organization", "PropAI")
    m.email = overrides.get("email", "hong@propai.kr")
    m.phone = overrides.get("phone", "010-1234-5678")
    m.responsibility = overrides.get("responsibility", None)
    m.is_active = overrides.get("is_active", True)
    m.notes = overrides.get("notes", None)
    return m


class TestGetValidRoles:
    def test_valid_roles_contains_developer(self):
        assert "developer" in StakeholderService.get_valid_roles()

    def test_valid_roles_contains_investor(self):
        assert "investor" in StakeholderService.get_valid_roles()

    def test_valid_roles_contains_contractor(self):
        assert "contractor" in StakeholderService.get_valid_roles()

    def test_valid_roles_contains_architect(self):
        assert "architect" in StakeholderService.get_valid_roles()

    def test_valid_roles_contains_authority(self):
        assert "authority" in StakeholderService.get_valid_roles()

    def test_valid_roles_count(self):
        assert len(StakeholderService.get_valid_roles()) == 5


@pytest.mark.asyncio
class TestCreateStakeholder:
    @patch("apps.api.services.stakeholder_service.get_settings")
    async def test_create_returns_dict(self, mock_settings):
        mock_settings.return_value = MagicMock()
        db = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda r: setattr(r, "id", STAKEHOLDER_ID))
        svc = StakeholderService(db)
        result = await svc.create_stakeholder(TENANT_ID, PROJECT_ID, "Hong", "developer")
        assert isinstance(result, dict)
        db.add.assert_called_once()
        db.commit.assert_awaited_once()


@pytest.mark.asyncio
class TestGetStakeholder:
    @patch("apps.api.services.stakeholder_service.get_settings")
    async def test_get_returns_none_when_not_found(self, mock_settings):
        mock_settings.return_value = MagicMock()
        db = AsyncMock()
        db.scalar = AsyncMock(return_value=None)
        svc = StakeholderService(db)
        result = await svc.get_stakeholder(STAKEHOLDER_ID, TENANT_ID)
        assert result is None

    @patch("apps.api.services.stakeholder_service.get_settings")
    async def test_get_returns_dict_when_found(self, mock_settings):
        mock_settings.return_value = MagicMock()
        db = AsyncMock()
        db.scalar = AsyncMock(return_value=_mock_stakeholder())
        svc = StakeholderService(db)
        result = await svc.get_stakeholder(STAKEHOLDER_ID, TENANT_ID)
        assert result is not None
        assert result["name"] == "Hong Gildong"


@pytest.mark.asyncio
class TestDeactivateStakeholder:
    @patch("apps.api.services.stakeholder_service.get_settings")
    async def test_deactivate_returns_true(self, mock_settings):
        mock_settings.return_value = MagicMock()
        db = AsyncMock()
        exec_result = MagicMock()
        exec_result.rowcount = 1
        db.execute = AsyncMock(return_value=exec_result)
        svc = StakeholderService(db)
        result = await svc.deactivate_stakeholder(STAKEHOLDER_ID, TENANT_ID)
        assert result is True

    @patch("apps.api.services.stakeholder_service.get_settings")
    async def test_deactivate_returns_false_when_not_found(self, mock_settings):
        mock_settings.return_value = MagicMock()
        db = AsyncMock()
        exec_result = MagicMock()
        exec_result.rowcount = 0
        db.execute = AsyncMock(return_value=exec_result)
        svc = StakeholderService(db)
        result = await svc.deactivate_stakeholder(STAKEHOLDER_ID, TENANT_ID)
        assert result is False


if __name__ == "__main__": pytest.main([__file__, "-v", "--tb=short"])