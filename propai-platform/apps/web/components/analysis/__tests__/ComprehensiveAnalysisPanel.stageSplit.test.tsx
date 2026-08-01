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

const post = vi.fn<(path: string, opts?: unknown) => Promise<unknown>>();
// ★get은 마운트 시 LLM 프로바이더 목록을 부른다 — Promise를 돌려주지 않으면 effect에서 터진다.
const get = vi.fn<(path: string, opts?: unknown) => Promise<unknown>>(
  async () => ({ providers: [] }),
);
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
  post.mockReset();
  useProjectContextStore.setState({ siteAnalysis: null } as never);
});

describe("종합분석 2단계 점진 렌더", () => {
  it("★1단계는 include_interpretation:false로 호출한다(엣지 컷오프 회피)", async () => {
    post.mockResolvedValueOnce(CORE).mockResolvedValueOnce(PARTS);
    await runAnalysis();

    await waitFor(() => expect(post).toHaveBeenCalled());
    const [path, opts] = post.mock.calls[0] as [string, { body: Record<string, unknown> }];
    expect(path).toBe("/analysis/comprehensive");
    expect(opts.body.include_interpretation).toBe(false);
  });

  it("★2단계는 해석 전용 엔드포인트에 1단계 결과를 넘긴다(전체 재실행 금지)", async () => {
    post.mockResolvedValueOnce(CORE).mockResolvedValueOnce(PARTS);
    await runAnalysis();

    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    const [path, opts] = post.mock.calls[1] as [string, { body: Record<string, unknown> }];
    expect(path).toBe("/analysis/interpretation");
    expect(opts.body.result).toMatchObject({ zone_type: "보전관리지역" });
    // 2단계가 comprehensive를 다시 부르면 190초가 반복된다.
    expect(post.mock.calls.filter((c) => c[0] === "/analysis/comprehensive")).toHaveLength(1);
  });

  it("1단계 결과가 2단계 완료 전에 이미 렌더된다(점진 렌더)", async () => {
    let releaseStage2: (v: unknown) => void = () => {};
    post
      .mockResolvedValueOnce(CORE)
      .mockReturnValueOnce(new Promise((res) => { releaseStage2 = res; }));
    await runAnalysis();

    // 2단계가 아직 안 끝났는데 1단계 값이 화면에 있어야 한다.
    await waitFor(() => expect(screen.getByText(/보전관리지역/)).toBeTruthy());
    expect(screen.getByText(/AI 종합 해석을 생성하고 있습니다/)).toBeTruthy();

    releaseStage2(PARTS);
    await waitFor(() => expect(screen.getByText(/개발 제약이 큽니다/)).toBeTruthy());
  });

  it("★★2단계가 실패해도 1단계 결과를 잃지 않는다(이번 웨이브의 핵심 이득)", async () => {
    post.mockResolvedValueOnce(CORE).mockRejectedValueOnce(new Error("타임아웃"));
    await runAnalysis();

    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    // 분석 본문은 그대로 남는다.
    await waitFor(() => expect(screen.getByText(/보전관리지역/)).toBeTruthy());
    // 해석만 정직하게 실패 표기된다.
    expect(screen.getByText(/AI 종합 해석을 생성하지 못했습니다/)).toBeTruthy();
    expect(screen.getByText(/위 분석 결과는 정상적으로 산출되었습니다/)).toBeTruthy();
  });

  it("★해석 실패를 '분석 실패'로 승격하지 않는다(전역 에러 배너 금지)", async () => {
    post.mockResolvedValueOnce(CORE).mockRejectedValueOnce(new Error("타임아웃"));
    await runAnalysis();

    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(screen.queryByText(/종합분석 중 오류가 발생했습니다/)).toBeNull();
  });

  it("1단계가 실패하면 2단계를 부르지 않는다(무의미한 호출·중복 과금 방지)", async () => {
    post.mockRejectedValueOnce(new Error("주소 해석 실패"));
    await runAnalysis();

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls.some((c) => c[0] === "/analysis/interpretation")).toBe(false);
    expect(screen.getByText(/주소 해석 실패/)).toBeTruthy();
  });
});
