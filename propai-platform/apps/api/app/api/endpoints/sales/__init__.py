"""sales 라우터 조립 — 정형 CRUD(REGISTRY) 일괄 노출 + 전용 액션.

main 에서 sales_router 를 prefix="/api/v1/sales" 로 포함한다.
정형 엔티티는 make_crud_router 로, 도메인 액션은 actions_router 로 제공.
"""

from fastapi import APIRouter

import app.schemas.sales as S
from app.api.crud_router import make_crud_router
from app.api.endpoints.sales.actions import actions_router
from app.api.endpoints.sales.commission_agreement import commission_agreement_router
from app.api.endpoints.sales.crm_enhance import crm_enhance_router
from app.api.endpoints.sales.lifecycle_p5 import r5
from app.api.endpoints.sales.lifecycle_p6 import r6
from app.api.endpoints.sales.mh import mh_router
from app.api.endpoints.sales.referral import referral_router
from app.api.endpoints.sales.site_auth import site_auth_router
from app.api.endpoints.sales.termination_cert import termination_cert_router
from app.api.endpoints.sales.units_live import units_live_router
from app.api.endpoints.sales.views import views_router
from apps.api.database.models.sales import (
    commission_ext as ce,
)
from apps.api.database.models.sales import (
    commission_mh_harness as cm,
)
from apps.api.database.models.sales import (
    contract_crm_ad as cc,
)
from apps.api.database.models.sales import (
    guarantee as gu,
)
from apps.api.database.models.sales import (
    loan as ln,
)
from apps.api.database.models.sales import (
    options as opn,
)
from apps.api.database.models.sales import (
    resale as rs,
)
from apps.api.database.models.sales import (
    site_org as so,
)
from apps.api.database.models.sales import (
    staff as st,
)
from apps.api.database.models.sales import (
    subscription as sub,
)
from apps.api.database.models.sales import (
    tax as tx,
)
from apps.api.database.models.sales import (
    units_pricing as up,
)

sales_router = APIRouter()

# (model, prefix) — 정형 CRUD 실코드 자동 적용
REGISTRY = [
    (so.SalesOrgCompany, "org-companies"), (so.SalesOrgContract, "org-contracts"),
    (st.SalesStaff, "staff"), (st.SalesStaffPhoneIndex, "staff-phones"),
    (st.SalesStaffAttendance, "attendance"), (st.SalesStaffSchedule, "schedules"),
    (st.SalesStaffDocument, "staff-docs"),
    (up.SalesUnitBlock, "blocks"), (up.SalesUnitType, "unit-types"),
    (up.SalesUnitInventory, "units"), (up.SalesUnitHold, "unit-holds"),
    (up.SalesDevTypeProfile, "dev-type-profile"), (up.SalesRound, "rounds"),
    (up.SalesPriceBase, "pricing-base"), (up.SalesPriceWeight, "pricing-weights"),
    (up.SalesPriceGroup, "pricing-groups"), (up.SalesPriceGroupMember, "pricing-group-members"),
    (up.SalesPriceComposition, "pricing-composition"),
    (cc.SalesApplication, "applications"), (cc.SalesContractExt, "contracts"),
    (cc.SalesContractInstallment, "installments"), (cc.SalesContractDocument, "contract-docs"),
    (cc.SalesCustomer, "customers"), (cc.SalesCustomerConsent, "consents"),
    (cc.SalesCustomerAssignment, "assignments"), (cc.SalesCustomerConsultation, "consultations"),
    (cc.SalesCustomerCall, "calls"),
    (cc.SalesAdCampaign, "ad-campaigns"), (cc.SalesAdChannel, "ad-channels"),
    (cc.SalesAdSpend, "ad-spend"), (cc.SalesAdLead, "ad-leads"), (cc.SalesAdCompliance, "ad-compliance"),
    (cm.SalesCommissionMaster, "commission-master"), (cm.SalesCommissionDistribution, "commission-distribution"),
    (cm.SalesCommissionClaim, "commission-claims"), (cm.SalesCommissionSettlement, "commission-settlements"),
    (cm.SalesWorkLog, "work-logs"),
    # Part5 [Q]청약 [R]옵션 [S]대출 [U]수납 — VA(민감)는 CRUD 미노출(액션 /payments/va/issue 사용)
    (sub.SalesSubscriptionAnnouncement, "subscription/announcements"),
    (sub.SalesSubscriptionApplication, "subscription/applications"),
    (sub.SalesSubscriptionWinner, "subscription/winners"),
    (opn.SalesOptionCatalog, "options/catalog"),
    (ln.SalesLoanProgram, "loan/programs"), (ln.SalesLoanAgreement, "loan/agreements"),
    # ★payments/overdue 는 자동 CRUD 에서 제거했다(예전엔 (pm.SalesOverdueInterest, "payments/overdue")).
    #   r5(lifecycle_p5)의 전용 GET 핸들러가 회차별 최신 calc_date 1건만(DISTINCT ON) 돌려주는데,
    #   자동 CRUD 가 같은 prefix 로 GET/POST 를 또 찍어내면 (등록순서로 r5 가 이기긴 하지만) 같은
    #   경로를 두 writer 가 소유하는 모호함이 남았다. 등록순서 의존을 없애고 r5 가 단독 소유하게
    #   REGISTRY 에서 뺀다(POST 도 멱등 핸들러 webhook/run-overdue 로만 — 자동 CRUD POST shadow 제거).
    # Part6 [T]보증/신탁 [V]실거래/전매 [W]수수료확장 [X]세무
    (gu.SalesGuaranteePolicy, "guarantee/policies"), (gu.SalesTrustAccount, "trust/accounts"),
    (rs.SalesRealtxReport, "realtx/reports"), (rs.SalesResaleRestriction, "resale/restrictions"),
    (rs.SalesResaleTransfer, "resale/transfers"),
    (ce.SalesCommissionPayoutSchedule, "commission/schedule"), (ce.SalesCommissionHoldback, "commission/holdback-list"),
    (tx.SalesTaxInvoice, "tax/invoices-list"), (tx.SalesWithholdingStatement, "tax/withholding-list"),
]

