// useNodeRunner 단위테스트 — Phase B B2
// 노드 불변계약 5단계 순서((b)runner→(c)expert-panel→(d)verify), store 환류(e), unavailable 경로.
// apiClient는 mock(실호출 금지), 데이터/오케스트레이션 store는 setState로 시드한다.

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook } from "@testing-library/react";

// ── apiClient mock(기존 api-client.test.ts 패턴) ──
const post = vi.fn();
const request = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: {
    post: (...a: unknown[]) => post(...a),
    request: (...a: unknown[]) => request(...a),
  },
  resolveApiOrigin: () => "https://api.test",
}));

import { useNodeRunner, deriveMassGfa } from "@/hooks/useNodeRunner";
import { useOrchestrationStore } from "@/store/useOrchestrationStore";
import { useProjectContextStore } from "@/store/useProjectContextStore";

function resetData(): void {
  useProjectContextStore.setState({
    projectId: "p1",
    siteAnalysis: null,
    designData: null,
    feasibilityData: null,
    costData: null,
    esgData: null,
    complianceData: null,
    updatedAt: {},
    snapshots: {},
    manualFields: {},
  });
}
function resetOrch(): void {
  useOrchestrationStore.setState({
    runMode: "guided",
    picked: {},
    activeProfileId: null,
    nodeOrder: [],
    plan: [],
    nodeResult: {},
    nodeUpdatedAt: {},
    currentProjectId: null,
    customProfiles: [],
    byProject: {},
  });
}

beforeEach(() => {
  post.mockReset();
  request.mockReset();
  resetData();
  resetOrch();
});

