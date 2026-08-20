/**
 * 실효용적률 카드 — **조건부 완화 후보를 보이되 적용값으로 읽히지 않게**.
 *
 * 【배경】조례는 `용도지역 → 값 하나`가 아니라 **`용도지역 × 조건 → 값들`**이다
 * (오산시 자연녹지 = 6개 조). 백엔드가 `ordinance_conditional`(조례 조건부 매칭)과
 * `conditional_ceiling`(법 §75의3 조건부 법정상한)을 내지만, **화면이 읽지 않으면
 * 고친 것이 아니다** — 이 캠페인이 내내 고쳐 온 "정의만 하고 소비처 0"이 된다.
 *
 * 【이 파일이 잠그는 것 — 양쪽 다】
 * · 값이 **보인다**(숨기면 사용자가 완화 여지를 영영 모른다)
 * · 그런데 **적용값으로 읽히지 않는다**(적용값처럼 보이면 근거 없는 단정이 된다)
 * · 조건이 안 맞으면 **뜨지 않는다**(가드의 위양성 방지)
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { L3EnhancedCards } from "@/app/[locale]/(dashboard)/projects/[id]/site-analysis/page";

const BASE_EFF = {
  effective_far_pct: 100,
  effective_bcr_pct: 20,
  ordinance_confirmed: true,
  legal_min_far_pct: 50,
  legal_max_far_pct: 100,
};

function renderWith(effective_far: Record<string, unknown>) {
  render(
    <L3EnhancedCards
      l3Data={{ effective_far } as never}
      siteAnalysis={null}
    />
  );
}

describe("조건부 완화 후보 표시", () => {
  it("★조례 조건부 매칭이 조문·수치와 함께 보인다", () => {
    renderWith({
      ...BASE_EFF,
      ordinance_conditional: {
        applied: false,
        matched: [{ kind: "bcr", value: 30, article: "제50조", article_title: "성장관리방안 수립지역에서의 건폐율 완화", condition_key: "growth_management_plan" }],
        undecidable: [],
      },
    });
    const line = screen.getByText(/제50조/);
    expect(line.textContent).toContain("건폐율");
    expect(line.textContent).toContain("30%");
  });

  it("★★적용값으로 읽히지 않는다 — '적용값이 아닙니다'가 함께 나온다", () => {
    renderWith({
      ...BASE_EFF,
      ordinance_conditional: {
        applied: false,
        matched: [{ kind: "bcr", value: 30, article: "제50조", article_title: "성장관리방안" }],
        undecidable: [],
      },
    });
    expect(screen.getByText(/적용값이 아닙니다/)).toBeTruthy();
    // 그리고 최종 실효값은 여전히 조례·법정 기준값이다(후보가 승격되지 않았다).
    expect(screen.getByText(/최종 실효 용적률/)).toBeTruthy();
  });

  it("법 §75의3 조건부 법정상한 고지도 보인다", () => {
    renderWith({
      ...BASE_EFF,
      conditional_ceiling: {
        applied: false,
        bcr_ceiling_pct: 30,
        note: "성장관리계획구역이라 자연녹지지역의 법정 건폐율 상한이 30% 까지 열릴 수 있습니다",
      },
    });
    expect(screen.getByText(/열릴 수 있습니다/)).toBeTruthy();
  });

  it("판정 보류 건수를 정직하게 말한다", () => {
    renderWith({
      ...BASE_EFF,
      ordinance_conditional: {
        applied: false,
        matched: [],
        undecidable: [{ article: "제49조", why: "설계가 정해져야 판정 가능" }],
      },
    });
    const note = screen.getByText(/판정 보류/);
    expect(note.textContent).toContain("제49조");
  });

  it("★대조군(음성) — 조건부가 없으면 블록이 뜨지 않는다(가드 위양성 방지)", () => {
    renderWith(BASE_EFF);
    // 공허 진리 가드 — 카드 자체는 렌더됐는가.
    expect(screen.getByText(/최종 실효 용적률/)).toBeTruthy();
    expect(screen.queryByText(/적용값이 아닙니다/)).toBeNull();
  });
});
