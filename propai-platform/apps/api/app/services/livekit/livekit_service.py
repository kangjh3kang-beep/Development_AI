"""LiveKit 화상회의 — 토큰 발급 + 녹화(Egress→S3) 서비스.

설정(LIVEKIT_URL/API_KEY/API_SECRET)은 settings(env)에서 읽는다. 미설정 시 RuntimeError를 올려
라우터가 503으로 정직 degrade(크래시 금지). 권한(VideoGrant)은 livekit_rules.video_grant 결정론
규칙을 그대로 사용한다. Egress 실연결은 LiveKit Cloud + S3 자격증명 필요 — 스테이징 검증 대상.
"""

from __future__ import annotations

import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


def _conf() -> tuple[str, str, str]:
    s = get_settings()
    return (
        getattr(s, "LIVEKIT_URL", "") or "",
        getattr(s, "LIVEKIT_API_KEY", "") or "",
        getattr(s, "LIVEKIT_API_SECRET", "") or "",
    )


def is_configured() -> bool:
    """토큰 발급 가능 여부 — URL/KEY/SECRET 모두 설정됐을 때만."""
    url, key, secret = _conf()
    return bool(url and key and secret)


def livekit_url() -> str:
    return _conf()[0]


def issue_access_token(identity: str, display_name: str, grant: dict) -> str:
    """LiveKit AccessToken(JWT) 발급 — grant는 livekit_rules.video_grant 결과. 미설정 시 RuntimeError."""
    _, key, secret = _conf()
    if not (key and secret):
        raise RuntimeError("LiveKit 미설정(LIVEKIT_API_KEY/SECRET)")
    from livekit import api  # 지연 임포트(미설치/미설정 환경 보호)

    token = (
        api.AccessToken(key, secret)
        .with_identity(identity)
        .with_name(display_name or identity)
        .with_grants(
            api.VideoGrants(
                room_join=bool(grant.get("room_join")),
                room=str(grant.get("room") or ""),
                can_publish=bool(grant.get("can_publish")),
                can_publish_data=bool(grant.get("can_publish_data")),
                can_subscribe=bool(grant.get("can_subscribe")),
                room_admin=bool(grant.get("room_admin")),
            )
        )
    )
    return token.to_jwt()


def _egress_s3() -> dict:
    s = get_settings()
    return {
        "bucket": getattr(s, "LIVEKIT_EGRESS_S3_BUCKET", "") or "",
        "region": getattr(s, "LIVEKIT_EGRESS_S3_REGION", "") or "",
        "access_key": getattr(s, "LIVEKIT_EGRESS_S3_ACCESS_KEY", "") or "",
        "secret": getattr(s, "LIVEKIT_EGRESS_S3_SECRET", "") or "",
    }


def egress_configured() -> bool:
    s3 = _egress_s3()
    return is_configured() and bool(s3["bucket"] and s3["access_key"] and s3["secret"])


async def start_room_recording(room: str) -> dict:
    """룸 합성 녹화(Egress) 시작 → {egress_id, s3_key}. 미설정 시 RuntimeError.

    스테이징 검증 대상(LiveKit Cloud + S3 필요). 예외는 호출측(라우터)이 503/failed로 정직 표기.
    """
    url, key, secret = _conf()
    s3 = _egress_s3()
    if not (egress_configured()):
        raise RuntimeError("LiveKit 녹화 미설정(LIVEKIT_URL/KEY/SECRET + Egress S3)")
    from livekit import api

    s3_key = f"recordings/{room}.mp4"
    lkapi = api.LiveKitAPI(url, key, secret)
    try:
        req = api.RoomCompositeEgressRequest(
            room_name=room,
            file_outputs=[
                api.EncodedFileOutput(
                    file_type=api.EncodedFileType.MP4,
                    filepath=s3_key,
                    s3=api.S3Upload(
                        access_key=s3["access_key"],
                        secret=s3["secret"],
                        bucket=s3["bucket"],
                        region=s3["region"],
                    ),
                )
            ],
        )
        info = await lkapi.egress.start_room_composite_egress(req)
        return {"egress_id": getattr(info, "egress_id", "") or "", "s3_key": s3_key}
    finally:
        await lkapi.aclose()


async def stop_recording(egress_id: str) -> None:
    """Egress 중지. 미설정 시 RuntimeError. 스테이징 검증 대상."""
    url, key, secret = _conf()
    if not is_configured():
        raise RuntimeError("LiveKit 미설정")
    from livekit import api

    lkapi = api.LiveKitAPI(url, key, secret)
    try:
        await lkapi.egress.stop_egress(api.StopEgressRequest(egress_id=egress_id))
    finally:
        await lkapi.aclose()
