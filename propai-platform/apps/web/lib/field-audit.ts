/**
 * 자가검증(field_audit) 표면화 SSOT — 백엔드 규칙 결과를 사용자 화면 언어로 옮긴다.
 *
 * ## 이게 뭘 하는 건가 (쉬운 설명)
 *
 * 플랫폼은 분석을 끝낸 뒤 "이 숫자가 규칙에 맞나"를 스스로 점검한다(백엔드 field_audit).
 * 그 점검 결과가 지금까지는 응답 안에만 있고 화면에 하나도 안 나왔다. 여기서 그 결과를
 * 사용자가 읽을 수 있는 형태로 바꾼다.
 *
 * ## 왜 이 파일이 SSOT인가 — 문구를 백엔드에서 가져오지 않는 이유
 *
 * 백엔드 규칙의 `note`는 개발자 언어다("freshness.is_fresh=false", "SSOT 대조 위반",
 * "mark_updated 상류 배선은 별도 티켓"). 그대로 화면에 옮기면 (1)비전문가가 못 읽고
 * (2)문구 하나 고치는 데 파이썬 PR + 배포가 필요하며 (3)나중에 페르소나별로 다르게 말해야
 * 할 때 분기할 자리가 없다. 그래서 **사용자 카피는 여기(프론트)가 정본**이고, 백엔드 note는
 * 참고용으로만 둔다. 미등재 code는 이름을 지어내지 않고 note를 '원문 그대로'라고 밝혀서 보여준다.
 *
 * ## 절대 하지 말아야 할 표기 (라이브 근거로 확정된 것들)
 *
 * - **"8규칙 중 8개 실행"** — 백엔드는 규칙이 입력을 못 찾아 아무 일도 안 해도 실행으로 센다
 *   (runner.py: `r.fn()` 호출 후 무조건 `executed += 1`). 데이터 수집이 실패할수록 지적이
 *   0건에 수렴하므로, 이 숫자를 그대로 보여주면 **가장 부실한 분석이 가장 깨끗해 보인다.**
 *   그래서 여기서는 규칙이 보는 입력이 실제로 있는지를 프론트가 직접 확인해 나눈다.
 * - **"검증됨"·"차단"** — 이 점검은 관측 전용이라 실제로 아무것도 막지 않는다.
 * - **"N% 검증"·커버리지 비율** — 백엔드 `coverage`는 항상 빈 값이다(채우는 통로가 아직 없음).
 *   비율을 만들어내면 날조다.
 */

/* ── 백엔드 계약 미러 (apps/api/.../field_audit/contracts.py) ── */

export type AuditSeverity = "P0" | "P1" | "P2";
export type AuditTier = "A" | "B" | "C";

export interface AuditFinding {
  code: string;
  severity: AuditSeverity;
  panel: string;
  field: string;
  expected?: unknown;
  observed?: unknown;
  rule_id: string;
  tier: AuditTier;
  note?: string | null;
}

export interface AuditReport {
  is_valid?: boolean;
  findings?: AuditFinding[];
  metadata?: Record<string, unknown>;
  coverage?: Record<string, unknown>;
}

/* ── 보고서 섹션 식별자 — 지적을 어느 섹션 안에 붙일지 ── */

export type SectionId =
  | "effective-far"
  | "supply"
  | "land-price"
  | "transactions"
  | "sale-price"
  | "location"
  | "dev-plans"
  | "special-parcel"
  | "evidence";

/**
 * finding code → 섹션. **panel 문자열을 키로 쓰지 않는다.**
 *
 * 백엔드 `panel`은 자유 문자열이고(계약에 enum 없음) 화면 섹션과 어긋난다 — `"개발행위"`는
 * 대응 섹션이 없고, `"risk"`만 영문이며, `"법규/공급"`은 두 섹션에 걸친다. 반면 `code`는
 * 계약이 "안정 식별자"로 선언한 값이라 매핑 키로 안전하다.
 */
export const SECTION_BY_CODE: Record<string, SectionId> = {
  G1_PROTECTION_ZONE_RISK_FLOOR: "dev-plans",
  G2_SCHOOL_POI_DEDUP: "location",
  G3_ZONE_COVERAGE_GAP: "effective-far",
  TERRAIN_SLOPE_COLLECTION_GAP: "special-parcel",
  MARKET_PRICE_METHODOLOGY: "land-price",
  SALE_PRICE_POINT_ESTIMATE: "sale-price",
  PROV_UNKNOWN_SOURCE: "evidence",
  PROV_STALE_DATA: "evidence",
};

