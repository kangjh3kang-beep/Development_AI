"""sales 라우터 조립 — 정형 CRUD(REGISTRY) 일괄 노출 + 전용 액션.

main 에서 sales_router 를 prefix="/api/v1/sales" 로 포함한다.
정형 엔티티는 make_crud_router 로, 도메인 액션은 actions_router 로 제공.
"""

from fastapi import APIRouter

import app.schemas.sales as S
from app.api.crud_router import make_crud_router
from app.api.endpoints.sales.actions import actions_router
from apps.api.database.models.sales import (
    commission_mh_harness as cm, contract_crm_ad as cc, site_org as so, staff as st, units_pricing as up,
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
