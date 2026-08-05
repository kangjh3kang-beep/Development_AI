/**
 * 종합분석 보고서 — 관점(페르소나)별 스토리라인 SSOT.
 *
 * 같은 데이터를 누가 읽느냐에 따라 **먼저 봐야 할 것이 다르다.** 설계사는 "법적으로 얼마나
 * 지을 수 있나"부터, 금융은 "담보가치와 회수재원이 얼마나 단단한가"부터 본다. 그래서 본문은
 * 한 벌 그대로 두고 **순서와 요약문만** 관점별로 얹는다(데이터 재계산 0 · 새 API 0).
 *
 * ## 설계 원칙
 *
 * 1. **기본값은 중립** — 아무도 고르지 않으면 종전과 정확히 같은 순서로 보인다. 관점 기능이
 *    켜졌다는 이유로 화면이 멋대로 바뀌면 안 된다.
 * 2. **키는 백엔드 페르소나 레지스트리와 같은 문자열** — designer·developer·constructor는
 *    이미 백엔드에 있는 키다. 화면 전용으로 새 이름을 만들면 같은 개념이 두 이름을 갖는다.
 * 3. **순서에 없는 섹션도 사라지지 않는다** — 명시 순서 뒤에 나머지가 원래 순서로 붙는다.
 *    새 섹션이 추가됐을 때 관점을 고른 사용자에게만 그 섹션이 안 보이는 사고를 막는다.
 * 4. **없는 것을 있다고 하지 않는다** — 시공·금융 관점의 핵심(공사비·공정 / 수지·LTV·상환)은
 *    이 보고서에 없다. 지어내지 않고 "이 보고서 범위 밖 · 어느 모듈로 가야 하는지"를 적는다.
 *
 * ★문구와 판정 키를 섞지 않는다: 이 파일의 `key`는 비교·저장용이고 사용자에게 보이는 것은
 *   `label`·`summary`다. 문구를 고쳐도 순서 판정이 흔들리지 않는다(2026-08-02 W4 교훈 13).
 */

/** 보고서 섹션 식별자 — 표시 문구가 아니라 코드다(문구를 바꿔도 순서가 안 깨진다). */
export type AnalysisSectionId =
  | "effective-far"       // §1 실효용적률(+1-B 최적화)
  | "supply-area"         // §2 개발방식별 적정공급면적
  | "land-price"          // §3 토지 주변시세
  | "transactions"        // §4 물건별 주변 실거래가
  | "sale-price"          // §5 개발유형별 예상 분양가
  | "location"            // §6 입지분석
  | "dev-plans";          // §7 주변 개발계획 및 규제

/** 화면에 나타나는 기본(중립) 순서 — 관점 미선택 시 이 순서 그대로다. */
export const NEUTRAL_SECTION_ORDER: readonly AnalysisSectionId[] = [
  "effective-far", "supply-area", "land-price", "transactions",
  "sale-price", "location", "dev-plans",
];

export type PersonaKey = "designer" | "developer" | "constructor" | "finance";

export type PersonaSpec = {
  key: PersonaKey;
  /** 화면 라벨(짧게 — 토글 버튼에 들어간다). */
  label: string;
  /** 이 관점이 이 보고서에서 무엇을 먼저 보는지 한 문장. */
  summary: string;
  /** 강조 순서. 여기 없는 섹션은 뒤에 중립 순서로 붙는다. */
  order: readonly AnalysisSectionId[];
  /** 처음부터 펼쳐 둘 섹션(그 관점이 가장 먼저 읽어야 하는 것). */
  expanded: readonly AnalysisSectionId[];
  /**
   * 이 관점의 핵심인데 **이 보고서에 없는 것**. 없으면 undefined.
   * 비워두지 않고 명시하는 이유: 관점 이름만 붙여놓고 정작 그 관점이 필요로 하는 것을
   * 안 준다면, 사용자는 없는 것을 있다고 오해한다.
   */
  outOfScope?: { what: string; where: string };
};

export const PERSONAS: readonly PersonaSpec[] = [
  {
    key: "designer",
    label: "설계사",
    summary: "법적으로 지을 수 있는 최대 규모와, 그것을 가로막는 규제·절차",
    order: ["effective-far", "supply-area", "dev-plans", "location"],
    expanded: ["effective-far"],
  },
  {
    key: "developer",
    label: "디벨로퍼",
    summary: "얼마에 팔 수 있고 얼마나 지을 수 있나 — 그리고 사업을 깨뜨릴 리스크",
    order: ["sale-price", "supply-area", "effective-far", "land-price", "transactions", "location", "dev-plans"],
    expanded: ["sale-price", "supply-area"],
  },
  {
    key: "constructor",
    label: "시공사",
    summary: "지어야 할 물량과, 현장 조건이 만드는 공사 난이도",
    order: ["supply-area", "effective-far", "location", "dev-plans"],
    expanded: ["supply-area"],
    outOfScope: {
      what: "공사비·공정",
      where: "적산·공정 모듈(이 보고서는 물량과 현장 조건까지만 다룹니다)",
    },
  },
  {
    key: "finance",
    label: "금융",
    summary: "담보가치와 회수재원의 근거 — 그리고 그 숫자가 추정인지 공식인지",
    order: ["land-price", "transactions", "sale-price", "supply-area", "effective-far", "location", "dev-plans"],
    expanded: ["land-price", "transactions"],
    outOfScope: {
      what: "수지·LTV·상환 스케줄",
      where: "사업성(수지) 모듈(이 보고서는 담보·회수재원의 근거까지만 다룹니다)",
    },
  },
];

export function personaByKey(key: string | null | undefined): PersonaSpec | null {
  if (!key) return null;
  return PERSONAS.find((p) => p.key === key) ?? null;
}

/**
 * 관점에 맞춘 섹션 순서. 관점이 없으면 중립 순서 그대로.
 *
 * ★명시 순서에 빠진 섹션은 **버리지 않고** 뒤에 중립 순서로 붙인다 — 새 섹션이 생겼을 때
 *   관점을 고른 사용자에게만 그 섹션이 사라지는 사고를 구조적으로 막는다.
 */
export function sectionOrderFor(key: string | null | undefined): AnalysisSectionId[] {
  const persona = personaByKey(key);
  if (!persona) return [...NEUTRAL_SECTION_ORDER];
  const head = persona.order.filter((id) => NEUTRAL_SECTION_ORDER.includes(id));
  const rest = NEUTRAL_SECTION_ORDER.filter((id) => !head.includes(id));
  return [...head, ...rest];
}

/** 관점 기준으로 이 섹션을 처음부터 펼칠지. 관점이 없으면 종전 기본값(caller가 정함)을 쓴다. */
export function isExpandedFor(key: string | null | undefined, section: AnalysisSectionId): boolean | null {
  const persona = personaByKey(key);
  if (!persona) return null;
  return persona.expanded.includes(section);
}
