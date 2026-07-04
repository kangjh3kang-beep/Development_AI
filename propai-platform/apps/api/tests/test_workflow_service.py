import os
import sys
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.workflow_service import WorkflowService

TENANT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
PROJECT_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
WORKFLOW_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

DEFAULT_STAGES = ["토지매입", "설계", "인허가", "시공", "분양", "준공", "입주"]


def _mock_workflow(**overrides):
    m = MagicMock()
    m.id = overrides.get("id", WORKFLOW_ID)
    m.tenant_id = overrides.get("tenant_id", TENANT_ID)
    m.project_id = overrides.get("project_id", PROJECT_ID)
    m.workflow_name = overrides.get("workflow_name", "Main Workflow")
    m.current_stage = overrides.get("current_stage", "init")
    m.stage_index = overrides.get("stage_index", 0)
    m.stages_json = overrides.get("stages_json", ["A", "B", "C"])
    m.started_at = overrides.get("started_at")
    m.completed_at = overrides.get("completed_at")
    m.assigned_to = overrides.get("assigned_to")
    m.status = overrides.get("status", "pending")
    m.notes = overrides.get("notes")
    return m


class TestGetDefaultStages:
    def test_default_stages_count(self):
        stages = WorkflowService.get_default_stages()
        assert len(stages) == 7

    def test_default_stages_first(self):
        stages = WorkflowService.get_default_stages()
        assert stages[0] == "토지매입"

    def test_default_stages_last(self):
        stages = WorkflowService.get_default_stages()
        assert stages[-1] == "입주"


@pytest.mark.asyncio
class TestCreateWorkflow:
    @patch("apps.api.services.workflow_service.get_settings")
    async def test_create_returns_dict(self, mock_settings):
        mock_settings.return_value = MagicMock()
        db = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda r: setattr(r, "id", WORKFLOW_ID))
        svc = WorkflowService(db)
        result = await svc.create_workflow(TENANT_ID, PROJECT_ID, "Test WF", ["A", "B"])
        assert isinstance(result, dict)
        db.add.assert_called_once()
        db.commit.assert_awaited_once()


@pytest.mark.asyncio
class TestGetWorkflow:
    @patch("apps.api.services.workflow_service.get_settings")
    async def test_get_returns_none_when_not_found(self, mock_settings):
        mock_settings.return_value = MagicMock()
        db = AsyncMock()
        db.scalar = AsyncMock(return_value=None)
        svc = WorkflowService(db)
        result = await svc.get_workflow(WORKFLOW_ID, TENANT_ID)
        assert result is None

    @patch("apps.api.services.workflow_service.get_settings")
    async def test_get_returns_dict_when_found(self, mock_settings):
        mock_settings.return_value = MagicMock()
        db = AsyncMock()
        db.scalar = AsyncMock(return_value=_mock_workflow())
        svc = WorkflowService(db)
        result = await svc.get_workflow(WORKFLOW_ID, TENANT_ID)
        assert result is not None
        assert result["workflow_name"] == "Main Workflow"


@pytest.mark.asyncio
class TestAdvanceStage:
    @patch("apps.api.services.workflow_service.get_settings")
    async def test_advance_moves_index(self, mock_settings):
        mock_settings.return_value = MagicMock()
        db = AsyncMock()
        wf = _mock_workflow(stage_index=0, stages_json=["A", "B", "C"])
        db.scalar = AsyncMock(return_value=wf)
        db.refresh = AsyncMock()
        svc = WorkflowService(db)
        await svc.advance_stage(WORKFLOW_ID, TENANT_ID)
        assert wf.stage_index == 1
        assert wf.current_stage == "B"

    @patch("apps.api.services.workflow_service.get_settings")
    async def test_advance_beyond_last_completes(self, mock_settings):
        mock_settings.return_value = MagicMock()
        db = AsyncMock()
        wf = _mock_workflow(stage_index=2, stages_json=["A", "B", "C"])
        db.scalar = AsyncMock(return_value=wf)
        db.refresh = AsyncMock()
        svc = WorkflowService(db)
        await svc.advance_stage(WORKFLOW_ID, TENANT_ID)
        assert wf.status == "completed"

    @patch("apps.api.services.workflow_service.get_settings")
    async def test_advance_not_found_raises(self, mock_settings):
        mock_settings.return_value = MagicMock()
        db = AsyncMock()
        db.scalar = AsyncMock(return_value=None)
        svc = WorkflowService(db)
        with pytest.raises(ValueError):
            await svc.advance_stage(WORKFLOW_ID, TENANT_ID)


@pytest.mark.asyncio
class TestSetStatus:
    @patch("apps.api.services.workflow_service.get_settings")
    async def test_set_status_updates(self, mock_settings):
        mock_settings.return_value = MagicMock()
        db = AsyncMock()
        wf = _mock_workflow()
        db.scalar = AsyncMock(return_value=wf)
        db.refresh = AsyncMock()
        svc = WorkflowService(db)
        await svc.set_status(WORKFLOW_ID, TENANT_ID, "in_progress")
        assert wf.status == "in_progress"

    @patch("apps.api.services.workflow_service.get_settings")
    async def test_set_completed_sets_completed_at(self, mock_settings):
        mock_settings.return_value = MagicMock()
        db = AsyncMock()
        wf = _mock_workflow()
        db.scalar = AsyncMock(return_value=wf)
        db.refresh = AsyncMock()
        svc = WorkflowService(db)
        await svc.set_status(WORKFLOW_ID, TENANT_ID, "completed")
        assert wf.completed_at is not None


if __name__ == "__main__": pytest.main([__file__, "-v", "--tb=short"])
