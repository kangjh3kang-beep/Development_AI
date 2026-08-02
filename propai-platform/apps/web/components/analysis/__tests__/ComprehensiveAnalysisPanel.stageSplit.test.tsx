/**
 * W2-c 2단계 점진 렌더 배선 잠금.
 *
 * ★배경: 종합분석은 오리진 190초인데 CF 엣지가 ~125초에서 끊어 **분석 전체가 사라졌다**.
 * 1단계(결정론)를 먼저 받아 렌더하고 2단계(AI 해석)를 병합한다. 핵심 이득은
 * "2단계가 실패해도 1단계 결과를 잃지 않는다"이므로 그것을 회귀락으로 고정한다.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * ★경로 기반 목: 호출 **순서**가 아니라 **경로**로 응답을 정한다.
 * 순서 기반(mockResolvedValueOnce 연쇄)은 파이프라인에 호출이 하나 추가되는 순간 전부
 * 어긋난다 — 실제로 W2-d에서 POI 자동조회가 붙자 W2-c 테스트 5건이 깨졌다.
 */
const routes = new Map<string, () => Promise<unknown>>();
const post = vi.fn<(path: string, opts?: unknown) => Promise<unknown>>(
  (path: string) => {
    const h = routes.get(path);
    return h ? h() : Promise.resolve({});
  },
);
/** 특정 경로의 응답을 지정. */
function onPost(path: string, handler: () => Promise<unknown>) {
  routes.set(path, handler);
}
/** 그 경로로 나간 호출만 센다(총 호출수 단언 금지 — 파이프라인 확장에 취약). */
function callsTo(path: string) {
  return post.mock.calls.filter((c) => c[0] === path);
}
// ★get은 마운트 시 LLM 프로바이더 목록을 부른다 — Promise를 돌려주지 않으면 effect에서 터진다.
const getRoutes = new Map<string, () => Promise<unknown>>();
const get = vi.fn<(path: string, opts?: unknown) => Promise<unknown>>(
  async (path: string) => {
    const h = getRoutes.get(path);
    if (h) return h();
    return { providers: [] };
  },
);
function onGet(path: string, handler: () => Promise<unknown>) {
  getRoutes.set(path, handler);
}
// ★모듈 전체를 대체하므로 하위 컴포넌트가 쓰는 export도 함께 제공해야 한다 —
//   빠뜨리면 "No export is defined on the mock"이 **unhandled rejection**으로만 새어나가
//   테스트는 초록인데 콘솔만 더러워진다(가짜 안전). 실제 모듈의 export 목록과 맞춘다.
vi.mock("@/lib/api-client", () => ({
  apiClient: {
    post: (path: string, opts?: unknown) => post(path, opts),
    get: (path: string, opts?: unknown) => get(path, opts),
  },
  hasAccessToken: () => true,
  resolveApiOrigin: () => "http://localhost:8000",
  apiV1BaseUrl: () => "http://localhost:8000/api/v1",
  ApiClientError: class ApiClientError extends Error {},
}));
vi.mock("@/components/precheck/SatongMapShell", () => ({ SatongMapShell: () => null }));

import { ComprehensiveAnalysisPanel } from "@/components/analysis/ComprehensiveAnalysisPanel";
import { useProjectContextStore } from "@/store/useProjectContextStore";

const ADDRESS = "경북 포항시 남구 호미곶면 대보리 산1-1";

const CORE = {
  address: "경북 포항시 남구 호미곶면 대보리 산1-1",
  zone_type: "보전관리지역",
  land_area_sqm: 152826,
  ai_interpretation: null,
  ai_interpretation_status: { status: "deferred", reason: "다음 단계에서 생성" },
  market_interpretation: null,
  market_interpretation_status: { status: "deferred", reason: "다음 단계에서 생성" },
};

const PARTS = {
  ai_interpretation: { overall_summary: "보전관리지역 임야로 개발 제약이 큽니다." },
  ai_interpretation_status: { status: "ok" },
  market_interpretation: { summary: "인근 실거래가 희소합니다." },
  market_interpretation_status: { status: "ok" },
};

