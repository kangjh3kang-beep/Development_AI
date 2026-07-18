/**
 * 시세추이 경량 조회(GET /market/trend) — 프론트 순수 헬퍼(state 없음, 네트워크 없음).
 *
 * 배경: MarketInsightsWorkspaceClient의 시세추이 카드는 보고서 생성(무거움: MOLIT 6유형+
 * SGIS+KOSIS+LLM) 결과의 3개월 추이만 표시했다. 기간 칩(3/12/24개월)에서 12·24를 선택하면
 * 보고서 전체를 재생성하지 않고 경량 GET /market/trend(아파트 매매 월별 평당가만)를 호출한다.
 *
 * 여기 함수들은 상태를 갖지 않는 순수 로직만 담당(쿼리 경로 조립·응답→차트 포인트 매핑·기간별
 * 데이터소스 선택·상태 메시지 결정) — 컴포넌트는 useState/useCallback으로 이 함수들을 감싸기만
 * 한다. 무목업: 데이터 부족 월을 채우지 않고 있는 그대로 반환(빈 배열이면 빈 배열).
 */

export type TrendPeriodMonths = 3 | 12 | 24;

/** LineChart(recharts)에 그대로 먹이는 포인트 — 기존 3개월 렌더러와 동일 shape(무변경). */
export type TrendChartPoint = { ym: string; perPyeong: number; mom: number | null };

/** report.raw_data.real_estate.trend_series 항목(보고서 생성 시 산출, mom_pct 포함). */
export type MarketTrendSeriesItem = {
  ym?: string;
  per_pyeong_manwon?: number | null;
  mom_pct?: number | null;
};

/** GET /market/trend 응답 trend[] 항목 — 전월대비(mom)는 경량 응답에 없다(신규 산식 0). */
export type MarketTrendLightItem = {
  ym?: string;
  avg_per_pyeong?: number | null;
};

export type MarketTrendLightResponse = {
  months: number;
  trend: MarketTrendLightItem[];
  source: string;
  cached: boolean;
};

/** report.trend_series(3개월, 기존 로직 그대로) → 차트 포인트. 3=무변경 기본 경로. */
export function mapReportTrendSeries(
  series: MarketTrendSeriesItem[] | null | undefined,
): TrendChartPoint[] {
  return (series ?? [])
    .filter((t) => typeof t.per_pyeong_manwon === "number" && (t.per_pyeong_manwon as number) > 0)
    .map((t) => ({ ym: t.ym ?? "", perPyeong: t.per_pyeong_manwon as number, mom: t.mom_pct ?? null }));
}

/** GET /market/trend 응답 trend[](avg_per_pyeong) → 차트 포인트. mom_pct 없음 → null(정직). */
export function mapLightTrend(
  trend: MarketTrendLightItem[] | null | undefined,
): TrendChartPoint[] {
  return (trend ?? [])
    .filter((t) => typeof t.avg_per_pyeong === "number" && (t.avg_per_pyeong as number) > 0)
    .map((t) => ({ ym: t.ym ?? "", perPyeong: t.avg_per_pyeong as number, mom: null }));
}

/** 선택된 기간 칩에 따라 차트에 쓸 데이터소스 선택 — 3=report(무변경), 12/24=경량 GET 결과. */
export function selectTrendChartPoints(
  months: TrendPeriodMonths,
  baseSeries: TrendChartPoint[],
  lightTrend: TrendChartPoint[],
): TrendChartPoint[] {
  return months === 3 ? baseSeries : lightTrend;
}

/** GET /market/trend 쿼리 경로 — address 필수, pnu는 있을 때만 포함(백엔드 계약과 동일). */
export function buildTrendLightPath(params: {
  address: string;
  pnu?: string | null;
  months: number;
}): string {
  const qs = new URLSearchParams({ address: params.address, months: String(params.months) });
  if (params.pnu) qs.set("pnu", params.pnu);
  return `/market/trend?${qs.toString()}`;
}

/**
 * 시세추이 카드 본문에 보여줄 상태 메시지 — 로딩 중/실패/데이터 부족을 정직하게 안내한다.
 * null이면 차트를 그린다(호출부의 단일 분기 창구 — 로딩·실패·데이터부족 처리를 산개시키지 않음).
 * 3개월(기본) 경로는 loading/error를 갖지 않으므로(별도 fetch 없음) 데이터부족만 검사한다.
 */
export function trendStatusMessage(state: {
  months: TrendPeriodMonths;
  loading: boolean;
  error: string;
  pointsCount: number;
}): string | null {
  if (state.months !== 3 && state.loading) return "추이 조회 중…";
  if (state.months !== 3 && state.error) return state.error;
  if (state.pointsCount < 2) return `표시할 추이 데이터가 부족합니다(${state.months}개월 기준).`;
  return null;
}
