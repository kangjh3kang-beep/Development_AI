"""계약 상태머신 — 서명(동호 CONTRACTED + 회차 자동생성 + 수수료 split + 투영),
취소(동호 CANCELLED + 변경 스냅샷 + 수수료 환수 + 투영). 1호 1계약은 동호 유니크로 보장.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.sales.commission.engine import clawback, split_commission
from app.services.sales.harness.outbox import emit_outbox
from apps.api.database.models.sales.commission_mh_harness import SalesCommissionEvent
from apps.api.database.models.sales.contract_crm_ad import (
    SalesContractChange,
    SalesContractExt,
    SalesContractInstallment,
)
from apps.api.database.models.sales.site_org import SalesSiteConfig
from apps.api.database.models.sales.units_pricing import SalesUnitInventory, SalesUnitStatusLog


class NotFoundError(ValueError):
    """리소스 미존재(계약·세대·물품 등) — 클라이언트가 없는 것을 지목한 경우 raise.

    ★응답계약 SSOT(iter-4): 과거엔 엔드포인트가 한국어 메시지 부분문자열
      ('찾을 수 없습니다' in str(e))로 404 ↔ 409 를 갈랐다(actions.cancel·mh.inventory_txn 등).
      문구가 한 글자만 바뀌어도 404 가 조용히 409 로 흔들리는 '상태코드 회귀' 위험이 있었다.
      commission/engine.CrossSiteOwnershipError(ValueError) 패턴과 동일하게, 미존재를 전용
      예외클래스로 코드화한다: 서비스가 NotFoundError 를 raise 하고, 엔드포인트는
      isinstance(e, NotFoundError) 로 404 를 분기한다(문구와 무관하게 상태코드 불변).
      ValueError 를 상속하므로 기존 'except ValueError' 경로와 하위호환된다(추가 import 없이
      그대로 409 로 떨어지던 곳도 의도대로 동작).
    """


async def _set_unit_status(db, unit_id, to_status, by=None, *, lock: bool = False):
    """세대(호실) 상태를 바꾸고 변경이력을 남긴다.

    lock=True 면 세대 행을 SELECT ... FOR UPDATE 로 잠근다. 두 사람이 같은 세대를 동시에
    계약/배정하려 할 때, 먼저 잠근 트랜잭션이 끝날 때까지 뒤 트랜잭션이 대기하게 해
    '같은 세대 이중계약'을 구조적으로 막는다(머니패스 동시성 핵심).
    """
    if not unit_id:
        return None
    stmt = select(SalesUnitInventory).where(SalesUnitInventory.id == unit_id)
    if lock:
        stmt = stmt.with_for_update()
    u = (await db.execute(stmt)).scalar_one()
    db.add(SalesUnitStatusLog(site_id=u.site_id, unit_id=unit_id, from_status=u.status, to_status=to_status, by=by))
    u.status = to_status
    await db.flush()
    return u


async def create_contract(db: AsyncSession, site_id, unit_id, customer_id=None, round_id=None,
                          total_price=None, member_node_id=None, by=None, hold_token=None):
    """계약 체결(최초 생성) — 세대 1호에 계약 1건을 만든다.

    이 함수가 없으면 '청약/세대 → 계약 → 수납/대출/전매'로 이어지는 전주기 흐름이 끊겨
    수납·대출·전매 화면의 계약 선택 목록이 항상 비게 된다(연결성 핵심).

    - total_price 미지정 시 해당 세대의 가격표(sales_unit_price_table)에서 자동으로 끌어온다.
    - 세대 상태를 RESERVED(예약)로 바꾸고, 다른 화면들이 곧바로 이 계약을 선택할 수 있게 한다.
    - member_node_id: 이 계약을 담당한 영업사원(조직도 노드). 이게 있어야 계약 체결 시
      수수료가 그 사원→상위 조직으로 배분된다(없으면 split이 빈 체인이라 아무도 수수료를 못 받음).
    - hold_token: FCFS 임시선점(atomic_hold)으로 본인이 잡아둔 HOLD 세대를 계약으로 전환할 때
      쓰는 선점 토큰. 본인(by)이 직접 잡은 경우는 토큰 없이도 통과하지만, 토큰을 넘기면
      held_by 대신 토큰 일치로도 소유권을 증명할 수 있다(아래 소유권 검증 참조).
    """
    from sqlalchemy import desc

    from apps.api.database.models.sales.units_pricing import SalesUnitPriceTable

    # ★동시성: 세대 행을 FOR UPDATE 로 잠근 뒤 상태를 확인한다. 잠그지 않으면 두 사람이
    #   동시에 같은 세대로 계약을 만들 때, 둘 다 'AVAILABLE'을 읽고 둘 다 통과해 이중계약이
    #   생긴다(읽고-나서-쓰기 사이의 race). FOR UPDATE 로 뒤 트랜잭션이 대기하게 하면,
    #   먼저 들어온 쪽이 RESERVED 로 바꾼 뒤 뒤 쪽은 갱신된 상태를 보고 막힌다.
    # ★[현장스코프 머니패스·iter-4 HIGH 전역스윕] 세대 행을 site_id 로 스코프한다. 스코프가 없으면
    #   A현장 사용자가 B현장 unit_id 를 넘겨 타현장 세대로 계약(점유=머니패스)을 만들 수 있다(IDOR).
    #   스코프 밖이면 '미존재'와 동일하게 NotFoundError(=404)로 본다(타현장 세대 존재를 누설하지 않음).
    unit = (await db.execute(select(SalesUnitInventory).where(
        SalesUnitInventory.id == unit_id,
        SalesUnitInventory.site_id == site_id).with_for_update())).scalar_one_or_none()
    if unit is None:
        raise NotFoundError("세대를 찾을 수 없습니다")
    # 1호 1계약: 계약을 만들 수 있는 세대 상태를 '허용목록(allowlist)'으로 제한한다(이중계약 차단).
    # ★[보강·iter-5] 과거엔 거부목록(denylist: RESERVED/APPLIED/CONTRACTED 거부) 방식이라, 장차
    #   새로운 점유 상태(예: HELD_BY_X, LOCKED 등)가 추가되면 그 상태가 거부목록에 빠져 'silent 계약
    #   허용'(이미 점유된 세대에 계약이 통과)이 되는 위험이 있었다. 허용목록으로 뒤집어, 명시적으로
    #   '분양 가능' 인 상태(AVAILABLE: 미점유, HOLD: 가청약/임시보류)에서만 계약을 허용한다. 새 점유
    #   상태가 생겨도 allowlist 에 추가하지 않는 한 자동 거부돼 안전하다(fail-closed). 취소돼 다시
    #   AVAILABLE 로 돌아온 세대는 재분양 허용(기존 거동 유지).
    if unit.status not in {"AVAILABLE", "HOLD"}:
        raise ValueError(f"이미 점유된 세대입니다(현재 상태={unit.status}). 재분양 가능한 세대만 계약할 수 있습니다.")

    # ★[보강·iter-7 HIGH security — HOLD 토큰 소유권 우회 차단(머니패스 점유탈취)] 위 allowlist 는
    #   HOLD 세대를 계약대상으로 열어주지만, '누가 그 HOLD 를 잡았는지'는 보지 않았다. FCFS 임시선점
    #   (units/concurrency.atomic_hold)은 held_by/hold_token/hold_expires_at 으로 본인 소유를 표시하는데,
    #   /contracts 경로는 FOR UPDATE 행잠금만 걸 뿐 그 소유권을 검증하지 않아, A직원이 임시선점한 세대를
    #   B직원이 RESERVED 계약으로 가로챌 수 있었다(머니패스 점유탈취). atomic_reserve(HOLD→CONTRACTED)와
    #   대칭이 되도록, '소유자가 있는 HOLD' 는 본인(by)이거나 토큰이 일치하고 미만료일 때만 계약을 허용한다.
    # ★정상경로 보존: 추첨 배정(draw_for_candidate)·동호지정대기(unit_action HOLD_REQUEST)는 HOLD 로 두되
    #   held_by 를 비워둔다(NULL). 즉 'held_by 가 NULL 인 HOLD' = 운영자가 배정·보류해둔 미점유 파킹상태이며
    #   FCFS 토큰 점유가 아니다 → 이 경로는 소유권 검증 없이 통과시켜 추첨배정→계약 흐름을 보존한다.
    #   (만료된 FCFS HOLD 는 expire_holds 배치가 AVAILABLE 로 되돌리므로, held_by 가 NULL 인데 남은
    #    'stale FCFS HOLD' 는 존재하지 않는다 — held_by 유무로 두 경로가 깨끗이 갈린다.)
    # ★held_by/hold_token/hold_expires_at 은 ORM 모델에 매핑돼 있지 않고(멱등 ALTER 로만 존재) now() 기준
    #   만료판정이 필요하므로, 이미 FOR UPDATE 로 잠근 같은 행을 raw SELECT 로 한 번 더 읽어 DB 의 now() 로
    #   소유권·만료를 판정한다(atomic_reserve 의 WHERE 조건과 동일 의미 — 잠긴 행이라 추가 경합 없음).
    if unit.status == "HOLD":
        own = (await db.execute(text(
            "SELECT held_by, hold_token, "
            "  (hold_expires_at IS NOT NULL AND hold_expires_at >= now()) AS not_expired "
            "FROM sales_unit_inventory WHERE id = :id AND site_id = :s"
        ), {"id": str(unit_id), "s": str(site_id)})).mappings().first()
        held_by = own["held_by"] if own else None
        if held_by is not None:
            # 소유자가 있는(FCFS 토큰 점유) HOLD — 본인이거나 토큰 일치 + 미만료일 때만 계약 허용.
            owner_ok = (by is not None and str(held_by) == str(by)) or (
                hold_token is not None and own is not None and own["hold_token"] == hold_token)
            if not owner_ok:
                raise ValueError("다른 사용자가 임시선점(HOLD)한 세대입니다. 선점자만 계약할 수 있습니다.")
            if not (own and own["not_expired"]):
                raise ValueError("임시선점(HOLD)이 만료된 세대입니다. 다시 선점한 뒤 계약하세요.")

    # ★[보강·iter-5 security] customer_id 인가검증 — 호출자가 넘긴 고객이 '본 현장(site_id) 소속의
    #   살아있는 고객'인지 1쿼리로 확인한다. 과거엔 body 의 customer_id 를 현장 대조 없이 그대로
    #   계약(customer_id)에 영속해, 임의의(타현장) 고객 명의로 계약을 위조할 수 있었다(FCFS claim 은
    #   이미 동일 검증을 함 — 계약 경로와 대칭을 맞춘다). 스코프 밖/미존재면 NotFoundError(=404)로
    #   거부한다(타현장 고객 존재를 누설하지 않음). customer_id 미전달(청약홈 채널 등 익명)은 검증
    #   대상이 아니다(기존 거동 유지).
    if customer_id is not None:
        from apps.api.database.models.sales.contract_crm_ad import SalesCustomer
        owned = (await db.execute(select(SalesCustomer.id).where(
            SalesCustomer.id == customer_id,
            SalesCustomer.site_id == site_id,
            SalesCustomer.deleted_at.is_(None)))).scalar_one_or_none()
        if owned is None:
            raise NotFoundError("해당 현장 소속 고객을 찾을 수 없습니다(타 현장 고객 명의 계약 불가)")

    # 금액이 안 넘어오면 세대 가격표에서 최신 round의 총액을 가져온다.
    price = total_price
    if price is None:
        q = select(SalesUnitPriceTable).where(SalesUnitPriceTable.unit_id == unit_id)
        if round_id:
            q = q.where(SalesUnitPriceTable.round_id == round_id)
        pt = (await db.execute(q.order_by(desc(SalesUnitPriceTable.id)))).scalars().first()
        if pt is not None:
            price = int(pt.override_price or pt.total_price or pt.base_price or 0)
        # 폴백: per-unit 가격표가 없으면(가격표 미생성) 기준단가(SalesPriceBase)에서 직접 산정.
        # 없을 경우 total_price=NULL→수수료·할부·연체 전량 0 cascade 가 발생하므로 자동해소한다.
        if not price:
            from app.services.sales.pricing.engine import resolve_unit_price
            price = await resolve_unit_price(db, site_id, unit, round_id)

    c = SalesContractExt(site_id=site_id, unit_id=unit_id, customer_id=customer_id,
                         round_id=round_id, member_node_id=member_node_id, stage="RESERVED", status="ACTIVE",
                         total_price=int(price) if price else None)
    db.add(c)
    await _set_unit_status(db, unit_id, "RESERVED", by)  # 예약 상태로 전환(청약·배치도와 동기화)
    # ★[보강·iter-7 MED correctness] HOLD→RESERVED 로 넘어가면 그 세대의 임시선점 메타(held_by/
    #   hold_token/hold_expires_at)는 더 이상 의미가 없다(계약으로 확정됨). 정리하지 않으면 만료된
    #   선점 흔적이 남아 감사·디버깅 때 '누가 아직 잡고 있는 것처럼' 혼동을 준다. atomic_reserve
    #   (HOLD→CONTRACTED)도 동일 정리를 하므로(아래) 두 확정 경로의 점유메타 정리를 일관시킨다.
    await db.execute(text(
        "UPDATE sales_unit_inventory SET held_by = NULL, hold_token = NULL, hold_expires_at = NULL "
        "WHERE id = :id AND site_id = :s"
    ), {"id": str(unit_id), "s": str(site_id)})
    await db.flush()
    return c


async def sign_contract(db: AsyncSession, site_id, contract_id, by=None):
    # ★동시성(머니패스 중복 차단): 계약 행을 FOR UPDATE 로 잠근 뒤 상태를 확인한다. 잠그지 않으면
    #   두 사람이 같은 계약을 동시에 서명할 때, 둘 다 'stage==RESERVED' 를 읽고 둘 다 가드를 통과해
    #   split_commission(수수료 배분)·할부 회차표·outbox 가 '중복' 실행된다(수수료 2배). 세대 행은
    #   둘 다 RESERVED→CONTRACTED 동일전이라 _set_unit_status 의 락만으로는 못 막는다(상태가 안 바뀜).
    #   계약 행 자체를 잠가, 먼저 들어온 쪽이 stage 를 SIGNED 로 바꾼 뒤 뒤 쪽은 갱신된 상태를 보고
    #   아래 멱등 가드에서 거부되게 한다(create/cancel 과 동일하게 계약행 잠금으로 직렬화 — 비대칭 해소).
    # ★[현장스코프 머니패스·iter-4 HIGH 전역스윕] 서명은 split_commission(수수료 배분)+할부 회차표를
    #   트리거하는 머니패스다. 계약 행을 site_id 로 스코프해 A현장 사용자가 B현장 contract_id 로 서명
    #   (타현장 수수료 발생)하는 IDOR 를 차단한다. 또 과거 scalar_one() 은 미존재 contract_id 에서
    #   NoResultFound→전역핸들러 500 을 누출했다(클라이언트 입력문제를 서버오류로 오표시). cancel/create
    #   와 대칭으로 scalar_one_or_none()+NotFoundError(=404)로 통일한다(500 누출 차단).
    c = (await db.execute(select(SalesContractExt).where(
        SalesContractExt.id == contract_id,
        SalesContractExt.site_id == site_id).with_for_update())).scalar_one_or_none()
    if c is None:
        raise NotFoundError("계약을 찾을 수 없습니다")
    # 이미 서명됐거나 취소된 계약을 또 서명하면 회차표·수수료가 중복 생성된다 → 막는다(멱등 가드).
    if c.stage != "RESERVED" or c.status != "ACTIVE":
        raise ValueError(f"서명할 수 없는 계약 상태입니다(현재 단계={c.stage}, 상태={c.status}). "
                         "예약(RESERVED) 상태에서만 서명 가능합니다.")
    c.stage = "SIGNED"
    c.signed_at = datetime.now(UTC)
    # lock=True: 서명 중 같은 세대를 건드리는 다른 트랜잭션(취소·재계약)과 직렬화한다.
    await _set_unit_status(db, c.unit_id, "CONTRACTED", by, lock=True)

    # ★회차표 멱등 백스톱: 이 계약에 이미 할부 회차가 있으면 다시 만들지 않는다. 위 stage 가드 +
    #   계약행 FOR UPDATE 로 동시 더블서명은 이미 직렬화되지만, 어떤 경로로든 sign 이 재진입돼도
    #   회차가 중복 적재되지 않도록 '이미 생성됨' 을 한 번 더 확인한다(머니패스 중복 차단·additive).
    existing_inst = (await db.execute(select(SalesContractInstallment).where(
        SalesContractInstallment.contract_ext_id == c.id))).scalars().first()
    if existing_inst is None:
        cfg = (await db.execute(select(SalesSiteConfig).where(SalesSiteConfig.site_id == site_id))).scalar_one_or_none()
        sched = ((cfg.installment_schedule if cfg else None) or {}).get("default", [])
        base = datetime.now(UTC).date()
        for i, s in enumerate(sched, start=1):
            db.add(SalesContractInstallment(
                contract_ext_id=c.id, seq=i, kind=s["kind"],
                due_date=base + timedelta(days=int(s["after_days"])),
                amount=int(round(float(c.total_price or 0) * float(s["ratio"]))),
            ))
    # split_commission 은 자체 멱등 가드(이미 발생한 contract_ext_id 이벤트면 조기반환)로 중복배분을 막는다.
    await split_commission(db, site_id, c)
    await emit_outbox(db, site_id, "ContractSigned",
                      {"unit_id": str(c.unit_id), "amount": int(c.total_price or 0), "stage": "SIGNED"})
    await db.flush()
    return c


async def cancel_contract(db: AsyncSession, site_id, contract_id, reason: str, by=None):
    # 계약 행을 FOR UPDATE 로 잠가, 동시에 들어온 두 취소 요청 중 하나만 실제 취소를 수행하게 한다.
    # ★[비대칭 미배선 해소·iter-3 HIGH] 과거엔 scalar_one() 이라 미존재 contract_id 입력 시
    #   NoResultFound 가 전역핸들러 HTTP500 으로 누출됐다(클라이언트 입력문제를 서버오류로 오표시).
    #   create/sign 과 대칭이 되도록 scalar_one_or_none() 으로 받고, 미존재면 명시적 ValueError 를
    #   던진다(엔드포인트가 404 로 매핑). NoResultFound→500 누출 차단.
    # ★[현장스코프 머니패스·iter-4 HIGH 전역스윕] 계약 행도 site_id 로 스코프해, A현장 사용자가
    #   B현장 contract_id 를 넘겨 타현장 계약을 취소(수수료 환수·세대 AVAILABLE 복원=머니패스)하는
    #   교차테넌트 IDOR 를 차단한다. 스코프 밖이면 '미존재'와 동일하게 NotFoundError(=404)로 정직 표기.
    c = (await db.execute(select(SalesContractExt).where(
        SalesContractExt.id == contract_id,
        SalesContractExt.site_id == site_id).with_for_update())).scalar_one_or_none()
    if c is None:
        raise NotFoundError("계약을 찾을 수 없습니다")
    # ★멱등 가드: 이미 취소된 계약을 또 취소하면 ①수수료 환수(clawback)가 중복 실행되고
    #   ②그 사이 재분양된 세대를 다시 AVAILABLE 로 덮어써 새 계약과 충돌한다. 이미 취소면
    #   부작용 없이 현재 상태를 그대로 반환한다(같은 입력에 같은 결과 = 멱등).
    if c.status == "CANCELLED":
        return c
    db.add(SalesContractChange(
        contract_ext_id=c.id, change_type="CANCEL", effective_at=datetime.now(UTC),
        reason=reason, prev_snapshot={"stage": c.stage, "total_price": int(c.total_price or 0)},
    ))
    c.status = "CANCELLED"
    c.stage = "CANCELLED"
    # 계약은 취소(CANCELLED)로 남기되, 세대(호실)는 다시 'AVAILABLE'로 되돌려 재분양이 가능하게 한다.
    # (이전엔 세대를 CANCELLED로 막아버려 해지 후 같은 호실을 영영 다시 팔 수 없는 결함이 있었음.)
    # lock=True: 세대 행을 잠가 동시 재계약과 직렬화(AVAILABLE 복원과 새 RESERVED 가 안 엉키게).
    await _set_unit_status(db, c.unit_id, "AVAILABLE", by, lock=True)
    ev = (await db.execute(select(SalesCommissionEvent).where(
        SalesCommissionEvent.contract_ext_id == c.id))).scalar_one_or_none()
    if ev:
        await clawback(db, ev.id, reason)
    await emit_outbox(db, site_id, "ContractCancelled",
                      {"unit_id": str(c.unit_id), "amount": int(c.total_price or 0)})
    await db.flush()
    return c
