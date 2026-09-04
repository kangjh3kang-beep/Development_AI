"""부지기반(site basis) 라우터 — 항목5(WP-G LOW-a) 테넌트 없는 세션 fail-closed 테스트.

수용 게이트: POST /api/v1/basis/{run_id}/approve는 tenant_id가 없는 세션(current_user에
tenant_id가 비어있음)을 403으로 거부한다(fail-closed). 이 검사는 DB·서비스 계층 호출보다
먼저 실행되므로, DB 세션을 실제로 열지 않고도(가짜 객체로 충분) 결정적으로 검증 가능하다.

★fastapi TestClient(전체 앱 기동) 없이 라우터 async 함수를 직접 호출한다 — 이 파일의 다른
테스트(test_site_basis_state.py 등)와 동일하게 "결정적 픽스처만" 원칙을 따른다.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.routers.basis import approve_endpoint, assess_endpoint, get_endpoint
from app.schemas.basis import SiteBasisApproveRequest, SiteBasisAssessRequest


class _NoTenantUser:
    """tenant_id 속성 자체가 없는(또는 빈 문자열인) 세션 — 정직하게 None으로 취급돼야 한다."""

    id = "user-no-tenant"
    email = "no-tenant@example.com"


class _EmptyTenantUser:
    """tenant_id가 빈 문자열인 세션 — _tenant_of가 falsy를 None으로 정규화하는 경로."""

    id = "user-empty-tenant"
    tenant_id = ""


class _WithTenantUser:
    """정상 테넌트 세션."""

    id = "user-with-tenant"
    tenant_id = "tenant-a"


# ── 항목5 — approve만 fail-closed(403) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_approve_rejects_missing_tenant_attr_with_403():
    """tenant_id 속성이 아예 없는 세션 → approve는 DB 호출 전에 403으로 거부."""
    with pytest.raises(HTTPException) as exc:
        await approve_endpoint(
            run_id="basis_deadbeefdeadbeef",
            req=SiteBasisApproveRequest(),
            db=None,  # ★fail-closed 검사가 DB보다 먼저 실행됨을 증명(None이어도 안전).
            current_user=_NoTenantUser(),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_approve_rejects_empty_string_tenant_with_403():
    """tenant_id가 빈 문자열인 세션도 _tenant_of가 None으로 정규화 → 403."""
    with pytest.raises(HTTPException) as exc:
        await approve_endpoint(
            run_id="basis_deadbeefdeadbeef",
            req=SiteBasisApproveRequest(),
            db=None,
            current_user=_EmptyTenantUser(),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_approve_with_tenant_passes_hardening_gate_and_reaches_service():
    """정상 테넌트 세션은 하드닝 게이트를 통과해 서비스 계층까지 도달한다(그다음 실패는 DB
    부재 등 다른 원인 — 이 테스트는 '403으로 막히지 않음'만 확인, 서비스 성공은 별도 스코프)."""
    with pytest.raises(Exception) as exc:  # noqa: PT011 — DB=None으로 인한 하류 예외는 허용(게이트 통과만 검증)
        await approve_endpoint(
            run_id="basis_deadbeefdeadbeef",
            req=SiteBasisApproveRequest(),
            db=None,
            current_user=_WithTenantUser(),
        )
    # 403(fail-closed)이 아니라 다른 예외(DB 접근 시도로 인한 AttributeError 등)여야 한다.
    assert not (isinstance(exc.value, HTTPException) and exc.value.status_code == 403)


# ── /assess·GET은 이 하드닝 범위 밖(제품결정 문구 유지) — 테넌트 없어도 403 아님 ──────


@pytest.mark.asyncio
async def test_assess_endpoint_not_hardened_by_this_change():
    """/assess는 조회·집계뿐이라 항목5 하드닝 대상이 아니다 — 테넌트 없어도 403으로 막히지
    않는다. assess_site_basis는 DB 실패까지 graceful(best-effort)로 흡수해 정상 판정을
    반환하도록 설계돼 있으므로(원 지시 회귀 스위트의 기존 계약), 예외가 아예 안 날 수도 있다
    — 어느 경우든 HTTPException(403)만 아니면 이 항목5 무관 검증은 충족된다."""
    try:
        result = await assess_endpoint(
            req=SiteBasisAssessRequest(),
            db=None,
            current_user=_NoTenantUser(),
        )
        assert result is not None
    except HTTPException as exc:
        assert exc.status_code != 403


@pytest.mark.asyncio
async def test_get_endpoint_not_hardened_by_this_change():
    """GET /{run_id}도 항목5 하드닝 대상이 아니다(조회뿐 — 승인 아님)."""
    with pytest.raises(Exception) as exc:  # noqa: PT011 — DB=None 하류 예외는 허용
        await get_endpoint(run_id="basis_deadbeefdeadbeef", db=None, current_user=_NoTenantUser())
    assert not (isinstance(exc.value, HTTPException) and exc.value.status_code == 403)
