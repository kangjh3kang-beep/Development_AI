import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  GoogleCallbackWorkspaceClient,
  LABELS,
} from "@/components/auth/GoogleCallbackWorkspaceClient";
import { apiClient } from "@/lib/api-client";

const { pushMock, replaceMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  replaceMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
}));

vi.mock("@/lib/api-client", () => ({
  ApiClientError: class ApiClientError extends Error {
    status: number;
    payload: unknown;
    constructor(message: string, status: number, payload: unknown) {
      super(message);
      this.status = status;
      this.payload = payload;
    }
  },
  apiClient: { post: vi.fn() },
}));

const EN = LABELS.en;
const SUCCESS = EN.success;
const STATE_MISMATCH = EN.stateMismatch;
const MISSING = EN.missingParams;

describe("GoogleCallbackWorkspaceClient", () => {
  // ★파생은 자기지시라 공허해질 수 있다 — 셋이 모두 ""가 되면 어떤 배선이든 통과한다.
  //   세 상태를 가르는 것이 이 문구들이므로, 같아지는 순간 판별력이 0이 된다.
  it("기대 문구가 비어 있지 않고 서로 다르다 (공허 진리 방지)", () => {
    for (const [k, v] of Object.entries({ SUCCESS, STATE_MISMATCH, MISSING })) {
      expect(v, `${k} 가 비었다`).toBeTruthy();
    }
    expect(new Set([SUCCESS, STATE_MISMATCH, MISSING]).size).toBe(3);
  });

  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    pushMock.mockReset();
    replaceMock.mockReset();
    vi.mocked(apiClient.post).mockReset();
  });

  it("exchanges the Google code(+state) when the saved state matches", async () => {
    window.sessionStorage.setItem("google_oauth_state", "st-g");
    vi.mocked(apiClient.post).mockResolvedValue({
      access_token: "g-access-001",
      refresh_token: "g-refresh-001",
      expires_in: 3600,
    });

    render(
      <GoogleCallbackWorkspaceClient
        locale="en"
        code="g-code-123"
        state="st-g"
        redirectUri="https://propai.ai/auth/google/callback"
      />,
    );

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/auth/google/callback",
        expect.objectContaining({
          useMock: false,
          body: {
            code: "g-code-123",
            state: "st-g",
            redirect_uri: "https://propai.ai/auth/google/callback",
          },
        }),
      );
    });
    expect(await screen.findByText(SUCCESS)).toBeInTheDocument();
    expect(window.localStorage.getItem("propai_access_token")).toBe("g-access-001");
    expect(window.sessionStorage.getItem("google_oauth_state")).toBeNull();
  });

  it("blocks on state mismatch (CSRF/session-fixation)", async () => {
    window.sessionStorage.setItem("google_oauth_state", "st-legit");
    render(
      <GoogleCallbackWorkspaceClient locale="en" code="attacker" state="st-forged" redirectUri={null} />,
    );
    await waitFor(() => expect(screen.getByText(STATE_MISMATCH)).toBeInTheDocument());
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("blocks when this browser did not initiate login (fail-closed, scenario A)", async () => {
    // sessionStorage 비어 있음(로그인 미개시) → fail-closed 차단.
    render(
      <GoogleCallbackWorkspaceClient locale="en" code="attacker" state="attacker-state" redirectUri={null} />,
    );
    await waitFor(() => expect(screen.getByText(STATE_MISMATCH)).toBeInTheDocument());
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("blocks when the state query is omitted (fail-closed, scenario B)", async () => {
    window.sessionStorage.setItem("google_oauth_state", "st-legit");
    render(
      <GoogleCallbackWorkspaceClient locale="en" code="attacker" state={null} redirectUri={null} />,
    );
    expect(screen.getByText(MISSING)).toBeInTheDocument();
    expect(apiClient.post).not.toHaveBeenCalled();
  });
});
