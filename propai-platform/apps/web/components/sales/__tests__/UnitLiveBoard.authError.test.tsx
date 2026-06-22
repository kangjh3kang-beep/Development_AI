/**
 * #2 워크스페이스 iter-5 — UnitLiveBoard 의 WS 영구거부(onAuthError) 종단배선 렌더 테스트.
 *
 * 검증 포인트(반쪽출하 회귀 방지):
 *   1) onAuthError('unauthenticated', 4401) → '다시 로그인' 복구 배너 렌더 + 좀비 '재연결 시도' 미표기.
 *   2) onAuthError('forbidden', 4403)       → '현장 재진입' 복구 배너 렌더.
 *   3) onStatus('closed') 만(영구거부 없음)  → 복구 배너 미렌더(일시 단절은 '재연결 시도' 유지).
 *
 * ★unitBoardWs / salesApi 는 모듈 모킹으로 격리한다(실 WS/네트워크 없이 콜백 주입만으로
 *   UnitLiveBoard 의 종단배선 = 4번째 onAuthError 인자 전달 + 배너/라벨 분기를 검증).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act, fireEvent } from "@testing-library/react";
import type { AuthErrorReason, UnitBoardWsStatus } from "@/lib/unitBoardWs";

// connectUnitBoardWs 가 받은 콜백을 테스트가 직접 붙잡아 호출할 수 있게 보관.
type Captured = {
  onStatus?: (s: UnitBoardWsStatus) => void;
  onAuthError?: (reason: AuthErrorReason, code: number) => void;
};
const captured: Captured = {};

vi.mock("@/lib/unitBoardWs", () => ({
  connectUnitBoardWs: (
    _siteId: string,
    _onMessage: unknown,
    onStatus?: (s: UnitBoardWsStatus) => void,
    onAuthError?: (reason: AuthErrorReason, code: number) => void,
  ) => {
    captured.onStatus = onStatus;
    captured.onAuthError = onAuthError; // ★4번째 인자가 실제로 전달되는지(미배선 회귀) 포착.
    return { close: () => {}, getStatus: () => "connecting" as UnitBoardWsStatus };
  },
}));

// clearSiteToken 스파이를 테스트가 직접 단언할 수 있게 보관.
const clearSiteTokenSpy = vi.fn();

// 보드 조회는 빈 결과로 격리(네트워크 없이 컴포넌트만 렌더).
vi.mock("@/lib/salesApi", () => ({
  salesApi: () => ({
    get: vi.fn().mockResolvedValue({ units: [], counts: {} }),
    post: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
    del: vi.fn().mockResolvedValue({}),
  }),
  clearSiteToken: (...args: unknown[]) => clearSiteTokenSpy(...args),
}));

import UnitLiveBoard from "@/components/sales/UnitLiveBoard";

beforeEach(() => {
  captured.onStatus = undefined;
  captured.onAuthError = undefined;
  clearSiteTokenSpy.mockClear();
});

describe("UnitLiveBoard — WS onAuthError 종단배선", () => {
  it("4번째 onAuthError 인자를 connectUnitBoardWs 에 전달한다(미배선 회귀 방지)", () => {
    render(<UnitLiveBoard siteCode="site-1" />);
    expect(typeof captured.onAuthError).toBe("function");
  });

  it("unauthenticated(4401) → '다시 로그인' 배너 렌더 + 좀비 '재연결 시도' 미표기", async () => {
    render(<UnitLiveBoard siteCode="site-1" />);
    await act(async () => {
      captured.onStatus?.("closed");
      captured.onAuthError?.("unauthenticated", 4401);
    });
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "다시 로그인" })).toBeInTheDocument();
    expect(screen.getByText("연결 중단(조치 필요)")).toBeInTheDocument();
    // 거짓 '재연결 시도' 좀비 라벨이 사라졌는지.
    expect(screen.queryByText("연결 끊김(재연결 시도)")).not.toBeInTheDocument();
  });

  it("forbidden(4403) → '현장 재진입' 배너 렌더", async () => {
    render(<UnitLiveBoard siteCode="site-1" />);
    await act(async () => {
      captured.onStatus?.("closed");
      captured.onAuthError?.("forbidden", 4403);
    });
    expect(screen.getByRole("button", { name: "현장 재진입" })).toBeInTheDocument();
    expect(screen.getByText("연결 중단(조치 필요)")).toBeInTheDocument();
  });

  it("일시 단절(closed, 영구거부 없음) → 복구 배너 미렌더 + '재연결 시도' 유지", async () => {
    render(<UnitLiveBoard siteCode="site-1" />);
    await act(async () => {
      captured.onStatus?.("closed"); // 4429/네트워크 단절 등 일시 오류 시나리오.
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("연결 끊김(재연결 시도)")).toBeInTheDocument();
  });
});

// ── MED(iter-6→iter-7): recoverAuth 사유별 정합(처방=원인=착지) ───────────────────
// 4401(access JWT 만료) = access 토큰 폐기 + ★로그인 페이지 착지(라벨 '다시 로그인'=착지 일치).
//   (iter-7: 과거 reload 는 상위가 현장 재진입 모달로 착지해 라벨-착지 불일치였다 → assign(/login).)
// 4403(현장 멤버십 상실) = 현장 토큰(clearSiteToken) 폐기 + reload(상위 403 감지→현장 재진입). access 보존.
describe("UnitLiveBoard — recoverAuth 사유별 정합", () => {
  const ACCESS_KEY = "propai_access_token";
  let reloadSpy: ReturnType<typeof vi.fn>;
  let assignSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    // jsdom 의 location.reload/assign 는 미구현이라 스텁으로 대체(호출만 관찰).
    //  pathname 은 /{locale}/... 형태로 두어 recoverAuth 가 로케일을 추출(ko 폴백)하는지도 확인.
    reloadSpy = vi.fn();
    assignSpy = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...window.location, pathname: "/ko/sales/sites/site-1", reload: reloadSpy, assign: assignSpy },
    });
    // 실제 localStorage 에 access 토큰을 심어 두고, 복구 후 '실제로 사라졌는지' 효과를 관찰한다
    // (spyOn 보다 견고 — 컴포넌트가 어떤 경로로 지우든 결과로 검증).
    window.localStorage.setItem(ACCESS_KEY, "live-access-token");
  });

  it("4401(unauthenticated) 복구 → access 토큰 폐기(현장 토큰 보존) + 로그인 페이지 착지", async () => {
    render(<UnitLiveBoard siteCode="site-1" />);
    await act(async () => {
      captured.onStatus?.("closed");
      captured.onAuthError?.("unauthenticated", 4401);
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "다시 로그인" }));
    });
    expect(window.localStorage.getItem(ACCESS_KEY)).toBeNull(); // access 토큰 폐기됨.
    expect(clearSiteTokenSpy).not.toHaveBeenCalled();           // 현장 토큰은 건드리지 않음.
    // ★라벨='다시 로그인'=착지: 현장 재진입 모달(reload)이 아니라 플랫폼 로그인 페이지로 이동.
    expect(assignSpy).toHaveBeenCalledWith("/ko/login");
    expect(reloadSpy).not.toHaveBeenCalled();
  });

  it("4403(forbidden) 복구 → 현장 토큰만 폐기(access 토큰 보존) + reload", async () => {
    render(<UnitLiveBoard siteCode="site-1" />);
    await act(async () => {
      captured.onStatus?.("closed");
      captured.onAuthError?.("forbidden", 4403);
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "현장 재진입" }));
    });
    expect(clearSiteTokenSpy).toHaveBeenCalledWith("site-1");      // 현장 토큰 폐기.
    expect(window.localStorage.getItem(ACCESS_KEY)).toBe("live-access-token"); // access 토큰 보존.
    expect(reloadSpy).toHaveBeenCalled();
    expect(assignSpy).not.toHaveBeenCalled();                      // 4403 은 로그인 이동 아님.
  });
});