/**
 * **항상 뜨는 방법론 고지** — 조건이 아니라 산출 방식 자체를 알리는 것이라 사실상 모든
 * 보고서에 나온다(토지 시세는 언제나 공시지가×보정계수, 분양가는 언제나 단일 점추정).
 *
 * 이걸 "확인 필요 N건" 카운터에 넣으면 매 보고서가 항상 N≥2가 되어, 세 번째 보고서부터는
 * 아무도 안 읽는다. 그러면 진짜 이상(G1·G2·G3 등)이 떴을 때 같이 묻힌다. 그래서 카운터에서
 * 빼고 해당 숫자 옆 회색 각주로만 렌더한다.
 */
export const ALWAYS_ON_CODES: ReadonlySet<string> = new Set([
  "MARKET_PRICE_METHODOLOGY",
  "SALE_PRICE_POINT_ESTIMATE",
]);

/**
 * 규칙이 판정에 쓰는 **입력 경로**(분석 응답 기준 점표기). 프론트는 이 경로가 실제로 있는지만
 * 보고 "적용됨 / 미판정"을 나눈다.
 *
 * ★여기서 규칙 로직을 재구현하지 않는다. 입력이 있다고 해서 그 값이 옳다는 뜻이 아니라
 *   "규칙이 볼 재료는 있었다"는 뜻일 뿐이다. 통과/합격이라고 말하면 안 된다.
 *
 * 경로 출처 = 각 규칙의 추출 함수가 실제 analyze() 결과에서 읽는 자리(주석에 "실 analyze()
 * 결과"로 명시된 경로). 골든 픽스처 전용 평면 경로는 넣지 않는다(화면에서는 안 오므로).
 */
export const RULE_INPUT_PATHS: Record<string, readonly string[]> = {
  G1_PROTECTION_ZONE_RISK: ["development_plans.land_use_regulations"],
  G2_SCHOOL_POI_DEDUP: ["location.education.school_count"],
  G3_ZONE_COVERAGE_GAP: ["effective_far"],
  TERRAIN_SLOPE_COLLECTION_GAP: ["special_parcel", "dev_act_permit_gate"],
  MARKET_PRICE_METHODOLOGY: ["land_prices"],
  SALE_PRICE_POINT_ESTIMATE: ["sale_prices"],
  PROV_UNKNOWN_SOURCE: ["provenance"],
  PROV_STALE_DATA: ["provenance"],
};

/* ── 사용자 카피 (프론트 정본) ── */

export interface FindingCopy {
  /** 한 줄 제목 — 무엇이 문제인지. */
  headline: string;
  /** 사용자가 이 표시를 보고 무엇을 해야 하는지. */
  action: string;
}

export const FINDING_COPY: Record<string, FindingCopy> = {
  G1_PROTECTION_ZONE_RISK_FLOOR: {
    headline: "보호구역이 있는데 종합 개발리스크가 그보다 낮게 산출됐습니다",
    action: "표시된 리스크 등급을 그대로 쓰지 마시고, 규제 목록의 보호구역을 기준으로 판단하세요.",
  },
  G2_SCHOOL_POI_DEDUP: {
    headline: "주변 학교 수가 실제보다 많게 집계됐습니다",
    action: "같은 학교가 여러 출입구·분교로 중복 집계된 경우입니다. 학교 목록의 이름을 직접 확인하세요.",
  },
  G3_ZONE_COVERAGE_GAP: {
    headline: "법으로 한도가 정해진 용도지역인데 건폐율·용적률이 '판정불가'로 나왔습니다",
    action: "법정 한도는 존재하므로 이 항목은 플랫폼의 자료 누락입니다. 조례 확인 전이라도 법정 한도는 적용됩니다.",
  },
  TERRAIN_SLOPE_COLLECTION_GAP: {
    headline: "임야인데 경사도를 확보하지 못했습니다",
    action: "경사도 없이는 개발행위 허가 가능성을 판단할 수 없습니다. 재조회하거나 실측 자료를 확보하세요.",
  },
  MARKET_PRICE_METHODOLOGY: {
    headline: "토지 시세는 실거래가 아니라 공시지가에 계수를 곱한 추정치입니다",
    action: "실제 거래가와 다를 수 있습니다. 금액이 중요한 판단이라면 인근 실거래를 따로 확인하세요.",
  },
  SALE_PRICE_POINT_ESTIMATE: {
    headline: "분양가는 폭이 없는 하나의 값으로만 제시됐습니다",
    action: "상·하한 없이 한 숫자만 나온 값입니다. 사업성 검토에는 여유폭을 두고 쓰세요.",
  },
  PROV_UNKNOWN_SOURCE: {
    headline: "출처가 등록되지 않은 데이터가 섞여 있습니다",
    action: "권위 있는 출처 목록에 없는 자료입니다. 해당 값은 별도 확인이 필요합니다.",
  },
  PROV_STALE_DATA: {
    headline: "원천 데이터가 오래됐습니다",
    action: "갱신 주기를 넘긴 자료입니다. 최신값이 중요하다면 재조회 후 다시 보세요.",
  },
};

