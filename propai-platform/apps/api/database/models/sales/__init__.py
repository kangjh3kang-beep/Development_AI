"""v62 분양관리 ERP + 모델하우스 데스크 모델 패키지 (66 테이블).

모든 모델을 명시 import 하여 Base.metadata / Alembic autogenerate 에 등록한다.
"""

from apps.api.database.models.sales.commission_ext import SalesCommissionHoldback, SalesCommissionPayoutSchedule
from apps.api.database.models.sales.commission_mh_harness import (
    MhDesk,
    MhInventoryItem,
    MhInventoryTxn,
    MhNotification,
    MhStaffMatch,
    MhVisitConsent,
    MhVisitor,
    MhVisitStat,
    SalesCommissionApproval,
    SalesCommissionClaim,
    SalesCommissionClawback,
    SalesCommissionDistribution,
    SalesCommissionEvent,
    SalesCommissionMaster,
    SalesCommissionPayout,
    SalesCommissionSettlement,
    SalesCommissionSplit,
    SalesHarnessOutbox,
    SalesHarnessSubscription,
    SalesWorkLog,
)
from apps.api.database.models.sales.contract_crm_ad import (
    SalesAdCampaign,
    SalesAdChannel,
    SalesAdCompliance,
    SalesAdLead,
    SalesAdSpend,
    SalesApplication,
    SalesContractChange,
    SalesContractDocument,
    SalesContractExt,
    SalesContractInstallment,
    SalesCustomer,
    SalesCustomerAssignment,
    SalesCustomerCall,
    SalesCustomerConsent,
    SalesCustomerConsultation,
    SalesCustomerGradeLog,
    SalesEcontractLink,
)

# v62 Part6 — [T]보증/신탁 [V]실거래/전매 [W]수수료확장 [X]세무 (9)
from apps.api.database.models.sales.guarantee import SalesGuaranteePolicy, SalesTrustAccount
from apps.api.database.models.sales.loan import SalesLoanAgreement, SalesLoanDisbursement, SalesLoanProgram
from apps.api.database.models.sales.options import SalesContractOption, SalesOptionCatalog
from apps.api.database.models.sales.payment import SalesOverdueInterest, SalesPayment, SalesVirtualAccount
from apps.api.database.models.sales.resale import (
    SalesRealtxReport,
    SalesResaleRestriction,
    SalesResaleTransfer,
)
from apps.api.database.models.sales.site_org import (
    SalesOrgCompany,
    SalesOrgContract,
    SalesOrgMembershipHistory,
    SalesOrgNode,
    SalesSite,
    SalesSiteConfig,
    SalesSiteProvisioning,
    SalesSiteSummary,
)
from apps.api.database.models.sales.staff import (
    SalesStaff,
    SalesStaffAttendance,
    SalesStaffDocument,
    SalesStaffPhoneIndex,
    SalesStaffSchedule,
)

# v62 Part5 — [Q]청약 [R]옵션 [S]대출 [U]수납 (13)
from apps.api.database.models.sales.subscription import (
    SalesSubscriptionAnnouncement,
    SalesSubscriptionApplication,
    SalesSubscriptionReserveQueue,
    SalesSubscriptionWinner,
    SalesUnrankedOffer,
)
from apps.api.database.models.sales.tax import SalesTaxInvoice, SalesWithholdingStatement
from apps.api.database.models.sales.units_pricing import (
    SalesDevTypeProfile,
    SalesPriceBase,
    SalesPriceComposition,
    SalesPriceGenerationLog,
    SalesPriceGroup,
    SalesPriceGroupMember,
    SalesPriceWeight,
    SalesRound,
    SalesUnitBlock,
    SalesUnitGeneration,
    SalesUnitHold,
    SalesUnitInventory,
    SalesUnitPriceBreakdown,
    SalesUnitPriceTable,
    SalesUnitStatusLog,
    SalesUnitType,
)

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
    # Part6 [T]보증/신탁(2) [V]실거래/전매(3) [W]수수료확장(2) [X]세무(2)
    "SalesGuaranteePolicy", "SalesTrustAccount",
    "SalesRealtxReport", "SalesResaleRestriction", "SalesResaleTransfer",
    "SalesCommissionPayoutSchedule", "SalesCommissionHoldback",
    "SalesTaxInvoice", "SalesWithholdingStatement",
]
