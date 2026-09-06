import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConsentGate, isConsentExemptPath } from "@/components/auth/ConsentGate";
import { apiClient } from "@/lib/api-client";

vi.mock("@/lib/api-client", () => ({
  ApiClientError: class ApiClientError extends Error {
    payload: unknown;
    constructor(m: string, p?: unknown) {
      super(m);
      this.payload = p;
    }
  },
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const CHILD = "보호-자원-본문";

describe("ConsentGate", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.post).mockReset();
  });

  it("★동의 미완이면 본문 대신 동의 화면을 보인다", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ consent_pending: true });
    render(
      <ConsentGate locale="ko" pathname="/ko/projects" authed>
        <div>{CHILD}</div>
      </ConsentGate>,
    );
    expect(await screen.findByTestId("consent-gate")).toBeInTheDocument();
    // ★두 모집단 — 화면이 뜨는 것과 **본문이 가려지는 것**은 다른 축이다
    expect(screen.queryByText(CHILD)).toBeNull();
  });

  it("★동의 완료면 본문을 그대로 보인다(과잉 차단 방지)", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ consent_pending: false });
    render(
      <ConsentGate locale="ko" pathname="/ko/projects" authed>
        <div>{CHILD}</div>
      </ConsentGate>,
    );
    expect(await screen.findByText(CHILD)).toBeInTheDocument();
    expect(screen.queryByTestId("consent-gate")).toBeNull();
  });

  it("★조회 실패해도 막지 않는다 — 게이트 오작동이 서비스를 세우면 안 된다", async () => {
    vi.mocked(apiClient.get).mockRejectedValue(new Error("boom"));
    render(
      <ConsentGate locale="ko" pathname="/ko/projects" authed>
        <div>{CHILD}</div>
      </ConsentGate>,
    );
    expect(await screen.findByText(CHILD)).toBeInTheDocument();
  });

  it("★미인증은 조회조차 하지 않는다", () => {
    render(
      <ConsentGate locale="ko" pathname="/ko/projects" authed={false}>
        <div>{CHILD}</div>
      </ConsentGate>,
    );
    expect(screen.getByText(CHILD)).toBeInTheDocument();
    expect(apiClient.get).not.toHaveBeenCalled();
  });

  it("★필수 두 개를 안 누르면 제출하지 않는다", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    vi.mocked(apiClient.get).mockResolvedValue({ consent_pending: true });
    render(
      <ConsentGate locale="ko" pathname="/ko/projects" authed>
        <div>{CHILD}</div>
      </ConsentGate>,
    );
    await screen.findByTestId("consent-gate");
    await userEvent.click(screen.getByRole("button", { name: "동의하고 계속하기" }));
    expect(apiClient.post).not.toHaveBeenCalled();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("★필수 둘을 누르면 제출하고 본문이 열린다", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    vi.mocked(apiClient.get).mockResolvedValue({ consent_pending: true });
    vi.mocked(apiClient.post).mockResolvedValue(undefined);
    render(
      <ConsentGate locale="ko" pathname="/ko/projects" authed>
        <div>{CHILD}</div>
      </ConsentGate>,
    );
    await screen.findByTestId("consent-gate");
    const boxes = screen.getAllByRole("checkbox");
    await userEvent.click(boxes[0]);
    await userEvent.click(boxes[1]);
    await userEvent.click(screen.getByRole("button", { name: "동의하고 계속하기" }));
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledTimes(1));
    const [path, opts] = vi.mocked(apiClient.post).mock.calls[0] as [string, { body: Record<string, boolean> }];
    expect(path).toBe("/auth/me/consents");
    // ★필드 이름이 서버 계약과 같아야 한다 — 다르면 조용히 400 이 난다
    expect(opts.body).toEqual({ agree_terms: true, agree_privacy: true, agree_marketing: false });
    expect(await screen.findByText(CHILD)).toBeInTheDocument();
  });
});

describe("면제 경로", () => {
  it("★약관을 읽을 수 있어야 동의할 수 있다", () => {
    expect(isConsentExemptPath("/ko/legal/terms")).toBe(true);
    expect(isConsentExemptPath("/ko/legal/privacy")).toBe(true);
    expect(isConsentExemptPath("/ko/login")).toBe(true);
  });

  it("★음성 대조군 — 보호 자원은 면제되지 않는다(전부 면제면 게이트가 무의미)", () => {
    for (const p of ["/ko/projects", "/ko/dashboard", "/ko/mypage/profile"]) {
      expect(isConsentExemptPath(p), p).toBe(false);
    }
  });
});
