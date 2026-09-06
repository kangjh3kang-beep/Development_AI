import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  LABELS,
  NaverCallbackWorkspaceClient,
} from "@/components/auth/NaverCallbackWorkspaceClient";
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

describe("NaverCallbackWorkspaceClient", () => {
  // ★파생은 자기지시라 공허해질 수 있다 — 셋이 모두 ""가 되면 어떤 배선이든 통과한다.
  //   세 상태를 가르는 것이 이 문구들이므로, 같아지는 순간 판별력이 0이 된다.
  it("기대 문구가 비어 있지 않고 서로 다르다 (공허 진리 방지)", () => {
    for (const [k, v] of Object.entries({ SUCCESS, STATE_MISMATCH, MISSING })) {
      expect(v, `${k} 가 비었다`).toBeTruthy();
    }
    expect(new Set([SUCCESS, STATE_MISMATCH, MISSING]).size).toBe(3);
  });

  // ★제목이 **상태를 따라간다** — 오류인데 성공 제목을 띄우면 화면이 거짓말을 한다.
  //   2026-09-06 라이브 실측: 파라미터 없이 콜백을 열면 본문은 실패를 말하는데
  //   제목은 「로그인되었습니다」였다(형제 카카오만 errorTitle 을 갖고 있었다 · §29).
  it("★오류 상태에서 성공 제목이 뜨지 않고 오류 제목이 뜬다", () => {
    // 세 제목이 서로 달라야 판별력이 있다(같으면 어떤 배선이든 통과)
    expect(new Set([EN.loadingTitle, EN.successTitle, EN.errorTitle]).size).toBe(3);
    render(
      <NaverCallbackWorkspaceClient locale="en" code={null} state={null} redirectUri={null} />,
    );
    expect(screen.getByText(EN.errorTitle)).toBeInTheDocument();
    expect(screen.queryByText(EN.successTitle)).toBeNull();
  });

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
