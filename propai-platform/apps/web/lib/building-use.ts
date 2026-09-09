/**
 * 건축물 용도 **정본**(SSOT) — 건축개요 축.
 *
 * ★2026-09-09 전수 실측으로 만들었다. 손으로 고르지 않았다:
 *   건축개요 축 **4벌 · 23항목 · 합집합 15종**
 *     app/[locale]/(dashboard)/settings/design-references/page.tsx  USES
 *     components/design/DesignStudio.tsx                            _BUILDING_USE_OPTIONS
 *     components/feasibility/ModuleInputForm.tsx                    BUILDING_TYPES
 *     components/analytics/CostEstimationClient.tsx                 BUILDING_TYPES
 *
 * ★★**제외한 3벌 — 다른 질문에 답하므로 섞으면 안 된다**:
 *     components/auction/AuctionWorkspace.tsx  USAGE_OPTIONS   경매 물건 종류(토지·기타 포함)
 *     lib/kr-auction-calculator.ts             USE_RATES       용도별 평균 낙찰가율 조회 키
 *     lib/kr-carbon-calculator.ts              ENERGY_USE_INTENSITY  에너지 원단위 키(영문)
 *   섞었으면 「토지」·「기타」가 **건축개요의 용도**로 들어왔을 것이다.
 *   《이름이 겹치면 같은 제도로 읽는다》 — 목록이 비슷하다고 같은 축이 아니다.
 */

/** 정본 용도 코드 — 저장·전송은 이 코드로 한다(라벨은 화면용). */
export const BUILDING_USE_CODES = [
  "apartment", // 공동주택
  "rowhouse", // 연립·다세대
  "detached", // 단독주택
  "officetel", // 오피스텔
  "office", // 업무시설
  "retail", // 판매시설
  "neighborhood", // 근린생활시설
  "lodging", // 숙박시설
  "education", // 교육연구시설
  "knowledge", // 지식산업센터·창고
  "mixed", // 복합
] as const;

export type BuildingUseCode = (typeof BUILDING_USE_CODES)[number];

/** 코드 → 한국어 라벨(화면 표시용 단일 출처). */
export const BUILDING_USE_LABEL: Record<BuildingUseCode, string> = {
  apartment: "공동주택",
  rowhouse: "연립·다세대",
  detached: "단독주택",
  officetel: "오피스텔",
  office: "업무시설",
  retail: "판매시설",
  neighborhood: "근린생활시설",
  lodging: "숙박시설",
  education: "교육연구시설",
  knowledge: "지식산업센터·창고",
  mixed: "복합",
};

/**
 * 기존 화면들이 쓰던 **동의어**를 정본 코드로 정규화한다.
 *
 * ★실측으로 나온 동의어(같은 것을 다르게 부르던 자리):
 *     공동주택 ← 아파트 · 아파트/공동주택
 *     업무시설 ← 오피스
 *     판매시설 ← 상가
 *   ★이 표가 없으면 기존 데이터가 **미분류로 떨어진다** — 이관 없이 정본만 만들면
 *     화면은 새 목록을 쓰고 저장된 값은 옛 문자열이라 조용히 갈린다.
 */
const ALIAS_TO_CODE: Record<string, BuildingUseCode> = {
  // 정본 라벨 자신
  공동주택: "apartment",
  "연립·다세대": "rowhouse",
  단독주택: "detached",
  오피스텔: "officetel",
  업무시설: "office",
  판매시설: "retail",
  근린생활시설: "neighborhood",
  숙박시설: "lodging",
  교육연구시설: "education",
  "지식산업센터·창고": "knowledge",
  복합: "mixed",
  // 실측된 동의어
  아파트: "apartment",
  "아파트/공동주택": "apartment",
  오피스: "office",
  상가: "retail",
  "지식산업센터/창고": "knowledge",
  // 기존 영문 코드(ModuleInputForm·CostEstimationClient 가 value 로 쓰던 것)
  apartment: "apartment",
  townhouse: "rowhouse",
  single_house: "detached",
  officetel: "officetel",
  office: "office",
  commercial: "retail",
  warehouse: "knowledge",
  mixed: "mixed",
};

/**
 * 임의 문자열을 정본 코드로 바꾼다. **모르면 `null`** 을 돌려준다.
 *
 * ★「모름」을 유효값으로 표현하지 않는다 — `mixed` 로 떨어뜨리면 미분류와 복합이
 *   구별되지 않는다(《모름을 유효값으로 표현하면 관측이 된다》).
 */
export function normalizeBuildingUse(raw: string | null | undefined): BuildingUseCode | null {
  if (typeof raw !== "string") return null;
  const key = raw.trim();
  if (!key) return null;
  return ALIAS_TO_CODE[key] ?? null;
}

/** 화면용 옵션 목록 — 정본에서 **파생**한다(손으로 두 번 적지 않는다). */
export function buildingUseOptions(): { code: BuildingUseCode; label: string }[] {
  return BUILDING_USE_CODES.map((code) => ({ code, label: BUILDING_USE_LABEL[code] }));
}
