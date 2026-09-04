// 자재 탄소발자국(EPD) 결과 → 모세혈관(esgData) 매핑 — 순수함수(테스트 용이).
//
// 왜 필요한가(쉬운 설명): CarbonEmissionsWorkspaceClient가 계산한 "총 자재 탄소발자국
// (내재탄소·embodied carbon)"을 화면에만 보여주고 SSOT(esgData)에 저장하지 않으면, esgData를
// 읽는 다른 소비처(GRESB 스코어링 등)가 이 값을 영영 못 본다(G3 write-path 기아).
//
// ★updateEsgData는 full-replace 계약이다(useProjectContextStore.ts updateEsgData: `esgData: data`
// — updateFeasibilityData/updateCostData처럼 내부에서 기존값을 스프레드하지 않는다). 따라서 이
// 매핑 함수가 "기존 esgData를 먼저 스프레드한 뒤 embodiedCarbonKg만 patch"하는 책임을 진다
// (operationalCarbonKg·totalCarbonPerSqm 등 다른 슬롯을 이 패널이 실수로 지우지 않도록).
//
// 무날조 원칙: 총 탄소발자국이 0/음수/비숫자면(EPD 산출 실패·자재 미등록) 해당 계산을 SSOT에
// 반영하지 않는다(null 반환 — 호출측이 커밋을 건너뛴다). 기존 SSOT 값을 가짜 0으로 덮지 않는다.

import type { EsgData } from "@/store/useProjectContextStore";

/** CarbonEmissionsWorkspaceClient의 CarbonResult 중 매핑에 필요한 최소 구조(응답 부분집합). */
export interface CarbonResultLike {
  total_carbon_footprint_kgco2e?: number | null;
}

/** 0보다 큰 유한수일 때만 그대로, 아니면 null(무날조 — 0/NaN/음수 강제 금지). */
function positiveOrNull(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) && v > 0 ? v : null;
}

/**
 * 자재 탄소발자국 분석 결과 → esgData 패치(전체 교체용 객체) 매핑.
 *
 * @param result       CarbonEmissionsWorkspaceClient의 분석 결과(총 탄소발자국 kgCO2e).
 * @param prevEsgData  현재 SSOT의 esgData(full-replace 전 보존할 기존값 — 없으면 null).
 * @returns 총 탄소발자국이 양수가 아니면 null(커밋 안 함). 양수면 기존 esgData를 스프레드한 뒤
 *   embodiedCarbonKg만 덮은 완전한 EsgData 객체(updateEsgData에 그대로 전달 가능).
 */
export function carbonResultToEsgPatch(
  result: CarbonResultLike | null | undefined,
  prevEsgData: EsgData | null | undefined,
): EsgData | null {
  const totalCarbonKg = positiveOrNull(result?.total_carbon_footprint_kgco2e);
  if (totalCarbonKg == null) return null; // 산출 실패/0/음수 → SSOT 오염 방지(생략)

  // 기존 esgData가 없으면(부분 결측) 나머지 두 슬롯은 정직하게 null로 채운다(가짜값 날조 금지).
  const base: EsgData = prevEsgData ?? {
    embodiedCarbonKg: null,
    operationalCarbonKg: null,
    totalCarbonPerSqm: null,
  };
  return { ...base, embodiedCarbonKg: totalCarbonKg };
}
