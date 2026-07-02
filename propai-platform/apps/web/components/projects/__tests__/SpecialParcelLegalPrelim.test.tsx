// 특이토지 법규 예비판정 UI — SpecialParcelLegalPrelim 컴포넌트 테스트(TDD).
//
// 백엔드 계약(apps/api/app/services/zoning/special_parcel.py — dict passthrough):
//   factor.forest_facts{평균경사도_pct·경사도_source·경사도_정확도한계·입목축적_per_ha…}
//   factor.preliminary_assessment{slope|stocking|*_skip_reason|disclaimer}
//   factor.charge_notice{charge_name·notice·formula·legal_ref_keys·estimate·estimate_note}
//
// 검증: ①경사도 예비판정(DEM값 vs 기준·라벨·근사치 캐비앗) ②입목축적 예비판정(비율·기준)
// ③부담금 고지(산식+verified 법령 링크·미검증은 무링크) ④'확정 아님·공식조사 필요' 정직 라벨
// ⑤데이터 부재 시 완전 미표시(무목업) ⑥skip 사유 정직 표기 ⑦추정액 포맷/미산출 고지.

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import {
  SpecialParcelLegalPrelim,
  hasLegalPrelimData,
  type SpecialParcelFactorLike,
} from "@/components/projects/SpecialParcelLegalPrelim";

// ── 백엔드 실제 반환 구조와 1:1 픽스처(_slope_preliminary/_stocking_preliminary/_augment_charge_disclosures) ──

function forestFactor(over: Partial<SpecialParcelFactorLike> = {}): SpecialParcelFactorLike {
  return {
    category: "임야(산지)",
    developability: "NEEDS_OFFICIAL_SURVEY",
    forest_facts: {
      평균경사도_pct: 38.4,
      경사도_source: "SRTM30_DEM",
      경사도_정확도한계: "30m DEM 근사 — 공식 평균경사도조사서 아님",
      입목축적_per_ha: 180,
      관할평균_입목축적_per_ha: 150,
    },
    preliminary_assessment: {
      slope: {
        judgment: "경계 — 공식조사 필수",
        value_pct: 38.4,
        value_deg: 21.0,
        criteria_deg: 25,
        criteria_pct: 46.63,
        criteria_source: "산지관리법 시행령 제20조 별표4 — 국가기준 평균경사도 25도 이하",
        formula: "%↔도 변환: pct = tan(도)×100",
        source: "SRTM30_DEM",
        caveats: ["지자체 조례가 더 엄격한 기준(예: 17.5도/20도)을 둘 수 있음 — 해당 지자체 조례 별도 확인 필요"],
        limitations: [
          "30m DEM 근사 — 공식 평균경사도조사서 아님(확정판정 불가 — 공식조사로만 확정)",
          "예비판정은 참고용이며 developability(NEEDS_OFFICIAL_SURVEY)를 변경하지 않음",
        ],
      },
      stocking: {
        judgment: "예비 적합 가능성",
        입목축적_비율_pct: 120.0,
        criteria: "관할 시군구 평균 입목축적의 150% 이하",
        formula: "비율 = 필지 입목축적(180㎥/ha) ÷ 관할평균(150㎥/ha) × 100 = 120%",
        limitations: ["API 조회값 — 공식 산림조사서 아님(확정판정 불가)"],
      },
      disclaimer:
        "예비판정(참고용) — 확정 아님. DEM·API 조회값은 공식 평균경사도조사서·산림조사서가 아니므로 developability(NEEDS_OFFICIAL_SURVEY)는 변경되지 않으며, 확정판정은 공식조사 확보 후에만 가능합니다.",
    },
    charge_notice: {
      charge_name: "대체산림자원조성비",
      notice: "산지전용허가 시 대체산림자원조성비가 부과됩니다(산지관리법 제19조 — (연도별 고시 단가 + 개별공시지가×1%) × 전용면적).",
      formula: "대체산림자원조성비 = (연도별 고시 단가[원/㎡] + 개별공시지가 × 1%) × 전용면적",
      legal_ref_keys: ["forest_replacement_charge"],
      estimate: null,
      estimate_note: "연도별 고시 단가(산림청 '대체산림자원조성비 부과기준' 고시) 미주입 — 추정액 미산출(산식만 고지, 무날조)",
    },
    legal_refs: [
      {
        key: "forest_replacement_charge",
        law_name: "산지관리법",
        article: "제19조",
        title: "대체산림자원조성비",
        url: "https://law.go.kr/법령/산지관리법/제19조",
        url_status: "verified",
      },
    ],
    ...over,
  };
}

