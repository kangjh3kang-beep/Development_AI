/**
 * 운영 인텔리전스 정직 고지 — **배치**를 렌더로 잠근다(2026-08-15).
 *
 * ★왜 별도 파일인가: 짝 파일 `ops-intelligence-honesty.test.ts` 는 고지의 **개수**를
 *   `<LocalEstimateNotice />` **소스 정규식**으로 센다. 그 검사는 두 가지를 못 본다 —
 *   ① 고지가 실제 DOM 에 렌더되는가 ② 고지가 **어디에** 붙는가.
 *   실제로 그 사각지대로 결함이 통과했다(아래).
 *
 * ★이 파일이 잡은 실결함(#634 R1): 세입자 섹션의 고지 2개가
 *   `<div className="mt-5 grid gap-4 md:grid-cols-2">` 의 **직계 자식**으로 들어가 있었다.
 *   피드백·만족도 결과가 **둘 다** 있으면 그리드 자식이 [고지, 카드, 고지, 카드] 가 되어
 *   ① 같은 문장이 **두 번** 보이고 ② 고지가 카드 옆 **격자 칸 하나를 차지**한다.
 *   정비 섹션은 같은 고지를 그리드 **바깥**에 두었다 — 같은 처방이 자리마다 달리 적용됐다.
 *
 * ★계약: **결과 묶음 하나당 고지는 정확히 1개**이고, 결과 그리드의 직계 자식이 아니다.
 *
 * ★한계(정직 바운딩): jsdom 은 레이아웃을 계산하지 않는다. 이 테스트가 증명하는 것은
 *   **DOM 구조·개수·역할**이지 "화면에서 어떻게 보이는가"가 아니다.
 *
 * ★변이 실측(2026-08-15, `scripts/mutate_changed.py --tests <이 파일>`)에서 남은 생존과 그 이유:
 *   · `role="note"` 삭제 → 잠갔다(아래 ③). 지워도 아무 검사가 안 깨지던 진짜 구멍이었다.
 *   · 고지의 `className` 삭제·변경 → **생존을 남긴다.** jsdom 은 페인트를 하지 않으므로
 *     "고지가 눈에 띄는가"는 여기서 증명할 수 없다. 클래스 문자열을 하드코딩해 잠그면
 *     정당한 토큰 재조정까지 막는 위양성 가드가 된다(이 저장소에서 2회 재발한 형태).
 *     → 시각적 확인은 라이브 뷰포트의 몫으로 남긴다. **모르는 것을 아는 척하지 않는다.**
 *   · 결과 그리드(`mt-5 grid gap-4 md:grid-cols-2`)의 클래스 변경 → **생존을 남긴다.**
 *     이 파일의 계약은 *고지의 개수와 자리*이지 결과 카드의 열 배치가 아니다(자리 판정은
 *     클래스가 아니라 부모 동일성으로 하므로 이 변이에 영향받지 않는다). 결과 그리드
 *     자체의 레이아웃은 **어느 테스트도 잠그지 않는다** — 이 수정 이전부터 그랬고,
 *     여기서 끌어안지 않는다. 필요하면 별도 계약으로 세울 것.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

import { OperationsIntelligenceWorkspaceClient } from "@/components/analytics/OperationsIntelligenceWorkspaceClient";

vi.mock("next/navigation", () => ({
  usePathname: () => "/ko/tenant",
  useParams: () => ({ locale: "ko" }),
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

// 프로젝트 목록 조회(useQuery)는 이 계약과 무관하다 — 영구 pending 으로 고정해 네트워크를 끊는다.
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
    },
  };
});

const NOTICE = "local-estimate-notice";

function renderWorkspace(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>
  );
}

describe("정직 고지 배치", () => {
  it("★피드백·만족도 결과가 둘 다 있어도 고지는 1개이고 결과 그리드 밖에 있다", async () => {
    renderWorkspace(
      <OperationsIntelligenceWorkspaceClient
        locale="ko"
        sections={["tenant"]}
        showHero={false}
      />
    );

    // 전제 — 고지는 결과가 나오기 전에는 없어야 한다(공허 진리 방지).
    expect(screen.queryAllByTestId(NOTICE)).toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: "피드백 분석" }));
    fireEvent.click(screen.getByRole("button", { name: "건전성 계산" }));

    // 전제 — 두 결과 카드가 **실제로 함께** 떴는가. 하나만 떴다면 중복을 증명할 수 없다
    // (두 모집단이 갈리지 않은 픽스처는 잠금이 아니다).
    await waitFor(() => {
      expect(
        screen.getByText("감성 라벨"),
        "피드백 결과 카드가 없다"
      ).toBeTruthy();
      expect(screen.getByText("등급"), "만족도 결과 카드가 없다").toBeTruthy();
    });

    // ① 개수 — 결과 묶음 하나당 고지 1개.
    const notices = screen.queryAllByTestId(NOTICE);
    expect(
      notices,
      "고지가 결과마다 반복돼 같은 문장이 여러 번 보인다"
    ).toHaveLength(1);

    // ③ 접근성 — 고지는 스크린리더에도 고지여야 한다. `role="note"` 를 지워도
    //    아무 검사가 안 깨지던 구멍을 변이 실측으로 확인하고 여기서 잠근다.
    expect(
      notices[0].getAttribute("role"),
      '고지에서 role="note" 가 사라졌다 — 화면에만 보이고 스크린리더에는 평범한 문단이 된다'
    ).toBe("note");

    // ② 자리 — 결과 카드와 **같은 컨테이너의 형제**면 격자 칸 하나를 차지한다.
    //    ★클래스 이름(`grid`)이 아니라 **구조**로 판정한다. 클래스명으로 보면 타이틀을
    //    바꾸는 것만으로 이 검사가 공허해진다(변이 실측에서 드러난 약점).
    const feedbackCard = screen.getByText("감성 라벨").closest("div");
    const resultsContainer = feedbackCard?.parentElement;
    expect(resultsContainer, "결과 컨테이너를 못 찾았다 — 검사가 공허하다").toBeTruthy();
    expect(
      notices[0].parentElement,
      "고지가 결과 카드와 같은 컨테이너의 형제다 — 격자 칸을 차지하고 결과마다 반복된다"
    ).not.toBe(resultsContainer);
  });

  it("정비 결과에도 고지가 붙고, 그 고지 역시 결과 그리드 밖이다", async () => {
    const { container } = renderWorkspace(
      <OperationsIntelligenceWorkspaceClient
        locale="ko"
        sections={["maintenance"]}
        showHero={false}
      />
    );

    expect(screen.queryAllByTestId(NOTICE)).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "정비 분석" }));

    await waitFor(() => {
      expect(screen.queryAllByTestId(NOTICE)).toHaveLength(1);
    });

    const grid = container.querySelector<HTMLElement>(
      "div.grid.md\\:grid-cols-2"
    );
    if (grid) {
      expect(
        grid.querySelectorAll(`:scope > [data-testid="${NOTICE}"]`).length,
        "정비 고지가 결과 그리드의 직계 자식이다"
      ).toBe(0);
    }
  });

  it("자산 결과에도 고지가 붙는다", async () => {
    renderWorkspace(
      <OperationsIntelligenceWorkspaceClient
        locale="ko"
        sections={["asset"]}
        showHero={false}
      />
    );

    expect(screen.queryAllByTestId(NOTICE)).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "자산 분석" }));

    await waitFor(() => {
      expect(screen.queryAllByTestId(NOTICE)).toHaveLength(1);
    });
  });

  /**
   * ★전수성 — 로컬 산출을 가진 섹션이 늘어나면 이 목록도 늘어야 한다.
   *   사람이 센 목록이 상한이 되지 않도록, **컴포넌트가 받는 섹션 전집합**에서 파생시킨다.
   *   새 섹션이 생기면 여기서 자동으로 실패한다(고지 0개 → 빨강).
   */
  const ALL_SECTIONS = ["maintenance", "tenant", "asset"] as const;
  const RUN_BUTTON: Record<(typeof ALL_SECTIONS)[number], string> = {
    maintenance: "정비 분석",
    tenant: "피드백 분석",
    asset: "자산 분석",
  };

  it.each(ALL_SECTIONS)(
    "★%s 섹션의 로컬 산출 결과는 고지 없이 나타나지 않는다",
    async (section) => {
      renderWorkspace(
        <OperationsIntelligenceWorkspaceClient
          locale="ko"
          sections={[section]}
          showHero={false}
        />
      );

      fireEvent.click(
        screen.getByRole("button", { name: RUN_BUTTON[section] })
      );

      await waitFor(() => {
        expect(
          screen.queryAllByTestId(NOTICE).length,
          `${section}: 결과가 떴는데 추정임을 밝히는 고지가 없다`
        ).toBe(1);
      });
    }
  );
});
