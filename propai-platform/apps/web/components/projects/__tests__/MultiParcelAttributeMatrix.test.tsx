// 다필지 필지×판정 매트릭스 UI — MultiParcelAttributeMatrix 컴포넌트 테스트(TDD, 계획서 S6).
//
// 백엔드 계약(MULTI_PARCEL_ATTRIBUTES_PLAN_2026-07-03 S3-A/B/C·S4·S5 — D 웨이브 병렬 진행 중,
// 형상은 W1 커밋된 순수모듈 산출 기준·전 필드 optional 가드):
//   usable_area  = compute_usable_area(usable_area.py):
//     {gross_sqm, usable_confirmed_sqm, usable_conditional_sqm, excluded_sqm,
//      share{confirmed_pct…}, excluded_parcels[].reasons[], area_unknown_parcels, honest_notes}
//   area_verification = verify_parcel_areas(parcel_verification.py):
//     {all_consistent, discrepancy_count, insufficient_count, per_parcel[]{pnu,status,recommendation}}
//   senior_review[] = RuleEvaluation.to_dict(land_assembly.py):
//     {rule_id, label, value, unit, verdict(PASS|WARN|BLOCK), threshold, basis, detail}
//   zone_straddle_ruling = {applied_rule, threshold_sqm?, honest_note} (S3-A — 국계법 §84)
//   exclusion_scenario = simulate_exclusion: {applied_exclude_pnus, lost_area_sqm,
//      excluded_parcels[], after{gross_sqm, usable_confirmed_sqm…}, note}
//
// 검증: ①매트릭스(게이트 배지·면적·지목) ②usable 3계층 게이지(합=총면적·정직 라벨)
// ③검증 상태 배지(미수렴=측량 권고) ④시니어 카드(verdict 색·근거) ⑤혼재 §84 라벨+정직 고지
// ⑥데이터 부재 시 해당 섹션 완전 미표시(추정 렌더 금지) ⑦'확정 아님' 라벨 ⑧resolver 다위치 호환.

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import {
  MultiParcelAttributeMatrix,
  resolveMultiParcelReport,
  hasMultiParcelAttributeData,
  type MultiParcelReportLike,
  type MatrixParcelLike,
} from "@/components/projects/MultiParcelAttributeMatrix";

// ── 백엔드 순수모듈 실제 반환 구조와 1:1 픽스처 ──

const usableArea = {
  parcel_count: 5,
  gross_sqm: 1000,
  usable_confirmed_sqm: 600,
  usable_conditional_sqm: 250,
  excluded_sqm: 150,
  share: { confirmed_pct: 60.0, conditional_pct: 25.0, excluded_pct: 15.0 },
  confirmed_parcels: [],
  conditional_parcels: [],
  excluded_parcels: [
    {
      index: 2, pnu: "4115010100100030000", land_category: "도로", area_sqm: 150,
      developability: "POSSIBLE", resolvable: "YES",
      reasons: [{
        code: "non_buildable_land_category",
        detail: "지목 '도로'은(는) 건축 불가 지목으로 사용가능 면적에서 전액 제외했습니다(임의 감보 계수 미적용). 용도폐지·합필 시 포함 가능성은 관할 지자체 확인이 필요합니다.",
      }],
    },
  ],
  area_unknown_parcels: [],
  basis: "지목(도로·구거·하천 전액 제외)·developability 게이트 기반 3계층 면적 정산",
  honest_notes: [
    "정밀 감보율(도로개설·기부채납·환지 감보 등)은 사업계획 확정 전에는 산정할 수 없어 미적용했습니다 — 실제 사용가능 면적은 이 수치보다 줄어들 수 있습니다.",
  ],
  warnings: [],
};

const areaVerification = {
  parcel_count: 5,
  consistent_count: 4,
  discrepancy_count: 1,
  insufficient_count: 0,
  all_consistent: false,
  per_parcel: [
    { index: 0, pnu: "4115010100100010000", status: "consistent" },
    {
      index: 1, pnu: "4115010100100020000", status: "discrepancy",
      recommendation: "면적 신호 간 괴리가 임계(10%)를 초과 — 지적측량(경계·면적 확정측량)으로 확인을 권고합니다.",
    },
  ],
  policy: { discrepancy_threshold_pct: 10, auto_correction: false },
};

