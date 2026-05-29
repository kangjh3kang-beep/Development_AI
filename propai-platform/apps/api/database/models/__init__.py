"""ORM 모델 패키지.

80개 테이블 + 2개 TimescaleDB 하이퍼테이블.
모든 핵심 테이블은 tenant_id 기반 RLS 격리를 전제로 한다.
"""

from apps.api.database.models.ai_usage_log import AIUsageLog

# v49.0 Part-N DevOps 모델
from apps.api.database.models.alert_rule import AlertRule
from apps.api.database.models.api_key import APIKey
from apps.api.database.models.auto_correction_history import AutoCorrectionHistory
from apps.api.database.models.avm_valuation import AVMValuation
from apps.api.database.models.backup_log import BackupLog
from apps.api.database.models.base import Base, TenantMixin, TimestampMixin

# v44.0 G96~G99 CAD/법규 엔진 모델
from apps.api.database.models.building_regulations import BuildingRegulation
from apps.api.database.models.cad_edit_history import CADEditHistory
from apps.api.database.models.compliance_violations import ComplianceViolationRecord
from apps.api.database.models.construction_log import ConstructionLog
from apps.api.database.models.cost_escalation_snapshot import CostEscalationSnapshot
from apps.api.database.models.design import Design
from apps.api.database.models.design_version import DesignVersion
from apps.api.database.models.development_method import DevelopmentMethodResult
from apps.api.database.models.digital_twin_anomaly import DigitalTwinAnomaly
from apps.api.database.models.drone_inspection import DroneInspection
from apps.api.database.models.escrow_transaction import EscrowTransaction
from apps.api.database.models.esign_request import ESignRequest
from apps.api.database.models.facility_reservation import FacilityReservation
from apps.api.database.models.financial_analysis import FinancialAnalysis
from apps.api.database.models.financing_structure import FinancingStructure
from apps.api.database.models.monte_carlo_result import MonteCarloResult
from apps.api.database.models.jeonse_analysis import JeonseAnalysis
from apps.api.database.models.kdx_market_metric import KDXMarketMetric
from apps.api.database.models.material_price_history import MaterialPriceHistory

# LCC 생애주기비용 (ISO 15686-5)
from apps.api.database.models.lcc_calculation import LccCalculation

# v50 KDX Integration
from apps.api.database.models.kdx_telemetry_log import KDXTelemetryLog
from apps.api.database.models.legal_audit_trail import LegalAuditTrail
from apps.api.database.models.model_performance import ModelPerformance
from apps.api.database.models.monitoring_metric import MonitoringMetric
from apps.api.database.models.notification_message import NotificationMessage
from apps.api.database.models.parcel import Parcel
from apps.api.database.models.parking_record import ParkingRecord

# Phase E
from apps.api.database.models.phase_e_climate import (
    ClimateRiskAssessment,
    InsuranceRecommendation,
)
from apps.api.database.models.phase_e_compliance import AMLScreening, ComplianceCheck, KYCDocument
from apps.api.database.models.phase_e_esg import CarbonFootprint, ESGReport, GRESBAssessment
from apps.api.database.models.phase_e_lease import LeaseAbstraction, LeaseIFRS16Schedule
from apps.api.database.models.phase_e_underwriting import (
    DataRoomDocument,
    InvestmentUnderwriting,
    LPReport,
)

# Phase F
from apps.api.database.models.phase_f_asset_intelligence import (
    AssetIntelligenceSnapshot,
    CapexOptimizationResult,
)
from apps.api.database.models.phase_f_domain_agents import DomainAgentApproval, DomainAgentTask
from apps.api.database.models.phase_f_maintenance import (
    EquipmentSensor,
    PredictiveMaintenanceAlert,
    WorkOrder,
)
from apps.api.database.models.phase_f_marketing import MarketingContent, OfferingMemorandum
from apps.api.database.models.phase_f_tenant import (
    TenantFinancialHealth,
    TenantSentimentScore,
    TenantTicket,
)

# Phase G
from apps.api.database.models.phase_g_ai_costs import AICostBudget
from apps.api.database.models.phase_g_chatbot import ChatbotMessage, ChatbotSession
from apps.api.database.models.phase_g_energy import (
    EnergyCertificationRecord,
    EnergyCertScore,
    KepcoRateCache,
)
from apps.api.database.models.phase_g_multilingual import MultilingualReport, TranslationJob
from apps.api.database.models.phase_g_operations import AuctionListing, Contractor
from apps.api.database.models.phase_g_portal import PortalListing, PortalPerformance
from apps.api.database.models.phase_v53_contracts import GeneratedContractDraft
from apps.api.database.models.phase_v53_operations import (
    DigitalTwinStatusSnapshot,
    PermitSubmission,
    UnifiedRiskAssessment,
)
from apps.api.database.models.project import Project
from apps.api.database.models.quantity_takeoff import QuantityTakeoff
from apps.api.database.models.rate_limit_violation import RateLimitViolation
from apps.api.database.models.re100_tracking import Re100Tracking
from apps.api.database.models.refresh_token import RefreshToken
from apps.api.database.models.regulation import Regulation
from apps.api.database.models.safety_violation import SafetyViolation
from apps.api.database.models.tax_calculation import TaxCalculation
from apps.api.database.models.tenant import Tenant
from apps.api.database.models.timeseries import DroneDetectionEvent, IoTCarbonSensor
from apps.api.database.models.user import User
from apps.api.database.models.webhook import Webhook
from apps.api.database.models.webhook_delivery import WebhookDelivery
from apps.api.database.models.webrtc_session import WebRTCSession

