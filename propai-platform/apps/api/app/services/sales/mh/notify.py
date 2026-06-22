"""데스크 알림 — FCM 앱푸시 + 카카오 알림톡 + 단체톡(WebSocket). 키 미설정 시 graceful skip.

모든 발송은 MhNotification 에 채널별 상태(SENT/SKIPPED/FAILED)로 기록한다.
발송 실패(FAILED)는 DB 이력에 남길 뿐 아니라 사유를 분류 로깅한다 — 조용히 묻히면(silent-drop)
운영자가 키 만료·외부 장애를 알 길이 없어 지명 방문객 알림이 통째로 누락될 수 있기 때문이다.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config_sales import sales_settings
from app.services.sales.mh.ws import ws_manager
from apps.api.database.models.sales.commission_mh_harness import MhDesk, MhNotification, MhVisitor
from apps.api.database.models.sales.staff import SalesStaff, SalesStaffPhoneIndex

logger = logging.getLogger(__name__)


def _mask(name: str | None, policy: dict | None) -> str:
    if not name:
        return "방문객"
    if policy and policy.get("mask_visitor_name"):
        return name[0] + "*" * (len(name) - 1)
    return name


async def notify_designated(db: AsyncSession, site_id, visitor_id, staff_id, masking_policy=None):
    # ★[graceful·silent-fail 제거] 방문객/담당자를 scalar_one() 으로 잡으면 행이 없을 때 NoResultFound 가
    #   터져 알림 흐름 전체가 미가공 예외로 중단된다(데스크 운영 단절). scalar_one_or_none() + 분류 로깅으로
    #   '왜 알림을 못 보냈는지'를 남기고 흐름을 안전히 종료한다(0/빈값 은폐 아님 — 원인 기록 후 정상 반환).
    v = (await db.execute(select(MhVisitor).where(MhVisitor.id == visitor_id))).scalar_one_or_none()
    staff = (await db.execute(select(SalesStaff).where(SalesStaff.id == staff_id))).scalar_one_or_none()
    if v is None or staff is None:
        logger.warning("지명 알림 스킵: 대상 미존재(visitor=%s found=%s, staff=%s found=%s)",
                       str(visitor_id), v is not None, str(staff_id), staff is not None)
        return
    desk = (await db.execute(select(MhDesk).where(MhDesk.id == v.desk_id))).scalar_one_or_none()
    disp = _mask(v.name, masking_policy)
    title = "지명 방문객 도착"
    body = f"{disp}님이 {desk.desk_name if desk else '데스크'}에 방문하셨습니다."

    await _send_fcm(db, staff, title, body, site_id, visitor_id)
    if sales_settings.kakao_biz_key:
        await _send_alimtalk(db, site_id, visitor_id, staff, body)
    if desk and desk.channel_id:
        await ws_manager.broadcast(desk.channel_id,
                                   {"type": "DESIGNATED_VISITOR", "visitor": disp, "staff": staff.name})
        db.add(MhNotification(site_id=site_id, visitor_id=visitor_id, target_staff_id=staff_id,
               channel="GROUP", payload={"channel_id": desk.channel_id}, status="SENT",
               sent_at=datetime.now(UTC)))
    await db.flush()


async def _send_fcm(db, staff, title, body, site_id, visitor_id):
    token = (staff.register_meta or {}).get("fcm_token")
    status = "SKIPPED"
    if token and sales_settings.fcm_credentials_json:
        try:
            from firebase_admin import credentials, get_app, initialize_app, messaging
            try:
                get_app()
            except ValueError:
                initialize_app(credentials.Certificate(sales_settings.fcm_credentials_json))
            messaging.send(messaging.Message(
                notification=messaging.Notification(title=title, body=body), token=token))
            status = "SENT"
        except Exception as exc:  # noqa: BLE001
            # ★[silent-fail 제거] FCM 발송 실패를 분류 로깅(키 만료·토큰 무효·네트워크 등). 발송흐름은
            #   막지 않고 status=FAILED 로 이력에 남기되, 사유를 운영자가 추적할 수 있게 남긴다.
            status = "FAILED"
            logger.warning("FCM 푸시 실패(staff=%s visitor=%s): %s",
                           str(staff.id), str(visitor_id), str(exc)[:200])
    db.add(MhNotification(site_id=site_id, visitor_id=visitor_id, target_staff_id=staff.id,
           channel="PUSH", payload={"title": title, "body": body}, status=status,
           sent_at=datetime.now(UTC)))


async def _send_alimtalk(db, site_id, visitor_id, staff, body):
    status = "SENT"
    pi = (await db.execute(select(SalesStaffPhoneIndex).where(
        SalesStaffPhoneIndex.staff_id == staff.id).limit(1))).scalar_one_or_none()
    phone = pi.phone_e164 if pi else None
    if phone:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as cli:
                await cli.post("https://kakaoapi.example/v2/sender/send",
                    headers={"Authorization": f"Bearer {sales_settings.kakao_biz_key}"},
                    json={"senderKey": sales_settings.kakao_sender_key, "to": phone,
                          "templateCode": "DESK_DESIGNATED", "text": body})
        except Exception as exc:  # noqa: BLE001
            # ★[silent-fail 제거] 알림톡 발송 실패를 분류 로깅(외부 게이트웨이 장애·키 만료 등).
            status = "FAILED"
            logger.warning("알림톡 발송 실패(staff=%s visitor=%s): %s",
                           str(staff.id), str(visitor_id), str(exc)[:200])
    else:
        status = "SKIPPED"
    db.add(MhNotification(site_id=site_id, visitor_id=visitor_id, target_staff_id=staff.id,
           channel="ALIMTALK", payload={"to": phone}, status=status,
           sent_at=datetime.now(UTC)))