const seniorReview = [
  {
    rule_id: "assembly.blocked_share", label: "차단면적 비중", value: 15.0, unit: "%",
    verdict: "PASS", threshold: ">30% WARN · >50% BLOCK",
    basis: "내부 리뷰 기준(실무 보수 원칙) — 법정 기준 아님",
    detail: "차단 150.0㎡ / 전체 1,000.0㎡ = 15.0%",
  },
  {
    rule_id: "assembly.area_verification", label: "면적 검증 수렴", value: 1, unit: "필지",
    verdict: "WARN", threshold: "미수렴 0필지",
    basis: "내부 리뷰 기준(실무 보수 원칙) — 법정 기준 아님",
    detail: "면적 3원 교차검증 미수렴 1필지 — 지적측량 확인 권고",
  },
];

const straddleRuling = {
  applied_rule: "가중평균+과반",
  threshold_sqm: 330,
  honest_note: "걸침 부분이 330㎡ 이하 — 건폐율·용적률은 면적가중평균, 그 밖의 규정은 넓은 부분을 적용합니다(확정은 허가권자 판단).",
};

const exclusionScenario = {
  requested_exclude_pnus: ["4115010100100030000"],
  applied_exclude_pnus: ["4115010100100030000"],
  not_found_pnus: [],
  excluded_parcels: [{ index: 2, pnu: "4115010100100030000", land_category: "도로", area_sqm: 150 }],
  lost_area_sqm: 150,
  after: { gross_sqm: 850, usable_confirmed_sqm: 600, usable_conditional_sqm: 250, excluded_sqm: 0 },
  note: "면적 3계층 재정산 비교표(순수 산출)",
};

const fullReport: MultiParcelReportLike = {
  usable_area: usableArea,
  area_verification: areaVerification,
  senior_review: seniorReview,
  zone_straddle_ruling: straddleRuling,
  exclusion_scenario: exclusionScenario,
};

const perParcel: MatrixParcelLike[] = [
  {
    pnu: "4115010100100010000", address: "경기 수원시 A동 1", area_sqm: 400,
    zone_type: "제2종일반주거지역", land_category: "대",
    special_parcel: null,
  },
  {
    pnu: "4115010100100020000", address: "경기 수원시 A동 2", area_sqm: 250,
    zone_type: "제2종일반주거지역", land_category: "임야",
    special_parcel: { developability: "NEEDS_OFFICIAL_SURVEY", label: "임야(산지)" },
  },
  {
    pnu: "4115010100100030000", address: "경기 수원시 A동 3", area_sqm: 150,
    zone_type: "제2종일반주거지역", land_category: "도로",
    special_parcel: { developability: "BLOCKED", label: "도로" },
  },
  {
    pnu: "4115010100100040000", address: "경기 수원시 A동 4", area_sqm: null,
    zone_type: null, land_category: null,
    special_parcel: null,
  },
];

describe("resolveMultiParcelReport — 응답 다위치 호환 가드", () => {
  it("top-level 키에서 계약 필드를 수집한다", () => {
    const r = resolveMultiParcelReport({ usable_area: usableArea, senior_review: seniorReview });
    expect(r).not.toBeNull();
    expect(r!.usable_area).toBe(usableArea);
    expect(r!.senior_review).toBe(seniorReview);
  });

  it("multi_parcel_report 중첩에서도 수집한다(top-level 우선)", () => {
    const r = resolveMultiParcelReport({
      multi_parcel_report: { usable_area: usableArea, zone_straddle_ruling: straddleRuling },
    });
    expect(r).not.toBeNull();
    expect(r!.usable_area).toBe(usableArea);
    expect(r!.zone_straddle_ruling).toBe(straddleRuling);
  });

  it("aggregate.multi_parcel_report(배치 패널 형상)에서도 수집한다", () => {
    const r = resolveMultiParcelReport({
      aggregate: { multi_parcel_report: { area_verification: areaVerification } },
    });
    expect(r).not.toBeNull();
    expect(r!.area_verification).toBe(areaVerification);
  });

  it("계약 필드가 전혀 없으면 null(추정 생성 금지)", () => {
    expect(resolveMultiParcelReport({})).toBeNull();
    expect(resolveMultiParcelReport(null)).toBeNull();
    expect(resolveMultiParcelReport({ per_parcel: [], integrated: {} })).toBeNull();
    expect(hasMultiParcelAttributeData({})).toBe(false);
  });
});