# v57 Track A 완성 모델
from apps.api.database.models.development_workflow import DevelopmentWorkflow
from apps.api.database.models.floor_plan import CadElement, FloorPlan
from apps.api.database.models.green_certification import GreenCertification
from apps.api.database.models.low_carbon_alternative import LowCarbonAlternative
from apps.api.database.models.reference_image import ReferenceImage
from apps.api.database.models.stakeholder import Stakeholder

# VCS (수지분석 버전관리)
from apps.api.database.models.feasibility_vcs import FeasibilityCommit, FeasibilityBranch, FeasibilityTag

# v61 설계도면
from apps.api.database.models.v61_design import (
    DesignStage, Drawing, DrawingLayer, DrawingEditHistory,
    PermitDocumentSet, DesignAlternative,
)
# v61 BIM 공사비
from apps.api.database.models.v61_cost import (
    CostWorkType, MaterialUnitPrice, BimQuantity, CostCalculationSheet,
    ProgressBilling, LegalRateHistory, StandardPriceUpdate,
)

__all__ = [
    "Base",
    "TenantMixin",
    "TimestampMixin",
    # 기본 엔티티
    "Tenant",
    "User",
    "RefreshToken",
    "Project",
    "Parcel",
    "Design",
    "Regulation",
    "AVMValuation",
    "FinancialAnalysis",
    "ConstructionLog",
    "CostEscalationSnapshot",
    "DroneInspection",
    "TaxCalculation",
    "EscrowTransaction",
    "LegalAuditTrail",
    "AIUsageLog",
    "ModelPerformance",
    "NotificationMessage",
    "IoTCarbonSensor",
    "DroneDetectionEvent",
    "JeonseAnalysis",
    "Webhook",
    "WebhookDelivery",
    "APIKey",
    "ESignRequest",
    # Phase E
    "InvestmentUnderwriting",
    "LPReport",
    "DataRoomDocument",
    "ComplianceCheck",
    "KYCDocument",
    "AMLScreening",
    "LeaseAbstraction",
    "LeaseIFRS16Schedule",
    "ESGReport",
    "CarbonFootprint",
    "GRESBAssessment",
    "ClimateRiskAssessment",
    "InsuranceRecommendation",
    # Phase F
    "MarketingContent",
    "OfferingMemorandum",
    "DomainAgentTask",
    "DomainAgentApproval",
    "EquipmentSensor",
    "PredictiveMaintenanceAlert",
    "WorkOrder",
    "TenantTicket",
    "TenantSentimentScore",
    "TenantFinancialHealth",
    "AssetIntelligenceSnapshot",
    "CapexOptimizationResult",
    # Phase G
    "AICostBudget",
    "PortalListing",
    "PortalPerformance",
    "MultilingualReport",
    "TranslationJob",
    "KepcoRateCache",
    "EnergyCertificationRecord",
    "EnergyCertScore",
    "AuctionListing",
    "Contractor",
    "ChatbotSession",
    "ChatbotMessage",
    "GeneratedContractDraft",
    # v44.0 G96~G99
    "BuildingRegulation",
    "CADEditHistory",
    "ComplianceViolationRecord",
    "AutoCorrectionHistory",
    # v49.0 Part-N DevOps
    "MonitoringMetric",
    "BackupLog",
    "RateLimitViolation",
    "AlertRule",
    # v49.0 Phase 2 (G113~G119)
    "SafetyViolation",
    "ParkingRecord",
    "WebRTCSession",
    "DigitalTwinAnomaly",
    "DigitalTwinStatusSnapshot",
    "FacilityReservation",
    # v50 KDX Integration
    "KDXTelemetryLog",
    "KDXMarketMetric",
    "MaterialPriceHistory",
    # RE100 + K-ETS
    "Re100Tracking",
    # LCC 생애주기비용
    "LccCalculation",
    # Monte Carlo 시뮬레이션 + 개발방법 평가
    "MonteCarloResult",
    "DevelopmentMethodResult",
    # Tier 3 신규 테이블
    "DesignVersion",
    "FinancingStructure",
    "QuantityTakeoff",
    "UnifiedRiskAssessment",
    "PermitSubmission",
    # v57 Track A
    "ReferenceImage",
    "GreenCertification",
    "LowCarbonAlternative",
    "Stakeholder",
    "DevelopmentWorkflow",
    "FloorPlan",
    "CadElement",
    # VCS (수지분석 버전관리)
    "FeasibilityCommit",
    "FeasibilityBranch",
    "FeasibilityTag",
    # v61 설계도면
    "DesignStage",
    "Drawing",
    "DrawingLayer",
    "DrawingEditHistory",
    "PermitDocumentSet",
    "DesignAlternative",
    # v61 BIM 공사비
    "CostWorkType",
    "MaterialUnitPrice",
    "BimQuantity",
    "CostCalculationSheet",
    "ProgressBilling",
    "LegalRateHistory",
    "StandardPriceUpdate",
]
