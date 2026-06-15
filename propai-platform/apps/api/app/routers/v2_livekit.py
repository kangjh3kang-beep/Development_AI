"""LiveKit 화상회의 API — 룸 토큰 발급 + 녹화(Egress) 시작/중지.

접근제어는 require_project_member(멤버십 1차). 권한(VideoGrant·녹화)은 livekit_rules 결정론 규칙.
LiveKit 미설정 시 503 정직 degrade(크래시 금지). 녹화는 host(owner/manager)만.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_collaboration import require_project_member
from app.core.database import get_db
from app.models.collaboration import PROJECT_ROLES
from app.models.livekit import Recording
from app.schemas.livekit import LiveKitTokenOut, RecordingOut
from app.services.auth.auth_service import get_current_user
from app.services.livekit import livekit_service
from app.services.livekit.livekit_rules import can_record, room_name, video_grant

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v2/livekit", tags=["livekit"])

_require_member = require_project_member(*PROJECT_ROLES)


def _recording_out(r: Recording) -> RecordingOut:
    return RecordingOut(
        id=str(r.id),
        project_id=str(r.project_id),
        room=r.room,
        status=r.status,
        egress_id=getattr(r, "egress_id", None),
        s3_key=getattr(r, "s3_key", None),
        started_at=getattr(r, "started_at", None),
        ended_at=getattr(r, "ended_at", None),
    )


@router.post("/projects/{project_id}/rooms/{room_key}/token", response_model=LiveKitTokenOut)
async def get_room_token(
    project_id: str,
    room_key: str,
    member=Depends(_require_member),
    user=Depends(get_current_user),
):
    """룸 입장 토큰 발급 — 활성 멤버. 역할별 VideoGrant(host=roomAdmin, viewer=구독만). 미설정 503."""
    if not livekit_service.is_configured():
        raise HTTPException(status_code=503, detail="화상회의(LiveKit)가 구성되지 않았습니다.")
    room = room_name(project_id, room_key)
    grant = video_grant(member.project_role, room)
    display = getattr(user, "name", None) or getattr(user, "email", None) or str(user.id)
    try:
        token = livekit_service.issue_access_token(str(user.id), str(display), grant)
    except RuntimeError as exc:
        logger.warning("livekit_token_failed", error=str(exc))
        raise HTTPException(status_code=503, detail="화상회의 토큰 발급 실패(구성 확인).") from exc
    return LiveKitTokenOut(
        url=livekit_service.livekit_url(),
        token=token,
        room=room,
        can_publish=grant["can_publish"],
        can_record=can_record(member.project_role),
    )


@router.post("/projects/{project_id}/rooms/{room_key}/recording/start", response_model=RecordingOut)
async def start_recording(
    project_id: str,
    room_key: str,
    member=Depends(_require_member),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """녹화 시작 — host(owner/manager)만. 미설정 503. 실 Egress는 스테이징 검증 대상."""
    if not can_record(member.project_role):
        raise HTTPException(status_code=403, detail="녹화는 관리자(owner/manager)만 가능합니다.")
    if not livekit_service.egress_configured():
        raise HTTPException(status_code=503, detail="화상회의 녹화(Egress/S3)가 구성되지 않았습니다.")
    room = room_name(project_id, room_key)
    try:
        result = await livekit_service.start_room_recording(room)
    except RuntimeError as exc:
        logger.warning("livekit_egress_start_failed", error=str(exc))
        raise HTTPException(status_code=503, detail="녹화 시작 실패(구성 확인).") from exc

    rec = Recording(
        project_id=uuid.UUID(project_id),
        organization_id=member.organization_id,
        room=room,
        egress_id=result.get("egress_id") or None,
        s3_key=result.get("s3_key") or None,
        status="recording",
        started_by=user.id,
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return _recording_out(rec)


@router.post("/projects/{project_id}/recording/{recording_id}/stop", response_model=RecordingOut)
async def stop_recording(
    project_id: str,
    recording_id: str,
    member=Depends(_require_member),
    db: AsyncSession = Depends(get_db),
):
    """녹화 중지 — host만. Egress 중지 + 메타 completed. 미설정/없음은 정직 처리."""
    if not can_record(member.project_role):
        raise HTTPException(status_code=403, detail="녹화는 관리자(owner/manager)만 가능합니다.")
    try:
        did = uuid.UUID(recording_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail="녹화를 찾을 수 없습니다") from exc

    rec = (
        await db.execute(select(Recording).where(Recording.id == did))
    ).scalar_one_or_none()
    if rec is None or str(rec.project_id) != str(uuid.UUID(project_id)):
        raise HTTPException(status_code=404, detail="녹화를 찾을 수 없습니다")

    try:
        if rec.egress_id:
            await livekit_service.stop_recording(rec.egress_id)
    except RuntimeError as exc:
        logger.warning("livekit_egress_stop_failed", error=str(exc))  # 메타는 닫되 정직 경고

    rec.status = "completed"
    rec.ended_at = datetime.utcnow()
    await db.commit()
    await db.refresh(rec)
    return _recording_out(rec)
