import { describe, expect, it } from "vitest";
import {
  annotatedGeometryFor,
  buildLegalFindings,
  complianceVerdict,
} from "./legalAnnotation";
import type {
  AutoDesignCompliance,
  AutoDesignSummary,
  LegalLimitsResponse,
} from "./types";

const SUMMARY: AutoDesignSummary = {
  building_area_sqm: 240,
  total_floor_area_sqm: 1200,
  num_floors: 5,
  building_height_m: 15,
  bcr_percent: 55,
  far_percent: 190,
  total_units: 12,
  parking_count: 12,
  building_width_m: 20,
  building_depth_m: 12,
};

const LIMITS: LegalLimitsResponse = {
  zone_code: "2R",
  max_bcr_percent: 60,
  max_far_percent: 200,
  max_height_m: 35,
  min_setback_m: 1,
  sunlight_hours: 2,
};

describe("buildLegalFindings — compliance → 도면 finding(정직)", () => {
  it("*_ok가 명시 false일 때만 fail (undefined는 pass로 — fail 오판 금지)", () => {
    const c: AutoDesignCompliance = { bcr_ok: false, far_ok: true, height_ok: true, setback_ok: true };
    const out = buildLegalFindings(SUMMARY, c, LIMITS);
    const bcr = out.find((f) => f.check_id === "rules8_건폐율")!;
    const far = out.find((f) => f.check_id === "rules8_용적률")!;
    expect(bcr.status).toBe("fail");
    expect(far.status).toBe("pass");
    // current는 실 산출값, limit은 법정 한도(날조 없음)
    expect(bcr.current).toBe(55);
    expect(bcr.limit).toBe(60);
  });

  it("compliance 키가 undefined면 fail로 단정하지 않는다(pass)", () => {
    const c = {} as AutoDesignCompliance;
    const out = buildLegalFindings(SUMMARY, c, LIMITS);
    expect(out.every((f) => f.status === "pass")).toBe(true);
  });

  it("높이 한도가 0/무제한이면 높이 finding을 생략(허위 항목 금지)", () => {
    const c: AutoDesignCompliance = { bcr_ok: true, far_ok: true, height_ok: true, setback_ok: true };
    const noHeight = buildLegalFindings(SUMMARY, c, { ...LIMITS, max_height_m: 0 });
    expect(noHeight.some((f) => f.check_id === "rules8_높이")).toBe(false);
    const withHeight = buildLegalFindings(SUMMARY, c, LIMITS);
    expect(withHeight.some((f) => f.check_id === "rules8_높이")).toBe(true);
  });

  it("legal_limits 미제공 시 limit은 null(현재값만 정직 표기)", () => {
    const c: AutoDesignCompliance = { bcr_ok: true, far_ok: true, height_ok: true, setback_ok: true };
    const out = buildLegalFindings(SUMMARY, c, undefined);
    expect(out[0].limit).toBeNull();
    expect(out[0].current).toBe(55);
  });
});

describe("annotatedGeometryFor — 건물 산출값 + 부지 개략", () => {
  it("건물 치수는 엔진 산출값을 그대로(부지는 면적 기반)", () => {
    const g = annotatedGeometryFor(900, SUMMARY)!;
    expect(g.building_width_m).toBe(20);
    expect(g.building_depth_m).toBe(12);
    // 부지변 = max(√900=30, 건물변+4) → 건물이 부지 안에 들어감
    expect(g.site_width_m).toBeGreaterThanOrEqual(g.building_width_m);
    expect(g.site_depth_m).toBeGreaterThanOrEqual(g.building_depth_m);
  });

  it("building_width/depth 미제공 시 √면적 폴백(구버전 호환)", () => {
    const old: AutoDesignSummary = { ...SUMMARY, building_width_m: undefined, building_depth_m: undefined };
    const g = annotatedGeometryFor(900, old)!;
    // √240 ≈ 15.5 정사각 근사
    expect(g.building_width_m).toBeCloseTo(Math.round(Math.sqrt(240) * 10) / 10, 1);
    expect(g.building_width_m).toBe(g.building_depth_m);
  });

  it("건물 면적·치수 모두 산출 불가 → null(가짜 도면 금지)", () => {
    const empty: AutoDesignSummary = {
      ...SUMMARY, building_area_sqm: 0, building_width_m: undefined, building_depth_m: undefined,
    };
    expect(annotatedGeometryFor(900, empty)).toBeNull();
  });

  it("부지변은 건물이 들어가도록 항상 건물변+여유 이상", () => {
    const big: AutoDesignSummary = { ...SUMMARY, building_width_m: 50, building_depth_m: 40 };
    const g = annotatedGeometryFor(100, big)!; // √100=10 < 건물 → 건물변+4가 채택돼야
    expect(g.site_width_m).toBeGreaterThanOrEqual(54);
    expect(g.site_depth_m).toBeGreaterThanOrEqual(44);
  });
});

describe("complianceVerdict — all_pass 불리언만 단정", () => {
  it("true → 적합, false → 부적합", () => {
    expect(complianceVerdict({ all_pass: true })).toBe("적합");
    expect(complianceVerdict({ all_pass: false })).toBe("부적합");
  });
  it("undefined → null(판정 보류, 부적합 오단정 금지)", () => {
    expect(complianceVerdict({} as AutoDesignCompliance)).toBeNull();
  });
});
