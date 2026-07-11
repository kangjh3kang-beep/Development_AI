import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HomeGate } from "@/components/marketing/HomeGate";
import { LandingPage } from "@/components/marketing/LandingPage";

// next/navigation — ReportPanelSection의 useRouter 의존 충족
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

// next/dynamic — HomeGate가 ssr:false로 지연 로드하는 DashboardHome을
// 무거운 실제 구현(지도 등) 대신 결정적 스텁으로 대체한다.
vi.mock("next/dynamic", () => ({
  default: () => {
    const DashboardHomeStub = ({ locale }: { locale: string }) => (
      <div data-testid="dashboard-home">dashboard:{locale}</div>
    );
    return DashboardHomeStub;
  },
}));

describe("HomeGate 인증 분기", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("미인증 상태에서는 랜딩을 렌더하고 DashboardHome은 렌더하지 않는다", async () => {
    render(
      <HomeGate
        locale="ko"
        landing={<div data-testid="landing-marker">랜딩</div>}
      />,
    );

    expect(await screen.findByTestId("landing-marker")).toBeInTheDocument();
    expect(screen.queryByTestId("dashboard-home")).not.toBeInTheDocument();
  });

  it("인증 토큰이 있으면 DashboardHome으로 스왑한다", async () => {
    window.localStorage.setItem("propai_access_token", "live-token");

    render(
      <HomeGate
        locale="ko"
        landing={<div data-testid="landing-marker">랜딩</div>}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("dashboard-home")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("landing-marker")).not.toBeInTheDocument();
  });
});

describe("LandingPage(미인증 랜딩) 렌더", () => {
  it("히어로 헤드라인과 브랜드 카피를 렌더한다", () => {
    render(<LandingPage locale="ko" />);

    // 히어로 H1(줄바꿈 포함) — 부분 매칭으로 확인
    expect(screen.getByText(/AI로 사통팔땅/)).toBeInTheDocument();
    // 리포트 패널 CTA
    expect(screen.getByRole("button", { name: /보고서 만들기/ })).toBeInTheDocument();
  });
});
