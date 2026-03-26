"""PropAI 공유 열거형 정의.

모든 에이전트가 참조하는 단일 소스.
변경 시 .build-journal/type-changes.md에 기록한다.
"""

try:
    from enum import StrEnum
except ImportError:
    # Python 3.10 호환성 백포트
    from enum import Enum
    class StrEnum(str, Enum):
        pass


class ProjectStatus(StrEnum):
    """프로젝트 진행 상태"""
    DRAFT = "draft"
    PLANNING = "planning"
    DESIGN = "design"
    PERMIT = "permit"
    CONSTRUCTION = "construction"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class EscrowStatus(StrEnum):
    """에스크로 트랜잭션 상태 (블록체인)

    온체인 매핑: PendingFunding(0) → PENDING_FUNDING,
    Funded(1) → FUNDED, Disputed(2) → DISPUTED,
    Released(3) → RELEASED, Refunded(4) → REFUNDED.
    FAILED는 DB 전용 상태 (온체인 트랜잭션 실패).
    """
    PENDING_FUNDING = "pending_funding"
    FUNDED = "funded"
    RELEASED = "released"
    DISPUTED = "disputed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"
    FAILED = "failed"


class DefectSeverity(StrEnum):
    """드론 하자 심각도"""
    EMERGENCY = "EMERGENCY"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class UserRole(StrEnum):
    """사용자 역할 (RBAC)"""
    ADMIN = "admin"
    MANAGER = "manager"
    ANALYST = "analyst"
    VIEWER = "viewer"


class AgentStepName(StrEnum):
    """7단계 에이전트 오케스트레이션 단계명"""
    PARCEL_ANALYSIS = "parcel_analysis"
    REGULATION = "regulation"
    DESIGN = "design"
    AVM = "avm"
    FEASIBILITY = "feasibility"
    PERMIT = "permit"
    REPORT = "report"


class TaskStatus(StrEnum):
    """비동기 태스크 상태"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DesignType(StrEnum):
    """설계 유형"""
    FLOOR_PLAN = "floor_plan"
    BIM_IFC = "bim_ifc"
    THREE_D = "three_d"
    SITE_PLAN = "site_plan"


class TaxType(StrEnum):
    """세금 유형"""
    ACQUISITION = "acquisition"       # 취득세
    PROPERTY = "property"             # 재산세
    TRANSFER = "transfer"             # 양도세
    COMPREHENSIVE_REAL_ESTATE = "comprehensive_real_estate"  # 종합부동산세
    REGISTRATION = "registration"     # 등록세
    INHERITANCE = "inheritance"       # 상속세
    GIFT = "gift"                     # 증여세


class RegulationType(StrEnum):
    """법규 유형"""
    ZONING = "zoning"                 # 용도지역
    BUILDING_CODE = "building_code"   # 건축법
    FIRE_SAFETY = "fire_safety"       # 소방법
    ENVIRONMENT = "environment"       # 환경법
    PARKING = "parking"               # 주차장법
    URBAN_PLANNING = "urban_planning" # 도시계획법


class CircuitBreakerState(StrEnum):
    """외부 API Circuit Breaker 상태"""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
