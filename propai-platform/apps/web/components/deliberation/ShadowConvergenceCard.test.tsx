import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const getMock = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: { get: (...args: unknown[]) => getMock(...args) },
}));

import { ShadowConvergenceCard } from "@/components/deliberation/ShadowConvergenceCard";

describe("ShadowConvergenceCard", () => {
  beforeEach(() => getMock.mockReset());

  it("도메인별 일치율 렌더 + 승격가능 표식, 올바른 경로 호출", async () => {
    getMock.mockResolvedValue({
      stats: [
        { domain: "design_audit", n: 600, matched_n: 597, match_rate: 0.995, avg_divergence: 0.005 },
        { domain: "building_compliance", n: 200, matched_n: 180, match_rate: 0.9, avg_divergence: 0.1 },
      ],
    });
    render(<ShadowConvergenceCard />);
    expect(await screen.findByText("design_audit")).toBeInTheDocument();
    expect(screen.getByText(/99.5%.*승격가능/)).toBeInTheDocument(); // 게이트(≥99%) 충족
    expect(screen.getByText("90%")).toBeInTheDocument(); // 미충족(승격가능 미표시)
    expect(getMock).toHaveBeenCalledWith("/deliberation/shadow/stats");
  });

  it("빈 데이터 — 관측 없음 정직 안내(무음0)", async () => {
    getMock.mockResolvedValue({ stats: [] });
    render(<ShadowConvergenceCard />);
    expect(await screen.findByText(/관측 데이터 없음/)).toBeInTheDocument();
  });

  it("조회 실패도 크래시 없이 표면화", async () => {
    getMock.mockRejectedValueOnce(new Error("boom"));
    render(<ShadowConvergenceCard />);
    expect(await screen.findByText(/수렴 통계 확인 실패/)).toBeInTheDocument();
  });
});
