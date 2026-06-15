"""v53 permit submission and tracking service."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone, UTC
UTC = UTC
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.database.models.phase_v53_operations import PermitSubmission

_PERMIT_CHECKLISTS = {
    "building_permit": [
        {"id": "BA-01", "name": "Site plan", "required": True},
        {"id": "BA-02", "name": "Structural review", "required": True},
        {"id": "BA-03", "name": "Fire and life safety plan", "required": True},
        {"id": "BA-04", "name": "Energy compliance sheet", "required": True},
        {"id": "BA-05", "name": "Land-use confirmation", "required": True},
        {"id": "BA-06", "name": "Traffic impact memo", "required": False, "condition": "large_site"},
        {"id": "BA-07", "name": "Environmental review note", "required": False, "condition": "public_or_large"},
    ],
    "development_permit": [
        {"id": "DA-01", "name": "Development masterplan", "required": True},
        {"id": "DA-02", "name": "Drainage strategy", "required": True},
        {"id": "DA-03", "name": "Access road plan", "required": True},
        {"id": "DA-04", "name": "Boundary survey", "required": True},
        {"id": "DA-05", "name": "Environmental baseline", "required": True},
        {"id": "DA-06", "name": "Agricultural conversion opinion", "required": False, "condition": "agricultural"},
    ],
    "occupancy_approval": [
        {"id": "UC-01", "name": "Completion certificate", "required": True},
        {"id": "UC-02", "name": "Commissioning report", "required": True},
        {"id": "UC-03", "name": "Fire completion sign-off", "required": True},
        {"id": "UC-04", "name": "Energy performance certificate", "required": True},
        {"id": "UC-05", "name": "Indoor air quality report", "required": True},
        {"id": "UC-06", "name": "Accessibility closeout", "required": False, "condition": "public"},
    ],
}

_PERMIT_DURATIONS = {
    "building_permit": {"seoul": 20, "gyeonggi": 18, "default": 15},
    "development_permit": {"seoul": 30, "gyeonggi": 28, "default": 24},
    "occupancy_approval": {"seoul": 12, "gyeonggi": 10, "default": 8},
}

_PERMIT_STAGES = [
    "document-prep",
    "submitted",
    "under-review",
    "site-inspection",
    "approved",
]

_DEFAULT_RULES_PATH = (
    Path(__file__).resolve().parents[1] / "config_data" / "seumter_permit_rules.default.json"
)
_DEFAULT_REGION_ALIASES = {
    "서울": "seoul",
    "서울시": "seoul",
    "서울특별시": "seoul",
    "seoul": "seoul",
    "경기": "gyeonggi",
    "경기도": "gyeonggi",
    "gyeonggi": "gyeonggi",
}
_DEFAULT_MULTIPLIERS = {
    "large_site_threshold_sqm": 10_000,
    "large_site_multiplier": 1.10,
    "very_large_site_threshold_sqm": 30_000,
    "very_large_site_multiplier": 1.20,
    "public_project_multiplier": 1.15,
    "agricultural_multiplier": 1.10,
}


def _load_dynamic_rules() -> dict[str, Any]:
    """외부 규칙 파일(환경변수/설정)을 우선 적용하고, 없으면 내장 기본 규칙을 사용한다."""
    settings = get_settings()
    configured = (settings.seumter_permit_rules_path or os.getenv("SEUMTER_PERMIT_RULES_PATH", "")).strip()
    candidate_paths = [Path(configured)] if configured else []
    candidate_paths.append(_DEFAULT_RULES_PATH)

    for path in candidate_paths:
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
    return {}


def _resolve_region_key(region: str, rules: dict[str, Any]) -> str:
    aliases = dict(_DEFAULT_REGION_ALIASES)
    aliases.update(rules.get("region_aliases") or {})
    normalized = region.strip().lower()
    return aliases.get(region, aliases.get(normalized, normalized))


class SeumterPermitService:
    """Submit and track project permit workflows."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _build_checklist(
        *,
        permit_type: str,
        building_area_sqm: float,
        is_public: bool,
        is_agricultural: bool,
        submitted_document_ids: list[str],
    ) -> list[dict]:
        rules = _load_dynamic_rules()
        permit_profiles = rules.get("permit_types") or {}
        profile = permit_profiles.get(permit_type) or {}
        template = profile.get("checklist") or _PERMIT_CHECKLISTS.get(permit_type)
        if template is None:
            raise ValueError(f"Unsupported permit type: {permit_type}")

        submitted = set(submitted_document_ids)
        items: list[dict] = []
        for item in template:
            condition = item.get("condition")
            applicable = item["required"]
            if condition == "large_site":
                applicable = building_area_sqm >= 10000
            elif condition == "public_or_large":
                applicable = is_public or building_area_sqm >= 15000
            elif condition == "public":
                applicable = is_public
            elif condition == "agricultural":
                applicable = is_agricultural

            items.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "required": item["required"],
                    "applicable": applicable,
                    "submitted": item["id"] in submitted,
                }
            )
        return items

    @staticmethod
    def _validate_checklist(checklist: list[dict]) -> dict:
        required_items = [item for item in checklist if item["applicable"]]
        required_submitted = [item for item in required_items if item["submitted"]]
        missing = [item["name"] for item in required_items if not item["submitted"]]
        readiness_score = round(
            (len(required_submitted) / max(len(required_items), 1)) * 100.0,
            2,
        )
        return {
            "required_total": len(required_items),
            "required_submitted": len(required_submitted),
            "missing_required_documents": missing,
            "is_ready": not missing,
            "readiness_score": readiness_score,
        }

    @staticmethod
    def _estimate_duration(permit_type: str, region: str) -> dict:
        return SeumterPermitService._estimate_duration_contextual(
            permit_type=permit_type,
            region=region,
            building_area_sqm=0.0,
            is_public=False,
            is_agricultural=False,
        )

    @staticmethod
    def _estimate_duration_contextual(
        *,
        permit_type: str,
        region: str,
        building_area_sqm: float,
        is_public: bool,
        is_agricultural: bool,
    ) -> dict:
        rules = _load_dynamic_rules()
        permit_profiles = rules.get("permit_types") or {}
        profile = permit_profiles.get(permit_type) or {}
        duration = profile.get("durations") or _PERMIT_DURATIONS.get(permit_type)
        if duration is None:
            raise ValueError(f"Unsupported permit type: {permit_type}")

        region_key = _resolve_region_key(region, rules)
        base_business_days = float(duration.get(region_key, duration["default"]))

        multipliers = dict(_DEFAULT_MULTIPLIERS)
        multipliers.update(rules.get("duration_multipliers") or {})
        applied_multiplier = 1.0

        if building_area_sqm >= float(multipliers["very_large_site_threshold_sqm"]):
            applied_multiplier *= float(multipliers["very_large_site_multiplier"])
        elif building_area_sqm >= float(multipliers["large_site_threshold_sqm"]):
            applied_multiplier *= float(multipliers["large_site_multiplier"])

        if is_public:
            applied_multiplier *= float(multipliers["public_project_multiplier"])
        if is_agricultural:
            applied_multiplier *= float(multipliers["agricultural_multiplier"])

        business_days = max(1, int(round(base_business_days * applied_multiplier)))
        return {
            "business_days": business_days,
            "calendar_days": int(round(business_days * 1.4)),
            "base_business_days": base_business_days,
            "region_key": region_key,
            "applied_multiplier": round(applied_multiplier, 4),
        }

    @staticmethod
    def _submission_reference(project_id: UUID) -> str:
        return f"SEUMTER-{datetime.now(UTC):%Y%m%d}-{str(project_id)[:8]}-{uuid4().hex[:6].upper()}"

    @staticmethod
    def _progress(stage: str) -> float:
        rules = _load_dynamic_rules()
        stages = list(rules.get("stages") or _PERMIT_STAGES)
        try:
            index = stages.index(stage) + 1
        except ValueError:
            index = 1
        return round(index / max(len(stages), 1) * 100.0, 1)

    @classmethod
    def _serialize(cls, submission: PermitSubmission) -> dict:
        validation = dict(submission.validation_summary_json or {})
        duration = dict(submission.duration_summary_json or {})
        return {
            "submission_id": submission.id,
            "project_id": submission.project_id,
            "permit_type": submission.permit_type,
            "region": submission.region,
            "submission_reference": submission.submission_reference,
            "status": submission.status,
            "current_stage": submission.current_stage,
            "progress_pct": cls._progress(submission.current_stage),
            "readiness_score": submission.readiness_score,
            "estimated_business_days": int(duration.get("business_days", 0)),
            "estimated_calendar_days": int(duration.get("calendar_days", 0)),
            "missing_required_documents": list(validation.get("missing_required_documents", [])),
            "checklist": list(submission.checklist_json or []),
            "summary": (
                f"{submission.permit_type} is {submission.status} with readiness "
                f"{submission.readiness_score:.1f}% in {submission.region}."
            ),
            "submitted_at": submission.submitted_at,
            "created_at": submission.created_at,
        }

    async def submit(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        permit_type: str,
        region: str,
        building_area_sqm: float,
        is_public: bool,
        is_agricultural: bool,
        applicant_name: str | None,
        submit_to_seumter: bool,
        submitted_document_ids: list[str],
    ) -> dict:
        checklist = self._build_checklist(
            permit_type=permit_type,
            building_area_sqm=building_area_sqm,
            is_public=is_public,
            is_agricultural=is_agricultural,
            submitted_document_ids=submitted_document_ids,
        )
        validation = self._validate_checklist(checklist)
        duration = self._estimate_duration_contextual(
            permit_type=permit_type,
            region=region,
            building_area_sqm=building_area_sqm,
            is_public=is_public,
            is_agricultural=is_agricultural,
        )

        should_submit = submit_to_seumter and validation["is_ready"]
        status = "submitted" if should_submit else "draft"
        current_stage = "submitted" if should_submit else "document-prep"
        submitted_at = datetime.now(UTC) if should_submit else None

        submission = PermitSubmission(
            tenant_id=tenant_id,
            project_id=project_id,
            permit_type=permit_type,
            region=region,
            applicant_name=applicant_name,
            submission_reference=self._submission_reference(project_id),
            status=status,
            current_stage=current_stage,
            building_area_sqm=building_area_sqm,
            is_public=is_public,
            is_agricultural=is_agricultural,
            submit_to_seumter=submit_to_seumter,
            readiness_score=validation["readiness_score"],
            checklist_json=checklist,
            validation_summary_json=validation,
            duration_summary_json=duration,
            submitted_documents_json=submitted_document_ids,
            submitted_at=submitted_at,
            last_checked_at=datetime.now(UTC),
        )
        self.db.add(submission)
        await self.db.commit()
        await self.db.refresh(submission)
        return self._serialize(submission)

    async def get_latest(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
    ) -> dict | None:
        result = await self.db.execute(
            select(PermitSubmission)
            .where(
                PermitSubmission.tenant_id == tenant_id,
                PermitSubmission.project_id == project_id,
            )
            .order_by(PermitSubmission.created_at.desc())
            .limit(1)
        )
        submission = result.scalar_one_or_none()
        if submission is None:
            return None
        return self._serialize(submission)

    async def get_status(
        self,
        *,
        tenant_id: UUID,
        submission_id: UUID,
    ) -> dict | None:
        result = await self.db.execute(
            select(PermitSubmission).where(
                PermitSubmission.tenant_id == tenant_id,
                PermitSubmission.id == submission_id,
            )
        )
        submission = result.scalar_one_or_none()
        if submission is None:
            return None
        submission.last_checked_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(submission)
        return self._serialize(submission)