describe("SpecialParcelLegalPrelim — 법규 예비판정 섹션", () => {
  it("경사도 예비판정: DEM값 vs 기준·판정 라벨·근사치 캐비앗을 표시한다", () => {
    render(<SpecialParcelLegalPrelim factors={[forestFactor()]} />);
    // 섹션 헤더
    expect(screen.getByText("법규 예비판정")).toBeInTheDocument();
    // 판정 라벨(3단 중 '경계')
    expect(screen.getByText("경계 — 공식조사 필수")).toBeInTheDocument();
    // DEM 측정값 vs 기준(도·%) 정량 대비
    const slopeLine = screen.getByTestId("prelim-slope-values");
    expect(slopeLine.textContent).toContain("38.4%");
    expect(slopeLine.textContent).toContain("21°");
    expect(slopeLine.textContent).toContain("25°");
    expect(slopeLine.textContent).toContain("46.63%");
    // 기준 출처 + 근사치 캐비앗(정직)
    expect(screen.getByText(/산지관리법 시행령 제20조 별표4/)).toBeInTheDocument();
    expect(screen.getByText(/30m DEM 근사 — 공식 평균경사도조사서 아님/)).toBeInTheDocument();
    // 조례 캐비앗
    expect(screen.getByText(/지자체 조례가 더 엄격한 기준/)).toBeInTheDocument();
  });

  it("입목축적 예비판정: 비율·기준·판정 라벨을 표시한다", () => {
    render(<SpecialParcelLegalPrelim factors={[forestFactor()]} />);
    expect(screen.getByText("예비 적합 가능성")).toBeInTheDocument();
    const stockingLine = screen.getByTestId("prelim-stocking-values");
    expect(stockingLine.textContent).toContain("120%");
    expect(stockingLine.textContent).toContain("관할 시군구 평균 입목축적의 150% 이하");
  });

  it("정직 라벨: '확정 아님 · 공식조사 필요' 배지와 disclaimer가 시각적으로 명확히 표시된다", () => {
    render(<SpecialParcelLegalPrelim factors={[forestFactor()]} />);
    const badge = screen.getByTestId("prelim-honest-badge");
    expect(badge.textContent).toContain("확정 아님");
    expect(badge.textContent).toContain("공식조사 필요");
    // developability 불변 고지(백엔드 disclaimer 원문)
    expect(screen.getByText(/확정판정은 공식조사 확보 후에만 가능합니다/)).toBeInTheDocument();
  });

  it("부담금 고지: 부담금명·산식·verified 법령 딥링크를 표시한다", () => {
    render(<SpecialParcelLegalPrelim factors={[forestFactor()]} />);
    expect(screen.getByText(/대체산림자원조성비가 부과됩니다/)).toBeInTheDocument();
    expect(
      screen.getByText(/대체산림자원조성비 = \(연도별 고시 단가\[원\/㎡\] \+ 개별공시지가 × 1%\) × 전용면적/),
    ).toBeInTheDocument();
    // verified 링크 → 클릭 가능한 law.go.kr 딥링크
    const link = screen.getByRole("link", { name: /산지관리법 제19조/ });
    expect(link).toHaveAttribute("href", "https://law.go.kr/법령/산지관리법/제19조");
    // 추정액 미산출 시 무날조 고지
    expect(screen.getByText(/추정액 미산출\(산식만 고지, 무날조\)/)).toBeInTheDocument();
  });

  it("부담금 추정액이 있으면 원화 포맷으로 표시한다(감면 미반영 고지 동반)", () => {
    const farm = forestFactor({
      category: "농지(전)",
      forest_facts: null,
      preliminary_assessment: null,
      charge_notice: {
        charge_name: "농지보전부담금",
        notice: "농지전용허가·협의 시 농지보전부담금이 부과됩니다(농지법 제38조 — 개별공시지가×30%, ㎡당 상한 50,000원).",
        formula: "농지보전부담금 = 개별공시지가 × 30% (㎡당 상한 50,000원) × 전용면적",
        legal_ref_keys: ["farmland_preservation_charge"],
        estimate: 12345678,
        estimate_note: "개별공시지가×30%(㎡당 상한 5만원)×전용면적 — 감면 미반영 추정치(확정 부과액 아님)",
      },
      legal_refs: [],
    });
    render(<SpecialParcelLegalPrelim factors={[farm]} />);
    expect(screen.getByText(/12,345,678원/)).toBeInTheDocument();
    expect(screen.getByText(/감면 미반영 추정치\(확정 부과액 아님\)/)).toBeInTheDocument();
  });

  it("부담금만 있는 요인(예비판정 없음)에는 '공식조사 필요' 배지를 표시하지 않고 부담금 안내 배지로 대체한다", () => {
    // 농지 등 공식 산림조사가 필요 없는 charge_notice-only 요인 — '공식조사 필요'는 오도.
    const farmOnly = forestFactor({
      category: "농지(전)",
      forest_facts: null,
      preliminary_assessment: null,
      charge_notice: {
        charge_name: "농지보전부담금",
        notice: "농지전용허가·협의 시 농지보전부담금이 부과됩니다(농지법 제38조).",
        formula: "농지보전부담금 = 개별공시지가 × 30% (㎡당 상한 50,000원) × 전용면적",
        legal_ref_keys: ["farmland_preservation_charge"],
        estimate: 12345678,
        estimate_note: "감면 미반영 추정치(확정 부과액 아님)",
      },
      legal_refs: [],
    });
    render(<SpecialParcelLegalPrelim factors={[farmOnly]} />);
    const badge = screen.getByTestId("prelim-honest-badge");
    expect(badge.textContent).not.toContain("공식조사 필요");
    expect(badge.textContent).toContain("부담금 안내");
    expect(badge.textContent).toContain("확정 부과액 아님");
    // 하단 disclaimer도 공식조사 문구 대신 부담금 참고용 고지여야 함(오도 방지)
    expect(screen.queryByText(/공식조사\(평균경사도조사서·산림조사서 등\) 확보 후에만 가능합니다/)).toBeNull();
    expect(screen.getByText(/확정 부과액이 아니며/)).toBeInTheDocument();
  });

  it("예비판정 요인이 하나라도 있으면 '확정 아님 · 공식조사 필요' 배지를 유지한다(정직게이트 불변)", () => {
    // 예비판정(임야) + 부담금-only(농지) 혼재 — 공식조사 배지는 유지되어야 함.
    const farmOnly = forestFactor({
      category: "농지(전)",
      forest_facts: null,
      preliminary_assessment: null,
      charge_notice: {
        charge_name: "농지보전부담금",
        notice: "농지전용허가·협의 시 농지보전부담금이 부과됩니다.",
        formula: "농지보전부담금 = 개별공시지가 × 30% × 전용면적",
        legal_ref_keys: [],
        estimate: null,
        estimate_note: null,
      },
      legal_refs: [],
    });
    render(<SpecialParcelLegalPrelim factors={[forestFactor(), farmOnly]} />);
    const badge = screen.getByTestId("prelim-honest-badge");
    expect(badge.textContent).toContain("확정 아님");
    expect(badge.textContent).toContain("공식조사 필요");
  });

  it("미검증(legal_refs에 없는 키) 부담금 법령은 링크 없이 렌더한다(죽은 링크 금지)", () => {
    const f = forestFactor({ legal_refs: [] });
    render(<SpecialParcelLegalPrelim factors={[f]} />);
    // 부담금 고지는 있으나 링크는 없음
    expect(screen.getByText(/대체산림자원조성비가 부과됩니다/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /산지관리법 제19조/ })).toBeNull();
  });

  it("예비판정·부담금 데이터가 전부 없으면 아무것도 렌더하지 않는다(무목업)", () => {
    const plain: SpecialParcelFactorLike = {
      category: "학교용지",
      developability: "PRECONDITION",
    };
    const { container } = render(<SpecialParcelLegalPrelim factors={[plain]} />);
    expect(container.firstChild).toBeNull();
    expect(hasLegalPrelimData([plain])).toBe(false);
    expect(hasLegalPrelimData([forestFactor()])).toBe(true);
    expect(hasLegalPrelimData(undefined)).toBe(false);
    expect(hasLegalPrelimData(["문자열요인"])).toBe(false);
  });

  it("값 미확보 skip 사유를 정직하게 표시한다(경사도/입목축적 각각)", () => {
    const f = forestFactor({
      preliminary_assessment: {
        slope: null,
        stocking: null,
        slope_skip_reason: "평균경사도(DEM terrain_facts) 미확보 — 경사도 예비판정 생략(무날조)",
        stocking_skip_reason: "산림청 데이터(forest_data) 미확보 — 별표4 150% 비교 생략(무날조)",
        disclaimer: "예비판정(참고용) — 확정 아님.",
      },
      charge_notice: null,
      legal_refs: [],
    });
    render(<SpecialParcelLegalPrelim factors={[f]} />);
    expect(screen.getByText(/경사도 예비판정 생략\(무날조\)/)).toBeInTheDocument();
    expect(screen.getByText(/별표4 150% 비교 생략\(무날조\)/)).toBeInTheDocument();
  });

  it("초과 판정은 위험 톤으로 구분 표시한다(대체부지 검토 권고 문구 보존)", () => {
    const f = forestFactor({
      preliminary_assessment: {
        slope: {
          judgment: "예비 초과 — 부적합 가능성 높음(대체부지 검토 권고)",
          value_pct: 60.1,
          value_deg: 31.0,
          criteria_deg: 25,
          criteria_pct: 46.63,
          criteria_source: "산지관리법 시행령 제20조 별표4 — 국가기준 평균경사도 25도 이하",
          caveats: [],
          limitations: [],
        },
        stocking: null,
        disclaimer: "예비판정(참고용) — 확정 아님.",
      },
      charge_notice: null,
      legal_refs: [],
    });
    render(<SpecialParcelLegalPrelim factors={[f]} />);
    const judgment = screen.getByText("예비 초과 — 부적합 가능성 높음(대체부지 검토 권고)");
    expect(judgment).toBeInTheDocument();
    expect(judgment.getAttribute("data-tone")).toBe("error");
  });
});
