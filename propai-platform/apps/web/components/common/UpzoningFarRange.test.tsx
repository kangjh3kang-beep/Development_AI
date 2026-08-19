/**
 * 종상향 잠재 용적률 "범위 붕괴" 정직표기 락.
 *
 * 결함(실측): 대표 목표 용도지역 선정이 보수적이라 여러 경로가 같은 목표를 가리키면
 *   min_pct == max_pct 가 되고, 화면은 그것을 `예상 상한 150.0~150.0%` 라고 적었다.
 *   상·하한이 같은 숫자면 개발사는 "그 위는 안 된다"로 읽는다 — 실제 의미는
 *   "우리가 한 경로만 봤다"인데 그 한정이 화면 어디에도 없었다.
 *
 * ★이 파일이 태우는 것
 *   ① 렌더 — 붕괴/비붕괴 **두 모집단**이 실제로 다른 DOM 을 낸다(소스 grep 아님).
 *   ② 배선 — 세 화면이 그 공용 표면을 정말 거치는가(주석처리 변이에 뚫리지 않도록
 *     주석을 벗긴 소스에서 확인한다 — 이 저장소가 두 번 뚫린 자리다).
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { formatUpzoningFarRange, type UpzoningFarRange } from "@/lib/formatters";
import { assertWiredThrough } from "@/lib/source-invariant";
import { mapUpzoning } from "@/lib/zoning-ssot";

import { UpzoningFarRangeNotice, UpzoningFarRangeValue } from "./UpzoningFarRange";

// ── 두 모집단 — 실제 백엔드 산출과 동형(자연녹지 서울 = 붕괴 / 2종일반 역세권 = 진짜 범위) ──
const DISCLOSURE =
  "검토한 경로 3건의 예상 용적률 상한이 모두 150%로 같아 범위가 산출되지 않았습니다. " +
  "150%는 상향 가능한 최댓값이 아니라 본 분석이 검토한 경로의 예상치입니다.";

const COLLAPSED: UpzoningFarRange = {
  min_pct: 150, max_pct: 150, is_collapsed: true, honest_disclosure: DISCLOSURE,
};
const RANGED: UpzoningFarRange = {
  min_pct: 300, max_pct: 500, is_collapsed: false, honest_disclosure: null,
};

describe("formatUpzoningFarRange — 붕괴 판정은 계약에서 온다", () => {
  it("두 모집단이 실제로 다른 결과를 낸다(같은 결과면 배선을 끊어도 통과한다)", () => {
    const c = formatUpzoningFarRange(COLLAPSED);
    const r = formatUpzoningFarRange(RANGED);
    expect(c.collapsed).toBe(true);
    expect(r.collapsed).toBe(false);
    expect(c.text).not.toBe(r.text);
    expect(Boolean(c.disclosure)).not.toBe(Boolean(r.disclosure));
  });

  it("붕괴하면 범위 기호(~)를 쓰지 않고 '단일 경로 기준'을 함께 적는다", () => {
    const c = formatUpzoningFarRange(COLLAPSED);
    expect(c.text).toContain("150.0%");
    expect(c.text).not.toContain("~");      // ★`150.0~150.0%` 재발 차단
    expect(c.text).toContain("단일 경로 기준");
  });

  it("붕괴가 아니면 범위를 그대로 적는다(대조군 — 항상 붕괴로 적으면 이 검사가 공허해진다)", () => {
    expect(formatUpzoningFarRange(RANGED).text).toBe("300.0~500.0%");
  });

  it("판정은 백엔드 계약이 1순위 — 값이 같아도 is_collapsed:false 면 붕괴로 단정하지 않는다", () => {
    // 두 목표 용도지역의 조례 상한이 우연히 같아진 경우까지 프론트가 '구조적 붕괴'로
    // 단정하면 안 된다. 그 판정은 근거를 아는 백엔드만 한다.
    const coincidence = formatUpzoningFarRange(
      { min_pct: 400, max_pct: 400, is_collapsed: false, honest_disclosure: null },
    );
    expect(coincidence.collapsed).toBe(false);
  });

  it("계약 필드가 없는 구(舊) 페이로드는 '범위인 척'만 막고 고지는 지어내지 않는다", () => {
    const legacy = formatUpzoningFarRange({ min_pct: 150, max_pct: 150 });
    expect(legacy.collapsed).toBe(true);
    expect(legacy.text).not.toContain("~");
    expect(legacy.disclosure).toBeNull();   // ★근거 없는 문구를 프론트가 만들지 않는다
  });

  it("한쪽이라도 없으면 미확보(가짜 0 표기 금지)", () => {
    expect(formatUpzoningFarRange({ min_pct: null, max_pct: 150 }).text).toBe("미확보");
    expect(formatUpzoningFarRange(null).text).toBe("미확보");
  });
});

describe("UpzoningFarRange 공용 표면 — 렌더", () => {
  it("붕괴 시 값에 범위 기호가 없고, 정직 고지가 함께 렌더된다", () => {
    const { container } = render(
      <div>
        <UpzoningFarRangeValue range={COLLAPSED} />
        <UpzoningFarRangeNotice range={COLLAPSED} />
      </div>,
    );
    // 공허 진리 가드 — 아무것도 안 그려졌으면 아래 단언은 전부 무의미하다.
    expect((container.textContent ?? "").length).toBeGreaterThan(20);

    expect(screen.getByText(/150\.0%/)).toBeTruthy();
    expect(container.textContent).not.toContain("150.0~150.0");
    // 고지가 **실제 DOM 에** 있어야 한다(문구를 백엔드에서 받아 그대로 나른다).
    expect(container.textContent).toContain("최댓값이 아니라");
  });

  it("붕괴가 아니면 범위를 그대로 그리고, 고지는 아예 그리지 않는다(빈 껍데기 금지)", () => {
    const { container } = render(
      <div>
        <UpzoningFarRangeValue range={RANGED} />
        <UpzoningFarRangeNotice range={RANGED} />
      </div>,
    );
    expect((container.textContent ?? "").length).toBeGreaterThan(5);
    expect(container.textContent).toContain("300.0~500.0%");
    expect(container.querySelector("p")).toBeNull();   // 고지 <p> 자체가 없다
  });
});

describe("배선 — 세 화면이 공용 표면을 실제로 거친다", () => {
  // ★주석처리+임포트유지 변이에 뚫리지 않도록, assertWiredThrough 가 주석을 벗긴 소스를 본다.
  //   mustContain 은 scope 와 같다(동어반복) — 이 락의 무게는 **minMatches** 에 있다:
  //   렌더가 사라지면 매치 0건이 되어 실패한다. "고지가 화면에 남아 있는가"가 잠기는 지점.
  const SCREENS = [
    "components/analysis/ComprehensiveAnalysisPanel.tsx",
    "components/feasibility/AutoRecommendPanel.tsx",
    "app/[locale]/(dashboard)/projects/[id]/site-analysis/page.tsx",
  ];

  it.each(SCREENS)("%s — 정직 고지를 렌더한다", (file) => {
    assertWiredThrough({
      file,
      scope: /<UpzoningFarRangeNotice/,
      mustContain: /<UpzoningFarRangeNotice/,
      minMatches: 1,
    });
  });

  it.each(SCREENS)("%s — 범위 문자열을 스스로 만들지 않는다", (file) => {
    // 종상향 범위를 만지는 모든 줄이 직접 보간(`${min}~${max}`)·formatPercentRange·
    // min===max 자체판정을 쓰지 않는다. 하나라도 되살아나면 그 화면만 다시 거짓 범위를 찍는다.
    assertWiredThrough({
      file,
      scope: /potential_far_range|potentialRange/,
      mustContain: /potential_far_range|potentialRange/,
      mustNotContain: /formatPercentRange\s*\(|min_pct\s*===|min_pct\s*\}\s*~|~\s*\$\{/,
      minMatches: 2,
    });
  });
});

describe("mapUpzoning — 붕괴 신호가 store 까지 도달한다", () => {
  // (변이 검증에서 zoning-ssot 의 is_collapsed 추출이 무잠금이었다 — 이 신호가 끊기면
  //  ProjectAnalysisSummary 가 단일 경로 예상치를 계속 "도달 가능한 상한"이라 부른다.)
  it("두 모집단이 store 패치에서도 갈린다", () => {
    const collapsed = mapUpzoning({ upzoning: { potential_far_range: COLLAPSED } });
    const ranged = mapUpzoning({ upzoning: { potential_far_range: RANGED } });
    expect(collapsed.upzoningFarRangeCollapsed).toBe(true);
    expect(ranged.upzoningFarRangeCollapsed).toBe(false);
    // 숫자(상한)는 두 경로 모두 그대로 실린다 — 신호만 추가된 것이다.
    expect(collapsed.upzoningPotentialFarHigh).toBe(150);
    expect(ranged.upzoningPotentialFarHigh).toBe(500);
  });

  it("계약 필드가 없으면 null 로 남긴다(false 로 단정하지 않는다)", () => {
    // false 로 채우면 "확인 결과 붕괴 아님"이 되어, 미확보를 사실로 둔갑시킨다.
    const legacy = mapUpzoning({ upzoning: { potential_far_range: { min_pct: 150, max_pct: 150 } } });
    expect(legacy.upzoningFarRangeCollapsed).toBeNull();
  });

  it("종상향 미확보면 붕괴 신호도 명시적 null(직전 부지 잔류 차단)", () => {
    expect(mapUpzoning(null).upzoningFarRangeCollapsed).toBeNull();
  });
});

describe("아직 잠기지 않은 것(부채 — 초록 안에 보이게 남긴다)", () => {
  // ProjectAnalysisSummary 의 "종상향 잠재(용적·단일 경로)" 라벨·근거 교체는 store 전체와
  // apiClient 를 세워야 렌더된다. 현재는 pnpm type-check 만이 그 배선을 지킨다.
  it.todo("ProjectAnalysisSummary — 붕괴 시 라벨·근거가 '단일 경로'로 바뀌는지 렌더로 확인");
  // AutoRecommendPanel 문장의 조사 분기("…이며" vs "…까지 가능하며")도 같은 이유로 미잠금.
  it.todo("AutoRecommendPanel — 붕괴 시 '까지 가능하며'가 '이며'로 바뀌는지 렌더로 확인");
});
