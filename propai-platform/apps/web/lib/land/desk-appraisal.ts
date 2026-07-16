/**
 * 탁상감정(desk appraisal) 공용 계약 — 타입·fetch·포매터·부지분석 요약 어댑터.
 *
 * DeskAppraisalReportClient(예상 시세 추정 보고서 전체 화면)와 부지분석 워크스페이스가
 * 동일한 응답 계약(타입·키 이름)을 공유하도록 이관한다(로직 변경 없음·재구현 금지).
 *
 * ★핵심 계약: 채택 총액 키는 `appraised_total_won` 이다. 응답에는 `final_value_won`
 *   키가 존재하지 않으므로(desk_appraisal_service 반환 dict 참조) 그 키를 읽으면 항상 null 이
 *   된다. 어댑터/소비처는 반드시 `appraised_total_won` 을 사용한다.
 */

/**
 * API 오리진(버전 prefix 제외) — DeskAppraisalReportClient 에서 이관(동작 불변).
 * 프로덕션 호스트에서는 절대 오리진, 그 외(로컬·프리뷰)는 Next 프록시 경로를 반환한다.
 */
export function apiBase(): string {
  if (typeof window !== "undefined") {
    const h = window.location.hostname;
    if (h === "4t8t.net" || h === "www.4t8t.net" || h.endsWith(".pages.dev") || h === "propai.kr")
      return "https://api.4t8t.net/api/v1";
  }
  return "/api/proxy";
}

// 억/원 포매터 — DeskAppraisalReportClient 에서 이관(로직 변경 없음).
export const eok = (v: number | null | undefined) =>
  v == null ? "—" : `${(v / 1e8).toLocaleString(undefined, { maximumFractionDigits: 2 })}억`;
export const won = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v).toLocaleString()}원`);

/** 산정방법 1건 — 방법명·추정 단가(원/㎡)·근거. */
export type DeskAppraisalMethod = { method: string; unit_price: number; rationale: string };

type Stat = { source?: string; pct?: number; basis?: string; rate?: number; factor?: number } | null;

/**
 * 탁상감정 응답 계약(DeskAppraisalReportClient 의 Result 를 이관 — 변경 없음).
 * 정식 감정평가가 아닌 참고용 추정. `appraised_total_won` 이 채택 총액(원)이다.
 */
export type DeskAppraisalResult = {
  ok: boolean; message?: string;
  appraised_price_per_sqm: number; appraised_total_won: number | null; area_sqm: number | null;
  official_price_per_sqm?: number; pnu?: string | null;
  subject?: {
    land_category?: string | null; zone_type?: string | null; zone_type_2?: string | null;
    land_use_situation?: string | null; terrain_height?: string | null; terrain_form?: string | null;
    official_price_year?: number | null;
  };
  confidence: number; range_per_sqm: { low: number; high: number };
  cross_check?: { firms: number[]; mean: number; cv_pct: number; min: number; max: number; note: string };
  irregularity?: number | null; methods: DeskAppraisalMethod[]; weight_note: string;
  road_side?: string | null; time_adjust?: number; time_adjust_basis?: string; source?: string; base_year?: number;
  building?: { building_value_won: number; rationale: string } | null; complex_total_won?: number | null;
  income?: { income_value_won: number; rationale: string } | null; income_total_won?: number | null;
  complex_note?: string | null;
  market_stats?: {
    region?: string;
    rone_available?: boolean; cap_rate?: Stat; jeonse_conversion_rate?: Stat; housing_time_adjust?: Stat;
    land_price_trend?: { monthly?: { period: string; rate: number }[]; yearly?: { year: string; rate: number }[] } | null;
  };
  disclaimer: string;
};

/**
 * 단일 주소 탁상감정 호출 — DeskAppraisalReportClient.fetchAppraisal 의 네트워크 코어를 이관.
 * payload(주소·수동입력·주소전용 여부 등)는 호출측이 구성한다(React 상태 의존부는 컴포넌트에 잔류).
 * 로직 불변: 401/오류 → throw, ok=false → message throw.
 */
export async function fetchDeskAppraisal(payload: Record<string, unknown>): Promise<DeskAppraisalResult> {
  const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
  const r = await fetch(`${apiBase()}/land-price/desk-appraisal`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(`서버 오류(${r.status})`);
  const d = await r.json();
  if (!d?.ok) throw new Error(d?.message || "추정 실패");
  return d as DeskAppraisalResult;
}

/** 탁상감정 → 부지분석 요약(어댑터 출력 계약). 없으면 null(무목업 — 0 강제 금지). */
export type DeskSiteSummary = {
  /** 추정 토지가치(총액, 원) = appraised_total_won. ★final_value_won 아님(키 부재). */
  estimatedTotalWon: number | null;
  /** ㎡당 채택 단가(원/㎡). */
  pricePerSqm: number | null;
  /** 신뢰도(0~1). */
  confidence: number | null;
  /** 방법별 단가·근거. */
  methods: DeskAppraisalMethod[];
  /** 복수 시나리오 교차검증(평균·CV%). */
  crossCheck: NonNullable<DeskAppraisalResult["cross_check"]> | null;
  /** 채택 단가 신뢰구간(원/㎡). */
  rangePerSqm: DeskAppraisalResult["range_per_sqm"] | null;
  /** 면책 문구(정직성 표기용). */
  disclaimer: string | null;
  /** 데이터 출처. */
  source: string | null;
};

/**
 * 탁상감정 결과 → 부지분석 요약 매핑(SSOT 단일 계약).
 * ★null 가드 철저 — 없는 값은 null 로 두고 0 을 강제하지 않는다(무목업).
 * ★estimatedTotalWon 은 반드시 `appraised_total_won`(응답에 final_value_won 키 없음).
 */
export function deskToSiteSummary(r: DeskAppraisalResult): DeskSiteSummary {
  return {
    estimatedTotalWon: r.appraised_total_won ?? null,
    pricePerSqm: r.appraised_price_per_sqm ?? null,
    confidence: r.confidence ?? null,
    methods: Array.isArray(r.methods) ? r.methods : [],
    crossCheck: r.cross_check ?? null,
    rangePerSqm: r.range_per_sqm ?? null,
    disclaimer: r.disclaimer ?? null,
    source: r.source ?? null,
  };
}
