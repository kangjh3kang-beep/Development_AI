"""청약 배정 엔진 — 가점/추첨/특공 + 예비순번 + 선착순/무순위. 추첨은 시드 고정(감사 가능)."""

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from itertools import groupby

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.sales.harness.outbox import emit_outbox
from apps.api.database.models.sales.subscription import (
    SalesSubscriptionAnnouncement,
    SalesSubscriptionApplication,
    SalesSubscriptionReserveQueue,
    SalesSubscriptionWinner,
    SalesUnrankedOffer,
)
from apps.api.database.models.sales.units_pricing import SalesUnitInventory, SalesUnitStatusLog

logger = logging.getLogger(__name__)


async def _set_unit_status(db, unit_id, to_status, by=None, *, unit=None, lock: bool = False):
    """세대(호실) 상태를 바꾸고 변경이력(SalesUnitStatusLog)을 남긴다 — 청약/추첨/FCFS 점유전이 공통.

    계약 경로(contract/service._set_unit_status)와 감사(from/to/by) 대칭을 맞추기 위한 헬퍼다.
    기존 청약 엔진은 'unit.status = ...' 직접 대입이라 상태 전이가 감사로그에 안 남았다(계약은 남김).
    여기로 통일해 청약/추첨/예비/FCFS 점유 전이도 동일하게 from/to/by 를 기록한다.

    - unit 이 이미 잠겨 조회된 ORM 객체로 넘어오면 재조회 없이 그대로 쓴다(중복 SELECT·락 회피).
    - lock=True 면 unit 미전달 시 세대 행을 SELECT ... FOR UPDATE 로 잠근다.
    """
    if not unit_id:
        return None
    if unit is None:
        stmt = select(SalesUnitInventory).where(SalesUnitInventory.id == unit_id)
        if lock:
            stmt = stmt.with_for_update()
        unit = (await db.execute(stmt)).scalar_one()
    db.add(SalesUnitStatusLog(site_id=unit.site_id, unit_id=unit_id,
                              from_status=unit.status, to_status=to_status, by=by))
    unit.status = to_status
    return unit


def _tiebreak(seed, app_id) -> str:
    return hashlib.sha256(f"{seed}:{app_id}".encode()).hexdigest()


def _rank_pick(apps, n, seed):
    ordered = sorted(apps, key=lambda a: ((a.rank or 9), -(float(a.gajeom_score or 0)), _tiebreak(seed, a.id)))
    n = max(int(n), 0)
    return ordered[:n], ordered[n:]


async def _available_units(db, site_id, type_id, *, lock: bool = False):
    """배정 가능한(AVAILABLE) 세대 목록. lock=True 면 행을 FOR UPDATE 로 잠근다.

    추첨(run_draw)은 이 세대들을 곧 APPLIED 로 바꾸므로, 잠그지 않으면 추첨 도중
    선착순(claim_offer)이 같은 세대를 가져가 정원이 어긋날 수 있다. 잠가서 직렬화한다.
    """
    stmt = select(SalesUnitInventory).where(
        SalesUnitInventory.site_id == site_id, SalesUnitInventory.type_id == type_id,
        SalesUnitInventory.status == "AVAILABLE", SalesUnitInventory.deleted_at.is_(None))
    if lock:
        stmt = stmt.with_for_update()
    return list((await db.execute(stmt.order_by(SalesUnitInventory.id))).scalars())


