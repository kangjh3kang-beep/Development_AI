// 설계 스튜디오 "층수 단일 진실원천(SSOT)" 공용 유틸.
//
// 배경(층수 3중 불일치 버그): 같은 화면에서 ① 축측 도식이 '25층', ② 예상층수 카드가
//   '43~65', ③ 우측 메트릭칩이 '층수 65'처럼 서로 다른 층수를 보였다. 근본원인은
//   (1) 높이제한이 없는 일반상업(heightLimit=null)에서 층수를 임의 25층으로 캡한 매직폴백,
//   (2) 층수가 calc.maxFloors(산술하한)·calc.recFloors·envResult.recommended_*·
//       activeMassing.floors 등 여러 곳에서 따로 산출돼 단일 정본이 없었던 점이다.
//
// 이 파일은 "정본 층수(canonicalFloors)"를 한 곳에서 도출하는 순수 함수를 제공한다
//   (스토어 미접근 — 인자로만 받는다). 모든 소비처(축측·배치도·예상층수 카드·메트릭칩)가
//   같은 정본을 읽게 해, 한 곳을 고치면 전역이 따라오게 한다(공용화).
//
// 무날조 원칙: 정본을 구할 수 없으면 null(가짜 숫자 0/임의 캡 금지) — 화면은 null을 "—"로 표기.

// 유한 숫자만 통과(NaN/Infinity/비숫자는 거름). 미확보 시 undefined. (zoning-ssot.ts 가드 패턴 차용)
function num(v: unknown): number | undefined {
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}

// 유한 '양수'만 통과(0·음수도 거름). 층수처럼 0·음수가 정본으로 새면 안 되는 값에 쓴다(무날조).
function posNum(v: unknown): number | undefined {
  const n = num(v);
  return n != null && n > 0 ? n : undefined;
}

// 문자열 정규화(공백 제거, 빈값은 null). (zoning-ssot.ts 가드 패턴 차용)
function str(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v.trim() : null;
}

/**
 * 정본 층수(canonicalFloors) — 모든 층수 소비처의 단일 진실원천.
 *
 * 우선순위: 일조 인벨로프 권장 상한(recommended_floors_high) > 권장 하한(recommended_floors_low)
 *   > 로컬 권장 폴백(recFloorsFallback, 양수일 때만). 셋 다 없으면 null(무날조 — 화면은 "—").
 *
 * 순수 함수. recFloorsFallback은 호출부에서 calc(법규 계산)가 있을 때만 넘긴다.
 */
export function resolveCanonicalFloors(
  envResult?: { recommended_floors_high?: number | null; recommended_floors_low?: number | null } | null,
  recFloorsFallback?: number | null,
): number | null {
  // ★층수는 0·음수가 정본으로 새면 안 된다(posNum) — 일조 엔진이 0층을 줘도 칩 "0층"/designData=0
  //   누수 차단. recFloorsFallback도 양수만(대칭). 셋 다 없으면 null(무날조 — 화면 "—").
  return (
    posNum(envResult?.recommended_floors_high) ??
    posNum(envResult?.recommended_floors_low) ??
    posNum(recFloorsFallback) ??
    null
  );
}

// ── deriveDesignSSOT 입력 타입(느슨한 옵셔널 — DesignStudio가 쓰는 것과 정합) ──
// 각 타입은 모든 키 옵셔널/nullable로 둬, 구버전/부분 데이터에도 무손상으로 동작한다.

// 부지분석(SiteAnalysis) — 면적·용도지역(통합값 우선 폴백 포함)만 느슨하게 받는다.
type DesignSiteInput = {
  landAreaSqm?: number | null;
  integratedFarEffPct?: number | null;
  integratedBcrEffPct?: number | null;
  dominantZoneCode?: string | null;
  effectiveFarPct?: number | null;
  effectiveBcrPct?: number | null;
  nationalFarPct?: number | null;
  nationalBcrPct?: number | null;
  zoneCode?: string | null;
} | null | undefined;

// 설계 산출(DesignData) — 건물용도만 폴백용으로 느슨하게 받는다.
type DesignDataInput = {
  buildingType?: string | null;
} | null | undefined;

// 일조 인벨로프 결과 — 정본 층수 도출에 쓰는 권장 층수 필드만.
type DesignEnvInput = {
  recommended_floors_high?: number | null;
  recommended_floors_low?: number | null;
} | null | undefined;

