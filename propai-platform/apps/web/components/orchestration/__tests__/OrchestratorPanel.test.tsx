// OrchestratorPanel 컨테이너 렌더 스모크 — Phase B B3
// 선택 모드: 레지스트리 구동 셀렉터 + 모드스위처 렌더. 별도 모드: 노드 단건 버튼 렌더.
// apiClient는 mock(실호출 차단). 데이터/오케스트레이션 store는 setState로 초기화.

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// apiClient mock — runner(request)/expert·verify(post) 실호출 차단·관측.
const post = vi.fn();
const request = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: {
    post: (...a: unknown[]) => post(...a),
    request: (...a: unknown[]) => request(...a),
  },
  resolveApiOrigin: () => "https://api.test",
}));

// @propai/ui(jsxDEV 사전번들)는 vitest 환경에서 import 실패 → 단순 래퍼를 div로 mock(렌더 스모크용).
vi.mock("@propai/ui", () => ({
  Card: ({ children, ...p }: { children?: React.ReactNode }) => <div {...p}>{children}</div>,
  CardContent: ({ children, ...p }: { children?: React.ReactNode }) => <div {...p}>{children}</div>,
}));

import { OrchestratorPanel } from "@/components/orchestration/OrchestratorPanel";
import { useOrchestrationStore } from "@/store/useOrchestrationStore";
import { useProjectContextStore } from "@/store/useProjectContextStore";