describe("useNodeRunner — 5단계 순서·환류", () => {
  it("land 노드: (b)runner→(d)verify 순서 호출 + siteAnalysis 환류 + grounding ok", async () => {
    // 입력 확보(부지 주소) → ready.
    useProjectContextStore.getState().updateSiteAnalysis({ address: "서울 강남구" });
    // runner 응답(부지 산출). verify는 pass.
    request.mockResolvedValueOnce({ landAreaSqm: 800, zoneCode: "제2종일반주거" });
    post.mockResolvedValueOnce({ verdict: "pass" }); // /verify/analysis

    const { result } = renderHook(() => useNodeRunner());
    const res = await result.current.runNode("land");

    // (b) runner: 절대 URL + 레지스트리 path(/api/v1/zoning/analyze).
    expect(request).toHaveBeenCalledTimes(1);
    const [url, opts] = request.mock.calls[0];
    expect(url).toBe("https://api.test/api/v1/zoning/analyze");
    expect((opts as { method: string }).method).toBe("POST");

    // land는 expertPanel:false → expert-panel 미호출. verify만 호출(1회).
    expect(post).toHaveBeenCalledTimes(1);
    expect(post.mock.calls[0][0]).toBe("/verify/analysis");

    // (d) verifyStatus 기록.
    expect(res.verifyStatus).toBe("pass");
    expect(res.state).toBe("done");
    // (a) 그라운딩: 입력 확보 → unavailable input 표기 없음, 출처 ok.
    expect(res.grounding["VWorld"]).toBe("ok");

    // (e) store 환류: siteAnalysis.landAreaSqm 채워짐(source auto).
    const site = useProjectContextStore.getState().siteAnalysis;
    expect(site?.landAreaSqm).toBe(800);
    expect(site?.zoneCode).toBe("제2종일반주거");
  });

  it("expertPanel:true 노드(legal): (b)runner→(c)expert-panel→(d)verify 3호출 순서", async () => {
    useProjectContextStore.getState().updateSiteAnalysis({ address: "서울 강남구" });
    request.mockResolvedValueOnce({ bcrCompliant: true, farCompliant: true, violations: [] });
    post.mockResolvedValueOnce({}); // /expert-panel/analyze
    post.mockResolvedValueOnce({ verdict: "warn" }); // /verify/analysis

    const { result } = renderHook(() => useNodeRunner());
    const res = await result.current.runNode("legal");

    // runner 1회.
    expect(request).toHaveBeenCalledTimes(1);
    // expert-panel → verify 순서.
    expect(post).toHaveBeenCalledTimes(2);
    expect(post.mock.calls[0][0]).toBe("/expert-panel/analyze");
    expect(post.mock.calls[1][0]).toBe("/verify/analysis");
    expect(res.verifyStatus).toBe("warn");

    // (e) compliance 환류.
    const comp = useProjectContextStore.getState().complianceData;
    expect(comp?.bcrCompliant).toBe(true);
  });

  it("available:false(audit): 백엔드 무호출 + skipped-unavailable + grounding unavailable", async () => {
    const { result } = renderHook(() => useNodeRunner());
    const res = await result.current.runNode("audit");

    expect(request).not.toHaveBeenCalled();
    expect(post).not.toHaveBeenCalled();
    expect(res.state).toBe("skipped-unavailable");
    expect(res.chargedKrw).toBe(0);
    // 0 강제 금지 — 그라운딩 출처 전부 unavailable 정직 표기.
    expect(Object.values(res.grounding).every((v) => v === "unavailable")).toBe(true);
  });

  it("입력 전무(상류 컨텍스트 0)면 백엔드 미호출 + skipped-unavailable(0 강제 금지)", async () => {
    // 데이터 store 빈 상태 → land 입력(주소) 미확보 → ready 0.
    const { result } = renderHook(() => useNodeRunner());
    const res = await result.current.runNode("land");

    expect(request).not.toHaveBeenCalled();
    expect(res.state).toBe("skipped-unavailable");
    expect(
      res.grounding["input:siteAnalysis.address"],
    ).toBe("unavailable");
  });

  it("과금 no-op: 프론트 호출가능 stage:* 엔드포인트 부재 → chargedKrw=0(가짜 호출 없음)", async () => {
    useProjectContextStore.getState().updateSiteAnalysis({ address: "서울" });
    request.mockResolvedValueOnce({ landAreaSqm: 500 });
    post.mockResolvedValueOnce({ verdict: "pass" });

    const { result } = renderHook(() => useNodeRunner());
    const res = await result.current.runNode("land");

    // billing/charge 류 호출이 없어야 한다(stage:* 화이트리스트 부재 → 날조 금지).
    const billingCalls = post.mock.calls.filter((c) =>
      String(c[0]).includes("billing"),
    );
    expect(billingCalls.length).toBe(0);
    expect(res.chargedKrw).toBe(0);
  });

  it("runner 실패 시 state=error + 결과 기록(verify 미진입)", async () => {
    useProjectContextStore.getState().updateSiteAnalysis({ address: "서울" });
    request.mockRejectedValueOnce(new Error("500"));

    const { result } = renderHook(() => useNodeRunner());
    const res = await result.current.runNode("land");

    expect(res.state).toBe("error");
    expect(res.error).toBe("500");
    expect(post).not.toHaveBeenCalled(); // verify 미진입
    // 오케스트레이션 store에 결과 환류.
    expect(useOrchestrationStore.getState().nodeResult["land"]?.state).toBe("error");
  });

  it("sales 노드: feasibilityData를 stamp/오염하지 않는다(ssotOutputs=[] — 매출주입은 Phase C)", async () => {
    // 부지·설계 확보(sales 입력) + 기존 feasibilityData 존재.
    useProjectContextStore.getState().updateSiteAnalysis({ address: "서울", landAreaSqm: 500 });
    useProjectContextStore.getState().updateDesignData({
      totalGfaSqm: 3000,
      floorCount: 10,
      buildingType: "공동주택",
      bcr: 50,
      far: 200,
    });
    useProjectContextStore.getState().updateFeasibilityData({ totalCostWon: 12345 });
    const stampBefore = useProjectContextStore.getState().updatedAt.feasibility;
    request.mockResolvedValueOnce({ totalRevenueWon: 99999, totalCostWon: 0 });
    post.mockResolvedValueOnce({}); // expert-panel(sales expertPanel:true)
    post.mockResolvedValueOnce({ verdict: "pass" }); // verify

    const { result } = renderHook(() => useNodeRunner());
    const res = await result.current.runNode("sales");

    // sales는 데이터 SSOT 비기록 → feasibilityData 불변(매출 미주입), stamp 불변(오염 없음).
    const feas = useProjectContextStore.getState().feasibilityData;
    expect(feas?.totalRevenueWon).not.toBe(99999); // runner 응답(99999) 미주입
    expect(feas?.totalCostWon).toBe(12345); // 기존값 보존
    expect(useProjectContextStore.getState().updatedAt.feasibility).toBe(stampBefore);
    // 결과는 orchestration nodeResult에만(done).
    expect(res.state).toBe("done");
  });

  it("design 노드: path {id}가 projectId로 치환돼 호출된다", async () => {
    // 입력 확보(부지+법규) + projectId 주입.
    useProjectContextStore.setState({ projectId: "proj-42" });
    useProjectContextStore.getState().updateSiteAnalysis({ address: "서울", landAreaSqm: 500 });
    useProjectContextStore.getState().updateComplianceData({
      bcrCompliant: true,
      farCompliant: true,
      heightCompliant: true,
      violations: [],
    });
    request.mockResolvedValueOnce({ totalGfaSqm: 3000, floorCount: 10 });
    post.mockResolvedValueOnce({ verdict: "pass" }); // verify(design expertPanel:false)

    const { result } = renderHook(() => useNodeRunner());
    const res = await result.current.runNode("design");

    expect(request).toHaveBeenCalledTimes(1);
    const [url] = request.mock.calls[0];
    // {id} → projectId 치환(리터럴 {id} 잔존 금지).
    expect(url).toBe("https://api.test/api/v1/design/proj-42/bim/generate");
    expect(String(url)).not.toContain("{id}");
    expect(res.state).toBe("done");
  });

  it("design 노드: projectId 미확보면 백엔드 무호출 + needs-input(0 강제 금지)", async () => {
    // projectId=null + 입력은 확보(ready) → path 플레이스홀더 치환 불가 → needs-input.
    useProjectContextStore.setState({ projectId: null });
    useProjectContextStore.getState().updateSiteAnalysis({ address: "서울", landAreaSqm: 500 });
    useProjectContextStore.getState().updateComplianceData({
      bcrCompliant: true,
      farCompliant: true,
      heightCompliant: true,
      violations: [],
    });

    const { result } = renderHook(() => useNodeRunner());
    const res = await result.current.runNode("design");

    expect(request).not.toHaveBeenCalled();
    expect(post).not.toHaveBeenCalled();
    expect(res.state).toBe("needs-input");
    expect(res.grounding["input:projectId"]).toBe("unavailable");
  });
});

