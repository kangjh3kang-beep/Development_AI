import { describe, expect, it } from "vitest";
import {
  auditFindingsToLegal,
  auditSchematicGeometry,
  auditVerdict,
  mapAuditStatus,
} from "./auditAnnotation";
import type { DesignAuditReport } from "./AuditReportView";

describe("mapAuditStatus — 한/영 혼용 status (부적합⊃적합·조건부적합⊃부적합 주의)", () => {
  it("부적합/fail → fail", () => {
    expect(mapAuditStatus("부적합")).toBe("fail");
    expect(mapAuditStatus("fail")).toBe("fail");
  });
  it("조건부적합/조건부/warn → warning (적합·부적합 부분문자 함정 회피)", () => {
    expect(mapAuditStatus("조건부적합")).toBe("warning");
    expect(mapAuditStatus("조건부")).toBe("warning");
    expect(mapAuditStatus("warn")).toBe("warning");
  });
  it("적합/pass → pass", () => {
    expect(mapAuditStatus("적합")).toBe("pass");
    expect(mapAuditStatus("pass")).toBe("pass");
  });
  it("판정불가/skipped/빈값 → null(제외, 가짜 판정 금지)", () => {
    expect(mapAuditStatus("판정불가")).toBeNull();
    expect(mapAuditStatus("skipped")).toBeNull();
    expect(mapAuditStatus("")).toBeNull();
    expect(mapAuditStatus(null)).toBeNull();
  });
});

const REPORT: DesignAuditReport = {
  verdict: "부적합",
  sections: [
    { id: "S1", findings: [
      { item: "건폐율", status: "부적합", current: 65, limit: 60 },
      { item: "용적률", status: "적합", current: 190, limit: 200 },
    ] },
    { id: "S2", findings: [
      { item: "정북일조", status: "조건부적합", current: 1.5, limit: 2.0 },
      { item: "주차", status: "판정불가", current: null, limit: null }, // 제외돼야
    ] },
  ],
};

describe("auditFindingsToLegal — sections 평탄화 + LegalFinding 변환", () => {
  it("판정 가능한 finding만(판정불가 제외) + status 매핑 + solar 엔진 인식", () => {
    const out = auditFindingsToLegal(REPORT);
    expect(out).toHaveLength(3); // 주차(판정불가) 제외
    const bcr = out.find((f) => f.check_id?.includes("건폐율"))!;
    expect(bcr.status).toBe("fail");
    expect(bcr.current).toBe(65);
    expect(bcr.limit).toBe(60);
    const solar = out.find((f) => f.engine === "solar_envelope")!;
    expect(solar.status).toBe("warning"); // 정북일조 → solar_envelope(북측 표시 발화)
  });

  it("current/limit이 문자열이어도 숫자로 강제(단위 텍스트 제거)", () => {
    const r: DesignAuditReport = { sections: [{ findings: [
      { item: "건폐율", status: "fail", current: "65%", limit: "60%" },
    ] }] };
    const out = auditFindingsToLegal(r);
    expect(out[0].current).toBe(65);
    expect(out[0].limit).toBe(60);
  });
});

describe("auditSchematicGeometry — 면적+건폐율 finding으로 개략 배치(건폐 없으면 null)", () => {
  it("면적·건폐율 → 부지(√면적)·건물(√footprint) 도출", () => {
    const legal = auditFindingsToLegal(REPORT);
    const g = auditSchematicGeometry(400, legal)!;
    // footprint = 400 * 65/100 = 260, 건물변 √260≈16.1, 부지변 √400=20
    expect(g.site_width_m).toBeCloseTo(20, 0);
    expect(g.building_width_m).toBeGreaterThan(10);
    expect(g.building_width_m).toBeLessThanOrEqual(g.site_width_m);
  });
  it("건폐율 finding 없으면 null(건물 footprint 도출 불가 — 가짜 금지)", () => {
    expect(auditSchematicGeometry(400, [
      { check_id: "rules8_용적률", engine: "rules8", status: "pass", current: 190, limit: 200 },
    ])).toBeNull();
  });
  it("면적 0/음수 → null", () => {
    const legal = auditFindingsToLegal(REPORT);
    expect(auditSchematicGeometry(0, legal)).toBeNull();
  });
});

describe("auditVerdict — 부적합/조건부적합/적합 (부분문자 함정 회피)", () => {
  it("조건부적합이 부적합으로 오판되지 않음", () => {
    expect(auditVerdict({ verdict: "조건부적합" })).toBe("조건부적합");
    expect(auditVerdict({ verdict: "부적합" })).toBe("부적합");
    expect(auditVerdict({ verdict: "적합" })).toBe("적합");
    expect(auditVerdict({ verdict: "판정불가" })).toBeNull();
  });
});
