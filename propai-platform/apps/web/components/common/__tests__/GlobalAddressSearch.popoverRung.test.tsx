/**
 * 주소 후보 드롭다운의 **본문 팝오버 칸** 계약 — 렌더 기반.
 *
 * ★왜 렌더인가 — 층위 사다리 계약 파일이 스스로 적어 둔 교훈이다: 소스 grep 락은
 *   "드롭다운을 통째로 죽여도 초록"이다(문자열이 남으니까). 실제로 이 PR 의 초판 락이
 *   `{false && …}` 렌더 억제 변이에 **생존**했다(적대검증 실증). 그래서 후보 목록을
 *   실제로 띄우고 **렌더된 class 에서** z 를 읽는다.
 *
 * ★그리고 z 값만 봐서는 부족하다 — 조상이 스태킹 컨텍스트를 만들면 **z 를 올려도 소용없다.**
 *   이 저장소가 이미 겪은 사고다(CAD 전체화면이 `relative z-10` 에 갇혀 실효 10).
 *   그래서 `DesignWorkspace.test.tsx` 의 조상 가드를 같은 방식으로 건다.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GlobalAddressSearch } from "@/components/common/GlobalAddressSearch";
import { SATONG_CONTENT_Z } from "@/lib/satong-map-z";
import { describeTraps, scanAncestorTraps } from "@/lib/stacking-context";

vi.mock("@/components/common/MapShell", () => ({
  MapShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  dynamicMap: () => function S() { return <div />; },
}));
vi.mock("@/components/ui/KakaoAddressSearch", () => ({ KakaoAddressSearch: () => <div /> }));
vi.mock("next/dynamic", () => ({ default: () => function S() { return <div />; } }));

const post = vi.fn();
vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return { ...actual, apiClient: { ...actual.apiClient, post: (...a: unknown[]) => post(...a) } };
});

beforeEach(() => {
  post.mockReset();
  post.mockResolvedValue({
    candidates: [
      { pnu: "1", jibun: "서울특별시 강남구 역삼동 736", roadAddr: "테헤란로 1" },
      { pnu: "2", jibun: "서울특별시 강남구 역삼동 737", roadAddr: "테헤란로 2" },
    ],
  });
});

/** 후보 목록을 실제로 띄우고 그 요소를 돌려준다. `wrapper` 를 주면 그 조상 아래에 마운트한다. */
async function openCandidates(wrapper?: string): Promise<HTMLElement> {
  const search = <GlobalAddressSearch single={false} writeToContext={false} />;
  render(wrapper === undefined ? search : <div className={wrapper}>{search}</div>);
  const input = screen.getAllByRole("textbox")[0];
  fireEvent.change(input, { target: { value: "역삼동" } });
  fireEvent.keyDown(input, { key: "Enter" });
  return waitFor(() => {
    const el = document.querySelector('ul[class*="top-full"]') as HTMLElement | null;
    if (!el) throw new Error("후보 드롭다운이 렌더되지 않았다 — 이 검사는 공허해진다");
    return el;
  });
}

