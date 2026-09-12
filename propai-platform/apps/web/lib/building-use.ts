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
const RAW_ALIAS_TO_CODE: Record<string, BuildingUseCode> = {
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
 * ★★정본 코드 **자신**을 항등으로 등재한다 — 손 목록이 아니라 `BUILDING_USE_CODES` 에서 **파생**.
 *
 * 왜(실증 2026-09-12 · 적대 리뷰가 런타임으로 잡았다): 위 표는 한국어 라벨과 **옛 전선값**만
 * 키로 갖고 있어, 정본 코드를 그대로 넣으면 **11종 중 7종이 `null`** 이었다
 * (`rowhouse · detached · retail · neighborhood · lodging · education · knowledge`).
 * 살아남은 4종(`apartment · officetel · office · mixed`)은 **설계가 아니라 우연**이었다 —
 * 옛 전선값과 철자가 겹쳤을 뿐이다.
 *
 * ★그 결과가 **무언 실패**였다: 모달의 `<option value={code}>` 를 고르면
 * `normalizeBuildingUse(code)` 가 `null` 을 돌려주고, 호출부의 `if (next)` 가 거짓이라
 * **상태가 안 바뀌고 오류도 안 뜬다.** 사용자는 클릭했는데 아무 일도 일어나지 않는다.
 *
 * ★목록이 아니라 **파생**인 이유 — 정본에 코드를 추가하면 그 순간 항등도 따라온다.
 *   손으로 적으면 다음에 추가하는 사람이 **정확히 같은 결함**을 다시 만든다.
 * ★충돌은 **개발 중에 터뜨린다**: 어떤 정본 코드가 이미 *다른* 코드의 동의어로 등재돼
 *   있으면 항등이 그 뜻을 조용히 덮어쓴다. 그건 결함이므로 락이 잡는다(아래 테스트).
 */
const ALIAS_TO_CODE: Record<string, BuildingUseCode> = (() => {
  const map: Record<string, BuildingUseCode> = { ...RAW_ALIAS_TO_CODE };
  for (const code of BUILDING_USE_CODES) map[code] = code;
  return map;
})();

/** 락 전용 — 항등 등재가 **다른 뜻을 덮어쓰는지** 보기 위해 원표를 노출한다. */
export const __rawAliasToCode = RAW_ALIAS_TO_CODE;

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

/**
 * 정본 코드 → **전선 값**(백엔드 `building_type`).
 *
 * ★2026-09-09 실측 — 전선 값을 바꾸면 **조용히 틀린다**:
 *   `app/services/feasibility/construction_cost_engine.py`
 *     DEFAULT_DIRECT_COST_PER_SQM = { apartment · officetel · commercial · office ·
 *                                     warehouse · townhouse · single_house }
 *     _resolve_direct_unit_cost() 는 **모르면 apartment 로 폴백**한다.
 *   즉 `retail` 을 보내면 상가 단가(220만)가 아니라 **아파트 단가(240만)** 가 쓰이고
 *   아무 오류도 나지 않는다. 그래서 정본 코드는 **내부용**이고 전선은 이 표로 나간다.
 *
 * ★엔진이 모르는 용도는 **null** — 호출부가 「이 용도는 단가를 모른다」를 알아야 한다.
 *   임의로 apartment 를 보내면 그 폴백을 우리가 대신 저지르는 것이다.
 */
const CODE_TO_WIRE: Record<BuildingUseCode, string | null> = {
  apartment: "apartment",
  rowhouse: "townhouse",
  detached: "single_house",
  officetel: "officetel",
  office: "office",
  retail: "commercial",
  knowledge: "warehouse",
  // ★엔진에 단가가 없는 용도 — 전선 값을 지어내지 않는다
  neighborhood: null,
  lodging: null,
  education: null,
  mixed: null,
};

/** 정본 코드를 백엔드 `building_type` 값으로. 엔진이 모르는 용도면 **null**. */
export function toWireBuildingType(code: BuildingUseCode): string | null {
  return CODE_TO_WIRE[code];
}

/** 전선 값을 가진 코드만 — 기존 폼의 선택지를 넓히되 **깨지지 않게** 한다. */
export function wireBackedUseOptions(): { code: BuildingUseCode; label: string; wire: string }[] {
  return BUILDING_USE_CODES.flatMap((code) => {
    const wire = CODE_TO_WIRE[code];
    return wire === null ? [] : [{ code, label: BUILDING_USE_LABEL[code], wire }];
  });
}
