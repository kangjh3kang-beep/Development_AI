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
  it("통합 IA 섹션 순서 + 게이팅", () => {
    expect(NAV.map((s) => s.id)).toEqual([
      "control",
      "projects",
      "market-acquisition",
      "design-center",
      "operations-center",
      "admin",
    ]);
    expect(NAV.find((s) => s.id === "operations-center")?.assetOpsOnly).toBe(true);
    expect(NAV.find((s) => s.id === "admin")?.adminOnly).toBe(true);
  });

  it("L2 그룹 신설 + L3 children('└' 흉내 제거)", () => {
    const projects = NAV.find((s) => s.id === "projects")!;
    const landRights = projects.items.find((n) => n.id === "land-rights");
    expect(landRights?.children?.map((c) => c.href)).toEqual([
      "/en/land-schedule", "/en/registry-analysis", "/en/desk-appraisal",
    ]);
    const business = projects.items.find((n) => n.id === "business-analysis");
    expect(business?.children?.map((c) => c.id)).toEqual(["investment", "cost"]);

    const marketAcquisition = NAV.find((s) => s.id === "market-acquisition")!;
    const marketSales = marketAcquisition.items.find((n) => n.id === "market-sales");
    expect(marketSales?.children?.map((c) => c.href)).toEqual([
      "/en/market-insights", "/en/sales-info",
    ]);
    const acquisition = marketAcquisition.items.find((n) => n.id === "acquisition");
    expect(acquisition?.children?.map((c) => c.href)).toEqual(["/en/auction", "/en/g2b"]);

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
    expect(activeGroupIds(NAV, path)).toContain("land-rights");
    expect(activeSectionIds(NAV, path)).toContain("projects");
  });

  it("L3 토지조서 활성 → 토지·권리 그룹·섹션 펼침", () => {
    const path = "/en/land-schedule";
    expect(activeGroupIds(NAV, path)).toContain("land-rights");
    expect(activeSectionIds(NAV, path)).toContain("projects");
  });

  it("획득 채널 활성 → 사업 획득 그룹·시장획득 섹션 펼침", () => {
    expect(activeSectionIds(NAV, "/en/g2b")).toEqual(["market-acquisition"]);
    expect(activeGroupIds(NAV, "/en/g2b")).toEqual(["acquisition"]);
  });

  it("nodeHasActive — 하위경로 포함", () => {
    expect(nodeHasActive(NAV[1].items[0], "/en/projects/abc")).toBe(true); // 프로젝트 관리
  });
});
