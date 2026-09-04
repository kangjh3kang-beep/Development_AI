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

  it("정직 3상 표기 — true=live·false=mock·null=미확인(구버전 미보고를 mock으로 오표기 금지)", async () => {
    // ★D1 회귀가드: 과거 `value ? 'live' : 'mock'`가 null(필드 미보고)까지 'mock'으로 왜곡했다.
    getMock.mockResolvedValue({
      status: "ok",
      engine: {
        database_configured: null,      // 미보고 → "미확인"(mock 아님)
        sheet_classifier_live: true,    // → "live"
        jurisdiction_live: false,       // → "mock"
        embedder_semantic: null,        // 미보고 → "미확인"
      },
    });
    render(<EngineHealthCard />);
    // 미보고(null) 2필드는 "미확인"으로 표기되어야 한다("mock" 오표기 금지).
    const unknowns = await screen.findAllByText("미확인");
    expect(unknowns).toHaveLength(2);
    // true=live 1개, false=mock 정확히 1개(jurisdiction만) — 미보고가 mock으로 새지 않음.
    expect(screen.getByText("live")).toBeInTheDocument();
    expect(screen.getAllByText("mock")).toHaveLength(1);
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
