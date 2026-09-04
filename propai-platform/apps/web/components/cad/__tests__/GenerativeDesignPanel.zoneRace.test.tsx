/**
 * GenerativeDesignPanel — zoneCode 초기값 1-tick 경합 회귀앵커(live-fix③).
 *
 * 배경: zoneCode가 useState("2R")로 마운트되면, 컨텍스트(siteAnalysis) 반영 useEffect가
 * 그 다음 렌더에야 zoneCode를 고치는 1-tick 경합으로 legal-limits?zone_code=2R이 실제
 * 부지 확정 전 1회 호출됐다(자연녹지 프로젝트에 "2R" 라벨 혼재). zoneCode를
 * useState(() => ctxZone ?? "2R")로 lazy 초기화해, siteAnalysis가 마운트 시점에 이미
 * 스토어에 있으면(흔한 케이스) 첫 렌더부터 정확한 zoneCode를 쓰는지 검증한다.
 */
import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GenerativeDesignPanel } from "@/components/cad/GenerativeDesignPanel";
import { useProjectContextStore, type SiteAnalysisData } from "@/store/useProjectContextStore";

// 네트워크 차단: legal-limits 등 마운트 조회를 영구 pending으로 고정(늦은 setState 제거 —
// GenerativeDesignPanel.smoke.test.tsx와 동일 패턴). 호출 인자(URL)만 캡처하면 충분하다.
const getMock = vi.fn<(...args: unknown[]) => Promise<never>>(() => new Promise<never>(() => {}));

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      get: (...args: unknown[]) => getMock(...args),
      post: vi.fn(() => new Promise<never>(() => {})),
    },
  };
});

function makeSite(partial: Partial<SiteAnalysisData>): SiteAnalysisData {
  return {
    estimatedValue: null,
    landAreaSqm: null,
    zoneCode: null,
    address: null,
    pnu: null,
    ...partial,
  };
}

afterEach(() => {
  getMock.mockClear();
  useProjectContextStore.setState({ siteAnalysis: null });
});

describe("GenerativeDesignPanel — zoneCode lazy 초기화(1-tick 경합 봉합)", () => {
  it("siteAnalysis가 마운트 시점에 이미 있으면(자연녹지) 첫 legal-limits 호출부터 올바른 zone을 쓴다(2R 아님)", () => {
    useProjectContextStore.setState({
      siteAnalysis: makeSite({ zoneCode: "자연녹지지역", landAreaSqm: 1000 }),
    });

    render(<GenerativeDesignPanel projectId="p1" />);

    expect(getMock).toHaveBeenCalled();
    const firstCallUrl = String(getMock.mock.calls[0]?.[0] ?? "");
    expect(firstCallUrl).toContain("legal-limits");
    expect(firstCallUrl).not.toContain("zone_code=2R");
    expect(firstCallUrl).toContain(encodeURIComponent("자연녹지지역"));
    // ★재발 방지 핵심: "2R" 호출이 단 한 번도 없어야 한다(1-tick 경합이면 최초 1회 섞여 들어온다).
    const anyCallWas2R = getMock.mock.calls.some((c) => String(c[0]).includes("zone_code=2R"));
    expect(anyCallWas2R).toBe(false);
  });

  it("siteAnalysis가 없으면 기존과 동일하게 기본값 2R로 조회한다(무회귀)", () => {
    render(<GenerativeDesignPanel projectId="p1" />);

    expect(getMock).toHaveBeenCalled();
    const firstCallUrl = String(getMock.mock.calls[0]?.[0] ?? "");
    expect(firstCallUrl).toContain("zone_code=2R");
  });
});
