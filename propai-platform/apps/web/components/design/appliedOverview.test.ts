import { describe, expect, it } from "vitest";
import { resolveAppliedOverview } from "./appliedOverview";

describe("resolveAppliedOverview — 적용 건축개요 3필드 원자 채택(백로그② R1 회귀앵커)", () => {
  it("① 완전한 m(세 필드 모두 존재) → 전부 m 채택", () => {
    const m = { total_floor_area_sqm: 670.32, bcr_pct: 11.03, far_pct: 44.1 };
    const designData = { totalGfaSqm: 1216, bcr: 20, far: 80 };
    expect(resolveAppliedOverview(m, designData)).toEqual({ gfa: 670.32, bcr: 11.03, far: 44.1 });
  });

  it("② 부분 m(total_floor_area_sqm만 없음) → 전부 designData로 폴백(거울상 혼입 금지)", () => {
    const m = { far_pct: 199, bcr_pct: 60, total_floor_area_sqm: null };
    const designData = { totalGfaSqm: 1216, bcr: 20, far: 80 };
    expect(resolveAppliedOverview(m, designData)).toEqual({ gfa: 1216, bcr: 20, far: 80 });
  });

  it("③ 그 역상(total_floor_area_sqm만 있고 far_pct 없음) → 전부 designData로 폴백", () => {
    const m = { total_floor_area_sqm: 670.32, bcr_pct: 11.03, far_pct: null };
    const designData = { totalGfaSqm: 1216, bcr: 20, far: 80 };
    expect(resolveAppliedOverview(m, designData)).toEqual({ gfa: 1216, bcr: 20, far: 80 });
  });

  it("④ m=null(massGeom 재사용·완전폴백 분기) → 전부 designData로 폴백", () => {
    const designData = { totalGfaSqm: 1216, bcr: 20, far: 80 };
    expect(resolveAppliedOverview(null, designData)).toEqual({ gfa: 1216, bcr: 20, far: 80 });
  });

  it("m·designData 모두 값이 없으면 세 필드 전부 null(가짜 0 금지)", () => {
    expect(resolveAppliedOverview(null, null)).toEqual({ gfa: null, bcr: null, far: null });
    expect(resolveAppliedOverview(undefined, undefined)).toEqual({ gfa: null, bcr: null, far: null });
  });
});
