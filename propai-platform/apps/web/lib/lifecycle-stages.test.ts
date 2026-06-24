import { describe, it, expect } from "vitest";
import { isHrefActive } from "@/components/layout/nav-config";
import { PROJECT_TOOLS, projectToolHref, STAGE_META } from "./lifecycle-stages";

describe("PROJECT_TOOLS — 프로젝트 도구 인덱스 SSOT", () => {
  it("고아 도구 8종 — route 유일 + 라벨/아이콘 비어있지 않음", () => {
    expect(PROJECT_TOOLS).toHaveLength(8);
    const routes = PROJECT_TOOLS.map((t) => t.route);
    expect(new Set(routes).size).toBe(routes.length); // 중복 없음
    for (const t of PROJECT_TOOLS) {
      expect(t.route).toMatch(/^[a-z-]+$/); // 라우트 세그먼트 형식
      expect(t.label.length).toBeGreaterThan(0);
      expect(t.icon).toMatch(/^tool_/); // StageIcon tool_* 키
    }
  });

  it("STAGE_META(11단계) 라우트와 겹치지 않음 — 진짜 고아·additive", () => {
    const stageRoutes = new Set(Object.values(STAGE_META).map((m) => m.route));
    for (const t of PROJECT_TOOLS) {
      expect(stageRoutes.has(t.route)).toBe(false);
    }
  });

  it("기대 라우트 집합(회귀 고정)", () => {
    expect(PROJECT_TOOLS.map((t) => t.route)).toEqual([
      "canvas",
      "cad",
      "collaboration",
      "cost",
      "boq",
      "multi-parcel",
      "blockchain",
      "agent",
    ]);
  });
});

describe("projectToolHref + 활성판정", () => {
  it("프로젝트 상세 하위 절대경로 빌더", () => {
    expect(projectToolHref("ko", "p1", "cad")).toBe("/ko/projects/p1/cad");
    expect(projectToolHref("en", "abc", "collaboration")).toBe("/en/projects/abc/collaboration");
  });

  it("isHrefActive 재사용 — 현재 도구만 활성(하위경로 포함)", () => {
    const href = projectToolHref("ko", "p1", "collaboration");
    expect(isHrefActive(href, "/ko/projects/p1/collaboration")).toBe(true);
    expect(isHrefActive(href, "/ko/projects/p1/collaboration/room-9")).toBe(true); // 하위경로 활성
    expect(isHrefActive(href, "/ko/projects/p1/cad")).toBe(false); // 다른 도구 비활성
    expect(isHrefActive(href, "/ko/projects/p1")).toBe(false); // 개요(루트) 비활성
  });
});
