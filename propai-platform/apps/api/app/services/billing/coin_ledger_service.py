"""코인 거래 원장 — coin_ledger_events append-only 해시체인(마이페이지 코인내역).

잔액 SSOT는 기존 public.users 컬럼(monthly_base_krw/topup_krw/llm_billed_krw)이고,
이 원장은 **이산 잔액 이벤트의 이력·감사·설명가능성**을 담당한다(충전/주문지급/서비스료/
월기본 부여/등급변경/관리자 조정). 고빈도 LLM 사용은 기존 llm_usage_log가 이력이므로
여기 중복 기록하지 않는다 — 마이페이지 '코인내역'은 merged_history()로 두 소스를 합친다.

★무결성(정통 해시체인): content_hash = sha256(정규화 이벤트 ‖ prev_hash ‖ seq) — 이전 해시를
  입력에 접어, 중간 행 변조 시 후행 전체가 깨지는 캐스케이드. 체인 단위 = user_id.
  금액은 f"{:.2f}" 고정 문자열로 접어 float 표현 비결정성을 제거한다.
★보안: 모든 조회/append는 user_id 스코프(IDOR 차단은 라우터의 current.user_id 강제와 이중).
★동시성: 같은 사용자 체인 append는 pg_advisory_xact_lock으로 직렬화(prev_hash 포크 방지).
★원자성 모드 2종:
  - db 세션 주입: 호출자 트랜잭션에 편승(커밋 안 함) — 주문 지급처럼 잔액 UPDATE와
    원장 append가 반드시 함께 성립해야 하는 경로용.
  - db=None: 자체 세션+커밋+graceful — 관측 훅(충전/서비스료/월부여)용. 실패해도
    잔액 처리를 막지 않는다(원장은 이력, 잔액이 SSOT).
★deploy 안전: CREATE TABLE IF NOT EXISTS 자가 프로비저닝(disbursement_ledger 패턴) —
  형식 정본은 alembic 043(동일 DDL·멱등)과 병행.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

ENTRY_TYPES = (
    "topup",          # 레거시 시뮬레이션 충전(+)
    "order_paid",     # 충전 주문 지급(+) — coin_orders 확정
    "service_fee",    # 서비스 사용료 차감(-)
    "monthly_grant",  # 월기본 부여/재설정(+)
    "tier_change",    # 등급 변경에 따른 월기본 재설정(+)
    "admin_adjust",   # 관리자 조정(±)
)

# 코인내역 그룹 필터 — 프론트 탭이 의미 단위로 여러 entry_type을 묶어 조회한다.
# (예: '충전' 탭은 신규 주문 지급 order_paid + 레거시 topup을 함께 보여야 항목 누락이 없다.)
# 값은 반드시 ENTRY_TYPES 부분집합(리터럴 SQL 삽입 안전성의 근거).
FILTER_GROUPS: dict[str, tuple[str, ...]] = {
    "charge": ("order_paid", "topup"),
}

_DDL = (
    "CREATE TABLE IF NOT EXISTS coin_ledger_events ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  user_id text NOT NULL,"
    "  tenant_id text,"
    "  seq int NOT NULL DEFAULT 1,"
    "  entry_type text NOT NULL,"
    "  amount_krw numeric(14,2) NOT NULL,"
    "  description text,"
    "  ref_type text,"
    "  ref_id text,"
    "  content_hash text NOT NULL,"
    "  prev_hash text,"
    "  created_by text,"
    "  created_at timestamptz DEFAULT now()"
    ")"
)
_IDX = (
    "CREATE INDEX IF NOT EXISTS idx_coin_ledger_chain ON coin_ledger_events(user_id, seq)",
    "CREATE INDEX IF NOT EXISTS idx_coin_ledger_user_created ON coin_ledger_events(user_id, created_at)",
)


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _chain_hash(payload: Any, prev_hash: str | None, seq: int) -> str:
    """정통 해시체인: H(contentₙ ‖ prev_hashₙ₋₁ ‖ seq)."""
    material = f"{_canonical(payload)}|{prev_hash or 'genesis'}|{seq}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _event_payload(
    user_id: str, entry_type: str, amount_krw: float,
    description: str | None, ref_type: str | None, ref_id: str | None,
    created_by: str | None = None, tenant_id: str | None = None,
) -> dict[str, Any]:
    """해시 대상 정규화 페이로드 — 금액은 고정 소수점 문자열(결정성).

    ★감사 무결성(성장루프 LOW 수렴): created_by(행위자 귀속)·tenant_id(스코프)를 해시에 접어,
      DB 쓰기 권한 침해자가 admin_adjust의 행위자를 다른 관리자로 위조하거나 이벤트를 타 테넌트로
      옮기면 content_hash 재계산이 불일치해 verify_chain이 탐지한다.
      ※잔여 한계(문서화): created_at 값의 교차 이동과 체인 **말미 행 삭제**는 순수(무 앵커)
        해시체인의 본질적 한계라 탐지 못한다 — 완전 방어는 외부 앵커/서명 체크포인트(후속 인프라)가
        필요하다. 잔액 SSOT는 users 테이블이라 이 원장 조작으로 금전 직접 절취는 불가.
    """
    return {
        "user_id": user_id,
        "entry_type": entry_type,
        "amount_krw": f"{float(amount_krw):.2f}",
        "description": description,
        "ref_type": ref_type,
        "ref_id": ref_id,
        "created_by": created_by,
        "tenant_id": tenant_id,
    }


async def _ensure(db) -> None:
    from sqlalchemy import text

    await db.execute(text(_DDL))
    for ix in _IDX:
        await db.execute(text(ix))


async def _append_with_session(
    db,
    *,
    user_id: str,
    entry_type: str,
    amount_krw: float,
    tenant_id: str | None,
    description: str | None,
    ref_type: str | None,
    ref_id: str | None,
    created_by: str | None,
) -> dict[str, Any]:
    from sqlalchemy import text

    await _ensure(db)
    # ★동시성: 같은 사용자 체인 append 직렬화 — prev_hash 포크 방지.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lk)::bigint)"),
        {"lk": f"coin_ledger:{user_id}"},
    )
    prev = (await db.execute(text(
        "SELECT content_hash, seq FROM coin_ledger_events "
        "WHERE user_id=:u ORDER BY seq DESC LIMIT 1"
    ), {"u": user_id})).first()
    prev_hash = prev[0] if prev else None
    seq = (prev[1] + 1) if prev else 1
    payload = _event_payload(
        user_id, entry_type, amount_krw, description, ref_type, ref_id,
        created_by=created_by, tenant_id=tenant_id,
    )
    chash = _chain_hash(payload, prev_hash, seq)
    await db.execute(text(
        "INSERT INTO coin_ledger_events"
        "(user_id, tenant_id, seq, entry_type, amount_krw, description, ref_type, ref_id,"
        " content_hash, prev_hash, created_by)"
        " VALUES(:u,:t,:s,:e,:a,:d,:rt,:ri,:h,:ph,:cb)"
    ), {
        "u": user_id, "t": tenant_id, "s": seq, "e": entry_type,
        "a": round(float(amount_krw), 2), "d": description, "rt": ref_type, "ri": ref_id,
        "h": chash, "ph": prev_hash, "cb": created_by,
    })
    return {"persisted": True, "seq": seq, "content_hash": chash, "prev_hash": prev_hash}


async def append_event(
    *,
    user_id: str,
    entry_type: str,
    amount_krw: float,
    tenant_id: str | None = None,
    description: str | None = None,
    ref_type: str | None = None,
    ref_id: str | None = None,
    created_by: str | None = None,
    db=None,
) -> dict[str, Any]:
    """원장 이벤트 1건 append.

    - db 주입 시: 호출자 트랜잭션 내 실행(커밋 없음) — 실패는 **호출자로 전파**(원자성 필요 경로).
    - db=None: 자체 세션+커밋, 실패 시 graceful({persisted:False}) — 관측 훅 경로.
    """
    if entry_type not in ENTRY_TYPES:
        return {"persisted": False, "reason": f"unknown entry_type: {entry_type}"}
    if db is not None:
        return await _append_with_session(
            db, user_id=user_id, entry_type=entry_type, amount_krw=amount_krw,
            tenant_id=tenant_id, description=description, ref_type=ref_type,
            ref_id=ref_id, created_by=created_by,
        )
    try:
        from app.core.database import async_session_factory

        async with async_session_factory() as session:
            out = await _append_with_session(
                session, user_id=user_id, entry_type=entry_type, amount_krw=amount_krw,
                tenant_id=tenant_id, description=description, ref_type=ref_type,
                ref_id=ref_id, created_by=created_by,
            )
            await session.commit()
        return out
    except Exception as e:  # noqa: BLE001 — 관측 훅은 잔액 처리를 막지 않는다(graceful)
        logger.warning("coin_ledger_append_skip", error=str(e)[:160])
        return {"persisted": False, "reason": str(e)[:160]}


async def list_events(
    user_id: str, *, days: int = 90, limit: int = 50, offset: int = 0,
    entry_type: str | None = None,
) -> list[dict[str, Any]]:
    """내 원장 이벤트(최신순). 실패/테이블 부재 시 빈 리스트(graceful). user_id 스코프."""
    try:
        from datetime import UTC, datetime, timedelta

        from sqlalchemy import text

        from app.core.database import async_session_factory

        days = max(1, min(int(days or 90), 1830))
        limit = max(1, min(int(limit or 50), 200))
        offset = max(0, int(offset or 0))
        since = datetime.now(UTC) - timedelta(days=days)
        # entry_type은 화이트리스트 검증(임의 문자열 SQL 삽입 원천 차단 — 바인딩이지만 이중 방어).
        etype = entry_type if entry_type in ENTRY_TYPES else None
        cond = "AND entry_type=:e " if etype else ""
        params: dict[str, Any] = {"u": user_id, "since": since, "l": limit, "o": offset}
        if etype:
            params["e"] = etype
        async with async_session_factory() as db:
            await _ensure(db)
            rows = (await db.execute(text(
                "SELECT seq, entry_type, amount_krw, description, ref_type, ref_id, created_at"
                " FROM coin_ledger_events"
                f" WHERE user_id=:u AND created_at >= :since {cond}"
                "ORDER BY created_at DESC, seq DESC LIMIT :l OFFSET :o"
            ), params)).mappings().all()
        return [
            {
                "seq": r["seq"],
                "entry_type": r["entry_type"],
                "amount_krw": round(float(r["amount_krw"]), 2),
                "description": r["description"],
                "ref_type": r["ref_type"],
                "ref_id": r["ref_id"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]
    except Exception as e:  # noqa: BLE001
        logger.warning("coin_ledger_list_skip", error=str(e)[:160])
        return []


async def verify_chain(user_id: str) -> dict[str, Any]:
    """해시체인 재계산 대조로 위·변조 탐지. {ok, count, broken_at?}. 실패 시 ok=None(graceful)."""
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory

        async with async_session_factory() as db:
            await _ensure(db)
            rows = (await db.execute(text(
                "SELECT seq, entry_type, amount_krw, description, ref_type, ref_id,"
                " content_hash, prev_hash, created_by, tenant_id"
                " FROM coin_ledger_events WHERE user_id=:u ORDER BY seq ASC"
            ), {"u": user_id})).mappings().all()
        prev = None
        for r in rows:
            payload = _event_payload(
                user_id, r["entry_type"], float(r["amount_krw"]),
                r["description"], r["ref_type"], r["ref_id"],
                created_by=r["created_by"],
                tenant_id=str(r["tenant_id"]) if r["tenant_id"] is not None else None,
            )
            expect = _chain_hash(payload, prev, r["seq"])
            if r["prev_hash"] != prev or r["content_hash"] != expect:
                return {"ok": False, "count": len(rows), "broken_at": r["seq"]}
            prev = r["content_hash"]
        return {"ok": True, "count": len(rows)}
    except Exception as e:  # noqa: BLE001
        logger.warning("coin_ledger_verify_skip", error=str(e)[:160])
        return {"ok": None, "reason": str(e)[:160]}


async def merged_history(
    user_id: str, *, days: int = 90, limit: int = 50, offset: int = 0,
    entry_type: str | None = None,
) -> dict[str, Any]:
    """마이페이지 '코인내역' 통합 타임라인 = 원장 이벤트 ∪ llm_usage_log(AI 사용, 음수).

    단일 UNION ALL 쿼리로 페이지네이션 정확성을 보장한다. 실패 시 빈 결과(graceful).
    entry_type 필터: 원장 타입 또는 'llm_usage'(AI 사용만).
    """
    try:
        from datetime import UTC, datetime, timedelta

        from sqlalchemy import text

        from app.core.database import async_session_factory

        days = max(1, min(int(days or 90), 1830))
        limit = max(1, min(int(limit or 50), 200))
        offset = max(0, int(offset or 0))
        since = datetime.now(UTC) - timedelta(days=days)

        # ★필터는 화이트리스트로만 SQL 분기(사용자 문자열은 절대 SQL에 직접 안 들어감).
        #   그룹 필터('charge')는 프론트 '충전' 탭이 레거시 topup ∪ 신규 order_paid를 함께
        #   보이도록 여러 entry_type을 묶는다(성장루프 LOW 수렴 — 필터별 항목 누락 방지).
        group = FILTER_GROUPS.get(entry_type or "")
        single = entry_type if entry_type in ENTRY_TYPES else None
        want_ledger = entry_type is None or single is not None or group is not None
        want_llm = entry_type is None or entry_type == "llm_usage"

        if group is not None:
            # group 멤버는 코드 상수(ENTRY_TYPES 부분집합)라 리터럴 삽입이 안전(사용자 입력 아님).
            ledger_cond = "AND entry_type IN (" + ",".join(f"'{g}'" for g in group) + ") "
        elif single is not None:
            ledger_cond = "AND entry_type=:e "
        else:
            ledger_cond = ""

        parts: list[str] = []
        if want_ledger:
            parts.append(
                "SELECT created_at, entry_type, amount_krw::float8 AS amount_krw,"
                " description, ref_type, ref_id"
                f" FROM coin_ledger_events WHERE user_id=:u AND created_at >= :since {ledger_cond}"
            )
        if want_llm:
            parts.append(
                "SELECT created_at, 'llm_usage' AS entry_type, -cost_krw::float8 AS amount_krw,"
                " service AS description, 'llm' AS ref_type, model AS ref_id"
                " FROM llm_usage_log WHERE user_id=:u AND created_at >= :since"
            )
        if not parts:
            return {"items": [], "limit": limit, "offset": offset}

        # ★결정적 정렬(성장루프 LOW 수렴): created_at 동률(같은 초 배치삽입) 시 페이지 경계에서
        #   순서가 흔들려 누락/중복되지 않도록 안정적 타이브레이커를 부여한다(llm_usage엔 seq가
        #   없어 amount/ref/description으로 결정화). NULL은 빈 문자열로 정규화해 순서 고정.
        sql = (
            "SELECT * FROM (" + " UNION ALL ".join(parts) + ") t"
            " ORDER BY created_at DESC, amount_krw DESC, entry_type,"
            " COALESCE(ref_id,''), COALESCE(description,'') LIMIT :l OFFSET :o"
        )
        params: dict[str, Any] = {"u": user_id, "since": since, "l": limit, "o": offset}
        if single is not None:
            params["e"] = single
        async with async_session_factory() as db:
            await _ensure(db)
            rows = (await db.execute(text(sql), params)).mappings().all()
        return {
            "items": [
                {
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                    "entry_type": r["entry_type"],
                    "amount_krw": round(float(r["amount_krw"] or 0), 2),
                    "description": r["description"],
                    "ref_type": r["ref_type"],
                    "ref_id": r["ref_id"],
                }
                for r in rows
            ],
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("coin_ledger_history_skip", error=str(e)[:160])
        return {"items": [], "limit": limit, "offset": offset}


async def export_rows(user_id: str, *, days: int = 365, cap: int = 5000) -> list[dict[str, Any]]:
    """CSV 내보내기 전용 — 최대 cap행을 **단일 쿼리·단일 스냅샷**으로 반환(누락/중복 방지).

    ★성장루프 LOW 수렴: offset 다중쿼리 순회는 순회 도중 신규 행 삽입 시 offset이 밀려
      경계 행이 중복/누락되고, created_at 동률 시 재정렬로 불일치가 생긴다. 단일 쿼리로 한 번에
      가져와 트랜잭션 스냅샷을 고정하고 결정적 타이브레이커로 정렬한다. 전상법 §6 열람 정합성 확보.
    """
    try:
        from datetime import UTC, datetime, timedelta

        from sqlalchemy import text

        from app.core.database import async_session_factory

        days = max(1, min(int(days or 365), 1830))
        cap = max(1, min(int(cap or 5000), 20000))
        since = datetime.now(UTC) - timedelta(days=days)
        sql = (
            "SELECT * FROM ("
            "SELECT created_at, entry_type, amount_krw::float8 AS amount_krw,"
            " description, ref_type, ref_id"
            " FROM coin_ledger_events WHERE user_id=:u AND created_at >= :since"
            " UNION ALL "
            "SELECT created_at, 'llm_usage' AS entry_type, -cost_krw::float8 AS amount_krw,"
            " service AS description, 'llm' AS ref_type, model AS ref_id"
            " FROM llm_usage_log WHERE user_id=:u AND created_at >= :since"
            ") t ORDER BY created_at DESC, amount_krw DESC, entry_type,"
            " COALESCE(ref_id,''), COALESCE(description,'') LIMIT :l"
        )
        async with async_session_factory() as db:
            await _ensure(db)
            rows = (await db.execute(text(sql), {"u": user_id, "since": since, "l": cap})).mappings().all()
        return [
            {
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "entry_type": r["entry_type"],
                "amount_krw": round(float(r["amount_krw"] or 0), 2),
                "description": r["description"],
                "ref_type": r["ref_type"],
                "ref_id": r["ref_id"],
            }
            for r in rows
        ]
    except Exception as e:  # noqa: BLE001
        logger.warning("coin_ledger_export_skip", error=str(e)[:160])
        return []
