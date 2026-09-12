/**
 * 건축개요 정본 → **기존 소비처 이름**으로 변환하는 어댑터.
 *
 * ★94개 파일을 한 PR 로 고치지 않는다 — 되돌리기가 불가능해진다.
 *   대신 정본에서 **각 소비처의 이름으로 내려주는 함수**를 두고, 소비처는 준비되는 대로 옮긴다.
 *
 * ★실측된 이름 분열(2026-09-09):
 *     lib/kr-construction-cost.ts   CostInput.totalFloorArea (number, 필수)
 *     lib/esg-extended-panels.ts    grossFloorAreaSqm (**string**, 빈 문자열이 미입력)
 *     feasibility/ModuleInputForm   total_land_area_sqm · total_gfa_sqm
 */
import {
  type BuildingOverview,
  deriveTotalGfaSqm,
} from "@/lib/building-overview";
import { type BuildingUseCode } from "@/lib/building-use";

/**
 * ★정본 코드 → `kr-construction-cost.BASE_COST_PER_SQM` 의 **키**.
 *
 * ★★2026-09-12 — 종전 구현은 여기에 **한국어 라벨**을 실었고, 주석은
 *   *"소비처가 한국어 문자열을 기대한다"* 고 **단정**했다. **거짓이었다**(재보지 않고 썼다).
 *   소비처는 `BASE_COST_PER_SQM[input.buildingUse] ?? BASE_COST_PER_SQM.apartment` 이고
 *   그 키는 **영문**이다. 실측: 라벨 경유 **HIT 0/11** — 전 용도가 아파트 단가로 계산됐다
 *   (근생 180만을 220만으로 = **+22%**). 이 PR 이 스스로 *"그 폴백을 우리가 대신 저지르는
 *   것이다"* 라고 경고해 놓고 **프론트에서 똑같이 저질렀다.**
 *
 * ★이 표가 `CODE_TO_WIRE` 와 **다른 이유** — 두 소비처의 키 집합이 다르다(실측):
 *     백엔드 엔진   townhouse · single_house 를 안다 · neighborhood 를 **모른다**
 *     프론트 표     neighborhood 를 안다 · townhouse · single_house 를 **모른다**
 *   하나로 합치면 어느 한쪽이 조용히 폴백된다. **소비처마다 표를 따로 둔다.**
 *
 * ★모르면 **null** — 임의로 `apartment` 를 보내면 그 폴백을 우리가 대신 저지르는 것이다.
 *   락이 이 표의 값을 **소비처 파일에서 파생한 키 집합**과 대조한다(이름이 아니라 도메인).
 */
const CODE_TO_COST_KEY: Record<BuildingUseCode, string | null> = {
  apartment: "apartment",
  officetel: "officetel",
  office: "office",
  retail: "commercial",
  neighborhood: "neighborhood",
  knowledge: "warehouse",
  rowhouse: null, // 표에 공동주택 계열 세분이 없다 — 아파트로 접지 않는다
  detached: null,
  lodging: null,
  education: null,
  mixed: null,
};

/**
 * `kr-construction-cost.CostInput` 의 면적·용도 부분.
 *
 * ★`totalFloorArea` 가 **필수 number** 라 「모름」을 표현할 수 없다.
 *   그래서 모르면 **null 을 돌려주고 호출부가 판단**하게 한다 —
 *   여기서 0 을 채우면 공사비가 **0원**으로 계산돼 조용히 틀린다.
 * ★용도를 모르면 `buildingUse` 도 **null** 이다. 빈 문자열을 보내면 소비처가
 *   `?? apartment` 로 접으므로, 「모름」이 **아파트로 둔갑**한다.
 */
export function toConstructionCostAreas(
  o: BuildingOverview,
): { totalFloorArea: number; buildingUse: string | null } | null {
  const total = deriveTotalGfaSqm(o);
  if (total === null) return null;
  const primary = o.uses[0]?.use ?? null;
  return {
    totalFloorArea: total,
    buildingUse: primary ? CODE_TO_COST_KEY[primary] : null,
  };
}

/** 락 전용 — 표 전체를 소비처 키 도메인과 대조하기 위해 노출한다. */
export const __codeToCostKey = CODE_TO_COST_KEY;

/**
 * `esg-extended-panels` 의 `grossFloorAreaSqm`.
 *
 * ★그쪽은 **문자열**이고 **빈 문자열이 미입력**을 뜻한다(실측).
 *   그 규약을 여기서 지킨다 — 소비처를 고치지 않고 흡수한다.
 */
export function toEsgGrossFloorAreaSqm(o: BuildingOverview): string {
  const total = deriveTotalGfaSqm(o);
  return total === null ? "" : String(total);
}

/**
 * `feasibility/ModuleInputForm` 의 스네이크 표기.
 *
 * ★그 폼은 «대지면적·연면적을 입력하세요» 를 `> 0` 으로 판정한다(실측).
 *   그래서 모름은 `null` 로 넘겨 **0 과 구별**되게 한다.
 */
export function toFeasibilityModuleInput(o: BuildingOverview): {
  total_land_area_sqm: number | null;
  total_gfa_sqm: number | null;
} {
  return {
    total_land_area_sqm: o.landAreaSqm,
    total_gfa_sqm: deriveTotalGfaSqm(o),
  };
}
