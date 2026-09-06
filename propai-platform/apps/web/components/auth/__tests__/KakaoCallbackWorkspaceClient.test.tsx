import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  KakaoCallbackWorkspaceClient,
  LABELS,
} from "@/components/auth/KakaoCallbackWorkspaceClient";
import { apiClient } from "@/lib/api-client";

const { pushMock, replaceMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  replaceMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
    replace: replaceMock,
  }),
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
  apiClient: {
    post: vi.fn(),
  },
}));

// ★기대값을 컴포넌트에서 **파생**시킨다 — 형제(네이버·구글)와 같은 형태로 맞춘다.
//   문구를 다듬어도 「어느 상태에 어느 라벨이 뜨는가」라는 계약만 남는다.
const EN = LABELS.en;
const SUCCESS_TITLE = EN.successTitle;
const STATE_MISMATCH = EN.stateMismatch;
const MISSING = EN.missingParams;

describe("KakaoCallbackWorkspaceClient", () => {
  // ★파생은 자기지시라 공허해질 수 있다 — 셋이 모두 ""가 되면 어떤 배선이든 통과한다.
  it("기대 문구가 비어 있지 않고 서로 다르다 (공허 진리 방지)", () => {
    for (const [k, v] of Object.entries({ SUCCESS_TITLE, STATE_MISMATCH, MISSING })) {
      expect(v, `${k} 가 비었다`).toBeTruthy();
    }
    expect(new Set([SUCCESS_TITLE, STATE_MISMATCH, MISSING]).size).toBe(3);
  });

  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    pushMock.mockReset();
    replaceMock.mockReset();
    vi.mocked(apiClient.post).mockReset();
  });

  it("exchanges the Kakao code(+state), stores tokens, and enables dashboard entry", async () => {
    // 로그인 시작 시 보관한 state와 콜백 state가 일치 → 정상 교환.
    window.sessionStorage.setItem("kakao_oauth_state", "st-abc");
    vi.mocked(apiClient.post).mockResolvedValue({
      access_token: "kakao-access-001",
      refresh_token: "kakao-refresh-001",
      expires_in: 3600,
    });

    render(
      <KakaoCallbackWorkspaceClient
        locale="en"
        code="kakao-code-123"
        state="st-abc"
        redirectUri="https://propai.ai/auth/kakao/callback"
      />,
    );

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/auth/kakao/callback",
        expect.objectContaining({
          useMock: false,
          body: {
            code: "kakao-code-123",
            state: "st-abc",
            redirect_uri: "https://propai.ai/auth/kakao/callback",
          },
        }),
      );
    });

    expect(
      await screen.findByText(SUCCESS_TITLE),
    ).toBeInTheDocument();
    expect(window.localStorage.getItem("propai_access_token")).toBe(
      "kakao-access-001",
    );
    // 성공 후 보관 state 제거(재사용 방지).
    expect(window.sessionStorage.getItem("kakao_oauth_state")).toBeNull();
  });

  it("blocks the exchange on state mismatch (CSRF/session-fixation)", async () => {
    // 보관 state와 콜백 state 불일치 → 교환하지 않고 보안 오류 표시.
    window.sessionStorage.setItem("kakao_oauth_state", "st-legit");

    render(
      <KakaoCallbackWorkspaceClient
        locale="en"
        code="attacker-code"
        state="st-forged"
        redirectUri={null}
      />,
    );

    await waitFor(() => {
      expect(
        screen.getByText(STATE_MISMATCH),
      ).toBeInTheDocument();
    });
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("blocks the exchange when this browser did not initiate login (fail-closed, scenario A)", async () => {
    // ★로그인 CSRF 주벡터: 피해자가 로그인을 개시하지 않아 sessionStorage에 보관 state가 없다.
    //  공격자가 자기 인가코드+state를 담은 콜백 링크를 피해자에게 전달해도, fail-closed 가드가
    //  '보관값 없음'을 이유로 교환을 차단해야 한다(과거 fail-open이면 그대로 로그인되어 세션 고정).
    // sessionStorage는 비어 있음(로그인 미개시).
    render(
      <KakaoCallbackWorkspaceClient
        locale="en"
        code="attacker-code"
        state="attacker-state"
        redirectUri={null}
      />,
    );

    await waitFor(() => {
      expect(
        screen.getByText(STATE_MISMATCH),
      ).toBeInTheDocument();
    });
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("blocks when the state query is omitted (fail-closed, scenario B)", async () => {
    // 공격자가 콜백 URL에서 state를 아예 빼도(state=null) 교환되지 않아야 한다.
    window.sessionStorage.setItem("kakao_oauth_state", "st-legit");

    render(
      <KakaoCallbackWorkspaceClient
        locale="en"
        code="attacker-code"
        state={null}
        redirectUri={null}
      />,
    );

    // state 누락 → hasRequiredParams=false → missingParams(교환 없음).
    expect(
      screen.getByText(MISSING),
    ).toBeInTheDocument();
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("surfaces a parameter error when the callback payload is incomplete", async () => {
    render(
      <KakaoCallbackWorkspaceClient
        locale="en"
        code={null}
        state={null}
        redirectUri={null}
      />,
    );

    expect(
      screen.getByText(MISSING),
    ).toBeInTheDocument();
    expect(apiClient.post).not.toHaveBeenCalled();
  });
});
