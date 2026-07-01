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

import type {
  SiteAnalysisData,
  UpzoningScenarioData,
} from "@/store/useProjectContextStore";

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

// 문자열 정규화(공백 제거, 빈값은 null).
function str(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v.trim() : null;
}

// 백엔드 per-scenario 종상향 응답(rich) — 모든 키 옵셔널·unknown(부분/구버전 응답 무손상).
type RawUpzoningScenario = {
  path?: unknown;
  target_zone?: unknown;
  expected_far_pct_low?: unknown;
  expected_far_pct_high?: unknown;
  feasibility?: unknown;
  feasibility_reason?: unknown;
  legal_basis?: unknown;
};

/**
 * 백엔드 종상향 per-scenario 배열을 UpzoningScenarioData[](미래 토지특성 SSOT)로 정규화.
 *
 * - 배열이 아니면 null(쓰기 경로 없음 — stale 방지는 호출부에서 명시 null로 처리).
 * - 의미 있는 필드(경로/목표/가능성/예상용적/근거/사유)가 하나도 없는 잡음 항목은 제외.
 * - 정규화 결과가 비면 null(빈 배열로 SSOT 오염 방지).
 * 무목업: 숫자가 아닌 용적률은 null(가짜 0/문자열 금지). 순수 함수.
 */
