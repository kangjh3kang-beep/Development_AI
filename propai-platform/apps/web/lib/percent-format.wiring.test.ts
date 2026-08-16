/**
 * 배선 불변식 — 종합분석 패널의 비율 표기가 포매터를 **거치는지**.
 *
 * ★행위 테스트만으로 부족한 이유: 포매터가 아무리 옳아도 화면이 그걸 안 부르면 원시 float가
 *   그대로 나간다. 실제로 #530은 §1에 포매터를 넣고 **같은 카드의 §1-B는 빠뜨려**, 한 카드
 *   안에서 `152.8%` 와 `152.83333333333334%` 가 같이 떴다. 그래서 소스 층을 따로 잠근다.
 *
 * ★필드 단위 단언으로는 못 잡는다 — 갈린 쪽은 Field가 아니라 **문장 보간**이었다.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { __stripCommentsForScan } from "@/lib/source-invariant";

const PANEL = "components/analysis/ComprehensiveAnalysisPanel.tsx";
const src = readFileSync(resolve(process.cwd(), PANEL), "utf-8");

/** ★2026-08-16 — 손수 만든 스트리퍼는 **단일행 `/* … *​/` 를 못 벗긴다**.
 *  스트립 규칙이 파일마다 갈리면 약한 쪽만 뚫린다 — 공용 도구로 일원화한다. */
const code = __stripCommentsForScan(src, PANEL);

describe("종합분석 패널 — 비율 표기 배선", () => {
  it("검사가 공허하지 않다 — 포매터 호출이 실제로 다수 존재한다", () => {
    const calls = code.match(/formatPercent(Delta|Range)?\(/g) ?? [];
    expect(calls.length).toBeGreaterThanOrEqual(10);
  });

  it("★§1-B 상한이 같은 카드에서 두 표기로 갈리지 않는다", () => {
    // 종전: Field는 formatPercent(capFar), 문장은 {capFar}% → 152.8% vs 152.83333333333334%
    expect(code).not.toMatch(/\{capFar\}%/);
    expect(code).not.toMatch(/\{structuralCapPct\}%/);
    const capFormatted = code.match(/formatPercent\(capFar\)/g) ?? [];
    expect(capFormatted.length).toBeGreaterThanOrEqual(2); // Field + 문장 둘 다
  });

  it("★시나리오 표의 비율 3칸이 원시 보간으로 되돌아가지 않는다", () => {
    expect(code).not.toMatch(/\{sc\.achieved_far\}%/);
    expect(code).not.toMatch(/\+\{sc\.total_incentive\}%/);
    // 0과 미확보를 같은 "-"로 합치던 형태
    expect(code).not.toMatch(/sc\.donation_pct\s*>\s*0\s*\?/);
  });

  it("비율 필드에 원시 보간이 남아 있지 않다(이 패널 한정 — 전역 스윕은 percent-sweep.wiring)", () => {
    // {…far}% · {…pct}% · {…percent}% 형태의 직접 보간
    const raw = code.match(/\{[^{}]*(?:far|Far|pct|Pct|percent|Percent)[^{}]*\}%/g) ?? [];
    expect(raw).toEqual([]);
  });
});