/* ── 심각도 표기 ── */

export interface SeverityMeta {
  /** 화면 라벨. "차단"이라는 말을 쓰지 않는다 — 실제로 막지 않기 때문. */
  label: string;
  /** 값 자체를 쓰면 안 되는 수준인가(P0). */
  holdValue: boolean;
}

export const SEVERITY_META: Record<AuditSeverity, SeverityMeta> = {
  P0: { label: "사용 보류 권고", holdValue: true },
  P1: { label: "확인 필요", holdValue: false },
  P2: { label: "참고", holdValue: false },
};

/* ── 판정 ── */

export type AuditState = "unavailable" | "ran";

export type RuleApplicability = "applied" | "undetermined";

export interface RuleStatus {
  ruleId: string;
  applicability: RuleApplicability;
}

export interface CredibilityView {
  /**
   * ran = 자가검증이 이 보고서에 실제로 돌았다.
   * unavailable = 결과에 자가검증 정보가 없다.
   *
   * ★상태를 3개로 두지 않는 이유: 백엔드가 자가검증을 끄면(kill switch) 응답에 키를
   *   **아예 붙이지 않고** 빠져나간다. 그래서 "꺼짐"과 "구버전"과 "내부 오류"를 화면에서
   *   구분할 방법이 없다. 구분되지 않는 것을 구분된 척 표시하지 않는다.
   */
  state: AuditState;
  /** 카운터에 들어가는 실제 지적(상시 방법론 고지 제외). 심각도 높은 순. */
  issues: AuditFinding[];
  /** 항상 뜨는 방법론 고지 — 각주로만 렌더. */
  notes: AuditFinding[];
  /** P0가 하나라도 있는가 — 값 사용 보류 표기의 근거. */
  hasHold: boolean;
  rulesRegistered: number | null;
  rulesExecuted: number | null;
  /** 등록됐는데 실행되지 못한 규칙이 있다 = 이 보고서의 점검 범위가 줄었다. */
  executionShortfall: boolean;
  /**
   * 점검 규칙이 **하나도 돌지 않았다.**
   *
   * ★이 상태가 가장 위험하다: 규칙 등록이 무성으로 깨지면 백엔드는 `field_audit`을 붙이긴
   *   하되 `rules_registered: 0`으로 정직하게 보고한다. 그런데 화면이 그 0을 무시하면
   *   "규칙 8개 중 7개 적용 · 이상 없음"이라고 **거짓 안심**을 준다(적대검증 실측 확인).
   *   `registered`와 `executed` 둘 다 0인 경우를 각각 잡는다. 값이 없으면(null) 알 수 없는
   *   것이므로 0으로 단정하지 않는다.
   */
  noRulesRan: boolean;
  /** 규칙별 입력 확보 여부. */
  ruleStatuses: RuleStatus[];
  /** 섹션 매핑이 없는 finding code — 개발 중 발견용(테스트가 실패시킨다). */
  unmappedCodes: string[];
}

const SEVERITY_ORDER: Record<AuditSeverity, number> = { P0: 0, P1: 1, P2: 2 };

/**
 * 점표기 경로에 **판단에 쓸 자료가 실제로 있는가.**
 *
 * ★키 존재만 보면 안 된다: 분석 응답은 수집이 실패해도 컨테이너를 **빈 채로 항상 채워
 *   넣는다**(`effective_far: {}`·`land_prices: {}`·`sale_prices: []`). 키 존재로 세면
 *   자료가 하나도 없는 보고서가 "규칙 5개 적용됨"으로 보여서, 이 파일이 없애려던 바로 그
 *   착시(부실할수록 깨끗해 보임)를 그대로 되살린다.
 *
 * 빈 배열·빈 객체·빈 문자열은 **부재**로 본다. 숫자 0과 false는 **유효한 값**이다
 * (학교 0곳·경사도 0%는 정상 수집 결과이지 자료 없음이 아니다).
 */
