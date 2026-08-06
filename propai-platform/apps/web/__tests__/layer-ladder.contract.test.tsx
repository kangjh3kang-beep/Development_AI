/**
 * 앱 전역 층위 사다리 계약 (2026-08-06).
 *
 * ★왜 필요한가: 층위를 **항목별로** 고치면 한 항목을 올릴 때 다른 항목과의 서열이 조용히
 *   뒤집힌다. 실제로 그렇게 됐다 — sticky ContextHeader 를 z-30 → 600 으로 올려 지도
 *   오버레이 문제를 고쳤더니, 데스크톱 네비 드롭다운(z-50)이 **그 아래로 깔려 클릭 불가**가
 *   됐다(전역 z 스윕이 적발). 사용자가 원래 지적한 "메뉴가 가려진다"와 같은 종류의 결함을
 *   봉합이 새로 만든 것이다.
 *
 * ★그래서 이 파일은 개별 값이 아니라 **사다리의 순서 관계**를 잠근다:
 *     지도 오버레이(≤500) < 본문 sticky(600) < 앱 네비 플라이아웃(700) < 모달(800) < 앱 크롬(1000)
 *   한 칸을 올리면 위/아래 칸과의 관계가 함께 검사되므로, 이번 같은 "한쪽만 올려 다른 쪽을
 *   덮는" 변경이 자동으로 깨진다.
 *
 * ★네비 rung 은 **렌더 기반**이다(소스 grep 아님). 초판은 readFileSync + 정규식이었는데
 *   드롭다운을 통째로 JSX 주석 처리해도 **4/4 초록**이었다 — 메뉴가 사라져도 통과한다는 뜻이다.
 *   이 저장소가 반복해 데인 "소스 검사는 주석처리 변이에 뚫린다"의 재발이라, 같은 캠페인의
 *   floating-layer / contentLayer 계약과 동일하게 **렌더된 class** 에서 z 를 뽑도록 바꿨다.
 *
 * ★커버리지 경계(정직 — "사다리 전체"가 아니다):
 *   · 오버레이 rung — 여기서는 `SATONG_UI_Z` **상수만** 본다. 소스 리터럴(z-[380]·z-[430] …)의
 *     렌더 전수는 `components/precheck/__tests__/SatongMapShell.contentLayer.test.tsx` 가 맡는다.
 *   · 본문 rung — 상수만. 소스 락은 위 contentLayer 계약에 있다.
 *   · 모달 rung — **계약에는 있으나**(appModal=800) 검사 강도가 갈린다: 렌더 가능한 3종은
 *     렌더 기반, 렌더 불가한 2종(경매 상세·라이트박스 — 컴포넌트가 export 되지 않는다)은
 *     **소스 락**이다. 그리고 감시 대상은 **하드코딩 목록**이라 신규 지도공존 모달은 무잠금이다.
 *   · jsdom 은 레이아웃·페인트를 하지 않으므로 **z 서열만** 증명한다. 실제 픽셀 겹침은 라이브 확인 대상.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { OnboardingWizard } from "@/components/onboarding/OnboardingWizard";
import { DeskAppraisalModal } from "@/components/operations/DeskAppraisalModal";
import { LandShareModal } from "@/components/operations/LandShareModal";
import { buildPrimaryNav } from "@/components/layout/nav-config";
import { WorkspaceNavBar } from "@/components/layout/WorkspaceNavBar";
import { SATONG_CONTENT_Z, SATONG_UI_Z } from "@/lib/satong-map-z";

vi.mock("next/navigation", () => ({ usePathname: () => "/ko" }));
// 역할 판별은 이 계약과 무관 — 영구 pending 으로 고정(기존 WorkspaceNavBar.test.tsx 와 동일 패턴).
vi.mock("@/lib/use-is-admin", () => ({
  fetchAuthMeRole: vi.fn(() => new Promise<string>(() => {})),
  fetchIsAdmin: vi.fn(() => new Promise<boolean>(() => {})),
}));

/** 플라이아웃을 실제로 열고, 렌더된 class 에서 z-[N] 을 뽑는다. */
function openFlyoutAndReadZ(): { dropdown: number; bridge: number | null } {
  render(<WorkspaceNavBar sections={buildPrimaryNav("ko")} />);
  const nav = screen.getByRole("navigation", { name: "Workspace navigation" });
  // ★섹션 버튼을 **명시적으로** 고른다 — getAllByRole("button")[0] 은 네비 선두에 다른 버튼이
  //   추가되면 엉뚱한 것을 집어 "menu 를 못 찾음"으로 원인을 오도한다(리뷰 지적).
  const button = within(nav).getAllByRole("button", { expanded: false })[0];
  expect(button, "aria-expanded 를 가진 섹션 버튼을 찾지 못했다").toBeTruthy();
  fireEvent.mouseEnter(button.parentElement!);

  // 플라이아웃이 안 열렸으면 여기서 throw 한다(공허 진리 방지 — 주석 처리·렌더 억제 변이가 죽는다).
  const menu = within(nav).getAllByRole("menu")[0];
  const zOf = (el: Element | null | undefined) => {
    const m = (el?.className ?? "").toString().match(/(?:^|\s)z-\[(\d+)\]/);
    return m ? Number(m[1]) : null;
  };
  const dropdown = zOf(menu);
  expect(dropdown, `드롭다운에서 z-[N] 을 읽지 못했다: ${menu.className}`).not.toBeNull();
  const bridgeEl = nav.querySelector('[data-testid^="workspace-nav-hover-bridge-"]');
  return { dropdown: dropdown!, bridge: zOf(bridgeEl) };
}