describe("MultiParcelAttributeMatrix — 표시(전 계약 필드)", () => {
  it("필지×판정 매트릭스: 게이트 배지·면적·지목을 필지별로 표시한다", () => {
    render(<MultiParcelAttributeMatrix report={fullReport} perParcel={perParcel} />);
    const matrix = screen.getByTestId("mpx-matrix");
    // 주소·면적·지목
    expect(matrix.textContent).toContain("경기 수원시 A동 1");
    expect(matrix.textContent).toContain("400");
    expect(matrix.textContent).toContain("대");
    expect(matrix.textContent).toContain("임야");
    expect(matrix.textContent).toContain("도로");
    // 게이트 배지: 일상(POSSIBLE 기본)=가능 / NEEDS_OFFICIAL_SURVEY=공식조사 필요 / BLOCKED=차단
    expect(screen.getByTestId("mpx-gate-0").textContent).toContain("가능");
    expect(screen.getByTestId("mpx-gate-1").textContent).toContain("공식조사 필요");
    expect(screen.getByTestId("mpx-gate-2").textContent).toContain("차단");
    // 면적 미확보 필지 — 수치 날조 없이 '미상'
    expect(screen.getByTestId("mpx-area-3").textContent).toContain("미상");
    expect(matrix.textContent).not.toContain("NaN");
  });

  it("usable 3계층 게이지: 총면적·확정/조건부/제외 정산과 비중을 표시한다(합=총면적)", () => {
    render(<MultiParcelAttributeMatrix report={fullReport} perParcel={perParcel} />);
    const gauge = screen.getByTestId("mpx-usable");
    expect(gauge.textContent).toContain("1,000");    // gross
    expect(gauge.textContent).toContain("600");      // confirmed
    expect(gauge.textContent).toContain("250");      // conditional
    expect(gauge.textContent).toContain("150");      // excluded
    expect(gauge.textContent).toContain("60");       // share pct
    // 제외 사유 명세(무날조 — 백엔드 원문)
    expect(screen.getByText(/건축 불가 지목으로 사용가능 면적에서 전액 제외/)).toBeInTheDocument();
    // honest_notes 원문 노출
    expect(screen.getByText(/정밀 감보율.*미적용했습니다/)).toBeInTheDocument();
  });

  it("검증 상태 배지: 미수렴 필지 수 + 지적측량 권고를 정직 표기한다", () => {
    render(<MultiParcelAttributeMatrix report={fullReport} perParcel={perParcel} />);
    const verif = screen.getByTestId("mpx-verification");
    expect(verif.textContent).toContain("미수렴 1필지");
    expect(verif.textContent).toContain("지적측량");
    // 괴리 필지의 권고 원문
    expect(screen.getByText(/괴리가 임계\(10%\)를 초과/)).toBeInTheDocument();
  });

  it("전 필지 정합이면 정합 배지를 표시한다", () => {
    render(
      <MultiParcelAttributeMatrix
        report={{ area_verification: { ...areaVerification, all_consistent: true, discrepancy_count: 0, per_parcel: [] } }}
      />,
    );
    expect(screen.getByTestId("mpx-verification").textContent).toContain("정합");
  });

  it("시니어 카드: rule별 verdict 배지·근거(basis)·산식(detail)을 표시한다", () => {
    render(<MultiParcelAttributeMatrix report={fullReport} perParcel={perParcel} />);
    const senior = screen.getByTestId("mpx-senior");
    expect(senior.textContent).toContain("차단면적 비중");
    expect(senior.textContent).toContain("면적 검증 수렴");
    expect(screen.getByTestId("mpx-senior-verdict-assembly.blocked_share").textContent).toContain("통과");
    expect(screen.getByTestId("mpx-senior-verdict-assembly.area_verification").textContent).toContain("경고");
    // 근거의 정직 성격(법정 기준 아님) 원문 노출
    expect(senior.textContent).toContain("내부 리뷰 기준(실무 보수 원칙) — 법정 기준 아님");
    expect(senior.textContent).toContain("차단 150.0㎡ / 전체 1,000.0㎡ = 15.0%");
  });

  it("혼재(걸침) 판정: 국토계획법 제84조 라벨 + applied_rule + 정직 고지를 표시한다", () => {
    render(<MultiParcelAttributeMatrix report={fullReport} perParcel={perParcel} />);
    const straddle = screen.getByTestId("mpx-straddle");
    expect(straddle.textContent).toContain("제84조");
    expect(straddle.textContent).toContain("가중평균+과반");
    expect(straddle.textContent).toContain("확정은 허가권자 판단");
  });

  it("제외 시나리오: 상실 면적·제외 후 정산을 표시한다", () => {
    render(<MultiParcelAttributeMatrix report={fullReport} perParcel={perParcel} />);
    const excl = screen.getByTestId("mpx-exclusion");
    expect(excl.textContent).toContain("150");   // lost_area_sqm
    expect(excl.textContent).toContain("850");   // after.gross_sqm
  });

  it("정직 라벨: 조건부 계층·시나리오에 '확정 아님'이 동반된다", () => {
    render(<MultiParcelAttributeMatrix report={fullReport} perParcel={perParcel} />);
    expect(screen.getAllByText(/확정 아님/).length).toBeGreaterThan(0);
  });
});

