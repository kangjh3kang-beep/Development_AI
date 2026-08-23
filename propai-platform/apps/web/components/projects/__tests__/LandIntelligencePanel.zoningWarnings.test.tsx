/**
 * 용도지역 경고(zoning warnings) 렌더 배선 잠금 — 2026-08-22 감사 후속.
 *
 * ★왜 이 테스트가 필요했나(실측):
 *   백엔드는 `warnings: ["용도지역이 주소 키워드 추론값입니다 — 실조회 확인 필요"]` 를 계속
 *   보내고 있었는데, 화면은 그것을 **특성칩 패딩**으로만 소비했다:
 *       if (chars.length < 4 && zoningWarnings.length > 0) → warnings[0].slice(0, 30)
 *   그래서 ①특성칩이 4개 이상이면 **통째로 사라지고** ②경고 원문 31자가 **30자로 잘렸다**.
 *   keyword_inference 때 pnu·면적이 null 이라 칩이 적어 **우연히** 보이던 것뿐이다.
 *
 * ★변이 생존 중 className 계열 5건은 **의도된 미잠금**이다 — 이 테스트의 계약은
 *   "경고 원문이 전량·무절단으로 보인다"이지 **스타일이 아니다**. CSS 문자열까지 잠그면
 *   정상 리스타일을 위반으로 신고한다(CLAUDE.md 회귀망 규율 A6 위양성).
 *
 * ★픽스처는 두 모집단을 가른다(CLAUDE.md 검증규율 2):
 *   A) 경고 있음 + 특성 4개  → 종전 패딩 경로라면 **드롭**된다. 배너는 반드시 보여야 한다.
 *   B) 경고 없음             → 배너가 없어야 한다(음성 대조군 — 공허한 초록 차단).
 */
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LandIntelligencePanel } from "@/components/projects/LandIntelligencePanel";

const INFERENCE_WARNING = "용도지역이 주소 키워드 추론값입니다 — 실조회 확인 필요";

/** 테스트마다 갈아끼우는 모집단 스위치(모듈 리셋 없이 두 모집단을 가른다). */
let currentWarnings: string[] | null = null;

vi.mock("@/lib/ai-analyze-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/ai-analyze-client")>();
  return {
    ...actual,
    useAIReady: () => ({ isReady: false }),
    useAIAnalyze: () => ({ mutate: vi.fn(), data: null, isPending: false, error: null }),
  };
});

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      request: vi.fn(pending),
      get: vi.fn(pending),
      // 특성칩 4개가 모두 차는 응답(=종전 패딩 경로가 경고를 버리는 조건).
      post: vi.fn((path: string) =>
        path.includes("/zoning/analyze")
          ? Promise.resolve({
              pnu: "4137010800105690000",
              zone_type: "제3종일반주거지역",
              land_category: "대",
              land_area_sqm: 29167,
              zone_limits: {
                max_height_m: 30, max_bcr_pct: 50, max_far_pct: 300, zone_key: "제3종일반주거지역",
              },
              special_districts: [],
              warnings: currentWarnings,
            })
          : new Promise<never>(() => {}),
      ),
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

/** 특성칩 4개가 실제로 렌더됐는지 — 공허한 진리 가드(칩이 3개면 종전 경로로도 통과한다). */
async function expectFourCharacteristicChips() {
  // 면적 칩은 이 화면에서 유일한 문자열이라 조회 완료의 앵커로 쓴다
  // (용도지역명은 헤더·요약에도 나와 다중 매칭된다).
  await waitFor(() => {
    expect(screen.getByText("29,167m²")).toBeInTheDocument();
  }, { timeout: 4000 });
  expect(screen.getByText("대")).toBeInTheDocument();          // 지목 칩
  expect(screen.getAllByText("30m").length).toBeGreaterThan(0);  // 높이 제한 칩
  expect(screen.getAllByText("제3종일반주거지역").length).toBeGreaterThan(0); // 용도지역 칩
}

describe("용도지역 경고 렌더 배선", () => {
  beforeEach(() => { currentWarnings = null; });

  it("A) 특성칩이 4개로 꽉 차도 경고 배너는 **원문 그대로** 보인다(종전 패딩 경로는 여기서 드롭됐다)", async () => {
    currentWarnings = [INFERENCE_WARNING];
    render(<LandIntelligencePanel projectId="p1" data={{ address: "경기도 오산시 수청동 569" }} />);

    await expectFourCharacteristicChips();
    // 경고는 **절단 없이** 전체가 보여야 한다(종전엔 30자로 잘렸다).
    expect(await screen.findByText(INFERENCE_WARNING)).toBeInTheDocument();
    // ★testid 를 **양성에서** 잠근다 — 이게 없으면 testid 가 바뀌어도 음성 대조군(B)의
    //   queryByTestId 는 '없음'으로 통과해 **공허한 진리**가 된다(변이 생존으로 적발).
    expect(screen.getByTestId("zoning-warnings")).toBeInTheDocument();
  });

  it("B) 경고가 없으면 배너도 없다(음성 대조군)", async () => {
    currentWarnings = null;
    // ★A와 **다른 주소** — 이 화면은 주소를 키로 분석결과를 캐시하므로(setCachedAnalysis)
    //   같은 주소를 쓰면 음성 대조군이 A의 경고를 캐시에서 읽어 오염된다(실측으로 겪음).
    render(<LandIntelligencePanel projectId="p2" data={{ address: "경기도 오산시 내삼미동 741" }} />);

    await expectFourCharacteristicChips();
    expect(screen.queryByText(INFERENCE_WARNING)).not.toBeInTheDocument();
    expect(screen.queryByTestId("zoning-warnings")).not.toBeInTheDocument();
  });
});