export function normalizeUpzoningScenarios(
  raw: unknown,
): UpzoningScenarioData[] | null {
  if (!Array.isArray(raw)) return null;
  const out: UpzoningScenarioData[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const s = item as RawUpzoningScenario;
    const path = str(s.path);
    const targetZone = str(s.target_zone);
    const feasibility = str(s.feasibility);
    const expectedFarLowPct = num(s.expected_far_pct_low) ?? null;
    const expectedFarHighPct = num(s.expected_far_pct_high) ?? null;
    const legalBasis = str(s.legal_basis);
    const rationale = str(s.feasibility_reason);
    if (
      path == null &&
      targetZone == null &&
      feasibility == null &&
      expectedFarLowPct == null &&
      expectedFarHighPct == null &&
      legalBasis == null &&
      rationale == null
    ) {
      continue;
    }
    out.push({
      path,
      targetZone,
      feasibility,
      expectedFarLowPct,
      expectedFarHighPct,
      legalBasis,
      rationale,
    });
  }
  return out.length > 0 ? out : null;
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
 * upzoning(종상향) 3필드만 SSOT 부분 패치로 추출(단일·통합 응답 공용 계약).
 *
 * `/zoning/analyze`(단일)와 `/zoning/integrated-analysis`(다필지 통합)는 모두 동형 키
 * (upzoning / upzoning_scenarios / potential_far_range)로 종상향을 반환한다. 이 헬퍼로
 * 두 경로가 한 곳을 고치면 함께 따라오게 하고(공용화), 다필지에서는 통합 응답의 종상향이
 * 단일 대표필지 종상향을 덮어쓰도록 한다(통합값 우선).
 *
 * 무목업: 종상향 미확보 시 세 필드를 명시적 null로 기록(직전 부지/대표필지 잔류 차단).
 */
export function mapUpzoning(resp: unknown): Partial<SiteAnalysisData> {
  const patch: Partial<SiteAnalysisData> = {};
  if (resp == null || typeof resp !== "object") {
    patch.upzoningPotentialFarHigh = null;
    patch.upzoningFeasibilityTop = null;
    patch.upzoningScenarios = null;
    return patch;
  }
  const r = resp as NonNullable<ZoningRichResponse>;

  // 종상향 잠재 상한(potential_far_range dict {min_pct,max_pct}) — upzoning 내부 우선, top-level 폴백.
  const range = r.upzoning?.potential_far_range ?? r.potential_far_range;
  patch.upzoningPotentialFarHigh =
    range != null && typeof range === "object" ? (num(range.max_pct) ?? null) : null;

  // 최상 가능성 등급 — upzoning.scenarios 우선, 동봉된 upzoning_scenarios 폴백. 없으면 null.
  patch.upzoningFeasibilityTop =
    topFeasibility(r.upzoning?.scenarios ?? r.upzoning_scenarios) ?? null;

  // per-scenario 종상향 상세 — 확보 시 보존, 미확보 시 명시적 null로 덮어 잔류(stale)를 차단.
  patch.upzoningScenarios = normalizeUpzoningScenarios(
    r.upzoning?.scenarios ?? r.upzoning_scenarios,
  );

  return patch;
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
  // 접도 도로폭(m·auto_zoning NED 도로접면 추정) — 시니어 심의 접도 CSP 입력원(미확보 시 null).
  patch.roadWidthM = num((r as { road_width_m?: unknown }).road_width_m) ?? null;

  // 종상향(종상향 잠재 상한·최상 가능성·per-scenario) — 단일/통합 공용 헬퍼로 추출(stale 명시 null 포함).
  Object.assign(patch, mapUpzoning(r));

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

/**
 * 다필지 통합 시 단일 PNU(대표 1필지) 유래 값으로 SSOT를 오염시키지 않도록 가드.
 *
 * 배경(SSOT 붕괴 버그): `/zoning/analyze`는 "대표 1필지"(작은 면적·단일 PNU) 분석이라
 *   mapZoningRich가 추출하는 **모든 단일유래 필드**(실효/법정 한도 effectiveFarPct·effectiveBcrPct·
 *   nationalFarPct·nationalBcrPct·farBasis, 종상향 upzoning*, 접도 roadWidthM, 특이부지
 *   specialParcel)가 대표필지 기준이다. 혼재 다필지(예: 제2종일반주거 + 자연녹지)에서 대표가
 *   자연녹지(100%/20%)면 store가 오염돼, 인벨로프 카드가 사업개요(면적가중 통합 192.4%)와
 *   불일치한다. 다필지에서는 통합 경로(/zoning/integrated-analysis blended_*_eff_pct)가
 *   진실원천이므로, mapZoningRich가 쓰는 단일유래 필드를 **하나도 빠짐없이** 패치에서 제거해
 *   통합값이 살아남게 한다(통합값 우선). 단일필지면 패치를 그대로 둔다(무회귀).
 *   ★불변식: mapZoningRich가 추출 필드를 추가하면 그 필드도 여기 delete에 추가해야 한다
 *   (대표필지 누출 차단 — 가드가 mapZoningRich의 단일유래 출력 전부를 커버).
 *
 * 순수 함수(입력 패치를 변형하지 않고 새 객체 반환). 같은 계약을 여러 컴포넌트가 공유해
 * 한 곳을 고치면 전역이 따라오게 한다(공용화).
 */
export function guardMultiParcelRich(
  patch: Partial<SiteAnalysisData>,
  isMultiParcel: boolean,
): Partial<SiteAnalysisData> {
  if (!isMultiParcel) return patch;
  const out = { ...patch };
  // 단일유래 실효/법정 한도 — 통합 경로가 진실원천(대표필지 오염 차단).
  delete out.effectiveFarPct;
  delete out.effectiveBcrPct;
  delete out.nationalFarPct;
  delete out.nationalBcrPct;
  delete out.farBasis;
  // 단일유래 종상향 — 통합 면적 기준 integrated.upzoning이 진실원천(대표필지 과소판정 차단).
  delete out.upzoningPotentialFarHigh;
  delete out.upzoningFeasibilityTop;
  delete out.upzoningScenarios;
  // 단일유래 접도 도로폭 — 대표 1필지의 도로접면이라 통합부지 접도와 무관(시니어 심의 접도 CSP 오염 차단).
  delete out.roadWidthM;
  // 단일유래 특이부지 게이트 — 대표 1필지 기준이라 혼재 다필지에 잘못 전파되면 하류 게이트 오발동.
  delete out.specialParcel;
  return out;
}

/* ── 실효 용적률/건폐율·용도지역 단일 진실원천 리졸버(읽기 통일 헬퍼) ──
 *
 * 배경(읽기 분기 버그): 다필지 통합값(integratedFarEffPct 등)은 그동안 일부 컴포넌트엔 prop으로만
 *   전파되고(BuildableEnvelopeCard), 나머지 소비처는 store.effectiveFarPct(대표 1필지 유래)를 직접
 *   읽어 사업개요(통합)와 불일치했다. 이 리졸버로 모든 소비처가 "통합값 우선 → 실효 → 법정" 단일
 *   우선순위로 읽게 해(공용화·한 곳을 고치면 전역이 따라옴), effectiveLandAreaSqm(다필지=통합 우선
 *   면적 헬퍼)와 대칭되는 단일 계약을 이룬다.
 *
 * 무목업: 어떤 값도 없으면 undefined/null(0/가짜 생성 금지). 순수 함수.
 */
type ResolvableSite = {
  integratedFarEffPct?: number | null;
  integratedBcrEffPct?: number | null;
  dominantZoneCode?: string | null;
  effectiveFarPct?: number | null;
  effectiveBcrPct?: number | null;
  nationalFarPct?: number | null;
  nationalBcrPct?: number | null;
  zoneCode?: string | null;
} | null | undefined;

// 실효 용적률(%) — 통합(blended) > 단일 실효 > 법정 상한 순. 미확보 시 undefined.
export function resolveFarPct(site: ResolvableSite): number | undefined {
  if (!site) return undefined;
  return (
    num(site.integratedFarEffPct) ??
    num(site.effectiveFarPct) ??
    num(site.nationalFarPct)
  );
}

// 실효 건폐율(%) — resolveFarPct와 동형(통합 > 실효 > 법정). 미확보 시 undefined.
export function resolveBcrPct(site: ResolvableSite): number | undefined {
  if (!site) return undefined;
  return (
    num(site.integratedBcrEffPct) ??
    num(site.effectiveBcrPct) ??
    num(site.nationalBcrPct)
  );
}

// 대표(우세) 용도지역 — 통합 dominant_zone 우선, 없으면 단일 zoneCode. 미확보 시 null.
export function resolveDominantZone(site: ResolvableSite): string | null {
  if (!site) return null;
  return str(site.dominantZoneCode) ?? str(site.zoneCode);
}

// 개발가능성 영문 게이트 → 한국어 라벨 공용 맵.
// AutoZoningBadge, LandIntelligencePanel, SiteInitiator 등 여러 곳에서 공유.
export const DEVELOPABILITY_LABEL: Record<string, string> = {
  POSSIBLE: "개발 가능",
  CAUTION: "사전확인 필요",
  CONDITIONAL: "조건부 가능",
  // 임야/산지 — 공식 산림데이터 미확보로 확정 판단 불가(참고용 예비안만). 원 enum 노출 금지.
  NEEDS_OFFICIAL_SURVEY: "공식 산림조사 필요(참고안 — 확정 아님)",
  PRECONDITION: "선행절차 필요",
  RESTRICTED: "제한적",
  BLOCKED: "개발 불가",
};
