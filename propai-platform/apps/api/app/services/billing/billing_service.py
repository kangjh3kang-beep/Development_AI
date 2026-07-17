"""구독 과금 서비스 — 사용자별 LLM 청구사용량 실계측·한도·충전·등급.

public.users의 tier/llm_billed_krw/billing_budget_krw/billing_cycle_start와
신규 컬럼 monthly_base_krw(월 제공 기본)/topup_krw(충전 잔액)를 raw SQL로
직접 다룬다(ORM 컬럼 불일치 회피). 월 단위 사이클 자동 리셋.

코인 분리(월기본/충전):
- monthly_base_krw: 매월 등급 포함한도(tier_included)로 리셋되는 월 제공 기본.
- topup_krw: 충전 잔액(영속, 월리셋 무관).
- 차감 우선순위: 월기본 먼저 소진 → 부족분은 충전(topup)에서 차감.
- 하위호환: billing_budget_krw = monthly_base_krw + topup_krw 로 동기 유지.

LLM 실계측: 모든 LLM 호출은 llm_usage_log에 service 귀속으로 1건 INSERT
(input/output tokens·cost_usd·마진·환율 적용 최종 cost_krw)되고, 동시에
사용자 청구사용량에 누적된다.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

from app.core.billing import (
    TIER_BILLING,
    analysis_module_fees,
    apply_config,
    billed_krw,
    free_tier_analysis_fee,
    free_tier_analysis_quota,
    get_config,
    get_usd_krw_rate,
    is_metered_tier,
    service_fee_concept_render,
    service_fee_land_analysis,
    service_fee_photoreal_render,
    service_fee_project_create,
    service_fee_registry_analysis,
    service_fee_registry_issue,
    service_fee_sales_provision,
    service_fee_stage,
    tier_fee_krw,
    tier_included_budget_krw,
    tier_multiplier,
)

_SEL = text(
    "SELECT tier, COALESCE(llm_billed_krw,0), COALESCE(billing_budget_krw,0), billing_cycle_start, "
    "COALESCE(monthly_base_krw,0), COALESCE(topup_krw,0) "
    "FROM public.users WHERE id = :id"
)

# ── 멱등 스키마 보장(컬럼·llm_usage_log). load_config에서 최초 1회 실행 ──
_SCHEMA_READY = False

_LLM_USAGE_DDL = """
CREATE TABLE IF NOT EXISTS llm_usage_log (
    id bigserial PRIMARY KEY,
    user_id text NOT NULL,
    service text NOT NULL,
    model text,
    input_tokens integer NOT NULL DEFAULT 0,
    output_tokens integer NOT NULL DEFAULT 0,
    cost_usd numeric(14,6) NOT NULL DEFAULT 0,
    cost_krw numeric(14,2) NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now()
)
"""

_LLM_USAGE_IDX = [
    "CREATE INDEX IF NOT EXISTS idx_llm_usage_user_created ON llm_usage_log (user_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_llm_usage_service_created ON llm_usage_log (service, created_at)",
]

_USER_COLS = [
    "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS monthly_base_krw numeric(14,2) DEFAULT 0",
    "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS topup_krw numeric(14,2) DEFAULT 0",
]


async def ensure_schema(db: AsyncSession, force: bool = False) -> None:
    """llm_usage_log 테이블·인덱스 + users 신규 컬럼(monthly_base_krw/topup_krw) 멱등 보장."""
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return
    try:
        await db.execute(text(_LLM_USAGE_DDL))
        for ddl in _LLM_USAGE_IDX:
            await db.execute(text(ddl))
        for ddl in _USER_COLS:
            await db.execute(text(ddl))
        await db.commit()
        _SCHEMA_READY = True
    except Exception:  # noqa: BLE001
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass


async def _row(db: AsyncSession, user_id: Any):
    return (await db.execute(_SEL, {"id": str(user_id)})).first()


def _sync_budget(monthly_base: float, topup: float) -> float:
    """하위호환 billing_budget_krw = 월기본 + 충전."""
    return float(monthly_base) + float(topup)


async def _record_coin_event(db: AsyncSession, **kwargs: Any) -> None:
    """관측 훅: 이미 커밋된 잔액 변경을 코인원장에 **비차단** 기록.

    ★호출자 세션(db)을 재사용한다 — 별도 async_session_factory를 열지 않으므로 무 DB 단위테스트
      (FakeSession)의 밀폐성이 보존되고, 실 DATABASE_URL 부수효과·연결 지연이 발생하지 않는다
      (성장루프 MEDIUM 수렴). 잔액은 이미 SSOT(users)에 커밋됐으므로, 원장 기록 실패는 잔액을
      되돌리지 않고 삼킨다(원장은 이력·감사 목적).
    """
    from app.services.billing import coin_ledger_service

    try:
        await coin_ledger_service.append_event(db=db, **kwargs)
        await db.commit()
    except Exception:  # noqa: BLE001 — 원장 기록 실패가 잔액 처리를 되돌리지 않는다(이미 커밋됨)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass


async def ensure_cycle(db: AsyncSession, user_id: Any):
    """월이 바뀌면 청구사용량 리셋 + 월기본만 등급 포함한도로 재설정(충전 보존).

    반환: (tier, billed, budget, monthly_base, topup)
    """
    await ensure_schema(db)
    row = await _row(db, user_id)
    if not row:
        return None
    tier, billed = row[0], float(row[1])
    budget, cycle = float(row[2]), row[3]
    monthly_base, topup = float(row[4]), float(row[5])
    now = datetime.now(UTC)
    rollover = cycle is None or (cycle.year, cycle.month) != (now.year, now.month)
    if rollover and is_metered_tier(tier):
        monthly_base = tier_included_budget_krw(tier)  # 월기본만 리셋
        budget = _sync_budget(monthly_base, topup)      # 충전은 보존
        await db.execute(
            text(
                "UPDATE public.users SET llm_billed_krw=0, monthly_base_krw=:m, "
                "billing_budget_krw=:b, billing_cycle_start=:c WHERE id=:id"
            ),
            {"m": monthly_base, "b": budget, "c": now, "id": str(user_id)},
        )
        await db.commit()
        billed = 0.0
        if monthly_base > 0:
            # 코인원장 관측 기록(월기본 부여가 코인내역에 보이도록) — 비차단·세션 재사용.
            await _record_coin_event(
                db, user_id=str(user_id), entry_type="monthly_grant", amount_krw=monthly_base,
                description=f"월기본 코인 부여({tier})", ref_type="billing_cycle",
                ref_id=f"{now.year}-{now.month:02d}",
            )
    elif is_metered_tier(tier) and monthly_base <= 0:
        # 같은 달이라도 월기본이 미할당(0)인 과금 등급 — 포함한도를 지연 할당(사용량·사이클 보존).
        #   원인: 마이그레이션 이전부터 현재 월 사이클이 잡혀 롤오버가 한 번도 안 돈 기존 유저.
        #   ★monthly_base_krw==0은 '미할당'을 뜻함(소진은 base_remaining=한도-billed로 별도 계산되며
        #     monthly_base_krw 자체는 유지). 따라서 0이면 안전하게 채워줄 수 있다(자가 백필).
        included = tier_included_budget_krw(tier)
        if included > 0:
            monthly_base = included
            budget = _sync_budget(monthly_base, topup)
            await db.execute(
                text(
                    "UPDATE public.users SET monthly_base_krw=:m, billing_budget_krw=:b "
                    "WHERE id=:id"
                ),
                {"m": monthly_base, "b": budget, "id": str(user_id)},
            )
            await db.commit()
    return tier, billed, budget, monthly_base, topup


async def get_status(db: AsyncSession, user_id: Any) -> dict[str, Any]:
    await load_config(db)
    await ensure_cycle(db, user_id)
    row = await _row(db, user_id)
    if not row:
        return {"tier": "guest", "metered": False, "blocked": False}
    tier, billed, budget = row[0], float(row[1]), float(row[2])
    monthly_base, topup = float(row[4]), float(row[5])
    rate = await get_usd_krw_rate()
    metered = is_metered_tier(tier)
    remaining = max(0.0, budget - billed)
    base_remaining = max(0.0, monthly_base - billed)             # 월기본 잔여
    topup_remaining = topup - max(0.0, billed - monthly_base)    # 충전 잔여(월기본 초과분 차감)
    meta = await _meta(db, user_id)
    acount = int(meta[1]) if meta else 0
    sfee = float(meta[2]) if meta else 0.0
    free_quota = free_tier_analysis_quota(tier) if not metered else 0
    team_limited = await team_limit_exceeded(db, user_id)  # 팀 멤버 한도 초과 여부
    return {
        "tier": tier,
        "tier_label": TIER_BILLING.get(tier, {}).get("label", tier),
        "metered": metered,
        "fee_krw": tier_fee_krw(tier),
        "included_budget_krw": tier_included_budget_krw(tier),
        "budget_krw": round(budget),
        "billed_krw": round(billed),
        "remaining_krw": round(remaining),
        "usage_pct": round(billed / budget * 100, 1) if budget > 0 else 0,
        "blocked": (metered and billed >= budget) or team_limited,
        "team_limited": team_limited,
        # 월기본/충전 코인 분리
        "monthly_base_krw": round(monthly_base),
        "monthly_base_remaining": round(base_remaining),
        "topup_krw": round(topup),
        "topup_remaining": round(max(0.0, topup_remaining)),
        # 서비스 사용료(LLM 별개)
        "service_fee_krw": round(sfee),
        "free_analysis_quota": free_quota,
        "free_analysis_used": acount if not metered else 0,
        "free_analysis_remaining": max(0, free_quota - acount) if not metered else 0,
        # 내부전용(노출 X)
        "multiplier": tier_multiplier(tier),
        "exchange_rate": round(rate, 2),
    }


async def team_limit_exceeded(db: AsyncSession, user_id: Any) -> bool:
    """이 사용자가 팀 멤버이고 팀장이 설정한 사용량 한도를 초과했는지(서버측 강제)."""
    try:
        from app.services.team.team_service import member_limit_status
        st = await member_limit_status(db, user_id)
        return bool(st.get("limited"))
    except Exception:  # noqa: BLE001 — 팀 테이블 미존재 등은 차단하지 않음
        return False


async def is_blocked(db: AsyncSession, user_id: Any) -> bool:
    row = await ensure_cycle(db, user_id)
    # ★팀 멤버 한도 초과는 구독 여부와 무관하게 차단(팀장이 설정한 개인 상한).
    if await team_limit_exceeded(db, user_id):
        return True
    if not row:
        return False
    tier, billed, budget = row[0], row[1], row[2]
    return is_metered_tier(tier) and billed >= budget


async def record_usage_usd(
    db: AsyncSession,
    user_id: Any,
    real_cost_usd: float,
    *,
    service: str | None = None,
    model: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> float | None:
    """실 LLM 원가($)를 등급 할증 적용 청구액(원)으로 누적. 반환=가산액(원).

    - 차감 우선순위: 월기본(monthly_base) 먼저 → 부족분은 충전(topup).
    - service가 주어지면 llm_usage_log에 1건 INSERT(실계측·service 귀속).
    - 시그니처 하위호환: service/model/tokens는 선택(키워드) 인자.
    """
    row = await ensure_cycle(db, user_id)
    if not row:
        return None
    tier = row[0]
    if not is_metered_tier(tier):
        return None
    billed_before = float(row[1])
    monthly_base = float(row[3])  # ensure_cycle 반환순서: (tier,billed,budget,base,topup); topup(row[4])은 아래 원자 UPDATE에서 직접 차감
    rate = await get_usd_krw_rate()
    add = billed_krw(real_cost_usd, tier, rate)

    # 월기본 → 충전 차감순서: billed_after가 월기본을 넘는 초과분만 충전에서 차감.
    billed_after = billed_before + add
    topup_draw = max(0.0, billed_after - monthly_base) - max(0.0, billed_before - monthly_base)
    # P1-6: topup/budget 절댓값 쓰기(read-modify-write)는 동시 호출 시 lost-update → 원자 컬럼식 차감.
    # billed는 이미 증분(COALESCE+:a). topup도 라이브 값에서 :draw 차감, budget=base+post-topup(=_sync_budget) 재계산.
    await db.execute(
        text(
            "UPDATE public.users SET llm_billed_krw = COALESCE(llm_billed_krw,0) + :a, "
            "topup_krw = GREATEST(0, COALESCE(topup_krw,0) - :draw), "
            "billing_budget_krw = :base + GREATEST(0, COALESCE(topup_krw,0) - :draw) "
            "WHERE id=:id"
        ),
        {"a": add, "draw": topup_draw, "base": monthly_base, "id": str(user_id)},
    )

    if service:
        await db.execute(
            text(
                "INSERT INTO llm_usage_log "
                "(user_id, service, model, input_tokens, output_tokens, cost_usd, cost_krw) "
                "VALUES (:uid, :svc, :mdl, :it, :ot, :usd, :krw)"
            ),
            {
                "uid": str(user_id),
                "svc": service,
                "mdl": (model or "")[:120] or None,
                "it": int(input_tokens or 0),
                "ot": int(output_tokens or 0),
                "usd": round(float(real_cost_usd), 6),
                "krw": round(add, 2),
            },
        )
    await db.commit()
    return round(add, 2)


async def topup(db: AsyncSession, user_id: Any, amount_krw: float) -> None:
    """추가결제(시뮬레이션): 충전 잔액(topup_krw) 증액 + 하위호환 budget 동기화.

    ★신규 충전 경로는 coin_orders(주문→확정)가 정본 — 이 함수는 레거시 /topup 하위호환.
    """
    await ensure_schema(db)
    row = await _row(db, user_id)
    if not row:
        return
    monthly_base = float(row[4])
    new_topup = float(row[5]) + float(amount_krw)
    await db.execute(
        text(
            "UPDATE public.users SET topup_krw = COALESCE(topup_krw,0) + :a, "
            "billing_budget_krw = :b WHERE id=:id"
        ),
        {"a": float(amount_krw), "b": _sync_budget(monthly_base, new_topup), "id": str(user_id)},
    )
    await db.commit()
    # 코인원장 관측 기록(이력·감사) — 비차단·세션 재사용.
    await _record_coin_event(
        db, user_id=str(user_id), entry_type="topup", amount_krw=float(amount_krw),
        description="충전(레거시 시뮬레이션)", ref_type="legacy_topup", created_by=str(user_id),
    )


async def is_super_admin(db: AsyncSession, user_id: Any) -> bool:
    """플랫폼 총괄관리자 여부 — users.tier == 'super_admin'으로만 판별한다.

    ★role이 아니라 tier로 판별한다: 가입 시 모든 사용자가 자기 테넌트의 role='admin'이
      되므로 role로 판별하면 모든 사용자가 플랫폼 전체를 보는 누출이 된다.
    """
    try:
        r = (await db.execute(
            text("SELECT tier FROM users WHERE id::text = :id"),
            {"id": str(user_id)},
        )).first()
        return bool(r and str(r[0] or "").lower() == "super_admin")
    except Exception:  # noqa: BLE001
        return False


async def token_usage(
    db: AsyncSession, user_id: Any, days: int = 30, *, platform_wide: bool = False
) -> dict[str, Any]:
    """LLM 실계측 사용량 집계(llm_usage_log). service별·일별 + 총합.

    platform_wide=True(관리자): user_id 필터 없이 플랫폼 전체 사용량을 집계한다
    (관리자는 전 사용자 AI 비용을 모니터링해야 하므로). 일반 사용자는 본인만.
    """
    await ensure_schema(db)
    days = max(1, min(int(days or 30), 365))
    since = datetime.now(UTC) - timedelta(days=days)
    # ★platform_wide면 user_id 조건 제거(전체 집계). 식별자는 코드 상수라 SQL 인젝션 무관.
    user_cond = "" if platform_wide else "user_id=:id AND "
    params: dict[str, Any] = {"since": since}
    if not platform_wide:
        params["id"] = str(user_id)

    total = (await db.execute(
        text(
            "SELECT COALESCE(SUM(input_tokens+output_tokens),0), COALESCE(SUM(cost_krw),0) "
            f"FROM llm_usage_log WHERE {user_cond}created_at >= :since"
        ),
        params,
    )).first()
    by_service_rows = (await db.execute(
        text(
            "SELECT service, COALESCE(SUM(input_tokens+output_tokens),0), COALESCE(SUM(cost_krw),0) "
            f"FROM llm_usage_log WHERE {user_cond}created_at >= :since "
            "GROUP BY service ORDER BY 3 DESC"
        ),
        params,
    )).all()
    daily_rows = (await db.execute(
        text(
            "SELECT to_char(created_at::date,'YYYY-MM-DD'), "
            "COALESCE(SUM(input_tokens+output_tokens),0), COALESCE(SUM(cost_krw),0) "
            f"FROM llm_usage_log WHERE {user_cond}created_at >= :since "
            "GROUP BY created_at::date ORDER BY 1"
        ),
        params,
    )).all()

    # 관리자 전체뷰일 때만 계정별(by_user) 사용량도 집계(총괄관리자가 계정별로 확인).
    by_user: list[dict[str, Any]] = []
    if platform_wide:
        user_rows = (await db.execute(
            text(
                "SELECT l.user_id, COALESCE(u.email,'(알수없음)'), COALESCE(u.role,''), "
                "COALESCE(SUM(l.input_tokens+l.output_tokens),0), COALESCE(SUM(l.cost_krw),0) "
                "FROM llm_usage_log l LEFT JOIN users u ON u.id::text = l.user_id "
                "WHERE l.created_at >= :since "
                "GROUP BY l.user_id, u.email, u.role ORDER BY 4 DESC LIMIT 100"
            ),
            {"since": since},
        )).all()
        by_user = [
            {
                "user_id": str(r[0]), "email": r[1], "role": r[2],
                "tokens": int(r[3] or 0), "cost_krw": round(float(r[4] or 0)),
            }
            for r in user_rows
        ]

    return {
        "scope": "platform" if platform_wide else "user",
        "days": days,
        "total_tokens": int(total[0] or 0),
        "total_cost_krw": round(float(total[1] or 0)),
        "by_service": [
            {"service": r[0], "tokens": int(r[1] or 0), "cost_krw": round(float(r[2] or 0))}
            for r in by_service_rows
        ],
        "by_user": by_user,
        "daily": [
            {"date": r[0], "tokens": int(r[1] or 0), "cost_krw": round(float(r[2] or 0))}
            for r in daily_rows
        ],
    }


async def get_balance(db: AsyncSession, user_id: Any) -> dict[str, Any]:
    """월기본/충전 코인 잔액 + 등급·사이클 시작.

    ★마진율(markup_pct)은 내부 정책이라 응답에 포함하지 않는다(개발자도구 노출 방지).
      청구 금액(used_this_cycle_krw 등)에는 이미 반영돼 있으므로 사용자는 실지급액만 본다.
    """
    await load_config(db)
    await ensure_cycle(db, user_id)
    row = await _row(db, user_id)
    if not row:
        return {
            "tier": "guest", "tier_label": "비회원", "monthly_base_krw": 0,
            "monthly_base_remaining": 0, "topup_krw": 0, "used_this_cycle_krw": 0,
            "cycle_start": None,
            "module_fees": {},
        }
    tier, billed = row[0], float(row[1])
    cycle = row[3]
    monthly_base, topup = float(row[4]), float(row[5])
    base_remaining = max(0.0, monthly_base - billed)
    topup_remaining = max(0.0, topup - max(0.0, billed - monthly_base))
    # ★비과금 등급(super_admin 등 TIER_BILLING 미포함)은 코인 게이트 면제(무제한).
    #   백엔드 하드게이트(is_blocked)는 이미 면제하나, 프론트 소프트게이트가 잔액 0원으로
    #   '분석 시작'을 막던 것을 해소한다. unlimited=True로 프론트가 무제한 처리.
    unlimited = not is_metered_tier(tier)
    return {
        "tier": tier,
        "tier_label": TIER_BILLING.get(tier, {}).get("label", tier),
        "unlimited": unlimited,
        "monthly_base_krw": round(monthly_base),
        "monthly_base_remaining": round(base_remaining),
        "topup_krw": round(topup),
        "topup_remaining": round(topup_remaining),
        "used_this_cycle_krw": round(billed),
        "cycle_start": cycle.isoformat() if cycle else None,
        # 관리자가 설정한 분석 모듈 사용료 맵(미설정 시 빈 dict = 전부 무료).
        # 프론트 셀렉터가 모듈별 추가 비용 표시에 사용한다.
        "module_fees": analysis_module_fees(),
    }


_CONFIG_DDL = "CREATE TABLE IF NOT EXISTS billing_config (id int PRIMARY KEY, config jsonb, updated_at timestamptz)"
_config_loaded = False


async def load_config(db: AsyncSession, force: bool = False) -> None:
    """billing_config(DB)에서 관리자 설정을 읽어 런타임 설정에 반영(최초 1회/강제)."""
    global _config_loaded
    await ensure_schema(db)
    if _config_loaded and not force:
        return
    try:
        await db.execute(text(_CONFIG_DDL))
        await db.commit()
        row = (await db.execute(text("SELECT config FROM billing_config WHERE id=1"))).first()
        if row and row[0]:
            cfg = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            apply_config(cfg)
        _config_loaded = True
    except Exception as e:  # noqa: BLE001
        logger.warning("빌링 설정 로드 실패 — 기본값 유지", err=str(e)[:160])


async def save_config(db: AsyncSession, override: dict[str, Any]) -> dict[str, Any]:
    """관리자 설정 저장(DB 영속 + 런타임 반영)."""
    await db.execute(text(_CONFIG_DDL))
    apply_config(override)
    cfg = json.dumps(get_config(), ensure_ascii=False)
    await db.execute(
        text("INSERT INTO billing_config(id, config, updated_at) VALUES (1, CAST(:c AS jsonb), now()) "
             "ON CONFLICT (id) DO UPDATE SET config=CAST(:c AS jsonb), updated_at=now()"),
        {"c": cfg},
    )
    await db.commit()
    return get_config()


async def _meta(db: AsyncSession, user_id: Any):
    """tier, analysis_count, service_fee_krw 조회."""
    r = (await db.execute(
        text("SELECT tier, COALESCE(analysis_count,0), COALESCE(service_fee_krw,0) "
             "FROM public.users WHERE id=:id"),
        {"id": str(user_id)},
    )).first()
    return r


def compute_service_fee(tier: str, action: str, analysis_count: int) -> dict[str, Any]:
    """행위별 서비스 사용료(원) 산정. LLM 과금과 별개.

    - 프로젝트 생성: 2,000원(구독자)
    - 토지분석: 구독자 2,000원 / 일반회원 무료 N회후 5,000원 / 비회원 무료 N회후 10,000원
    """
    if action == "project_create":
        return {"fee_krw": service_fee_project_create(), "free": False, "free_remaining": 0}
    if action == "sales_provision":
        return {"fee_krw": service_fee_sales_provision(), "free": False, "free_remaining": 0}
    if action == "photoreal_render":
        return {"fee_krw": service_fee_photoreal_render(), "free": False, "free_remaining": 0}
    if action == "concept_render":
        # 컨셉 렌더(text2img). 관리자 미설정 시 0원=무료(미설정무료 정책).
        fee = service_fee_concept_render()
        return {"fee_krw": fee, "free": fee <= 0, "free_remaining": 0}
    if action == "registry_analysis":
        return {"fee_krw": service_fee_registry_analysis(), "free": False, "free_remaining": 0}
    if action == "registry_issue":
        return {"fee_krw": service_fee_registry_issue(), "free": False, "free_remaining": 0}
    # 파이프라인 단계별 과금 (stage:<name>)
    if action.startswith("stage:"):
        return {"fee_krw": service_fee_stage(action.split(":", 1)[1]), "free": False, "free_remaining": 0}
    # land_analysis
    if is_metered_tier(tier):  # 구독자
        return {"fee_krw": service_fee_land_analysis(), "free": False, "free_remaining": 0}
    quota = free_tier_analysis_quota(tier)
    if analysis_count < quota:
        return {"fee_krw": 0, "free": True, "free_remaining": quota - analysis_count - 1}
    return {"fee_krw": free_tier_analysis_fee(tier), "free": False, "free_remaining": 0}


async def preview_service_fee(db: AsyncSession, user_id: Any, action: str) -> dict[str, Any]:
    m = await _meta(db, user_id)
    if not m:
        return {"fee_krw": 0, "free": True, "free_remaining": 0}
    return compute_service_fee(m[0], action, int(m[1]))


async def charge_service(db: AsyncSession, user_id: Any, action: str) -> dict[str, Any]:
    """행위 발생 시 서비스 사용료 누적(+무료 토지분석이면 analysis_count 증가)."""
    m = await _meta(db, user_id)
    if not m:
        return {"charged_krw": 0, "free": True}
    tier, acount, sfee = m[0], int(m[1]), float(m[2])
    calc = compute_service_fee(tier, action, acount)
    fee = calc["fee_krw"]
    if action == "land_analysis" and calc.get("free"):
        # P2-3: read-check-increment TOCTOU 제거 — 원자 조건부 증가(한도 미만일 때만 +1).
        quota = free_tier_analysis_quota(tier)
        res = await db.execute(
            text(
                "UPDATE public.users SET analysis_count = COALESCE(analysis_count,0)+1 "
                "WHERE id=:id AND COALESCE(analysis_count,0) < :quota"
            ),
            {"id": str(user_id), "quota": int(quota)},
        )
        if (res.rowcount or 0) == 0:
            # 동시호출 경쟁에서 졌음 — 이미 무료 한도 소진 → 유료로 정직 재계산(무료 초과 방지).
            calc = {"fee_krw": free_tier_analysis_fee(tier), "free": False, "free_remaining": 0}
            fee = calc["fee_krw"]
    if fee > 0:
        await db.execute(
            text("UPDATE public.users SET service_fee_krw = COALESCE(service_fee_krw,0)+:f WHERE id=:id"),
            {"f": float(fee), "id": str(user_id)},
        )
    await db.commit()
    if fee > 0:
        # 코인원장 관측 기록(마이페이지 '코인내역'의 서비스료 이력) — 비차단·세션 재사용.
        await _record_coin_event(
            db, user_id=str(user_id), entry_type="service_fee", amount_krw=-float(fee),
            description=f"서비스 사용료({action})", ref_type="action", ref_id=action,
            created_by=str(user_id),
        )
    return {
        "action": action,
        "charged_krw": fee,
        "free": calc.get("free", False),
        "free_remaining": calc.get("free_remaining", 0),
        "service_fee_total_krw": round(sfee + fee),
    }


async def set_tier(db: AsyncSession, user_id: Any, tier: str) -> None:
    """등급 변경 + 월기본 재설정(관리자). 충전(topup)은 보존."""
    await ensure_schema(db)
    monthly_base = tier_included_budget_krw(tier)
    row = await _row(db, user_id)
    topup = float(row[5]) if row else 0.0
    await db.execute(
        text(
            "UPDATE public.users SET tier=:t, llm_billed_krw=0, monthly_base_krw=:m, "
            "billing_budget_krw=:b, billing_cycle_start=:c WHERE id=:id"
        ),
        {"t": tier, "m": monthly_base, "b": _sync_budget(monthly_base, topup),
         "c": datetime.now(UTC), "id": str(user_id)},
    )
    await db.commit()
    # 코인원장 관측 기록(등급 변경에 따른 월기본 재설정 이력) — 비차단·세션 재사용.
    await _record_coin_event(
        db, user_id=str(user_id), entry_type="tier_change", amount_krw=monthly_base,
        description=f"등급 변경({tier}) — 월기본 재설정", ref_type="tier", ref_id=tier,
    )
