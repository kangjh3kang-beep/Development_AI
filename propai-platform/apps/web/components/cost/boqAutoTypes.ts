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
  /** POST — 드래프트 전체 엑셀(xlsx) blob 내보내기. (백엔드 라우트: /draft/export) */
  export: "/boq-auto/draft/export",
  /** POST — 수지 반영 "후보" 총액 산출. (백엔드 라우트: /draft/apply-cost) */
  applyCost: "/boq-auto/draft/apply-cost",
  /** POST — N3 단가결합 드래프트(금액까지 채움 — DB/fallback·도면참고단가). */
  pricedDraft: "/boq-auto/draft/priced",
  /** POST — N3 단가결합 엑셀(금액 모드: 단가/금액칸·공종 소계·총계 시트). */
  pricedExport: "/boq-auto/draft/priced/export",
  /** POST — N2 프로젝트 BIM 실측 물량 우선 병합 드래프트. */
  fromProject: "/boq-auto/draft/from-project",
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

/* ── 드래프트 생성 요청(POST /draft·/draft/priced·/draft/from-project·/draft/apply-cost) ── */

/**
 * 실제 백엔드 요청 계약 — params 를 **반드시 중첩**한다(평탄형 {gfa_sqm}은 422 거부).
 * project_id 는 apply-cost·from-project 에서 상단 레벨 필수.
 */
export interface BoqDraftRequestBody {
  params: {
    /** 대상 연면적(㎡) — 필수 스케일 드라이버. */
    gfa_sqm: number;
    /** 세대수 — 세대 드라이버 항목용(없으면 GFA 비례 폴백은 서버 정책). */
    households?: number | null;
  };
  /** 공종 필터(미지정 = 5공종 전체). */
  disciplines?: BoqDisciplineKey[];
  /** apply-cost · from-project 에서 필수(BIM 물량 조회 대상/응답 echo). */
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

  /* ── N2 BIM 병합(additive·옵셔널) ── */
  /** 수량 출처: "user" | "bim" | "parametric"(없으면 추정 취급). */
  qty_source?: "user" | "bim" | "parametric" | string | null;
  /** BIM 실측치로 교체된 경우의 원 파라메트릭 수량(정직 표기). */
  qty_parametric?: number | null;
  /** 매칭된 BIM work_code(예: "A04"). */
  bim_work_code?: string | null;

  /* ── N3 단가결합(additive·옵셔널) ── */
  /** 단가 출처: "db" | "fallback" | "도면참고단가" | null(미결합·가짜값 금지). */
  price_source?: string | null;
  /** 매칭된 단가 SSOT 키(예: "concrete"). */
  price_key?: string | null;
  mat_unit?: number | null;
  labor_unit?: number | null;
  exp_unit?: number | null;
  /** 금액(원) = qty × (채워진 단가 합). 미결합이면 null. */
  amount?: number | null;
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

/** 실제 백엔드 응답의 공종 블록(disciplines record 값). */
export interface BoqAutoDraftDisciplineBlock {
  items?: BoqAutoDraftItem[] | null;
  item_count?: number | null;
  sections?: Array<{ section_code?: string; section_name?: string }> | null;
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
  /** 공종 블록 — 실제 백엔드는 record(한글 공종명 키)로 반환. 배열형도 방어적 허용. */
  disciplines?:
    | Record<string, BoqAutoDraftDisciplineBlock>
    | BoqAutoDraftDiscipline[]
    | null;
  warnings?: string[] | null;
  badges?: BoqAutoDraftBadges | null;
  provenance?: BoqMasterProject | null;
  /** 서버 summary — N2 BIM 병합 / N3 단가결합 통계(옵셔널·additive). */
  summary?: {
    total_items?: number | null;
    warnings?: string[] | null;
    /** N2 BIM 병합 통계(/draft/from-project 응답). */
    bim_merge?: {
      bim_rows_count?: number | null;
      bim_matched_count?: number | null;
      by_source?: Record<string, number> | null;
      note?: string | null;
      [k: string]: unknown;
    } | null;
    /** N3 단가결합 통계(/draft/priced 응답). */
    pricing?: {
      priced_count?: number | null;
      total_items?: number | null;
      coverage_pct?: number | null;
      priced_amount_won?: number | null;
      by_source?: Record<string, number> | null;
      unit_mismatch_count?: number | null;
      note?: string | null;
      [k: string]: unknown;
    } | null;
    [k: string]: unknown;
  } | null;
}

/* ── 수지 반영 후보(POST /draft/apply-cost) ── 요청은 BoqDraftRequestBody(+project_id) 사용 ── */

/** N3 단가결합 직접비 → 12단계 법정요율 경로(apply-cost 가산 블록). */
export interface BoqPricedCostEstimate {
  cost_source?: string | null;          // "boq_priced"
  direct_cost_won?: number | null;      // 결합 항목 직접비 합
  total_construction_cost_won?: number | null;
  coverage_pct?: number | null;
  priced_count?: number | null;
  total_items?: number | null;
  priced_amount_won?: number | null;
  note?: string | null;
}

/**
 * 수지 반영 "후보" 응답 — 실제 백엔드 /draft/apply-cost 형태.
 * costData 자동 반영 없음(persisted=false). 가짜값 금지(미발견은 null).
 */
export interface BoqApplyCostResponse {
  project_id?: string | null;
  boq_draft_summary?: Record<string, unknown> | null;
  /** boq_builder 개산 경로(기본). */
  cost_estimate?: {
    total_construction_cost_won?: number | null;
    source?: string | null;             // "boq_builder 개산"
    summary?: Record<string, unknown> | null;
    assumptions?: Record<string, unknown> | null;
    builder_badges?: Record<string, unknown> | null;
  } | null;
  /** N3 단가결합 직접비 → 법정요율 경로(결합 0건이면 null — 정직). */
  priced_cost_estimate?: BoqPricedCostEstimate | null;
  badges?: string[] | null;
  persisted?: boolean | null;
}
