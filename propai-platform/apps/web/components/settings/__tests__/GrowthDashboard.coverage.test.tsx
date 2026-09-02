/**
 * 성장루프가 **「지금 판정할 수 없다」를 화면에 말하는가.**
 *
 * ★배경(라이브 실측 2026-08-27 · `propai-v002826-6dfbfd88`):
 *   fallback_rate      judged=0/2   (하한 10)  ← 판정 불가
 *   latency_regression judged=7/23  (하한 20)
 *   quality_drop       judged=0/0   (하한 5)   ← 대상 없음
 *
 * 조치 탐지기들이 조용한 이유가 *"문제가 없어서"* 가 아니라 *"표본이 하한에 못 미쳐서"*
 * 였는데, 그 사실은 **`metrics_json` 에는 있었고 화면에는 없었다.** 운영자는 open 3,188건을
 * 보면서 **폴백 탐지가 눈이 멀었다**는 것을 알 수 없었다.
 *
 * ★이 파일은 **판정 문구**만 잠근다. *"생산된 키가 그려지거나 면제되는가"* 는 백엔드
 * 파생형 락 `apps/api/tests/test_insight_metrics_key_coverage.py` 가 잠근다 —
 * 오라클을 `analyzer.py` 에 두어 프론트에서 동어반복이 되지 않게 나눴다.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { coverageRows, InsightMetrics } from "@/components/settings/GrowthDashboard";

const LIVE_COVERAGE = {
  fallback_rate: { judged: 0, total: 2, floor: 10 },
  latency_regression: { judged: 7, total: 23, floor: 20 },
  quality_drop: { judged: 0, total: 0, floor: 5 },
};

function insight(over: Record<string, unknown> = {}) {
  return {
    id: "t1",
    insight_type: "fallback_rate",
    severity: "critical",
    status: "open",
    narrative: "[critical] site_analysis 폴백률 76.19%",
    recommended_action: "heal",
    created_at: "2026-08-26T19:05:00Z",
    metrics_json: {
      service: "site_analysis",
      fallback_pct: 76.19,
      llm_call: 42,
      analysis_coverage: LIVE_COVERAGE,
      ...over,
    },
  } as never;
}

describe("coverageRows — 판정 커버리지 문구", () => {
  it("★공허한 참 방지 — 라이브 모양에서 행이 실제로 나온다", () => {
    const rows = coverageRows(LIVE_COVERAGE);
    expect(rows.length).toBe(3);
  });

  it("★두 모집단이 갈린다 — 판정 불가 · 부분 판정 · 대상 없음이 서로 다른 문구다", () => {
    const by = Object.fromEntries(coverageRows(LIVE_COVERAGE).map((r) => [r.label, r.value]));
    expect(by.fallback_rate).toContain("판정 불가");
    expect(by.latency_regression).not.toContain("판정 불가");
    expect(by.quality_drop).toContain("대상 없음");
    // 셋이 서로 달라야 구별된다(같은 문구면 화면이 상태를 못 가른다).
    expect(new Set(Object.values(by)).size).toBe(3);
  });

  it("모수와 하한을 함께 적는다 — 「judged=N」이 「N건이 옳다」로 읽히면 안 된다", () => {
    const by = Object.fromEntries(coverageRows(LIVE_COVERAGE).map((r) => [r.label, r.value]));
    expect(by.fallback_rate).toContain("2"); // 모수
    expect(by.fallback_rate).toContain("10"); // 하한
    expect(by.latency_regression).toContain("7/23");
    expect(by.latency_regression).toContain("20");
  });

  it("망가진 입력에 던지지 않고 조용히 빈 배열을 준다", () => {
    for (const v of [null, undefined, 3, "x", [], {}, { a: 1 }, { a: { judged: "x" } }]) {
      expect(() => coverageRows(v)).not.toThrow();
      expect(Array.isArray(coverageRows(v))).toBe(true);
    }
    expect(coverageRows({ a: { judged: 1 } })).toHaveLength(0); // total 없으면 스킵
  });
});

describe("InsightMetrics — 커버리지가 실제로 렌더된다", () => {
  it("★배선 — 판정 불가 축이 화면에 나온다(헬퍼 존재로는 부족하다)", () => {
    render(<InsightMetrics insight={insight()} />);
    expect(screen.getByText(/판정 fallback_rate/)).toBeTruthy();
    expect(screen.getByText(/판정 불가/)).toBeTruthy();
  });

  it("★타입을 몰라야 한다 — 커버리지는 switch 밖이라 어느 타입에서도 나온다", () => {
    // analyzer 가 커버리지를 **전 타입에** 박은 이유가 "타입별 손수 분기는 새 타입을
    // 자동으로 누락시킨다" 이므로, 소비 쪽도 타입을 몰라야 한다.
    const { container } = render(
      <InsightMetrics insight={insight({ __t: 1 }) as never} />,
    );
    expect(container.textContent).toContain("판정 latency_regression");
    for (const t of ["error_cluster", "quality_drop", "latency_baseline", "정체불명타입"]) {
      const r = render(
        <InsightMetrics
          insight={{ ...(insight() as unknown as Record<string, unknown>), insight_type: t } as never}
        />,
      );
      expect(r.container.textContent, `${t} 에서 커버리지가 사라졌다`).toContain("판정 불가");
      r.unmount();
    }
  });

  it("★음성 대조군 — 커버리지가 없으면 그 행도 없다(항상 찍히는 상수 행 금지)", () => {
    const { container } = render(
      <InsightMetrics insight={insight({ analysis_coverage: undefined })} />,
    );
    expect(container.textContent).not.toContain("판정 불가");
    expect(container.textContent).not.toContain("판정 fallback_rate");
    // 그래도 원래 행들은 남아야 한다(전부 사라지면 위 단언이 공허해진다).
    expect(container.textContent).toContain("폴백률");
  });

  it("recurring_verify_error 에 **그중 심각**이 나온다(주석이 계약으로 열거한 키)", () => {
    const { container } = render(
      <InsightMetrics
        insight={
          {
            ...(insight() as unknown as Record<string, unknown>),
            insight_type: "recurring_verify_error",
            metrics_json: {
              service: "site_analysis",
              issue_type: "계산오류",
              per_hour: 18,
              count: 18,
              high_count: 18,
            },
          } as never
        }
      />,
    );
    expect(container.textContent).toContain("그중 심각");
    expect(container.textContent).toContain("18");
  });
});
