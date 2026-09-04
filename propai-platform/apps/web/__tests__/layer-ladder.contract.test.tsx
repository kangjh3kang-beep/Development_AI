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
 *   · 모달 rung — **계약에는 있으나**(appModal=800) 검사 강도가 갈린다: 렌더 가능한 4종은
 *     렌더 기반, 렌더 불가한 2종(경매 상세·라이트박스 — 컴포넌트가 export 되지 않는다)은
 *     **소스 락**이다. 감시 대상은 하드코딩 목록이 아니라 **지도 공존 화면의 임포트 폐포에서
 *     파생**한다(2026-08-07 — 상대 임포트·다단계까지).
 *   · jsdom 은 레이아웃·페인트를 하지 않으므로 **z 서열만** 증명한다. 실제 픽셀 겹침은 라이브 확인 대상.
 */
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

/** apps/web 절대경로. 모듈 최상단에서 한 번만 평가한다(테스트가 cwd 를 바꾸면 그대로 흔들린다 — 이 파일은 바꾸지 않는다). */
const WEB_ROOT = process.cwd();

import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { OnboardingWizard } from "@/components/onboarding/OnboardingWizard";
import { DeskAppraisalModal } from "@/components/operations/DeskAppraisalModal";
import { LandShareModal } from "@/components/operations/LandShareModal";
import { buildPrimaryNav } from "@/components/layout/nav-config";
import { WorkspaceNavBar } from "@/components/layout/WorkspaceNavBar";
import { InputResolveModal } from "@/components/orchestration/InputResolveModal";
import { collectBackdrops, importClosure } from "@/lib/source-invariant";
import { __stripCommentsForScan as stripCommentsForScan } from "@/lib/source-invariant";
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
    // ★본문 팝오버(650)는 sticky 본문(600)과 네비(700) **사이**다 — 입력에 붙는 목록은
    //   자기 본문보다 위, 전역 내비보다 아래.
    expect(SATONG_CONTENT_Z.stickyContextHeader).toBeLessThan(SATONG_CONTENT_Z.contentPopover);
    expect(SATONG_CONTENT_Z.contentPopover).toBeLessThan(SATONG_CONTENT_Z.appNavFlyout);
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
      // ★`z-50` 같은 **대괄호 없는** 표기도 읽는다 — 종전엔 `z-[N]` 만 봐서, 계약 위반인
      //   z-50 백드롭이 "값 불일치"가 아니라 "z 를 읽지 못했다"로 보고돼 원인을 오도했다.
      const m = (el!.className ?? "").toString().match(/(?:^|\s)z-\[?(\d+)\]?(?=\s|$)/);
      expect(m, `백드롭에서 z 유틸을 찾지 못했다: ${el!.className}`).not.toBeNull();
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

    // ④ 입력 자동해소 모달 — 2026-08-07 파생 확장이 **새로 찾아낸** 실누락(z-50 이었다).
    //    MarketInsightsWorkspaceClient(지도 공존) → OrchestratorPanel → 이 모달.
    //    소스 락으로도 잡히지만, 렌더 가능한 모달은 렌더로 판정한다(주석 처리 변이 면역).
    const d = render(
      <InputResolveModal
        nodeId="feasibility"
        resolution={{ ready: [], missing: [], autoCandidates: [] }}
        onClose={() => {}}
        onRun={() => {}}
        onAutoRunUpstream={() => {}}
        onManualSubmit={() => {}}
      />,
    );
    expect(zOfBackdrop(d.container)).toBe(SATONG_CONTENT_Z.appModal);
    d.unmount();
  });

  it("★전체화면 오버레이가 계약값(appFullscreen)과 일치한다 — 상수를 장식으로 두지 않는다", () => {
    // ★리뷰 지적(H2): 계약에 appFullscreen=9990 을 넣고 **아무데서도 참조하지 않았다**.
    //   두 소비처가 문자열 하드코딩이라, CAD 를 z-[60] 으로 되돌려도 깨지는 테스트가 없었다.
    //   Tailwind JIT 상 `z-[${상수}]` 동적 생성은 불가하므로 소스로 결속한다.
    const consumers = [
      "components/design/CadBimIntegrationPanel.tsx",
      "hooks/useMapFullscreen.ts",
    ];
    for (const rel of consumers) {
      const src = readSource(rel);
      const zs = Array.from(src.matchAll(/(?:^|[\s"'`])z-\[(\d+)\]/g)).map((m) => Number(m[1]));
      // 공허 진리 방지 — z 유틸이 없으면 "위반 0"이 무의미하다.
      expect(zs.length, `${rel} 에서 z-[N] 을 찾지 못했다`).toBeGreaterThan(0);
      expect(
        zs,
        `${rel} 에 전체화면 계약값(${SATONG_CONTENT_Z.appFullscreen})이 없다 — 전체화면이 앱 크롬에 가린다`,
      ).toContain(SATONG_CONTENT_Z.appFullscreen);
    }
  });

  it("★지도 공존 화면의 모달을 **파생으로** 찾아 전수 검사한다 — 목록형 금지", () => {
    // ★종전엔 감시 대상이 하드코딩 4파일이라, 지도 공존 화면에 새 모달이 z-50 으로 추가돼도
    //   잡히지 않았다(리뷰 지적 — 이 저장소가 "목록형 골든은 새 항목을 못 잡는다"고 스스로
    //   박제한 교훈의 재발). 그래서 **시드만 고정하고 대상은 파생**한다:
    //     ①지도 컴포넌트를 임포트하는 파일 = 지도 공존 화면
    //     ②그 화면에서 시작해 **임포트를 끝까지** 따라간 폐포에서 백드롭을 수집
    //     ③각 백드롭 z 가 계약값(appModal)이거나 앱 크롬급(≥1000)이어야 한다
    //   새 모달이 지도 화면에 추가되면 **자동으로 감시망에 들어온다**.
    //
    // ★2026-08-07 두 구멍을 메웠다(자기 지적 → 실측 확인):
    //   ①임포트를 **1단계만**, 그것도 `@/…` 별칭만 따라갔다. 이 저장소는 같은 폴더를
    //     `./X` 로 부르므로 **상대 임포트가 통째로 안 보였다** → 실누락 1건
    //     (MarketInsights → OrchestratorPanel → `./InputResolveModal` z-50).
    //   ②백드롭을 `className="…"` 리터럴만 봤다 → 삼항·`cn()`·템플릿은 정규식 밖.
    //   둘 다 `lib/source-invariant.ts` 의 공용 도구(importClosure·collectBackdrops)로 옮겼고,
    //   **비리터럴 파서의 능력은 픽스처로** 잠근다(`lib/__tests__/source-invariant.backdrop.test.ts`)
    //   — 저장소에 비리터럴 백드롭이 실제로 0건이라 스캔만으로는 아무것도 증명되지 않는다.
    const MAP_SEEDS = [
      "components/precheck/SatongMapShell",
      "components/map/SatongMultiMap",
      "components/map/KakaoMapControls",
      "components/auction/AuctionMonitorPanel",
      "components/presale/ProjectPresaleMap",
    ];

    const walk = (dir: string, out: string[] = []): string[] => {
      for (const e of readdirSync(dir, { withFileTypes: true })) {
        const full = join(dir, e.name);
        if (e.isDirectory()) {
          if (e.name === "node_modules" || e.name === "__tests__") continue;
          walk(full, out);
        } else if (e.name.endsWith(".tsx") && !e.name.includes(".test.")) {
          out.push(full);
        }
      }
      return out;
    };
    const all = [...walk("components"), ...walk("app")];

    // ① 지도 공존 화면
    // ★`src.includes(seed)` 는 **주석 안 언급**까지 지도 화면으로 오인한다(리뷰 실증: 마케팅
    //   문서 파일이 감시망에 끌려 들어왔다). 정적/동적 임포트 **문**만 본다.
    const importsSeed = (src: string) =>
      MAP_SEEDS.some((seed) =>
        new RegExp(`(?:from\\s+|import\\()["'\`]@/${seed}["'\`]`).test(src),
      );
    const mapScreens = all.filter((f) => importsSeed(readFileSync(f, "utf8")));
    // 공허 진리 방지 — 시드가 아무 파일도 못 찾으면 아래 전부가 무의미하다.
    expect(mapScreens.length, "지도 공존 화면을 하나도 찾지 못했다 — 시드 경로가 낡았다").toBeGreaterThan(3);

    // ② 지도 공존 화면에서 시작한 **전이 폐포**(정적·동적·상대 임포트 전부)
    // 공허 진리 가드는 `importClosure` 가 **구조적으로** 강제한다(선언 없이는 호출 불가) —
    // 이 파일의 assertWiredThrough 가 minMatches 를 필수로 받는 것과 같은 설계다.
    const closure = importClosure(mapScreens, {
      // ★**성긴 붕괴 하한**이다(회귀는 mustInclude·minDepth 가 진다). 150 까지 올렸더니
      //   정상 제품 변경이 관통했다 — 지도 공존 화면 15개 중 하나가 지도를 그만 쓰면 폐포가
      //   122~155 로 줄고, 그중 143 은 회귀A(별칭 전용)와 **같은 값**이라 구분 불가였다.
      //   실측 확인: minFiles 를 1 로 낮춰도 회귀A 는 mustInclude 가 단독으로 잡는다.
      minFiles: 100,
      // ★개수만으로는 "깊이에서 자르기"를 못 잡는다(깊이 2 절단 140파일·깊이 3 절단 155파일이
      //   둘 다 통과했다 — 독립 검증 H1). 실측 최대깊이 4 를 그대로 요구한다.
      minDepth: 4,
      // ★해석기 **분기마다** 하나씩 — 목록형 1건이면 나머지 분기가 무잠금이다.
      mustInclude: [
        "components/orchestration/InputResolveModal.tsx", // `./` + .tsx (이 PR 이 고친 형태·깊이 2)
        "components/precheck/types.ts", // `./` + .ts
        "lib/parcel-rows.ts", // 별칭 + .ts (lib/* 가 통째로 빠지는지)
        "components/cad/types.ts", // 깊이 4 — 끝까지 따라갔는가
      ],
    });
    // ※ `../` 와 index 배럴은 **폐포에 그 형태로만 닿는 파일이 없어** 여기서 잠기지 않는다.
    //    그 두 분기는 `lib/__tests__/source-invariant.backdrop.test.ts` 의 해석기 픽스처가 맡는다.

    // ★읽기 실패를 삼키면 대상이 조용히 사라진다 — 폐포 파일은 존재가 확인된 것들이므로 그대로 던진다.
    const collected = closure.flatMap((rel) =>
      collectBackdrops(readFileSync(join(process.cwd(), rel), "utf8"), rel),
    );
    // 공허 진리 가드: 수집 0 이면 아래 판정이 무의미하다. 실측 8건 — 여유를 두면 그만큼
    // "조용히 사라져도 통과"하는 창이 생기므로 실측값 그대로 하한으로 쓴다.
    expect(
      collected.length,
      `지도 공존 폐포에서 모달 백드롭을 ${collected.length}건만 수집했다(실측 8) — 대상이 사라졌다`,
    ).toBeGreaterThanOrEqual(8);

    // ③ 판정 — 리터럴 백드롭의 z 가 계약값이거나 앱 크롬급이어야 한다.
    //    ★"판정불가" 개념을 두지 않는다. R2 에서 인라인 style·변수 z 를 판정불가로 분리했다가
    //      창(窓) 휴리스틱이 양방향으로 틀렸고(무관한 텍스트의 "zIndex: 800" 을 z 로 오인 /
    //      style 이 className 앞이면 준수 코드를 위반으로 신고), 그 분리의 효익은 진단 문구뿐이었다
    //      (기준선 0 이라 결국 똑같이 깨진다). 범위를 리터럴 클래스 표기로 좁혀 개념 자체를 없앤다.
    const violations: string[] = [];
    for (const hit of collected) {
      if (!hit.zs.length)
        violations.push(
          `${hit.file} — 백드롭에 z 클래스가 없다(인라인 style 로 주고 있다면 계약값을 클래스로 표기하라): ${hit.classes.slice(0, 70)}`,
        );
      for (const z of hit.zs)
        if (z !== SATONG_CONTENT_Z.appModal && z < APP_CHROME_Z)
          violations.push(
            `${hit.file} z=${z} — 계약값(${SATONG_CONTENT_Z.appModal}) 또는 앱 크롬급(≥${APP_CHROME_Z})이어야 한다`,
          );
    }
    expect(violations, `지도 공존 모달 층위 위반:\n${violations.join("\n")}`).toHaveLength(0);
  });

  // ★남은 경계(2026-08-07 재실측 — 앞선 두 항목 ①다단계·상대 임포트 ②비리터럴 className 은
  //   해소했다). 폐포는 **157파일**(tsx 84 + ts 73)이고, 저장소 전체 tsx 는 468 이다
  //   (분모가 다르므로 tsx 기준이면 84/468 — 독립 검증 L4 정정).
  //   지도와 공존하지 않는 화면의 모달은 여전히 이 계약 밖이고, 그건 의도한 범위다.
  //   같은 파서 규칙으로 센 전역 백드롭은 **34건**(리터럴 33 + 비리터럴 1)이고 그중 계약 밖
  //   위반이 **20건**이다(초판이 적은 36/22 는 스스로 위양성이라 제외한 `pointer-events-none`
  //   2건을 포함한 수였다 — 독립 검증 L3 정정). **일괄 승격은 하지 않기로 판정**했다
  //   (2026-08-06 실측 근거: 실위험 조합이 적어 회귀 위험 대비 이득이 낮다). 새로 생기는
  //   위험 조합은 위 파생 검사가 자동으로 잡는다.
  it.todo(
    "★파생 밖 경계: 지도 **비공존** 화면의 모달 z 산재(40/50/100/120) — 일괄 승격 대신 " +
      "지도 공존 폐포에 들어오는 순간 위 파생 검사가 잡는다(의도한 범위)",
  );

  // ★파서의 정직한 경계(2026-08-07 R3 판정으로 **범위를 줄인 뒤**의 실제 경계):
  //   수집기는 **통짜 문자열 리터럴 className 만** 본다. 삼항·`cn()`·템플릿·상수 조립은 안 본다.
  //   R1~R2 에서 비리터럴 파서를 만들었다가 3라운드 연속 위양성을 생산했고, 실측상 그 코드가
  //   지키는 대상은 전 저장소 1건(그마저 준수)이었다. 폐포 백드롭 8건은 전부 리터럴이라
  //   **감시 8/8 은 그대로**다.
  //   ★"현황 0건"이 아니다 — 조립형 className 은 폐포 안에 **실사례가 있다**:
  //     `hooks/useMapFullscreen.ts` 의 `wrapperClass()` 반환값을 쓰는 **6곳**
  //     (직접 4: AuctionMonitorPanel:858 · ProjectPresaleMap:159 · AuctionItemsMap:161 ·
  //      SatongMultiMap:2656 / 별칭 2: PopulationDensityMap:154 · MigrationRegionMap:173).
  //     ★그 전체화면 경로를 **실제로 잠그는 것**은 `components/precheck/__tests__/
  //       SatongMapShell.fullscreenOverlays.test.tsx` 계열이다. 같은 파일의 appFullscreen
  //       단언은 **파일에 문자열 `z-[9990]` 이 있는지**만 보므로 배선 락이 아니다 —
  //       전체화면 분기를 `if (false)` 로 죽여도 그 단언은 초록이다(독립 검증 실측).
  //       한때 '그 단언이 잠근다'고 적었는데 **거짓 귀속**이었다.
  //   ★★정정 2건(독립 검증): ⓐ한때 "3곳"이라 적었으나 **6곳**이다 — 별칭 소비처를 못 셌다.
  //     ⓑ이 형태는 엄밀히 "삼항·cn()·템플릿·상수 조립"이 아니라 **헬퍼 반환값**이다.
  //     삭제된 비리터럴 파서도 이 형태는 못 봤다(문자열 조각에 클래스가 없다). 즉 범주가
  //     다르므로, 이걸 근거로 "비리터럴 현황 0건이 거짓"이라고 한 것도 정확하지 않았다 —
  //     정확히는 **어느 파서로도 못 보는 별개 형태**다.
  it.todo(
    "★수집 밖 경계: **비리터럴 className**(삼항·cn()·템플릿·상수 조립) 백드롭은 수집되지 않는다 — " +
      "폐포 실사례는 useMapFullscreen.wrapperClass 계열 6곳(전체화면 z-[9990] — 실제 잠금은 " +
      "SatongMapShell.fullscreenOverlays 계열이지 이 파일의 appFullscreen 단언이 아니다)",
  );

  // ★독립 검증(제품 렌즈)이 찾은 **다른 결함 클래스** — 이 감시망은 `fixed inset-0` **백드롭**만
  //   본다. 백드롭이 아니라 **패널 자체**가 낮은 z 인 경우는 대상 밖이다. 실재 1건:
  //     `components/precheck/SatongMapShell.tsx:3499` 주소 후보 리스트박스 `z-30`
  //     — 같은 셸의 칩바(380)·레일(420)·팝오버(430) 아래이고, DOM 상 지도(:3855)보다 **앞**이라
  //       `top-full` 로 지도 상단 띠에 내려앉으면 오버레이에 가린다(z 서열은 실측·기하 겹침은
  //       정적 판독 기반 추정 — 라이브 확인 대상).
  //   이 PR 에서 고치지 않는다(3라운드 연속 감시망 결함 뒤라 범위를 넓히지 않기로 판정).
  // ★2026-08-08 라이브 실측으로 **회귀 확정 → 봉합**했다(종전 `it.todo` 를 실측이 대체).
  //   `/ko` 에서 주소 후보 목록을 연 채 240px 스크롤하니 ContextHeader(600)가 목록(z-30)을
  //   **127px 덮어** 상단 후보 2~3행이 클릭 불가였다(`elementFromPoint` 로 판정).
  //   종전엔 둘 다 z-30 이라 DOM 순서로 목록이 이겼는데, 한쪽만 600 으로 올려 뒤집힌 것이다.
  //   ★전역 값을 올리면 **그 값과 경쟁하던 모든 것을 다시 봐야 한다** — 네비 플라이아웃에 이어
  //   두 번째 짝 결함이라, 이번엔 목록형이 아니라 **형태로 파생**시켜 전수로 잠근다.
  it("★입력에 붙는 드롭다운은 계약 상수(contentPopover)를 쓴다 — 형태로 파생", () => {
    const files: string[] = [];
    const walk = (dir: string): void => {
      for (const e of readdirSync(dir, { withFileTypes: true })) {
        if (e.name === "node_modules" || e.name.startsWith(".")) continue;
        const full = join(dir, e.name);
        if (e.isDirectory()) walk(full);
        else if (/\.tsx$/.test(e.name)) files.push(full);
      }
    };
    walk(join(WEB_ROOT, "components"));
    walk(join(WEB_ROOT, "app"));

    // ★주석을 스트립한 뒤 본다 — 안 하면 **주석이 className 을 인용만 해도** 위반으로
    //   신고한다(적대검증 실증: 문서용 예시 주석 한 줄이 offender 가 됐다).
    const offenders: string[] = [];
    const anchors = new Set<string>();
    for (const f of files) {
      const raw = readFileSync(f, "utf-8");
      // ★값싼 사전 필터 — 주석 스트립(TS 파서)은 파일당 수 ms 라 전 파일에 돌리면
      //   전수 실행에서 10초를 넘긴다(단독 통과·전수 실패는 없느니만 못하다).
      //   `top-full` 이 아예 없는 파일은 스트립해도 결과가 같으므로 건너뛴다.
      if (!raw.includes("top-full")) continue;
      const src = stripCommentsForScan(raw, f);
      for (const m of src.matchAll(/className="([^"]*\btop-full\b[^"]*)"/g)) {
        const rel = f.replace(`${WEB_ROOT}/`, "");
        anchors.add(rel);
        const hit = /\bz-\[(\d+)\]/.exec(m[1]);
        // ★대역이 아니라 **값**으로 건다. `> 600` 으로 걸면 상수가 장식이 되고 상한이
        //   무제한이 된다 — z-900 이면 모달(800) 위인데도 통과한다(실증됨).
        if (!hit || Number(hit[1]) !== SATONG_CONTENT_Z.contentPopover) {
          offenders.push(`${rel} → z=${hit ? hit[1] : "없음"}`);
        }
      }
    }

    // ★공허 진리 방지 — `seen > 0` 만으로는 **절반이 사라져도** 통과한다(실증됨).
    //   알려진 앵커가 모집단에 실재하는지를 단언한다.
    for (const known of [
      "components/precheck/SatongMapShell.tsx",
      "components/common/GlobalAddressSearch.tsx",
    ]) {
      expect(anchors, `알려진 드롭다운이 모집단에서 사라졌다: ${known}`).toContain(known);
    }
    expect(
      offenders,
      `입력에 붙는 드롭다운이 계약값(${SATONG_CONTENT_Z.contentPopover})을 안 쓴다 — ` +
        "sticky 본문(600)에 덮이거나 모달(800) 위로 튀어오른다",
    ).toEqual([]);
  });

  // ★이 소스 파생의 **정직한 경계**(다음 리뷰어가 "전수"로 오독하지 않게):
  //   ①`className="…"` 리터럴만 본다 — `cn()`·삼항·배열 join 은 안 보인다(저장소 관용구다).
  //   ②`top-full` 이라는 **위치 관용구**를 대리 지표로 쓴다 — `top-[52px]` 같은 하드코딩
  //     오프셋이나 portal 로 띄우는 형태는 안 보인다.
  //   ③스캔 루트가 `apps/web` 이라 **`packages/ui` 는 사각지대**다. 거기 `dropdown.tsx` 가
  //     `cn("absolute z-50 mt-1 …")` 로 세 겹(패키지 밖·비리터럴·top-full 아님) 안 보인다.
  //     현재 apps/web 소비처 0건이라 오늘의 결함은 아니나, z-600 화면에서 쓰이는 순간이
  //     "셋째 짝 결함"이다.
  //   실효 층위(조상 스태킹 컨텍스트)는 소스로 못 본다 —
  //   `components/common/__tests__/GlobalAddressSearch.popoverRung.test.tsx` 가 렌더로 맡는다.
  it.todo(
    "★수집 밖 경계: 비리터럴 className·`top-full` 아닌 위치 관용구·`packages/ui/dropdown.tsx`(cn 비리터럴)",
  );

  it("★★z 를 **모달 칸으로 올린 표면**은 ARIA 로도 모달이어야 한다 — 선언 누락이 계약 회피였다", () => {
    // ## 이 계약이 없으면 무슨 일이 생기나 (2026-08-23 실측)
    //
    // ESC 계약(`#697`)과 포커스 계약(`#749~`)은 표면을 모을 때 **`aria-modal="true"`** 를 쓴다.
    // 그래서 화면 전체를 덮고 모달 칸 z 를 쓰면서도 **그 선언만 빠뜨리면 두 계약을 통째로
    // 빠져나간다.** 즉 *"선언을 안 하는 것"* 이 가장 쉬운 계약 회피였다.
    //
    // 실제로 셋이 그렇게 새어 있었다 — `DeskAppraisalModal`·`LandShareModal` 은 백드롭
    // 클릭으로 닫히는 전형적 모달인데 **ESC 로 안 닫히고** Tab 이 배경으로 샜고,
    // 스크린리더에는 모달로 읽히지도 않았다.
    //
    // ★그래서 수집 기준을 **시각적 사실**(화면 전체를 덮는가 + 모달 칸 z 인가)로 바꾼다.
    //   ARIA 선언은 그 사실의 **결과**여야지, 계약에 걸릴지 말지를 정하는 **입구**이면 안 된다.
    const files: string[] = [];
    const walk = (dir: string) => {
      for (const e of readdirSync(dir, { withFileTypes: true })) {
        if (e.name === "node_modules" || e.name === "__tests__") continue;
        const full = join(dir, e.name);
        if (e.isDirectory()) walk(full);
        else if (/\.tsx$/.test(e.name)) files.push(full);
      }
    };
    walk(join(WEB_ROOT, "components"));
    walk(join(WEB_ROOT, "app"));

    const modalZ = SATONG_CONTENT_Z.appModal;
    const overlays: string[] = [];
    const offenders: string[] = [];
    for (const f of files) {
      const raw = readFileSync(f, "utf-8");
      if (!raw.includes("fixed inset-0")) continue; // 값싼 사전 필터
      const src = stripCommentsForScan(raw, f);
      // 화면 전체를 덮으면서 **모달 칸 z** 를 쓰는 className 리터럴.
      const hit = new RegExp(
        `className="[^"]*\\bfixed inset-0\\b[^"]*\\bz-\\[${modalZ}\\][^"]*"`,
      ).test(src);
      if (!hit) continue;
      const rel = f.replace(`${WEB_ROOT}/`, "");
      overlays.push(rel);
      if (!src.includes('aria-modal="true"')) offenders.push(rel);
    }

    // ★공허 진리 가드 — 대상을 못 모으면 "위반 0"이 저절로 참이 된다.
    expect(
      overlays.length,
      `모달 칸(z-[${modalZ}]) 전체덮기 표면을 하나도 못 찾았다 — 스캐너·상수가 깨졌다`,
    ).toBeGreaterThan(0);

    expect(
      offenders,
      `화면 전체를 덮고 모달 칸(z-[${modalZ}])을 쓰면서 aria-modal 을 선언하지 않는다 — ` +
        "ESC·포커스 계약이 이 표면을 **수집조차 못 한다**(스크린리더에도 모달로 안 읽힌다)",
    ).toEqual([]);
  });

  it.todo(
    "★남은 회피 경로: 비리터럴 className(cn()·삼항)으로 조립한 전체덮기 오버레이는 위 수집에 " +
      "안 잡힌다 — `top-full` 계약과 같은 한계이고, 근본 처방은 오버레이 공용 컴포넌트다",
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
