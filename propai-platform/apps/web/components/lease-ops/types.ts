/* ------------------------------------------------------------------ */
/*  Lease-Ops 운영서비스 1탄 — 임대·임차인 관리 타입                  */
/*  백엔드 정합: routers/lease_ops.py (prefix /api/v1/lease-ops)        */
/* ------------------------------------------------------------------ */

/** 계약 상태 화이트리스트 (백엔드 VALID_STATUSES와 정합) */
export const LEASE_STATUSES = [
  "active",
  "occupied",
  "leased",
  "expired",
  "vacant",
  "pending",
] as const;

export type LeaseStatus = (typeof LEASE_STATUSES)[number];

/** GET /summary 응답 */
export type LeaseSummaryResponse = {
  ok: boolean;
  total_units: number;
  leased: number;
  vacant: number;
  vacancy_rate_pct: number;
  monthly_rent_total: number;
  annual_income_est: number;
  by_status: Record<string, number>;
  message?: string;
};

/** GET /tenants 항목 */
export type Tenant = {
  id: string;
  name: string;
  contact: string | null;
  business_type: string | null;
};

export type TenantsResponse = {
  ok: boolean;
  tenants: Tenant[];
  message?: string;
};

/** POST /tenants 입력 */
export type TenantCreateInput = {
  name: string;
  contact?: string;
  business_type?: string;
  notes?: string;
};

/** GET /contracts 항목 */
export type LeaseContract = {
  id: string;
  unit_label: string;
  lessee_name: string | null;
  deposit: number | null;
  monthly_rent: number | null;
  start_date: string | null;
  end_date: string | null;
  status: string;
  area_sqm: number | null;
};

export type ContractsResponse = {
  ok: boolean;
  contracts: LeaseContract[];
  message?: string;
};

/** POST /contracts 입력 (lessee = tenant id) */
export type ContractCreateInput = {
  unit_label: string;
  lessee: string;
  deposit?: number;
  monthly_rent?: number;
  start_date?: string;
  end_date?: string;
  area_sqm?: number;
  status?: string;
  notes?: string;
};

/** POST 공통 응답 */
export type MutationResponse = {
  ok: boolean;
  id?: string;
  status?: string;
  message?: string;
};

/** (결합) POST /leases/analyze 응답 (관용 파싱) */
export type LeaseAnalyzeResponse = {
  ok?: boolean;
  summary?: string;
  analysis?: string;
  result?: string;
  message?: string;
  [key: string]: unknown;
};

/** (결합) POST /tenant/satisfaction/nps 응답 (관용 파싱) */
export type NpsResponse = {
  ok?: boolean;
  nps?: number;
  score?: number;
  promoters?: number;
  passives?: number;
  detractors?: number;
  message?: string;
  [key: string]: unknown;
};
