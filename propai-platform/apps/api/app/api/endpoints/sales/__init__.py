"""sales 라우터 조립 — 정형 CRUD(REGISTRY) 일괄 노출 + 전용 액션.

main 에서 sales_router 를 prefix="/api/v1/sales" 로 포함한다.
정형 엔티티는 make_crud_router 로, 도메인 액션은 actions_router 로 제공.
"""

from fastapi import APIRouter

import app.schemas.sales as S
from app.api.crud_router import make_crud_router
from app.api.endpoints.sales.actions import actions_router
from app.api.endpoints.sales.commission_agreement import commission_agreement_router
from app.api.endpoints.sales.site_auth import site_auth_router
from app.api.endpoints.sales.mh import mh_router
from app.api.endpoints.sales.views import views_router
from app.api.endpoints.sales.lifecycle_p5 import r5
from app.api.endpoints.sales.lifecycle_p6 import r6
from apps.api.database.models.sales import (
    commission_mh_harness as cm, contract_crm_ad as cc, site_org as so, staff as st, units_pricing as up,
)
from apps.api.database.models.sales import (
    loan as ln, options as opn, payment as pm, subscription as sub,
)
from apps.api.database.models.sales import (
    commission_ext as ce, guarantee as gu, resale as rs, tax as tx,
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
    (pm.SalesOverdueInterest, "payments/overdue"),
    # Part6 [T]보증/신탁 [V]실거래/전매 [W]수수료확장 [X]세무
    (gu.SalesGuaranteePolicy, "guarantee/policies"), (gu.SalesTrustAccount, "trust/accounts"),
    (rs.SalesRealtxReport, "realtx/reports"), (rs.SalesResaleRestriction, "resale/restrictions"),
    (rs.SalesResaleTransfer, "resale/transfers"),
    (ce.SalesCommissionPayoutSchedule, "commission/schedule"), (ce.SalesCommissionHoldback, "commission/holdback-list"),
    (tx.SalesTaxInvoice, "tax/invoices-list"), (tx.SalesWithholdingStatement, "tax/withholding-list"),
]

for _model, _prefix in REGISTRY:
    _name = _model.__name__
    sales_router.include_router(make_crud_router(
        model=_model,
        create_schema=getattr(S, f"{_name}Create"),
        update_schema=getattr(S, f"{_name}Update"),
        read_schema=getattr(S, f"{_name}Read"),
        prefix=f"/{_prefix}", tags=["sales"],
    ))

sales_router.include_router(actions_router)
sales_router.include_router(commission_agreement_router)
sales_router.include_router(site_auth_router)
sales_router.include_router(mh_router)
sales_router.include_router(views_router)
sales_router.include_router(r5)
sales_router.include_router(r6)
