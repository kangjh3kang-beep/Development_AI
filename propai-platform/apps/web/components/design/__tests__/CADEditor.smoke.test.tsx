/**
 * CADEditor 스모크(W3-2) — "크래시 없이 마운트 + 핵심 랜드마크 존재"만 확인.
 * Konva Stage는 size(w/h)>0일 때만 마운트되는데 jsdom은 clientWidth/Height가 0이라
 * 실제 캔버스는 생성되지 않는다(도구 바·레이어 칩 등 UI 크롬만 렌더).
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import CADEditor from "@/components/design/CADEditor";

// 네트워크 차단: 마운트 시 저장본 로드(/drawings/load) 등은 영구 pending으로 고정해
// 늦은 setState(act 경고)와 실네트워크 시도를 모두 제거한다(스모크 안정성).
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

describe("CADEditor 스모크", () => {
  it("크래시 없이 마운트되고 도구 바·레이어 패널이 보인다", () => {
    render(<CADEditor projectId="p1" siteAreaSqm={500} zoneCode="2R" />);

    // 상단 도구 바(도형 도구) + undo 버튼 — CAD 편집기 UI 크롬의 핵심 랜드마크.
    expect(screen.getByRole("button", { name: "다각형" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "실행 취소" })).toBeInTheDocument();
    // 좌상단 레이어 칩 패널.
    expect(screen.getByText("Layers")).toBeInTheDocument();
  });
});
