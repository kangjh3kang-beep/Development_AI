import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnalysisDiffTable, DIFF_FIELD_MAP, formatFieldValue, getFieldPath } from "./AnalysisDiffTable";

describe("AnalysisDiffTable", () => {
  it("feasibility 키맵의 모든 필드를 행으로 렌더하고 증감(Δ)을 부호와 함께 표기한다", () => {
    render(
      <AnalysisDiffTable
        analysisType="feasibility"
        oldEntry={{
          version: 1,
          created_at: "2026-07-01T00:00:00Z",
          payload: {
            profit_rate_pct: 10,
            npv_won: 1_000_000,
            total_revenue_won: 5_000_000,
            net_profit_won: 500_000,
            grade: "B",
          },
        }}
        newEntry={{
          version: 2,
          created_at: "2026-07-10T00:00:00Z",
          payload: {
            profit_rate_pct: 12,
            npv_won: 900_000,
            total_revenue_won: 5_000_000,
            net_profit_won: 600_000,
            grade: "A",
          },
        }}
      />,
    );

    // 헤더 — 비교 대상 버전
    expect(screen.getByText("v1")).toBeInTheDocument();
    expect(screen.getByText("v2")).toBeInTheDocument();

    // 수익률 10% → 12% : +2.0%p
    expect(screen.getByText("수익률")).toBeInTheDocument();
    expect(screen.getByText("+2.0%p")).toBeInTheDocument();

    // NPV 감소(-100,000원) → down 방향
    expect(screen.getByText("-100,000원")).toBeInTheDocument();

    // 변동 없는 총 매출 → ±0
    const flatCells = screen.getAllByText("±0");
    expect(flatCells.length).toBeGreaterThan(0);

    // 텍스트 필드(등급)는 증감 개념이 없어 "—"로 표기
    expect(screen.getByText("등급")).toBeInTheDocument();
    expect(screen.getByText("B")).toBeInTheDocument();
    expect(screen.getByText("A")).toBeInTheDocument();
  });

  it("결측값은 가짜 0이 아니라 '—'로 표기한다(무날조)", () => {
    render(
      <AnalysisDiffTable
        analysisType="regulation"
        oldEntry={{ version: 1, created_at: "2026-07-01T00:00:00Z", payload: { zone_type: "제2종일반주거" } }}
        newEntry={{ version: 2, created_at: "2026-07-10T00:00:00Z", payload: {} }}
      />,
    );
    // newEntry에 zone_type이 없으므로 "—" 표기(빈 문자열·0 등 가짜값 금지)
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThan(0);
  });

  it("★버그 재현 방지: regulation limits는 실제 백엔드 dict shape({legal,ordinance,effective})이고, " +
    "실효 용적률/건폐율(.effective)이 숫자로 렌더된다 — 수정 전 코드(key='limits.far' 자체)라면 " +
    "'[object Object]'가 찍혔을 것이다", () => {
    // 실제 regulation_analysis_service.py 산출 shape 그대로(legal=법정·ordinance=조례·effective=실효).
    render(
      <AnalysisDiffTable
        analysisType="regulation"
        oldEntry={{
          version: 1,
          created_at: "2026-07-01T00:00:00Z",
          payload: {
            limits: {
              far: { legal: 250, ordinance: 200, effective: 180 },
              bcr: { legal: 60, ordinance: 50, effective: 45 },
            },
          },
        }}
        newEntry={{
          version: 2,
          created_at: "2026-07-10T00:00:00Z",
          payload: {
            limits: {
              far: { legal: 250, ordinance: 200, effective: 190 },
              bcr: { legal: 60, ordinance: 50, effective: 48 },
            },
          },
        }}
      />,
    );
    expect(screen.getByText("실효 용적률")).toBeInTheDocument();
    expect(screen.getByText("실효 건폐율")).toBeInTheDocument();
    expect(screen.getByText("180.0%")).toBeInTheDocument();
    expect(screen.getByText("190.0%")).toBeInTheDocument();
    expect(screen.getByText("45.0%")).toBeInTheDocument();
    expect(screen.getByText("48.0%")).toBeInTheDocument();
    // dict를 leaf로 잘못 렌더하면 이 문자열이 찍힌다 — 부재를 명시적으로 확인(무날조 회귀 방지).
    expect(screen.queryByText("[object Object]")).not.toBeInTheDocument();
  });

  it("실효(.effective)가 old/new 모두 결측이면 법정(.legal) 폴백 행을 추가로 표시한다(무날조)", () => {
    render(
      <AnalysisDiffTable
        analysisType="regulation"
        oldEntry={{
          version: 1,
          created_at: "2026-07-01T00:00:00Z",
          payload: { limits: { far: { legal: 100, ordinance: null, effective: null } } },
        }}
        newEntry={{
          version: 2,
          created_at: "2026-07-10T00:00:00Z",
          payload: { limits: { far: { legal: 100, ordinance: null, effective: null } } },
        }}
      />,
    );
    // 실효 행은 결측 "—", 법정 폴백 행이 별도로 추가되어 100.0%를 보여준다(값 실종 금지).
    expect(screen.getByText("실효 용적률")).toBeInTheDocument();
    expect(screen.getByText("법정 용적률")).toBeInTheDocument();
    expect(screen.getAllByText("100.0%").length).toBe(2); // old·new 모두 동일 법정값
  });

  it("정의되지 않은 분석 유형은 안내 문구만 표시하고 크래시하지 않는다", () => {
    render(
      <AnalysisDiffTable
        // @ts-expect-error — 런타임 방어 확인용 미정의 타입
        analysisType="unknown_type"
        oldEntry={{ version: 1, created_at: "2026-07-01T00:00:00Z", payload: {} }}
        newEntry={{ version: 2, created_at: "2026-07-10T00:00:00Z", payload: {} }}
      />,
    );
    expect(screen.getByText(/비교 항목이 정의되어 있지 않습니다/)).toBeInTheDocument();
  });

  it("getFieldPath — 점 표기 중첩 경로를 안전하게 조회한다(중간 경로 부재는 undefined)", () => {
    expect(getFieldPath({ limits: { far: 250 } }, "limits.far")).toBe(250);
    expect(getFieldPath({}, "limits.far")).toBeUndefined();
    expect(getFieldPath(null, "limits.far")).toBeUndefined();
  });

  it("formatFieldValue — fmt별 표기 규칙(퍼센트·원·만원·텍스트)", () => {
    expect(formatFieldValue(12.345, "percent")).toBe("12.3%");
    expect(formatFieldValue(1_234_567, "won")).toBe("1,234,567원");
    expect(formatFieldValue(12500, "manwon")).toBe("1억 2,500만원");
    expect(formatFieldValue("제2종일반주거", "text")).toBe("제2종일반주거");
    expect(formatFieldValue(null, "text")).toBe("—");
    expect(formatFieldValue(undefined, "won")).toBe("—");
  });

  it("DIFF_FIELD_MAP — 6개 분석 유형 모두 키맵이 정의되어 있다", () => {
    expect(DIFF_FIELD_MAP.feasibility.map((f) => f.key)).toEqual([
      "profit_rate_pct",
      "npv_won",
      "total_revenue_won",
      "net_profit_won",
      "grade",
    ]);
    expect(DIFF_FIELD_MAP.regulation.map((f) => f.key)).toEqual([
      "zone_type",
      "limits.far.effective",
      "limits.bcr.effective",
      "parcel_count",
    ]);
    expect(DIFF_FIELD_MAP.market_report.map((f) => f.key)).toEqual([
      "trade_count",
      "avg_price_10k",
      "parcel_count",
    ]);
    expect(DIFF_FIELD_MAP.permit_ai.map((f) => f.key)).toEqual(["verdict", "development_methods"]);
    expect(DIFF_FIELD_MAP.site_analysis.map((f) => f.key)).toEqual([
      "zone_type",
      "effective_far.effective_far_pct",
      "land_area_sqm",
      "potential_far_range.max_pct",
      "location.grade",
    ]);
    expect(DIFF_FIELD_MAP.precheck.map((f) => f.key)).toEqual([
      "zone_type",
      "area_sqm",
      "far_effective_pct",
      "bcr_effective_pct",
      "best",
      "pass_count",
    ]);
  });

  it("site_analysis — comprehensive_analysis 원장 요약 필드를 렌더한다(실효 용적률 결측 시 상향 상한 폴백)", () => {
    render(
      <AnalysisDiffTable
        analysisType="site_analysis"
        oldEntry={{
          version: 1,
          created_at: "2026-07-01T00:00:00Z",
          payload: {
            zone_type: "자연녹지지역",
            effective_far: { effective_far_pct: null },
            land_area_sqm: 500,
            potential_far_range: { max_pct: 80 },
            // ★R1 REVISE: comprehensive_analysis_service._analyze_location() 실제 반환 형태(1:1) —
            //   과거 { grade: "B" }만 손수 날조해 getFieldPath("location.grade")가 항상 통과하는
            //   허위 안전망이었다. 실 payload 형태(transportation/education/coordinates 등 동봉)로
            //   재작성해 wb_payload가 정말 이 형태를 그대로 실어야 그리드가 렌더됨을 검증한다.
            location: {
              transportation: { nearest_subway: null, subway_accessible: false },
              education: { schools: [], school_count: 0 },
              coordinates: {},
              location_score: 65,
              grade: "B",
              grade_description: "양호 입지 — 교통 또는 교육 인프라 중 하나 이상 양호",
              score_breakdown: ["기본 입지점수 50점"],
            },
          },
        }}
        newEntry={{
          version: 2,
          created_at: "2026-07-10T00:00:00Z",
          payload: {
            zone_type: "자연녹지지역",
            effective_far: { effective_far_pct: null },
            land_area_sqm: 520,
            potential_far_range: { max_pct: 100 },
            location: {
              transportation: {
                nearest_subway: { name: "테스트역", distance_m: 250 },
                subway_accessible: true,
              },
              education: { schools: [{ name: "테스트초" }], school_count: 1 },
              coordinates: { lat: 37.5, lon: 127.0 },
              location_score: 85,
              grade: "A",
              grade_description: "우수 입지 — 역세권·학군 모두 양호하여 주거·상업 개발 모두 유리",
              score_breakdown: ["기본 입지점수 50점", "역세권 최우수 — 테스트역 도보 250m (+25점)"],
            },
          },
        }}
      />,
    );
    expect(screen.getByText("용도지역")).toBeInTheDocument();
    expect(screen.getByText("대지면적")).toBeInTheDocument();
    expect(screen.getByText("입지등급")).toBeInTheDocument();
    // 실효 용적률이 old/new 모두 결측 → "실효 용적률" 행은 "—", 상향 상한 폴백 행이 추가된다.
    expect(screen.getByText("실효 용적률")).toBeInTheDocument();
    // "상향 상한" 라벨은 두 번 등장한다 — ①실효 결측 시 붙는 폴백 행, ②상향 상한 자체의 주 필드 행.
    // 두 행 모두 같은 키(potential_far_range.max_pct)를 읽으므로 값도 동일하게 두 번씩 렌더된다.
    expect(screen.getAllByText("상향 상한").length).toBe(2);
    expect(screen.getAllByText("80.0%").length).toBe(2);
    expect(screen.getAllByText("100.0%").length).toBe(2);
  });

  it("site_analysis — 실효 용적률이 확보되면 폴백 행 없이 실측값을 렌더한다", () => {
    render(
      <AnalysisDiffTable
        analysisType="site_analysis"
        oldEntry={{
          version: 1,
          created_at: "2026-07-01T00:00:00Z",
          payload: { effective_far: { effective_far_pct: 180 } },
        }}
        newEntry={{
          version: 2,
          created_at: "2026-07-10T00:00:00Z",
          payload: { effective_far: { effective_far_pct: 190 } },
        }}
      />,
    );
    expect(screen.getByText("180.0%")).toBeInTheDocument();
    expect(screen.getByText("190.0%")).toBeInTheDocument();
    // 실효값이 있으므로 폴백 행은 추가되지 않는다 — "상향 상한" 라벨은 그 자체의 주 필드 행(4번째
    // 정의) 1개만 남는다(값은 potential_far_range 미전달이라 "—").
    expect(screen.getAllByText("상향 상한").length).toBe(1);
  });

  it("precheck — /precheck/instant 원장 요약 필드를 렌더하고 결측은 '—'로 표기한다", () => {
    render(
      <AnalysisDiffTable
        analysisType="precheck"
        oldEntry={{
          version: 1,
          created_at: "2026-07-01T00:00:00Z",
          payload: {
            zone_type: "제2종일반주거지역",
            area_sqm: 300,
            far_effective_pct: 200,
            bcr_effective_pct: 50,
            best: "M06",
            pass_count: 3,
          },
        }}
        newEntry={{
          version: 2,
          created_at: "2026-07-10T00:00:00Z",
          payload: { zone_type: "제2종일반주거지역" },
        }}
      />,
    );
    expect(screen.getByText("용도지역")).toBeInTheDocument();
    expect(screen.getByText("대지면적")).toBeInTheDocument();
    expect(screen.getByText("실효 용적률")).toBeInTheDocument();
    expect(screen.getByText("실효 건폐율")).toBeInTheDocument();
    expect(screen.getByText("추천 개발방식")).toBeInTheDocument();
    expect(screen.getByText("허용방식수")).toBeInTheDocument();
    // newEntry에 area_sqm/far/bcr/best/pass_count가 모두 없음 → 각 "—"(가짜 0 금지)
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(5);
  });
});
