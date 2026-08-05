/**
 * 플로팅 레이어 서열 계약 (모바일 IA P0 회귀망, 2026-08-05).
 *
 * ★사용자 지적: "메뉴 아이콘·텍스트필드가 네비게이션 위로 나타난다."
 *   실측된 종전 서열은 `딤 100 < 네비 드로어 101 < 앱 헤더 1000 < 플로팅 AI 버튼 9999` 였다.
 *   모바일 메뉴를 열면 AI 플로팅 버튼이 메뉴와 딤 **위에** 떠서 메뉴를 가리고 오조작을 유발했다.
 *
 * ★이 파일이 잠그는 것: z 값을 **소스 grep 이 아니라 실제 렌더 결과의 class 속성에서 뽑아**
 *   서로 비교한다. 한쪽만 바꾸고 다른 쪽을 잊는 변경(예: FAB 을 다시 9999 로 올림, 네비를
 *   9999 위로 올림)이 어느 방향이든 이 테스트를 깨뜨린다 — 숫자를 기대값으로 하드코딩하지
 *   않았으므로 "둘 다 같이 올리는" 정당한 재조정은 통과한다(서열만이 계약이다).
 *
 * ★한계(정직 바운딩): jsdom 은 레이아웃·페인트를 하지 않으므로 이 테스트는 z 서열만 증명한다.
 *   "실제로 겹치는가"는 증명하지 않는다 — 겹침 자체는 라이브 뷰포트 확인 대상이다.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AIAssistant } from "@/components/common/AIAssistant";
import { ConfirmDeleteModal } from "@/components/common/ConfirmDeleteModal";
import { MobileSidebarToggle } from "@/components/layout/MobileSidebarToggle";

vi.mock("next/navigation", () => ({
  usePathname: () => "/ko",
  useParams: () => ({ locale: "ko" }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

// 네트워크 차단(useIsAdmin → /auth/is-admin 등) — 영구 pending 으로 고정.
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

// 드로어 '안'의 메뉴 트리는 이 계약과 무관(네비 서열만 본다) — 스텁으로 대체해 무겁지 않게.
vi.mock("@/components/layout/SidebarNav", () => ({
  SidebarNav: () => <nav data-testid="sidebar-nav-stub" />,
}));

/** 렌더된 요소의 class 에서 Tailwind 임의값 z 유틸(z-[N])의 N 을 뽑는다. */
function renderedZ(el: Element | null, what: string): number {
  expect(el, `${what} 요소를 찾지 못했다`).not.toBeNull();
  const cls = el!.getAttribute("class") ?? "";
  const match = cls.match(/(?:^|\s)z-\[(\d+)\]/);
  // ★공허 진리 방지 — z 유틸이 아예 없으면 "서열을 지켰다"가 아니라 계약 밖으로 나간 것이다.
  expect(match, `${what} 의 class 에 z-[N] 유틸이 없다: "${cls}"`).not.toBeNull();
  return Number(match![1]);
}

function fabContainerZ(): number {
  render(<AIAssistant />);
  const button = screen.getByRole("button", { name: /AI 어시스턴트 열기/ });
  return renderedZ(button.closest("div.fixed"), "AI 플로팅 버튼 컨테이너");
}

function navZ(): { dim: number; drawer: number } {
  const { container } = render(<MobileSidebarToggle sections={[]} />);
  // 드로어는 닫힘 상태에서도 항상 마운트된다(-translate-x-full 로 오프캔버스).
  const drawer = renderedZ(container.querySelector("aside"), "네비 드로어");
  // 딤은 열렸을 때만 렌더된다 — 햄버거를 실제로 눌러 띄운다.
  // ★fireEvent(=act 래핑)여야 상태 갱신이 조회 전에 반영된다. 네이티브 element.click()은
  //   갱신이 flush 되기 전에 다음 줄이 실행돼 딤을 못 찾는다(첫 작성 시 실제로 그렇게 실패했다).
  fireEvent.click(screen.getByRole("button", { name: "메뉴 열기" }));
  const dim = renderedZ(container.querySelector("div.fixed.inset-0"), "네비 딤");
  return { dim, drawer };
}

describe("플로팅 레이어 서열 — AI 버튼은 네비/모달 아래에 있어야 한다", () => {
  it("★AI 플로팅 버튼 < 네비 딤 < 네비 드로어", () => {
    const fab = fabContainerZ();
    const { dim, drawer } = navZ();

    expect(fab, `FAB(${fab}) 이 네비 딤(${dim}) 위에 있다 — 메뉴를 가린다`).toBeLessThan(dim);
    expect(dim).toBeLessThan(drawer);
  });

  it("★AI 플로팅 버튼 < 모달 — 확인 모달이 항상 위에 온다", () => {
    const fab = fabContainerZ();

    render(
      <ConfirmDeleteModal open name="테스트" onConfirm={() => {}} onCancel={() => {}} />,
    );
    const modal = renderedZ(screen.getByRole("dialog"), "확인 모달");

    expect(fab, `FAB(${fab}) 이 모달(${modal}) 위에 있다`).toBeLessThan(modal);
  });

  it("★강등의 짝: 열린 대화 패널은 앱 헤더 띠를 침범하지 않도록 높이 상한을 갖는다", () => {
    // z 를 내린 순간 앱 헤더(z-1000)가 이 패널 **위**로 올라온다. 상한이 없으면 짧은 뷰포트에서
    // 패널 상단(대화 제목)이 헤더에 가린다 — 강등이 만들어내는 새 결함이라 같이 잠근다.
    render(<AIAssistant />);
    fireEvent.click(screen.getByRole("button", { name: /AI 어시스턴트 열기/ }));

    const scroller = document.querySelector('[class*="max-h-[calc(100dvh"]');
    expect(scroller, "대화 패널의 뷰포트 기반 높이 상한을 찾지 못했다").not.toBeNull();
    // 헤더 띠를 실제로 빼고 있는지까지 확인한다(임의의 max-h 로 때우는 변경을 막는다).
    expect(scroller!.getAttribute("class")).toContain("--app-header-offset");
  });

  it("★본문 최상단 레이어보다는 위에 있다 — 강등이 과해 콘텐츠에 묻히면 안 된다", () => {
    const fab = fabContainerZ();

    // 본문에서 가장 높은 층은 z-[70](AuctionWorkspace·CadBimIntegrationPanel 오버레이).
    // 이 하한이 없으면 "네비 아래로 내린다"는 요구를 z-0 으로도 만족시켜 버튼이 사라진다.
    expect(fab).toBeGreaterThan(70);
  });
});
