/**
 * 모달 ESC 해제 계약 (2026-08-18 · R2 강화).
 *
 * ## 증상
 *
 * `aria-modal="true"` 를 선언하는 표면 13개(파일 11개) 중 **ESC 로 닫히는 것은 4개뿐**이었고,
 * 그 4개는 각자 `window`/`document` 에 keydown 을 걸고 있었다. 각자 리스너는 두 표면이 함께
 * 열려 있을 때 **같은 keydown 에 둘 다 닫는다** — 사용자는 한 번 눌렀는데 두 개가 사라진다.
 *
 * ## 이 파일이 잠그는 것
 *
 * ① **파생 전수** — 소스에서 `aria-modal="true"` 선언을 긁어 표면을 스스로 모은다. 사람이 센
 *    목록이 아니므로 새 모달이 생기면 자동으로 감시망에 들어온다.
 * ② **배선의 모양** — 등록 호출이 "있기만" 해서는 안 된다. 열림 인자가 상수 리터럴이면 안 되고
 *    (열림 검사를 안 한 것과 구분되지 않는다), 칸은 `DISMISS_Z` 에서 와야 하며, 한 파일에 표면이
 *    여럿이면 **서로 다른 칸**이어야 한다(동률이면 등록 순서가 승부를 정한다).
 * ③ **조정기 밖 ESC 리스너 0건** — 이 계약이 없으면 다음 미편입이 조용히 들어온다. 실제로
 *    R1 이 놓쳤다: `WorkspaceNavBar` 가 `document` 에 ESC 를 걸고 **열림 검사도 없이** 대시보드
 *    전 페이지 위에 떠 있었고, ESC 1회에 모달과 플라이아웃이 함께 닫혔다(R2 실측).
 * ④ **런타임 표** — 소스 검사만으로는 배선을 죽이는 변이가 통과한다(R2 실측 3종 SURVIVED:
 *    `open`→`false` · 칸 바꿔치기 · `close`→무동작). 그래서 렌더 가능한 표면을 **표로 돌려**
 *    실제로 등록되는 칸과 ESC 로 닫히는지를 태운다.
 *
 * ## 범위 (정직 — 하지 않은 것)
 *
 * 이번 계약은 **ESC 만** 다룬다. 포커스 트랩·초기 포커스·포커스 복귀는 폼 표면에서 회귀 위험이
 * 커서 다음 단계로 미뤘고, 아래 `it.todo` 로 초록 안에 **보이게** 남긴다.
 * jsdom 이므로 **실제 브라우저 확인이 아니다**(IME 조합·전체화면 API 는 흉내 낼 수 없다).
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import type { ReactElement } from "react";

import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfirmDeleteModal } from "@/components/common/ConfirmDeleteModal";
import ConsentModal from "@/components/desk/ConsentModal";
import { DocumentViewerModal } from "@/components/collaboration/DocumentViewerModal";
import { G2BBidDetailModal } from "@/components/g2b/G2BBidDetailModal";
import { InputResolveModal } from "@/components/orchestration/InputResolveModal";
import { FieldMenuSheet } from "@/components/sales-app/FieldNav";
import SiteEnterModal from "@/components/sales-app/SiteEnterModal";
import SitePasswordModal from "@/components/sales-app/SitePasswordModal";
import CustomerCardDrawer from "@/components/sales/CustomerCardDrawer";
import { visibleTabs } from "@/components/sales-app/roleConfig";
import { buildPrimaryNav } from "@/components/layout/nav-config";
import { WorkspaceNavBar } from "@/components/layout/WorkspaceNavBar";
import { DISMISS_Z, __dismissibleSnapshot } from "@/lib/satong-dismiss";
import { __stripCommentsForScan } from "@/lib/source-invariant";

// 네비의 역할 판별은 이 계약과 무관 — 영구 pending 으로 고정(기존 WorkspaceNavBar.test.tsx 관례).
vi.mock("@/lib/use-is-admin", () => ({
  fetchAuthMeRole: vi.fn(() => new Promise<string>(() => {})),
  fetchIsAdmin: vi.fn(() => new Promise<boolean>(() => {})),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/ko",
}));
// 네트워크는 이 계약의 대상이 아니다 — **영구 pending** 으로 고정해 렌더만 통과시킨다
// (해소되는 목을 주면 상태 갱신이 테스트 밖에서 일어나 소음이 된다).
vi.mock("@/lib/api-client", () => {
  const never = () => new Promise(() => {});
  class ApiClientError extends Error {
    status = 0;
  }
  return {
    ApiClientError,
    apiClient: { get: never, post: never, patch: never, delete: never },
    resolveApiOrigin: () => "",
  };
});

/** apps/web 절대경로. 모듈 최상단에서 한 번만 평가한다(테스트가 cwd 를 바꾸면 흔들린다). */
const WEB_ROOT = process.cwd();