/** 주소는 입력란이 아니라 프로젝트 컨텍스트 스토어(siteAnalysis)에서 온다 — 지도 선택 경로. */
async function runAnalysis() {
  useProjectContextStore.setState({
    siteAnalysis: { address: ADDRESS, zoneCode: "보전관리지역" } as never,
  });
  render(<ComprehensiveAnalysisPanel />);
  const btn = await screen.findByRole("button", { name: /종합 분석 시작/ });
  await waitFor(() => expect(btn).not.toBeDisabled());
  await userEvent.click(btn);
}

beforeEach(() => {
  post.mockClear();
  routes.clear();
  getRoutes.clear();
  // 파이프라인 부수 호출(POI·시뮬)은 기본적으로 무해한 응답으로 흘린다.
  onPost("/site-score/poi-infra", async () => ({ score: 60 }));
  onPost("/development-methods/scenarios", async () => ({}));
  useProjectContextStore.setState({ siteAnalysis: null } as never);
});

describe("종합분석 2단계 점진 렌더", () => {
  it("★1단계는 include_interpretation:false로 호출한다(엣지 컷오프 회피)", async () => {
    onPost("/analysis/comprehensive", async () => CORE);
    onPost("/analysis/interpretation", async () => PARTS);
    await runAnalysis();

    await waitFor(() => expect(callsTo("/analysis/comprehensive")).toHaveLength(1));
    const [, opts] = callsTo("/analysis/comprehensive")[0] as [string, { body: Record<string, unknown> }];
    expect(opts.body.include_interpretation).toBe(false);
  });

  it("★2단계는 해석 전용 엔드포인트에 1단계 결과를 넘긴다(전체 재실행 금지)", async () => {
    onPost("/analysis/comprehensive", async () => CORE);
    onPost("/analysis/interpretation", async () => PARTS);
    await runAnalysis();

    await waitFor(() => expect(callsTo("/analysis/interpretation")).toHaveLength(1));
    const [, opts] = callsTo("/analysis/interpretation")[0] as [string, { body: Record<string, unknown> }];
    expect(opts.body.result).toMatchObject({ zone_type: "보전관리지역" });
    // ★2단계가 comprehensive를 다시 부르면 190초가 반복된다.
    expect(callsTo("/analysis/comprehensive")).toHaveLength(1);
  });

  it("1단계 결과가 2단계 완료 전에 이미 렌더된다(점진 렌더)", async () => {
    let releaseStage2: (v: unknown) => void = () => {};
    onPost("/analysis/comprehensive", async () => CORE);
    onPost("/analysis/interpretation", () => new Promise((res) => { releaseStage2 = res; }));
    await runAnalysis();

    // 2단계가 아직 안 끝났는데 1단계 값이 화면에 있어야 한다.
    await waitFor(() => expect(screen.getByText(/보전관리지역/)).toBeTruthy());
    expect(screen.getByText(/AI 종합 해석을 생성하고 있습니다/)).toBeTruthy();

    releaseStage2(PARTS);
    await waitFor(() => expect(screen.getByText(/개발 제약이 큽니다/)).toBeTruthy());
  });

  it("★★2단계가 실패해도 1단계 결과를 잃지 않는다(이번 웨이브의 핵심 이득)", async () => {
    onPost("/analysis/comprehensive", async () => CORE);
    onPost("/analysis/interpretation", async () => { throw new Error("타임아웃"); });
    await runAnalysis();

    await waitFor(() => expect(callsTo("/analysis/interpretation")).toHaveLength(1));
    // 분석 본문은 그대로 남는다.
    await waitFor(() => expect(screen.getByText(/보전관리지역/)).toBeTruthy());
    // 해석만 정직하게 실패 표기된다.
    expect(screen.getByText(/AI 종합 해석을 생성하지 못했습니다/)).toBeTruthy();
    expect(screen.getByText(/위 분석 결과는 정상적으로 산출되었습니다/)).toBeTruthy();
  });

  it("★해석 실패를 '분석 실패'로 승격하지 않는다(전역 에러 배너 금지)", async () => {
    onPost("/analysis/comprehensive", async () => CORE);
    onPost("/analysis/interpretation", async () => { throw new Error("타임아웃"); });
    await runAnalysis();

    await waitFor(() => expect(callsTo("/analysis/interpretation")).toHaveLength(1));
    expect(screen.queryByText(/종합분석 중 오류가 발생했습니다/)).toBeNull();
  });

  it("1단계가 실패하면 2단계를 부르지 않는다(무의미한 호출·중복 과금 방지)", async () => {
    onPost("/analysis/comprehensive", async () => { throw new Error("주소 해석 실패"); });
    await runAnalysis();

    await waitFor(() => expect(callsTo("/analysis/comprehensive")).toHaveLength(1));
    expect(callsTo("/analysis/interpretation")).toHaveLength(0);
    expect(screen.getByText(/주소 해석 실패/)).toBeTruthy();
  });
});

