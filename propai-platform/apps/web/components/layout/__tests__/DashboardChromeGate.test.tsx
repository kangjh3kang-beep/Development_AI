import type { ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { NavSection } from "@/components/layout/nav-config";

const { pathnameRef } = vi.hoisted(() => ({ pathnameRef: { current: "/en" } }));

vi.mock("next/navigation", () => ({
  usePathname: () => pathnameRef.current,
}));

// 크롬 하위 컴포넌트는 존재 여부만 검증하면 되므로 가벼운 스텁으로 대체
// (WorkspaceNavBar 등은 관리자 판정 fetch 등 무거운 부수효과를 갖는다).
vi.mock("@/components/layout/WorkspaceNavBar", () => ({
  WorkspaceNavBar: () => <nav data-testid="workspace-nav-bar" />,
}));
vi.mock("@/components/layout/MobileSidebarToggle", () => ({
  MobileSidebarToggle: () => <button type="button" data-testid="mobile-sidebar-toggle" />,
}));
vi.mock("@/components/layout/HomeLink", () => ({
  HomeLink: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));
vi.mock("@/components/common/AIAssistant", () => ({ AIAssistant: () => null }));
vi.mock("@/components/common/ProjectSyncProvider", () => ({ ProjectSyncProvider: () => null }));
vi.mock("@/components/common/Disclaimer", () => ({
  Disclaimer: () => <div data-testid="disclaimer" />,
}));
vi.mock("@/components/auth/AuthButton", () => ({
  AuthButton: () => <div data-testid="auth-button" />,
}));
vi.mock("@/components/ui/LocaleSwitcher", () => ({
  LocaleSwitcher: () => <div data-testid="locale-switcher" />,
}));
vi.mock("@/components/ui/ThemeToggle", () => ({ ThemeToggle: () => <div data-testid="theme-toggle" /> }));
vi.mock("@/components/ui/Logo", () => ({ Logo: () => <div data-testid="logo" /> }));

// HomeGate(페이지 홈 콘텐츠 분기)가 지연 로드하는 DashboardHome을 결정적 스텁으로 대체.
vi.mock("next/dynamic", () => ({
  default: () => {
    const DashboardHomeStub = ({ locale }: { locale: string }) => (
      <div data-testid="dashboard-home">dashboard:{locale}</div>
    );
    return DashboardHomeStub;
  },
}));

import { DashboardChromeGate } from "@/components/layout/DashboardChromeGate";
import { HomeGate } from "@/components/marketing/HomeGate";

const sections: NavSection[] = [];

describe("DashboardChromeGate — 앱 크롬 표시 여부 분기", () => {
  beforeEach(() => {
    window.localStorage.clear();
    pathnameRef.current = "/en";
  });

  it("(a) 미인증 + 홈 라우트(/en) = 크롬 없이 children만 풀블리드 렌더", async () => {
    pathnameRef.current = "/en";

    render(
      <DashboardChromeGate locale="en" localeLabel="Language" runtimeModeLabel="LIVE" sections={sections}>
        <div data-testid="landing-marker">landing</div>
      </DashboardChromeGate>,
    );

    expect(await screen.findByTestId("landing-marker")).toBeInTheDocument();
    expect(screen.queryByTestId("workspace-nav-bar")).not.toBeInTheDocument();
    expect(screen.queryByTestId("disclaimer")).not.toBeInTheDocument();
    expect(screen.queryByTestId("auth-button")).not.toBeInTheDocument();
  });

  it("(b) 인증 + 홈 라우트(/en) = 크롬 + DashboardHome을 함께 렌더", async () => {
    pathnameRef.current = "/en";
    window.localStorage.setItem("propai_access_token", "live-token");

    render(
      <DashboardChromeGate locale="en" localeLabel="Language" runtimeModeLabel="LIVE" sections={sections}>
        <HomeGate locale="en" landing={<div data-testid="landing-marker">landing</div>} />
      </DashboardChromeGate>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("dashboard-home")).toBeInTheDocument();
    });
    expect(screen.getByTestId("workspace-nav-bar")).toBeInTheDocument();
    expect(screen.getByTestId("disclaimer")).toBeInTheDocument();
    expect(screen.queryByTestId("landing-marker")).not.toBeInTheDocument();
  });

  it("(c) 미인증 + 타 라우트(/en/precheck) = 크롬 유지(회귀 0)", async () => {
    pathnameRef.current = "/en/precheck";

    render(
      <DashboardChromeGate locale="en" localeLabel="Language" runtimeModeLabel="LIVE" sections={sections}>
        <div data-testid="page-content">precheck</div>
      </DashboardChromeGate>,
    );

    expect(await screen.findByTestId("page-content")).toBeInTheDocument();
    expect(screen.getByTestId("workspace-nav-bar")).toBeInTheDocument();
    expect(screen.getByTestId("disclaimer")).toBeInTheDocument();
    expect(screen.getByTestId("auth-button")).toBeInTheDocument();
  });
});
