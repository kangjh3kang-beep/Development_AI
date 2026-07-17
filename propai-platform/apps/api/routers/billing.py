"""구독 과금 라우터 — 사용 현황·추가결제(시뮬레이션)·견적·등급변경(관리자).

마이페이지(2026-07-17): 충전 주문(coin_orders)·코인내역(coin_ledger ∪ llm_usage 통합)·
무결성 검증·CSV 내보내기 추가. 스펙=docs/design/MYPAGE_SAAS_SPEC_2026-07-17.md.
"""

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
    """관리자 전용: 과금 금액 설정 수정/변경(DB 영속 + 즉시 반영)."""
    if not await billing_service.is_super_admin(db, current.user_id):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    return await billing_service.save_config(db, override or {})


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
        "payment_mode": "simulated" if settings.billing_simulated_payments else "manual_only",
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
    order["payment_mode"] = "simulated" if settings.billing_simulated_payments else "manual_only"
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
