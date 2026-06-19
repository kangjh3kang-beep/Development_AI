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

import {
  useNodeRunner,
  deriveMassGfa,
  pickRecommendedDevType,
  pickSalesPricePerPyeongWon,
} from "@/hooks/useNodeRunner";
import { useOrchestrationStore } from "@/store/useOrchestrationStore";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { buildNodeBody, type NodeBodyContext } from "@/lib/orchestration/node-body-builders";

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

  it("sales 노드(Phase C-2): 적정분양가(원/평)만 환류 + 매출·원가·stamp는 오염하지 않는다", async () => {
    // 부지·설계 확보(sales 입력) + 기존 feasibilityData 존재.
    // pnu 포함(land→sales 정상 폐포) — sales는 lawd_cd 도출에 pnu/bcode가 필요(Issue2 게이트).
    useProjectContextStore.getState().updateSiteAnalysis({ address: "서울", landAreaSqm: 500, pnu: "1168010100100000000" });
    useProjectContextStore.getState().updateDesignData({
      totalGfaSqm: 3000,
      floorCount: 10,
      buildingType: "공동주택",
      bcr: 50,
      far: 200,
    });
    useProjectContextStore.getState().updateFeasibilityData({ totalCostWon: 12345 });
    const stampBefore = useProjectContextStore.getState().updatedAt.feasibility;
    // sales 라이브 응답 모양: trade.아파트.per_pyeong.avg=11161(만원/평) + 매출/원가 오염 시도.
    request.mockResolvedValueOnce({
      trade: { 아파트: { per_pyeong: { avg: 11161 } } },
      totalRevenueWon: 99999,
      totalCostWon: 0,
    });
    post.mockResolvedValueOnce({}); // expert-panel(sales expertPanel:true)
    post.mockResolvedValueOnce({ verdict: "pass" }); // verify

    const { result } = renderHook(() => useNodeRunner());
    const res = await result.current.runNode("sales");

    const feas = useProjectContextStore.getState().feasibilityData;
    // ★분양가만 환류(만원/평 11161 → 원/평 ×10000 = 111,610,000).
    expect(feas?.salePricePerPyeongWon).toBe(111_610_000);
    // 매출·원가는 미접촉(sales는 매출단가만 시드 — ROI 최종 산출은 feasibility 노드 담당).
    expect(feas?.totalRevenueWon ?? null).not.toBe(99999); // runner 응답(99999) 미주입
    expect(feas?.totalCostWon).toBe(12345); // 기존값 보존
    // ★staleness 오염 없음 — updatedAt.feasibility 불변(수지 노드 skipped-fresh 함정 회피).
    expect(useProjectContextStore.getState().updatedAt.feasibility).toBe(stampBefore);
    expect(res.state).toBe("done");
  });

  it("sales 노드(Phase C-2): 실거래 자료 없으면(trade 부재) 분양가 미환류(무목업·무회귀)", async () => {
    useProjectContextStore.getState().updateSiteAnalysis({ address: "서울", landAreaSqm: 500, pnu: "1168010100100000000" });
    useProjectContextStore.getState().updateDesignData({
      totalGfaSqm: 3000, floorCount: 10, buildingType: "공동주택", bcr: 50, far: 200,
    });
    const stampBefore = useProjectContextStore.getState().updatedAt.feasibility;
    request.mockResolvedValueOnce({ pricing_band: { fair_price_10k: 282100 } }); // trade 없음
    post.mockResolvedValueOnce({}); // expert-panel
    post.mockResolvedValueOnce({ verdict: "pass" }); // verify

    const { result } = renderHook(() => useNodeRunner());
    const res = await result.current.runNode("sales");

    // 평당 직접경로 자료가 없으므로 미환류(fair_price_10k는 84㎡ 총액이라 채택하지 않음).
    expect(useProjectContextStore.getState().feasibilityData?.salePricePerPyeongWon ?? null).toBeNull();
    expect(useProjectContextStore.getState().updatedAt.feasibility).toBe(stampBefore);
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

  it("sales 노드(Issue2): pnu·bcode 미확보면 백엔드 무호출 + needs-input(400 회피·0 강제 금지)", async () => {
    // 주소·설계는 확보(ready)되어 sales 노드는 진행하지만, pnu가 없어 lawd_cd 도출 불가.
    // → 백엔드 400(법정동코드 결정 불가) 대신 사전에 needs-input으로 정직 고지.
    useProjectContextStore.getState().updateSiteAnalysis({ address: "서울", landAreaSqm: 500 }); // pnu 없음
    useProjectContextStore.getState().updateDesignData({
      totalGfaSqm: 3000, floorCount: 10, buildingType: "공동주택", bcr: 50, far: 200,
    });

    const { result } = renderHook(() => useNodeRunner());
    const res = await result.current.runNode("sales");

    expect(request).not.toHaveBeenCalled();
    expect(post).not.toHaveBeenCalled();
    expect(res.state).toBe("needs-input");
    expect(res.grounding["input:pnu"]).toBe("unavailable");
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

// (Phase C-1) recommend 응답에서 최상위 추천 개발방식(ranked[0].method, 현행 우선) 추출.
describe("pickRecommendedDevType — 추천 개발방식 코드 추출", () => {
  it("현행 근거(far_basis=현행) 후보를 우선 채택(정렬 순서 보존)", () => {
    const resp = {
      ranked: [
        { method: "M06", far_basis: "현행", composite: 16.0 },
        { method: "M08", far_basis: "현행", composite: 14.0 },
      ],
    };
    expect(pickRecommendedDevType(resp)).toBe("M06");
  });

  it("현행 후보가 없으면 ranked[0](정렬 1순위) 폴백", () => {
    const resp = {
      ranked: [
        { method: "M11", far_basis: "종상향", composite: 20.0 },
        { method: "M06", far_basis: "종상향", composite: 10.0 },
      ],
    };
    expect(pickRecommendedDevType(resp)).toBe("M11");
  });

  it("종상향이 1순위여도 현행 후보가 있으면 현행을 채택(조건부 시나리오 배제)", () => {
    const resp = {
      ranked: [
        { method: "M11", far_basis: "종상향", composite: 20.0 },
        { method: "M08", far_basis: "현행", composite: 12.0 },
      ],
    };
    expect(pickRecommendedDevType(resp)).toBe("M08");
  });

  it("ranked 비었거나 부재(게이트 차단)면 null → 환류 미실행(폴백 유도)", () => {
    expect(pickRecommendedDevType({ ranked: [] })).toBeNull();
    expect(pickRecommendedDevType({})).toBeNull();
    expect(pickRecommendedDevType({ ranked: "nope" } as Record<string, unknown>)).toBeNull();
  });

  it("method가 비정상(빈/비문자)이면 null", () => {
    expect(pickRecommendedDevType({ ranked: [{ far_basis: "현행" }] })).toBeNull();
    expect(pickRecommendedDevType({ ranked: [{ method: "" }] })).toBeNull();
  });
});

// (Phase C-1) 폐루프: recommend stamp → feasibility bodyBuilder가 그 development_type 사용.
describe("recommend → feasibility 폐루프(development_type 환류)", () => {
  it("recommend 실행이 feasibilityData.developmentType을 stamp하되 updatedAt.feasibility는 오염하지 않는다", async () => {
    // 부지+법규 확보(recommend 입력 ready) + 기존 수지 데이터(원가) 존재.
    useProjectContextStore.getState().updateSiteAnalysis({ address: "서울 강남구 역삼동 737", landAreaSqm: 800 });
    useProjectContextStore.getState().updateComplianceData({
      bcrCompliant: true,
      farCompliant: true,
      heightCompliant: true,
      violations: [],
    });
    useProjectContextStore.getState().updateFeasibilityData({ totalCostWon: 12345 });
    const stampBefore = useProjectContextStore.getState().updatedAt.feasibility;

    // recommend 라이브 응답 모양(현행 ranked[0]=M06).
    request.mockResolvedValueOnce({
      ranked: [
        { method: "M06", type_name: "일반분양", far_basis: "현행", composite: 16.0 },
        { method: "M08", type_name: "오피스텔", far_basis: "현행", composite: 14.0 },
      ],
    });
    post.mockResolvedValueOnce({}); // expert-panel(recommend expertPanel:true)
    post.mockResolvedValueOnce({ verdict: "pass" }); // verify

    const { result } = renderHook(() => useNodeRunner());
    const res = await result.current.runNode("recommend");
    expect(res.state).toBe("done");

    const feas = useProjectContextStore.getState().feasibilityData;
    // 추천값 stamp.
    expect(feas?.developmentType).toBe("M06");
    // 기존 수지 슬롯 보존(매출·원가 미접촉).
    expect(feas?.totalCostWon).toBe(12345);
    // ★staleness 오염 없음 — updatedAt.feasibility 불변(수지 노드 skipped-fresh 함정 회피).
    expect(useProjectContextStore.getState().updatedAt.feasibility).toBe(stampBefore);
  });

  it("폐루프: stamp된 developmentType을 feasibility bodyBuilder가 그대로 development_type으로 전송", async () => {
    // recommend가 M08을 stamp한 상태로 시드.
    useProjectContextStore.getState().updateSiteAnalysis({ address: "서울", landAreaSqm: 800 });
    useProjectContextStore.getState().updateComplianceData({
      bcrCompliant: true, farCompliant: true, heightCompliant: true, violations: [],
    });
    request.mockResolvedValueOnce({
      ranked: [{ method: "M08", far_basis: "현행", composite: 14.0 }],
    });
    post.mockResolvedValueOnce({}); // expert-panel
    post.mockResolvedValueOnce({ verdict: "pass" }); // verify
    const { result } = renderHook(() => useNodeRunner());
    await result.current.runNode("recommend");

    // 이제 feasibility bodyBuilder가 store 슬롯(M08)을 읽어 body.development_type=M08로 전송해야 한다.
    const s = useProjectContextStore.getState();
    useProjectContextStore.getState().updateDesignData({
      totalGfaSqm: 3000, floorCount: 10, buildingType: "공동주택", bcr: 50, far: 200,
    });
    const ctx: NodeBodyContext = {
      siteAnalysis: s.siteAnalysis,
      designData: useProjectContextStore.getState().designData,
      feasibilityData: useProjectContextStore.getState().feasibilityData,
    };
    const { body } = buildNodeBody("feasibility", ctx, "p1");
    expect(body.development_type).toBe("M08"); // ★폐루프: 추천값이 수지로 흘러감(M06 고정 해소)
  });

  it("게이트 차단(ranked 비음)이면 developmentType 미stamp → feasibility는 M06 폴백(무회귀)", async () => {
    useProjectContextStore.getState().updateSiteAnalysis({ address: "서울", landAreaSqm: 800 });
    useProjectContextStore.getState().updateComplianceData({
      bcrCompliant: true, farCompliant: true, heightCompliant: true, violations: [],
    });
    request.mockResolvedValueOnce({ ranked: [], gate: { developability: "BLOCKED" } });
    post.mockResolvedValueOnce({}); // expert-panel
    post.mockResolvedValueOnce({ verdict: "warn" }); // verify
    const { result } = renderHook(() => useNodeRunner());
    await result.current.runNode("recommend");

    // 추천 코드 미산출 → developmentType 미stamp(없음).
    expect(useProjectContextStore.getState().feasibilityData?.developmentType ?? null).toBeNull();
    // feasibility bodyBuilder는 백엔드 기본 M06 폴백.
    useProjectContextStore.getState().updateDesignData({
      totalGfaSqm: 3000, floorCount: 10, buildingType: "공동주택", bcr: 50, far: 200,
    });
    const { body } = buildNodeBody("feasibility", {
      siteAnalysis: useProjectContextStore.getState().siteAnalysis,
      designData: useProjectContextStore.getState().designData,
      feasibilityData: useProjectContextStore.getState().feasibilityData,
    }, "p1");
    expect(body.development_type).toBe("M06");
  });
});

// (Phase C-2) sales 응답에서 적정분양가(trade.아파트.per_pyeong.avg 만원/평 → 원/평) 추출.
describe("pickSalesPricePerPyeongWon — 적정분양가 단가 추출(만원/평 → 원/평)", () => {
  it("trade.아파트.per_pyeong.avg(만원/평)를 ×10000(원/평)로 변환", () => {
    // 라이브 강남 역삼동 예: 11161 만원/평 → 111,610,000 원/평.
    const resp = { trade: { 아파트: { per_pyeong: { avg: 11161, min: 9000, max: 13000 } } } };
    expect(pickSalesPricePerPyeongWon(resp)).toBe(111_610_000);
  });

  it("trade/아파트/per_pyeong/avg 경로가 비면 null(자료 없음 → 미환류)", () => {
    expect(pickSalesPricePerPyeongWon({})).toBeNull();
    expect(pickSalesPricePerPyeongWon({ trade: {} })).toBeNull();
    expect(pickSalesPricePerPyeongWon({ trade: { 아파트: {} } })).toBeNull();
    expect(pickSalesPricePerPyeongWon({ trade: { 아파트: { per_pyeong: {} } } })).toBeNull();
  });

  it("avg가 비양수/비숫자면 null(0 강제 금지·날조 배제)", () => {
    expect(pickSalesPricePerPyeongWon({ trade: { 아파트: { per_pyeong: { avg: 0 } } } })).toBeNull();
    expect(pickSalesPricePerPyeongWon({ trade: { 아파트: { per_pyeong: { avg: -1 } } } })).toBeNull();
    expect(
      pickSalesPricePerPyeongWon({ trade: { 아파트: { per_pyeong: { avg: "11161" } } } } as Record<string, unknown>),
    ).toBeNull();
  });

  it("fair_price_10k(84㎡ 총액)는 평당 직접경로가 아니므로 채택하지 않음(부정확 추정 배제)", () => {
    // trade가 없고 pricing_band만 있어도 평당경로가 없으면 null(무목업).
    const resp = { pricing_band: { fair_price_10k: 282100 } };
    expect(pickSalesPricePerPyeongWon(resp)).toBeNull();
  });
});

// (Phase C-2) 폐루프: sales 적정분양가 환류 → feasibility bodyBuilder가 그 매출단가(원/평) 사용.
describe("sales → feasibility 폐루프(적정분양가 환류)", () => {
  it("sales 실행이 salePricePerPyeongWon을 stamp하되 updatedAt.feasibility는 오염하지 않는다", async () => {
    useProjectContextStore.getState().updateSiteAnalysis({ address: "서울 강남구 역삼동 736", landAreaSqm: 800, pnu: "1168010100100000000" });
    useProjectContextStore.getState().updateDesignData({
      totalGfaSqm: 3000, floorCount: 10, buildingType: "공동주택", bcr: 50, far: 200, unitCount: 40,
    });
    useProjectContextStore.getState().updateFeasibilityData({ totalCostWon: 12345 });
    const stampBefore = useProjectContextStore.getState().updatedAt.feasibility;

    request.mockResolvedValueOnce({
      trade: { 아파트: { per_pyeong: { avg: 11161 } } },
    });
    post.mockResolvedValueOnce({}); // expert-panel(sales expertPanel:true)
    post.mockResolvedValueOnce({ verdict: "pass" }); // verify

    const { result } = renderHook(() => useNodeRunner());
    const res = await result.current.runNode("sales");
    expect(res.state).toBe("done");

    const feas = useProjectContextStore.getState().feasibilityData;
    // 환류값(원/평) stamp.
    expect(feas?.salePricePerPyeongWon).toBe(111_610_000);
    // 기존 수지 슬롯 보존(원가 미접촉).
    expect(feas?.totalCostWon).toBe(12345);
    // ★staleness 오염 없음 — updatedAt.feasibility 불변(수지 노드 skipped-fresh 함정 회피).
    expect(useProjectContextStore.getState().updatedAt.feasibility).toBe(stampBefore);
  });

  it("폐루프: stamp된 분양가(원/평)를 feasibility bodyBuilder가 avg_sale_price_per_pyeong으로 그대로 전송", async () => {
    useProjectContextStore.getState().updateSiteAnalysis({ address: "서울", landAreaSqm: 800, pnu: "1168010100100000000" });
    useProjectContextStore.getState().updateDesignData({
      totalGfaSqm: 3000, floorCount: 10, buildingType: "공동주택", bcr: 50, far: 200, unitCount: 40,
    });
    request.mockResolvedValueOnce({ trade: { 아파트: { per_pyeong: { avg: 11161 } } } });
    post.mockResolvedValueOnce({}); // expert-panel
    post.mockResolvedValueOnce({ verdict: "pass" }); // verify
    const { result } = renderHook(() => useNodeRunner());
    await result.current.runNode("sales");

    // feasibility bodyBuilder가 store 슬롯(원/평)을 무변환 전달해야 한다.
    const s = useProjectContextStore.getState();
    const ctx: NodeBodyContext = {
      siteAnalysis: s.siteAnalysis,
      designData: s.designData,
      feasibilityData: s.feasibilityData,
    };
    const { body } = buildNodeBody("feasibility", ctx, "p1");
    // ★폐루프: 분양가가 수지 입력단가로 흘러감(수지가 분양가에 무관하던 결함 해소).
    expect(body.avg_sale_price_per_pyeong).toBe(111_610_000);
    // 동반 co-requisite: 세대수·세대 전용면적도 함께 채워야 분양수입이 0이 아니게 산출됨(라이브 검증).
    expect(body.total_households).toBe(40);
    // ★면적정합(HIGH 수정): 전용단가에 곱하는 면적은 "전용면적 평"(연면적×전용률).
    //  공동주택 표준 전용률 0.76 → 전용평 = GFA(3000㎡) × 0.76 ÷ 3.305785 ÷ 40세대 ≈ 17.24평.
    //  (종전 22.68평=연면적 그대로 → 과대. 0.76배로 축소됨.)
    expect(body.avg_area_pyeong).toBeCloseTo((3000 * 0.76) / 3.305785 / 40, 2);
  });

  it("실거래 자료 없음(trade 부재)이면 분양가 미stamp → bodyBuilder는 단가 미주입(무회귀)", async () => {
    useProjectContextStore.getState().updateSiteAnalysis({ address: "서울", landAreaSqm: 800, pnu: "1168010100100000000" });
    useProjectContextStore.getState().updateDesignData({
      totalGfaSqm: 3000, floorCount: 10, buildingType: "공동주택", bcr: 50, far: 200,
    });
    request.mockResolvedValueOnce({ pricing_band: { fair_price_10k: 282100 } }); // 평당경로 없음
    post.mockResolvedValueOnce({}); // expert-panel
    post.mockResolvedValueOnce({ verdict: "pass" }); // verify
    const { result } = renderHook(() => useNodeRunner());
    await result.current.runNode("sales");

    expect(useProjectContextStore.getState().feasibilityData?.salePricePerPyeongWon ?? null).toBeNull();
    const { body } = buildNodeBody("feasibility", {
      siteAnalysis: useProjectContextStore.getState().siteAnalysis,
      designData: useProjectContextStore.getState().designData,
      feasibilityData: useProjectContextStore.getState().feasibilityData,
    }, "p1");
    // 단가 미주입 → 백엔드 기본 0(종전과 동일 동작, 무회귀).
    expect(body.avg_sale_price_per_pyeong).toBeUndefined();
  });
});
