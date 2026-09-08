/**
 * 탁상감정 §Ⅵ — **렌더 락**(소스 검사가 아니다).
 *
 * ## 왜 이 파일이 생겼나 (독립 리뷰 R5 HIGH-1/HIGH-2 · 2026-09-08)
 *
 * 직전 라운드에 나는 «grep 락을 행위 락으로 교체했다» 고 커밋에 썼다. **절반만 참이었다** —
 * 줄 조립은 순수 함수로 빠졌지만 **배선 축은 여전히 문자열 검사**였고, 리뷰어가 그것을 뚫었다:
 *
 *     {buildMarketBasisLines(res).map(  →  {false && buildMarketBasisLines(res).map(
 *     → Tests 14 passed  ::VERDICT=SURVIVED
 *
 * 정직 라벨 블록 전체를 화면에서 지워도 초록이었다. **클래스가 고쳐진 게 아니라 한 칸 옮겨갔다.**
 * 그리고 같은 파일의 형제 grep 락 5건은 손도 대지 않아 「시계열 아님」 배지도 같은 변이로 생존했다.
 *
 * ⇒ 여기서는 **컴포넌트를 실제로 렌더**하고 **DOM 을 본다.** 렌더가 죽으면 DOM 이 비어 잡힌다.
 *   부모를 렌더하는 것이 핵심이다 — §Ⅵ 를 하위 컴포넌트로 빼고 그것만 렌더하면
 *   같은 결함이 **한 칸 위**(부모의 `{false && <Section/>}`)로 옮겨갈 뿐이다.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const fetchDeskAppraisal = vi.fn();
vi.mock("@/lib/land/desk-appraisal", async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, fetchDeskAppraisal: (...a: unknown[]) => fetchDeskAppraisal(...a) };
});
vi.mock("@/components/avm-vision/AvmVisionPanel", () => ({ AvmVisionPanel: () => null }));
// ★디자인 시스템은 모킹한다 — 이 락이 잠그려는 것은 **내 컴포넌트의 JSX 배선**이지
//   `@propai/ui` 의 렌더가 아니다(모노레포 링크 상태에 락이 좌우되면 그것도 결함이다).
vi.mock("@propai/ui", () => ({
  Card: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  CardContent: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
}));

import { DeskAppraisalReportClient } from "../DeskAppraisalReportClient";
import { useProjectContextStore } from "@/store/useProjectContextStore";

const ADDRESS = "서울특별시 강남구 역삼동 1";

/** 라이브 응답 모양 그대로 — §Ⅵ 가 읽는 필드만 채운다. */
function result(overrides: Record<string, unknown> = {}) {
  return {
    ok: true,
    // ★필수 필드는 `DeskAppraisalResult` 타입에서 파생해 채운다 — 얇은 픽스처는 §Ⅵ 에
    //   닿기도 전에 렌더를 터뜨려, 이 락이 «렌더가 죽었다» 를 구별하지 못하게 만든다.
    appraised_price_per_sqm: 2_000_000,
    appraised_total_won: 1_000_000_000,
    area_sqm: 500,
    official_price_per_sqm: 1_600_000,
    confidence: 0.7,
    confidence_basis: "단일 출처 추정",
    range_per_sqm: { low: 1_900_000, high: 2_100_000 },
    methods: [],
    weight_note: "공시지가기준법 단독 채택",
    time_adjust_basis: "R-ONE 지가변동률 서울 실데이터",
    market_stats: {
      region: "서울",
      rone_available: true,
      cap_rate: { source: "R-ONE", pct: 4.5, basis: "상업용부동산 투자수익률 실측" },
      jeonse_conversion_rate: { source: "R-ONE", pct: 5.4, basis: "전월세전환율 실측" },
      housing_time_adjust: { source: "R-ONE", factor: 1.0243, basis: "주택매매가격지수 누적 변동(서울)" },
      land_price_trend: {
        monthly: [{ period: "202607", rate: 0.5 }],
        yearly: [{ year: "2025", rate: 6.0 }],
        scope: "서울", distinct_periods: 1, requested_months: 24, is_time_series: false,
      },
    },
    ...overrides,
  };
}

async function renderAndRun(res: unknown) {
  fetchDeskAppraisal.mockResolvedValue(res);
  useProjectContextStore.setState({ siteAnalysis: { address: ADDRESS } } as never);
  render(<DeskAppraisalReportClient locale="ko" />);
  await userEvent.click(screen.getByRole("button", { name: /서칭·분석/ }));
  await waitFor(() => expect(fetchDeskAppraisal).toHaveBeenCalled());
}

describe("탁상감정 §Ⅵ 렌더 락", () => {
  beforeEach(() => {
    fetchDeskAppraisal.mockReset();
    useProjectContextStore.setState({ siteAnalysis: null, projectId: null } as never);
  });

  it("★§Ⅵ 근거 줄이 **화면에 실제로 그려진다**(소스가 아니라 DOM)", async () => {
    await renderAndRun(result());
    await waitFor(() => {
      expect(screen.getByText(/시점수정: R-ONE 지가변동률 서울 실데이터/)).toBeTruthy();
    });
    // 세 형제가 모두 basis 를 달고 그려진다 — 비대칭이 화면에서 확인된다.
    expect(screen.getByText(/자본환원율\(R-ONE 실측\).*상업용부동산 투자수익률 실측/)).toBeTruthy();
    expect(screen.getByText(/전월세전환율\(R-ONE 실측\).*전월세전환율 실측/)).toBeTruthy();
    expect(screen.getByText(/주택가격지수 누적변동.*주택매매가격지수 누적 변동\(서울\)/)).toBeTruthy();
  });

  it("★「시계열 아님」 정직 배지가 **화면에 그려진다**(형제 grep 락이 못 잡던 자리)", async () => {
    await renderAndRun(result());
    await waitFor(() => {
      expect(screen.getByText(/시계열이 아닙니다|시계열 아님|고유 기간/)).toBeTruthy();
    });
  });

  it("★위양성 축 — 시계열이 정상이면 그 배지는 **뜨지 않는다**", async () => {
    const ok = result();
    (ok.market_stats.land_price_trend as Record<string, unknown>).is_time_series = true;
    (ok.market_stats.land_price_trend as Record<string, unknown>).distinct_periods = 24;
    await renderAndRun(ok);
    await waitFor(() => expect(screen.getByText(/시점수정: R-ONE/)).toBeTruthy());
    expect(screen.queryByText(/시계열이 아닙니다|시계열 아님/)).toBeNull();
  });

  it("★R-ONE 이 아닌 통계는 «실측» 줄을 그리지 않는다(지어낸 라벨 금지)", async () => {
    const fallback = result();
    (fallback.market_stats.cap_rate as Record<string, unknown>).source = "기본";
    await renderAndRun(fallback);
    await waitFor(() => expect(screen.getByText(/시점수정: R-ONE/)).toBeTruthy());
    expect(screen.queryByText(/자본환원율\(R-ONE 실측\)/)).toBeNull();
  });
});
