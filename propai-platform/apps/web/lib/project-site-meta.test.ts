import { describe, expect, it } from "vitest";
import type { SiteAnalysisData } from "@/store/useProjectContextStore";
import { buildSiteMetaPatch } from "./project-site-meta";

const META = {
  address: "서울특별시 동작구 상도동 210-453",
  total_area_sqm: 1000,
  zone_type: "제2종일반주거지역",
  pnu_codes: ["1159010300102100453"],
};

describe("buildSiteMetaPatch (U1 — 부지 게이트 통과용 보강)", () => {
  it("siteAnalysis가 비었으면 address 포함 전 필드 보강", () => {
    const patch = buildSiteMetaPatch(null, META);
    expect(patch.address).toBe("서울특별시 동작구 상도동 210-453");
    expect(patch.landAreaSqm).toBe(1000);
    expect(patch.zoneCode).toBe("제2종일반주거지역");
    expect(patch.pnu).toBe("1159010300102100453");
  });

  it("★스냅샷 복원이 address 없는 siteAnalysis로 덮은 경우 address를 보강(부지오류 해소)", () => {
    const site = {
      estimatedValue: 1816000,
      landAreaSqm: 1000,
      zoneCode: "제2종일반주거지역",
      address: null,
      pnu: null,
    } as unknown as SiteAnalysisData;
    const patch = buildSiteMetaPatch(site, META);
    expect(patch.address).toBe("서울특별시 동작구 상도동 210-453"); // 빈 address 보강
    expect(patch.pnu).toBe("1159010300102100453"); // 빈 pnu도 보강
    // 이미 있는 필드는 보강 안 함(사용자/분석 값 보존)
    expect("landAreaSqm" in patch).toBe(false);
    expect("zoneCode" in patch).toBe(false);
  });

  it("address가 이미 있으면 덮지 않음(사용자/분석 값 보존)", () => {
    const site = { address: "사용자 입력 주소", landAreaSqm: 500 } as unknown as SiteAnalysisData;
    const patch = buildSiteMetaPatch(site, META);
    expect("address" in patch).toBe(false);
    expect("landAreaSqm" in patch).toBe(false);
  });

  it("meta가 비면 빈 패치(보강할 것 없음)", () => {
    const patch = buildSiteMetaPatch(null, {});
    expect(Object.keys(patch)).toHaveLength(0);
  });
});
