/**
 * /zoning/multi-parcel-report(S5) 응답 → MultiParcelAttributeMatrix 소비 계약 매퍼(순수함수·additive).
 *
 * 백엔드 build_multi_parcel_report(special_parcel.py:1753) 계약의 검증 필드 키는 `verification`
 * (tests/test_multi_parcel_report.py SSOT)이지만, 기존 S6 렌더 컴포넌트(MultiParcelAttributeMatrix)의
 * 계약 키는 `area_verification`(다위치 resolver 관례 — resolveMultiParcelReport 참고)이다. 이 파일은
 * 그 키 이름만 정렬(값 변형 없음)해 컴포넌트를 재사용할 수 있게 한다(산식복제 0, 무날조).
 */

import type {
  AreaVerificationLike,
  ExclusionScenarioLike,
  MatrixParcelLike,
  MultiParcelReportLike,
  SeniorRuleLike,
  UsableAreaLike,
  ZoneStraddleRulingLike,
} from "@/components/projects/MultiParcelAttributeMatrix";

type Rec = Record<string, unknown>;

/** POST /zoning/multi-parcel-report 원본 응답 형태(백엔드 build_multi_parcel_report 계약). */
export type MultiParcelReportResponse = {
  report_type?: string | null;
  parcel_count?: number | null;
  matrix?: MatrixParcelLike[] | null;
  usable_area?: UsableAreaLike | null;
  zone_straddle_ruling?: ZoneStraddleRulingLike | null;
  integrated_zoning?: Rec | null;
  charges?: ({
    per_parcel?: Rec[] | null;
    total_estimated_won?: number | null;
    estimated?: boolean | null;
    unestimated_count?: number | null;
    basis?: string | null;
    honest_note?: string | null;
  } & Rec) | null;
  verification?: AreaVerificationLike | null;
  senior_review?: SeniorRuleLike[] | null;
  senior_verdict?: string | null;
  exclusion_scenario?: ExclusionScenarioLike | null;
  developability?: string | null;
  resolvable?: string | null;
  blocking_parcels?: Rec[] | null;
  honest_disclosure?: string | null;
  recommendation?: string | null;
  honest_limitations?: string[] | null;
  basis?: string | null;
} & Rec;

/** S5 응답 → MultiParcelAttributeMatrix report prop. resp가 없으면 null(추정 렌더 금지). */
export function mapMultiParcelReportResponse(
  resp: MultiParcelReportResponse | null | undefined,
): MultiParcelReportLike | null {
  if (!resp) return null;
  return {
    matrix: resp.matrix ?? null,
    usable_area: resp.usable_area ?? null,
    // ★키 정렬: 백엔드 `verification` → 컴포넌트 계약 `area_verification`(값은 그대로).
    area_verification: resp.verification ?? null,
    senior_review: resp.senior_review ?? null,
    zone_straddle_ruling: resp.zone_straddle_ruling ?? null,
    exclusion_scenario: resp.exclusion_scenario ?? null,
  };
}