async def run_draw(db: AsyncSession, site_id, announcement_id, seed: str | None = None) -> int:
    # 공고 행을 FOR UPDATE 로 잠가, 동시에 두 번 들어온 추첨 요청을 직렬화한다.
    # ★[IDOR·security 전역스윕·iter-5 HIGH] 과거엔 공고를 id 로만 조회(site_id 미스코프)하고
    #   scalar_one() 이라 두 가지 결함이 있었다.
    #   ① 미존재 announcement_id → NoResultFound → 추첨 엔드포인트가 except ValueError 만 잡아
    #      전역핸들러 HTTP500 으로 누출(클라이언트 입력문제를 서버오류로 오표시).
    #   ② site_id 미스코프 → A현장 사용자가 B현장 announcement_id 를 주입하면 '타현장 신청서로
    #      추첨하되 자기현장(_available_units 는 site_id 스코프) 세대를 점유'하는 정합위험(교차테넌트
    #      추첨). _available_units·winner/reserve INSERT 는 site_id 스코프인데 공고만 빠져 있었다.
    #   해결: WHERE 에 site_id 를 더하고 scalar_one_or_none()+NotFoundError(=404)로 통일한다
    #   (claim_offer/promote_reserve/create_contract 와 동일 규약 — 타현장 공고 거부·500 누출 차단).
    from app.services.sales.contract.service import NotFoundError
    ann = (await db.execute(select(SalesSubscriptionAnnouncement).where(
        SalesSubscriptionAnnouncement.id == announcement_id,
        SalesSubscriptionAnnouncement.site_id == site_id).with_for_update())).scalar_one_or_none()
    if ann is None:
        raise NotFoundError("청약 공고를 찾을 수 없습니다")
    # ★멱등 가드: 이미 추첨이 끝난(DRAWN) 공고를 다시 돌리면 당첨자(winner)·예비큐가 중복 생성되고
    #   세대가 또 점유돼 정원·공정성이 깨진다. 이미 추첨됐으면 다시 돌리지 않고 0을 반환한다.
    #   (재추첨이 필요하면 별도의 '추첨 취소→재오픈' 흐름을 둬야 한다 — 여기서 임의 재실행 금지.)
    if ann.status == "DRAWN":
        return 0
    seed = seed or ann.announce_no or str(announcement_id)
    rules = ann.rules or {}
    special_ratio = rules.get("special_ratio", {})  # {type_id: 0~1} 파라미터
    apps = list((await db.execute(select(SalesSubscriptionApplication).where(
        SalesSubscriptionApplication.announcement_id == announcement_id,
        SalesSubscriptionApplication.eligibility == "OK"))).scalars())
    apps.sort(key=lambda a: str(a.unit_type_id))
    total_win = 0
    for type_id, grp in groupby(apps, key=lambda a: a.unit_type_id):
        group = list(grp)
        units = await _available_units(db, site_id, type_id, lock=True)
        quota = len(units)
        sp_quota = int(quota * float(special_ratio.get(str(type_id), 0)))
        specials = [a for a in group if a.supply_class == "SPECIAL"]
        generals = [a for a in group if a.supply_class == "GENERAL"]
        win_sp, rest_sp = _rank_pick(specials, sp_quota, seed)
        win_gen, _rest_gen = _rank_pick(generals + rest_sp, quota - len(win_sp), seed)
        winners = [(a, "SPECIAL") for a in win_sp] + [(a, "GENERAL") for a in win_gen]
        # ★[CRITICAL 회귀 제거·iter-3] 청약 신청이 세대 수(quota)보다 적으면(미달청약) _rank_pick 은
        #   quota 보다 적은 당첨자만 돌려준다 → len(winners) < len(units). 이건 '비정상'이 아니라
        #   정상적인 미달 추첨이다(남는 세대는 그냥 비워두면 됨). 과거 iter-2 가 넣은
        #   zip(winners, units, strict=True) 는 이 정상 미달경로에서도 길이 불일치를 ValueError 로
        #   터뜨려, lifecycle_p5 가 409+rollback 으로 받아 '재고가 남는 정상 추첨' 전체를 실패시켰다
        #   (당첨 0명 — CRITICAL 회귀). 그래서 strict=True 를 제거하고 plain zip(짧은 쪽 기준 순회)으로
        #   되돌린다. 남는 units 는 자르지 않고 AVAILABLE 그대로 둔다(예비/추가 모집 대상).
        #
        # ★[dead-branch 정합·iter-4] '초과(winners > units)' 는 사실 도달 불가능한 분기다:
        #   _rank_pick 은 ordered[:n] 로 n(quota)에서 캡되므로 len(win_sp)<=sp_quota,
        #   len(win_gen)<=quota-len(win_sp) → len(winners)<=quota=len(units) 가 항상 성립한다.
        #   (실제 '초과 청약'에서 정원을 넘는 신청자는 winners 가 아니라 _rank_pick 의 rest=_rest_gen
        #   으로 빠져 아래 예비 큐에 편입된다 — test_over_subscribed 가 검증하는 경로가 바로 이것이다.)
        #   과거엔 이 불변식을 assert 로 보존했으나 assert 는 python -O 에서 통째로 제거돼, 만에 하나
        #   _rank_pick 계약이 깨지면 winners 초과분이 silent 누락될 위험이 있었다. assert 대신 명시
        #   if + 경고 로깅으로 바꿔, -O 에서도 살아남는 '방어적 비절단' 처리를 둔다(unreachable 이지만
        #   깨지면 누락 없이 예비 편입+로깅). 정상경로(미달/정확/초과)에선 overflow 는 항상 []다.
        overflow = winners[len(units):]
        if overflow:  # 도달 불가(불변식). 도달하면 _rank_pick 캡 계약이 깨진 것 → 누락 없이 예비 편입+경고.
            logger.warning(
                "run_draw 불변식 위반: winners(%d) > units(%d) — _rank_pick quota 캡 계약 점검 필요. "
                "초과 %d명은 silent 누락 없이 예비 큐로 편입.",
                len(winners), len(units), len(overflow))
            winners = winners[:len(units)]
        # zip(.., strict=False): 미달(winners 적음)이면 winners 쪽에서 멈춰 남는 units 는 그대로
        # AVAILABLE 유지(정상). 정확히 같으면 모두 배정. 초과분(이론상)은 위에서 overflow 로 분리됨.
        #   strict=False 는 '짧은 쪽 기준 순회·예외 없음'을 명시한 plain zip 이다(iter-2 의 strict=True
        #   가 미달경로를 ValueError 로 터뜨린 회귀를 되돌린 것 — B905 충족 위해 명시값만 부여).
        for (a, wtype), unit in zip(winners, units, strict=False):
            a.result = "WIN"
            db.add(SalesSubscriptionWinner(
                site_id=site_id, application_id=a.id, unit_id=unit.id, win_type=wtype, status="NOTIFIED",
                contract_due=(ann.contract_end or (datetime.now(UTC).date() + timedelta(days=7)))))
            await _set_unit_status(db, unit.id, "APPLIED", by=None, unit=unit)  # 점유 전이(감사로그)
            total_win += 1
        # 세대 수를 초과한 당첨자(이론상)는 누락(silent)시키지 않고 예비 큐 앞에 편입한다.
        reserve_apps = [a for (a, _wt) in overflow] + list(_rest_gen)
        for i, a in enumerate(reserve_apps, start=1):
            a.result = "RESERVE"
            db.add(SalesSubscriptionReserveQueue(site_id=site_id, announcement_id=announcement_id,
                   application_id=a.id, unit_type_id=type_id, reserve_no=i))
    ann.status = "DRAWN"
    await emit_outbox(db, site_id, "ApplicationReceived", {"round_id": str(ann.round_id or ""), "unit_id": ""})
    await db.flush()
    return total_win


