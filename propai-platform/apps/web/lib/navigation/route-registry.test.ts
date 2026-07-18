import { describe, expect, it } from "vitest";
import {
  PRIMARY_NAV_SECTIONS,
  PRIMARY_ROUTE_REGISTRY,
  buildPrimaryRegistrySections,
  localizedHref,
  visibleRouteRegistryItems,
} from "./route-registry";

describe("route registry IA gate", () => {
  it("keeps primary section order stable", () => {
    expect(PRIMARY_NAV_SECTIONS.map((section) => section.id)).toEqual([
      "control",
      "projects",
      "cost-mgmt",
      "market-acquisition",
      "design-center",
      "sales-management",
      "my",
      "admin",
    ]);
  });

  it("has unique route ids and visible paths", () => {
    const ids = PRIMARY_ROUTE_REGISTRY.map((item) => item.id);
    expect(new Set(ids).size).toBe(ids.length);

    const paths = visibleRouteRegistryItems().map((item) => item.path);
    expect(paths.every(Boolean)).toBe(true);
    expect(new Set(paths).size).toBe(paths.length);
  });

  it("does not leave children without registered parents", () => {
    const ids = new Set(PRIMARY_ROUTE_REGISTRY.map((item) => item.id));
    const missingParents = PRIMARY_ROUTE_REGISTRY
      .filter((item) => item.parentId && !ids.has(item.parentId))
      .map((item) => item.id);

    expect(missingParents).toEqual([]);
  });

  it("localizes home and nested paths consistently", () => {
    expect(localizedHref("ko", "/")).toBe("/ko");
    expect(localizedHref("ko", "/analysis")).toBe("/ko/analysis");
    expect(localizedHref("ko", "/projects")).toBe("/ko/projects");
    expect(localizedHref("en", "/settings/design-references")).toBe("/en/settings/design-references");
  });

  it("builds the recursive tree used by sidebar and sitemap", () => {
    const sections = buildPrimaryRegistrySections("ko");
    const control = sections.find((section) => section.id === "control");
    const projects = sections.find((section) => section.id === "projects");
    const landRights = projects?.items.find((item) => item.id === "land-rights");
    const market = sections.find((section) => section.id === "market-acquisition");
    const acquisition = market?.items.find((item) => item.id === "acquisition");
    const designRefs = sections
      .find((section) => section.id === "design-center")
      ?.items.find((item) => item.id === "design-refs");

    expect(control?.items.map((item) => item.href)).toEqual([
      "/ko", "/ko/precheck", "/ko/analysis", "/ko/settings/team",
    ]);

    expect(landRights?.children?.map((child) => child.href)).toEqual([
      "/ko/land-schedule",
      "/ko/registry-analysis",
      "/ko/desk-appraisal",
    ]);
    expect(acquisition?.children?.map((child) => child.href)).toEqual(["/ko/auction", "/ko/g2b"]);
    expect(designRefs?.prefetch).toBe(false);
  });

  it("적산·시공비를 최상위 단일-리프 섹션으로 승격(프로젝트 하위 아님)", () => {
    const sections = buildPrimaryRegistrySections("ko");
    const costMgmt = sections.find((section) => section.id === "cost-mgmt");
    const projects = sections.find((section) => section.id === "projects");

    // 프로젝트(20)와 시장·획득(30) 사이 order 25로 정렬 — 프로젝트 직후.
    const order = sections.map((section) => section.id);
    expect(order.indexOf("cost-mgmt")).toBe(order.indexOf("projects") + 1);
    expect(order.indexOf("cost-mgmt")).toBe(order.indexOf("market-acquisition") - 1);

    // cost는 이제 cost-mgmt 섹션의 단독 리프(하위메뉴 없음) — 프로젝트 섹션에는 없어야 한다.
    expect(costMgmt?.items).toHaveLength(1);
    const cost = costMgmt?.items[0];
    expect(cost?.id).toBe("cost");
    expect(cost?.href).toBe("/ko/analytics/cost");
    expect(cost?.children).toBeUndefined();
    expect(projects?.items.some((item) => item.id === "cost")).toBe(false);
  });
});
