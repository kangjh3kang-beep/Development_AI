import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { NaverCallbackWorkspaceClient } from "@/components/auth/NaverCallbackWorkspaceClient";
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

const SUCCESS = "Naver authentication completed and the browser session has been stored.";
const STATE_MISMATCH =
  "Security check (state) mismatch — please try signing in again (CSRF protection).";
const MISSING =
  "The Naver callback payload is incomplete. Check that the code and state parameters are present.";

describe("NaverCallbackWorkspaceClient", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    pushMock.mockReset();
    replaceMock.mockReset();
    vi.mocked(apiClient.post).mockReset();
  });

  it("exchanges the Naver code(+state) when the saved state matches", async () => {
    window.sessionStorage.setItem("naver_oauth_state", "st-n");
    vi.mocked(apiClient.post).mockResolvedValue({
      access_token: "n-access-001",
      refresh_token: "n-refresh-001",
      expires_in: 3600,
    });

    render(
      <NaverCallbackWorkspaceClient
        locale="en"
        code="n-code-123"
        state="st-n"
        redirectUri="https://propai.ai/auth/naver/callback"
      />,
    );

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/auth/naver/callback",
        expect.objectContaining({
          useMock: false,
          body: {
            code: "n-code-123",
            state: "st-n",
            redirect_uri: "https://propai.ai/auth/naver/callback",
          },
        }),
      );
    });
    expect(await screen.findByText(SUCCESS)).toBeInTheDocument();
    expect(window.localStorage.getItem("propai_access_token")).toBe("n-access-001");
    expect(window.sessionStorage.getItem("naver_oauth_state")).toBeNull();
  });

  it("blocks on state mismatch (CSRF/session-fixation)", async () => {
    window.sessionStorage.setItem("naver_oauth_state", "st-legit");
    render(
      <NaverCallbackWorkspaceClient locale="en" code="attacker" state="st-forged" redirectUri={null} />,
    );
    await waitFor(() => expect(screen.getByText(STATE_MISMATCH)).toBeInTheDocument());
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("blocks when this browser did not initiate login (fail-closed, scenario A)", async () => {
    render(
      <NaverCallbackWorkspaceClient locale="en" code="attacker" state="attacker-state" redirectUri={null} />,
    );
    await waitFor(() => expect(screen.getByText(STATE_MISMATCH)).toBeInTheDocument());
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("shows a parameter error when state is omitted (naver requires code+state)", async () => {
    render(
      <NaverCallbackWorkspaceClient locale="en" code="c" state={null} redirectUri={null} />,
    );
    expect(screen.getByText(MISSING)).toBeInTheDocument();
    expect(apiClient.post).not.toHaveBeenCalled();
  });
});