const APP_CHROME_Z = 1000; // DashboardChromeGate 헤더 · 토스트 뷰포트

function readSource(rel: string): string {
  return readFileSync(join(process.cwd(), rel), "utf8");
}


describe("앱 전역 층위 사다리", () => {
  it("★사다리 순서: 지도 오버레이 < 본문 sticky < 네비 플라이아웃 < 앱 크롬", () => {
    const maxOverlay = Math.max(...Object.values(SATONG_UI_Z));
    expect(maxOverlay).toBeLessThan(SATONG_CONTENT_Z.stickyContextHeader);
    expect(SATONG_CONTENT_Z.stickyContextHeader).toBeLessThan(SATONG_CONTENT_Z.appNavFlyout);
    expect(SATONG_CONTENT_Z.appNavFlyout).toBeLessThan(SATONG_CONTENT_Z.appModal);
    expect(SATONG_CONTENT_Z.appModal).toBeLessThan(APP_CHROME_Z);
  });

  it("★데스크톱 네비 드롭다운이 본문 sticky 위에 온다 — 렌더 결과로 판정", () => {
    // 이 관계가 깨지면 네비 메뉴 항목이 본문 카드에 가려 **클릭 불가**가 된다.
    // ★소스 grep 이 아니라 **실제로 플라이아웃을 열어** 렌더된 class 를 읽는다 — 드롭다운을
    //   주석 처리해 없애는 변이가 여기서 죽는다(초판은 그 변이에 통과했다).
    const { dropdown } = openFlyoutAndReadZ();
    expect(
      dropdown,
      `네비 드롭다운 z(${dropdown}) 가 본문 sticky(${SATONG_CONTENT_Z.stickyContextHeader}) 이하다 — 메뉴가 가려진다`,
    ).toBeGreaterThan(SATONG_CONTENT_Z.stickyContextHeader);
  });

  it("★렌더된 드롭다운 z 가 계약 상수와 일치한다(소스↔상수 동기화)", () => {
    const { dropdown } = openFlyoutAndReadZ();
    expect(dropdown).toBe(SATONG_CONTENT_Z.appNavFlyout);
  });

  it("★hover bridge 도 본문 sticky 위에 있다 — 드롭다운의 짝", () => {
    // ★초판 주석은 "본문 sticky 위여야 hover 가 끊기지 않는다"고 단언했는데, 리뷰가 기하로
    //   반증했다(bridge 는 nav 패딩 안 8px 띠라 ContextHeader 와 겹치지 않는다). 그래서 그
    //   인과는 주석에서 걷어냈다. 다만 값 자체는 드롭다운의 짝으로 계약 대역 안에 두므로,
    //   "중요하다고 주장하면서 잠그지는 않는" 상태가 되지 않게 여기서 잠근다.
    const { bridge } = openFlyoutAndReadZ();
    expect(bridge, "hover bridge 에서 z-[N] 을 읽지 못했다").not.toBeNull();
    expect(bridge!).toBeGreaterThan(SATONG_CONTENT_Z.stickyContextHeader);
    expect(bridge!).toBeLessThan(SATONG_CONTENT_Z.appNavFlyout);
  });

  it("★지도 공존 모달(렌더 가능분)이 계약값과 정확히 일치한다 — 렌더 기반", () => {
    // ★소스 grep 은 주석 처리 변이에 뚫린다(이 파일이 네비 rung 에서 이미 겪은 결함).
    //   prop 만으로 렌더되는 모달은 **실제 렌더 결과**로 판정한다.
    const zOfBackdrop = (root: HTMLElement) => {
      const el = root.querySelector<HTMLElement>('[class*="fixed"][class*="inset-0"]');
      expect(el, "모달 백드롭을 찾지 못했다 — 렌더되지 않았다").not.toBeNull();
      const m = (el!.className ?? "").toString().match(/(?:^|\s)z-\[(\d+)\]/);
      expect(m, `백드롭에서 z-[N] 을 읽지 못했다: ${el!.className}`).not.toBeNull();
      return Number(m![1]);
    };

    // ① 감정평가 모달
    const a = render(
      <DeskAppraisalModal jibun="역삼동 736" areaSqm={100} onClose={() => {}} onApply={() => {}} />,
    );
    expect(zOfBackdrop(a.container)).toBe(SATONG_CONTENT_Z.appModal);
    a.unmount();

    // ② 지분 모달
    const b = render(
      <LandShareModal jibun="역삼동 736" onClose={() => {}} onApplyArea={() => {}} />,
    );
    expect(zOfBackdrop(b.container)).toBe(SATONG_CONTENT_Z.appModal);
    b.unmount();

    // ③ 온보딩 위저드 — localStorage 가 비어 있어야 표시된다(최초 방문 재현).
    localStorage.clear();
    const c = render(<OnboardingWizard />);
    expect(zOfBackdrop(c.container)).toBe(SATONG_CONTENT_Z.appModal);
    c.unmount();
  });

  it("★렌더 불가 모달(경매 상세·라이트박스)은 소스 락 — 순서 무관 토큰 + 개수까지 잠근다", () => {
    // ★AuctionWorkspace 의 DetailModal 은 export 되지 않아 렌더할 수 없다. 소스로 잠그되,
    //   초판 정규식(`fixed inset-0 z-[N]` 연속 매칭)은 **클래스 순서만 바꿔도 스캔에서 사라지고**,
    //   같은 파일의 다른 백드롭이 "0개 아님" 가드를 만족시켜 **무성 통과**했다(리뷰 실증).
    //   그래서 ①순서 무관 토큰으로 후보를 뽑고 ②후보에 z 가 없으면 실패시키고 ③개수까지 잠근다.
    const rel = "components/auction/AuctionWorkspace.tsx";
    const src = readSource(rel);
    const candidates = Array.from(
      src.matchAll(/className="([^"]*\bfixed\b[^"]*\binset-0\b[^"]*)"/g),
    ).map((m) => m[1]);

    // 공허 진리 방지 + 개수 잠금 — 하나가 스캔에서 사라지는 경로를 막는다.
    expect(candidates.length, `${rel} 에서 fixed inset-0 백드롭 후보를 찾지 못했다`).toBe(2);

    for (const cls of candidates) {
      const m = cls.match(/(?:^|\s)z-\[(\d+)\]/);
      expect(m, `백드롭 후보에 z-[N] 이 없다(클래스 순서 변경으로 누락되면 여기서 죽는다): "${cls}"`).not.toBeNull();
      expect(
        Number(m![1]),
        `${rel} 의 모달 백드롭 z(${m![1]}) 가 계약값(${SATONG_CONTENT_Z.appModal})과 다르다`,
      ).toBe(SATONG_CONTENT_Z.appModal);
    }
  });

  it.todo(
    "★모달 감시가 **하드코딩 목록**이다 — 지도공존 화면에 새 모달이 z-50 으로 추가돼도 잡히지 않는다. " +
      "파생형(지도 컴포넌트를 임포트하는 파일 글롭)으로 바꾸는 것이 옳다. " +
      "그리고 저장소 전역 모달 z(50/60/70/100/120/1000)는 여전히 흩어져 있다(지도 비공존 화면 미적용)",
  );

  it("★모바일 네비는 앱 헤더 안에 렌더돼 계약 밖이다 — 그 전제가 유지되는지 확인", () => {
    // MobileSidebarToggle 의 z-[100]/[101] 은 헤더(z-[1000]) 컨텍스트 안이라 안전하다.
    // 헤더에서 빠지는 순간 조용히 깨지는 암묵 의존이므로 여기서 못 박는다.
    const gate = readSource("components/layout/DashboardChromeGate.tsx");
    const headerStart = gate.indexOf("<header");
    const headerEnd = gate.indexOf("</header>");
    expect(headerStart, "DashboardChromeGate 에서 <header> 를 찾지 못했다").toBeGreaterThan(-1);
    expect(headerEnd).toBeGreaterThan(headerStart);
    const headerBlock = gate.slice(headerStart, headerEnd);
    expect(headerBlock).toContain("z-[1000]");
    expect(
      headerBlock,
      "MobileSidebarToggle 이 헤더 밖으로 나갔다 — z-[100]/[101] 이 맨몸으로 지도 오버레이(≤500)와 경쟁하게 된다",
    ).toContain("MobileSidebarToggle");
  });
});
