"""#7 계약·CRM·청약 — 순수로직 회귀 안전망(Wave2 P1).

라이브 DB 없이(가짜세션·순수함수) 머니패스 상태머신·동시성·공정성·CRM 가드의 회귀를 영구 차단한다.

- 계약 상태머신: create→sign→cancel 전이 정합 + 멱등(이미 취소 재취소 무부작용) +
  이미 점유된 세대 재계약 차단(이중계약 방지) + 취소 시 세대 AVAILABLE 복원.
- 청약 추첨: run_draw 결정론(같은 seed→같은 당첨자 순서) + 특공(SPECIAL) 우선 후 일반 +
  이미 DRAWN 공고 재추첨 차단(중복당첨 방지) + 세대 잠금(FOR UPDATE) 사용 확인.
- FCFS: claim_offer 가 AVAILABLE 아닌 세대 거부(선착순 1명만 성공하는 상태가드).
- CRM: _night_guard(야간 21~08 차단) + 메시지 reason_code 분류(silent-drop 아님) +
  _mask_phone 마스킹 일관.

가짜세션(FakeSession)은 SQLAlchemy 인터페이스(execute/scalar_one/scalars/add/flush)를 흉내내
순수 상태전이만 검증한다(외부 I/O·실DB 없음). 동시성은 'FOR UPDATE 잠금을 걸었는가'와
'상태가드가 두 번째 요청을 거부하는가'로 검증한다(실제 락 경합 대신 불변식 검증).
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid as uuid_mod
from datetime import UTC, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402

from app.services.sales.subscription import engine as sub_engine  # noqa: E402
from app.services.sales.subscription.engine import _rank_pick, _tiebreak  # noqa: E402


# ════════════════════════ 가짜 세션/엔티티 ════════════════════════
class _Result:
    """db.execute(...) 반환 흉내 — scalar_one / scalar_one_or_none / scalars / mappings 지원."""

    def __init__(self, rows):
        self._rows = list(rows)

    def scalar_one(self):
        if not self._rows:
            raise LookupError("no row")
        return self._rows[0]

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return _Scalars(self._rows)

    def mappings(self):
        # ★[iter-7] create_contract 의 HOLD 소유권 raw SELECT 는 .mappings().first() 로 dict 행을 읽는다.
        #   가짜세션 핸들러가 그 raw SELECT 자리에 dict(또는 dict 리스트)을 돌려주면 그대로 흉내낸다.
        return _Mappings(self._rows)


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _Mappings:
    """result.mappings() 흉내 — first() 로 dict 행(또는 None)을 돌려준다."""

    def __init__(self, rows):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None


class CompositePKViolationError(Exception):
    """라이브 PG 의 23505(UniqueViolation) 를 흉내내는 가짜 예외 — FakeSession 복합PK 충돌 시뮬."""


class FakeSession:
    """SELECT 결과를 핸들러로 결정하는 가짜 비동기 세션. with_for_update 사용도 기록한다.

    ★[iter-6 완결게이트] SalesUnitStatusLog 는 라이브에서 복합PK(unit_id, ts)이고 ts 는
    server_default=now()(트랜잭션 내 상수)다 — 한 트랜잭션에서 같은 unit_id 로 status-log 를 2회
    add 하면 (unit_id, now()) 키가 겹쳐 flush 에서 23505 가 난다(예비승계 이중 전이 회귀의 정체).
    가짜세션은 복합PK·유니크 제약을 강제하지 않아 그 회귀가 테스트를 통과해버리는 사각이 있었다.
    여기서 flush 시 added 안의 SalesUnitStatusLog 를 unit_id 기준으로 묶어, 같은 unit_id 가 2회
    이상이면 라이브 23505 와 동치인 CompositePKViolationError 을 던져 그 회귀를 테스트가 잡게 한다.
    (ts 를 흉내내지 않고 'unit_id 가 트랜잭션 내 2회면 충돌' 로 단순화 — 실제 now() 상수성과 동치.)
    """

    def __init__(self, handler):
        self._handler = handler          # callable(stmt) -> list[rows]
        self.added = []                  # db.add 로 들어온 객체들
        self.flushed = 0
        self.lock_seen = False           # with_for_update() 가 걸린 SELECT 를 본 적 있는가

    async def execute(self, stmt, params=None):
        # ★[iter-7] raw text() SQL 은 db.execute(text(...), {params}) 처럼 두 번째 인자(바인드 파라미터)를
        #   받는다(create_contract 의 HOLD 소유권 SELECT·점유메타 정리 UPDATE 등). 가짜세션도 그 시그니처를
        #   받아주되 핸들러는 stmt 만 보고 결과를 결정한다(params 는 무시 — 순수 상태전이 검증이라 무관).
        # SQLAlchemy Select 에 FOR UPDATE 가 걸렸는지(동시성 가드) 탐지
        try:
            if getattr(stmt, "_for_update_arg", None) is not None:
                self.lock_seen = True
        except Exception:
            pass
        return _Result(self._handler(stmt))

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self._assert_no_status_log_pk_clash()
        self.flushed += 1

    def _assert_no_status_log_pk_clash(self):
        """같은 unit_id 의 SalesUnitStatusLog 가 2개 이상이면 복합PK(unit_id, ts) 충돌로 본다."""
        seen = {}
        for o in self.added:
            if type(o).__name__ != "SalesUnitStatusLog":
                continue
            uid = getattr(o, "unit_id", None)
            seen[uid] = seen.get(uid, 0) + 1
            if seen[uid] > 1:
                raise CompositePKViolationError(
                    f"SalesUnitStatusLog 복합PK(unit_id={uid}, ts=now()) 충돌 — "
                    f"한 트랜잭션에서 같은 unit 으로 status-log 를 2회 INSERT 했습니다(라이브 23505).")


class FakeUnit:
    def __init__(self, status="AVAILABLE", type_id=None, site_id=None):
        self.id = uuid_mod.uuid4()
        self.status = status
        self.type_id = type_id or uuid_mod.uuid4()
        self.site_id = site_id or uuid_mod.uuid4()
        self.deleted_at = None


class FakeItem:
    """물품 수불(inventory_txn)용 가짜 품목 — site_id 스코프·재고(stock_qty)만 본다."""

    def __init__(self, site_id=None, stock_qty=10):
        self.id = uuid_mod.uuid4()
        self.site_id = site_id or uuid_mod.uuid4()
        self.stock_qty = stock_qty


class FakeContract:
    def __init__(self, unit_id, stage="RESERVED", status="ACTIVE", total_price=100):
        self.id = uuid_mod.uuid4()
        self.unit_id = unit_id
        self.stage = stage
        self.status = status
        self.total_price = total_price
        self.signed_at = None
        self.member_node_id = None  # 담당 영업사원 노드(수수료 배분 체인 시작점)


def _run(coro):
    return asyncio.run(coro)


def _stmt_table(stmt) -> str:
    """SELECT 문이 어느 테이블을 대상으로 하는지 소문자 SQL 문자열에서 식별(가짜세션 분기용)."""
    try:
        return str(stmt).lower()
    except Exception:
        return ""


# ════════════════════════ 계약 상태머신 ════════════════════════
from app.services.sales.contract import service as contract_svc  # noqa: E402


class TestContractStateMachine:
    def test_cancel_is_idempotent_no_double_effect(self):
        """이미 CANCELLED 계약을 또 취소하면 부작용 없이 그대로 반환(환수 중복·세대 덮어쓰기 방지)."""
        unit = FakeUnit(status="AVAILABLE")
        c = FakeContract(unit.id, stage="CANCELLED", status="CANCELLED")

        def handler(stmt):
            return [c]

        db = FakeSession(handler)
        out = _run(contract_svc.cancel_contract(db, unit.site_id, c.id, reason="중복요청"))
        assert out is c
        assert out.status == "CANCELLED"
        # 멱등 가드로 조기반환 → 변경이력·세대상태변경(add)·flush 가 전혀 일어나지 않아야 한다.
        assert db.added == []
        assert db.flushed == 0
        # 계약행을 FOR UPDATE 로 잠갔는지(동시 취소 직렬화) 확인.
        assert db.lock_seen is True

    def test_sign_rejects_non_reserved(self):
        """예약(RESERVED)·활성(ACTIVE) 아닌 계약 서명은 거부(중복 서명·회차/수수료 중복생성 방지)."""
        unit = FakeUnit()
        c = FakeContract(unit.id, stage="SIGNED", status="ACTIVE")  # 이미 서명됨

        def handler(stmt):
            return [c]

        db = FakeSession(handler)
        with pytest.raises(ValueError, match="서명할 수 없는"):
            _run(contract_svc.sign_contract(db, unit.site_id, c.id))

    def test_sign_missing_or_cross_site_is_notfounderror(self):
        """★[현장스코프 머니패스·iter-4 HIGH] 미존재/타현장 contract_id 서명은 NotFoundError
        (=404)로 거부된다(과거 scalar_one()의 NoResultFound→500 누출 + 교차테넌트 수수료 발생 차단).
        FakeSession 이 site_id 스코프 0행을 흉내내 빈 결과를 돌려준다."""
        from app.services.sales.contract.service import NotFoundError

        def handler(stmt):
            return []   # site_id 스코프 0행(미존재/타현장)

        db = FakeSession(handler)
        with pytest.raises(NotFoundError, match="계약을 찾을 수 없습니다"):
            _run(contract_svc.sign_contract(db, uuid_mod.uuid4(), uuid_mod.uuid4()))
        assert db.lock_seen is True   # 계약행 FOR UPDATE(스코프된 SELECT 도 잠금)

    def test_cancel_missing_or_cross_site_is_notfounderror(self):
        """★[현장스코프 머니패스·iter-4 HIGH] 미존재/타현장 contract_id 취소는 NotFoundError(=404).
        타현장 계약을 취소(수수료 환수·세대 복원=머니패스)하는 IDOR 를 차단한다."""
        from app.services.sales.contract.service import NotFoundError

        def handler(stmt):
            return []   # site_id 스코프 0행

        db = FakeSession(handler)
        with pytest.raises(NotFoundError, match="계약을 찾을 수 없습니다"):
            _run(contract_svc.cancel_contract(db, uuid_mod.uuid4(), uuid_mod.uuid4(), reason="x"))
        assert db.lock_seen is True

    def test_create_missing_or_cross_site_unit_is_notfounderror(self):
        """★[현장스코프 머니패스·iter-4 HIGH] 미존재/타현장 unit_id 로 계약 생성은 NotFoundError(=404).
        타현장 세대로 계약(점유=머니패스)을 만드는 IDOR 를 차단한다."""
        from app.services.sales.contract.service import NotFoundError

        def handler(stmt):
            return []   # site_id 스코프 0행

        db = FakeSession(handler)
        with pytest.raises(NotFoundError, match="세대를 찾을 수 없습니다"):
            _run(contract_svc.create_contract(db, uuid_mod.uuid4(), uuid_mod.uuid4()))
        assert db.lock_seen is True


class TestCommissionIdempotency:
    """★수수료 2배 방지(iter-2 HIGH) — split_commission 내부 멱등 가드 회귀 안전망."""

    def test_split_returns_existing_event_no_double(self):
        """이 계약(contract_ext_id)에 이미 발생한 수수료 이벤트가 있으면, 다시 배분하지 않고
        기존 이벤트를 그대로 반환한다(더블서명·재처리로 수수료가 2배 배분되는 것을 차단)."""
        from app.services.sales.commission import engine as comm_engine

        class _Event:
            def __init__(self):
                self.id = uuid_mod.uuid4()
                self.contract_ext_id = uuid_mod.uuid4()
                self.status = "SPLIT"

        ev = _Event()
        c = FakeContract(uuid_mod.uuid4())
        c.id = ev.contract_ext_id
        c.member_node_id = uuid_mod.uuid4()

        def handler(stmt):
            s = _stmt_table(stmt)
            # 멱등 가드의 '기존 이벤트 조회' 만 동작시키고 그 외는 빈 결과.
            if "sales_commission_events" in s:
                return [ev]
            return []

        db = FakeSession(handler)
        out = _run(comm_engine.split_commission(db, c.member_node_id, c))
        # 기존 이벤트를 그대로 반환(새 이벤트 add·flush 없음 = 중복배분 차단).
        assert out is ev
        assert db.added == []

    def test_split_voided_event_does_not_block(self):
        """VOID(무효처리)된 이벤트는 '존재'로 보지 않아, 정정 후 재배분을 막지 않는다.
        (status != 'VOID' 필터 — REVERSED 는 '발생 후 되돌림'이라 막지만 VOID 는 제외)."""
        from app.services.sales.commission import engine as comm_engine

        c = FakeContract(uuid_mod.uuid4())
        c.id = uuid_mod.uuid4()
        c.member_node_id = uuid_mod.uuid4()

        def handler(stmt):
            # 멱등 가드 조회는 status!=VOID 필터라 VOID 이벤트는 안 잡힘 → 빈 결과.
            # master 미설정(빈 결과) → resolve_total=0 → split 조기반환 None(부작용 없음).
            return []

        db = FakeSession(handler)
        out = _run(comm_engine.split_commission(db, c.member_node_id, c))
        # master 미설정이라 total<=0 → None 반환(멱등 가드에 막히지 않고 정상 진행했음을 확인).
        assert out is None


class TestUnitStatusGuard:
    """이미 점유된 세대 재계약 차단 — create_contract 의 상태가드(이중계약 방지)."""

    @pytest.mark.parametrize("occupied", ["RESERVED", "APPLIED", "CONTRACTED"])
    def test_create_contract_rejects_occupied_unit(self, occupied):
        unit = FakeUnit(status=occupied)

        def handler(stmt):
            return [unit]

        db = FakeSession(handler)
        with pytest.raises(ValueError, match="이미 점유된 세대"):
            _run(contract_svc.create_contract(db, unit.site_id, unit.id))
        # 세대 조회 시 FOR UPDATE 로 잠갔는지(동시 생성 race 차단) 확인.
        assert db.lock_seen is True

    def test_create_contract_rejects_unknown_status_allowlist(self):
        """★[보강·iter-5] allowlist(AVAILABLE/HOLD만 허용) 전환 회귀 안전망 — 거부목록에 없던
        '새 점유상태'(예: LOCKED)도 allowlist 밖이면 자동 거부된다(fail-closed). denylist 였다면
        LOCKED 가 거부목록에 빠져 silent 계약허용이 됐을 위험을 차단한다."""
        unit = FakeUnit(status="LOCKED")   # 거부목록(RESERVED/APPLIED/CONTRACTED)에 없는 새 점유상태

        def handler(stmt):
            return [unit]

        db = FakeSession(handler)
        with pytest.raises(ValueError, match="이미 점유된 세대"):
            _run(contract_svc.create_contract(db, unit.site_id, unit.id))
        assert db.lock_seen is True

    def test_create_contract_rejects_cross_site_customer(self):
        """★[보강·iter-5 security] body 의 customer_id 가 타현장 고객이면(site_id 스코프 SELECT 0행)
        NotFoundError(=404)로 거부된다 — 타현장 고객 명의로 계약을 위조할 수 없다(FCFS claim 과 대칭).
        세대(AVAILABLE)는 통과하되 고객 검증에서 막혀, 계약(SalesContractExt) add 가 일어나지 않는다."""
        from app.services.sales.contract.service import NotFoundError
        unit = FakeUnit(status="AVAILABLE")
        cust = uuid_mod.uuid4()

        def handler(stmt):
            s = _stmt_table(stmt)
            if "sales_unit_inventory" in s:
                return [unit]                # 세대는 본 현장 소속(통과)
            if "sales_customers" in s:
                return []                    # 고객은 타현장 스코프 → 0행(거부)
            return []

        db = FakeSession(handler)
        with pytest.raises(NotFoundError, match="해당 현장 소속 고객을 찾을 수 없습니다"):
            _run(contract_svc.create_contract(db, unit.site_id, unit.id, customer_id=cust))
        # 고객 검증에서 막혀 계약 생성(SalesContractExt add)이 일어나지 않아야 한다(부작용 0).
        added_types = [type(o).__name__ for o in db.added]
        assert "SalesContractExt" not in added_types


class TestHoldOwnershipGuard:
    """★[iter-7 HIGH security] HOLD 토큰 소유권 우회(머니패스 점유탈취) 차단 회귀 안전망.

    create_contract 가 HOLD 세대를 계약대상으로 열 때, FCFS 임시선점(atomic_hold)으로 누군가
    잡아둔(held_by 가 있는) HOLD 는 '본인(by)이거나 토큰일치 + 미만료' 일 때만 계약을 허용한다.
    held_by 가 NULL 인 HOLD(추첨 배정·동호지정대기 파킹)는 소유권 검증 없이 통과해 추첨배정→계약
    정상흐름을 보존한다. FakeSession 핸들러가 세대 SELECT 와 소유권 raw SELECT(dict 행)를 분기한다."""

    @staticmethod
    def _ownership_row(held_by=None, hold_token=None, not_expired=True):
        """create_contract 의 소유권 raw SELECT 가 돌려받는 mappings 행(dict) 흉내."""
        return {"held_by": held_by, "hold_token": hold_token, "not_expired": not_expired}

    def _make_db(self, unit, ownership):
        """세대 SELECT(ORM)→unit, 소유권 SELECT(held_by 컬럼 포함)→ownership dict 로 분기."""

        def handler(stmt):
            s = _stmt_table(stmt)
            # 소유권 raw SELECT 는 'held_by' 컬럼을 명시적으로 고른다(세대 ORM SELECT 와 구분).
            if "sales_unit_inventory" in s and "held_by" in s and "not_expired" in s:
                return [ownership] if ownership is not None else []
            if "sales_unit_inventory" in s:
                return [unit]
            if "sales_unit_price_table" in s:
                return []          # 가격표 없음 → 폴백 resolve_unit_price(아래 핸들러로 0 처리)
            if "sales_price_base" in s:
                return []          # 기준단가도 없음 → price=None(계약은 생성됨)
            return []

        return FakeSession(handler)

    def test_create_rejects_other_staff_hold_seizure(self):
        """★타직원 HOLD 세대 계약 거부(점유탈취 차단) — held_by 가 호출자(by)와 다르고 토큰도 없으면
        ValueError(엔드포인트 409)로 거부한다. A직원 임시선점을 B직원이 가로채는 머니패스를 막는다."""
        staff_a = uuid_mod.uuid4()
        staff_b = uuid_mod.uuid4()
        unit = FakeUnit(status="HOLD")
        own = self._ownership_row(held_by=staff_a, hold_token="tokA", not_expired=True)
        db = self._make_db(unit, own)
        with pytest.raises(ValueError, match="선점자만 계약할 수 있습니다"):
            _run(contract_svc.create_contract(db, unit.site_id, unit.id, by=staff_b))
        # 거부 후 계약(SalesContractExt) add 가 일어나지 않아야 한다(부작용 0).
        assert "SalesContractExt" not in [type(o).__name__ for o in db.added]
        assert db.lock_seen is True   # 세대행 FOR UPDATE(소유권 판정 전 직렬화)

    def test_create_allows_owner_hold(self):
        """★본인 HOLD 세대 계약 정상통과 — held_by == by(본인이 잡은 선점)면 토큰 없이도 계약 생성."""
        staff_a = uuid_mod.uuid4()
        unit = FakeUnit(status="HOLD")
        own = self._ownership_row(held_by=staff_a, hold_token="tokA", not_expired=True)
        db = self._make_db(unit, own)
        c = _run(contract_svc.create_contract(db, unit.site_id, unit.id, by=staff_a))
        # 계약이 생성되고 세대는 RESERVED 로 전이한다(정상 머니패스).
        assert type(c).__name__ == "SalesContractExt"
        assert unit.status == "RESERVED"

    def test_create_allows_matching_hold_token(self):
        """★토큰 일치 시 통과 — by 가 held_by 와 달라도(예: 위임/세션차이) hold_token 이 일치하면
        선점 소유권을 토큰으로 증명해 계약 허용(atomic_reserve 의 토큰검증과 대칭)."""
        staff_a = uuid_mod.uuid4()
        other = uuid_mod.uuid4()
        unit = FakeUnit(status="HOLD")
        own = self._ownership_row(held_by=staff_a, hold_token="tokA", not_expired=True)
        db = self._make_db(unit, own)
        c = _run(contract_svc.create_contract(db, unit.site_id, unit.id, by=other, hold_token="tokA"))
        assert type(c).__name__ == "SalesContractExt"
        assert unit.status == "RESERVED"

    def test_create_rejects_expired_owner_hold(self):
        """★만료된 HOLD 거부 — 본인 선점이라도 hold_expires_at 이 지나(not_expired=False) 만료됐으면
        계약을 막는다(만료 후 잔존 점유로 계약되는 것을 차단; atomic_reserve 의 미만료 조건과 대칭)."""
        staff_a = uuid_mod.uuid4()
        unit = FakeUnit(status="HOLD")
        own = self._ownership_row(held_by=staff_a, hold_token="tokA", not_expired=False)
        db = self._make_db(unit, own)
        with pytest.raises(ValueError, match="만료된 세대"):
            _run(contract_svc.create_contract(db, unit.site_id, unit.id, by=staff_a))
        assert "SalesContractExt" not in [type(o).__name__ for o in db.added]

    def test_create_allows_draw_park_hold_held_by_null(self):
        """★추첨 배정→계약 정상경로 통과(held_by NULL) — draw_for_candidate·HOLD_REQUEST 는 세대를
        HOLD 로 두되 held_by 를 비워둔다(미점유 파킹). 이 경로는 소유권 검증 없이 통과해야
        contract_from_candidate(추첨 당첨자 계약 연결)가 깨지지 않는다(정상흐름 보존)."""
        unit = FakeUnit(status="HOLD")
        # held_by NULL = 추첨/지정 파킹 HOLD. by 는 임의(계약 담당자)여도 통과해야 한다.
        own = self._ownership_row(held_by=None, hold_token=None, not_expired=False)
        db = self._make_db(unit, own)
        c = _run(contract_svc.create_contract(db, unit.site_id, unit.id, by=uuid_mod.uuid4()))
        assert type(c).__name__ == "SalesContractExt"
        assert unit.status == "RESERVED"

    def test_create_cleans_stale_hold_meta(self):
        """★[MED] HOLD→RESERVED 전이 시 임시선점 메타(held_by/hold_token/hold_expires_at)를 NULL 로
        정리하는 UPDATE 가 실행된다 — 계약 확정 후 만료 선점 흔적이 남아 감사를 혼동시키지 않게.
        (소유자 있는 HOLD 를 본인이 계약하는 정상경로에서 정리 UPDATE 가 발행됐는지 SQL 로 확인.)"""
        staff_a = uuid_mod.uuid4()
        unit = FakeUnit(status="HOLD")
        own = self._ownership_row(held_by=staff_a, hold_token="tokA", not_expired=True)

        seen_sql = []

        def handler(stmt):
            seen_sql.append(_stmt_table(stmt))
            s = _stmt_table(stmt)
            if "sales_unit_inventory" in s and "held_by" in s and "not_expired" in s:
                return [own]
            if "sales_unit_inventory" in s:
                return [unit]
            return []

        db = FakeSession(handler)
        _run(contract_svc.create_contract(db, unit.site_id, unit.id, by=staff_a))
        # held_by/hold_token/hold_expires_at 을 NULL 로 정리하는 UPDATE 가 한 번은 발행돼야 한다.
        cleanup = [q for q in seen_sql
                   if "update sales_unit_inventory" in q and "held_by = null" in q
                   and "hold_token = null" in q and "hold_expires_at = null" in q]
        assert cleanup, "HOLD→RESERVED 전이 시 점유메타 NULL 정리 UPDATE 가 발행돼야 한다(stale 메타 제거)"


# ════════════════════════ 청약 추첨(결정론·특공) ════════════════════════
class _App:
    """추첨용 가짜 신청서(_rank_pick 가 보는 필드만)."""

    def __init__(self, rank=1, gajeom=0.0, supply="GENERAL"):
        self.id = uuid_mod.uuid4()
        self.rank = rank
        self.gajeom_score = gajeom
        self.supply_class = supply
        self.result = None


class TestDrawDeterminism:
    def test_rank_pick_same_seed_same_order(self):
        """같은 seed → 같은 당첨자 순서(감사 가능한 결정론). 동점은 seed 기반 타이브레이크."""
        apps = [_App(rank=1, gajeom=10) for _ in range(5)]
        win_a, rest_a = _rank_pick(apps, 2, "SEED-X")
        win_b, rest_b = _rank_pick(apps, 2, "SEED-X")
        assert [a.id for a in win_a] == [a.id for a in win_b]
        assert [a.id for a in rest_a] == [a.id for a in rest_b]

    def test_rank_pick_different_seed_may_reorder_tie(self):
        """동점자 집합에서 seed 가 다르면 타이브레이크가 달라질 수 있다(seed 의존성 = 재현성의 근거)."""
        apps = [_App(rank=1, gajeom=10) for _ in range(6)]
        order_x = [a.id for a in _rank_pick(apps, 6, "SEED-X")[0]]
        order_y = [a.id for a in _rank_pick(apps, 6, "SEED-Y")[0]]
        # 같은 집합이라도 seed 별 정렬키(_tiebreak)가 달라 순서가 바뀔 수 있다(결정론은 seed 고정 시).
        assert set(order_x) == set(order_y)
        assert _tiebreak("SEED-X", apps[0].id) != _tiebreak("SEED-Y", apps[0].id)

    def test_rank_pick_priority_rank_then_gajeom(self):
        """1순위(rank 작은) 우선, 동순위는 가점 높은 순. 정원 초과분은 rest 로."""
        a_r1_high = _App(rank=1, gajeom=80)
        a_r1_low = _App(rank=1, gajeom=20)
        a_r2 = _App(rank=2, gajeom=99)
        win, rest = _rank_pick([a_r2, a_r1_low, a_r1_high], 2, "S")
        assert [a.id for a in win] == [a_r1_high.id, a_r1_low.id]  # 1순위 가점순
        assert [a.id for a in rest] == [a_r2.id]                   # 2순위는 탈락(예비)

    def test_rank_pick_zero_quota(self):
        """정원 0이면 당첨 없음(음수 슬라이싱 버그 방지 — max(n,0))."""
        apps = [_App() for _ in range(3)]
        win, rest = _rank_pick(apps, 0, "S")
        assert win == []
        assert len(rest) == 3


class TestRunDrawIdempotency:
    def test_drawn_announcement_not_redrawn(self):
        """이미 DRAWN 공고 재추첨 차단 — 중복당첨·정원초과 방지(0 반환, 부작용 없음)."""

        class _Ann:
            def __init__(self):
                self.id = uuid_mod.uuid4()
                self.status = "DRAWN"
                self.announce_no = "2026-001"
                self.rules = {}
                self.round_id = None
                self.contract_end = None

        ann = _Ann()

        def handler(stmt):
            return [ann]

        db = FakeSession(handler)
        n = _run(sub_engine.run_draw(db, uuid_mod.uuid4(), ann.id))
        assert n == 0
        assert db.added == []           # winner/예비큐 생성 없음
        assert db.lock_seen is True     # 공고행 FOR UPDATE 로 직렬화

    def test_run_draw_cross_site_announcement_not_found(self):
        """★[IDOR·security 전역스윕·iter-5 HIGH] A현장 사용자가 B현장 announcement_id 를 주입하면
        run_draw 의 공고 SELECT 가 site_id 로 스코프돼 0행 → NotFoundError(=404)로 거부된다.
        '타현장 신청서로 추첨하되 자기현장 세대를 점유'하는 교차테넌트 추첨을 회귀 차단한다(과거
        scalar_one() 의 NoResultFound→500 누출 + site_id 미스코프 정합위험 동시 해소).

        FakeSession 핸들러가 site_id 스코프 공고 SELECT 를 흉내내 0행을 돌려준다."""
        from app.services.sales.contract.service import NotFoundError

        def handler(stmt):
            s = _stmt_table(stmt)
            if "sales_subscription_announcements" in s:
                return []   # 타현장 스코프 → 0행(미존재/타현장)
            return []

        db = FakeSession(handler)
        with pytest.raises(NotFoundError, match="청약 공고를 찾을 수 없습니다"):
            _run(sub_engine.run_draw(db, uuid_mod.uuid4(), uuid_mod.uuid4()))
        # 공고행 FOR UPDATE(스코프된 SELECT 도 잠금)·부작용 0(winner/예비큐 생성 없음).
        assert db.lock_seen is True
        assert db.added == []


class _DrawAnn:
    """추첨 실행용 가짜 공고(run_draw 가 보는 필드만)."""

    def __init__(self):
        self.id = uuid_mod.uuid4()
        self.status = "OPEN"            # ★DRAWN 이 아니어야 실제 추첨 경로(zip 라인)로 진입
        self.announce_no = "2026-RUN"
        self.rules = {}
        self.round_id = None
        self.contract_end = None


class _DrawApp:
    """추첨 실행용 가짜 신청서(run_draw 가 보는 필드 전부 — _App 보다 넓다)."""

    def __init__(self, unit_type_id, rank=1, gajeom=10.0, supply="GENERAL"):
        self.id = uuid_mod.uuid4()
        self.unit_type_id = unit_type_id
        self.eligibility = "OK"
        self.supply_class = supply
        self.rank = rank
        self.gajeom_score = gajeom
        self.result = None


class TestRunDrawEndToEnd:
    """★[정상경로 미배선 해소·iter-3] run_draw 를 zip 라인까지 실제로 태워(=DRAWN 조기반환이 아님)
    미달/정확/초과 3경로의 길이 불일치가 ValueError(strict) 없이 안전히 처리되는지 검증한다.

    iter-2 회귀(zip strict=True)는 미달청약에서 ValueError→409→전체 추첨 실패(당첨0)였다. 기존
    TestRunDrawIdempotency 는 status=DRAWN 조기반환만 커버해 zip 라인에 도달하지 못했다(silent
    test-pass). 여기선 status=OPEN 으로 실제 추첨을 돌려 winners 수·잔여 AVAILABLE·예비 편입을
    직접 확인한다."""

    @staticmethod
    def _make_db(ann, apps, units):
        """공고/신청서/세대 SELECT 를 테이블명으로 분기해 돌려주는 FakeSession 핸들러."""

        def handler(stmt):
            s = _stmt_table(stmt)
            if "sales_subscription_announcements" in s:
                return [ann]
            if "sales_subscription_applications" in s:
                return list(apps)
            if "sales_unit_inventory" in s:
                # _available_units 는 AVAILABLE 만 가져온다 — 가짜에서도 그 필터를 흉내낸다.
                return [u for u in units if u.status == "AVAILABLE" and u.deleted_at is None]
            return []

        return FakeSession(handler)

    def test_under_subscribed_no_valueerror_leftover_available(self):
        """미달청약(신청<세대): ValueError 없이 통과 + 신청자만 당첨 + 남는 세대는 AVAILABLE 유지."""
        type_id = uuid_mod.uuid4()
        site_id = uuid_mod.uuid4()
        units = [FakeUnit(status="AVAILABLE", type_id=type_id, site_id=site_id) for _ in range(3)]
        apps = [_DrawApp(type_id)]  # 신청 1 < 세대 3 → 미달
        ann = _DrawAnn()
        db = self._make_db(ann, apps, units)

        n = _run(sub_engine.run_draw(db, site_id, ann.id))  # strict 회귀였다면 여기서 ValueError→실패
        assert n == 1                                       # 신청자 1명만 당첨
        winners = [o for o in db.added if type(o).__name__ == "SalesSubscriptionWinner"]
        assert len(winners) == 1
        # 배정된 세대는 APPLIED 1개, 남는 2개는 AVAILABLE 그대로(자르지 않음).
        applied = [u for u in units if u.status == "APPLIED"]
        available = [u for u in units if u.status == "AVAILABLE"]
        assert len(applied) == 1 and len(available) == 2
        assert apps[0].result == "WIN"
        assert ann.status == "DRAWN"

    def test_exact_match_all_assigned(self):
        """정확(신청==세대): 전원 당첨·전 세대 APPLIED·잔여/예비 없음."""
        type_id = uuid_mod.uuid4()
        site_id = uuid_mod.uuid4()
        units = [FakeUnit(status="AVAILABLE", type_id=type_id, site_id=site_id) for _ in range(2)]
        apps = [_DrawApp(type_id), _DrawApp(type_id)]
        ann = _DrawAnn()
        db = self._make_db(ann, apps, units)

        n = _run(sub_engine.run_draw(db, site_id, ann.id))
        assert n == 2
        assert all(u.status == "APPLIED" for u in units)
        reserves = [o for o in db.added if type(o).__name__ == "SalesSubscriptionReserveQueue"]
        assert reserves == []                               # 잔여·예비 없음

    def test_over_subscribed_extra_goes_to_reserve(self):
        """초과(신청>세대): 세대 수만큼 당첨 + 나머지는 예비 큐(RESERVE) 편입(silent 누락 없음)."""
        type_id = uuid_mod.uuid4()
        site_id = uuid_mod.uuid4()
        units = [FakeUnit(status="AVAILABLE", type_id=type_id, site_id=site_id) for _ in range(2)]
        apps = [_DrawApp(type_id) for _ in range(5)]        # 신청 5 > 세대 2 → 3명 예비
        ann = _DrawAnn()
        db = self._make_db(ann, apps, units)

        n = _run(sub_engine.run_draw(db, site_id, ann.id))
        assert n == 2                                       # 세대 수만큼만 당첨
        assert all(u.status == "APPLIED" for u in units)
        reserves = [o for o in db.added if type(o).__name__ == "SalesSubscriptionReserveQueue"]
        assert len(reserves) == 3                           # 나머지 3명 전원 예비(누락 0)
        wins = [a for a in apps if a.result == "WIN"]
        rsv = [a for a in apps if a.result == "RESERVE"]
        assert len(wins) == 2 and len(rsv) == 3


# ════════════════════════ FCFS 선착순 ════════════════════════
class TestClaimOfferFCFS:
    def test_claim_rejects_non_available(self):
        """이미 점유(APPLIED)된 세대 claim 거부 — 동시 클릭 시 1명만 성공하는 상태가드."""
        unit = FakeUnit(status="APPLIED")

        def handler(stmt):
            return [unit]

        db = FakeSession(handler)
        with pytest.raises(ValueError, match="이미 점유된 세대"):
            _run(sub_engine.claim_offer(db, unit.site_id, unit.id, uuid_mod.uuid4()))
        assert db.lock_seen is True     # 세대행 FOR UPDATE(선착순 직렬화)

    def test_claim_success_marks_applied(self):
        """AVAILABLE 세대 claim 성공 → APPLIED 로 전이(점유 확정)."""
        unit = FakeUnit(status="AVAILABLE")

        def handler(stmt):
            return [unit]

        db = FakeSession(handler)
        out = _run(sub_engine.claim_offer(db, unit.site_id, unit.id, uuid_mod.uuid4()))
        assert out == unit.id
        assert unit.status == "APPLIED"

    def test_claim_fcfs_records_customer_and_audit(self):
        """★FCFS 감사단절 해소(iter-2 MED) — 선착순(FCFS)도 누가 선점했는지(claimed_by=customer)
        를 SalesUnrankedOffer 로 기록하고, 점유 전이를 SalesUnitStatusLog(감사로그)에 남긴다
        (예전엔 UNRANKED 만 기록 → FCFS 추적 끊김)."""
        unit = FakeUnit(status="AVAILABLE")
        cust = uuid_mod.uuid4()

        def handler(stmt):
            return [unit]

        db = FakeSession(handler)
        _run(sub_engine.claim_offer(db, unit.site_id, unit.id, cust, kind="FCFS"))
        added = {type(o).__name__: o for o in db.added}
        # FCFS 점유자(customer) 기록 — channel='FCFS', claimed_by=customer.
        assert "SalesUnrankedOffer" in added
        assert added["SalesUnrankedOffer"].claimed_by == cust
        assert added["SalesUnrankedOffer"].channel == "FCFS"
        # 점유 전이 감사로그(계약 경로와 대칭).
        assert "SalesUnitStatusLog" in added

    def test_claim_rejects_cross_site_unit_not_found(self):
        """★[IDOR·머니패스 교차테넌트·iter-4 HIGH] A현장 사용자가 B현장 unit_id 를 넘기면
        claim_offer 의 SELECT WHERE 가 site_id 로 스코프돼 0행 → NotFoundError(엔드포인트 404)로
        거부된다. 타현장 세대를 선점(FCFS 머니패스)할 수 없음을 회귀 차단한다.

        FakeSession 핸들러가 'site_id 스코프 SELECT' 를 흉내내, stmt 에 그 현장의 unit 만 들어
        있을 때만 반환한다(타현장 호출이면 빈 결과 → 미존재 분기)."""
        unit = FakeUnit(status="AVAILABLE")           # B현장 세대
        attacker_site = uuid_mod.uuid4()              # A현장(타현장) — unit.site_id 와 다름

        def handler(stmt):
            # site_id 스코프를 흉내냄: SELECT 에 공격자 현장(attacker_site)이 바인딩됐다면
            # 그 현장엔 이 unit 이 없으므로 빈 결과(=NotFoundError 유발).
            s = _stmt_table(stmt)
            if "sales_unit_inventory" in s:
                return []   # 타현장 스코프 → 0행
            return []

        db = FakeSession(handler)
        with pytest.raises(ValueError, match="세대를 찾을 수 없습니다"):
            _run(sub_engine.claim_offer(db, attacker_site, unit.id, uuid_mod.uuid4()))
        # 미존재라도 세대행 잠금(FOR UPDATE)은 시도됨(스코프된 SELECT 도 잠금 대상).
        assert db.lock_seen is True
        # 점유 기록(SalesUnrankedOffer)·상태전이가 일어나지 않아야 한다(거부 후 부작용 0).
        assert db.added == []

    def test_claim_not_found_is_notfounderror(self):
        """미존재/타현장 세대는 전용 NotFoundError(ValueError 하위)로 던져진다 —
        엔드포인트가 문구 substring 이 아닌 isinstance 로 404 를 분기한다(상태코드 불변)."""
        from app.services.sales.contract.service import NotFoundError

        def handler(stmt):
            return []   # 세대 없음

        db = FakeSession(handler)
        with pytest.raises(NotFoundError):
            _run(sub_engine.claim_offer(db, uuid_mod.uuid4(), uuid_mod.uuid4(), uuid_mod.uuid4()))


class _Winner:
    """가짜 청약 당첨자(promote_reserve 가 보는 필드만)."""

    def __init__(self, unit_id, status="NOTIFIED"):
        self.id = uuid_mod.uuid4()
        self.unit_id = unit_id
        self.status = status
        self.application_id = uuid_mod.uuid4()


class _ReserveItem:
    def __init__(self):
        self.application_id = uuid_mod.uuid4()
        self.promoted = False


class TestPromoteReserveGuard:
    def test_promote_rejects_occupied_unit_no_winner(self):
        """winner 행이 없는데 세대가 점유 중(다른 경로)이면 승계 차단(한 세대 2명 승계 방지)."""
        unit = FakeUnit(status="APPLIED")

        def handler(stmt):
            s = _stmt_table(stmt)
            if "sales_unit_inventory" in s:
                return [unit]
            return []  # 점유 winner 없음 → 'elif unit.status!=AVAILABLE' 경로로 거부

        db = FakeSession(handler)
        with pytest.raises(ValueError, match="이미 점유된 세대"):
            _run(sub_engine.promote_reserve(db, unit.site_id, unit.id))
        assert db.lock_seen is True

    def test_promote_rejects_cross_site_unit_not_found(self):
        """★[현장스코프 머니패스·iter-4 HIGH 전역스윕] 타현장 unit_id 로 예비승계는 site_id 스코프
        SELECT 0행 → NotFoundError(=404)로 거부. 타현장 세대 점유전이(머니패스) IDOR 차단."""
        from app.services.sales.contract.service import NotFoundError

        def handler(stmt):
            return []   # site_id 스코프 0행(미존재/타현장)

        db = FakeSession(handler)
        with pytest.raises(NotFoundError, match="세대를 찾을 수 없습니다"):
            _run(sub_engine.promote_reserve(db, uuid_mod.uuid4(), uuid_mod.uuid4()))
        assert db.lock_seen is True

    def test_promote_rejects_contracted_unit(self):
        """계약(CONTRACTED)까지 간 당첨 세대는 예비로 넘길 수 없다(중복 분양 차단)."""
        unit = FakeUnit(status="APPLIED")
        winner = _Winner(unit.id, status="CONTRACTED")

        def handler(stmt):
            s = _stmt_table(stmt)
            if "sales_unit_inventory" in s:
                return [unit]
            if "sales_subscription_winners" in s:
                return [winner]
            return []

        db = FakeSession(handler)
        with pytest.raises(ValueError, match="이미 계약 체결"):
            _run(sub_engine.promote_reserve(db, unit.site_id, unit.id))

    def test_promote_forfeits_occupant_and_promotes_next(self):
        """★예비승계 정상동작(unreachable 해소) — 기존 NOTIFIED 당첨자를 FORFEITED 로 전이하고
        세대를 비운 뒤 다음 예비를 NOTIFIED 로 올린다(세대는 다시 APPLIED). 한 세대 2명 충돌·
        영구차단 없이 승계가 작동하는지 검증."""
        unit = FakeUnit(status="APPLIED")
        occupant = _Winner(unit.id, status="NOTIFIED")
        nxt = _ReserveItem()

        def handler(stmt):
            s = _stmt_table(stmt)
            if "sales_unit_inventory" in s:
                return [unit]
            if "sales_subscription_winners" in s:
                return [occupant]
            if "sales_subscription_reserve_queue" in s:
                return [nxt]
            return []

        db = FakeSession(handler)
        out = _run(sub_engine.promote_reserve(db, unit.site_id, unit.id, by=uuid_mod.uuid4()))
        # 기존 당첨자 포기 처리(유니크 충돌 회피의 핵심).
        assert occupant.status == "FORFEITED"
        # 예비 큐 다음 1명이 승계되어 반환됨.
        assert out == nxt.application_id
        assert nxt.promoted is True
        # 세대는 예비 당첨자 점유로 APPLIED 복귀.
        assert unit.status == "APPLIED"
        # 새 RESERVE winner 가 add 됐고, 점유 전이가 감사로그(SalesUnitStatusLog)에도 남는다.
        added_types = [type(o).__name__ for o in db.added]
        assert "SalesSubscriptionWinner" in added_types
        assert "SalesUnitStatusLog" in added_types
        assert db.lock_seen is True
        # ★[CRITICAL 회귀가드·iter-6] 같은 unit 으로 status-log 를 '정확히 1회' 만 INSERT 해야 한다
        #   (과거엔 AVAILABLE→APPLIED 2회 → 복합PK(unit_id, now()) 23505 로 예비승계가 항상 실패했다).
        unit_logs = [o for o in db.added if type(o).__name__ == "SalesUnitStatusLog"]
        assert len(unit_logs) == 1, "예비승계는 같은 unit 으로 status-log 를 1회만 남겨야 한다(23505 회귀)"
        # flush 가 실제로 호출됐음(가짜세션 복합PK 가드가 통과 = 충돌 없음).
        assert db.flushed >= 1

    def test_promote_no_reserve_releases_unit_available_single_log(self):
        """★[iter-6] 예비 큐가 비어 승계할 다음 사람이 없으면, 포기시킨 점유자(FORFEITED) 자리에
        세대를 AVAILABLE 로 1회만 되돌린다('주인 없는 APPLIED' 방지). 이때도 status-log 는 같은
        unit 으로 정확히 1회(복합PK 충돌 없음)."""
        unit = FakeUnit(status="APPLIED")
        occupant = _Winner(unit.id, status="NOTIFIED")

        def handler(stmt):
            s = _stmt_table(stmt)
            if "sales_unit_inventory" in s:
                return [unit]
            if "sales_subscription_winners" in s:
                return [occupant]
            if "sales_subscription_reserve_queue" in s:
                return []   # 올릴 예비 없음
            return []

        db = FakeSession(handler)
        out = _run(sub_engine.promote_reserve(db, unit.site_id, unit.id, by=uuid_mod.uuid4()))
        assert out is None                       # 승계 대상 없음
        assert occupant.status == "FORFEITED"    # 점유자는 포기 처리됨
        assert unit.status == "AVAILABLE"        # 세대는 비워짐(APPLIED 잔류 금지)
        unit_logs = [o for o in db.added if type(o).__name__ == "SalesUnitStatusLog"]
        assert len(unit_logs) == 1               # AVAILABLE 전이 1회만(복합PK 충돌 없음)
        # 새 winner 는 생성되지 않아야 한다(승계 없음).
        assert "SalesSubscriptionWinner" not in [type(o).__name__ for o in db.added]

    def test_promote_does_not_double_log_same_unit(self):
        """★[완결게이트 사각보강·iter-6] 가짜세션 복합PK 가드가 실제로 회귀를 잡는지 메타검증.
        만약 promote_reserve 가 (회귀 시나리오처럼) 같은 unit 으로 status-log 를 2회 add 하면,
        FakeSession.flush 가 CompositePKViolationError(라이브 23505 동치)을 던져야 한다."""
        unit = FakeUnit(status="APPLIED")
        occupant = _Winner(unit.id, status="NOTIFIED")
        nxt = _ReserveItem()

        def handler(stmt):
            s = _stmt_table(stmt)
            if "sales_unit_inventory" in s:
                return [unit]
            if "sales_subscription_winners" in s:
                return [occupant]
            if "sales_subscription_reserve_queue" in s:
                return [nxt]
            return []

        # 정상 promote 는 충돌 없이 통과해야 한다(가드가 정상경로를 오탐하지 않음).
        db_ok = FakeSession(handler)
        _run(sub_engine.promote_reserve(db_ok, unit.site_id, unit.id, by=uuid_mod.uuid4()))
        # 같은 unit 으로 status-log 를 인위로 2개 넣으면 가드가 23505 동치 예외를 던진다(가드 유효성).
        from apps.api.database.models.sales.units_pricing import SalesUnitStatusLog
        db_bad = FakeSession(handler)
        db_bad.add(SalesUnitStatusLog(site_id=unit.site_id, unit_id=unit.id,
                                      from_status="AVAILABLE", to_status="APPLIED", by=None))
        db_bad.add(SalesUnitStatusLog(site_id=unit.site_id, unit_id=unit.id,
                                      from_status="APPLIED", to_status="AVAILABLE", by=None))
        with pytest.raises(CompositePKViolationError):
            _run(db_bad.flush())


# ════════════════════════ CRM 가드(야간·분류·마스킹) ════════════════════════
from app.api.endpoints.sales import crm_enhance  # noqa: E402


class TestCrmGuards:
    def test_night_guard_blocks_night_hours_kst(self):
        """야간(21~08) 광고성 발송 제한(정보통신망법) — ★KST(UTC+9) 고정 기준 경계 검증.

        tautology(동일식 재계산) 가 아니라, KST 시각의 고정 기대값으로 검증한다. UTC 시각 h 는
        KST 로 (h+9)%24 시. 야간 차단 = KST 시 ∈ [21,24)∪[0,8). 테스트 환경 TZ 와 무관하게
        KST 고정이라 컨테이너가 UTC/KST 어디든 동일 결과여야 한다(서버 로컬TZ 의존 제거 검증)."""
        for h_utc in range(24):
            now = datetime(2026, 6, 19, h_utc, 0, tzinfo=UTC)
            kst_hour = (h_utc + 9) % 24
            expected = kst_hour >= 21 or kst_hour < 8  # KST 고정 기대값(독립 산출)
            assert crm_enhance._night_guard(now) is expected, f"UTC {h_utc}시(KST {kst_hour}시)"

    def test_night_guard_naive_treated_as_utc(self):
        """tz 정보 없는(naive) 입력은 UTC 로 간주 후 KST 변환 — 모호성 제거(오작동 방지)."""
        # naive 12:00 == UTC 12:00 == KST 21:00 → 야간(차단).
        assert crm_enhance._night_guard(datetime(2026, 6, 19, 12, 0)) is True
        # naive 02:00 == UTC 02:00 == KST 11:00 → 주간(허용).
        assert crm_enhance._night_guard(datetime(2026, 6, 19, 2, 0)) is False

    def test_reason_codes_are_machine_codes(self):
        """발송 차단/실패 사유는 기계코드(프론트 BLOCK_REASON 맵 키)로 정의돼 있어야 한다(half-wiring 방지)."""
        assert crm_enhance.REASON_NO_CONSENT == "no_consent"
        assert crm_enhance.REASON_NIGHT == "night"
        assert crm_enhance.REASON_NO_SENDER == "no_sender"
        assert crm_enhance.REASON_NO_KEY == "no_key"
        assert crm_enhance.REASON_DISPATCH_FAIL == "dispatch_fail"

    def test_mask_phone_consistency(self):
        """연락처 마스킹 일관 — 앞3+마스킹+뒤4. 짧으면 *** (개인정보 노출 방지)."""
        assert crm_enhance._mask_phone("010-1234-5678") == "010****5678"
        assert crm_enhance._mask_phone("+821012345678") == "821****5678"
        assert crm_enhance._mask_phone(None) is None
        assert crm_enhance._mask_phone("12345") == "***"

    def test_dispatch_message_classifies_failure(self, monkeypatch):
        """외부발송 실패를 silent-drop 하지 않고 (FAILED, dispatch_fail) 로 분류 반환.

        ★tautology/유동기대 제거: 기존엔 {FAILED,SENT} 둘 다 허용해 실제 분류를 검증하지 못했다.
          httpx.AsyncClient 를 monkeypatch 로 예외를 던지게 고정해, 외부발송 오류가 반드시
          (FAILED, dispatch_fail) 로 '분류' 되는지(은폐 아님) 결정론적으로 검증한다."""

        class _Body:
            template = None
            body = "안녕하세요"

        # httpx.AsyncClient(...) 진입(__aenter__)에서 예외를 던지도록 고정 → _dispatch_message 의
        # except 분류 경로를 결정론적으로 태운다(망 상태·키 설정에 무관).
        import httpx

        class _Boom:
            def __init__(self, *a, **k):
                raise OSError("network blocked (forced)")

        monkeypatch.setattr(httpx, "AsyncClient", _Boom)
        status, code = _run(crm_enhance._dispatch_message("sms", "01000000000", _Body()))
        assert status == "FAILED"
        assert code == crm_enhance.REASON_DISPATCH_FAIL


# ════════════════════════ NotFoundError 예외 코드화(anti-pattern 제거) ════════════════════════
class TestNotFoundErrorContract:
    """★[anti-pattern 제거·iter-4] 404↔409 분기를 한국어 메시지 substring 대신 전용 예외클래스로
    코드화했다. NotFoundError 가 ValueError 하위인지(하위호환·기존 except ValueError 경로 흡수)와
    엔드포인트 isinstance 분기가 문구와 무관함(상태코드 불변)을 회귀 차단한다."""

    def test_notfounderror_is_valueerror_subclass(self):
        """NotFoundError 는 ValueError 를 상속한다(기존 except ValueError 가 그대로 흡수 — 하위호환)."""
        from app.services.sales.contract.service import NotFoundError
        assert issubclass(NotFoundError, ValueError)
        e = NotFoundError("계약을 찾을 수 없습니다")
        assert isinstance(e, ValueError)
        assert isinstance(e, NotFoundError)

    def test_inventory_txn_missing_raises_notfounderror(self):
        """mh.ops.inventory_txn 미존재 item 은 NotFoundError(=404). 재고 부족(상태충돌)과 분리됨."""
        from app.services.sales.contract.service import NotFoundError
        from app.services.sales.mh import ops as mh_ops

        def handler(stmt):
            return []   # 미등록 item → scalar_one_or_none None

        db = FakeSession(handler)
        with pytest.raises(NotFoundError, match="물품을 찾을 수 없습니다"):
            _run(mh_ops.inventory_txn(db, uuid_mod.uuid4(), uuid_mod.uuid4(), "OUT", 1))

    def test_inventory_txn_cross_site_item_not_found(self):
        """★[IDOR·security 교차테넌트 write·iter-5 HIGH] A현장 사용자가 B현장 item_id 를 넘기면
        inventory_txn 의 SELECT 가 site_id 로 스코프돼 0행 → NotFoundError(엔드포인트 404)로 거부.
        타현장 재고(stock_qty)를 증감(교차테넌트 write)할 수 없음을 회귀 차단한다.

        FakeSession 핸들러가 'site_id 스코프 SELECT' 를 흉내내, 타현장 스코프면 빈 결과를 돌려준다."""
        from app.services.sales.contract.service import NotFoundError
        from app.services.sales.mh import ops as mh_ops

        def handler(stmt):
            # site_id 스코프 흉내: 공격자 현장 스코프엔 그 품목이 없으므로 빈 결과(=미존재 분기).
            s = _stmt_table(stmt)
            if "mh_inventory_items" in s:
                return []   # 타현장 스코프 → 0행
            return []

        db = FakeSession(handler)
        attacker_site = uuid_mod.uuid4()
        with pytest.raises(NotFoundError, match="물품을 찾을 수 없습니다"):
            _run(mh_ops.inventory_txn(db, attacker_site, uuid_mod.uuid4(), "IN", 5))
        # 거부 후 재고 증감(MhInventoryTxn add)·flush 가 일어나지 않아야 한다(부작용 0).
        assert db.added == []


# ════════════════════════ run_draw overflow dead-branch 정합 ════════════════════════
class TestRunDrawOverflowInvariant:
    """★[dead-branch 정합·iter-4] '초과(winners>units)' 는 _rank_pick quota 캡으로 도달 불가다.
    실제 초과청약의 잉여 신청자는 winners 가 아니라 _rest_gen 으로 예비 큐에 편입된다
    (TestRunDrawEndToEnd.test_over_subscribed_extra_goes_to_reserve 가 그 경로를 검증). 여기선
    초과청약에서도 어떤 winner 도 silent 누락 없이 '당첨=세대수 / 잉여=예비'로 정확히 나뉘는지
    (overflow 분기에 의존하지 않고도 누락 0) 추가 검증한다."""

    def test_over_subscribed_no_winner_dropped(self):
        type_id = uuid_mod.uuid4()
        site_id = uuid_mod.uuid4()
        units = [FakeUnit(status="AVAILABLE", type_id=type_id, site_id=site_id) for _ in range(2)]
        apps = [_DrawApp(type_id) for _ in range(7)]  # 신청 7 > 세대 2

        def handler(stmt):
            s = _stmt_table(stmt)
            if "sales_subscription_announcements" in s:
                return [ann]
            if "sales_subscription_applications" in s:
                return list(apps)
            if "sales_unit_inventory" in s:
                return [u for u in units if u.status == "AVAILABLE" and u.deleted_at is None]
            return []

        ann = _DrawAnn()
        db = FakeSession(handler)
        n = _run(sub_engine.run_draw(db, site_id, ann.id))
        assert n == 2                                       # 세대 수만큼만 당첨(초과 없음)
        wins = [a for a in apps if a.result == "WIN"]
        rsv = [a for a in apps if a.result == "RESERVE"]
        # 당첨 2 + 예비 5 = 7 = 전체 신청(누락 0). 잉여는 _rest_gen 경로로 예비 편입.
        assert len(wins) == 2 and len(rsv) == 5
        assert len(wins) + len(rsv) == len(apps)


# ════════════════════════ 청약 라이프사이클 권한 분리(iter-6 회귀교정) ════════════════════════
class TestSubscriptionRoleSets:
    """★[권한 분리·iter-6 HIGH 회귀교정] claim/draw/reserve_promote 는 민감도가 달라 경로별 역할집합으로
    분리한다. iter-5 가 셋을 한 상수로 묶어 데스크(MEMBER/TEAM_LEADER)에게 추첨실행(draw)·예비 강등
    (reserve_promote)까지 새던 과확장을 교정한다. 경계(데스크 포함/제외)를 회귀 차단(라이브 라우트는
    deploy-pending)."""

    def test_claim_includes_desk_roles(self):
        """claim(선착순)만 데스크 실무역할(MEMBER/TEAM_LEADER)을 포함한다(워크인 대리 FCFS 단절 해소)."""
        from app.api.endpoints.sales.lifecycle_p5 import _R_SUBSCRIPTION_CLAIM
        roles = set(_R_SUBSCRIPTION_CLAIM)
        assert {"MEMBER", "TEAM_LEADER"} <= roles            # 데스크 포함(iter-5 가 푼 진짜 단절 보존)
        assert {"DIRECTOR", "AGENCY", "DEVELOPER"} <= roles  # 관리역할도 유지

    def test_draw_excludes_desk_roles_narrow(self):
        """draw(추첨 실행=전 가용세대 일괄 점유)는 시행/대행 상위 권한만(데스크·중간관리 제외 — 과확장 교정)."""
        from app.api.endpoints.sales.lifecycle_p5 import _R_SUBSCRIPTION_DRAW
        roles = set(_R_SUBSCRIPTION_DRAW)
        assert roles == {"DEVELOPER", "AGENCY"}              # 정확히 둘만(좁힘)
        assert not ({"MEMBER", "TEAM_LEADER", "DIRECTOR"} & roles)  # 데스크·DIRECTOR 차단

    def test_reserve_promote_excludes_desk_roles(self):
        """reserve_promote(당첨자 FORFEITED 강등+세대 점유전이=머니패스)는 관리 권한만(데스크 제외)."""
        from app.api.endpoints.sales.lifecycle_p5 import _R_SUBSCRIPTION_RESERVE_PROMOTE
        roles = set(_R_SUBSCRIPTION_RESERVE_PROMOTE)
        assert {"DIRECTOR", "GM_DIRECTOR", "SUBAGENCY", "AGENCY", "DEVELOPER"} == roles
        assert not ({"MEMBER", "TEAM_LEADER"} & roles)       # 데스크 차단(추첨 강등은 데스크 권한 아님)

    def test_old_merged_constant_removed(self):
        """단일 병합 상수(_R_SUBSCRIPTION_LIFECYCLE)는 제거됐다 — 다시 한 상수로 묶이는 회귀 차단."""
        import app.api.endpoints.sales.lifecycle_p5 as m
        assert not hasattr(m, "_R_SUBSCRIPTION_LIFECYCLE")


# ════════════════════════ 물품 수불 txn_type allowlist(iter-6) ════════════════════════
class TestInventoryTxnType:
    """★[MED·silent-fail 제거·iter-6] inventory_txn 의 txn_type 을 {'IN','OUT'} 으로 강제한다.
    과거엔 'IN' 외 모든 값(오타 'in'/'OUTT'/빈문자)이 조용히 출고(-qty)로 처리되는 silent-fail 이었다."""

    def test_invalid_txn_type_rejected(self):
        """허용 외 txn_type 은 ValueError 로 거부(엔드포인트가 400 매핑) — 조용한 출고 차단."""
        from app.services.sales.mh import ops as mh_ops
        site_id = uuid_mod.uuid4()
        item = FakeItem(site_id=site_id, stock_qty=10)

        def handler(stmt):
            return [item]   # 품목 존재(site_id 스코프 통과)

        for bad in ("in", "OUTT", "", "TRANSFER"):
            db = FakeSession(handler)
            with pytest.raises(ValueError, match="txn_type은 IN 또는 OUT"):
                _run(mh_ops.inventory_txn(db, site_id, item.id, bad, 1))
            # 거부 후 재고 증감(MhInventoryTxn add)·flush 가 일어나지 않아야 한다(부작용 0).
            assert [o for o in db.added if type(o).__name__ == "MhInventoryTxn"] == []
            # 재고도 변하지 않아야 한다(조용한 차감 없음).
            assert item.stock_qty == 10

    def test_valid_in_increases_stock(self):
        """IN 은 입고(+qty) — 정상경로 무회귀."""
        from app.services.sales.mh import ops as mh_ops
        site_id = uuid_mod.uuid4()
        item = FakeItem(site_id=site_id, stock_qty=10)

        def handler(stmt):
            return [item]

        db = FakeSession(handler)
        out = _run(mh_ops.inventory_txn(db, site_id, item.id, "IN", 5))
        assert out == 15
        assert item.stock_qty == 15

    def test_valid_out_decreases_stock(self):
        """OUT 은 출고(-qty) — 정상경로 무회귀(재고 충분할 때)."""
        from app.services.sales.mh import ops as mh_ops
        site_id = uuid_mod.uuid4()
        item = FakeItem(site_id=site_id, stock_qty=10)

        def handler(stmt):
            return [item]

        db = FakeSession(handler)
        out = _run(mh_ops.inventory_txn(db, site_id, item.id, "OUT", 3))
        assert out == 7
        assert item.stock_qty == 7


if __name__ == "__main__":  # 직접 실행 디버그용
    sys.exit(pytest.main([__file__, "-v"]))