describe("주소 후보 드롭다운 — 본문 팝오버 칸", () => {
  it("★렌더된 z 가 계약 상수와 정확히 같다(대역이 아니라 값)", async () => {
    const list = await openCandidates();
    const z = /\bz-\[(\d+)\]/.exec(String(list.className));
    expect(z, `드롭다운에 z 유틸이 없다: ${list.className}`).not.toBeNull();
    // ★`> 600` 같은 대역으로 걸면 상수가 장식이 되고 **상한이 무제한**이 된다
    //   (z-900 이면 모달 800 위로 올라가는데 대역 검사는 통과한다 — 실증됨).
    expect(Number(z![1])).toBe(SATONG_CONTENT_Z.contentPopover);
  });

  it("★조상이 스태킹 컨텍스트를 만들지 않는다 — 만들면 z 를 올려도 갇힌다", async () => {
    const list = await openCandidates();

    // ★판정은 **공용 판정기**가 한다(lib/stacking-context.ts). 종전 이 자리의 정규식은
    //   `isolate|transform|filter|backdrop-filter` 를 찾았는데 이건 Tailwind **v3** 토큰이다.
    //   저장소는 v4 라서 실측 결과 `backdrop-filter` 0건·맨몸 `filter` 2건인 반면
    //   v4 에서 실제로 층 상자를 만드는 `backdrop-blur-*`(120건)·`opacity-N`(603건)·`blur-*`(27건) 는
    //   **한 건도 못 봤다** — "조상이 깨끗한지 검사한다"는 선언이 대부분 공허했다.
    const scan = scanAncestorTraps(list);

    // 공허 진리 방지 — 조상을 실제로 훑었는가.
    expect(scan.depth, "조상이 0개다 — 렌더 구조가 바뀌었다").toBeGreaterThan(1);
    expect(
      scan.traps,
      `드롭다운 조상에 스태킹 컨텍스트가 있다 — z-${SATONG_CONTENT_Z.contentPopover} 를 걸어도 갇힌다:\n${describeTraps(scan.traps)}`,
    ).toHaveLength(0);
  });

  // ★★위 검사만으로는 **아무것도 잠기지 않는다.** 단독 렌더의 조상 체인에는 스태킹 컨텍스트가
  //   원래 0개라서, 판정 로직을 통째로 지워도 초록이기 때문이다(차가 0인 픽스처 = 잠금 아님, 규율 A-2).
  //   그래서 **실제 프로덕션에서 트랩을 만드는 모양**을 조상으로 세워 두 모집단을 가른다.
  //   아래 셋은 실측한 소비처 className 을 **그대로(verbatim)** 옮긴 것이다
  //   (종전엔 SiteInitiator 것만 손질된 편집본이라 "실측 그대로"가 사실이 아니었다):
  //     · `app/[locale]/(dashboard)/projects/new/page.tsx:199`
  //     · `components/projects/ProjectAnalysisFlow.tsx:62`
  //     · `components/projects/SiteInitiator.tsx:140`
  describe.each([
    ["relative z-10 max-w-2xl space-y-5", "ProjectAnalysisFlow.tsx:62"],
    ["grid gap-2 relative z-10", "projects/new/page.tsx:199"],
    [
      "relative rounded-[var(--radius-lg)] border border-[var(--line)] bg-[var(--glass-bg)] p-8 shadow-2xl backdrop-blur-3xl",
      "SiteInitiator.tsx:140",
    ],
  ])("실측된 소비처 모양(%s = %s)을 조상으로 세우면", (wrapper) => {
    it("★가드가 빨개진다 — 이게 성립해야 위 '위반 0' 이 의미를 갖는다", async () => {
      const list = await openCandidates(wrapper);
      const scan = scanAncestorTraps(list);
      expect(
        scan.traps.length,
        `이 조상 모양을 위반으로 잡지 못한다 — 가드가 프로덕션 형태를 잠그지 않는다: ${wrapper}`,
      ).toBeGreaterThan(0);
    });
  });

  it("★잘라내는 조상이 있어도 무해한 근거 — 본문 최소높이가 팝오버 최대높이보다 크다", async () => {
    const list = await openCandidates();

    // 이 컴포넌트의 다필지 패널은 둥근 모서리를 위해 스스로 `overflow-hidden` 을 건다.
    // 그건 팝오버를 **잘라낼 수 있는 상태**다 — 지금 무해한 이유는 오직 하나,
    // 검색줄 **아래 본문이 팝오버보다 훨씬 길어서** 팝오버가 패널 밖으로 나가지 않기 때문이다.
    // ★그 전제를 산문이 아니라 **숫자로 잠근다**. 본문 최소높이를 줄이면 여기서 빨개진다.
    //   (전제가 깨지면 잘림은 실제 결함이 된다 — 사용자는 하단 후보를 클릭할 수 없다.)
    //   ※ 잘라내는 조상이 0개가 되면 이 검사는 지킬 전제가 없어진다 — 그때는 삭제할 것.
    //     다만 그 경우에도 **조용히 통과시키지 않는다**: 아래 두 상수 확인은 그대로 수행한다.
    const clip = scanAncestorTraps(list, { kinds: ["clipping"] });

    // 팝오버 최대높이 — 스케일 표기(`max-h-64`)와 임의값(`max-h-[256px]`) 둘 다 읽는다.
    //   ★종전엔 스케일 표기만 읽어서, 임의값으로 바꾸면 기하 단언이 **실행조차 안 됐다**.
    const cls = String(list.className);
    const scale = /\bmax-h-(\d+)\b/.exec(cls);
    const arb = /\bmax-h-\[(\d+)px\]/.exec(cls);
    expect(scale ?? arb, `팝오버에서 max-h 를 찾지 못했다: ${cls}`).not.toBeNull();
    const popoverMaxPx = arb ? Number(arb[1]) : Number(scale![1]) * 4; // 간격 1 = 0.25rem = 4px

    // 여유는 **잘라내는 상자 안에서, 그리고 팝오버 앵커보다 뒤(아래)에 오는** 요소로만 센다.
    //   ★종전엔 상자 안 전체에서 `Math.max` 를 골라, 앵커 **위**에 있는 큰 요소도 근거가 될 수
    //     있었다. 실제로 이 잠금은 `min-h-[500px]` 을 80% 줄여도 초록이었다(적대검증 실측) —
    //     같은 상자 안 `min-h-[420px]` 이 백업으로 남았기 때문이다. 그래서 **앵커 뒤**로 좁히고
    //     **가장 작은 값**을 본다: 어느 하나만 줄어도 여기서 빨개진다.
    const box = clip.traps[0]?.element ?? document.body;
    const below = Array.from(box.querySelectorAll("*")).filter(
      (el) => !!(list.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING),
    );
    const bodies = below
      .map((el) => /\bmin-h-\[(\d+)px\]/.exec(el.getAttribute("class") ?? "")?.[1])
      .filter((v): v is string => !!v)
      .map(Number);
    expect(
      bodies.length,
      "팝오버 아래에 최소높이(min-h-[Npx])를 선언한 요소가 없다 — 무해하다는 근거가 사라졌다",
    ).toBeGreaterThan(0);

    expect(
      Math.min(...bodies),
      `팝오버 최대높이(${popoverMaxPx}px)가 아래 본문 최소높이(최소 ${Math.min(...bodies)}px)를 넘어선다 — 잘라내는 조상 ${clip.traps.length}개 아래에서 하단 후보가 잘린다`,
    ).toBeGreaterThan(popoverMaxPx);
  });

  // ── 부채(초록 안에 드러내 둔다 — 커밋 메시지에만 적으면 다음 사람이 못 본다) ──
  // ★이 파일의 가드는 `GlobalAddressSearch` 를 **단독 렌더**한다. 따라서 조상 체인에
  //   소비처 래퍼가 **하나도 없다** — 실제 트랩이 사는 곳(소비처)을 구조적으로 볼 수 없다.
  //   실측(2026-08-12): `<GlobalAddressSearch` 렌더 14곳 + `<ProjectAddressInput` 렌더 14곳.
  //   그중 조상 트랩이 실재하는 곳 8건 — `projects/new/page.tsx:201`(`.cc-panel` overflow:hidden
  //   + `relative z-10`) · `ProjectAnalysisFlow.tsx:72`(입력 아래 여유 거의 0 = **가장 심함**) ·
  //   `PermitAiWorkspaceClient.tsx:242` · `RegulationsWorkspaceClient.tsx:184` ·
  //   `SiteInitiator.tsx:151`(`backdrop-blur-3xl` + framer-motion 인라인 transform) ·
  //   `PreCheckWorkspace.tsx:264` · `RoughScenarioPanel.tsx:521`(`.sa-di-block`) ·
  //   `ProjectPipelinePanel.tsx:1147`. ※ 이 목록은 **스냅샷**이다 — 가드는 목록이 아니라
  //   소스에서 **파생**해야 한다(사람이 센 목록은 곧 상한이 된다 — 규율 A-4).
  it.todo("소비처 조상 체인까지 태운다 — 단독 렌더로는 소비처가 만든 트랩을 볼 수 없다");
});