// 법규 계산(localCalc) — 면적·용적률·건폐율·산술하한/권장 층수 등 확정값.
type DesignCalcInput = {
  floorAreaRatio?: number | null;   // 적용 용적률(%·실효 우선)
  buildingCoverage?: number | null; // 적용 건폐율(%·실효 우선)
  maxGrossArea?: number | null;     // 최대 연면적(㎡)
  buildableArea?: number | null;    // 건축가능면적(㎡)
  maxFloors?: number | null;        // 산술하한(건폐율 만충) — 법적 개념 아님
  recFloors?: number | null;        // 로컬 권장 층수(현실 보정)
} | null | undefined;

/**
 * 설계 SSOT 계약 타입 — 향후 메트릭바·소비처가 한 객체로 읽도록 표준화(INC4용).
 *
 * 무날조: 미확보 필드는 null(0/가짜 생성 금지). 숫자 비율(farPct·bcrPct 등)은 비율 자체가
 *   없으면 0이 아니라 그대로 0% 의미가 모호하므로, 입력에 확정값이 없으면 0 폴백 대신
 *   원입력을 그대로 반영하고 부재는 별도 nullable 필드로 구분한다.
 */
export type DesignSSOT = {
  landAreaSqm: number | null;       // 대지면적(㎡·통합 우선) — 미확보 시 null
  zoneCode: string | null;          // 용도지역 코드(통합 dominant 우선) — 미확보 시 null
  farPct: number;                   // 적용 용적률(%)
  bcrPct: number;                   // 적용 건폐율(%)
  gfaSqm: number;                   // 최대 연면적(㎡)
  buildableAreaSqm: number;         // 건축가능면적(㎡)
  canonicalFloors: number | null;   // 정본 층수 — 미확보 시 null(무날조 "—")
  arithmeticMinFloors: number;      // 산술하한 층수(근거용·정본과 구분)
  buildingType: string | null;      // 건물용도 — 미확보 시 null
  bcr: number;                      // bcrPct 별칭(소비처 호환)
  far: number;                      // farPct 별칭(소비처 호환)
};

/**
 * 설계 SSOT 도출 — 부지분석·설계데이터·일조 인벨로프·법규 계산을 묶어 단일 계약 객체로.
 *
 * ★이번 증분에서 DesignStudio가 당장 이 함수를 쓸 필요는 없다(존재만 — INC4용). 핵심은
 *   resolveCanonicalFloors로 층수를 일원화하는 것이며, 이 함수는 그 정본을 포함한 전체
 *   설계 SSOT를 한 객체로 표준화해 향후 메트릭바가 재사용하게 한다.
 *
 * 우선순위(면적·용도·비율): 통합(blended) > 단일 실효 > 법정. (zoning-ssot.ts resolve*와 동형)
 * 무날조: 면적·용도·정본 층수는 미확보 시 null. 순수 함수.
 */
export function deriveDesignSSOT(
  siteAnalysis: DesignSiteInput,
  designData: DesignDataInput,
  envResult: DesignEnvInput,
  calc: DesignCalcInput,
): DesignSSOT {
  // 면적(㎡) — 부지분석 통합/대표 면적. 미확보 시 null.
  const landAreaSqm = num(siteAnalysis?.landAreaSqm) ?? null;
  // 용도지역 — 통합 dominant 우선, 없으면 단일 zoneCode. 미확보 시 null.
  const zoneCode = str(siteAnalysis?.dominantZoneCode) ?? str(siteAnalysis?.zoneCode);
  // 적용 용적률/건폐율(%) — calc가 이미 "통합>실효>법정" 우선순위로 산출한 확정값.
  const farPct = num(calc?.floorAreaRatio) ?? 0;
  const bcrPct = num(calc?.buildingCoverage) ?? 0;
  const gfaSqm = num(calc?.maxGrossArea) ?? 0;
  const buildableAreaSqm = num(calc?.buildableArea) ?? 0;
  const arithmeticMinFloors = num(calc?.maxFloors) ?? 0;
  // 정본 층수 — 일조 인벨로프 권장 우선, 없으면 calc.recFloors 폴백(calc 있을 때만 의미).
  const canonicalFloors = resolveCanonicalFloors(envResult, num(calc?.recFloors) ?? null);
  const buildingType = str(designData?.buildingType);
  return {
    landAreaSqm,
    zoneCode,
    farPct,
    bcrPct,
    gfaSqm,
    buildableAreaSqm,
    canonicalFloors,
    arithmeticMinFloors,
    buildingType,
    bcr: bcrPct,
    far: farPct,
  };
}
