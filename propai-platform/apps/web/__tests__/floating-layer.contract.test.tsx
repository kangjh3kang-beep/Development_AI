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

    // ★대상을 "스크롤되는 대화 영역"으로 못 박는다(R1 지적 L3) — 종전엔 문서 전체에서 max-h
    //   문자열만 찾아, 상한이 엉뚱한 장식용 div 로 옮겨가도 통과했다.
    const scroller = document.querySelector(".overflow-y-auto[class*='max-h-[calc(100dvh']");
    expect(scroller, "대화 스크롤 영역에서 뷰포트 기반 높이 상한을 찾지 못했다").not.toBeNull();
    // 헤더 띠를 실제로 빼고 있는지까지 확인한다(임의의 max-h 로 때우는 변경을 막는다).
    expect(scroller!.getAttribute("class")).toContain("--app-header-offset");

    // ★감산량이 **하단 앵커까지** 반영하는지 잠근다(R2 지적 MEDIUM). 이 패널은 뷰포트 하단에서
    //   위로 자라므로(fixed bottom-10 + FAB h-16 + gap-4 + mb-6 = 144px), 헤더 띠와 패널 크롬만
    //   빼면 상한을 걸고도 헤더 침범이 남는다 — 초판이 정확히 그 상태로 "침범 자체를 없앤다"고
    //   썼다. 헤더 변수 외 rem 항의 합이 크롬(≈187px) + 하단 앵커(144px) 이상이어야 한다.
    const calc = (scroller!.getAttribute("class") ?? "").match(/max-h-\[calc\(([^\]]+)\)\]/);
    expect(calc, "max-h 의 calc 식을 파싱하지 못했다").not.toBeNull();
    const remSum = Array.from(calc![1].matchAll(/(\d+(?:\.\d+)?)rem/g)).reduce(
      (sum, m) => sum + Number(m[1]) * 16,
      0,
    );
    expect(
      remSum,
      `감산의 rem 항 합이 ${remSum}px 로 부족하다 — 하단 앵커(144px)가 빠지면 헤더 침범이 남는다`,
    ).toBeGreaterThanOrEqual(331);
  });

  it("★상한의 짝: 대화 영역에는 하한도 있어야 한다 — 짧은 뷰포트에서 0px로 붕괴 금지", () => {
    // ★이 케이스가 없으면 상한만 단독으로 존재해도 위 테스트가 통과한다. 실제로 초판이 그랬고,
    //   감산량이 388px 고정(= --app-header-offset 6.25rem + 18rem)이라 dvh 390px(폰 가로모드)에서
    //   대화 영역이 2px, 388px 이하에서 0px 로 붕괴했다 — 답변이 한 글자도 안 보이는 상태다.
    //   "상한을 걸었다"가 곧 "안전하다"가 아니라는 것을 이 하한 단언이 잠근다.
    render(<AIAssistant />);
    fireEvent.click(screen.getByRole("button", { name: /AI 어시스턴트 열기/ }));

    const scroller = document.querySelector(".overflow-y-auto[class*='max-h-[calc(100dvh']");
    expect(scroller, "대화 스크롤 영역을 찾지 못했다").not.toBeNull();
    const cls = scroller!.getAttribute("class") ?? "";

    // 하한이 실제로 붙어 있고, 그 값이 0 이 아님을 확인한다(min-h-0 은 하한이 아니다).
    // ★임의값 표기(min-h-[9rem]·min-h-[144px])와 **스케일 표기(min-h-36 = 9rem)** 를 모두 받는다
    //   — 등가 리팩터를 "하한이 없다"고 거짓 실패시키면 그것도 결함이다(R2 지적 LOW). 변형자
    //   접두(sm: 등)도 허용한다.
    const min = cls.match(
      /(?:^|\s)(?:[a-z0-9-]+:)*min-h-(?:\[(\d+(?:\.\d+)?)(rem|px)\]|(\d+(?:\.\d+)?))(?=\s|$)/,
    );
    expect(min, `대화 영역에 높이 하한(min-h-*)이 없다: "${cls}"`).not.toBeNull();
    const px =
      min![3] !== undefined
        ? Number(min![3]) * 4 // Tailwind 스케일 1 = 0.25rem = 4px
        : min![2] === "rem"
          ? Number(min![1]) * 16
          : Number(min![1]);
    expect(px, `하한이 ${px}px 로 너무 낮다 — 메시지 한 줄도 안 보인다`).toBeGreaterThanOrEqual(96);
  });

  it("★열린 패널의 모든 버튼은 접근 가능한 이름을 갖는다(아이콘 전용 버튼 무명 금지)", () => {
    // ★목록형이 아니라 **전수 열거형** 불변식이다 — "닫기·전송 두 개를 고쳤다"를 잠그면 새
    //   아이콘 버튼이 늘 때 조용히 통과한다. 렌더된 버튼을 전부 훑어 이름 없는 것을 찾는다.
    //   (이 저장소 교훈: 목록형 골든은 새 항목을 못 잡는다 — 생산물을 실행으로 전수 열거하라.)
    render(<AIAssistant />);
    fireEvent.click(screen.getByRole("button", { name: /AI 어시스턴트 열기/ }));

    // ★공허 진리 방지 — 패널이 안 열리면 버튼이 FAB 하나뿐이라 "이름 없는 버튼 0개"가 참이 되어
    //   검사가 무의미해진다. 버튼 수 하한(현재 정확히 3: 닫기·전송·FAB)만으로는 패널 밖 버튼이
    //   늘었을 때 오도되므로, **패널 자체의 존재**를 먼저 못 박는다(R2 지적 LOW).
    //   부수 효과로 이 커밋이 만든 패널 id 배선도 함께 잠긴다.
    expect(
      document.getElementById("ai-assistant-panel"),
      "대화 패널이 열리지 않았다 — 아래 검사가 공허해진다",
    ).not.toBeNull();

    const buttons = Array.from(document.querySelectorAll("button"));
    expect(buttons.length, "검사할 버튼이 없다").toBeGreaterThanOrEqual(3);

    const nameless = buttons
      .filter((b) => {
        // 접근성 트리 밖 버튼은 이름이 필요 없다(있으면 오히려 오탐).
        if (b.getAttribute("aria-hidden") === "true") return false;
        const label =
          b.getAttribute("aria-label") ??
          (b.getAttribute("aria-labelledby")
            ? (document.getElementById(b.getAttribute("aria-labelledby")!)?.textContent ?? "")
            : null) ??
          b.getAttribute("title") ??
          "";
        // ★aria-hidden 자손의 텍스트는 이름이 되지 않는다(R2 지적 LOW) — svg 를 유니코드 문자로
        //   바꾸면서 aria-hidden 을 붙이면 이름이 사라지는데 textContent 로만 보면 통과한다.
        const clone = b.cloneNode(true) as HTMLElement;
        clone.querySelectorAll('[aria-hidden="true"]').forEach((n) => n.remove());
        return !label.trim() && !(clone.textContent ?? "").trim();
      })
      .map((b) => b.outerHTML.slice(0, 120));

    expect(nameless, `접근 가능한 이름이 없는 버튼: ${nameless.join(" | ")}`).toHaveLength(0);
  });

  it("★본문 일반 레이어보다는 위에 있다 — 강등이 과해 콘텐츠에 묻히면 안 된다", () => {
    const fab = fabContainerZ();

    // 본문 **일반** 레이어의 최상단은 z-[70](CadBimIntegrationPanel 배지).
    // ※ AuctionWorkspace 의 z-[70] 라이트박스는 모달 계약(appModal=800)으로 승격돼 더 이상 여기 없다.
    // 이 하한이 없으면 "네비 아래로 내린다"는 요구를 z-0 으로도 만족시켜 버튼이 사라진다.
    // ★"본문 전체 위"는 아니다(R1 지적 H1 — 초판 주석의 사실오기 정정): 사통맵 지도 오버레이
    //   (SatongMapShell 팝오버 z-[430]·레이어 레일 z-[420]·배지 칩바 z-[380]
    //    ·lib/satong-map-z.ts SATONG_UI_Z 400~500)
    //   는 지도 래퍼가 스태킹 컨텍스트를 만들지 않아 루트에서 경쟁하므로 이 버튼보다 위에 온다.
    //   지도 위에서는 지도 컨트롤이 이기는 편이 옳아 의도된 서열로 두며, 근원 봉합(래퍼 isolate)은
    //   풀스크린 경로 회귀 위험 때문에 별도 PR 대상이다.
    expect(fab).toBeGreaterThan(70);
  });
});
