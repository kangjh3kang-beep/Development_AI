import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const getMock = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: { get: (...args: unknown[]) => getMock(...args) },
}));

import { EngineHealthCard } from "@/components/deliberation/EngineHealthCard";

describe("EngineHealthCard", () => {
  beforeEach(() => getMock.mockReset());

  it("ok 상태 — 연결됨 배지 + 화이트리스트 필드, 올바른 경로 호출", async () => {
    getMock.mockResolvedValue({
      status: "ok",
      engine: {
        database_configured: true,
        sheet_classifier_live: true,
        jurisdiction_live: false,
        embedder_semantic: true,
      },
    });
    render(<EngineHealthCard />);
    expect(await screen.findByText("연결됨")).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledWith("/deliberation/health");
  });

  it("degraded — 미연결 + 사유 표면화(무음0)", async () => {
    getMock.mockResolvedValue({ status: "degraded", reason: "engine_unreachable", engine: null });
    render(<EngineHealthCard />);
    expect(await screen.findByText("미연결")).toBeInTheDocument();  // 배지(정확매칭)
    expect(screen.getByText(/engine_unreachable/)).toBeInTheDocument();  // 사유 표면화
  });

  it("fetch 실패도 크래시 없이 표면화", async () => {
    getMock.mockRejectedValueOnce(new Error("boom"));
    render(<EngineHealthCard />);
    expect(await screen.findByText("확인 실패")).toBeInTheDocument();  // 배지(정확매칭)
  });
});