describe("W2-d 파이프라인 편입(POI·개발방식 시뮬 자동 실행)", () => {
  it("★종합분석 시작이 입지 인프라(POI) 조회를 함께 태운다(버튼 별도 클릭 불요)", async () => {
    onPost("/analysis/comprehensive", async () => CORE);
    onPost("/analysis/interpretation", async () => PARTS);
    await runAnalysis();

    await waitFor(() => expect(callsTo("/site-score/poi-infra")).toHaveLength(1));
  });

  it("POI 자동 조회는 종합분석 1단계 완료를 기다리지 않는다(병렬 — 빈 카드 시간 최소화)", async () => {
    let releaseCore: (v: unknown) => void = () => {};
    onPost("/analysis/comprehensive", () => new Promise((res) => { releaseCore = res; }));
    await runAnalysis();

    // 1단계가 아직 안 끝났는데 POI는 이미 나갔어야 한다.
    await waitFor(() => expect(callsTo("/site-score/poi-infra")).toHaveLength(1));
    releaseCore(CORE);
  });

  it("★분석을 시작하지 않으면 자동 조회가 나가지 않는다(마운트만으로 과금 금지)", async () => {
    useProjectContextStore.setState({
      siteAnalysis: { address: ADDRESS, zoneCode: "보전관리지역" } as never,
    });
    render(<ComprehensiveAnalysisPanel />);
    await screen.findByRole("button", { name: /종합 분석 시작/ });

    // 마운트 직후에는 llm-providers(get)만 나가고 POI/시뮬 post는 없어야 한다.
    expect(callsTo("/site-score/poi-infra")).toHaveLength(0);
    expect(callsTo("/development-methods/scenarios")).toHaveLength(0);
  });
});


describe("AI 해석 비동기 잡(폴링)", () => {
  it("★job_id를 받으면 폴링해 결과를 병합한다", async () => {
    onPost("/analysis/comprehensive", async () => CORE);
    onPost("/analysis/interpretation", async () => ({ job_id: "interp_x", status: "pending" }));
    let polls = 0;
    onGet("/analysis/interpretation/interp_x", async () => {
      polls += 1;
      return polls < 2 ? { status: "pending" } : { status: "done", result: PARTS };
    });
    await runAnalysis();

    await waitFor(() => expect(screen.getByText(/개발 제약이 큽니다/)).toBeTruthy(), { timeout: 15000 });
    expect(polls).toBeGreaterThanOrEqual(2);
  }, 20000);

  it("★잡이 error면 1단계 결과를 유지한 채 해석만 실패 표기한다", async () => {
    onPost("/analysis/comprehensive", async () => CORE);
    onPost("/analysis/interpretation", async () => ({ job_id: "interp_e", status: "pending" }));
    onGet("/analysis/interpretation/interp_e", async () => ({ status: "error", error: "LLM 한도 초과" }));
    await runAnalysis();

    await waitFor(() => expect(screen.getByText(/AI 종합 해석을 생성하지 못했습니다/)).toBeTruthy(), { timeout: 15000 });
    expect(screen.getByText(/보전관리지역/)).toBeTruthy();
    expect(screen.queryByText(/종합분석 중 오류가 발생했습니다/)).toBeNull();
  }, 20000);

  it("★구버전 백엔드(동기 응답)도 그대로 수용한다(배포 순서 어긋남 방어)", async () => {
    onPost("/analysis/comprehensive", async () => CORE);
    onPost("/analysis/interpretation", async () => PARTS); // job_id 없음
    await runAnalysis();

    await waitFor(() => expect(screen.getByText(/개발 제약이 큽니다/)).toBeTruthy());
    // 폴링을 시도하지 않는다.
    expect(get.mock.calls.some((c) => String(c[0]).startsWith("/analysis/interpretation/"))).toBe(false);
  });
});