export function hasPath(result: unknown, path: string): boolean {
  let cur: unknown = result;
  for (const seg of path.split(".")) {
    if (cur === null || cur === undefined || typeof cur !== "object") return false;
    cur = (cur as Record<string, unknown>)[seg];
  }
  if (cur === null || cur === undefined) return false;
  if (typeof cur === "string") return cur.trim() !== "";
  if (Array.isArray(cur)) return cur.length > 0;
  if (typeof cur === "object") return Object.keys(cur as object).length > 0;
  return true; // 숫자·불리언 — 0/false도 유효한 수집값
}

function asFindings(raw: unknown): AuditFinding[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter(
    (f): f is AuditFinding =>
      !!f && typeof f === "object" && typeof (f as AuditFinding).code === "string",
  );
}

function numberOrNull(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/**
 * 분석 결과에서 자가검증 정보를 읽어 화면이 쓸 형태로 만든다.
 *
 * 네트워크 호출 없음 — 자가검증 결과는 1단계 분석 응답에 이미 실려 온다.
 */
export function readFieldAudit(result: unknown): CredibilityView {
  const empty: CredibilityView = {
    state: "unavailable",
    issues: [],
    notes: [],
    hasHold: false,
    rulesRegistered: null,
    rulesExecuted: null,
    executionShortfall: false,
    noRulesRan: false,
    ruleStatuses: [],
    unmappedCodes: [],
  };

  if (!result || typeof result !== "object") return empty;
  const report = (result as Record<string, unknown>).field_audit as AuditReport | undefined;
  if (!report || typeof report !== "object") return empty;

  const findings = asFindings(report.findings);
  const meta = (report.metadata ?? {}) as Record<string, unknown>;
  const rulesRegistered = numberOrNull(meta.rules_registered);
  const rulesExecuted = numberOrNull(meta.rules_executed);

  const issues = findings
    .filter((f) => !ALWAYS_ON_CODES.has(f.code))
    .sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9));
  const notes = findings.filter((f) => ALWAYS_ON_CODES.has(f.code));

  const ruleStatuses: RuleStatus[] = Object.entries(RULE_INPUT_PATHS).map(([ruleId, paths]) => ({
    ruleId,
    applicability: paths.some((p) => hasPath(result, p)) ? "applied" : "undetermined",
  }));

  return {
    state: "ran",
    issues,
    notes,
    hasHold: findings.some((f) => f.severity === "P0"),
    rulesRegistered,
    rulesExecuted,
    executionShortfall:
      rulesRegistered !== null && rulesExecuted !== null && rulesExecuted < rulesRegistered,
    noRulesRan: rulesRegistered === 0 || rulesExecuted === 0,
    ruleStatuses,
    unmappedCodes: Array.from(
      new Set(findings.filter((f) => !SECTION_BY_CODE[f.code]).map((f) => f.code)),
    ),
  };
}

/** 특정 섹션에 붙일 지적·각주를 고른다. 매핑 없는 code는 어느 섹션에도 붙지 않는다. */
export function findingsForSection(view: CredibilityView, section: SectionId): {
  issues: AuditFinding[];
  notes: AuditFinding[];
} {
  return {
    issues: view.issues.filter((f) => SECTION_BY_CODE[f.code] === section),
    notes: view.notes.filter((f) => SECTION_BY_CODE[f.code] === section),
  };
}

/**
 * 섹션에 붙지 못한 지적 — 매핑 누락으로 화면에서 사라지면 안 되므로 요약 카드가 떠맡는다.
 * (조용히 버리는 대신 위로 올린다.)
 */
export function orphanIssues(view: CredibilityView): AuditFinding[] {
  return view.issues.filter((f) => !SECTION_BY_CODE[f.code]);
}

/** 등재된 카피가 있으면 그것을, 없으면 백엔드 원문을 '미가공'으로 밝혀서 돌려준다. */
export function copyFor(finding: AuditFinding): FindingCopy & { raw: boolean } {
  const known = FINDING_COPY[finding.code];
  if (known) return { ...known, raw: false };
  return {
    headline: finding.note?.trim() || `점검 항목 ${finding.code}`,
    action: "이 항목은 아직 쉬운 설명이 준비되지 않아 점검 원문을 그대로 표시합니다.",
    raw: true,
  };
}
