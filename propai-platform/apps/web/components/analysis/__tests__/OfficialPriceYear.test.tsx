/**
 * 공시지가는 **기준연도와 한 쌍**으로 보인다 (2026-08-22 · #753 후속).
 *
 * ★왜: 기준연도가 화면에 없어서 `year=2025` 하드코딩으로 **1년 낡은 공시지가**가
 *   나가는 동안 아무도 눈치채지 못했다(VWorld 는 2026년치를 주고 있었다).
 *   값만 보이면 낡음이 보이지 않는다.
 *
 * ★두 모집단(CLAUDE.md 검증규율 2):
 *   A) 백엔드가 연도를 주면 → 라벨에 연도가 **붙는다**
 *   B) 연도를 모르면(land_register 폴백) → 붙이지 **않는다**(지어내면 "최신" 거짓 신호)
 *
 * ★조건부 렌더 주의(회귀망 규율 A1): 공시지가는 접힌 SectionCard 안에 있다 —
 *   섹션을 **열어서** 검사한다. 안 열면 "검사는 있는데 대상이 없어" 통과한다.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const routes = new Map<string, () => Promise<unknown>>();
const post = vi.fn<(path: string, opts?: unknown) => Promise<unknown>>((path: string) => {
  const h = routes.get(path);
  return h ? h() : Promise.resolve({});
});
function onPost(path: string, handler: () => Promise<unknown>) {
  routes.set(path, handler);
}
const get = vi.fn<(path: string, opts?: unknown) => Promise<unknown>>(async () => ({ providers: [] }));

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    post: (path: string, opts?: unknown) => post(path, opts),
    get: (path: string, opts?: unknown) => get(path, opts),
  },
  hasAccessToken: () => true,
  resolveApiOrigin: () => "http://localhost:8000",
  apiV1BaseUrl: () => "http://localhost:8000/api/v1",
  ApiClientError: class ApiClientError extends Error {},
}));
vi.mock("@/components/precheck/SatongMapShell", () => ({ SatongMapShell: () => null }));

import { ComprehensiveAnalysisPanel } from "@/components/analysis/ComprehensiveAnalysisPanel";
import { useProjectContextStore } from "@/store/useProjectContextStore";

const ADDRESS = "경기도 오산시 수청동 569";

function coreWith(landPrices: Record<string, unknown>) {
  return {
    address: ADDRESS,
    zone_type: "제3종일반주거지역",
    land_area_sqm: 29167,
    land_prices: landPrices,
    ai_interpretation: null,
    ai_interpretation_status: { status: "deferred", reason: "다음 단계" },
  };
}

async function runWith(landPrices: Record<string, unknown>) {
  onPost("/analysis/comprehensive", async () => coreWith(landPrices));
  useProjectContextStore.setState({
    siteAnalysis: { address: ADDRESS, zoneCode: "제3종일반주거지역" } as never,
  });
  render(<ComprehensiveAnalysisPanel />);
  const btn = await screen.findByRole("button", { name: /종합 분석 시작/ });
  await waitFor(() => expect(btn).not.toBeDisabled());
  await userEvent.click(btn);
  // ★접힌 섹션을 **연다** — 안 열면 대상이 DOM 에 없어 공허하게 통과한다.
  const section = await screen.findByText(/3\. 토지 주변시세/, {}, { timeout: 5000 });
  await userEvent.click(section);
}

beforeEach(() => {
  post.mockClear();
  routes.clear();
  onPost("/site-score/poi-infra", async () => ({ score: 60 }));
  onPost("/development-methods/scenarios", async () => ({}));
  useProjectContextStore.setState({ siteAnalysis: null } as never);
});

describe("공시지가 기준연도 표시", () => {
  it("A) 백엔드가 연도를 주면 라벨에 연도가 붙는다", async () => {
    await runWith({
      official_price_per_sqm: 1377000,
      official_price_year: 2026,
      total_official_value_won: 40166_000_000,
      estimated_market_per_sqm: 1652400,
      total_estimated_value_won: 48199_000_000,
      market_multiplier: 1.2,
    });

    expect(await screen.findByText(/공시지가 \(2026년 · 원\/m²\)/)).toBeInTheDocument();
    // ★값도 잠근다 — 라벨만 보면 **값 렌더가 통째로 사라져도** 통과한다(변이 생존으로 적발).
    expect(screen.getByText("137.7만원")).toBeInTheDocument();
  });

  it("B) 연도를 모르면 붙이지 않는다(지어내지 않는다)", async () => {
    await runWith({
      official_price_per_sqm: 1389000,
      official_price_year: null,          // land_register 폴백 — 연도 미상
      total_official_value_won: 40513_000_000,
      estimated_market_per_sqm: 1666800,
      total_estimated_value_won: 48615_000_000,
      market_multiplier: 1.2,
    });

    // 값 자체는 보여야 한다(전제 가드 — 대상이 없어서 통과하는 걸 막는다)
    expect(await screen.findByText("공시지가 (원/m²)")).toBeInTheDocument();
    expect(screen.getByText("138.9만원")).toBeInTheDocument();   // 값 렌더 잠금(두 모집단이 다른 값)
    expect(screen.queryByText(/공시지가 \(\d{4}년/)).not.toBeInTheDocument();
  });
});
