"""구독 과금 라우터 — 사용 현황·추가결제(시뮬레이션)·견적·등급변경(관리자).

마이페이지(2026-07-17): 충전 주문(coin_orders)·코인내역(coin_ledger ∪ llm_usage 통합)·
무결성 검증·CSV 내보내기 추가. 스펙=docs/design/MYPAGE_SAAS_SPEC_2026-07-17.md.
"""

import logging
import math
import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.billing import (
    TIER_BILLING,
    get_usd_krw_rate,
    markup_quote,
    public_status,
    tier_included_budget_krw,
)
from app.services.billing import billing_service, coin_ledger_service, coin_orders_service
from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.config import Settings, get_settings
from apps.api.database.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/billing", tags=["구독·과금"])


@router.get("/plans")
async def list_plans():
    """등급별 요금·포함 사용량 안내.

    ★할증배수(50/40/30%)는 내부 정책 → 외부 미노출. 사용자에겐 요금·포함 사용량(원)만.
    """
    return {
        "plans": [
            {
                "tier": t,
                "label": info["label"],
                "fee_krw": info["fee_krw"],
                "included_budget_krw": tier_included_budget_krw(t),
            }
            for t, info in TIER_BILLING.items()
        ],
    }


@router.get("/status")
async def billing_status(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """사용자 과금 현황 — 실지급액(원)만 노출(내부 배수·환율 제외)."""
    status = await billing_service.get_status(db, current.user_id)
    return public_status(status)


@router.get("/token-usage")
async def token_usage(
    days: int = 30,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """LLM 실계측 사용량(llm_usage_log) — 총 토큰·청구액(원)·service별·일별 집계.

    관리자/총괄관리자는 플랫폼 전체 사용량을, 일반 사용자는 본인 사용량을 본다.
    """
    # ★플랫폼 전체뷰는 총괄관리자(tier=super_admin)만. role로 판별하면 모든 가입자가
    #  자기 테넌트 role='admin'이라 전 사용자 사용량·이메일이 노출되므로 절대 금지.
    platform = await billing_service.is_super_admin(db, current.user_id)
    return await billing_service.token_usage(
        db, current.user_id, days, platform_wide=platform
    )


@router.get("/balance")
async def balance(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """월기본/충전 코인 잔액 — 등급·마진율·사이클 시작."""
    return await billing_service.get_balance(db, current.user_id)


class TopupRequest(BaseModel):
    # ★plain float로 받고 핸들러에서 math.isfinite+양수 하드가드로 차단한다.
    #   pydantic Field(gt/allow_inf_nan) 제약은 nan/inf를 422로 거부하되 그 오류 응답이
    #   입력값(nan)을 echo하다 JSON 직렬화가 깨지는(FastAPI 알려진 버그) 문제가 있어 회피.
    amount_krw: float


@router.post("/topup")
async def topup(
    req: TopupRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """레거시 직접 충전 — **결제 없이 잔액을 증액하므로 dev/demo(시뮬레이션 모드) 전용**.

    ★보안(성장루프 HIGH 수렴): 과거 이 엔드포인트는 무게이트로 topup_krw(실지출 잔액)를
      무제한 자가 증액할 수 있어 신규 결제(coin_orders)의 fail-closed 게이트를 완전히
      우회했다. 이제 신규 결제와 동일하게 billing_simulated_payments 플래그로 게이트한다.
      프로덕션(플래그 off)에서는 403 — 실제 충전은 마이페이지 코인 충전 주문을 이용한다.
    """
    # ★유한·양수 금액만 허용 — NaN/Infinity가 예산(budget)을 오염시켜 차단 게이트를 무력화하던
    #   문제를 결정적으로 차단(pydantic allow_inf_nan에 의존하지 않는 서버측 하드가드).
    if not math.isfinite(req.amount_krw) or req.amount_krw <= 0:
        raise HTTPException(status_code=400, detail="충전 금액이 올바르지 않습니다.")
    if not settings.billing_simulated_payments:
        raise HTTPException(
            status_code=403,
            detail="직접 충전은 지원되지 않습니다. 마이페이지의 코인 충전 주문을 이용해 주세요.",
        )
    await _require_active_user(db, current)
    await billing_service.topup(db, current.user_id, req.amount_krw)
    return await billing_service.get_status(db, current.user_id)


class QuoteRequest(BaseModel):
    real_cost_usd: float


@router.post("/quote")
async def quote(
    req: QuoteRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """추가결제 견적 — 실지급액(원)만 반환. (할증·실원가·환율은 내부 비노출)"""
    st = await billing_service.get_status(db, current.user_id)
    rate = await get_usd_krw_rate()
    return markup_quote(req.real_cost_usd, st["tier"], rate, internal=False)


class ChargeRequest(BaseModel):
    action: str  # "project_create" | "land_analysis"


@router.post("/preview-charge")
async def preview_charge(
    req: ChargeRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """서비스 사용료 사전 견적(차감 전 표시용). LLM 과금과 별개."""
    if req.action not in ("project_create", "land_analysis", "sales_provision", "registry_issue", "registry_analysis"):
        raise HTTPException(status_code=400, detail="알 수 없는 행위")
    return await billing_service.preview_service_fee(db, current.user_id, req.action)


@router.post("/charge")
async def charge(
    req: ChargeRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """행위 발생 시 서비스 사용료 차감(프로젝트 생성·토지분석). LLM 과금과 별개."""
    if req.action not in ("project_create", "land_analysis", "sales_provision", "registry_issue", "registry_analysis"):
        raise HTTPException(status_code=400, detail="알 수 없는 행위")
    return await billing_service.charge_service(db, current.user_id, req.action)


class SetTierRequest(BaseModel):
    user_id: str
    tier: str


@router.get("/admin/config")
async def get_billing_config(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """관리자 전용: 현재 과금 설정(등급요금·할증·서비스료·단계별·무료횟수) 조회."""
    if not await billing_service.is_super_admin(db, current.user_id):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    from app.core.billing import get_config

    await billing_service.load_config(db, force=True)
    return get_config()


@router.put("/admin/config")
async def update_billing_config(
    override: dict,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """관리자 전용: 과금 금액 설정 수정/변경(DB 영속 + 즉시 반영 + 변경 감사).

    ★주체를 반드시 넘긴다. 저장은 billing_config 단일 행을 덮어써 이전 요율이 소멸하므로,
    여기서 안 넘기면 감사에 주체가 빈 채로 남는다 — 그러면 "이 청구가 어떤 요율에서
    나왔나"에는 답해도 "누가, 무슨 권한으로 그렇게 정했나"에는 못 답한다.
    감사 자체는 서비스 층(`save_config`)이 수행한다 — 이 결함이 생긴 방식이 바로
    **엔드포인트를 추가하며 감사 호출을 빠뜨린 것**이라, 잊을 수 없는 자리로 옮겼다.
    """
    if not await billing_service.is_super_admin(db, current.user_id):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    return await billing_service.save_config(
        db,
        override or {},
        actor_id=str(current.user_id),
        actor_role=getattr(current, "role", None),
    )


@router.post("/admin/set-tier")
async def admin_set_tier(
    req: SetTierRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """관리자 전용: 사용자 등급 변경."""
    if not await billing_service.is_super_admin(db, current.user_id):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    await billing_service.set_tier(db, req.user_id, req.tier)
    try:
        from app.core.audit import audit_admin_action
        await audit_admin_action(
            actor_id=str(getattr(current, "user_id", "") or ""), actor_role=getattr(current, "role", ""),
            action="billing.set_tier", target=req.user_id,
            tenant_id=str(getattr(current, "tenant_id", "") or ""), detail={"tier": req.tier},
        )
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "user_id": req.user_id, "tier": req.tier}


# ═══════════════════ 마이페이지 — 충전 주문·코인내역(2026-07-17) ═══════════════════


def _valid_uuid_or_404(value: str) -> str:
    """경로 주문 id 검증 — 비정형 문자열이 uuid 캐스트 오류(500)로 새지 않게 404로 정규화."""
    try:
        return str(_uuid.UUID(value))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=404, detail="주문을 찾을 수 없습니다.") from None


async def _require_active_user(db: AsyncSession, current: CurrentUser) -> None:
    """코인 변이(충전 주문·확정·취소) 공용 활성계정 가드.

    ★get_current_user는 JWT만 검증(무 DB)하므로, 탈퇴(deleted_at)·정지 계정의 access 토큰이
      만료 전(최대 30분) 잔존하는 창에서 잔액 변이가 성립할 수 있다. 민감 변이는 auth의 공용
      가드로 즉시 차단한다(성장루프 LOW 수렴, auth.py 변이 계약과 정합).
    """
    from apps.api.routers.auth import _load_current_active_user

    await _load_current_active_user(db, current)


@router.get("/packages")
async def list_packages(settings: Settings = Depends(get_settings)):
    """충전 패키지 안내(공개 — /plans와 동급 요금정보). 금액은 서버가 유일하게 결정.

    payment_mode: 프론트가 결제 확정 UI(시뮬레이션 self-confirm 버튼)를 정직하게 게이트하도록
      현재 결제 경로를 함께 알린다(simulated=데모 self-confirm 가능 / manual_only=관리자 확정만).
    """
    return {
        "packages": [
            {"key": k, "amount_krw": v["amount_krw"], "label": v["label"]}
            for k, v in coin_orders_service.COIN_PACKAGES.items()
        ],
        "custom": {
            "min_krw": coin_orders_service.CUSTOM_MIN_KRW,
            "max_krw": coin_orders_service.CUSTOM_MAX_KRW,
            "unit_krw": coin_orders_service.CUSTOM_UNIT_KRW,
        },
        # ★단일 리졸버 — 세 번째 값(`toss`)이 생겨도 여기가 갈라지지 않는다.
        "payment_mode": resolve_payment_mode(settings),
    }


class CreateOrderRequest(BaseModel):
    package_key: str = Field(max_length=32)
    # custom일 때만 사용 — 프리셋 키면 무시(금액은 서버 결정). plain float — nan/inf/음수는
    # resolve_order_amount의 isfinite+범위검증이 400으로 차단(pydantic echo 직렬화 버그 회피).
    amount_krw: float | None = Field(default=None)


@router.get("/orders")
async def my_orders(
    limit: int = 20,
    offset: int = 0,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """내 결제내역(충전 주문 목록) — 전자상거래법 §6 거래기록 열람 수단.

    ★정지·탈퇴 계정 차단(성장루프 LOW 수렴): get_current_user는 무 DB(JWT만)라 정지/탈퇴 계정도
      토큰 잔존 창(≤30분) 동안 유효하다. 결제/코인 조회는 변이 경로·GET /me와 동일하게 활성계정만
      허용해 접근제어를 일관화한다. (동의이력 /me/consents는 PIPA §22·§35 열람권이라 예외 유지.)
    """
    await _require_active_user(db, current)
    return {"orders": await coin_orders_service.list_orders(
        db, str(current.user_id), limit=limit, offset=offset
    )}


@router.post("/orders", status_code=201)
async def create_order(
    req: CreateOrderRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """충전 주문 생성(pending). 결제 확정은 별도 단계(시뮬레이션/관리자/후속 PG)."""
    # 입력 검증(무 DB)을 계정 조회보다 먼저 — 잘못된 상품·금액은 DB 접근 없이 400.
    try:
        coin_orders_service.resolve_order_amount(req.package_key, req.amount_krw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    await _require_active_user(db, current)
    try:
        order = await coin_orders_service.create_order(
            db, user_id=str(current.user_id), tenant_id=str(current.tenant_id),
            package_key=req.package_key, amount_krw=req.amount_krw,
        )
    except coin_orders_service.PendingCapExceededError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    except ValueError as e:  # 방어적(위에서 이미 검증됨)
        raise HTTPException(status_code=400, detail=str(e)) from None
    # 프론트가 다음 행동을 정직하게 안내하도록 결제 경로 상태를 함께 반환.
    order["payment_mode"] = resolve_payment_mode(settings)
    return order


@router.post("/orders/{order_id}/confirm")
async def confirm_my_order(
    order_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """주문 self-confirm — **시뮬레이션 모드 전용**(기본 꺼짐).

    ★프로덕션(플래그 off)에서는 501 정직 응답: 실결제(PG) 미연동 상태에서 사용자가
      스스로 지급을 만들 수 없다. 지급은 관리자 수동 확정 또는 후속 PG 웹훅만.
    """
    if not settings.billing_simulated_payments:
        raise HTTPException(
            status_code=501,
            detail="온라인 결제 연동 준비 중입니다. 계좌이체 후 관리자 확인으로 충전되며, 문의: k3880@kakao.com",
        )
    oid = _valid_uuid_or_404(order_id)  # 무 DB 검증 먼저
    await _require_active_user(db, current)
    try:
        return await coin_orders_service.confirm_order(
            db, order_id=oid, owner_user_id=str(current.user_id),
            provider="simulated", actor_id=str(current.user_id),
        )
    except coin_orders_service.OrderNotConfirmableError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None


@router.post("/orders/{order_id}/cancel")
async def cancel_my_order(
    order_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """pending 주문 취소(소유자 본인)."""
    oid = _valid_uuid_or_404(order_id)  # 무 DB 검증 먼저
    await _require_active_user(db, current)
    try:
        return await coin_orders_service.cancel_order(
            db, order_id=oid, user_id=str(current.user_id)
        )
    except coin_orders_service.OrderNotConfirmableError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None


@router.post("/admin/orders/{order_id}/confirm")
async def admin_confirm_order(
    order_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """관리자 수동 지급 확정(계좌이체 확인 대응) — 총괄관리자(tier=super_admin) 전용."""
    if not await billing_service.is_super_admin(db, current.user_id):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    oid = _valid_uuid_or_404(order_id)
    owner = await coin_orders_service.get_order_owner(db, oid)
    if owner is None:
        raise HTTPException(status_code=404, detail="주문을 찾을 수 없습니다.")
    try:
        result = await coin_orders_service.confirm_order(
            db, order_id=oid, owner_user_id=owner,
            provider="manual", actor_id=str(current.user_id),
        )
    except coin_orders_service.OrderNotConfirmableError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    try:
        from app.core.audit import audit_admin_action
        await audit_admin_action(
            actor_id=str(current.user_id), actor_role=getattr(current, "role", ""),
            action="billing.order_confirm", target=oid,
            tenant_id=str(getattr(current, "tenant_id", "") or ""),
            detail={"provider": "manual", "owner": owner},
        )
    except Exception:  # noqa: BLE001
        pass
    return result


@router.get("/ledger")
async def my_coin_ledger(
    days: int = 90,
    limit: int = 50,
    offset: int = 0,
    entry_type: str | None = None,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """내 코인내역 — 원장(충전·부여·서비스료·조정) ∪ AI 사용(llm_usage) 통합 타임라인."""
    await _require_active_user(db, current)  # 정지·탈퇴 계정 차단(접근제어 일관)
    return await coin_ledger_service.merged_history(
        str(current.user_id), days=days, limit=limit, offset=offset, entry_type=entry_type
    )


@router.get("/ledger/verify")
async def verify_my_coin_ledger(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """코인 원장 무결성 셀프검증(해시체인 재계산 대조) — 위·변조 탐지 결과 공개."""
    await _require_active_user(db, current)  # 정지·탈퇴 계정 차단
    return await coin_ledger_service.verify_chain(str(current.user_id))


def _csv_safe(value: object) -> str:
    """CSV 셀 값 안전화 — 포뮬러 인젝션(=,+,-,@,탭,CR) 방어 + RFC4180 인용.

    ★음수 금액(-1500) 같은 순수 숫자는 하이픈 가드에서 제외(데이터 오염 방지) —
      수식 위험은 숫자가 아닌 텍스트 선두 기호에만 있다.
    """
    s = "" if value is None else str(value)
    lead = s[:1]
    if lead in ("=", "+", "@", "\t", "\r"):
        s = "'" + s
    elif lead == "-":
        try:
            float(s)
        except ValueError:
            s = "'" + s
    if any(c in s for c in (",", '"', "\n", "\r")):
        s = '"' + s.replace('"', '""') + '"'
    return s


@router.get("/ledger/export")
async def export_my_coin_ledger(
    days: int = 365,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """코인내역 CSV 내보내기(최대 5,000행·utf-8-sig — 엑셀 한글 호환).

    ★단일 스냅샷 조회(export_rows) — offset 다중쿼리 순회의 누락/중복(동시쓰기·동률 재정렬) 없이
      전상법 §6 열람 정합성을 확보한다.
    """
    await _require_active_user(db, current)  # 정지·탈퇴 계정 차단
    items = await coin_ledger_service.export_rows(str(current.user_id), days=days, cap=5000)
    header = "일시,구분,금액(원),내용,참조유형,참조"
    lines = [header] + [
        ",".join(
            _csv_safe(v)
            for v in (
                it.get("created_at"), it.get("entry_type"), it.get("amount_krw"),
                it.get("description"), it.get("ref_type"), it.get("ref_id"),
            )
        )
        for it in items[:5000]
    ]
    # utf-8-sig BOM — 엑셀이 한글 CSV를 UTF-8로 인식하게 한다.
    csv_body = "﻿" + "\n".join(lines) + "\n"
    return Response(
        content=csv_body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="coin_history.csv"'},
    )


# ═════════════════════════════════════════════════════════════════════════════
# 토스페이먼츠 결제 (2026-08-27)
#
# 설계 근거는 `_workspace/PLAN_toss_payments_integration_2026-08-27.md`.
# 이 절이 지키는 것 세 가지:
#   ① **클라이언트를 믿지 않는다** — 금액·소유자는 서버 저장값으로만 판정
#   ② **HTTP 200 ≠ 승인** — `status == "DONE"` 만이 「돈이 움직였다」
#   ③ **모르는 것은 모른다고 말한다** — 미확정을 실패로 접지 않는다
# ═════════════════════════════════════════════════════════════════════════════
from app.services.billing import (  # noqa: E402
    payment_receipts,
    revenue_service,
    toss_orders_service,
    toss_payments,
)


def resolve_payment_mode(settings: Settings) -> str:
    """현재 결제 경로 — ★**이 함수가 유일한 판정처**다.

    옛 코드는 `"simulated" if settings.billing_simulated_payments else "manual_only"` 를
    **두 곳에 복제**해 뒀다. 세 번째 값을 넣는 순간 그 복제가 갈라진다.

    ★**상호배제**(보안 렌즈 C3): 시뮬레이션 self-confirm 은 **결제 없이 코인을 만든다.**
      토스가 켜져 있는데 그것도 켜져 있으면 결제 게이트가 통째로 우회된다
      (`POST /orders/{id}/confirm` 한 번에 무료 충전). 그래서 **토스가 우선**이고,
      토스가 켜지면 시뮬레이션은 **꺼진 것으로 취급**한다.
    """
    if toss_payments.is_configured():
        return "toss"
    if settings.billing_simulated_payments:
        return "simulated"
    return "manual_only"


class TossConfirmRequest(BaseModel):
    """결제창 인증 후 리다이렉트가 넘겨 준 값.

    ★`amount` 를 받되 **쓰지 않는다** — 서버 저장값과 **대조만** 한다.
      (문서가 요구하는 위변조 검증. 값 자체는 신뢰 대상이 아니다)
    """

    order_id: str = Field(..., min_length=6, max_length=64)
    payment_key: str = Field(..., min_length=1, max_length=200)
    amount: int = Field(..., ge=0)


class RefundRequest(BaseModel):
    reason: str = Field(..., min_length=2, max_length=200)
    #: None = 남은 전액. 부분 환불은 남은 결제금액 이내.
    amount: int | None = Field(default=None, ge=1)
    #: 가상계좌 환불 전용. ★키 이름은 `bank` 다(`bankCode` 아님 — 응답과 비대칭).
    refund_receive_account: dict[str, str] | None = None


def _payment_error(exc: Exception) -> HTTPException:
    """결제 예외 → HTTP. ★**사유와 조치를 반드시 실어 보낸다.**

    이 저장소가 데인 형태: *"폴백이 failure_reason 을 싣는데 화면 소비처 0건"*.
    그래서 여기서 버리면 사용자도 조사자도 원인을 모른다.
    """
    if isinstance(exc, toss_orders_service.PaymentRejectedError):
        return HTTPException(
            status_code=exc.http_status,
            detail={
                "code": exc.code,
                "message": exc.message,
                "remediation": exc.remediation,
                "retryable": exc.retryable,
                "outcome": "rejected",
            },
        )
    if isinstance(exc, toss_orders_service.PaymentPendingError):
        # ★202 — 실패가 아니다. 가상계좌 안내를 그대로 실어 사용자가 입금할 수 있게 한다.
        return HTTPException(
            status_code=202,
            detail={
                "code": exc.status,
                "message": str(exc),
                "remediation": "안내된 계좌로 입금하시면 자동으로 충전됩니다.",
                "outcome": "pending",
                "virtual_account": exc.virtual_account,
                "due_date": exc.due_date,
            },
        )
    if isinstance(exc, toss_orders_service.PaymentUnresolvedError):
        # ★409 — "실패"라고 말하지 않는다. 중복 결제를 유도하면 안 된다.
        return HTTPException(
            status_code=409,
            detail={
                "code": "PAYMENT_UNRESOLVED",
                "message": str(exc),
                "remediation": "중복 결제하지 마시고 충전 내역을 확인하신 뒤 고객센터로 문의해 주세요.",
                "outcome": "unresolved",
                "receipt_id": exc.receipt_id,
                "order_no": exc.order_no,
            },
        )
    raise exc


@router.get("/payments/toss/config")
async def toss_config(
    current: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """결제창을 띄우는 데 필요한 **공개** 설정.

    ★`client_key` 는 공개키다(브라우저가 쓴다). **시크릿 키는 절대 나가지 않는다.**
    ★경로가 `/billing/` 아래라 서비스워커의 `API_NO_STORE_PATTERNS` 에 걸려 캐시되지 않는다
      — 키를 교체했는데 옛 키가 재생되는 사고를 막는다(보안 렌즈 M6 실측).
    """
    mode = resolve_payment_mode(settings)
    return {
        "payment_mode": mode,
        "client_key": toss_payments.client_key() if mode == "toss" else None,
        # ★테스트 키면 실제 결제가 일어나지 않는다 — 화면이 그것을 크게 알려야 한다.
        "test_mode": toss_payments.is_test_mode() if mode == "toss" else None,
    }


@router.post("/payments/toss/confirm")
async def confirm_toss(
    req: TossConfirmRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """결제 승인 — 리다이렉트로 돌아온 결제를 서버가 확정한다.

    ★`amount` 를 받지만 **토스로 보내는 값은 서버 저장값**이다.
    ★활성계정 가드는 다른 코인 변이와 **같은 통로**를 쓴다(형제와 어긋나지 않게).
    """
    if resolve_payment_mode(settings) != "toss":
        raise HTTPException(status_code=501, detail="카드 결제가 설정되지 않았습니다.")
    oid = _valid_uuid_or_404(req.order_id)
    await _require_active_user(db, current)
    try:
        return await toss_orders_service.confirm_toss_payment(
            db,
            order_id=oid,
            payment_key=req.payment_key,
            claimed_amount=int(req.amount),
            current_user_id=str(current.user_id),
        )
    except (
        toss_orders_service.PaymentRejectedError,
        toss_orders_service.PaymentPendingError,
        toss_orders_service.PaymentUnresolvedError,
    ) as e:
        raise _payment_error(e) from e


@router.get("/orders/{order_id}/receipts")
async def order_receipts(
    order_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """내 주문의 **결제 처리 타임라인** — 무엇이 언제 어떻게 됐는지.

    ★사용자가 *"결제했는데 왜 코인이 없나"* 를 **스스로 확인**할 수 있게 한다.
      이게 없으면 모든 문의가 고객센터로 간다.
    """
    oid = _valid_uuid_or_404(order_id)
    owner = await coin_orders_service.get_order_owner(db, oid)
    # ★소유자 불일치도 404 — 존재 여부가 새면 주문 열거의 단서가 된다.
    if owner is None or str(owner) != str(current.user_id):
        raise HTTPException(status_code=404, detail="주문을 찾을 수 없습니다.")
    return {"order_id": oid, "receipts": await payment_receipts.list_for_order(db, oid)}


@router.post("/orders/{order_id}/refund")
async def refund_my_order(
    order_id: str,
    req: RefundRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """사용자 셀프 환불 — ★**남아 있는 코인 범위 안에서만.**

    이미 쓴 코인은 환불하지 않는다(없는 것을 돌려줄 수 없다). 그 경우 사유와 함께
    거절하고 고객센터로 안내한다 — 조용히 적게 환불하면 사용자가 모른다.
    """
    if resolve_payment_mode(settings) != "toss":
        raise HTTPException(status_code=501, detail="카드 결제가 설정되지 않았습니다.")
    oid = _valid_uuid_or_404(order_id)
    await _require_active_user(db, current)
    order_no = await coin_orders_service.get_order_no(db, oid)
    if order_no is None:
        raise HTTPException(status_code=404, detail="주문을 찾을 수 없습니다.")
    try:
        return await toss_orders_service.refund_toss_payment(
            db,
            order_no=order_no,
            reason=req.reason,
            amount=req.amount,
            actor_id=str(current.user_id),
            is_admin=False,
            refund_receive_account=req.refund_receive_account,
        )
    except (
        toss_orders_service.PaymentRejectedError,
        toss_orders_service.PaymentUnresolvedError,
    ) as e:
        raise _payment_error(e) from e


@router.post("/payments/toss/webhook")
async def toss_webhook(body: dict, db: AsyncSession = Depends(get_db)):
    """토스 웹훅 — ★**본문을 데이터로 쓰지 않는다.**

    ## 왜 본문을 안 믿나 (보안 렌즈 CRITICAL)

    토스 v2 의 결제/입금 웹훅에는 **서명이 없다**(서명 헤더는 `payout.changed`·
    `seller.changed` 에만 붙는다 — 법령 렌즈가 원문에서 확인). 이 엔드포인트는 토스가
    부르므로 **인증을 걸 수 없다.** 따라서 본문을 그대로 믿으면:

        POST /billing/payments/toss/webhook
        {"data": {"orderId": "<남의 주문>", "status": "DONE", "paymentKey": "아무거나"}}

    **누구나 무한히 코인을 만들 수 있다.**

    ## 그래서 본문은 **「뭔가 바뀌었다」는 신호로만** 쓴다

    `paymentKey`(또는 `orderId`)만 꺼내고, **우리 시크릿 키로 토스에 다시 물어** 진실을
    확인한다. 조작된 본문은 재조회에서 죽는다(존재하지 않는 결제 = 404).

    ★**항상 200 을 돌려준다.** 오류를 돌려주면 토스가 최대 7회 재전송한다(3일 19시간).
      그리고 유효/무효를 응답으로 구별해 주면 그 자체가 탐지 도구가 된다.
    """
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    payment_key = str(data.get("paymentKey") or body.get("paymentKey") or "").strip()
    order_id = str(data.get("orderId") or body.get("orderId") or "").strip()
    event_type = str(body.get("eventType") or ("DEPOSIT_CALLBACK" if body.get("secret") else ""))

    await payment_receipts.record(
        event=payment_receipts.EVENT_RECONCILED,
        order_id=order_id or None,
        payment_key=payment_key or None,
        toss_code=event_type or "WEBHOOK",
        toss_message="웹훅 수신 — 본문은 신호로만 사용",
        raw=body,
    )
    try:
        await toss_orders_service.reconcile_from_webhook(
            db, payment_key=payment_key or None, order_id=order_id or None
        )
    except Exception:  # noqa: BLE001 — 웹훅 응답은 언제나 200 이어야 한다
        logger.exception("토스 웹훅 처리 실패 — order_id=%s", order_id)
    return {"ok": True}


# ── 관리자 결제·매출 관리 ─────────────────────────────────────────────────────
async def _require_super_admin(db: AsyncSession, current: CurrentUser) -> None:
    """★`tier` 로 판정한다 — `role` 은 가입 시 전원이 자기 테넌트의 admin 이 되므로
    role 기반이면 **전원 통과**한다(`admin_secrets.py` 가 같은 근거를 적어 뒀다)."""
    if not await billing_service.is_super_admin(db, current.user_id):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")


@router.get("/admin/payments/health")
async def admin_payment_health(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """결제 연동 진단 — ★**키 값은 절대 반환하지 않는다**(존재·길이·환경만).

    ★`billing_simulated_payments` 가 켜져 있으면 **크게 경고**한다 —
      그 상태는 결제 없이 코인이 만들어지는 경로가 열려 있다는 뜻이다.
    """
    await _require_super_admin(db, current)
    cfg = toss_payments.config_status()
    warnings: list[str] = []
    if cfg["configured"] and not cfg["key_pairing_ok"]:
        warnings.append(
            "★클라이언트 키와 시크릿 키가 다른 환경(테스트/라이브)입니다 — 결제가 거절됩니다."
        )
    if cfg["configured"] and cfg["test_mode"]:
        warnings.append("★테스트 키를 사용 중입니다 — 실제 결제가 일어나지 않습니다.")
    if settings.billing_simulated_payments:
        warnings.append(
            "★시뮬레이션 결제가 켜져 있습니다 — 결제 없이 코인이 충전될 수 있습니다."
            " 운영 환경에서는 반드시 끄세요."
        )
    if not cfg["configured"]:
        warnings.append(
            "결제 키가 설정되지 않았습니다. 관리자 > API 키 > 「결제(PG)」에서 등록하세요."
        )
    return {
        **cfg,
        "payment_mode": resolve_payment_mode(settings),
        "simulated_payments_enabled": bool(settings.billing_simulated_payments),
        "warnings": warnings,
    }


@router.get("/admin/payments/revenue")
async def admin_revenue(
    days: int = 30,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """매출 관리 — 요약·일별추이·경로별·실패사유·상위결제자를 한 번에."""
    await _require_super_admin(db, current)
    d = max(1, min(int(days), 365))
    return {
        "summary": await revenue_service.summary(db, days=d),
        "daily": await revenue_service.daily(db, days=d),
        "by_provider": await revenue_service.by_provider(db, days=d),
        "failure_reasons": await revenue_service.failure_reasons(db, days=d),
        "top_payers": await revenue_service.top_payers(db, days=d),
        # ★관리자가 환불을 집행하는 목록. 이게 없으면 관리자 환불 API 는 도달 불가다.
        "recent_orders": await revenue_service.recent_orders(db, days=d),
        # ★매출과 **같은 응답**에 미해결 건을 싣는다 — 따로 두면 아무도 안 본다.
        "unresolved": await payment_receipts.list_unresolved(db, limit=50),
    }


@router.post("/admin/payments/{order_id}/reconcile")
async def admin_reconcile(
    order_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """★정합성 회복 — 「승인은 됐는데 코인이 안 들어간」 건을 **토스에 다시 물어** 바로잡는다.

    이것이 `payment_receipts` 가 존재하는 이유다. 영수증이 없으면 이 복구가 불가능하다.
    """
    await _require_super_admin(db, current)
    oid = _valid_uuid_or_404(order_id)
    result = await toss_orders_service.reconcile_order(db, order_id=oid, actor_id=str(current.user_id))
    from app.core.audit import audit_admin_action

    await audit_admin_action(
        db, actor_id=str(current.user_id), action="billing.payment_reconcile",
        target=oid, detail=result,
    )
    return result


@router.post("/admin/orders/{order_id}/refund")
async def admin_refund_order(
    order_id: str,
    req: RefundRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """관리자 대리 환불 — 감사 로그를 남긴다."""
    await _require_super_admin(db, current)
    oid = _valid_uuid_or_404(order_id)
    order_no = await coin_orders_service.get_order_no(db, oid)
    if order_no is None:
        raise HTTPException(status_code=404, detail="주문을 찾을 수 없습니다.")
    try:
        result = await toss_orders_service.refund_toss_payment(
            db, order_no=order_no, reason=req.reason, amount=req.amount,
            actor_id=str(current.user_id), is_admin=True,
            refund_receive_account=req.refund_receive_account,
        )
    except (
        toss_orders_service.PaymentRejectedError,
        toss_orders_service.PaymentUnresolvedError,
    ) as e:
        raise _payment_error(e) from e
    from app.core.audit import audit_admin_action

    await audit_admin_action(
        db, actor_id=str(current.user_id), action="billing.order_refund",
        target=oid, detail=result,
    )
    return result
