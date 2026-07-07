import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { buildPrimaryNav } from "./nav-config";
import { WorkspaceNavBar } from "./WorkspaceNavBar";

vi.mock("next/navigation", () => ({
  usePathname: () => "/en/market-insights",
}));

// 역할 판별 mock — 테스트별 제어(기본: 미해결 promise = 비관리자 pending 상태 유지).
const roleMocks = vi.hoisted(() => ({
  fetchAuthMeRole: vi.fn<() => Promise<string>>(() => new Promise<string>(() => {})),
  fetchIsAdmin: vi.fn<() => Promise<boolean>>(() => new Promise<boolean>(() => {})),
}));
vi.mock("@/lib/use-is-admin", () => roleMocks);

describe("WorkspaceNavBar", () => {
  it("renders compact workspace sections with priority links", () => {
    render(<WorkspaceNavBar sections={buildPrimaryNav("en")} />);

    const nav = screen.getByRole("navigation", { name: "Workspace navigation" });

    expect(within(nav).getByText("관제")).toBeInTheDocument();
    expect(within(nav).getByText("프로젝트")).toBeInTheDocument();
    expect(within(nav).getByText("시장·획득")).toBeInTheDocument();
    expect(within(nav).getByText("설계 센터")).toBeInTheDocument();

    const marketButton = within(nav).getByRole("button", { name: /시장·획득/ });
    fireEvent.mouseEnter(marketButton.parentElement!);

    expect(within(nav).getByRole("link", { name: "시장·시세 분석" })).toHaveAttribute(
      "href",
      "/en/market-insights",
    );
    // 분양 관리는 코어 워크플로우라 일반 사용자에게도 노출(구 IA "분양 현장 관리" 복원).
    expect(within(nav).getByText("분양 관리")).toBeInTheDocument();
    expect(within(nav).queryByText("관리")).not.toBeInTheDocument();
  });

  it("keeps only one dropdown menu open on rollover", () => {
    render(<WorkspaceNavBar sections={buildPrimaryNav("en")} />);

    const nav = screen.getByRole("navigation", { name: "Workspace navigation" });
    const marketButton = within(nav).getByRole("button", { name: /시장·획득/ });
    const projectButton = within(nav).getByRole("button", { name: /프로젝트/ });

    fireEvent.mouseEnter(marketButton.parentElement!);
    expect(within(nav).getByRole("link", { name: "시장·시세 분석" })).toBeInTheDocument();

    fireEvent.mouseEnter(projectButton.parentElement!);
    expect(within(nav).queryByRole("link", { name: "시장·시세 분석" })).not.toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "프로젝트 관리" })).toBeInTheDocument();
  });

  it("closes the dropdown after rollout or item selection", () => {
    vi.useFakeTimers();

    try {
      render(<WorkspaceNavBar sections={buildPrimaryNav("en")} />);
      act(() => {
        vi.runOnlyPendingTimers();
      });

      const nav = screen.getByRole("navigation", { name: "Workspace navigation" });
      const projectButton = within(nav).getByRole("button", { name: /프로젝트/ });

      fireEvent.mouseEnter(projectButton.parentElement!);
      expect(within(nav).getByRole("link", { name: "프로젝트 관리" })).toBeInTheDocument();

      fireEvent.mouseLeave(projectButton.parentElement!);
      expect(within(nav).getByRole("link", { name: "프로젝트 관리" })).toBeInTheDocument();

      act(() => {
        vi.advanceTimersByTime(140);
      });
      expect(within(nav).queryByRole("link", { name: "프로젝트 관리" })).not.toBeInTheDocument();

      fireEvent.click(projectButton);
      const projectLink = within(nav).getByRole("link", { name: "프로젝트 관리" });
      fireEvent.click(projectLink);
      expect(within(nav).queryByRole("link", { name: "프로젝트 관리" })).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps the dropdown open while the pointer crosses into the menu", () => {
    vi.useFakeTimers();

    try {
      render(<WorkspaceNavBar sections={buildPrimaryNav("en")} />);
      act(() => {
        vi.runOnlyPendingTimers();
      });

      const nav = screen.getByRole("navigation", { name: "Workspace navigation" });
      const projectButton = within(nav).getByRole("button", { name: /프로젝트/ });

      fireEvent.mouseEnter(projectButton.parentElement!);
      expect(within(nav).getByRole("link", { name: "프로젝트 관리" })).toBeInTheDocument();

      fireEvent.mouseLeave(projectButton.parentElement!);
      const bridge = within(nav).getByTestId(/workspace-nav-hover-bridge-/);
      fireEvent.mouseEnter(bridge);

      act(() => {
        vi.advanceTimersByTime(220);
      });
      expect(within(nav).getByRole("link", { name: "프로젝트 관리" })).toBeInTheDocument();

      fireEvent.mouseLeave(projectButton.parentElement!);
      act(() => {
        vi.advanceTimersByTime(140);
      });
      expect(within(nav).queryByRole("link", { name: "프로젝트 관리" })).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("관리자 로그인 시 역할 게이트 섹션(관리)까지 전부 노출된다 — 절단 회귀 방지", async () => {
    // 근본원인 회귀 테스트: 과거 slice(0,5)가 관리자에게 6번째가 되는 '관리' 섹션을 잘라
    // 관리자 메뉴가 사라졌다. 역할 판별이 완료되면 게이트 통과 섹션은 하나도 잘리지 않아야 한다.
    roleMocks.fetchIsAdmin.mockResolvedValueOnce(true);
    roleMocks.fetchAuthMeRole.mockResolvedValueOnce("admin");

    render(<WorkspaceNavBar sections={buildPrimaryNav("en")} />);
    // fetchIsAdmin/fetchAuthMeRole promise 해소 → isAdmin 상태 반영까지 플러시
    await act(async () => {
      await Promise.resolve();
    });

    const nav = screen.getByRole("navigation", { name: "Workspace navigation" });
    // 일반 5섹션(분양 관리 포함) + 역할 게이트 1섹션(관리=admin) 전부 존재
    for (const title of ["관제", "프로젝트", "시장·획득", "설계 센터", "분양 관리", "관리"]) {
      expect(within(nav).getByText(title)).toBeInTheDocument();
    }
  });
});
