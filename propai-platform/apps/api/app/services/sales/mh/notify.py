"""데스크 알림 — FCM 앱푸시 + 카카오 알림톡 + 단체톡(WebSocket). 키 미설정 시 graceful skip.

모든 발송은 MhNotification 에 채널별 상태(SENT/SKIPPED/FAILED)로 기록한다.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config_sales import sales_settings
from apps.api.database.models.sales.commission_mh_harness import MhDesk, MhNotification, MhVisitor
from apps.api.database.models.sales.staff import SalesStaff, SalesStaffPhoneIndex
from app.services.sales.mh.ws import ws_manager


def _mask(name: str | None, policy: dict | None) -> str:
    if not name:
        return "방문객"
    if policy and policy.get("mask_visitor_name"):
        return name[0] + "*" * (len(name) - 1)
    return name


async def notify_designated(db: AsyncSession, site_id, visitor_id, staff_id, masking_policy=None):
    v = (await db.execute(select(MhVisitor).where(MhVisitor.id == visitor_id))).scalar_one()
    staff = (await db.execute(select(SalesStaff).where(SalesStaff.id == staff_id))).scalar_one()
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
               sent_at=datetime.now(timezone.utc)))
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
        except Exception:  # noqa: BLE001
            status = "FAILED"
    db.add(MhNotification(site_id=site_id, visitor_id=visitor_id, target_staff_id=staff.id,
           channel="PUSH", payload={"title": title, "body": body}, status=status,
           sent_at=datetime.now(timezone.utc)))


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
        except Exception:  # noqa: BLE001
            status = "FAILED"
    else:
        status = "SKIPPED"
    db.add(MhNotification(site_id=site_id, visitor_id=visitor_id, target_staff_id=staff.id,
           channel="ALIMTALK", payload={"to": phone}, status=status,
           sent_at=datetime.now(timezone.utc)))