async def promote_reserve(db: AsyncSession, site_id, unit_id, by=None):
    # 세대 행을 잠그고(이중 승계 race 방지) 현재 점유 당첨자를 정리한 뒤 다음 예비를 올린다.
    # ★[현장스코프 머니패스·iter-4 HIGH 전역스윕] 예비승계는 새 winner 생성+세대 점유전이(머니패스)다.
    #   세대 행을 site_id 로 스코프해 A현장 사용자가 B현장 unit_id 로 예비를 승계(타현장 세대 점유)하는
    #   IDOR 를 차단한다. 스코프 밖이면 '미존재'와 동일하게 NotFoundError(=404)로 본다(scalar_one()의
    #   NoResultFound→500 누출도 함께 해소). 아래 occupant/reserve 조회는 이미 site_id 로 스코프돼 있다.
    from app.services.sales.contract.service import NotFoundError
    unit = (await db.execute(select(SalesUnitInventory).where(
        SalesUnitInventory.id == unit_id,
        SalesUnitInventory.site_id == site_id).with_for_update())).scalar_one_or_none()
    if unit is None:
        raise NotFoundError("세대를 찾을 수 없습니다")
    # ★[예비승계 unreachable 해소·iter-2 HIGH] 기존 당첨자가 계약을 안 해 그 세대를 예비에게 넘길 때,
    #   ① 그 세대를 점유 중인 '유효 당첨(NOTIFIED)' winner 를 FORFEITED(포기)로 전이하고
    #   ② 세대 상태를 AVAILABLE 로 복원한다.
    #   이 정리가 없으면 (a)당첨 직후 세대가 APPLIED 로 남아 'unit.status!=AVAILABLE' 가드가 예비승계를
    #   영구 차단했고, (b)기존 NOTIFIED winner 가 같은 unit_id 로 남아 새 RESERVE winner INSERT 시
    #   부분 유니크 인덱스(uq_sales_sub_winner_unit, WHERE status<>'FORFEITED')에 23505 충돌이 났다.
    #   FORFEITED 로 전이하면 그 행은 유니크 대상에서 빠져, 새 RESERVE 당첨이 같은 세대를 받을 수 있다.
    #   계약 체결(CONTRACTED)된 당첨은 정상 점유이므로 예비승계를 막는다(중복 분양 차단).
    occupant = (await db.execute(select(SalesSubscriptionWinner).where(
        SalesSubscriptionWinner.site_id == site_id,
        SalesSubscriptionWinner.unit_id == unit_id,
        SalesSubscriptionWinner.status.in_(("NOTIFIED", "CONTRACTED")))
        .with_for_update())).scalars().first()
    if occupant is not None and occupant.status == "CONTRACTED":
        # 이미 계약까지 간 세대는 예비로 넘길 수 없다(정상 점유 — 중복 분양 방지).
        raise ValueError("이미 계약 체결된 세대입니다 — 예비를 승계할 수 없습니다.")
    if occupant is not None:
        # 미계약(NOTIFIED) 당첨자를 포기 처리한다(winner 행만 FORFEITED 로 — 세대 점유자만 교체).
        # ★[CRITICAL 회귀 제거·iter-6] 과거엔 여기서 세대를 한 번 AVAILABLE 로 _set_unit_status 하고
        #   아래에서 다시 APPLIED 로 _set_unit_status 했다(같은 unit_id 2회). 그런데 SalesUnitStatusLog
        #   PK 가 복합(unit_id, ts)이고 ts 의 server_default 는 now()(=PG transaction_timestamp(),
        #   한 트랜잭션 안에서 상수)라, 두 INSERT 가 동일한 (unit_id, now()) 키가 돼 flush 에서 23505
        #   UniqueViolation 으로 터졌다 → 예비승계(머니패스)가 '항상' 실패했다. 중간 AVAILABLE 기록을
        #   생략한다: 세대는 굳이 로그상 AVAILABLE 을 '거치지' 않아도 되고(점유자만 교체), 아래에서
        #   APPLIED 로 단 1회만 _set_unit_status 하면 한 트랜잭션 내 동일 unit 이중 전이가 사라진다.
        occupant.status = "FORFEITED"
    elif unit.status != "AVAILABLE":
        # winner 행은 없는데 세대가 점유 중(다른 경로로 점유) — 빈 세대에만 승계 가능(이중 승계 차단).
        raise ValueError(f"이미 점유된 세대입니다(현재 상태={unit.status}). 빈 세대에만 예비를 승계할 수 있습니다.")
    # 예비 큐의 다음 1명을 FOR UPDATE + SKIP LOCKED 로 집는다. 동시 승계 요청이 같은
    # reserve_no 를 둘 다 집어 한 사람을 두 번 올리는 것을 막고(잠금), 잠긴 행은 건너뛰어
    # 서로 다른 다음 후보를 집게 한다(SKIP LOCKED) — 데드락 없이 직렬화.
    nxt = (await db.execute(select(SalesSubscriptionReserveQueue).where(
        SalesSubscriptionReserveQueue.site_id == site_id,
        SalesSubscriptionReserveQueue.unit_type_id == unit.type_id,
        SalesSubscriptionReserveQueue.promoted.is_(False))
        .order_by(SalesSubscriptionReserveQueue.reserve_no).limit(1)
        .with_for_update(skip_locked=True))).scalar_one_or_none()
    if not nxt:
        # 올릴 예비가 없으면 세대를 비운다(AVAILABLE) — 점유자(occupant)를 FORFEITED 로 내렸는데
        # 새 점유자가 없으니 세대가 APPLIED 인 채로 남아 '주인 없는 점유' 가 되는 것을 막는다.
        # ★[iter-6] occupant 경로에선 위에서 중간 AVAILABLE 전이를 생략했으므로(2회 전이 회귀 제거),
        #   '승계 실패(예비 0명)' 일 때만 여기서 1회 AVAILABLE 전이를 기록한다(트랜잭션 내 동일 unit
        #   전이는 여전히 최대 1회 — 23505 재발 없음). 이미 AVAILABLE 이면 _set_unit_status 는
        #   from==to 로그 1행만 남기므로 정원·정합엔 영향 없다.
        if occupant is not None:
            await _set_unit_status(db, unit_id, "AVAILABLE", by, unit=unit)
            await db.flush()
        return None
    nxt.promoted = True
    db.add(SalesSubscriptionWinner(site_id=site_id, application_id=nxt.application_id, unit_id=unit_id,
           win_type="RESERVE", status="NOTIFIED"))
    await _set_unit_status(db, unit_id, "APPLIED", by, unit=unit)  # 예비 당첨자에게 점유 전이(감사로그)
    await db.flush()
    return nxt.application_id


