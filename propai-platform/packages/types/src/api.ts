// PropAI v30.0 - API 응답/요청 타입 (packages/schemas/models.py 미러)

import type {
  ProjectStatus,
  EscrowStatus,
  UserRole,
  DesignType,
  TaskStatus,
  DefectSeverity,
} from './enums';

// ── 공통 응답 래퍼 ──

export interface ApiResponse<T = unknown> {
  success: boolean;
  message?: string | null;
  data?: T | null;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

export interface ErrorResponse {
  success: false;
  error_code: string;
  message: string;
  details?: Record<string, unknown> | null;
}

// ── 인증 ──

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
  expires_in: number;
}

export interface UserResponse {
  id: string;
  tenant_id: string;
  email: string;
  name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

// ── 프로젝트 ──

export interface ProjectResponse {
  id: string;
  tenant_id: string;
  name: string;
  status: ProjectStatus;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  total_area_sqm?: number | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreateRequest {
  name: string;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  total_area_sqm?: number | null;
}

export interface ProjectUpdateRequest {
  name?: string | null;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  total_area_sqm?: number | null;
  description?: string | null;
}

// ── 부지 분석 ──

export interface SiteAnalysisResponse {
  id: string;
  project_id: string;
  pnu: string;
  land_use_zone?: string | null;
  building_coverage_ratio?: number | null;
  floor_area_ratio?: number | null;
  land_area_sqm?: number | null;
  official_land_price?: number | null;
  created_at: string;
}

// ── AVM 감정 평가 ──

export interface AVMValuationResponse {
  id: string;
  project_id: string;
  estimated_value: number;
  confidence_score: number;
  model_version: string;
  comparable_properties?: ComparableProperty[];
  created_at: string;
}

export interface ComparableProperty {
  address: string;
  price: number;
  area_sqm: number;
  distance_km: number;
  similarity_score: number;
}

// ── 수익성 분석 ──

export interface FeasibilityResponse {
  id: string;
  project_id: string;
  total_project_cost: number;
  total_revenue: number;
  net_profit: number;
  irr?: number | null;
  npv?: number | null;
  payback_period_months?: number | null;
  created_at: string;
}

// ── 설계 ──

export interface DesignResponse {
  id: string;
  project_id: string;
  design_type: DesignType;
  file_url?: string | null;
  thumbnail_url?: string | null;
  metadata?: Record<string, unknown>;
  created_at: string;
}

// ── 인허가 ──

export interface PermitResponse {
  id: string;
  project_id: string;
  permit_type: string;
  status: string;
  submitted_at?: string | null;
  approved_at?: string | null;
  tracking_number?: string | null;
}

// ── 에스크로 ──

export interface EscrowTransactionResponse {
  id: string;
  project_id: string;
  contract_address: string;
  tx_hash?: string | null;
  status: EscrowStatus;
  amount: string;
  buyer_address: string;
  seller_address: string;
  created_at: string;
}

// ── 드론 ──

export interface DroneInspectionResponse {
  id: string;
  project_id: string;
  flight_date: string;
  total_images: number;
  defects_found: number;
  status: TaskStatus;
  created_at: string;
}

export interface DefectResponse {
  id: string;
  inspection_id: string;
  severity: DefectSeverity;
  description: string;
  location_x: number;
  location_y: number;
  image_url: string;
  confidence: number;
}

// ── 비동기 태스크 ──

export interface TaskResponse {
  task_id: string;
  status: TaskStatus;
  result?: unknown;
  error?: string | null;
  created_at: string;
  completed_at?: string | null;
}
