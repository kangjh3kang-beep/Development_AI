/**
 * 개발가능성 라벨 SSOT — 원시 코드가 화면으로 새지 않는다.
 *
 * ★왜(2026-08-05 R2 MEDIUM 실측): 소비처 여러 곳이 `DEVELOPABILITY_LABEL[code] ?? code` 로
 *   맵을 직접 뒤졌다. 지금은 맵이 등급 전부를 덮어 누수가 없지만 **등급이 하나만 늘어도
 *   여러 화면이 동시에 원시 코드를 뿌린다.** 그 미래 시점을 지금 잠근다.
 *
 * ※보고는 "7곳이 SSOT를 우회한다"였으나 실측하니 **원시 코드가 새는 곳은 4곳**이고,
 *   나머지 3곳은 severity_label(백엔드가 준 더 구체적인 한국어)로 폴백해 이미 안전하다.
 *   그 3곳은 바꾸면 오히려 덜 구체적인 문구가 되므로 건드리지 않았다.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { DEVELOPABILITY_LABEL, developabilityLabel, developabilityText } from "@/lib/zoning-ssot";

describe("developabilityText", () => {
  it("등재된 등급은 한국어 라벨 그대로", () => {
    expect(developabilityText("POSSIBLE")).toBe(DEVELOPABILITY_LABEL.POSSIBLE);
    expect(developabilityText("UNKNOWN")).toBe(DEVELOPABILITY_LABEL.UNKNOWN);
  });

  it("★미등재 등급은 원시 코드만 던지지 않는다 — 설명이 없다는 사실을 함께 말한다", () => {
    const got = developabilityText("FUTURE_GRADE_X");
    expect(got).toContain("FUTURE_GRADE_X");
    expect(got).toContain("설명 준비 중");
    // 원시 코드 '그것뿐'이면 안 된다(종전 `?? code` 동작).
    expect(got).not.toBe("FUTURE_GRADE_X");
  });

  it("이름을 지어내지 않는다 — 모르는 코드에 그럴듯한 한국어를 붙이지 않는다", () => {
    expect(developabilityText("FUTURE_GRADE_X")).not.toMatch(/가능|불가|필요|제한/);
  });

  it("빈 값은 빈 문자열 — 소비처의 조건부 렌더가 종전대로 동작한다", () => {
    expect(developabilityText(null)).toBe("");
    expect(developabilityText(undefined)).toBe("");
    expect(developabilityText("   ")).toBe("");
  });

  it("소문자·공백 입력도 정규화한다", () => {
    expect(developabilityText("  possible ")).toBe(DEVELOPABILITY_LABEL.POSSIBLE);
  });

  it("developabilityLabel과 판정이 어긋나지 않는다", () => {
    for (const code of Object.keys(DEVELOPABILITY_LABEL)) {
      const { text, known } = developabilityLabel(code);
      expect(known).toBe(true);
      expect(developabilityText(code)).toBe(text);
    }
  });
});

describe("배선 — 원시 맵 직접 색인이 되살아나지 않는다", () => {
  // ★대상은 '원시 코드로 폴백하던' 4곳. severity_label 폴백을 가진 3곳은 제외한다
  //   (그쪽은 맵을 직접 봐도 원시 코드가 새지 않는다 — 과도스코프 방지).
  const FILES = [
    "components/projects/ProjectAnalysisSummary.tsx",
    "components/projects/SiteInitiator.tsx",
    "components/projects/LandIntelligencePanel.tsx",
  ];

  it("공허하지 않다 — 대상 파일들이 실제로 SSOT 헬퍼를 부른다", () => {
    let calls = 0;
    for (const f of FILES) {
      const src = readFileSync(resolve(process.cwd(), f), "utf-8");
      calls += (src.match(/developabilityText\(/g) ?? []).length;
    }
    // 호출 지점 4곳(요약 1·시드 1·목록 2). 임포트는 `(`가 없어 이 카운트에 안 잡힌다.
    expect(calls).toBe(4);
  });

  it("★`DEVELOPABILITY_LABEL[...] ?? 원시코드` 형태가 없다", () => {
    for (const f of FILES) {
      const src = readFileSync(resolve(process.cwd(), f), "utf-8");
      const code = src
        .split("\n")
        .map((l) => l.replace(/(^|[^:])\/\/.*$/, "$1"))
        .join("\n");
      expect(code).not.toMatch(/DEVELOPABILITY_LABEL\s*\[/);
    }
  });
});
