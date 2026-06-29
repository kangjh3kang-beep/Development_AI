import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { buildPrimaryNav } from "./nav-config";
import { WorkspaceNavBar } from "./WorkspaceNavBar";

vi.mock("next/navigation", () => ({
  usePathname: () => "/en/market-insights",
}));

vi.mock("@/lib/use-is-admin", () => ({
  fetchAuthMeRole: vi.fn(() => new Promise<string>(() => {})),
  fetchIsAdmin: vi.fn(() => new Promise<boolean>(() => {})),
}));

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
    expect(within(nav).queryByText("운영 센터")).not.toBeInTheDocument();
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
    render(<WorkspaceNavBar sections={buildPrimaryNav("en")} />);

    const nav = screen.getByRole("navigation", { name: "Workspace navigation" });
    const projectButton = within(nav).getByRole("button", { name: /프로젝트/ });

    fireEvent.mouseEnter(projectButton.parentElement!);
    expect(within(nav).getByRole("link", { name: "프로젝트 관리" })).toBeInTheDocument();

    fireEvent.mouseLeave(projectButton.parentElement!);
    expect(within(nav).queryByRole("link", { name: "프로젝트 관리" })).not.toBeInTheDocument();

    fireEvent.click(projectButton);
    const projectLink = within(nav).getByRole("link", { name: "프로젝트 관리" });
    fireEvent.click(projectLink);
    expect(within(nav).queryByRole("link", { name: "프로젝트 관리" })).not.toBeInTheDocument();
  });
});
