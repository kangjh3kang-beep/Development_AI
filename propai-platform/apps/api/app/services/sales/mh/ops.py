"""데스크 운영 — 방문통계/물품수불/출퇴근."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.sales.contract.service import NotFoundError
from apps.api.database.models.sales.commission_mh_harness import MhInventoryItem, MhInventoryTxn, MhVisitor
from apps.api.database.models.sales.staff import SalesStaffAttendance


async def visit_stats(db: AsyncSession, site_id, since, until):
    rows = (await db.execute(
        select(func.date_trunc("hour", MhVisitor.checked_in_at).label("h"), func.count().label("c"))
        .where(MhVisitor.site_id == site_id, MhVisitor.checked_in_at.between(since, until))
        .group_by("h").order_by("h"))).all()
    return [{"hour": r.h.isoformat(), "visitors": r.c} for r in rows]


async def inventory_txn(db: AsyncSession, site_id, item_id, txn_type, qty, staff_id=None, memo=None):
    # ★[전역스윕·미존재 item NoResultFound→500 차단·iter-3 HIGH] 과거엔 scalar_one() 이라
    #   미등록 item_id 가 NoResultFound→전역핸들러 HTTP500 으로 누출됐다(재고 부족 ValueError 는
    #   엔드포인트가 잡지만, '없는 품목' 은 그 앞에서 터져 트랜잭션도 정리 안 됐다). cancel_contract
    #   와 동일하게 scalar_one_or_none() 으로 받고 미존재면 명시 ValueError(엔드포인트가 404 로 매핑).
    # ★[IDOR·security 교차테넌트 write·iter-5 HIGH] 과거엔 WHERE id==item_id 만이라 site_id 스코프가
    #   없었다 → A현장 사용자가 B현장 item_id 를 넘기면 타현장 재고(stock_qty)를 증감(교차테넌트
    #   write IDOR)할 수 있었다. MhInventoryItem 은 site_id 를 가지고 데스크 엔드포인트(desk_inv)는
    #   ctx.site_id 를 보유하므로, SELECT WHERE 에 site_id 를 더해 타현장 품목 조작을 차단한다.
    #   스코프 밖이면 '미존재'와 동일하게 NotFoundError(=404)로 본다(타현장 품목 존재 누설 금지).
    item = (await db.execute(select(MhInventoryItem).where(
        MhInventoryItem.id == item_id,
        MhInventoryItem.site_id == site_id))).scalar_one_or_none()
    if item is None:
        # ★[전용 예외·iter-4] 미존재는 NotFoundError(ValueError 하위)로 코드화한다. 엔드포인트가
        #   한국어 문구 substring('찾을 수 없습니다') 대신 isinstance(NotFoundError)로 404 를 분기한다
        #   (문구 변경에도 404↔409 상태코드 불변). 재고 부족(상태충돌)은 일반 ValueError→409 그대로.
        raise NotFoundError("물품을 찾을 수 없습니다")
    # ★[MED·silent-fail 제거·iter-6] 과거엔 delta = qty if txn_type=='IN' else -qty 라,
    #   'IN' 이 아닌 '모든' 값(오타 'in'/'OUTT'/빈문자/None)이 조용히 출고(-qty)로 처리됐다 —
    #   오타 하나가 입고 의도를 재고 차감으로 뒤집는 silent-fail. txn_type 을 {'IN','OUT'} 만
    #   허용하고, 그 외 값은 ValueError 로 거부한다(엔드포인트가 400 으로 매핑 — 은폐 금지).
    if txn_type not in ("IN", "OUT"):
        raise ValueError("txn_type은 IN 또는 OUT 이어야 합니다.")
    delta = qty if txn_type == "IN" else -qty
    if item.stock_qty is not None and item.stock_qty + delta < 0:
        raise ValueError("재고 부족")
    item.stock_qty = (item.stock_qty or 0) + delta
    # [backlog·iter-6] MhInventoryTxn 에는 site_id 컬럼이 없다 — 현재는 FK(item_id)가 item.site_id
    #   스코프 안에 있어 현장 격리는 보장되므로(item 조회를 site_id 로 스코프) 그대로 둔다. 추후 수불
    #   원장을 site_id 로 직접 질의·집계하려면 컬럼 추가(마이그레이션)를 검토(여기선 추가구현 금지).
    db.add(MhInventoryTxn(item_id=item_id, txn_type=txn_type, qty=qty, staff_id=staff_id, memo=memo))
    await db.flush()
    return item.stock_qty


async def attendance_check(db: AsyncSession, site_id, staff_id, kind, lat=None, lng=None):
    if kind == "IN":
        a = SalesStaffAttendance(site_id=site_id, staff_id=staff_id, check_in=datetime.now(UTC),
                                 method="QR", geo=(f"POINT({lng} {lat})" if lat and lng else None))
        db.add(a)
        await db.flush()
        return a
    a = (await db.execute(select(SalesStaffAttendance).where(
        SalesStaffAttendance.staff_id == staff_id, SalesStaffAttendance.check_out.is_(None))
        .order_by(SalesStaffAttendance.check_in.desc()).limit(1))).scalar_one_or_none()
    if a:
        a.check_out = datetime.now(UTC)
        a.work_minutes = int((a.check_out - a.check_in).total_seconds() // 60)
    await db.flush()
    return a