describe("MultiParcelAttributeMatrix — 데이터 부재 시 미표시(추정 렌더 금지)", () => {
  it("report가 비면 아무것도 렌더하지 않는다", () => {
    const { container } = render(<MultiParcelAttributeMatrix report={{}} />);
    expect(container.firstChild).toBeNull();
  });

  it("usable_area만 있으면 다른 섹션은 미표시", () => {
    render(<MultiParcelAttributeMatrix report={{ usable_area: usableArea }} />);
    expect(screen.getByTestId("mpx-usable")).toBeInTheDocument();
    expect(screen.queryByTestId("mpx-verification")).toBeNull();
    expect(screen.queryByTestId("mpx-senior")).toBeNull();
    expect(screen.queryByTestId("mpx-straddle")).toBeNull();
    expect(screen.queryByTestId("mpx-exclusion")).toBeNull();
  });

  it("usable_area의 gross_sqm이 없으면 게이지 미표시(수치 추정 금지)", () => {
    render(
      <MultiParcelAttributeMatrix
        report={{ usable_area: { honest_notes: ["x"] }, senior_review: seniorReview }}
      />,
    );
    expect(screen.queryByTestId("mpx-usable")).toBeNull();
    expect(screen.getByTestId("mpx-senior")).toBeInTheDocument();
  });

  it("perParcel과 report.matrix가 모두 없으면 매트릭스 미표시", () => {
    render(<MultiParcelAttributeMatrix report={{ usable_area: usableArea }} />);
    expect(screen.queryByTestId("mpx-matrix")).toBeNull();
  });

  it("senior_review가 빈 배열이면 시니어 카드 미표시", () => {
    render(<MultiParcelAttributeMatrix report={{ senior_review: [], usable_area: usableArea }} />);
    expect(screen.queryByTestId("mpx-senior")).toBeNull();
  });

  it("조회 실패(status!=='ok') 필지는 '가능'으로 과대표시하지 않고 '판정 불가'를 표기한다", () => {
    render(
      <MultiParcelAttributeMatrix
        report={{ usable_area: usableArea }}
        perParcel={[{ pnu: "9", address: "서울 C동 9", area_sqm: 100, land_category: "대", special_parcel: null, status: "error", reason: "조회 실패" }]}
      />,
    );
    const gate = screen.getByTestId("mpx-gate-0");
    expect(gate.textContent).toContain("판정 불가");
    expect(gate.textContent).not.toContain("가능");
  });

  it("report.matrix 행이 있으면 perParcel 없이도 매트릭스를 그린다(D 계약 대비)", () => {
    render(
      <MultiParcelAttributeMatrix
        report={{
          matrix: [
            { pnu: "1", address: "서울 B동 10", area_sqm: 330, land_category: "대", developability: "CONDITIONAL" },
          ],
        }}
      />,
    );
    const matrix = screen.getByTestId("mpx-matrix");
    expect(matrix.textContent).toContain("서울 B동 10");
    expect(matrix.textContent).toContain("330");
    expect(screen.getByTestId("mpx-gate-0").textContent).toContain("조건부");
  });
});
