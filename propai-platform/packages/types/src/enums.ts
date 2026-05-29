// PropAI v30.0 - 공유 열거형 (packages/schemas/enums.py 미러)

export const ProjectStatus = {
  DRAFT: 'draft',
  PLANNING: 'planning',
  DESIGN: 'design',
  PERMIT: 'permit',
  CONSTRUCTION: 'construction',
  COMPLETED: 'completed',
  ARCHIVED: 'archived',
} as const;
export type ProjectStatus = (typeof ProjectStatus)[keyof typeof ProjectStatus];

export const EscrowStatus = {
  PENDING_FUNDING: 'pending_funding',
  FUNDED: 'funded',
  RELEASED: 'released',
  DISPUTED: 'disputed',
  REFUNDED: 'refunded',
  CANCELLED: 'cancelled',
  FAILED: 'failed',
} as const;
export type EscrowStatus = (typeof EscrowStatus)[keyof typeof EscrowStatus];

export const DefectSeverity = {
  EMERGENCY: 'EMERGENCY',
  HIGH: 'HIGH',
  MEDIUM: 'MEDIUM',
  LOW: 'LOW',
} as const;
export type DefectSeverity = (typeof DefectSeverity)[keyof typeof DefectSeverity];

export const UserRole = {
  ADMIN: 'admin',
  MANAGER: 'manager',
  ANALYST: 'analyst',
  VIEWER: 'viewer',
} as const;
export type UserRole = (typeof UserRole)[keyof typeof UserRole];

export const AgentStepName = {
  PARCEL_ANALYSIS: 'parcel_analysis',
  REGULATION: 'regulation',
  DESIGN: 'design',
  AVM: 'avm',
  FEASIBILITY: 'feasibility',
  PERMIT: 'permit',
  REPORT: 'report',
} as const;
export type AgentStepName = (typeof AgentStepName)[keyof typeof AgentStepName];

export const TaskStatus = {
  PENDING: 'pending',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
  CANCELLED: 'cancelled',
} as const;
export type TaskStatus = (typeof TaskStatus)[keyof typeof TaskStatus];

export const DesignType = {
  FLOOR_PLAN: 'floor_plan',
  BIM_IFC: 'bim_ifc',
  THREE_D: 'three_d',
  SITE_PLAN: 'site_plan',
} as const;
export type DesignType = (typeof DesignType)[keyof typeof DesignType];

export const TaxType = {
  ACQUISITION: 'acquisition',
  PROPERTY: 'property',
  TRANSFER: 'transfer',
  COMPREHENSIVE_REAL_ESTATE: 'comprehensive_real_estate',
  REGISTRATION: 'registration',
  INHERITANCE: 'inheritance',
  GIFT: 'gift',
} as const;
export type TaxType = (typeof TaxType)[keyof typeof TaxType];

export const RegulationType = {
  ZONING: 'zoning',
  BUILDING_CODE: 'building_code',
  FIRE_SAFETY: 'fire_safety',
  ENVIRONMENT: 'environment',
  PARKING: 'parking',
  URBAN_PLANNING: 'urban_planning',
} as const;
export type RegulationType = (typeof RegulationType)[keyof typeof RegulationType];

export const CircuitBreakerState = {
  CLOSED: 'closed',
  OPEN: 'open',
  HALF_OPEN: 'half_open',
} as const;
export type CircuitBreakerState = (typeof CircuitBreakerState)[keyof typeof CircuitBreakerState];
