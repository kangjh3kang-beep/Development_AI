"""v62 분양관리 ERP + 모델하우스 데스크 모델 패키지 (66 테이블).

모든 모델을 명시 import 하여 Base.metadata / Alembic autogenerate 에 등록한다.
"""

from apps.api.database.models.sales.site_org import (
    SalesSite, SalesSiteProvisioning, SalesSiteConfig, SalesOrgCompany, SalesOrgNode,
    SalesOrgMembershipHistory, SalesOrgContract, SalesSiteSummary,
)
from apps.api.database.models.sales.staff import (
    SalesStaff, SalesStaffPhoneIndex, SalesStaffAttendance, SalesStaffSchedule, SalesStaffDocument,
)
from apps.api.database.models.sales.units_pricing import (
    SalesUnitBlock, SalesUnitType, SalesUnitInventory, SalesUnitPriceTable, SalesUnitHold,
    SalesUnitStatusLog, SalesUnitGeneration, SalesDevTypeProfile, SalesRound, SalesPriceBase,
    SalesPriceWeight, SalesPriceGroup, SalesPriceGroupMember, SalesPriceComposition,
    SalesUnitPriceBreakdown, SalesPriceGenerationLog,
)
from apps.api.database.models.sales.contract_crm_ad import (
    SalesApplication, SalesContractExt, SalesContractInstallment, SalesContractDocument,
    SalesContractChange, SalesEcontractLink, SalesCustomer, SalesCustomerConsent,
    SalesCustomerAssignment, SalesCustomerConsultation, SalesCustomerCall, SalesCustomerGradeLog,
    SalesAdCampaign, SalesAdChannel, SalesAdSpend, SalesAdLead, SalesAdCompliance,
)
from apps.api.database.models.sales.commission_mh_harness import (
    SalesCommissionMaster, SalesCommissionDistribution, SalesCommissionEvent, SalesCommissionSplit,
    SalesCommissionClaim, SalesCommissionApproval, SalesCommissionPayout, SalesCommissionClawback,
    SalesCommissionSettlement, MhDesk, MhVisitor, MhVisitConsent, MhStaffMatch, MhNotification,
    MhVisitStat, MhInventoryItem, MhInventoryTxn, SalesWorkLog,
    SalesHarnessOutbox, SalesHarnessSubscription,
)
# v62 Part5 — [Q]청약 [R]옵션 [S]대출 [U]수납 (13)
from apps.api.database.models.sales.subscription import (
    SalesSubscriptionAnnouncement, SalesSubscriptionApplication, SalesSubscriptionWinner,
    SalesSubscriptionReserveQueue, SalesUnrankedOffer,
)
from apps.api.database.models.sales.options import SalesOptionCatalog, SalesContractOption
from apps.api.database.models.sales.loan import SalesLoanProgram, SalesLoanAgreement, SalesLoanDisbursement
from apps.api.database.models.sales.payment import SalesVirtualAccount, SalesPayment, SalesOverdueInterest

__all__ = [
    # [A] 현장/조직 (8)
    "SalesSite", "SalesSiteProvisioning", "SalesSiteConfig", "SalesOrgCompany", "SalesOrgNode",
    "SalesOrgMembershipHistory", "SalesOrgContract", "SalesSiteSummary",
    # [B] 직원 (5)
    "SalesStaff", "SalesStaffPhoneIndex", "SalesStaffAttendance", "SalesStaffSchedule", "SalesStaffDocument",
    # [C] 동/호 (7) + [P] 분양가 (9)
    "SalesUnitBlock", "SalesUnitType", "SalesUnitInventory", "SalesUnitPriceTable", "SalesUnitHold",
    "SalesUnitStatusLog", "SalesUnitGeneration", "SalesDevTypeProfile", "SalesRound", "SalesPriceBase",
    "SalesPriceWeight", "SalesPriceGroup", "SalesPriceGroupMember", "SalesPriceComposition",
    "SalesUnitPriceBreakdown", "SalesPriceGenerationLog",
    # [D] 계약 (6) + [E] CRM (6) + [F] 광고 (5)
    "SalesApplication", "SalesContractExt", "SalesContractInstallment", "SalesContractDocument",
    "SalesContractChange", "SalesEcontractLink", "SalesCustomer", "SalesCustomerConsent",
    "SalesCustomerAssignment", "SalesCustomerConsultation", "SalesCustomerCall", "SalesCustomerGradeLog",
    "SalesAdCampaign", "SalesAdChannel", "SalesAdSpend", "SalesAdLead", "SalesAdCompliance",
    # [G] 수수료 (9) + [H] 데스크 (9) + [I] 하네스 (2)
    "SalesCommissionMaster", "SalesCommissionDistribution", "SalesCommissionEvent", "SalesCommissionSplit",
    "SalesCommissionClaim", "SalesCommissionApproval", "SalesCommissionPayout", "SalesCommissionClawback",
    "SalesCommissionSettlement", "MhDesk", "MhVisitor", "MhVisitConsent", "MhStaffMatch", "MhNotification",
    "MhVisitStat", "MhInventoryItem", "MhInventoryTxn", "SalesWorkLog",
    "SalesHarnessOutbox", "SalesHarnessSubscription",
    # [Q] 청약 (5)
    "SalesSubscriptionAnnouncement", "SalesSubscriptionApplication", "SalesSubscriptionWinner",
    "SalesSubscriptionReserveQueue", "SalesUnrankedOffer",
    # [R] 옵션 (2) + [S] 대출 (3) + [U] 수납 (3)
    "SalesOptionCatalog", "SalesContractOption",
    "SalesLoanProgram", "SalesLoanAgreement", "SalesLoanDisbursement",
    "SalesVirtualAccount", "SalesPayment", "SalesOverdueInterest",
]