/* ────────────────────────────── 파생 수집 ────────────────────────────── */

/**
 * ★속성 **값**까지 본다(R2 정정). 초판은 `/aria-modal/g` 였는데 `aria-modal="false"` 는 유효한
 *   ARIA 이고 뜻은 정확히 **"모달이 아니다"** 다 — 그걸 모달로 세면 정상 코드를 위반으로
 *   신고한다(가드의 위양성도 결함이다).
 */
const ARIA_MODAL_TRUE = /aria-modal\s*=\s*(?:"true"|'true'|\{\s*true\s*\})/g;
/** 등록으로 인정하는 호출 — 훅 2종(권장) 또는 조정기 직접 호출(사통맵 기존 소비처). */
const REGISTER_CALL = /\b(useDismissible|useDismissibleWhileMounted|registerDismissible)\s*\(/g;
/** `useDismissible(칸, 열림, ...)` 의 앞 두 인자를 뜯어 본다. */
const USE_DISMISSIBLE_ARGS = /\buseDismissible\s*\(\s*([^,]+?)\s*,\s*([^,]+?)\s*,/g;
/** `useDismissibleWhileMounted(칸, ...)` 의 첫 인자. */
const WHILE_MOUNTED_ARGS = /\buseDismissibleWhileMounted\s*\(\s*([^,]+?)\s*,/g;

/**
 * 면제 — **왜 구멍이 아닌지**를 여기 적는다. 사유 없이 이름만 넣지 않는다.
 * (비어 있다 = 모든 모달 표면이 배선됐다.)
 */
const EXEMPT: Record<string, string> = {};

/**
 * 한 파일 안의 여러 `aria-modal="true"` 가 **같은 하나의 표면**일 때(예: 같은 모달을 두 갈래로
 * 렌더) 등록 1회로 충분하다. 그 경우만 여기에 사유와 함께 적는다.
 * ★기본 규칙(선언 수 ≤ 등록 수)을 약화시키는 예외이므로, "왜 같은 표면인지"를 반드시 적는다.
 * (지금은 비어 있다 — 현재 다중 선언 파일 2개는 **서로 다른 표면**이다.)
 */
const SHARED_REGISTRATION: Record<string, string> = {};

function walk(dir: string, out: string[] = []): string[] {
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch {
    return out;
  }
  for (const e of entries) {
    if (e === "node_modules" || e === ".next" || e === "dist") continue;
    const p = join(dir, e);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.tsx?$/.test(p) && !/\.test\.tsx?$/.test(p) && !p.includes("__tests__")) out.push(p);
  }
  return out;
}

/**
 * 실행되는 줄만 남긴다 — 주석 속 문자열이 검사를 속이지 못하게.
 * `__stripCommentsForScan` 은 TypeScript 파서 기반이라 블록 주석·JSDoc·**줄 주석**을 모두 지운다
 * (2026-08-07 R3 에서 줄 주석까지 파서 간극으로 편입됐다 — 손수 정규식이 아니다).
 */
function executable(file: string): string {
  return __stripCommentsForScan(readFileSync(file, "utf8"), file);
}

/**
 * 검사 대상 소스. `lib` 를 **일부러 포함**한다 — 조정기 자신이 이 집합 안에 있어야
 * "조정기만 예외"라는 제외가 실재하는 제외가 되고(빈 제외가 아니고), 앞으로 lib 에 새로
 * 생기는 전역 리스너도 감시망에 들어온다.
 */
function sourceFiles(): string[] {
  return [
    ...walk(join(WEB_ROOT, "components")),
    ...walk(join(WEB_ROOT, "app")),
    ...walk(join(WEB_ROOT, "hooks")),
    ...walk(join(WEB_ROOT, "lib")),
  ];
}

function rel(file: string): string {
  return relative(WEB_ROOT, file).replace(/\\/g, "/");
}

/** 조정기 자신. 정의 자리는 소비처 규칙(리터럴 금지·DISMISS_Z 칸)의 대상이 아니다. */
const COORDINATOR = "lib/satong-dismiss.ts";

/** 소비처만 — 조정기 정의 파일을 뺀 집합. */
function consumerFiles(): string[] {
  return sourceFiles().filter((f) => rel(f) !== COORDINATOR);
}

type Surface = { file: string; declared: number; registered: number; rungs: string[] };

/** 소스에서 모달 표면을 **파생으로** 모은다(사람이 센 목록 금지). */
function collectSurfaces(): Surface[] {
  const out: Surface[] = [];
  for (const f of consumerFiles()) {
    const src = executable(f);
    const declared = (src.match(ARIA_MODAL_TRUE) ?? []).length;
    if (declared === 0) continue;
    const rungs = [
      ...[...src.matchAll(USE_DISMISSIBLE_ARGS)].map((m) => m[1].trim()),
      ...[...src.matchAll(WHILE_MOUNTED_ARGS)].map((m) => m[1].trim()),
    ];
    out.push({
      file: rel(f),
      declared,
      registered: (src.match(REGISTER_CALL) ?? []).length,
      rungs,
    });
  }
  return out.sort((a, b) => a.file.localeCompare(b.file));
}

describe("모달 ESC 해제 계약 — 소스 파생 전수", () => {
  it("전제: 표면을 실제로 모았다(공허 진리 가드)", () => {
    // ★"위반 0"이 "대상 0"이어서 참이 되는 일을 막는다. 착수 시점 실측은 파일 11 · 선언 13.
    const surfaces = collectSurfaces();
    expect(surfaces.length, "aria-modal 표면을 못 찾았다 — 스캐너가 죽었는지 먼저 의심하라").toBeGreaterThanOrEqual(10);
    const declared = surfaces.reduce((n, s) => n + s.declared, 0);
    expect(declared, "선언 총량이 줄었다 — 표면이 사라졌거나 스캐너가 덜 본다").toBeGreaterThanOrEqual(13);
  });

  it("대조군: 주석 속 선언은 세지 않고, `aria-modal=\"false\"` 도 모달로 세지 않는다", () => {
    const count = (src: string) => (__stripCommentsForScan(src, "x.tsx").match(ARIA_MODAL_TRUE) ?? []).length;
    expect(count(`// <div aria-modal="true" />\n/* aria-modal="true" */\nconst x = 1;\n`), "주석에 뚫린다").toBe(0);
    // ★위양성 대조 — "모달이 아니다"를 뜻하는 유효한 ARIA 를 위반으로 신고하면 정상 코드를 막는다.
    expect(count(`<div aria-modal="false" />`), "aria-modal=\"false\" 를 모달로 셌다").toBe(0);
    // 양성대조 — 실행되는 줄의 참 선언은 그대로 센다(스캐너가 전부 삼키지 않는다).
    expect(count(`<div aria-modal="true" />`)).toBe(1);
    expect(count(`<div aria-modal={true} />`)).toBe(1);
  });

  it("★모든 모달 표면이 ESC 조정기에 등록한다(면제는 사유와 함께)", () => {
    const violations = collectSurfaces()
      .filter((s) => !EXEMPT[s.file])
      .filter((s) => s.registered < (SHARED_REGISTRATION[s.file] ? 1 : s.declared))
      .map((s) => `${s.file}: aria-modal ${s.declared}개 · 등록 ${s.registered}개`);
    expect(
      violations,
      "ESC 로 닫히지 않는 모달이 있다. useDismissible(DISMISS_Z.…, open, close) 로 등록하거나,\n" +
        "구멍이 아니라면 EXEMPT 에 **사유와 함께** 넣어라.\n" + violations.join("\n"),
    ).toEqual([]);
  });

  it("★열림 인자에 상수 리터럴을 쓰지 않는다 — 열림 검사 누락과 구분되어야 한다", () => {
    // R2 실측: `open` 자리를 `false` 로 바꾸는 변이가 초판 락을 그대로 통과했다(SURVIVED).
    // 의도가 정말 "마운트 = 열림"이면 `useDismissibleWhileMounted` 라는 **이름**을 쓴다.
    const bad: string[] = [];
    for (const f of consumerFiles()) {
      for (const m of executable(f).matchAll(USE_DISMISSIBLE_ARGS)) {
        if (/^(true|false)$/.test(m[2].trim())) bad.push(`${rel(f)}: useDismissible(${m[1]}, ${m[2]}, …)`);
      }
    }
    expect(bad, "열림 자리에 리터럴이 있다 — useDismissibleWhileMounted 를 쓰거나 실제 상태를 넘겨라\n" + bad.join("\n")).toEqual([]);
  });

  it("★등록 칸은 DISMISS_Z 에서 온다 — 숫자를 새로 짓지 않는다", () => {
    const keys = new Set(Object.keys(DISMISS_Z));
    const bad: string[] = [];
    for (const f of consumerFiles()) {
      const src = executable(f);
      const rungs = [
        ...[...src.matchAll(USE_DISMISSIBLE_ARGS)].map((m) => m[1].trim()),
        ...[...src.matchAll(WHILE_MOUNTED_ARGS)].map((m) => m[1].trim()),
      ];
      for (const r of rungs) {
        const key = /^DISMISS_Z\.(\w+)$/.exec(r)?.[1];
        if (!key || !keys.has(key)) bad.push(`${rel(f)}: ${r}`);
      }
    }
    expect(bad, "DISMISS_Z 의 칸이 아닌 값으로 등록한다\n" + bad.join("\n")).toEqual([]);
  });

  it("★한 파일에 표면이 여럿이면 **서로 다른 칸**이어야 한다 — 동률은 등록 순서가 승부를 정한다", () => {
    // R2 실측: OrgTree 의 두 시트가 같은 칸(800)이라, 키보드로 둘이 함께 열리면 **아래 것**이
    // 닫히고 위에 보이는 시트가 남았다(first:1 / second:0). 그건 이 조정기가 없애려던 상태다.
    const multi = collectSurfaces().filter((s) => s.declared >= 2 && !SHARED_REGISTRATION[s.file]);
    expect(multi.length, "다중 표면 파일이 하나도 없다 — 이 검사가 공허하다").toBeGreaterThanOrEqual(2);
    const bad = multi
      .filter((s) => new Set(s.rungs).size < s.declared)
      .map((s) => `${s.file}: 표면 ${s.declared}개인데 칸은 ${new Set(s.rungs).size}종 (${s.rungs.join(", ")})`);
    expect(bad, "같은 파일의 두 표면이 같은 칸에 등록한다\n" + bad.join("\n")).toEqual([]);
  });

  it("면제 목록의 항목은 실재해야 한다(죽은 면제 방지)", () => {
    const files = new Set(collectSurfaces().map((s) => s.file));
    for (const [f, reason] of [...Object.entries(EXEMPT), ...Object.entries(SHARED_REGISTRATION)]) {
      expect(files.has(f), `면제에 적힌 ${f} 가 더는 모달 표면이 아니다 — 면제를 지워라`).toBe(true);
      expect(reason.length, `면제 사유가 비었다: ${f}`).toBeGreaterThan(10);
    }
  });
});

/* ──────────────────── 조정기 밖 ESC 리스너 0건 (HIGH-1) ──────────────────── */

/**
 * 문서/윈도우 레벨 ESC 리스너를 찾는다.
 *
 * ★요소 레벨 `onKeyDown` 은 **대상이 아니다** — 포커스가 그 요소에 있을 때만 발화하므로 문서
 *   전역 리스너끼리의 충돌을 만들지 않는다(`lib/satong-dismiss.ts` 의 경계 선언과 같다).
 *   실제 사례: `PipelineResultDetail`·`CADEditor` 의 입력 onKeyDown.
 * ★그래서 파일에 "Escape" 가 있는지를 보지 않고, **addEventListener 에 넘긴 핸들러의 본문**만
 *   본다. 핸들러는 이 저장소에서 항상 등록 직전에 `const 이름 = …` 로 선언된다 — 그 사이 구간을
 *   읽는다. 선언을 못 찾으면 **조용히 넘기지 않고 실패**시킨다(스캐너가 눈먼 채 초록이 되는 것 방지).
 */
function findGlobalEscListeners(): string[] {
  const hits: string[] = [];
  for (const f of sourceFiles()) {
    if (rel(f) === COORDINATOR) continue; // 조정기 자신 — 이 하나만 ESC 를 받는다
    const src = executable(f);
    for (const m of src.matchAll(/(?:window|document)\.addEventListener\(\s*"keydown"\s*,\s*(\w+)/g)) {
      const handler = m[1];
      const declIdx = src.lastIndexOf(`const ${handler} =`, m.index);
      expect(declIdx, `${rel(f)}: keydown 핸들러 ${handler} 의 선언을 못 찾았다 — 스캐너를 고쳐라`).toBeGreaterThan(-1);
      const body = src.slice(declIdx, m.index);
      if (/["']Escape["']/.test(body)) hits.push(`${rel(f)}: ${handler}`);
    }
  }
  return hits.sort();
}

/** 조정기 밖 ESC 를 **의도적으로** 남긴 곳 — 사유를 적는다(부채를 초록 안에 보이게). */
const EXEMPT_LISTENERS: Record<string, string> = {};

describe("조정기 밖 ESC 리스너", () => {
  it("전제: 스캐너가 실제로 keydown 리스너를 본다(공허 진리 가드)", () => {
    // 대조군 — ESC 를 다루지 않는 keydown 리스너(Ctrl+Z·화살표)는 여전히 존재한다.
    // 그것들이 0이면 스캐너가 아무것도 못 보고 있다는 뜻이다.
    let total = 0;
    for (const f of sourceFiles()) {
      total += [...executable(f).matchAll(/(?:window|document)\.addEventListener\(\s*"keydown"/g)].length;
    }
    // R2 실측 4건 = 조정기 1 + ESC 아닌 리스너 3(AuctionMonitorPanel·CADEditor 의 Ctrl+Z,
    // AuctionWorkspace 라이트박스 화살표). 이 수가 0 이면 스캐너가 눈이 먼 것이다.
    expect(total, "keydown 리스너를 하나도 못 찾았다 — 스캐너가 죽었다").toBeGreaterThanOrEqual(4);
  });

  it("★ESC 를 다루는 문서/윈도우 리스너는 조정기 하나뿐이다", () => {
    const hits = findGlobalEscListeners().filter((h) => !EXEMPT_LISTENERS[h.split(":")[0]]);
    expect(
      hits,
      "조정기 밖에서 ESC 를 직접 받는 리스너가 있다 — 같은 keydown 에 여러 표면이 함께 닫힌다.\n" +
        "useDismissible 로 이관하거나, 이관이 위험하면 EXEMPT_LISTENERS 에 **사유와 함께** 넣어라.\n" +
        hits.join("\n"),
    ).toEqual([]);
  });

  it("면제 리스너 목록의 항목은 실재해야 한다", () => {
    const files = new Set(findGlobalEscListeners().map((h) => h.split(":")[0]));
    for (const [f, reason] of Object.entries(EXEMPT_LISTENERS)) {
      expect(files.has(f), `면제에 적힌 ${f} 에 더는 ESC 리스너가 없다 — 면제를 지워라`).toBe(true);
      expect(reason.length).toBeGreaterThan(10);
    }
  });
});

/* ────────────────────────────── 런타임 표 ────────────────────────────── */

type RuntimeCase = {
  /** 파생 수집 결과와 대조할 소스 경로. */
  file: string;
  label: string;
  /** 기대하는 등록 칸 — 칸 바꿔치기 변이를 여기서 죽인다. */
  z: number;
  open: (close: () => void) => ReactElement;
  /** 열림 인자가 있는 표면만 — 닫힌 상태에서 등록이 없어야 한다. */
  closed?: () => ReactElement;
};

const noop = () => {};
const MEMBER_TABS = visibleTabs(["dashboard", "units", "customers"]);

const RUNTIME_CASES: RuntimeCase[] = [
  {
    file: "components/desk/ConsentModal.tsx",
    label: "개인정보 동의",
    z: DISMISS_Z.appModal,
    open: (close) => <ConsentModal onConfirm={noop} onCancel={close} />,
  },
  {
    file: "components/common/ConfirmDeleteModal.tsx",
    label: "삭제 확인",
    z: DISMISS_Z.nestedOverModal,
    open: (close) => <ConfirmDeleteModal open name="대상" onConfirm={noop} onCancel={close} />,
    closed: () => <ConfirmDeleteModal open={false} name="대상" onConfirm={noop} onCancel={noop} />,
  },
  {
    file: "components/sales-app/FieldNav.tsx",
    label: "현장앱 전체메뉴 시트",
    z: DISMISS_Z.navSheet,
    open: (close) => <FieldMenuSheet open tabs={MEMBER_TABS} activeTab="home" onNavigate={noop} onClose={close} />,
    closed: () => <FieldMenuSheet open={false} tabs={MEMBER_TABS} activeTab="home" onNavigate={noop} onClose={noop} />,
  },
  {
    file: "components/sales-app/SiteEnterModal.tsx",
    label: "현장 진입",
    z: DISMISS_Z.appModal,
    open: (close) => <SiteEnterModal locale="ko" siteId="s1" siteName="현장" open onClose={close} onEntered={noop} />,
    closed: () => (
      <SiteEnterModal locale="ko" siteId="s1" siteName="현장" open={false} onClose={noop} onEntered={noop} />
    ),
  },
  {
    file: "components/sales-app/SitePasswordModal.tsx",
    label: "현장 비밀번호",
    z: DISMISS_Z.appModal,
    open: (close) => <SitePasswordModal siteId="s1" open onClose={close} onDone={noop} />,
    closed: () => <SitePasswordModal siteId="s1" open={false} onClose={noop} onDone={noop} />,
  },
  {
    file: "components/collaboration/DocumentViewerModal.tsx",
    label: "문서 뷰어",
    z: DISMISS_Z.appModal,
    open: (close) => (
      <DocumentViewerModal
        doc={{ id: "d1", original_filename: "a.txt", file_url: "/x", content_type: "text/plain" } as never}
        onClose={close}
      />
    ),
    closed: () => <DocumentViewerModal doc={null} onClose={noop} />,
  },
  {
    file: "components/sales/CustomerCardDrawer.tsx",
    label: "고객 카드 드로어",
    z: DISMISS_Z.appModal,
    open: (close) => <CustomerCardDrawer siteCode="c1" customerId="u1" customerName="홍길동" onClose={close} />,
  },
  {
    file: "components/g2b/G2BBidDetailModal.tsx",
    label: "G2B 입찰 상세",
    z: DISMISS_Z.appModal,
    open: (close) => (
      <G2BBidDetailModal
        seed={{ id: "b1", bid_notice_nm: "공고", bid_notice_no: "1", bid_type: "일반" } as never}
        onClose={close}
        onAnalyze={noop}
      />
    ),
  },
  {
    file: "components/orchestration/InputResolveModal.tsx",
    label: "입력 자동해소",
    z: DISMISS_Z.appModal,
    open: (close) => (
      <InputResolveModal
        nodeId="design"
        resolution={{ ready: [], missing: [], autoCandidates: [] }}
        onClose={close}
        onRun={noop}
        onAutoRunUpstream={noop}
        onManualSubmit={noop}
      />
    ),
  },
];

/**
 * 런타임 표가 아직 덮지 못한 표면 — **사유를 적는다**(부채를 초록 안에 보이게).
 * 소스 파생 락은 이 파일들도 그대로 덮는다. 여기 없는 것은 "런타임까지" 태운다는 뜻이다.
 */
const RUNTIME_UNCOVERED: Record<string, string> = {
  "components/auction/AuctionWorkspace.tsx":
    "상세 모달·라이트박스는 파일 안의 비-export 컴포넌트(DetailModal)라 단독 렌더가 불가하다. " +
    "워크스페이스 전체를 띄우려면 목록 조회·지도까지 목이 필요해 이 계약의 범위를 넘는다.",
  "components/sales/OrgTree.tsx":
    "마운트 즉시 /org/tree·/org/context 를 조회하고 그 응답으로 트리를 그려야 시트를 열 수 있다. " +
    "시트를 여는 경로까지 재현하려면 조직 픽스처가 필요해 별도 rung 으로 미룬다.",
};

describe("모달 ESC 해제 계약 — 런타임 표", () => {
  afterEach(() => {
    expect(__dismissibleSnapshot().count, "등록이 새고 있다 — 언마운트 정리가 빠졌다").toBe(0);
  });

  it("전제: 런타임 표가 모달 표면의 대부분을 덮는다(부채는 사유와 함께)", () => {
    const surfaceFiles = collectSurfaces().map((s) => s.file);
    const covered = new Set(RUNTIME_CASES.map((c) => c.file));
    const missing = surfaceFiles.filter((f) => !covered.has(f) && !RUNTIME_UNCOVERED[f]);
    expect(missing, "런타임으로 안 태우는 표면이 사유 없이 남았다\n" + missing.join("\n")).toEqual([]);
    expect(RUNTIME_CASES.length, "표가 비었다 — 이 describe 가 공허하다").toBeGreaterThanOrEqual(9);
    // 죽은 부채 방지 — 사유에 적힌 파일이 더는 표면이 아니면 지워야 한다.
    for (const [f, reason] of Object.entries(RUNTIME_UNCOVERED)) {
      expect(surfaceFiles.includes(f), `${f} 는 더는 모달 표면이 아니다 — RUNTIME_UNCOVERED 에서 지워라`).toBe(true);
      expect(reason.length).toBeGreaterThan(20);
    }
  });

  describe.each(RUNTIME_CASES)("$label", (c) => {
    it("열리면 **기대한 칸으로** 등록된다", () => {
      const view = render(c.open(noop));
      const snap = __dismissibleSnapshot();
      expect(snap.count, `${c.file}: 등록되지 않았다`).toBe(1);
      expect(snap.zs[0], `${c.file}: 다른 칸으로 등록됐다 — 겹칠 때 닫히는 순서가 뒤집힌다`).toBe(c.z);
      view.unmount();
    });

    it("ESC 로 닫힌다", () => {
      const close = vi.fn();
      const view = render(c.open(close));
      fireEvent.keyDown(window, { key: "Escape" });
      expect(close, `${c.file}: ESC 를 눌러도 닫기 콜백이 불리지 않았다`).toHaveBeenCalledTimes(1);
      view.unmount();
    });

    it("ESC 가 아닌 키에는 반응하지 않는다(판별력 대조군)", () => {
      const close = vi.fn();
      const view = render(c.open(close));
      fireEvent.keyDown(window, { key: "Enter" });
      expect(close).not.toHaveBeenCalled();
      view.unmount();
    });

    if (c.closed) {
      it("닫혀 있으면 등록하지 않는다(음성대조)", () => {
        const view = render(c.closed!());
        expect(__dismissibleSnapshot().count, `${c.file}: 닫힌 표면이 ESC 를 삼킨다`).toBe(0);
        view.unmount();
      });
    }
  });
});

describe("모달 ESC 해제 계약 — 겹친 표면", () => {
  afterEach(() => {
    expect(__dismissibleSnapshot().count, "등록이 새고 있다").toBe(0);
  });

  it("전제: 겹침 픽스처의 두 칸이 **실제로 다른 값**이다", () => {
    // ★같은 값이면 배선을 끊어도 결과가 같아 잠금이 되지 않는다.
    expect(DISMISS_Z.nestedOverModal).toBeGreaterThan(DISMISS_Z.appModal);
    expect(DISMISS_Z.appModal).toBeGreaterThan(DISMISS_Z.navSheet);
    expect(DISMISS_Z.navSheet).toBeGreaterThan(DISMISS_Z.fullscreenExit);
  });

  it("IME 조합 중 ESC 는 무시한다(입력 유실 방지)", () => {
    // ★한계 — jsdom 은 IME 를 흉내 내지 못한다. 여기서 태우는 것은 **플래그 분기**이지
    //   "실제 한글 조합 중 브라우저가 이 플래그를 세운다"는 사실이 아니다(그건 미검증).
    const close = vi.fn();
    const view = render(<ConsentModal onConfirm={noop} onCancel={close} />);
    fireEvent.keyDown(window, { key: "Escape", isComposing: true });
    expect(close, "조합 중 ESC 에 모달이 닫혔다 — 치던 입력이 함께 날아간다").not.toHaveBeenCalled();
    // 양성대조 — 조합이 끝난 ESC 는 정상적으로 닫는다(분기가 전부를 삼키지 않는다).
    fireEvent.keyDown(window, { key: "Escape" });
    expect(close).toHaveBeenCalledTimes(1);
    view.unmount();
  });

  it("★ESC 1회 = **위에 겹친 확인창만** 닫힌다 — 아래 모달은 살아남는다", () => {
    const closeBase = vi.fn();
    const closeTop = vi.fn();
    const view = render(
      <>
        <ConsentModal onConfirm={noop} onCancel={closeBase} />
        <ConfirmDeleteModal open name="대상" onConfirm={noop} onCancel={closeTop} />
      </>,
    );
    expect(__dismissibleSnapshot().count, "두 모달이 조정기에 등록되지 않았다").toBe(2);

    fireEvent.keyDown(window, { key: "Escape" });
    expect(closeTop, "위에 겹친 확인창이 안 닫혔다").toHaveBeenCalledTimes(1);
    expect(closeBase, "★아래 모달까지 같이 닫혔다 — 종전 결함 그대로다").not.toHaveBeenCalled();
    view.unmount();
  });

  it("★★이관 회귀: 전체메뉴 시트 위에 모달이 열리면 **모달이 먼저** 닫힌다", () => {
    // 종전 FieldNav 는 자기 window 리스너로 ESC 를 받아, 같은 keydown 에 시트와 모달이 함께 닫혔다.
    const closeSheet = vi.fn();
    const closeModal = vi.fn();
    const view = render(
      <>
        <FieldMenuSheet open tabs={MEMBER_TABS} activeTab="home" onNavigate={noop} onClose={closeSheet} />
        <ConsentModal onConfirm={noop} onCancel={closeModal} />
      </>,
    );
    expect(__dismissibleSnapshot().zs).toEqual([DISMISS_Z.navSheet, DISMISS_Z.appModal]);

    fireEvent.keyDown(window, { key: "Escape" });
    expect(closeModal, "모달이 안 닫혔다").toHaveBeenCalledTimes(1);
    expect(closeSheet, "★시트까지 같이 닫혔다 — 이관 전 결함 그대로다").not.toHaveBeenCalled();
    view.unmount();
  });
});

describe("★HIGH-1 회귀: 데스크톱 네비 플라이아웃", () => {
  afterEach(() => {
    expect(__dismissibleSnapshot().count, "등록이 새고 있다").toBe(0);
  });

  /** 포커스만으로 플라이아웃이 열린다(`onFocus={() => openSection(...)}`) — 그게 이 결함의 입구였다. */
  function openFlyout() {
    const nav = screen.getByRole("navigation", { name: "Workspace navigation" });
    const button = within(nav).getAllByRole("button", { expanded: false })[0];
    expect(button, "aria-expanded 를 가진 섹션 버튼을 찾지 못했다").toBeTruthy();
    fireEvent.focus(button.parentElement!);
    expect(within(nav).queryAllByRole("menu").length, "플라이아웃이 안 열렸다 — 전제가 무너졌다").toBe(1);
    return nav;
  }

  it("★ESC 1회는 모달만 닫는다 — 플라이아웃은 살아남는다(R1 이 놓친 결함)", () => {
    // R2 재현(수정 전): ESC 1회 → 모달 닫힘 1 · 플라이아웃 닫힘 1. 사용자는 한 번 눌렀는데 둘이 사라졌다.
    // 원인 ① `document` 리스너라 조정기(window)보다 **먼저** 발화 ② 열림 검사 없음.
    const closeModal = vi.fn();
    const view = render(
      <>
        <WorkspaceNavBar sections={buildPrimaryNav("ko")} />
        <ConsentModal onConfirm={noop} onCancel={closeModal} />
      </>,
    );
    const nav = openFlyout();
    expect(__dismissibleSnapshot().zs).toEqual([DISMISS_Z.navSheet, DISMISS_Z.appModal]);

    fireEvent.keyDown(document, { key: "Escape" });
    expect(closeModal, "모달이 안 닫혔다").toHaveBeenCalledTimes(1);
    expect(
      within(nav).queryAllByRole("menu").length,
      "★플라이아웃까지 같이 닫혔다 — 조정기 밖 리스너가 되살아났다",
    ).toBe(1);

    view.unmount();
  });

  it("다음 ESC 가 플라이아웃을 닫는다(단계적 해제)", () => {
    const view = render(<WorkspaceNavBar sections={buildPrimaryNav("ko")} />);
    const nav = openFlyout();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(within(nav).queryAllByRole("menu").length, "혼자 열려 있을 때는 ESC 로 닫혀야 한다").toBe(0);
    view.unmount();
  });

  it("닫힌 플라이아웃은 등록하지 않는다(음성대조 — 열림 검사 부재가 이 결함의 절반이었다)", () => {
    const view = render(<WorkspaceNavBar sections={buildPrimaryNav("ko")} />);
    expect(__dismissibleSnapshot().count, "안 열린 네비가 ESC 를 삼킨다").toBe(0);
    view.unmount();
  });
});

describe("모달 접근성 — 다음 단계(미구현 부채)", () => {
  // ★부채는 커밋 메시지가 아니라 여기 남긴다 — 초록 안에 보여야 다음 사람이 안다.
  //   착수 시점 실측: 포커스 트랩·초기 포커스·포커스 복귀는 13개 표면 **전부 0/13**.
  //   ★R2 에서 확인된 결과이기도 하다 — OrgTree 의 두 시트가 키보드로 함께 열릴 수 있는 이유가
  //     바로 트랩 부재다(지금은 상호배타로 막아 뒀지만 근본 처방은 트랩이다).
  it.todo("모든 모달이 열릴 때 내부 첫 요소로 포커스를 옮긴다(초기 포커스)");
  it.todo("모든 모달이 Tab/Shift+Tab 을 모달 안에 가둔다(포커스 트랩)");
  it.todo("모달이 닫히면 열기 전 눌렀던 요소로 포커스가 돌아간다(포커스 복귀)");
});
