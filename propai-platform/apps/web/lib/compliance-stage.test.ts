import { describe, it, expect, beforeEach } from "vitest";
import { useProjectContextStore } from "@/store/useProjectContextStore";

// Fix #1 (감사 HIGH): legal 노드 환류 단선 — 백엔드 /regulation/analyze는 limits/evidence/legal_refs/zone_type를
// 산출하나 useNodeRunner가 없는 camelCase 불리언만 읽어 complianceData가 항상 all-null → 법규단계 영구 미완료·
// 정량한도/근거 SSOT 유실. 수선: complianceData에 limits/evidence 보존 + 단계완료 판정이 이를 인식.
describe("Fix #1: legal 환류 — 법령허브 산출(limits/evidence) 보존 + 단계 완료 인식", () => {
  beforeEach(() => {
    useProjectContextStore.getState().clearProject();
    useProjectContextStore.getState().setProject("p1", "test", "active");
  });

  it("limits/evidence가 보존되면(불리언 null) 법규단계 완료로 인식", () => {
    useProjectContextStore.getState().updateComplianceData({
      bcrCompliant: null,
      farCompliant: null,
      heightCompliant: null,
      violations: [],
      limits: { far: { effective_pct: 200 }, bcr: { effective_pct: 50 } },
      evidence: [{ label: "용적률", value: "200%" }],
      legalRefs: [{ law_name: "국토의 계획 및 이용에 관한 법률" }],
      zoneType: "제2종일반주거지역",
    });
    const s = useProjectContextStore.getState();
    expect(s.stageHasData("legal")).toBe(true);
    expect(s.projectCompleteness().stages.find((x) => x.key === "compliance")?.done).toBe(true);
    // SSOT 보존 확인(하류가 재호출 없이 읽도록)
    expect(s.complianceData?.limits).toBeTruthy();
    expect(s.complianceData?.evidence?.length).toBe(1);
    expect(s.complianceData?.zoneType).toBe("제2종일반주거지역");
  });

  it("불리언·violations·limits·evidence 전부 없으면 법규단계 미완료(회귀 보존)", () => {
    useProjectContextStore.getState().updateComplianceData({
      bcrCompliant: null,
      farCompliant: null,
      heightCompliant: null,
      violations: [],
    });
    expect(useProjectContextStore.getState().stageHasData("legal")).toBe(false);
  });

  it("기존 불리언 판정 경로도 여전히 완료 인식(무회귀)", () => {
    useProjectContextStore.getState().updateComplianceData({
      bcrCompliant: true,
      farCompliant: false,
      heightCompliant: null,
      violations: ["높이 제한 초과"],
    });
    expect(useProjectContextStore.getState().stageHasData("legal")).toBe(true);
  });
});