async def claim_offer(db: AsyncSession, site_id, unit_id, customer_id, kind="FCFS"):
    # ★선착순(FCFS) race: 두 사람이 같은 세대를 동시에 클릭하면, 잠그지 않을 경우 둘 다
    #   'AVAILABLE'을 읽고 둘 다 점유에 성공해 같은 세대가 2명에게 팔린다. 세대 행을
    #   FOR UPDATE 로 잠가, 먼저 들어온 1명만 APPLIED 로 바꾸고 뒤 1명은 갱신된 상태를
    #   보고 거부(ValueError)되게 한다 — 선착순 1명 보장.
    # ★[IDOR·머니패스 교차테넌트·iter-4 HIGH] 과거엔 unit 을 id 로만 조회하고 site_id 검증이
    #   없어, A현장 사용자가 B현장 unit_id 를 body 로 넘겨 타현장 세대를 선점(FCFS 점유=머니패스)할
    #   수 있었다(site_id 는 감사기록 write 에만 쓰이고 SELECT 스코프엔 빠짐). run_draw/promote_reserve
    #   는 site_id 로 스코프하나 claim 만 누락. SELECT WHERE 에 site_id 를 더해 타현장 unit_id 점유를
    #   차단한다. 스코프 밖이면 '미존재'와 동일하게 NotFoundError(=404)로 정직 표기(scalar_one()의
    #   NoResultFound→500 누출도 함께 해소). 타현장 세대 존재를 점유 성공/실패로 누설하지 않는다.
    from app.services.sales.contract.service import NotFoundError
    unit = (await db.execute(select(SalesUnitInventory).where(
        SalesUnitInventory.id == unit_id,
        SalesUnitInventory.site_id == site_id).with_for_update())).scalar_one_or_none()
    if unit is None:
        raise NotFoundError("세대를 찾을 수 없습니다")
    if unit.status != "AVAILABLE":
        raise ValueError("이미 점유된 세대")
    # ★[감사단절 해소·iter-2 MED] 기존엔 UNRANKED(무순위) 만 누가 점유했는지(claimed_by) 기록하고
    #   FCFS(선착순)는 customer_id 를 어디에도 남기지 않아 '누가 이 세대를 선점했는가' 추적이 끊겼다.
    #   FCFS 도 SalesUnrankedOffer(claimed_by=customer_id, channel=kind) 로 동일하게 점유자를 남긴다
    #   (테이블 재사용 — channel 로 FCFS/UNRANKED 구분). 둘 다 감사 가능하게 통일.
    db.add(SalesUnrankedOffer(site_id=site_id, unit_id=unit_id, claimed_by=customer_id,
           channel=kind, claimed_at=datetime.now(UTC)))
    await _set_unit_status(db, unit_id, "APPLIED", by=customer_id, unit=unit)  # 점유 전이(감사로그)
    await db.flush()
    return unit_id
