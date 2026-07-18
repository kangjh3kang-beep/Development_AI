import { describe, expect, it } from "vitest";
import {
  buildTrendLightPath,
  mapLightTrend,
  mapReportTrendSeries,
  selectTrendChartPoints,
  trendStatusMessage,
} from "@/lib/market-trend-light";

describe("market-trend-light — 순수 헬퍼(state 없음)", () => {
  describe("mapReportTrendSeries — 3개월(기존 report.trend_series) 매핑 무변경", () => {
    it("유효값만 매핑하고 mom_pct를 그대로 보존한다", () => {
      const out = mapReportTrendSeries([
        { ym: "202604", per_pyeong_manwon: 3000, mom_pct: null },
        { ym: "202605", per_pyeong_manwon: 3100, mom_pct: 3.3 },
      ]);
      expect(out).toEqual([
        { ym: "202604", perPyeong: 3000, mom: null },
        { ym: "202605", perPyeong: 3100, mom: 3.3 },
      ]);
    });

    it("0/음수/누락 평당가는 제외한다(무날조)", () => {
      const out = mapReportTrendSeries([
        { ym: "202603", per_pyeong_manwon: 0 },
        { ym: "202604", per_pyeong_manwon: null },
        { ym: "202605", per_pyeong_manwon: -5 },
        { ym: "202606", per_pyeong_manwon: 3100, mom_pct: 1 },
      ]);
      expect(out).toEqual([{ ym: "202606", perPyeong: 3100, mom: 1 }]);
    });

    it("null/undefined 입력은 빈 배열(예외 없음)", () => {
      expect(mapReportTrendSeries(null)).toEqual([]);
      expect(mapReportTrendSeries(undefined)).toEqual([]);
    });
  });

  describe("mapLightTrend — GET /market/trend 응답(avg_per_pyeong) 매핑", () => {
    it("mom은 항상 null(경량 응답에 전월대비 없음 — 신규 산식 0)", () => {
      const out = mapLightTrend([
        { ym: "202501", avg_per_pyeong: 2800 },
        { ym: "202502", avg_per_pyeong: 2900 },
      ]);
      expect(out).toEqual([
        { ym: "202501", perPyeong: 2800, mom: null },
        { ym: "202502", perPyeong: 2900, mom: null },
      ]);
    });

    it("데이터 부족 월(0/누락)은 빈 채로 두지 않고 그대로 제외한다(빈 월 채우기 금지)", () => {
      const out = mapLightTrend([
        { ym: "202501", avg_per_pyeong: 0 },
        { ym: "202502", avg_per_pyeong: 2900 },
        { ym: "202503" },
      ]);
      expect(out).toEqual([{ ym: "202502", perPyeong: 2900, mom: null }]);
    });
  });

  describe("selectTrendChartPoints — 기간 칩에 따른 데이터소스 선택", () => {
    const baseSeries = [{ ym: "202604", perPyeong: 3000, mom: 1 }];
    const lightTrend = [
      { ym: "202501", perPyeong: 2800, mom: null },
      { ym: "202502", perPyeong: 2900, mom: null },
    ];

    it("3개월 = report.trend_series 그대로(무변경 기본)", () => {
      expect(selectTrendChartPoints(3, baseSeries, lightTrend)).toBe(baseSeries);
    });

    it("12개월 = 경량 GET 응답", () => {
      expect(selectTrendChartPoints(12, baseSeries, lightTrend)).toBe(lightTrend);
    });

    it("24개월 = 경량 GET 응답", () => {
      expect(selectTrendChartPoints(24, baseSeries, lightTrend)).toBe(lightTrend);
    });
  });

  describe("buildTrendLightPath — 쿼리 경로 조립", () => {
    it("pnu가 있으면 포함한다", () => {
      const path = buildTrendLightPath({ address: "서울 강남구 역삼동", pnu: "1168010100", months: 12 });
      const [base, qs] = path.split("?");
      const params = new URLSearchParams(qs);
      expect(base).toBe("/market/trend");
      expect(params.get("address")).toBe("서울 강남구 역삼동");
      expect(params.get("pnu")).toBe("1168010100");
      expect(params.get("months")).toBe("12");
    });

    it("pnu가 없으면(null/undefined/빈문자열) 쿼리에서 생략한다", () => {
      for (const pnu of [null, undefined, ""] as const) {
        const path = buildTrendLightPath({ address: "서울", pnu, months: 24 });
        const params = new URLSearchParams(path.split("?")[1]);
        expect(params.has("pnu")).toBe(false);
      }
    });
  });

  describe("trendStatusMessage — 로딩/실패/데이터부족 상태 메시지(정직 실패 문구)", () => {
    it("12/24개월 로딩 중이면 로딩 문구", () => {
      expect(trendStatusMessage({ months: 12, loading: true, error: "", pointsCount: 0 }))
        .toBe("추이 조회 중…");
    });

    it("12/24개월 실패 시 실패 사유를 그대로 노출한다(삼키지 않음)", () => {
      expect(
        trendStatusMessage({ months: 24, loading: false, error: "네트워크 오류 — 연결이 지연되거나 끊겼습니다. 다시 시도해 주세요.", pointsCount: 0 }),
      ).toBe("네트워크 오류 — 연결이 지연되거나 끊겼습니다. 다시 시도해 주세요.");
    });

    it("3개월 경로는 loading/error를 갖지 않으므로(별도 fetch 없음) 무시하고 데이터부족만 본다", () => {
      expect(trendStatusMessage({ months: 3, loading: true, error: "무시되어야 함", pointsCount: 5 })).toBeNull();
    });

    it("포인트가 2개 미만이면 데이터 부족 문구(기간 숫자 포함)", () => {
      expect(trendStatusMessage({ months: 12, loading: false, error: "", pointsCount: 1 }))
        .toBe("표시할 추이 데이터가 부족합니다(12개월 기준).");
    });

    it("정상(로딩 아님·실패 없음·2개 이상)이면 null(차트 렌더)", () => {
      expect(trendStatusMessage({ months: 12, loading: false, error: "", pointsCount: 2 })).toBeNull();
    });
  });
});
