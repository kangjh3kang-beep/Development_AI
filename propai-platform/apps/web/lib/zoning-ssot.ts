// 토지/법규 심층 결과(rich) → SiteAnalysis SSOT 매핑 공용 유틸.
//
// 배경: `/zoning/analyze` 응답은 이미 풍부한 산출물(실효용적률 계층·종상향 잠재·특이부지
// 게이트)을 담지만, 프론트 기록 경로가 기본 4~5필드만 store에 저장해 하류(추천·설계·수지)가
// 같은 API를 재호출했다. 이 매퍼는 응답에서 **확보된 rich 필드만** 뽑아 SiteAnalysisData
// 부분 패치로 정규화해, 한 번 분석한 결과를 SSOT(useProjectContextStore.siteAnalysis)에
// 보존하도록 한다.
//
// 무목업 원칙: 값이 없으면(undefined/null) 0으로 지어내지 않는다 — 해당 키를 생략하거나 null.
// 백엔드 키 정합(읽어서 확인한 실제 키):
//   - effective_far(dict): national_far_pct / national_bcr_pct / effective_far_pct /
//                          effective_bcr_pct / far_basis  (far_tier_service.calc_effective_far)
//   - upzoning(dict): potential_far_range(dict: {min_pct,max_pct,note} 또는 null) / scenarios[]
//                     (각 scenario.feasibility = '상'|'중'|'하')  (upzoning_potential.analyze)
//     (top-level potential_far_range 도 동봉됨 — 폴백으로 사용)
//   - special_parcel(dict): is_special / developability / resolvable / factors[]
//                           (각 factor.category) / honest_disclosure  (special_parcel.detect_special_parcel)

import type { SiteAnalysisData } from "@/store/useProjectContextStore";

// 응답 타입은 느슨하게(필요한 키만 옵셔널 정의). 모든 키가 옵셔널 — 구버전/부분 응답 무손상.
type FarRange = { min_pct?: number | null; max_pct?: number | null } | null | undefined;

type EffectiveFar = {
  national_far_pct?: number | null;
  national_bcr_pct?: number | null;
  effective_far_pct?: number | null;
  effective_bcr_pct?: number | null;
  far_basis?: string | null;
} | null | undefined;

type Scenario = { feasibility?: string | null } | null | undefined;

type Upzoning = {
  potential_far_range?: FarRange;
  scenarios?: Scenario[] | null;
} | null | undefined;

type SpecialFactor =
  | { category?: string | null; name?: string | null; label?: string | null }
  | string
  | null
  | undefined;

type SpecialParcel = {
  is_special?: boolean | null;
  developability?: string | null;
  resolvable?: string | null;
  factors?: SpecialFactor[] | null;
  honest_disclosure?: string | null;
} | null | undefined;

export type ZoningRichResponse = {
  effective_far?: EffectiveFar;
  upzoning?: Upzoning;
  // top-level 폴백(analyze 핸들러가 upzoning과 함께 동봉).
  potential_far_range?: FarRange;
  upzoning_scenarios?: Scenario[] | null;
  special_parcel?: SpecialParcel;
} | null | undefined;

// 가능성 등급 순위 — 작을수록 상위('상' > '중' > '하').
const FEASIBILITY_RANK: Record<string, number> = { "상": 0, "중": 1, "하": 2 };

// 유한 숫자만 통과(NaN/Infinity/비숫자는 거름). 미확보 시 undefined.
function num(v: unknown): number | undefined {
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}

// factors[]를 라벨 문자열 배열로 정규화(객체면 category > label > name 추출, 문자열이면 그대로).
function normalizeFactors(factors: SpecialFactor[] | null | undefined): string[] {
  if (!Array.isArray(factors)) return [];
  const out: string[] = [];
  for (const f of factors) {
    if (typeof f === "string") {
      const t = f.trim();
      if (t) out.push(t);
    } else if (f && typeof f === "object") {
      const label = (f.category ?? f.label ?? f.name ?? "").toString().trim();
      if (label) out.push(label);
    }
  }
  return out;
}

