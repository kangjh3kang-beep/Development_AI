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
import { DeskAppraisalModal } from "@/components/operations/DeskAppraisalModal";
import { LandShareModal } from "@/components/operations/LandShareModal";
import { visibleTabs } from "@/components/sales-app/roleConfig";
import { buildPrimaryNav } from "@/components/layout/nav-config";
import { WorkspaceNavBar } from "@/components/layout/WorkspaceNavBar";
import { DISMISS_Z, __dismissibleSnapshot } from "@/lib/satong-dismiss";
import { __stripCommentsForScan } from "@/lib/source-invariant";

// ── 저장소 전수 스캔 테스트의 시간 상한 ──────────────────────────────────────
//  이 파일은 `it` 안에서 저장소의 **모든 소스 파일(약 941개)** 을 다시 읽는다. 그래서 실행
//  시간이 **검증 대상의 성질이 아니라 그때의 CPU 경합**에 좌우된다 — 전체 스위트를 돌리면
//  워커가 붙는 만큼 느려져 기본 10초를 넘고, 단독 실행은 항상 통과한다(실측: 실패는 전부
//  `Test timed out in 10000ms` 이고 비타임아웃 실패는 0건). CI 는 더 느릴 수 있다.
//  ★10초는 **정확성 경계가 아니라 벽시계**다. 늘려도 잡아내는 결함은 그대로다.
//  ★근본 처방은 941파일 읽기를 모듈 스코프로 호이스팅하는 것이고, 별건으로 남겼다.
vi.setConfig({ testTimeout: 60_000 });


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
const EXEMPT: Record<string, string> = {
  // ★2026-08-23 — ARIA 를 붙이자 이 표면이 처음으로 ESC 계약에 **수집됐다**(종전엔 선언이
  //   없어 계약 밖이었다). 그런데 ESC 를 닫기로 연결하면 안 된다:
  //   이 위저드는 `onClose` 가 없고 "건너뛰기"가 곧 `handleComplete`(다시 안 뜸)라,
  //   **실수로 ESC 를 한 번 누른 사용자가 온보딩을 영영 못 보게** 된다.
  //   접근성 문제가 아니라 **제품 결정**이므로 여기서 정하지 않고 사유와 함께 면제한다.
  "components/onboarding/OnboardingWizard.tsx":
    "ESC 를 닫기로 연결하면 '건너뛰기=완료'와 같아져 실수 한 번에 온보딩을 영영 못 본다 — 되돌릴 수 있는 닫기 경로를 먼저 정해야 하는 제품 결정",
};

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
const KEYDOWN_LISTENER = /(?:window|document)\.addEventListener\(\s*"keydown"\s*,\s*/g;
/** 핸들러 본문을 얼마나 읽을지 — 이 저장소의 keydown 핸들러는 전부 이보다 짧다(실측 최대 ~350자). */
const HANDLER_WINDOW = 800;

/**
 * 한 소스에서 "ESC 를 다루는 전역 keydown 리스너"를 찾는다. **순수 함수**라 합성 소스로
 * 스캐너 자신을 대조할 수 있다(아래 양성·음성 대조군).
 *
 * ★두 등록 형태를 모두 읽는다:
 *   ① `const onKey = …; window.addEventListener("keydown", onKey)` — 이름을 거슬러 선언을 찾는다.
 *   ② `window.addEventListener("keydown", (e) => { … })` — 인라인. **초판은 이 형태를 아예 못 봤다**
 *      (정규식이 식별자만 받았다) — 즉 인라인으로 쓰면 가드를 그냥 지나간다. 내가 방금 만든
 *      가드의 구멍이라 스스로 막는다.
 * ★이름을 썼는데 선언을 못 찾으면 **조용히 넘기지 않고 실패**시킨다(스캐너가 눈먼 채 초록이 되는 것 방지).
 */
export function escListenersIn(src: string, label: string): string[] {
  const hits: string[] = [];
  for (const m of src.matchAll(KEYDOWN_LISTENER)) {
    const after = src.slice(m.index + m[0].length, m.index + m[0].length + HANDLER_WINDOW);
    const named = /^(\w+)\s*[),]/.exec(after);
    let body: string;
    let name: string;
    if (named) {
      name = named[1];
      const declIdx = src.lastIndexOf(`const ${name} =`, m.index);
      expect(declIdx, `${label}: keydown 핸들러 ${name} 의 선언을 못 찾았다 — 스캐너를 고쳐라`).toBeGreaterThan(-1);
      body = src.slice(declIdx, m.index);
    } else {
      name = "(인라인)";
      body = after;
    }
    if (/["']Escape["']/.test(body)) hits.push(`${label}: ${name}`);
  }
  return hits.sort();
}

function findGlobalEscListeners(): string[] {
  const hits: string[] = [];
  for (const f of sourceFiles()) {
    if (rel(f) === COORDINATOR) continue; // 조정기 자신 — 이 하나만 ESC 를 받는다
    hits.push(...escListenersIn(executable(f), rel(f)));
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

  it("전제: 스캐너가 두 등록 형태를 모두 본다(합성 소스 대조군)", () => {
    // ★양성 — 이름 붙은 핸들러
    expect(
      escListenersIn(`const onKey = (e) => { if (e.key === "Escape") close(); };\nwindow.addEventListener("keydown", onKey);`, "f"),
    ).toEqual(["f: onKey"]);
    // ★양성 — **인라인** 핸들러(초판 스캐너가 못 보던 형태)
    expect(
      escListenersIn(`document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });`, "f"),
    ).toEqual(["f: (인라인)"]);
    // ★음성 — ESC 를 다루지 않는 전역 리스너(Ctrl+Z)는 위반이 아니다
    expect(
      escListenersIn(`const onKey = (e) => { if (e.ctrlKey && e.key === "z") undo(); };\nwindow.addEventListener("keydown", onKey);`, "f"),
    ).toEqual([]);
    // ★음성(위양성 방지) — **요소 레벨** onKeyDown 의 Escape 는 대상이 아니다.
    //   포커스가 그 요소에 있을 때만 발화하므로 문서 전역 리스너끼리의 충돌을 만들지 않는다.
    expect(escListenersIn(`<input onKeyDown={(e) => { if (e.key === "Escape") cancel(); }} />`, "f")).toEqual([]);
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
  {
    file: "components/operations/DeskAppraisalModal.tsx",
    label: "탁상감정",
    z: DISMISS_Z.appModal,
    open: (close) => (
      <DeskAppraisalModal jibun="테스트동 1-1" areaSqm={500} onClose={close} onApply={noop} />
    ),
  },
  {
    file: "components/operations/LandShareModal.tsx",
    label: "대지지분",
    z: DISMISS_Z.appModal,
    open: (close) => <LandShareModal jibun="테스트동 1-1" pnu={null} onClose={close} onApplyArea={noop} />,
  },
];

/**
 * 런타임 표가 아직 덮지 못한 표면 — **사유를 적는다**(부채를 초록 안에 보이게).
 * 소스 파생 락은 이 파일들도 그대로 덮는다. 여기 없는 것은 "런타임까지" 태운다는 뜻이다.
 */
const RUNTIME_UNCOVERED: Record<string, string> = {
  "components/sales/OrgTree.tsx":
    "이 표 대신 전용 스펙(`components/sales/__tests__/OrgTree.focusTrap.test.tsx`)이 렌더 경로를 " +
    "직접 만들어 트랩을 태운다 — 조직 목이 필요해 공용 표에 넣기보다 그쪽이 정확하다.",
  "components/onboarding/OnboardingWizard.tsx":
    "자체 `visible` 상태를 localStorage 로 결정해 스스로 연다 — 부모가 주는 열림 인자가 없어 " +
    "밖에서 '열린 상태'를 만들 수 없다. 저장소 목을 세우면 가능하니 별도 rung 으로 남긴다.",
  "components/auction/AuctionWorkspace.tsx":
    "이 표 대신 전용 스펙(`components/auction/__tests__/AuctionWorkspace.focusTrap.test.tsx`)이 " +
    "렌더 경로를 직접 만들어 트랩을 태운다 — 트랩이 둘 겹치는 표면이라 공용 표보다 그쪽이 정확하다. " +
    "★종전 사유(『목록 조회·지도 목이 필요』)는 실측으로 기각됐다: 필요한 목은 상세 응답 하나였다.",
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

describe("모달 접근성 — 포커스 생명주기(2026-08-22 부분 상환)", () => {
  // 종전엔 `it.todo` 3건(초기 포커스·트랩·복귀)이 **뭉뚱그려** 있었다.
  // 착수 시점 실측은 **13표면 전부 0/13** 이었고, 미룬 이유는 *"폼 표면 회귀 위험"* 이었다.
  //
  // ★상환하면서 **근본 결함 하나를 찾았다**: `trapFocus`(hooks/useAccessibility)는 **이미
  //   있었는데 소비처가 0** 이었고, 그 안의 가시성 판정이 `offsetParent !== null` 이었다.
  //   **`position: fixed` 요소는 사양상 offsetParent 가 null** 이다(MDN) — 모달은 대부분
  //   fixed 이므로 이 함수는 **정확히 자기 사용처에서 0개**를 돌려줬다. 그러면 trapFocus 는
  //   `preventDefault()` 만 하고 끝나 **Tab 이 순환이 아니라 죽는다.** jsdom 만의 문제가 아니다.
  //   → 판정을 `disabled`·`hidden`·`aria-hidden` 으로 바꿨다(fixed 무관·관측 가능).
  //
  // ★그리고 훅이 **저자의 `autoFocus` 를 빼앗지 않게** 했다 — 이미 모달 안에 포커스가 있으면
  //   건드리지 않는다. (ConfirmDeleteModal 은 확인 입력창이 autoFocus 다. 첫 포커스 요소인
  //   "복사" 버튼으로 옮기는 것은 개선이 아니라 **회귀**다.)
  //
  // ★부채를 **뭉뚱그리지 않는다** — 아래 맵이 표면별 사유를 들고 있고, 래칫이 그 맵을 감시한다.

  /** 포커스 생명주기가 **배선된** 표면(소스에서 훅 호출로 판정). */
  const FOCUS_WIRED = [
    "components/common/ConfirmDeleteModal.tsx",
    // ── 2026-08-22 R1 상환 — 미룬 **사유를 먼저 실측**해 기각한 3표면 ──
    //   세 건 모두 미룬 근거가 *가설*이었고, 재보니 사실이 아니었다.
    "components/sales-app/SiteEnterModal.tsx",
    "components/sales-app/SitePasswordModal.tsx",
    "components/collaboration/DocumentViewerModal.tsx",
    // ── 2026-08-23 R2 — **계약 비대칭**이 진짜 원인이었다 ──
    //   ESC 계약은 `useDismissible`(open prop) / `useDismissibleWhileMounted`(마운트=열림)
    //   **두 변종**인데 포커스 계약은 앞의 것만 있었다. 아래 셋 중 둘이 마운트=열림이라
    //   넣을 `open` 인자가 없었던 것이지, 표면별 사정이 달랐던 게 아니다.
    "components/desk/ConsentModal.tsx",
    "components/g2b/G2BBidDetailModal.tsx",
    "components/orchestration/InputResolveModal.tsx",
    // ── 2026-08-23 R3 — 드로어 2표면. **미룬 사유 둘 다 재보니 해소됐다** ──
    //   ①"딤이 포커스 가능해 본체 트랩이면 닫을 수단이 없다" → **본체 안에 닫기 버튼이 있다**
    //   ②"라우팅 언마운트로 복귀 대상이 사라진다" → 훅이 `document.contains` 로 이미 막는다
    "components/sales/CustomerCardDrawer.tsx",
    "components/sales-app/FieldNav.tsx",
    // ── 2026-08-23 R4 — **ARIA 선언 누락으로 계약을 통째로 빠져나가던 표면 3종** ──
    //   화면 전체를 덮고 모달 칸 z 를 쓰면서 `aria-modal` 만 없어, ESC·포커스 계약이
    //   수집조차 못 했다. layer-ladder 의 **z 기반 수집 계약**이 이들을 처음 드러냈다.
    "components/operations/DeskAppraisalModal.tsx",
    "components/operations/LandShareModal.tsx",
    "components/onboarding/OnboardingWizard.tsx",
    // ── 2026-08-23 R5 — **렌더 경로를 먼저 만든 뒤** 배선했다 ──
    //   `OrgTree` 는 마운트 즉시 /org/tree·/org/context 를 조회해야 시트에 닿는다.
    //   목을 세워 여는 경로를 만들고(`OrgTree.focusTrap.test.tsx`) 그 위에 트랩을 잠갔다.
    //   순서를 뒤집었으면 **런타임으로 못 태우는 배선**이 됐을 것이다.
    "components/sales/OrgTree.tsx",
    // ── 2026-08-23 R6 — **부채 사유를 재보니 가리킨 대상이 틀렸다** ──
    //   *"단독 렌더에 목록 조회·지도 목이 필요"* 라 적혀 있었으나, `DetailModal` 이 받는 것은
    //   `item`·`locale`·`onClose` 뿐이다. 실제로 필요한 목은 **상세 응답 하나**였고
    //   (사진이 `/auction/detail` 에서 온다) 막고 있던 것은 **`export` 하나**였다.
    //   ★이 표면은 트랩이 **둘 겹친다**(라이트박스가 상세 모달 안에 렌더된다) —
    //     그래서 훅에 **중첩 양보** 규칙을 넣고, 전용 스펙이 실제 Tab 으로 태운다.
    "components/auction/AuctionWorkspace.tsx",
  ] as const;

  /**
   * 아직 배선하지 않은 표면 — **1건 남았다**(`OrgTree` 는 별건 PR 이 상환 중이다).
   *
   * ★새 모달 표면이 생기면 아래 "덮이지 않은 표면 0" 계약이 먼저 실패하고, 그때 배선하거나
   *   사유와 함께 여기 등재하게 된다.
   */
  const FOCUS_UNWIRED: Record<string, string> = {
    // ★2026-08-24 — **비었다.** 마지막 두 건이 각각 다른 PR 로 상환되며 만난 자리다.
    //   `AuctionWorkspace`(#780) · `OrgTree`(이 PR) 둘 다 **적힌 사유가 실제보다 컸다** —
    //   전자는 *"목록 조회·지도 목이 필요"* 였으나 실제로는 상세 응답 하나였고,
    //   후자는 조직 목 하나로 시트에 닿았다. 사유를 물려받아 믿으면 부채가 실제보다
    //   비싸 보이고, **비싸 보이는 부채는 영원히 미뤄진다** — 착수 전에 재라.
    //
    //   ★맵이 비어도 공허한 초록이 아니다: 아래 "덮이지 않은 표면 0" 계약이 **양성 방향**으로
    //   감시하고, `surfaces.length > 8` 가드가 스캐너 사망을 함께 본다.
  };

  /**
   * 마운트 자체가 열림인 표면 — `open` 인자가 없어 `useModalFocusWhileMounted` 를 쓴다.
   * ★이 목록이 **닫힘 픽스처 면제**의 근거다(닫힌 상태가 원리적으로 존재하지 않는다).
   */
  /**
   * 닫힘 픽스처를 만들 수 **없는** 표면 — 사유를 적는다(빈 사유는 아래 래칫이 막는다).
   *
   * ★"음성대조가 없다"를 조용히 넘기지 않기 위한 맵이다. 게으름과 **원리적 불가**를
   *   구분해서 적어야 다음 사람이 재시도할지 말지 안다.
   */
  const CLOSED_FIXTURE_EXEMPT: Record<string, string> = {
    "components/desk/ConsentModal.tsx":
      "마운트 자체가 열림 — 부모가 열 때만 렌더하므로 닫힌 상태가 존재하지 않는다",
    "components/g2b/G2BBidDetailModal.tsx":
      "마운트 자체가 열림 — 부모가 상세를 고른 순간에만 렌더하므로 닫힌 상태가 존재하지 않는다",
    "components/sales/CustomerCardDrawer.tsx":
      "마운트 자체가 열림 — 부모가 고객을 고른 순간에만 렌더하므로 닫힌 상태가 존재하지 않는다",
    "components/operations/DeskAppraisalModal.tsx":
      "마운트 자체가 열림 — 부모가 감정 버튼을 누른 순간에만 렌더하므로 닫힌 상태가 존재하지 않는다",
    "components/operations/LandShareModal.tsx":
      "마운트 자체가 열림 — 부모가 대지지분 조회를 연 순간에만 렌더하므로 닫힌 상태가 존재하지 않는다",
    "components/onboarding/OnboardingWizard.tsx":
      "자체 `visible` 상태로 스스로 열고 닫는다 — 부모가 주는 열림 인자가 없어 닫힌 픽스처를 밖에서 만들 수 없다",
    "components/orchestration/InputResolveModal.tsx":
      "★타입이 막는다 — `nodeId` 가 `NodeId` 유니온이라 **존재하지 않는 노드를 줄 수 없고**, 유효한 id 는 항상 노드를 찾아 열린다. 억지 캐스팅으로 타입이 막는 상태를 만들지 않는다(그건 실사용에 없는 경로다)",
  };

  const FOCUS_WIRED_WHILE_MOUNTED: readonly string[] = [
    // ★실측으로 확정한 목록이다. `ConfirmDeleteModal` 은 `useDismissible(z, open, …)` 을 쓰는
    //   **open prop 방식**이라 여기 들어가지 않는다(처음에 넣었다가 이 계약이 잡아냈다).
    "components/desk/ConsentModal.tsx",
    "components/g2b/G2BBidDetailModal.tsx",
    "components/sales/CustomerCardDrawer.tsx",
    "components/operations/DeskAppraisalModal.tsx",
    "components/operations/LandShareModal.tsx",
    "components/onboarding/OnboardingWizard.tsx",
    // 상세 모달은 부모가 `selected` 일 때만 렌더한다 — 넣을 `open` 인자가 없다.
    // (같은 파일의 라이트박스는 `zoomOpen` 이 있어 인자를 받는 변종을 쓴다.)
    "components/auction/AuctionWorkspace.tsx",
  ];

  it("★배선된 표면은 훅을 **호출**한다(임포트만 남는 회귀 방지)", () => {
    for (const f of FOCUS_WIRED) {
      const code = executable(join(WEB_ROOT, f));
      // ★두 변종 중 하나를 **호출**해야 한다. `useModalFocus(` 만 보면
      //   `useModalFocusWhileMounted(` 를 쓰는 표면이 미배선으로 오판된다(실측).
      const called =
        code.includes("useModalFocus(") || code.includes("useModalFocusWhileMounted(");
      expect(called, `${f} 가 포커스 훅을 호출하지 않는다`).toBe(true);
    }
  });

  it("★`WhileMounted` 표면은 실제로 그 변종을 쓴다 — 상수 리터럴 `true` 우회 금지", () => {
    for (const f of FOCUS_WIRED_WHILE_MOUNTED) {
      const code = executable(join(WEB_ROOT, f));
      expect(code, `${f} 가 WhileMounted 변종을 쓰지 않는다`).toContain(
        "useModalFocusWhileMounted(",
      );
      // 열림 인자에 상수를 박는 우회(= 열림 검사 누락과 구분 불가)를 막는다.
      expect(code, `${f} 가 open 인자에 상수 리터럴을 박았다`).not.toContain(
        "useModalFocus(bodyRef, true)",
      );
    }
    // ★양성 대조 — 목록이 비면 위 루프가 통째로 사라진다.
    expect(FOCUS_WIRED_WHILE_MOUNTED.length).toBeGreaterThanOrEqual(2);
  });

  it("★미배선 사유가 비어 있지 않다 — 부채를 뭉뚱그리지 않는다", () => {
    // 맵이 비어 있는 것은 **정상**이다(전부 상환됨). 비어 있지 않다면 사유가 있어야 한다.
    for (const [f, reason] of Object.entries(FOCUS_UNWIRED)) {
      expect(reason.length, `${f} 의 사유가 너무 짧다`).toBeGreaterThan(15);
    }
  });

  it("★★모든 모달 표면이 포커스 배선을 갖는다 — 새 표면이 조용히 새지 않는다", () => {
    // 종전 래칫은 *"미배선 맵이 비면 안 된다"* 였다(부채가 남아 있던 시절의 계약).
    // 이제 전부 상환됐으므로 계약을 뒤집는다: **덮이지 않은 표면이 0** 이어야 한다.
    // 새 모달이 추가되면 여기서 먼저 걸리고, 배선하거나 사유와 함께 FOCUS_UNWIRED 에 등재한다.
    const surfaces = collectSurfaces().map((s) => s.file);
    expect(surfaces.length, "표면을 못 모았다 — 스캐너가 죽었다(공허 진리 방지)").toBeGreaterThan(8);

    const wired = new Set<string>(FOCUS_WIRED);
    // ★`RUNTIME_UNCOVERED` 를 여기에 쓰면 안 된다 — **다른 축**이다.
    //   그것은 *"단독 렌더가 불가해 런타임 표에 못 넣는다"* 는 **테스트 방법**의 면제이지,
    //   *"포커스를 배선하지 않아도 된다"* 는 뜻이 아니다. 처음엔 그걸 섞어 써서
    //   `AuctionWorkspace`(aria-modal 표면 2개 · 포커스 배선 0)를 통째로 놓쳤다.
    const uncovered = [...new Set(surfaces)].filter(
      (f) => !wired.has(f) && !FOCUS_UNWIRED[f],
    );
    expect(
      uncovered,
      "포커스 배선도 사유도 없는 모달 표면이 있다 — 배선하거나 FOCUS_UNWIRED 에 사유와 함께 등재하라",
    ).toEqual([]);
  });

  it("★죽은 부채를 남기지 않는다 — 맵의 파일이 실제로 모달 표면이어야 한다", () => {
    const surfaces = new Set(collectSurfaces().map((s) => s.file));
    for (const f of Object.keys(FOCUS_UNWIRED)) {
      expect(surfaces.has(f), `${f} 는 더는 모달 표면이 아니다 — FOCUS_UNWIRED 에서 지워라`).toBe(true);
    }
    // ★배선된 표면이 미배선 맵에 남아 있으면 안 된다(양쪽에 있으면 래칫이 거짓말한다).
    for (const f of FOCUS_WIRED) {
      expect(FOCUS_UNWIRED[f], `${f} 는 배선됐는데 미배선 맵에 남아 있다`).toBeUndefined();
    }
  });

  // ── ★런타임 잠금 ──────────────────────────────────────────────────────────
  //  위의 `useModalFocus(` 소스 검사만으로는 **배선을 죽이는 변이가 통과**한다
  //  (ESC 계약이 R2 에서 실증한 것과 같은 구멍: 인자를 `false` 로 바꾸거나 ref 를 백드롭에
  //  달아도 호출 문자열은 그대로다). 그래서 실제로 렌더해 **포커스가 어디 있는지**를 태운다.

  const focusablesIn = (root: HTMLElement): HTMLElement[] =>
    Array.from(
      root.querySelectorAll<HTMLElement>(
        'a[href], button, textarea, input, select, [tabindex]:not([tabindex="-1"])',
      ),
    ).filter((el) => !el.hasAttribute("disabled") && el.getAttribute("aria-hidden") !== "true");

  /**
   * 훅이 **실제로 가둔 컨테이너**. 트랩 범위를 재려면 이걸 봐야 한다.
   *
   * ★`[role="dialog"]`(백드롭)로 재면 드로어에서 틀린다 — `CustomerCardDrawer`·`FieldNav` 는
   *   백드롭 안에 **포커스 가능한 딤 버튼**을 본체의 형제로 두기 때문에, 백드롭 기준
   *   focusables 에는 트랩 밖 요소가 섞인다. 다른 모달은 백드롭에 포커스 요소가 없어
   *   둘이 우연히 같았고, 그래서 이 차이가 여태 안 드러났다.
   */
  const trapEl = (): HTMLElement => {
    const el = document.body.querySelector<HTMLElement>("[data-modal-focus]");
    if (!el) throw new Error("트랩된 컨테이너가 없다 — 훅이 돌지 않았다(공허한 초록 방지)");
    return el;
  };

  const dialogEl = (): HTMLElement => {
    // ★포털 표면(DocumentViewerModal)은 render 컨테이너 밖에 그려지므로 document 에서 찾는다.
    const el = document.body.querySelector<HTMLElement>('[role="dialog"]');
    if (!el) throw new Error("role=dialog 를 못 찾았다 — 표면이 안 열렸다(공허한 초록 방지)");
    return el;
  };

  const WIRED_RUNTIME = RUNTIME_CASES.filter((c) =>
    (FOCUS_WIRED as readonly string[]).includes(c.file),
  );

  it("전제: 배선된 표면이 **전부** 런타임 표에 있다 — 없으면 아래 표가 공허하다", () => {
    // ★하한 가드가 **먼저** 와야 한다(2026-08-22 R2 추가). 종전엔 이게 없어서
    //   `FOCUS_WIRED` 를 `[]` 로 만들면 아래 `describe.each` 가 **스위트 0개**가 되고
    //   위 `toBe` 도 `0 === 0` 으로 통과해 **런타임 락 20건이 통째로 사라져도 초록**이었다.
    //   같은 파일 ESC 블록은 이미 이렇게 막고 있었는데(`RUNTIME_CASES.length >= 9`)
    //   새 블록에만 빠져 있었다 — 선언한 원칙을 자기 새 코드에 안 쓴 형태(§D.16).
    expect(
      FOCUS_WIRED.length,
      "배선 표면이 비었다 — 이 describe 가 공허하다",
    ).toBeGreaterThanOrEqual(4);

    const covered = WIRED_RUNTIME.map((c) => c.file);
    for (const f of FOCUS_WIRED) {
      // ★런타임 표에 못 넣는 표면은 **사유가 적혀 있어야** 넘어간다(조용한 면제 금지).
      if (RUNTIME_UNCOVERED[f]) {
        expect(RUNTIME_UNCOVERED[f].length, `${f} 의 런타임 면제 사유가 너무 짧다`).toBeGreaterThan(30);
        continue;
      }
      expect(covered, `${f} 가 런타임 표에 없어 소스 검사로만 잠긴다`).toContain(f);
    }
    // ★런타임 면제된 표면만큼 차이가 난다 — 그 수를 **명시적으로** 뺀다(조용한 불일치 금지).
    const runtimeExempt = FOCUS_WIRED.filter((f) => RUNTIME_UNCOVERED[f]).length;
    expect(WIRED_RUNTIME.length).toBe(FOCUS_WIRED.length - runtimeExempt);

    // ★닫힘 픽스처가 없으면 음성대조가 **소리 없이 사라진다**(아래 `if (c.closed)`).
    //   단 **마운트 자체가 열림**인 표면은 닫힌 상태가 원리적으로 없다(부모가 렌더를 안 한다)
    //   — 면제하되 **그 사실을 목록으로 못박아** 아무 표면이나 빠져나가지 못하게 한다.
    for (const c of WIRED_RUNTIME) {
      if (CLOSED_FIXTURE_EXEMPT[c.file]) continue;
      expect(c.closed, `${c.file} 에 닫힘 픽스처가 없어 음성대조가 실행되지 않는다`).toBeTypeOf(
        "function",
      );
    }
    // ★면제 목록이 실제 배선 표면과 어긋나면 다음 사람이 오독한다(죽은 면제 방지).
    for (const f of FOCUS_WIRED_WHILE_MOUNTED) {
      expect(FOCUS_WIRED as readonly string[], `${f} 는 배선 목록에 없다`).toContain(f);
    }
    for (const [f, reason] of Object.entries(CLOSED_FIXTURE_EXEMPT)) {
      expect(FOCUS_WIRED as readonly string[], `${f} 는 배선 목록에 없다`).toContain(f);
      expect(reason.length, `${f} 의 면제 사유가 너무 짧다`).toBeGreaterThan(20);
    }
  });

  it("★★트랩 대상이 백드롭이 아니라 **대화상자 본체**다 — 결과가 같아 대상을 직접 봐야 한다", () => {
    // `#750` 은 *"ref 를 백드롭에 달아도 통과하는 것을 막는다"* 고 선언했지만 **막지 못했다.**
    // 실측(2026-08-22): ref 를 백드롭으로 옮겨도 76건 전부 초록. 우리 모달은 전부
    // `백드롭 > 본체` 구조이고 백드롭의 유일한 요소 자식이 본체라 **포커스 목록이 동일**하다.
    // → 결과로 구분이 안 되면 **대상을 관측**한다(`useModalFocus` 가 다는 `data-modal-focus`).
    for (const c of WIRED_RUNTIME) {
      const view = render(c.open(noop));
      const backdrop = dialogEl();
      expect(
        backdrop.hasAttribute("data-modal-focus"),
        `${c.file}: ref 가 **백드롭**에 달렸다 — 트랩 범위가 대화상자보다 넓다`,
      ).toBe(false);
      // ★양성 짝 — "백드롭이 아니다"만으로는 훅이 아예 안 돌아도 참이 된다.
      expect(
        backdrop.querySelector("[data-modal-focus]"),
        `${c.file}: 트랩된 컨테이너가 없다 — 훅이 돌지 않았다`,
      ).not.toBeNull();
      view.unmount();
    }
  });

  describe.each(WIRED_RUNTIME)("포커스 런타임 — $label", (c) => {
    it("★열리면 포커스가 대화상자 **안**으로 들어온다", () => {
      const view = render(c.open(noop));
      const dialog = trapEl();
      expect(
        focusablesIn(dialog).length,
        `${c.file} 에 포커스 가능 요소가 0개 — 트랩 단언이 공허해진다`,
      ).toBeGreaterThan(0);
      expect(
        dialog.contains(document.activeElement),
        `${c.file} 를 열었는데 포커스가 대화상자 밖(${document.activeElement?.nodeName})에 있다`,
      ).toBe(true);
      view.unmount();
    });

    it("★마지막 요소에서 Tab 하면 첫 요소로 **돈다**(트랩)", () => {
      const view = render(c.open(noop));
      const items = focusablesIn(trapEl());
      items[items.length - 1].focus();
      fireEvent.keyDown(document, { key: "Tab" });
      expect(
        document.activeElement,
        `${c.file} 에서 Tab 이 모달 밖으로 샌다 — ref 가 백드롭에 달렸거나 훅이 죽었다`,
      ).toBe(items[0]);
      view.unmount();
    });

    it("★Shift+Tab 은 첫 요소에서 마지막으로 돈다(역방향)", () => {
      const view = render(c.open(noop));
      const items = focusablesIn(trapEl());
      items[0].focus();
      fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
      expect(document.activeElement, `${c.file} 역방향 트랩이 없다`).toBe(items[items.length - 1]);
      view.unmount();
    });

    it("★음성대조 — Tab 이 아닌 키는 포커스를 옮기지 않는다(판별력)", () => {
      const view = render(c.open(noop));
      const items = focusablesIn(trapEl());
      const probe = items[Math.min(1, items.length - 1)];
      probe.focus();
      fireEvent.keyDown(document, { key: "Enter" });
      fireEvent.keyDown(document, { key: "a" });
      expect(document.activeElement, `${c.file} 가 아무 키에나 포커스를 옮긴다`).toBe(probe);
      view.unmount();
    });

    // ★부재 단언은 짝이 있어야 잠금이다 — 위 "열리면 들어온다"(양성)와 같은 실행 축에서
    //   "닫혀 있으면 안 훔친다"(음성)를 함께 단언한다.
    if (c.closed) {
      it("★음성대조 — 닫혀 있으면 포커스를 **훔치지 않는다**", () => {
        const outside = document.createElement("button");
        document.body.appendChild(outside);
        outside.focus();
        const view = render(c.closed!());
        expect(
          document.activeElement,
          `${c.file} 가 닫힌 채로 포커스를 가져갔다`,
        ).toBe(outside);
        view.unmount();
        outside.remove();
      });
    }
  });

  it("★트랩 중첩 금지 — 배선된 모달이 또 다른 배선 모달을 품으면 두 트랩이 겹친다", () => {
    // `useDismissible` 은 `DISMISS_Z` 로 **가장 위 하나만** 고르지만, `useModalFocus` 에는
    // 그런 조정이 없다. 두 트랩이 같은 keydown 에 각자 다른 컨테이너로 포커스를 옮기면
    // Tab 이 두 모달 사이를 튄다. 지금은 침범이 0건이고(실측), 이 래칫이 그 상태를 지킨다.
    // ★바늘을 `FOCUS_WIRED` 에서 **파생**시킨다(2026-08-22 R2). 종전엔 `"<ConfirmDeleteModal"`
    //   **하나로 고정**돼 있었는데, 정작 같은 커밋이 배선 표면을 1→4 로 늘렸다. 목록형이라
    //   새로 배선된 모달끼리 중첩되면 래칫이 못 본다(§A.4 목록형 금지).
    const nameOf = (f: string) => "<" + f.split("/").pop()!.replace(/\.tsx$/, "");
    const wiredNames = FOCUS_WIRED.map(nameOf);

    const offenders: string[] = [];
    for (const f of FOCUS_WIRED) {
      const code = executable(join(WEB_ROOT, f));
      for (const n of wiredNames) {
        if (n !== nameOf(f) && code.includes(n)) offenders.push(`${f} ⊃ ${n}`);
      }
    }
    expect(
      offenders,
      "포커스 배선 모달 안에 또 다른 배선 모달이 있다 — z 조정이 없어 두 트랩이 겹친다",
    ).toEqual([]);

    // ★양성 대조 — **같은 파이프라인**을 태워야 의미가 있다.
    //   종전엔 `"<ConfirmDeleteModal…".includes("<ConfirmDeleteModal")` 이었는데, 그건
    //   자바스크립트의 `String.includes` 를 검증할 뿐 `executable()`·경로 조립·주석 스트리퍼를
    //   **하나도 태우지 않는다**(항진명제). `executable()` 이 전부 빈 문자열을 돌려줘도 통과했다.
    expect(
      executable(join(WEB_ROOT, "components/projects/ProjectsOverviewClient.tsx")),
      "검사기가 죽었다 — 실제로 ConfirmDeleteModal 을 렌더하는 파일에서도 못 찾는다",
    ).toContain("<ConfirmDeleteModal");
  });
});