# ── 등록 순서 규칙(중요) ─────────────────────────────────────────────
# '구체적인 업무 라우터'를 '자동 CRUD'보다 반드시 '먼저' 등록한다.
# 왜? 자동 CRUD(make_crud_router)는 모델마다 GET/POST /<prefix>, GET/PATCH/DELETE /<prefix>/{id}
# 같은 일반 경로를 찍어낸다. 그런데 우리가 따로 만든 똑똑한 핸들러가 같은 경로를 쓰는 경우가 있다.
#   예) POST /contracts(가격 자동산출·세대 RESERVED 전환), GET /contracts(선택기 라벨 목록),
#       GET /work-logs/summary(실적 집계), POST /work-logs(활동→고객 이력 연계).
# FastAPI는 '먼저 등록된 경로'가 이기므로, CRUD가 앞서면 우리 핸들러가 가려져
# 라벨이 비거나(선택기), "summary"가 UUID로 잘못 파싱돼 422가 나는 식으로 조용히 깨진다.
# 따라서 업무 라우터를 전부 앞에 두고, 일반 CRUD는 맨 마지막에 '못 잡힌 경로의 기본값'으로만 둔다.
sales_router.include_router(actions_router)
sales_router.include_router(commission_agreement_router)
sales_router.include_router(crm_enhance_router)
sales_router.include_router(referral_router)
sales_router.include_router(termination_cert_router)
sales_router.include_router(site_auth_router)
sales_router.include_router(mh_router)
sales_router.include_router(views_router)
sales_router.include_router(units_live_router)
sales_router.include_router(r5)
sales_router.include_router(r6)

# 일반 CRUD는 맨 마지막(위 업무 라우터가 못 잡은 경로만 처리 = 안전한 폴백).
for _model, _prefix in REGISTRY:
    _name = _model.__name__
    sales_router.include_router(make_crud_router(
        model=_model,
        create_schema=getattr(S, f"{_name}Create"),
        update_schema=getattr(S, f"{_name}Update"),
        read_schema=getattr(S, f"{_name}Read"),
        prefix=f"/{_prefix}", tags=["sales"],
    ))
