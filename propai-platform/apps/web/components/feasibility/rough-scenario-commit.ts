// 개략수지(rough-scenario) 결과 → 모세혈관(feasibilityData) 매핑 — 순수함수(테스트 용이).
//
// 왜 필요한가(쉬운 설명): RoughScenarioPanel이 계산한 결과를 화면에만 보여주고 SSOT에
// 저장하지 않으면, 뒤 단계(STEP2 투자수익성 요약·STEP3 리스크 시뮬 base 조립)가 이 값을
// 못 읽어 "먼저 개략수지를 만들어야 한다"는 안내만 반복한다. 이 파일은 그 결과를
// feasibilityData 패치(부분 갱신 객체)로 변환해, RoughScenarioPanel의 커밋 이펙트가
// updateFeasibilityData에 넘길 수 있게 한다.
//
// 무날조 원칙: 백엔드가 실제로 준 값만 옮긴다. 값이 없으면 해당 키를 patch에서 아예
// 생략해 기존 SSOT 값을 그대로 보존한다(0/가짜값으로 덮지 않음).
// 자기자본(equityWon 등)은 여기서 절대 건드리지 않는다 — updateFeasibilityData가
// 총사업비×비율로 자동 재파생하므로, 여기서 값을 세팅하면 그 자동재파생을 방해한다
// (equityIsManual=true로 오인돼 옛 값에 앵커링되는 함정 — FeasibilityEditorV2 정답 기준선 참고).

import type { FeasibilityData, FeasibilityPatch } from "@/store/useProjectContextStore";

/** RoughScenarioPanel의 RoughScenarioResult 중 매핑에 필요한 최소 구조(백엔드 응답 부분집합).
 *  RoughScenarioPanel.tsx의 private interface(RsSummary·RsRevenue·RsInputs 등)를 import하지
 *  않고, 이 파일이 실제로 읽는 필드만 구조적으로 다시 선언한다(테스트·재사용 용이). */
export interface RoughScenarioLike {
  project_id?: string | null;
  // ★정밀도 등급(#770) — 백엔드 `build_rough_scenario` 가 **최상위**에 싣는다
  //   (`summary` 안이 아니다 — orchestrator 의 반환 dict 에서 `summary` 와 형제다).
  precision?: string | null;
  precision_label?: string | null;
  precision_basis?: string | null;
  summary?: {
    total_cost_won?: number | null;
    total_revenue_won?: number | null;
    net_profit_won?: number | null;
    roi_pct?: number | null;
    npv_won?: number | null;
    grade?: string | null;
  } | null;
  revenue?: {
    sale_price_per_pyeong?: number | null;
  } | null;
  inputs?: {
    gfa_sqm?: number | null;
    // 세대수 가정(GFA÷유형 표준 전용면적, 백엔드 unit_standards 관례) — additive.
    total_households?: number | null;
  } | null;
  cashflow?: {
    summary?: {
      profit_rate_pct?: number | null;
    } | null;
  } | null;
}

