import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import DeliberationReviewPage from "../deliberation-review/page";
import DesignAuditPage from "../design-audit/page";
import MeetingRoomsPage from "../meeting-rooms/page";

vi.mock("@/components/design-audit/DesignAuditWorkspace", () => ({
  DesignAuditWorkspace: ({
    showHeader,
  }: {
    showHeader?: boolean;
  }) => <div data-testid="design-audit-workspace">{String(showHeader)}</div>,
}));

vi.mock("@/components/collaboration/MeetingRoomsListClient", () => ({
  MeetingRoomsListClient: ({ locale }: { locale: string }) => (
    <div data-testid="meeting-rooms-list">{locale}</div>
  ),
}));

vi.mock("@/components/deliberation/EngineHealthCard", () => ({
  EngineHealthCard: () => <div data-testid="engine-health-card" />,
}));

vi.mock("@/components/deliberation/RegDivergenceCard", () => ({
  RegDivergenceCard: () => <div data-testid="reg-divergence-card" />,
}));

vi.mock("@/components/deliberation/ShadowConvergenceCard", () => ({
  ShadowConvergenceCard: () => <div data-testid="shadow-convergence-card" />,
}));

vi.mock("@/components/analysis/DeliberationResultPanel", () => ({
  DeliberationResultPanel: () => <div data-testid="deliberation-result-panel" />,
}));

vi.mock("@/components/deliberation/DeliberationConsole", () => ({
  DeliberationConsole: () => <div data-testid="deliberation-console" />,
}));

vi.mock("@/i18n/get-dictionary", () => ({
  getDictionary: vi.fn(async () => ({
    vision: {
      badge: "VLLM · 차세대 심의분석 엔진",
      title: "멀티모달 AI 심의분석",
      lead: "설계도서를 자동 해석합니다.",
      engineTitle: "심의분석 11계층",
      engineNote: "BFF degrade-safe",
      areas: {
        engine: "심의 엔진",
      },
      pillars: {
        multimodal: { title: "멀티모달", desc: "도면과 문서를 함께 읽습니다." },
        deterministic: { title: "결정론", desc: "규칙 기반 검증을 고정합니다." },
        frontier: { title: "확장성", desc: "후속 엔진으로 확장합니다." },
      },
      layers: ["도면", "법규", "일조"],
    },
  })),
}));

describe("Design-center route shells", () => {
  it("renders design-audit inside the shared design center frame", async () => {
    render(await DesignAuditPage({ params: Promise.resolve({ locale: "ko" }) }));

    expect(screen.getByRole("heading", { name: "AI 설계분석" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /AI 설계도면/ })).toHaveAttribute(
      "href",
      "/ko/design-studio",
    );
    expect(screen.getByTestId("design-audit-workspace")).toHaveTextContent("false");
  });

  it("renders meeting rooms inside the shared design center frame", async () => {
    render(await MeetingRoomsPage({ params: Promise.resolve({ locale: "ko" }) }));

    expect(screen.getByRole("heading", { name: "프로젝트 회의방" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /프로젝트 회의방/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByTestId("meeting-rooms-list")).toHaveTextContent("ko");
  });

  it("renders deliberation review without the legacy page hero", async () => {
    render(await DeliberationReviewPage({ params: Promise.resolve({ locale: "ko" }) }));

    expect(screen.getByRole("heading", { name: "멀티모달 AI 심의분석" })).toBeInTheDocument();
    expect(screen.getByText("심의분석 11계층")).toBeInTheDocument();
    expect(screen.getByTestId("deliberation-console")).toBeInTheDocument();
  });
});
