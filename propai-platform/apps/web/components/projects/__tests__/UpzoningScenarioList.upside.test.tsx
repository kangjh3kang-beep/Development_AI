/**
 * 종상향 카드 — **상향 여지를 용도지역과 함께** 보인다.
 *
 * 【배경(2026-08-19 실측)】백엔드가 상·하한을 후보 합집합에서 내면서 `target_zone` 라벨과
 * 어긋났다(2종이라 써 놓고 3종 상한 300%). 교정으로 최상위는 라벨된 용도지역 범위로
 * 되돌리고, 상향 여지는 `upside_far_*` 로 **자기 라벨과 함께** 낸다.
 *
 * 【이 파일이 잠그는 것 — 표면층】
 * 백엔드가 정직해져도 **화면이 안 읽으면 사용자 불만이 되살아난다**(#700 의 발단:
 * "어떤 경로도 150%를 못 넘는다"). 실제로 `target_zone_candidates`·`target_zone_max` 는
 * 프론트 소비처가 **0** 이었다 — 그래서 새 필드는 소비처와 같은 커밋에 잠근다.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { UpzoningScenarioList } from "@/components/projects/UpzoningScenarioList";

const BASE = {
  path: "정비사업",
  target_zone: "제2종일반주거지역",
  expected_far_pct_low: 150,
  expected_far_pct_high: 250,
  expected_far_source: "국토계획법 시행령 법정 범위(목표지역 조례 확인 필요)",
  // ★실현가능성은 "상"/"중"이어야 카드가 펼쳐진 상태로 렌더된다(isHighFeasibility).
  //   "가능" 같은 값을 주면 컴포넌트가 **접힌 요약**만 그려 단언이 대상 없이 실패한다 —
  //   조건부 렌더는 그 상태를 만들어서 검사해야 한다(CLAUDE.md 회귀망 A.1).
  feasibility: "상",
};

describe("상향 여지 표시", () => {
  it("★더 높은 후보가 있으면 그 용도지역을 밝혀 보인다", () => {
    render(
      <UpzoningScenarioList
        scenarios={[{ ...BASE, upside_far_pct_high: 300, upside_far_zone: "제3종일반주거지역" }]}
      />
    );
    // 대표 범위(라벨과 정합)는 그대로 보인다.
    expect(screen.getByText(/예상 용적률/).textContent).toMatch(/150.*250/);
    // 그리고 상향 여지가 **용도지역과 함께** 보인다 — 숫자만 올리면 위법값이 된다.
    const upside = screen.getByText(/최대 제3종일반주거지역 상향 시/);
    expect(upside.textContent).toContain("300");
  });

  it("대조군(음성) — 상향 여지가 대표값과 같으면 줄을 만들지 않는다", () => {
    render(
      <UpzoningScenarioList
        scenarios={[{ ...BASE, upside_far_pct_high: 250, upside_far_zone: "제2종일반주거지역" }]}
      />
    );
    // 공허 진리 가드 — 카드 자체는 렌더됐는가.
    expect(screen.getByText(/예상 용적률/).textContent).toMatch(/150.*250/);
    expect(screen.queryByText(/상향 시/)).toBeNull();
  });

  it("대조군(음성) — 필드가 없으면(구버전 응답) 아무것도 깨지지 않는다", () => {
    render(<UpzoningScenarioList scenarios={[BASE]} />);
    expect(screen.getByText(/예상 용적률/).textContent).toMatch(/150.*250/);
    expect(screen.queryByText(/상향 시/)).toBeNull();
  });
});