// design bim/generate 응답 mass엔 GFA 키가 없으므로 폭×깊이×층수로 도출(HIGH 결함 수정).
describe("deriveMassGfa — design GFA 도출 폴백", () => {
  it("mass 폭×깊이×층수로 GFA 도출(반올림)", () => {
    const resp = {
      mass: { building_width_m: 22.5, building_depth_m: 20.7, num_floors: 3 },
    };
    expect(deriveMassGfa(resp)).toBe(Math.round(22.5 * 20.7 * 3)); // ≈1397
  });

  it("폭/깊이/층수 중 하나라도 미확보면 null(0 강제 금지)", () => {
    expect(deriveMassGfa({ mass: { building_width_m: 22.5, num_floors: 3 } })).toBeNull();
    expect(deriveMassGfa({ mass: {} })).toBeNull();
    expect(deriveMassGfa({})).toBeNull();
  });

  it("비양수(0/음수)면 null(무의미 GFA 방지)", () => {
    expect(
      deriveMassGfa({ mass: { building_width_m: 0, building_depth_m: 20, num_floors: 3 } }),
    ).toBeNull();
    expect(
      deriveMassGfa({ mass: { building_width_m: 22, building_depth_m: -1, num_floors: 3 } }),
    ).toBeNull();
  });
});
