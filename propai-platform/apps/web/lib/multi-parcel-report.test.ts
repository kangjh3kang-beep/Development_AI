// mapMultiParcelReportResponse — S5(/zoning/multi-parcel-report) 응답 → MultiParcelAttributeMatrix
// 계약 매퍼 순수함수 테스트. 검증: ①verification→area_verification 키 정렬(값 불변)
// ②나머지 필드 그대로 통과 ③null/undefined 입력 → null(추정 렌더 금지).

import { describe, it, expect } from "vitest";
import { mapMultiParcelReportResponse, type MultiParcelReportResponse } from "@/lib/multi-parcel-report";

describe("mapMultiParcelReportResponse", () => {
  it("verification 키를 area_verification으로 정렬하고 값은 그대로 보존한다", () => {
    const resp: MultiParcelReportResponse = {
      report_type: "multi_parcel_report",
      parcel_count: 3,
      matrix: [{ pnu: "P-A", area_sqm: 1000 }],
      usable_area: { gross_sqm: 1800, usable_confirmed_sqm: 1000 },
      verification: { all_consistent: true, discrepancy_count: 0 },
      senior_review: [{ rule_id: "assembly.blocked_share", verdict: "WARN" }],
      zone_straddle_ruling: { straddle: true, applied_rule: "가중평균+과반" },
      exclusion_scenario: { lost_area_sqm: 300 },
    };
    const mapped = mapMultiParcelReportResponse(resp);
    expect(mapped).not.toBeNull();
    expect(mapped!.area_verification).toEqual({ all_consistent: true, discrepancy_count: 0 });
    expect(mapped!.matrix).toEqual(resp.matrix);
    expect(mapped!.usable_area).toEqual(resp.usable_area);
    expect(mapped!.senior_review).toEqual(resp.senior_review);
    expect(mapped!.zone_straddle_ruling).toEqual(resp.zone_straddle_ruling);
    expect(mapped!.exclusion_scenario).toEqual(resp.exclusion_scenario);
    // 원본 응답에는 area_verification 키 자체가 없다(백엔드는 `verification`만 반환).
    expect((resp as Record<string, unknown>).area_verification).toBeUndefined();
  });

  it("필드 미확보는 null로 정직 표기한다(추정 채움 금지)", () => {
    const mapped = mapMultiParcelReportResponse({ report_type: "multi_parcel_report" });
    expect(mapped).toEqual({
      matrix: null,
      usable_area: null,
      area_verification: null,
      senior_review: null,
      zone_straddle_ruling: null,
      exclusion_scenario: null,
    });
  });

  it("null/undefined 입력은 null을 반환한다(완전 미표시 유도)", () => {
    expect(mapMultiParcelReportResponse(null)).toBeNull();
    expect(mapMultiParcelReportResponse(undefined)).toBeNull();
  });
});
