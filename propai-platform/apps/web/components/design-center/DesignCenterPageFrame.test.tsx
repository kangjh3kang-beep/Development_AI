import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  DesignCenterEmptyState,
  DesignCenterPageFrame,
} from "./DesignCenterPageFrame";

describe("DesignCenterPageFrame", () => {
  it("renders the design-center sibling navigation from the route registry", () => {
    render(
      <DesignCenterPageFrame
        locale="ko"
        activeId="design-audit"
        title="AI 설계분석"
        description="설계센터 통합 셸"
        metrics={[{ label: "입력", value: "4단계" }]}
      >
        <div>본문</div>
      </DesignCenterPageFrame>,
    );

    expect(screen.getByRole("heading", { name: "AI 설계분석" })).toBeInTheDocument();
    expect(screen.getByText("4단계")).toBeInTheDocument();
    expect(screen.getByText("본문")).toBeInTheDocument();

    expect(screen.getByRole("link", { name: /AI 설계도면/ })).toHaveAttribute(
      "href",
      "/ko/design-studio",
    );
    expect(screen.getByRole("link", { name: /AI 설계분석/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: /프로젝트 회의방/ })).toHaveAttribute(
      "href",
      "/ko/meeting-rooms",
    );
  });

  it("renders the shared empty state with the project CTA", () => {
    render(
      <DesignCenterEmptyState
        title="프로젝트 선택 필요"
        description="대상 프로젝트를 먼저 선택하세요."
        actionHref="/ko/projects"
      />,
    );

    expect(screen.getByRole("heading", { name: "프로젝트 선택 필요" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /프로젝트 관리로 이동/ })).toHaveAttribute(
      "href",
      "/ko/projects",
    );
  });
});
