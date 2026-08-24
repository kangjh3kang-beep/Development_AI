/**
 * ★헤더 근거에 **기준 시각(as-of)** 이 붙는가.
 *
 * ## 왜 (2026-08-24 라이브 증상)
 *
 * `e56fc2a0` 화면에서 헤더는 **자연녹지지역**이라 단정했는데, 같은 페이지의 용도별 구성은
 * 서버 판정으로 **제2종일반주거 91%** 를 보여 주고 있었다. 헤더 값은 **낡은 저장 스냅샷**에서
 * 왔고, 사용자에게는 **그것이 언제 것인지 알 방법이 없었다.**
 *
 * ★값이 **틀린 것**은 전제 감사(`#813`)가 잡는다. 여기서 고치는 것은
 *   **언제 것인지 말하지 않는 것**이다 — 둘은 다른 결함이다.
 *
 * ★설계 원칙
 *   · 새 UI 를 만들지 않는다(이미 있는 근거 표면을 재사용 — 레이아웃 위험 0)
 *   · **임의 임계(며칠이면 낡음)를 두지 않는다** — 낡음 판정은 사람이 한다. 시스템은 사실만 말한다
 *   · 값이 없으면 **아무것도 덧붙이지 않는다**(무목업 — 가짜 시각 금지)
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { withAsOf } from "@/lib/context-header";

const HERE = dirname(fileURLToPath(import.meta.url));
const HEADER = resolve(HERE, "../../components/common/ContextHeader.tsx");

describe("★기준 시각(as-of) — 근거가 '언제 것인지' 말한다", () => {
  it("탐지 — fetchedAt 이 있으면 근거에 날짜가 붙는다", () => {
    const out = withAsOf("부지분석 확정 용도지역", "2026-08-24T02:20:41.722Z");
    expect(out).toContain("부지분석 확정 용도지역");   // 원문 보존
    expect(out).toMatch(/\(\d{4}-\d{2}-\d{2} 기준\)/);
  });

  it("★특이도 — fetchedAt 이 없으면 **아무것도 덧붙이지 않는다**(가짜 시각 금지)", () => {
    // 두 모집단이 **다른 값**을 내야 잠금이다. 항상 덧붙이면 null 케이스가 무잠금이 된다.
    const base = "부지분석 확정 용도지역";
    expect(withAsOf(base, null)).toBe(base);
    expect(withAsOf(base, undefined)).toBe(base);
    expect(withAsOf(base, "")).toBe(base);
  });

  it("★특이도 — 파싱 불가한 값도 원문을 그대로 둔다(깨진 시각을 만들지 않는다)", () => {
    const base = "단일필지 대지면적";
    expect(withAsOf(base, "언제인지-모름")).toBe(base);
    expect(withAsOf(base, "not-a-date")).toBe(base);
  });

  it("근거가 비면 덧붙이지 않는다(빈 문자열에 시각만 남지 않게)", () => {
    expect(withAsOf("", "2026-08-24T00:00:00Z")).toBe("");
  });

  it("★배선 — ContextHeader 가 두 근거 모두에 실제로 적용한다", () => {
    // 주석·문자열이 아니라 **실행되는 줄**만 본다(주석 처리 변이에 뚫린 전례가 있다).
    const live = readFileSync(HEADER, "utf-8")
      .split("\n")
      .filter((ln) => ln.trim() && !ln.trim().startsWith("//") && !ln.trim().startsWith("*"))
      .join("\n");
    const uses = (live.match(/basis:\s*withAsOf\(/g) ?? []).length;
    expect(uses, "용도지역·대지면적 두 근거 모두에 적용돼야 한다").toBeGreaterThanOrEqual(2);
    expect(live, "파생값 fetchedAt 을 넘기지 않는다").toContain("data.fetchedAt");
  });

  it("★배선 — 파생 함수가 fetchedAt 을 실제로 내보낸다(소비처 0 방지)", () => {
    const src = readFileSync(resolve(HERE, "../context-header.ts"), "utf-8")
      .split("\n")
      .filter((ln) => ln.trim() && !ln.trim().startsWith("//") && !ln.trim().startsWith("*"))
      .join("\n");
    expect(src).toContain("fetchedAt:");
  });
});
