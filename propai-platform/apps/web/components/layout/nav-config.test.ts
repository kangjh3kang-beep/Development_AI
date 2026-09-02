import { describe, it, expect } from "vitest";
import { PRIMARY_ROUTE_REGISTRY } from "@/lib/navigation/route-registry";
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
      "cost-mgmt",
      "market-acquisition",
      "design-center",
      "sales-management",
      "my",
      "admin",
    ]);
    // 분양 관리는 코어 워크플로우(개발→분양)라 역할 게이트 없음 — 일반 사용자에게 노출.
    expect(NAV.find((s) => s.id === "sales-management")?.assetOpsOnly).toBeUndefined();
    expect(NAV.find((s) => s.id === "admin")?.adminOnly).toBe(true);
    // 마이페이지 — 전 회원 노출(게이트 없음) + 코인·보안 등 6개 진입.
    const my = NAV.find((s) => s.id === "my");
    expect(my?.adminOnly).toBeUndefined();
    expect(my?.items.map((n) => n.href)).toEqual([
      "/en/mypage",
      "/en/mypage/coins",
      "/en/mypage/usage",
      "/en/mypage/profile",
      "/en/mypage/privacy",
      "/en/account",
    ]);
  });

  it("최신 main의 관제 동선과 프리페치 정책을 registry에서 전달", () => {
    const control = NAV.find((s) => s.id === "control")!;
    expect(control.items.map((n) => n.href)).toEqual([
      "/en", "/en/precheck", "/en/analysis", "/en/settings/team",
    ]);

    const designRefs = NAV.find((s) => s.id === "design-center")?.items.find((n) => n.id === "design-refs");
    const adminItems = NAV.find((s) => s.id === "admin")?.items ?? [];

    expect(designRefs?.prefetch).toBe(false);
    // ★사람이 센 목록(길이 4)을 쓰지 않는다 — 관리자 화면이 하나 늘 때마다 이 줄이 깨졌고,
    //   그 목록이 곧 상한이 되어 새 항목이 감시망 밖으로 밀려난다(CLAUDE.md §A.4).
    //   불변식은 "관리자 항목은 전부 프리페치하지 않는다"이므로 그것을 파생형으로 잠근다.
    // ★★개수도 **레지스트리에서 파생**한다(2026-08-19 적대리뷰): 손으로 적은 하한(>=4)은
    //   실제(5)보다 낮아 항목이 하나 사라져도 통과했다. 하한이 아니라 **일치**를 본다.
    const expectedAdmin = PRIMARY_ROUTE_REGISTRY.filter(
      (item) => item.sectionId === "admin" && item.status !== "hidden" && !item.parentId,
    );
    expect(expectedAdmin.length, "관리자 항목이 0개 — 아래 단언이 공허해진다").toBeGreaterThan(0);
    expect(adminItems.map((item) => item.id).sort()).toEqual(
      expectedAdmin.map((item) => item.id).sort(),
    );
    expect(adminItems.filter((item) => item.prefetch !== false)).toEqual([]);
  });

  it("L2 그룹 신설 + L3 children('└' 흉내 제거)", () => {
    const projects = NAV.find((s) => s.id === "projects")!;
    const landRights = projects.items.find((n) => n.id === "land-rights");
    expect(landRights?.children?.map((c) => c.href)).toEqual([
      "/en/land-schedule", "/en/registry-analysis", "/en/registry-analysis/quote", "/en/desk-appraisal",
    ]);
    // 사업성·비용 얇은 그룹 해체: 투자 수익성을 프로젝트 섹션 직속 L2 리프로 승격.
    // (기본 접힘 그룹이 핵심 사업기능을 가리던 발견성 문제 해소 — 이제 상시 노출.)
    expect(projects.items.find((n) => n.id === "business-analysis")).toBeUndefined();
    const investment = projects.items.find((n) => n.id === "investment");
    expect(investment?.href).toBe("/en/analytics/investment");
    expect(investment?.children).toBeUndefined();

    // 적산·공사비 관리는 최상위 독립 섹션(cost-mgmt "적산·시공비")의 단독 리프로 이동 — 프로젝트 하위 아님.
    expect(projects.items.find((n) => n.id === "cost")).toBeUndefined();
    const costMgmt = NAV.find((s) => s.id === "cost-mgmt")!;
    expect(costMgmt.items).toHaveLength(1);
    const cost = costMgmt.items[0];
    expect(cost.id).toBe("cost");
    expect(cost.href).toBe("/en/analytics/cost");
    expect(cost.children).toBeUndefined();

    const marketAcquisition = NAV.find((s) => s.id === "market-acquisition")!;
    const marketSales = marketAcquisition.items.find((n) => n.id === "market-sales");
    // ★이 단언은 **목록형**이라 라우트가 하나 늘 때마다 깨진다(CLAUDE.md §A-4 가 경고하는 형태).
    //   지금은 최소 변경으로 신규 라우트만 반영한다 — 파생형 전환은 이 PR 범위 밖이다.
    //   `quick-survey` 는 order 5 로 `market-insights`(10) 보다 앞에 온다.
    expect(marketSales?.children?.map((c) => c.href)).toEqual([
      // ★`realtx-report`(order 12)는 `market-insights`(10)와 `market-ai`(15) **사이**다 —
      //   위치까지 단언해야 order 를 바꿔도 여기서 드러난다.
      "/en/quick-survey", "/en/market-insights", "/en/realtx-report", "/en/market-ai", "/en/sales-info",
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
