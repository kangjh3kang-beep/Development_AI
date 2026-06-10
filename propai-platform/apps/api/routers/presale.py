"""분양·청약 정보 API.

공개(인증 불필요 — 공공데이터 열람):
  GET  /presale/areas                  — 시도 목록(탭)
  GET  /presale/list                   — 전국/시도별 분양 공고 목록
  GET  /presale/detail                 — 단지 상세 + 주택형별 분양가
  POST /presale/nearby                 — 관심지역/반경 내 분양 단지(지도)

인증(로그인 사용자):
  GET/POST/DELETE /presale/interests   — 관심지역 모니터링 등록·삭제
  POST /presale/monitor/run-now        — 내 관심지역 즉시 점검(수동)
  GET  /presale/monitor/summary        — 코인패널 배지(미확인·특이점 수)
  GET  /presale/monitor/feed           — 분류된 모니터링 알림 피드
  POST /presale/monitor/read           — 알림 읽음 처리
  GET/PUT /presale/notify/prefs        — 알림 설정(전화번호·SMS·알림톡)
  POST /presale/notify/test            — 알림 발송 테스트
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.database.session import get_db
from apps.api.app.services.land_intelligence.presale_service import PresaleService, AREA_LIST, area_from_lawd
from apps.api.app.services.land_intelligence import presale_monitor_service as monitor
from app.services.notification import notification_service as notif

router = APIRouter(prefix="/api/v1/presale", tags=["분양정보"])


# ── 공개 열람 ──
@router.get("/areas")
async def areas():
    return {"areas": AREA_LIST}


@router.get("/list")
async def presale_list(area: str | None = Query(None), months_back: int = Query(6, ge=1, le=24)):
    """전국(area 미지정) 또는 시도별 분양 공고 목록."""
    return await PresaleService().list_announcements(area=area, months_back=months_back)


@router.get("/detail")
async def presale_detail(house_manage_no: str = Query(...), pblanc_no: str = Query("")):
    """단지 상세 + 주택형별 분양가(최저~최고)."""
    return await PresaleService().detail(house_manage_no, pblanc_no)


class NearbyReq(BaseModel):
    lat: float | None = None
    lon: float | None = None
    area: str | None = None
    lawd_cd: str | None = None   # 있으면 시도 자동 도출
    radius_m: int = 3000
    months_back: int = 12


@router.post("/nearby")
async def presale_nearby(req: NearbyReq):
    """중심좌표 반경 내 분양 단지(지도 '분양' 카테고리)."""
    area = req.area or (area_from_lawd(req.lawd_cd) if req.lawd_cd else None)
    return await PresaleService().nearby(
        center_lat=req.lat, center_lon=req.lon, area=area,
        radius_m=req.radius_m, months_back=req.months_back,
    )


# ── 관심지역 모니터링(인증) ──
class InterestReq(BaseModel):
    label: str
    area: str | None = None
    sigungu: str | None = None
    keyword: str | None = None
    min_households: int = 0


@router.get("/interests")
async def list_interests(current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {"interests": await monitor.list_interests(db, current.user_id)}


@router.post("/interests")
async def add_interest(req: InterestReq, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await monitor.add_interest(db, current.user_id, req.label, req.area, req.sigungu,
                                     req.keyword, req.min_households)
    # 등록 직후 베이스라인 1회 즉시 수행(현재 매칭 건수 요약 알림).
    try:
        interests = await monitor.list_interests(db, current.user_id)
        target = next((i for i in interests if i["id"] == res["id"]), None)
        if target:
            await monitor.check_interest(db, {**target, "user_id": str(current.user_id)})
    except Exception:  # noqa: BLE001
        pass
    return res


@router.delete("/interests/{interest_id}")
async def remove_interest(interest_id: str, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await monitor.remove_interest(db, current.user_id, interest_id)


@router.post("/monitor/run-now")
async def run_now(current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """내 관심지역만 즉시 점검(신규·접수시작·마감임박 알림 생성)."""
    interests = await monitor.list_interests(db, current.user_id)
    svc = PresaleService()
    events = 0
    for it in interests:
        try:
            res = await monitor.check_interest(db, {**it, "user_id": str(current.user_id)}, svc)
            events += res.get("events", 0)
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "checked": len(interests), "events": events}


@router.get("/monitor/summary")
async def monitor_summary(current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """코인·충전잔액 패널 배지용 — 미확인 분양 알림 수 + 최신 1건."""
    count = await notif.unread_count(db, current.user_id, category="presale")
    latest = await notif.list_inapp(db, current.user_id, unread_only=False, limit=1)
    return {"unread": count, "latest": latest[0] if latest else None}


@router.get("/monitor/feed")
async def monitor_feed(unread_only: bool = False, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """분류된 모니터링 알림 피드(category=presale)."""
    rows = await notif.list_inapp(db, current.user_id, unread_only=unread_only, limit=80)
    return {"items": [r for r in rows if r["category"] == "presale"]}


class ReadReq(BaseModel):
    ids: list[str] | None = None


@router.post("/monitor/read")
async def monitor_read(req: ReadReq, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await notif.mark_read(db, current.user_id, req.ids)


# ── 알림 설정(인증) ──
class PrefsReq(BaseModel):
    phone: str = ""
    sms_enabled: bool = False
    kakao_enabled: bool = False
    inapp_enabled: bool = True


@router.get("/notify/prefs")
async def get_prefs(current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await notif.get_prefs(db, current.user_id)


@router.put("/notify/prefs")
async def set_prefs(req: PrefsReq, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await notif.set_prefs(db, current.user_id, req.phone, req.sms_enabled,
                                 req.kakao_enabled, req.inapp_enabled)


@router.post("/notify/test")
async def notify_test(current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """현재 설정으로 테스트 알림 발송(인앱 + 가능 시 SMS/알림톡)."""
    return await notif.notify(
        db, current.user_id, title="알림 테스트",
        body="사통팔땅 분양정보 알림이 정상 설정되었습니다.",
        category="presale", payload={"kind": "test"},
    )