/** 유한수일 때만 그대로, 아니면 null(무날조 — 0/NaN 강제 금지). */
function finiteOrNull(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** 0보다 큰 유한수일 때만 그대로, 아니면 null. */
function positiveOrNull(v: unknown): number | null {
  const n = finiteOrNull(v);
  return n != null && n > 0 ? n : null;
}

/** 0보다 큰 정수일 때만 그대로(반올림), 아니면 null(세대수 등 정수 계약용). */
function positiveIntOrNull(v: unknown): number | null {
  const n = positiveOrNull(v);
  return n == null ? null : Math.round(n);
}

/** 개략수지 결과 → 모세혈관(feasibilityData) 패치 매핑.
 *  무날조: 백엔드가 준 값만 옮기고, 없으면 해당 키를 patch에서 생략해 기존 SSOT 값을 보존한다.
 *  자기자본(equityWon/equityIsManual/equityRatioPct)은 절대 건드리지 않는다 —
 *  updateFeasibilityData가 총사업비×비율로 자동 재파생한다(수동입력 앵커링 함정 회피).
 *  의미있는 값이 하나도 없으면 null을 반환해 호출측이 stamp(updatedAt.feasibility)를 아끼게 한다. */
export function roughResultToFeasibilityPatch(
  result: RoughScenarioLike | null | undefined,
): FeasibilityPatch | null {
  if (!result) return null;
  // ★내부 조립은 느슨한 형태로 하고, 반환 직전에 grade↔precision 짝을 세운다(아래 참조).
  const patch: Partial<FeasibilityData> = {};

  // ★L1: 총사업비·총수입은 양수일 때만 커밋한다(0·음수 degraded 값이 STEP2 게이트를
  //   "결과 있음"으로 잘못 열게 두지 않는다 — 순이익(profitRatePct)은 손실(음수)도 정상값이라
  //   별도로 취급한다).
  const totalCostWon = positiveOrNull(result.summary?.total_cost_won);
  if (totalCostWon != null) patch.totalCostWon = totalCostWon;

  const totalRevenueWon = positiveOrNull(result.summary?.total_revenue_won);
  if (totalRevenueWon != null) patch.totalRevenueWon = totalRevenueWon;

  const roiPct = finiteOrNull(result.summary?.roi_pct);
  if (roiPct != null) patch.roiPct = roiPct;

  const npvWon = finiteOrNull(result.summary?.npv_won);
  if (npvWon != null) patch.npvWon = npvWon;

  const grade = result.summary?.grade;
  if (typeof grade === "string" && grade.trim()) patch.grade = grade;

  // ★정밀도 등급 — **생성 경로에서도** 옮긴다(2026-08-24).
  //
  //   `#770`(백엔드)이 등급을 산출하고 `#771`(프론트)이 배지를 붙였는데, 라이브에서
  //   배지가 **뜨지 않았다**(사용자 계정으로 '개략수지 생성'을 실제로 실행해 확인:
  //   `등급 F` 는 생기는데 스토어에 `precision` 키 자체가 없었다).
  //
  //   원인은 `feasibilityData` 의 **쓰기 경로가 둘**이라는 것이다:
  //     · `projects/[id]/page.tsx` — 프로젝트 레코드 **하이드레이션**  → `#771` 이 배선함
  //     · 이 매퍼            — 사용자가 실제로 누르는 **생성** 경로 → **누락**
  //   짝이 반만 착지한 게 아니라 **양쪽 다 착지했는데 경로가 갈려** 안 보이는 형태였다.
  //
  //   ★등급 문자열을 검증한다: 스토어 타입이 `"E"|"D"|"V"|null` 이라 모르는 값을 넣으면
  //     소비처(배지 조건 `precision === "E"`)가 판정할 수 없는 상태가 된다.
  //     모르면 **키를 만들지 않는다** — 화면은 "정밀도 미표기"로 정직하게 남는다.
  const precision = result.precision;
  if (precision === "E" || precision === "D" || precision === "V") patch.precision = precision;

  const precisionLabel = result.precision_label;
  if (typeof precisionLabel === "string" && precisionLabel.trim()) {
    patch.precisionLabel = precisionLabel;
  }

  const precisionBasis = result.precision_basis;
  if (typeof precisionBasis === "string" && precisionBasis.trim()) {
    patch.precisionBasis = precisionBasis;
  }

  // 수익률(%) — cashflow 요약(정밀 산출)이 우선, 없으면 총수입·순이익으로 산술파생
  //   (백엔드가 준 실데이터끼리의 산술이므로 무날조 위반 아님). 둘 다 없으면 생략.
  const cashflowProfitRate = finiteOrNull(result.cashflow?.summary?.profit_rate_pct);
  if (cashflowProfitRate != null) {
    patch.profitRatePct = cashflowProfitRate;
  } else {
    const netProfitWon = finiteOrNull(result.summary?.net_profit_won);
    if (totalRevenueWon != null && totalRevenueWon > 0 && netProfitWon != null) {
      patch.profitRatePct = (netProfitWon / totalRevenueWon) * 100;
    }
  }

  // 분양단가(원/평) — 백엔드 FeasibilityCalculateRequest.avg_sale_price_per_pyeong과
  //   동일 단위(무변환)로 옮긴다.
  const salePricePerPyeongWon = positiveOrNull(result.revenue?.sale_price_per_pyeong);
  if (salePricePerPyeongWon != null) patch.salePricePerPyeongWon = salePricePerPyeongWon;

  // 연면적(㎡) — 설계 확정 전 STEP3 base 조립 폴백(node-body-builders.ts가 설계 우선으로 소비).
  const totalGfaSqm = positiveOrNull(result.inputs?.gfa_sqm);
  if (totalGfaSqm != null) patch.totalGfaSqm = totalGfaSqm;

  // 세대수 가정(GFA÷유형 표준 전용면적) — 백엔드가 additive로 노출한 값을 그대로 소비한다
  //   (프론트가 산식을 복제하지 않음). 설계 확정 전 STEP3 base의 avg_area_pyeong 산식(세대수
  //   소거)이 이 값을 폴백으로 써 매출이 0으로 오탐하지 않게 한다.
  const totalHouseholds = positiveIntOrNull(result.inputs?.total_households);
  if (totalHouseholds != null) patch.totalHouseholds = totalHouseholds;

  if (Object.keys(patch).length === 0) return null;

  // ★grade↔precision 짝 세우기 — 스토어 계약(FeasibilityPatch)이 둘을 함께 요구한다.
  //   `grade` 가 없으면 정밀도도 건드리지 않는다(기존 SSOT 보존).
  //   `grade` 가 있는데 백엔드가 정밀도를 안 줬으면 **`null` 로 명시**한다 — 그래야 이전
  //   개략치(E)의 배지가 새 등급 위에 **거짓으로 남지 않는다**(merge 패치라 생략하면 남는다).
  if (!("grade" in patch)) {
    return patch as FeasibilityPatch;
  }
  return {
    ...patch,
    grade: patch.grade ?? null,
    precision: patch.precision ?? null,
  } as FeasibilityPatch;
}
