/**
 * 토지 동의율·확보율 산정 — 면적 가중이 기본(법정 기준).
 *
 * 왜 면적 가중인가:
 *   도시개발법 제11조·주택법 등 개발사업 동의 요건의 핵심 축은 "토지면적"이다
 *   (예: 도시개발법은 토지면적 2/3 이상 + 토지소유자 총수 1/2 이상을 함께 요구).
 *   필지 "건수" 비율만 보면 큰 필지 1개가 미동의여도 작은 필지 다수가 동의하면
 *   높은 수치가 나와 법정 요건 충족으로 오독된다.
 *   (예: 10,000㎡ 1필지 미동의 + 100㎡ 9필지 동의 → 건수 90% / 면적 8.3%)
 *
 * 건수 비율은 소유자 수 요건의 근사치로서 의미가 있으므로 함께 반환해 병기한다
 * (1필지=1소유자 가정이므로 정확한 소유자 수는 아님 — 공유지분은 별도).
 */

/** 면적을 가진 필지 행의 최소 계약. */
export interface LandAreaRow {
  area_sqm?: number | null;
}

export interface LandRatio {
  /** 면적 가중 비율 0~1. 총면적이 0이면 0. ★법정 요건 판정 축. */
  areaRatio: number;
  /** 필지 건수 비율 0~1. 총 건수가 0이면 0. 소유자 수 요건의 근사. */
  countRatio: number;
  matchedAreaSqm: number;
  totalAreaSqm: number;
  matchedCount: number;
  totalCount: number;
}

/** 유한 양수만 면적으로 인정(null·NaN·음수는 0). */
function sqm(row: LandAreaRow): number {
  const v = row.area_sqm;
  return typeof v === "number" && Number.isFinite(v) && v > 0 ? v : 0;
}

/**
 * `match`를 만족하는 필지의 비율을 면적 가중·건수 양축으로 산정한다.
 * 면적이 0인 필지(미입력)는 면적 분모/분자에서 자연히 빠지고 건수에는 남는다.
 */
export function landRatio<T extends LandAreaRow>(
  rows: readonly T[],
  match: (row: T) => boolean,
): LandRatio {
  let matchedAreaSqm = 0;
  let totalAreaSqm = 0;
  let matchedCount = 0;

  for (const row of rows) {
    const a = sqm(row);
    totalAreaSqm += a;
    if (match(row)) {
      matchedAreaSqm += a;
      matchedCount += 1;
    }
  }

  const totalCount = rows.length;
  return {
    areaRatio: totalAreaSqm > 0 ? matchedAreaSqm / totalAreaSqm : 0,
    countRatio: totalCount > 0 ? matchedCount / totalCount : 0,
    matchedAreaSqm,
    totalAreaSqm,
    matchedCount,
    totalCount,
  };
}
