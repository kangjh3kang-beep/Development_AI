/**
 * LandIntelligencePanel 스모크(W3-2) — "크래시 없이 마운트 + 핵심 랜드마크 존재"만 확인.
 * data가 비어 있으면(주소 없음) 용도지역/실거래 자동 조회가 스킵된다.
 * useAIAnalyze/useAIReady는 @tanstack/react-query 기반(Provider 필요)이라
 * 기존 대시보드 테스트 관례대로 모듈 모킹한다.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LandIntelligencePanel } from "@/components/projects/LandIntelligencePanel";

vi.mock("@/lib/ai-analyze-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/ai-analyze-client")>();
  return {
    ...actual,
    useAIReady: () => ({ isReady: false }),
    useAIAnalyze: () => ({
      mutate: vi.fn(),
      data: null,
      isPending: false,
      error: null,
    }),
  };
});

// 네트워크 차단: 남는 조회 경로도 전부 영구 pending으로 고정(스모크 안정성).
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

describe("LandIntelligencePanel 스모크", () => {
  it("빈 데이터로 크래시 없이 마운트되고 분석 헤더·주소 플레이스홀더가 보인다", () => {
    render(<LandIntelligencePanel projectId="p1" data={{}} />);

    expect(screen.getByText("지능형 입지 분석")).toBeInTheDocument();
    expect(screen.getByText("분석 대상 주소를 입력하세요")).toBeInTheDocument();
  });
});
