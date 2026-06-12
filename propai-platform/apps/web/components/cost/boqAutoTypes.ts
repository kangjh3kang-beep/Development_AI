/**
 * BOQ 자동작성(B5) — /api/v1/boq-auto 프론트 계약 타입.
 *
 * 데이터 원천: apps/api/app/services/cost/data/boq_master/{architecture,mechanical,
 * electrical,landscape,civil}.json + _meta.json — 실적 공내역서 1건(의정부동 424
 * 주상복합, GFA 238,504㎡) 기반 표준항목 마스터(3,997 고유항목 · 414 섹션).
 *
 * 정직성 원칙: 마스터는 n=1 참고치 — 모든 산출물은 "전문 적산(QS) 검토 필수"
 * 배지와 함께 표기한다. 단가 없는 공내역(빈 단가·물량 채움)이 실무 표준이며,
 * 이 화면도 수량·근거까지만 확정 표기하고 금액은 apply-cost 후보치로만 다룬다.
 *
 * additive 계약: 백엔드가 키를 추가해도 프론트가 깨지지 않도록 옵셔널 위주로
 * 정의하고, 소비부(BoqAutoWorkspace)는 누락 키를 방어적으로 처리한다.
 */

/* ── 공종(discipline) 상수 — 마스터 파일 키 기준 ── */

export type BoqDisciplineKey =
  | "architecture"
  | "mechanical"
  | "electrical"
  | "landscape"
  | "civil";

/** 탭 순서·라벨 SSOT — _meta.json의 한글 공종명과 1:1. */
export const BOQ_DISCIPLINES: ReadonlyArray<{
  key: BoqDisciplineKey;
  label: string;
  file: string;
}> = [
  { key: "architecture", label: "건축", file: "architecture.json" },
  { key: "mechanical", label: "기계소방", file: "mechanical.json" },
  { key: "electrical", label: "전기통신소방", file: "electrical.json" },
  { key: "landscape", label: "조경", file: "landscape.json" },
  { key: "civil", label: "토목", file: "civil.json" },
] as const;

/* ── API 경로 상수(v1 — apiClient가 /api/v1 prefix를 붙인다) ── */

export const BOQ_AUTO_API = {
  /** GET — 마스터 요약(공종별 섹션·항목 수 + 표본 프로젝트 출처). */
  masterSummary: "/boq-auto/master/summary",
  /** POST — 파라메트릭 드래프트 생성(수량 스케일링, 단가 없음). */
  draft: "/boq-auto/draft",
  /** POST — 드래프트 전체 엑셀(xlsx) blob 내보내기. */
  export: "/boq-auto/export",
  /** POST — 수지 반영 "후보" 총액 산출(단가 SSOT 결합) — store 직접 반영 없음. */
  applyCost: "/boq-auto/apply-cost",
} as const;

/* ── 마스터 요약(GET master/summary) ── */

/** 표본 프로젝트 메타(_meta.json project 블록 미러). */
export interface BoqMasterProject {
  name?: string | null;
  gfa_sqm?: number | null;
  gfa_basis?: string | null;
  sample_count?: number | null;
  provenance?: string | null;
}

/** 공종별 마스터 집계(_meta.json disciplines 값 미러). */
export interface BoqMasterDisciplineSummary {
  /** 영문 파일 키(서버가 주면 우선 매칭). */
  key?: string | null;
  /** 한글 공종명(예: "건축") — 키로도 올 수 있어 둘 다 허용. */
  discipline?: string | null;
  file?: string | null;
  sections?: number | null;
  unique_items?: number | null;
  rows_aggregated?: number | null;
}

export interface BoqMasterSummaryResponse {
  ok?: boolean;
  project?: BoqMasterProject | null;
  /** 한글 공종명 키 record(_meta.json 원형) 또는 배열 — 소비부가 정규화. */
  disciplines?:
    | Record<string, BoqMasterDisciplineSummary>
    | BoqMasterDisciplineSummary[]
    | null;
  total_items?: number | null;
  total_sections?: number | null;
  note?: string | null;
}

