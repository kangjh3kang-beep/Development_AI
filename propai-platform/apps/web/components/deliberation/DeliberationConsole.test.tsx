import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { postMock, FakeApiClientError } = vi.hoisted(() => {
  class FakeApiClientError extends Error {
    status: number;
    payload: unknown;
    constructor(message: string, status: number, payload: unknown) {
      super(message);
      this.name = "ApiClientError";
      this.status = status;
      this.payload = payload;
    }
  }
  return { postMock: vi.fn(), FakeApiClientError };
});

vi.mock("@/lib/api-client", () => ({
  apiClient: { post: (...args: unknown[]) => postMock(...args) },
  ApiClientError: FakeApiClientError,
}));

import { DeliberationConsole } from "@/components/deliberation/DeliberationConsole";

const RESULT = {
  input_hash: "abc123def456ghi7",
  snapshot_id: "snap-1",
  preflight: null,
  legal_quantities: [],
  findings: [{
    rule_id: "far_limit", verdict: "NON_COMPLIANT", measured_value: 250,
    limit_value: 200, basis_article: "국토계획법", requires_committee: false,
  }],
  sim_metrics: [],
  precedent: null,
  qualitative: [],
  report: { sections: {} },
  skipped: [],
};
const ENVELOPE_OK = {
  degraded: false, reused: false, deterministic: true, run_id: "r1",
  audit_degraded: false, audit_skipped: [], result: RESULT,
};

describe("DeliberationConsole (중심엔진 BFF 경유)", () => {
  beforeEach(() => postMock.mockReset());

  it("분석 제출이 BFF /deliberation/analyze로 라우팅된다(엔진 직결 아님)", async () => {
    postMock.mockResolvedValue(ENVELOPE_OK);
    render(<DeliberationConsole />);
    fireEvent.click(screen.getByText("심의분석 실행"));
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    const [path, opts] = postMock.mock.calls[0] as [string, { body: Record<string, unknown> }];
    expect(path).toBe("/deliberation/analyze");
    expect(opts.body).toMatchObject({ pnu: expect.any(String) }); // 파싱된 JSON 본문 전달
  });

  it("정상 봉투 → 판정 결과 렌더", async () => {
    postMock.mockResolvedValue(ENVELOPE_OK);
    render(<DeliberationConsole />);
    fireEvent.click(screen.getByText("심의분석 실행"));
    expect(await screen.findByText("far_limit")).toBeInTheDocument();
    expect(screen.getByText("NON_COMPLIANT")).toBeInTheDocument();
  });

  it("degrade 봉투 → 사유 표면화(무음0), result=null이어도 크래시 없음", async () => {
    postMock.mockResolvedValue({
      degraded: true, reason: "engine_unreachable", result: null,
      audit_degraded: false, audit_skipped: [],
    });
    render(<DeliberationConsole />);
    fireEvent.click(screen.getByText("심의분석 실행"));
    expect(await screen.findByText(/engine_unreachable/)).toBeInTheDocument();
  });

  it("401 ApiClientError → 로그인 안내", async () => {
    postMock.mockRejectedValueOnce(new FakeApiClientError("unauthorized", 401, null));
    render(<DeliberationConsole />);
    fireEvent.click(screen.getByText("심의분석 실행"));
    expect(await screen.findByText(/로그인/)).toBeInTheDocument();
  });

  it("내부 엔진 오리진 URL을 노출하지 않는다(핑거프린트 차단)", () => {
    postMock.mockResolvedValue(ENVELOPE_OK);
    render(<DeliberationConsole />);
    expect(screen.queryByText(/localhost:8801/)).toBeNull();
    expect(screen.queryByText(/http:\/\//)).toBeNull();
  });
});
