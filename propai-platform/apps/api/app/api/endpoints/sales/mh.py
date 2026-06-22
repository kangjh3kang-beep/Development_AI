"""모델하우스 데스크 라우터 (sales_router 하위 /mh)."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.deps_sales import SalesCtx, sales_ctx
from app.services.sales.contract.service import NotFoundError
from app.services.sales.mh.checkin import checkin
from app.services.sales.mh.consent import template as consent_template
from app.services.sales.mh.match import match_staff
from app.services.sales.mh.notify import notify_designated
from app.services.sales.mh.ops import attendance_check, inventory_txn, visit_stats
from apps.api.database.models.sales.site_org import SalesSiteConfig

mh_router = APIRouter(prefix="/mh", tags=["model-house"])


def _client_ip(request: Request) -> str | None:
    """동의 IP(고지이력). 프록시 환경은 X-Forwarded-For 첫 IP 우선."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None


@mh_router.get("/consent-template")
async def desk_consent_template(_ctx: SalesCtx = Depends(sales_ctx)):
    """방문객 동의 고지문(수집항목·이용목적·보유기간 + 필수/선택 분리). 동의팝업이 렌더."""
    return consent_template()


@mh_router.post("/visitors/checkin")
async def desk_checkin(body: dict, request: Request, db: AsyncSession = Depends(get_db),
                       ctx: SalesCtx = Depends(sales_ctx)):
    v = await checkin(db, ctx.site_id, body.get("desk_id"), body, consent_ip=_client_ip(request))
    # MGM 추천코드 경유 방문이면(랜딩 ?ref=code 가 전달됨) visit 퍼널 이벤트를 무파괴로 기록.
    # 유효하지 않은 코드는 record_event 가 조용히 무시 → 체크인 본흐름을 막지 않는다.
    ref = body.get("ref")
    if ref:
        from app.api.endpoints.sales.referral import record_event  # 지연 import(순환 방지)
        await record_event(db, str(ref), "visit", visitor_ref=str(v.id), customer_id=None)
    await db.commit()
    return {"visitor_id": str(v.id)}


@mh_router.post("/match")
async def desk_match(body: dict, db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    res = await match_staff(db, ctx.site_id, uuid.UUID(body["visitor_id"]), body["input_type"], body["raw"])
    await db.commit()
    return res


@mh_router.post("/notify")
async def desk_notify(body: dict, db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    cfg = (await db.execute(select(SalesSiteConfig).where(SalesSiteConfig.site_id == ctx.site_id))).scalar_one_or_none()
    await notify_designated(db, ctx.site_id, uuid.UUID(body["visitor_id"]), uuid.UUID(body["staff_id"]),
                            masking_policy=(cfg.masking_policy if cfg else None))
    await db.commit()
    return {"ok": True}


@mh_router.get("/stats")
async def desk_stats(hours: int = 24, db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    until = datetime.now(UTC)
    since = until - timedelta(hours=hours)
    return await visit_stats(db, ctx.site_id, since, until)


@mh_router.post("/inventory/txn")
async def desk_inv(body: dict, db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    # ★[전역스윕·ValueError→409] inventory_txn 은 재고가 음수가 되는 출고를 ValueError('재고 부족')로
    #   거부한다(정상적인 업무 거부). 과거엔 try/except 가 없어 이 거부가 전역 핸들러 HTTP500 으로
    #   은폐돼 친화 메시지가 안 닿고 트랜잭션이 정리되지 않았다. item_id/qty 형식오류는 400,
    #   재고 부족(상태충돌)은 409+rollback 으로 매핑한다(lifecycle_p5 청약 엔드포인트와 동일 규약).
    try:
        item_id = uuid.UUID(str(body["item_id"]))
        txn_type = body["txn_type"]
        qty = int(body["qty"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(400, "item_id(UUID)·txn_type·qty(정수)가 필요합니다.") from None
    # ★[MED·입력검증·iter-6] txn_type 화이트리스트를 엔드포인트에서 1차로 강제한다(잘못된 값=400,
    #   클라이언트 입력문제). 과거엔 'IN' 외 모든 값이 ops.inventory_txn 에서 조용히 출고로 처리됐다.
    #   서비스 계층(ops.py)에도 동일 가드를 둬 이중방어(다른 호출자도 보호)하되, 엔드포인트에선
    #   400 으로 매핑해 상태충돌(409)과 구분한다(은폐 금지).
    if txn_type not in ("IN", "OUT"):
        raise HTTPException(400, "txn_type은 IN(입고) 또는 OUT(출고) 이어야 합니다.")
    # ★[전역스윕·미존재 item 404·iter-3 HIGH] inventory_txn 은 이제 미등록 item_id 에서
    #   scalar_one() 의 NoResultFound→500 대신 NotFoundError 를 던진다.
    #   미존재(찾을 수 없음)는 404, 그 외(재고 부족 등 상태충돌)는 409 로 분리 매핑한다
    #   (cancel_contract 미존재 404 매핑과 대칭).
    # ★[anti-pattern 제거·iter-4] 과거엔 한국어 문구 substring('찾을 수 없습니다' in str(e))으로
    #   404↔409 를 갈라, 문구 한 글자만 바뀌어도 상태코드가 조용히 흔들렸다. 전용 예외
    #   isinstance 분기(NotFoundError)로 코드화해 문구와 무관하게 404 불변으로 만든다.
    # ★[IDOR·security 교차테넌트 write·iter-5 HIGH] 호출자 현장(ctx.site_id)을 inventory_txn 에
    #   전달해 SELECT 를 site_id 로 스코프하게 한다 → 타현장 item_id 로 남의 현장 재고를 증감하는
    #   교차테넌트 write IDOR 를 차단한다(미존재/타현장은 위 NotFoundError→404 분기로 정직 표기).
    try:
        stock = await inventory_txn(db, ctx.site_id, item_id, txn_type, qty,
                                    body.get("staff_id"), body.get("memo"))
    except NotFoundError as e:
        await db.rollback()
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        await db.rollback()
        raise HTTPException(409, str(e)) from e
    await db.commit()
    return {"stock_qty": stock}


@mh_router.post("/attendance/check")
async def desk_att(body: dict, db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    a = await attendance_check(db, ctx.site_id, uuid.UUID(body["staff_id"]), body["kind"],
                               body.get("lat"), body.get("lng"))
    await db.commit()
    return {"id": str(a.id) if a else None}