/* ── 드래프트 생성(POST draft) ── */

export interface BoqAutoDraftRequest {
  /** 대상 연면적(㎡) — 필수 스케일 드라이버. */
  gfa_sqm: number;
  /** 세대수 — 세대 드라이버 항목용(없으면 GFA 비례 폴백은 서버 정책). */
  unit_count?: number | null;
  /** 공종 필터(미지정 = 5공종 전체). */
  disciplines?: BoqDisciplineKey[];
  /** 추적용 프로젝트 id(서버 영속화 시 사용, 옵셔널). */
  project_id?: string | null;
}

/** 드래프트 항목 — 마스터 item 미러 + 스케일 수량·근거. 단가/금액 없음(공내역). */
export interface BoqAutoDraftItem {
  id: string;
  section_code: string;
  section_name: string;
  name: string;
  spec?: string | null;
  unit?: string | null;
  /** 스케일된 추정 수량(대상 GFA 기준). */
  qty?: number | null;
  /** 마스터 표본 수량(GFA 238,504㎡ 기준 원본). */
  qty_sample?: number | null;
  /** 스케일 드라이버(예: "gfa_ratio" | "unit_count" | "fixed"). */
  driver?: string | null;
  /** 산출 근거 한 줄(예: "표본수량 × (50,000 / 238,504)"). */
  basis?: string | null;
  /** 신뢰도(high|medium|low) — low는 전문검토 강조 표기. */
  confidence?: string | null;
  /** 전기 마스터만 존재하는 참고 자재단가(원) — 표기만, 합산 금지. */
  ref_mat_price?: number | null;
}

export interface BoqAutoDraftDiscipline {
  /** 영문 키(서버 제공 시) — 탭 매칭 1순위. */
  key?: string | null;
  /** 한글 공종명 — 탭 매칭 2순위. */
  discipline?: string | null;
  items?: BoqAutoDraftItem[] | null;
  /** 전체 항목 수(items가 서버측에서 잘렸을 때의 원본 수). */
  total_item_count?: number | null;
  truncated?: boolean | null;
}

/** 드래프트 상단 고정 배지(정직성) — 서버 문구를 그대로 표기. */
export interface BoqAutoDraftBadges {
  note?: string | null;
  provenance?: string | null;
  confidence?: string | null;
  [k: string]: unknown;
}

export interface BoqAutoDraftResponse {
  ok?: boolean;
  draft_id?: string | null;
  /** 서버가 적용한 파라미터 에코(스케일비 포함 가능). */
  params?: {
    gfa_sqm?: number | null;
    unit_count?: number | null;
    scale_ratio?: number | null;
    [k: string]: unknown;
  } | null;
  disciplines?: BoqAutoDraftDiscipline[] | null;
  warnings?: string[] | null;
  badges?: BoqAutoDraftBadges | null;
}

/* ── 엑셀 내보내기(POST export — blob) ── */

/** 드래프트와 동일 파라미터 + draft_id(있으면 서버 재계산 생략 가능). */
export interface BoqAutoExportRequest extends BoqAutoDraftRequest {
  draft_id?: string | null;
}

/* ── 수지 반영 후보(POST apply-cost) ── */

export interface BoqApplyCostRequest extends BoqAutoDraftRequest {
  draft_id?: string | null;
}

/** 후보 총액 — costData 자동 반영 없음(기존 수지 흐름에서 사용자가 적용). */
export interface BoqApplyCostResponse {
  ok?: boolean;
  /** 단가 결합 총액 후보(원). 단가 미결합이면 null — 가짜값 금지. */
  total_won?: number | null;
  direct_won?: number | null;
  indirect_won?: number | null;
  per_sqm_won?: number | null;
  /** 단가 출처(예: "표준품셈/물가 SSOT", basis_year 포함 문구). */
  source?: string | null;
  /** 단가가 매칭된/안 된 항목 수 — 커버리지 정직 표기. */
  priced_item_count?: number | null;
  unpriced_item_count?: number | null;
  note?: string | null;
  badges?: { note?: string | null; [k: string]: unknown } | null;
}