beforeEach(() => {
  post.mockReset();
  request.mockReset();
  useOrchestrationStore.setState({
    runMode: "selective",
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
});

describe("OrchestratorPanel — 선택 모드 렌더", () => {
  it("모드스위처 + 레지스트리 구동 셀렉터(노드 라벨) 렌더", () => {
    render(<OrchestratorPanel scopeNodes={["land", "sales", "feasibility"]} />);
    // 모드스위처 탭.
    expect(screen.getByRole("tab", { name: /선택/ })).toBeInTheDocument();
    // nodesToOptions가 그룹 라벨 + 노드 라벨을 생성.
    expect(screen.getByText("토지·부지분석")).toBeInTheDocument();
    expect(screen.getByText("분양성·분양가")).toBeInTheDocument();
    expect(screen.getByText("사업수지·ROI")).toBeInTheDocument();
  });

  it("coinCost는 balance.module_fees에서(미설정 0=무료, 하드코딩 금지)", () => {
    render(
      <OrchestratorPanel
        scopeNodes={["sales"]}
        balance={{ module_fees: { "stage:sales": 3000 } }}
      />,
    );
    // 셀렉터가 +3,000원 표기(요율 주입 확인).
    expect(screen.getByText(/\+3,000원/)).toBeInTheDocument();
  });
});

describe("OrchestratorPanel — 별도 모드 렌더", () => {
  it("standalone 전환 시 노드 단건 버튼 그리드 렌더", () => {
    render(<OrchestratorPanel scopeNodes={["land", "sales"]} />);
    fireEvent.click(screen.getByRole("tab", { name: /별도/ }));
    expect(screen.getByText("분석 단독 실행")).toBeInTheDocument();
    // 노드 단건 버튼(라벨 표기).
    expect(screen.getByText("토지·부지분석")).toBeInTheDocument();
  });
});

describe("OrchestratorPanel — standalone 자동실행이 실제 노드를 실행한다(수정1)", () => {
  it("입력 확보된 land를 별도 클릭→'바로 실행'하면 runner가 1회 호출된다(빈 plan 무실행 회귀 가드)", async () => {
    // land 입력(주소) 확보 → 모달은 allReady → '바로 실행'.
    useProjectContextStore.getState().updateSiteAnalysis({ address: "서울 강남구" });
    request.mockResolvedValueOnce({ landAreaSqm: 800, zoneCode: "제2종일반주거" });
    post.mockResolvedValueOnce({ verdict: "pass" }); // /verify/analysis

    render(<OrchestratorPanel scopeNodes={["land", "sales"]} />);
    fireEvent.click(screen.getByRole("tab", { name: /별도/ }));
    // land 단건 버튼 클릭 → 모달.
    fireEvent.click(screen.getByText("토지·부지분석"));
    const runBtn = await screen.findByRole("button", { name: /바로 실행/ });
    fireEvent.click(runBtn);

    // ★executePlan이 buildPlan 재호출(seed 없음)로 빈 plan을 만들지 않고 실제 land를 실행해야 한다.
    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(String(request.mock.calls[0][0])).toContain("/api/v1/zoning/analyze");
  });

  it("업스트림 자동실행 동의(2인자)→폐포가 상류부터 실행(design 클릭 시 land도 실행)", async () => {
    // 입력 전무 → design은 missing(siteAnalysis·compliance). 모달의 '업스트림 자동실행' 동의.
    // 폐포 = land·legal·recommend·design. runner는 폐포 노드 순서대로 호출되어야 한다.
    request.mockResolvedValue({}); // 모든 runner 응답(부분/빈)
    post.mockResolvedValue({ verdict: "pass" }); // expert-panel/verify 공용

    render(<OrchestratorPanel scopeNodes={["design"]} />);
    fireEvent.click(screen.getByRole("tab", { name: /별도/ }));
    fireEvent.click(screen.getByText("건축개요·설계 AI"));
    const autoBtn = await screen.findByRole("button", { name: /업스트림 .*자동 실행/ });
    fireEvent.click(autoBtn);

    // 폐포 첫 노드 land가 실제로 실행(입력 자동주입 경로 — land는 주소 미확보라 skipped-unavailable이지만
    // 폐포 선두로서 실행 시도 자체는 일어난다). 최소한 runner 또는 needs-input/skip 경로로 노드가 처리된다.
    // 여기서는 "빈 plan 무실행"이 아님을 보증: 오케스트레이션 nodeResult에 폐포 노드 상태가 기록된다.
    await waitFor(() => {
      const nr = useOrchestrationStore.getState().nodeResult;
      // land는 주소 미확보 → skipped-unavailable로라도 처리(실행 경로 도달).
      expect(nr["land"]).toBeDefined();
    });
  });
});

describe("OrchestratorPanel — 수동입력 값 실제 SSOT 주입(수정2)", () => {
  it("land 모달에 주소 입력→'입력값으로 실행' 시 updateSiteAnalysis(source:user) 주입 후 실행", async () => {
    // 입력 전무 → land는 missing(siteAnalysis.address, manual 폼 노출).
    request.mockResolvedValueOnce({ landAreaSqm: 700 });
    post.mockResolvedValueOnce({ verdict: "pass" });

    render(<OrchestratorPanel scopeNodes={["land"]} />);
    fireEvent.click(screen.getByRole("tab", { name: /별도/ }));
    fireEvent.click(screen.getByText("토지·부지분석"));

    // 수동입력 폼(manualPrompt placeholder) → 주소 입력.
    const input = await screen.findByPlaceholderText(/주소 또는 PNU/);
    fireEvent.change(input, { target: { value: "서울특별시 종로구 1-1" } });
    const submit = screen.getByRole("button", { name: /입력값으로 실행/ });
    fireEvent.click(submit);

    // ★조용히 버려지지 않고 실제 SSOT에 user 출처로 주입되어야 한다.
    await waitFor(() => {
      const site = useProjectContextStore.getState().siteAnalysis;
      expect(site?.address).toBe("서울특별시 종로구 1-1");
    });
    // user 머지가드 stamp 확인.
    const prov = useProjectContextStore.getState().getFieldProvenance("siteAnalysis", "address");
    expect(prov?.source).toBe("user");
    // 주입 후 노드 실행(runner 호출).
    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
  });
});

describe("OrchestratorPanel — 상류 실패 시 하류 미실행·차단(수정4)", () => {
  it("land가 error면 같은 plan의 하류(feasibility 등)는 runner 미호출+blocked 표기", async () => {
    // feasibility 선택 → 폐포 = land·legal·recommend·design·sales·qto·feasibility.
    // land 입력(주소) 확보로 실행 진입시키되, '전체 자동분석'(force) 경로로 신선분 스킵을 풀어 land가 실제로 runner 진입→실패하게 한다.
    useProjectContextStore.getState().updateSiteAnalysis({ address: "서울 강남구" });
    useOrchestrationStore.getState().setPicked({ feasibility: true });
    // 첫 runner 호출(land) 실패. 이후 호출은 일어나면 안 됨(하류 차단).
    request.mockRejectedValueOnce(new Error("500"));
    post.mockResolvedValue({ verdict: "pass" });

    render(<OrchestratorPanel scopeNodes={["feasibility"]} />);
    // '전체 자동분석' 1클릭(force 미리보기) → 2클릭(force 실행). force라 land(신선)도 실행 시도.
    const allBtn = await screen.findByRole("button", { name: /전체 자동분석/ });
    fireEvent.click(allBtn); // 1클릭: 미리보기
    fireEvent.click(allBtn); // 2클릭: 실행

    await waitFor(() => {
      const nr = useOrchestrationStore.getState().nodeResult;
      expect(nr["land"]?.state).toBe("error");
    });
    // ★land가 실패했으므로 runner는 land 1회만 호출(하류 runner 미호출 — 빈입력 호출·과금 방지).
    expect(request).toHaveBeenCalledTimes(1);
    // 하류 노드는 차단(skipped-unavailable) 표기.
    const nr = useOrchestrationStore.getState().nodeResult;
    expect(nr["feasibility"]?.state).toBe("skipped-unavailable");
  });
});
