import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const getMock = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: { get: (...args: unknown[]) => getMock(...args) },
}));

import { RegDivergenceCard } from "@/components/deliberation/RegDivergenceCard";

// 카드는 2개 엔드포인트를 호출(/reg/divergence + /reg/baseline-staleness). 경로별 응답 매핑 헬퍼.
function routeMock(map: Record<string, unknown>) {
  getMock.mockImplementation((path: string) =>
    path in map ? Promise.resolve(map[path]) : Promise.resolve({ degraded: true, reason: "n/a" }),
  );
}

const DIV = "/deliberation/reg/divergence";
const STALE = "/deliberation/reg/baseline-staleness";

describe("RegDivergenceCard", () => {
  beforeEach(() => getMock.mockReset());

  it("완전 일치(drift 0·회귀없음) — 일치 표식, 올바른 경로 호출", async () => {
    getMock.mockResolvedValue({
      degraded: false,
      compared: 42,
      drift: 0,
      matched: 42,
      match_rate: 1.0,
      unexpected_platform_only: [],
      engine_meta: { source: "국토계획법 시행령 §84·§85", version: "v1" },
    });
    render(<RegDivergenceCard />);
    expect(await screen.findByText(/대조 42건 · drift 0/)).toBeInTheDocument();
    expect(screen.getByText(/100% · 일치/)).toBeInTheDocument();
    expect(screen.getByText(/v1/)).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledWith("/deliberation/reg/divergence");
  });

  it("엔진 규제 누락 회귀 신호를 별도 경보로 표면화(drift 0이어도)", async () => {
    getMock.mockResolvedValue({
      degraded: false,
      compared: 40,
      drift: 0,
      match_rate: 1.0,
      unexpected_platform_only: ["제2종일반주거지역"],
    });
    render(<RegDivergenceCard />);
    expect(await screen.findByText(/엔진 규제 누락 의심: 제2종일반주거지역/)).toBeInTheDocument();
  });

  it("drift 검출 시 미일치 표식(amber)", async () => {
    getMock.mockResolvedValue({
      degraded: false,
      compared: 42,
      drift: 1,
      match_rate: 0.976,
      unexpected_platform_only: [],
    });
    render(<RegDivergenceCard />);
    expect(await screen.findByText(/대조 42건 · drift 1/)).toBeInTheDocument();
    expect(screen.getByText("97.6%")).toBeInTheDocument(); // '일치' 미표시(drift>0)
  });

  it("대조불가(match_rate null·compared 0) — '일치'/녹색 위장 금지(정직 불변식)", async () => {
    getMock.mockResolvedValue({
      degraded: false,
      compared: 0,
      drift: 0,
      match_rate: null,
      unexpected_platform_only: [],
    });
    render(<RegDivergenceCard />);
    expect(await screen.findByText("대조불가")).toBeInTheDocument();
    expect(screen.queryByText(/일치/)).toBeNull(); // 거짓 '일치' 미표기(대조 0건을 합치로 위장 금지)
  });

  it("대조불가 + 회귀경보 동시 — 둘 다 정직 표면화(카드 최고가치 시나리오)", async () => {
    // 엔진이 규제표를 잃어 대조 0건(match_rate null)이면서 표준 zone 누락 회귀까지 — 거짓 '일치' 금지 +
    // 회귀 경보는 role=alert로 별도 노출(둘이 모순 없이 공존).
    getMock.mockResolvedValue({
      degraded: false,
      compared: 0,
      drift: 0,
      match_rate: null,
      unexpected_platform_only: ["제2종일반주거지역", "제3종일반주거지역"],
    });
    render(<RegDivergenceCard />);
    expect(await screen.findByText("대조불가")).toBeInTheDocument();
    expect(screen.queryByText(/일치/)).toBeNull(); // 거짓 '일치' 금지
    expect(screen.getByRole("alert")).toHaveTextContent(
      /엔진 규제 누락 의심: 제2종일반주거지역, 제3종일반주거지역/,
    );
  });

  it("엔진만 보유(플랫폼 미수록) coverage gap을 중립 정보로 표면화", async () => {
    getMock.mockResolvedValue({
      degraded: false,
      compared: 40,
      drift: 0,
      match_rate: 1.0,
      unexpected_platform_only: [],
      engine_only_zones: ["준주거지역"],
    });
    render(<RegDivergenceCard />);
    expect(await screen.findByText(/플랫폼 미수록\(엔진만\): 준주거지역/)).toBeInTheDocument();
  });

  it("엔진 미연결 — degrade 정직 안내(무음0)", async () => {
    getMock.mockResolvedValue({ degraded: true, reason: "circuit_open", engine_configured: true });
    render(<RegDivergenceCard />);
    expect(await screen.findByText(/엔진 미연결 — 대조 보류\(circuit_open\)/)).toBeInTheDocument();
  });

  it("baseline 신선도 — 출처 관련 법령 개정 감지 시 별도 경보(role=alert, 실제 법령명 기반)", async () => {
    routeMock({
      [DIV]: { degraded: false, compared: 42, drift: 0, match_rate: 1.0, unexpected_platform_only: [] },
      [STALE]: {
        degraded: false,
        stale: true,
        triggering_laws: [{ law_name: "국토의 계획 및 이용에 관한 법률" }],
      },
    });
    render(<RegDivergenceCard />);
    expect(await screen.findByText(/출처 관련 법령 개정 감지 — baseline 검토 필요/)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/국토의 계획 및 이용에 관한 법률/);
    expect(screen.queryByText(/시행령 개정 감지/)).toBeNull(); // '시행령' 단정 오라벨 제거 확인
  });

  it("baseline 신선도 not-stale(stale=false) — 경보 미표시(거짓 경보 금지)", async () => {
    routeMock({
      [DIV]: { degraded: false, compared: 42, drift: 0, match_rate: 1.0, unexpected_platform_only: [] },
      [STALE]: { degraded: false, stale: false, triggering_laws: [] },
    });
    render(<RegDivergenceCard />);
    expect(await screen.findByText(/100% · 일치/)).toBeInTheDocument();
    expect(screen.queryByText(/시행령 개정 감지/)).toBeNull();
  });

  it("baseline 신선도 degraded(법제처 키 미설정 등) — 경보 미표시(감지 불가를 위장 안 함)", async () => {
    routeMock({
      [DIV]: { degraded: false, compared: 42, drift: 0, match_rate: 1.0, unexpected_platform_only: [] },
      [STALE]: { degraded: true, reason: "monitor_key_missing" },
    });
    render(<RegDivergenceCard />);
    expect(await screen.findByText(/100% · 일치/)).toBeInTheDocument();
    expect(screen.queryByText(/시행령 개정 감지/)).toBeNull();
  });

  it("조회 실패도 크래시 없이 표면화", async () => {
    getMock.mockRejectedValueOnce(new Error("boom"));
    render(<RegDivergenceCard />);
    expect(await screen.findByText(/정합 조회 실패/)).toBeInTheDocument();
  });
});