// scenarios 중 가능성 최상('상'>'중'>'하') 등급. 없으면 undefined.
function topFeasibility(scenarios: Scenario[] | null | undefined): string | undefined {
  if (!Array.isArray(scenarios)) return undefined;
  let best: string | undefined;
  let bestRank = Number.POSITIVE_INFINITY;
  for (const s of scenarios) {
    const raw = s?.feasibility;
    if (typeof raw !== "string") continue;
    const grade = raw.trim(); // 서버 표기 흔들림(공백/개행) 방어 정규화
    const rank = FEASIBILITY_RANK[grade];
    if (rank === undefined) continue;
    if (rank < bestRank) {
      bestRank = rank;
      best = grade;
    }
  }
  return best;
}

/**
 * /zoning/analyze 응답(또는 동형 객체)에서 rich 필드를 추출해 SiteAnalysisData 부분 패치로 변환.
 *
 * ★주소 변경 시 직전 부지 값 잔류(stale) 방지: rich 필드는 "현재 주소"의 속성이므로, 응답이
 *   있으면 각 필드를 값(확보 시) 또는 명시적 null(미확보 시)로 기록한다(키 생략 금지). null은
 *   "이 주소엔 해당 데이터 없음"으로 0/가짜 생성과 다르다(무목업 유지). 키를 생략하면
 *   updateSiteAnalysis의 shallow-merge가 직전 주소 값(예: 특이부지 게이트)을 그대로 보존해
 *   하류 할루시네이션 가드가 오발동하므로, 조건부 필드(특이부지·종상향)도 반드시 null로 덮는다.
 *   resp 자체가 없으면(null) 빈 패치 반환(쓰기 경로 없음 — 기존 값 불변).
 */
export function mapZoningRich(resp: unknown): Partial<SiteAnalysisData> {
  const patch: Partial<SiteAnalysisData> = {};
  if (resp == null || typeof resp !== "object") return patch;
  // 경계 매퍼 — 외부 API 응답을 unknown으로 받아 런타임 검증 후 좁힌다(호출부 타입 무관·무오염).
  const r = resp as NonNullable<ZoningRichResponse>;

  // 실효용적률 계층(effective_far dict) — 값 또는 명시적 null(stale 방지).
  const ef =
    r.effective_far != null && typeof r.effective_far === "object"
      ? r.effective_far
      : null;
  patch.nationalFarPct = ef ? (num(ef.national_far_pct) ?? null) : null;
  patch.nationalBcrPct = ef ? (num(ef.national_bcr_pct) ?? null) : null;
  patch.effectiveFarPct = ef ? (num(ef.effective_far_pct) ?? null) : null;
  patch.effectiveBcrPct = ef ? (num(ef.effective_bcr_pct) ?? null) : null;
  patch.farBasis =
    ef && typeof ef.far_basis === "string" && ef.far_basis.trim()
      ? ef.far_basis
      : null;

  // 종상향 잠재 상한(potential_far_range dict {min_pct,max_pct}) — upzoning 내부 우선, top-level 폴백.
  const range = r.upzoning?.potential_far_range ?? r.potential_far_range;
  patch.upzoningPotentialFarHigh =
    range != null && typeof range === "object" ? (num(range.max_pct) ?? null) : null;

  // 최상 가능성 등급 — upzoning.scenarios 우선, 동봉된 upzoning_scenarios 폴백. 없으면 null.
  patch.upzoningFeasibilityTop =
    topFeasibility(r.upzoning?.scenarios ?? r.upzoning_scenarios) ?? null;

  // 특이부지 게이트 — is_special truthy일 때만 객체, 아니면 명시적 null(직전 부지 특이정보 초기화).
  const sp = r.special_parcel;
  if (sp != null && typeof sp === "object" && sp.is_special) {
    patch.specialParcel = {
      isSpecial: true,
      developability:
        typeof sp.developability === "string" ? sp.developability : null,
      resolvable: typeof sp.resolvable === "string" ? sp.resolvable : null,
      factors: normalizeFactors(sp.factors),
      honest:
        typeof sp.honest_disclosure === "string" ? sp.honest_disclosure : null,
    };
  } else {
    patch.specialParcel = null;
  }

  return patch;
}

// 개발가능성 영문 게이트 → 한국어 라벨 공용 맵.
// AutoZoningBadge, LandIntelligencePanel, SiteInitiator 등 여러 곳에서 공유.
export const DEVELOPABILITY_LABEL: Record<string, string> = {
  POSSIBLE: "개발 가능",
  CAUTION: "사전확인 필요",
  CONDITIONAL: "조건부 가능",
  PRECONDITION: "선행절차 필요",
  RESTRICTED: "제한적",
  BLOCKED: "개발 불가",
};
