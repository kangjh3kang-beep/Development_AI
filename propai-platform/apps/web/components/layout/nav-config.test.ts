import { describe, it, expect } from "vitest";
import {
  buildPrimaryNav,
  isHrefActive,
  nodeHasActive,
  activeGroupIds,
  activeSectionIds,
} from "./nav-config";

const NAV = buildPrimaryNav("en");

describe("buildPrimaryNav", () => {
  it("6 섹션 순서 + 게이팅", () => {
    expect(NAV.map((s) => s.id)).toEqual([
      "review", "land-finance", "execution", "design", "asset-ops", "admin",
    ]);
    expect(NAV.find((s) => s.id === "asset-ops")?.assetOpsOnly).toBe(true);
    expect(NAV.find((s) => s.id === "admin")?.adminOnly).toBe(true);
  });

  it("L2 그룹 신설 + L3 children('└' 흉내 제거)", () => {
    const review = NAV[0];
    const marketSales = review.items.find((n) => n.id === "market-sales");
    expect(marketSales?.children?.map((c) => c.href)).toEqual([
      "/en/market-insights", "/en/sales-info",
    ]);
    const land = NAV[1].items.find((n) => n.id === "land-schedule");
    expect(land?.href).toBe("/en/land-schedule"); // 그룹이 자체 페이지도 가짐
    expect(land?.children?.map((c) => c.id)).toEqual([
      "registry-analysis", "desk-appraisal",
    ]);
    // 라벨에 '└' 문자 없음(진짜 계층)
    const allLabels = NAV.flatMap((s) => s.items).flatMap((n) => [n.label, ...(n.children ?? []).map((c) => c.label)]);
    expect(allLabels.some((l) => l.includes("└"))).toBe(false);
  });
});

describe("isHrefActive", () => {
  it("정확 일치/하위경로, 홈은 정확만", () => {
    expect(isHrefActive("/en/projects", "/en/projects")).toBe(true);
    expect(isHrefActive("/en/projects", "/en/projects/123")).toBe(true);
    expect(isHrefActive("/en", "/en/projects")).toBe(false); // 홈 접두 오활성 방지
    expect(isHrefActive("/en", "/en")).toBe(true);
    expect(isHrefActive(undefined, "/en")).toBe(false);
    expect(isHrefActive("/en/sales", "/en/sales-info")).toBe(false); // 부분문자열 오활성 방지
  });
});

describe("자동 펼침(activeGroupIds / activeSectionIds)", () => {
  it("L3 활성 → 부모 그룹·섹션 펼침", () => {
    const path = "/en/registry-analysis";
    expect(activeGroupIds(NAV, path)).toContain("land-schedule");
    expect(activeSectionIds(NAV, path)).toContain("land-finance");
  });

  it("L2 그룹 자체 페이지 활성 → 그룹·섹션 펼침", () => {
    const path = "/en/land-schedule";
    expect(activeGroupIds(NAV, path)).toContain("land-schedule");
    expect(activeSectionIds(NAV, path)).toContain("land-finance");
  });

  it("리프 활성 → 섹션만 펼침(그룹 펼침 없음)", () => {
    expect(activeSectionIds(NAV, "/en/g2b")).toEqual(["execution"]);
    expect(activeGroupIds(NAV, "/en/g2b")).toEqual([]);
  });

  it("nodeHasActive — 하위경로 포함", () => {
    expect(nodeHasActive(NAV[0].items[2], "/en/projects/abc")).toBe(true); // 프로젝트 관리
  });
});
