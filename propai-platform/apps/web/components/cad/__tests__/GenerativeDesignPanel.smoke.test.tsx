/**
 * GenerativeDesignPanel 스모크(W3-2) — "크래시 없이 마운트 + 핵심 랜드마크 존재"만 확인.
 * 마운트 시 법정 한도 조회(/drawing/legal-limits)가 발화하므로 api-client를 pending으로
 * 고정한다. 스토어(useProjectContextStore)는 기본값(siteAnalysis=null)으로 동작.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { GenerativeDesignPanel } from "@/components/cad/GenerativeDesignPanel";

// 네트워크 차단: legal-limits 등 마운트 조회를 영구 pending으로 고정(늦은 setState 제거).
vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      request: vi.fn(pending),
      get: vi.fn(pending),
      post: vi.fn(pending),
      put: vi.fn(pending),
      patch: vi.fn(pending),
      delete: vi.fn(pending),
      getV2: vi.fn(pending),
      postV2: vi.fn(pending),
      putV2: vi.fn(pending),
      deleteV2: vi.fn(pending),
    },
  };
});

describe("GenerativeDesignPanel 스모크", () => {
  it("크래시 없이 마운트되고 헤더·자연어 입력 섹션이 보인다", () => {
    render(<GenerativeDesignPanel projectId="p1" />);

    expect(screen.getByText("AI 설계 생성 · GENERATIVE")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "원하는 설계를 말이나 음성으로 설명하세요" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("textbox", { name: "설계 의도 자연어 입력" }),
    ).toBeInTheDocument();
  });
});
