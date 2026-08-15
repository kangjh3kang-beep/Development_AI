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
 *   **DOM 구조와 개수**이지 "화면에서 어떻게 보이는가"가 아니다.
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

    // ② 자리 — 결과 그리드의 직계 자식이면 격자 칸 하나를 차지한다.
    for (const n of notices) {
      const parentClass = n.parentElement?.className ?? "";
      expect(
        /(^|\s)grid(\s|$)/.test(parentClass),
        `고지가 그리드의 직계 자식이라 격자 칸을 차지한다 — parent="${parentClass}"`
      ).toBe(false);
    }
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
