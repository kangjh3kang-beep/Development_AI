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
import { BUILDING_USE_LABEL } from "@/lib/building-use";

/**
 * `kr-construction-cost.CostInput` 의 면적·용도 부분.
 *
 * ★`totalFloorArea` 가 **필수 number** 라 「모름」을 표현할 수 없다.
 *   그래서 모르면 **null 을 돌려주고 호출부가 판단**하게 한다 —
 *   여기서 0 을 채우면 공사비가 **0원**으로 계산돼 조용히 틀린다.
 */
export function toConstructionCostAreas(
  o: BuildingOverview,
): { totalFloorArea: number; buildingUse: string } | null {
  const total = deriveTotalGfaSqm(o);
  if (total === null) return null;
  const primary = o.uses[0]?.use ?? null;
  return {
    totalFloorArea: total,
    // 소비처가 한국어 문자열을 기대한다 — 정본 라벨을 쓴다(라벨도 정본에서 파생)
    buildingUse: primary ? BUILDING_USE_LABEL[primary] : "",
  };
}

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
