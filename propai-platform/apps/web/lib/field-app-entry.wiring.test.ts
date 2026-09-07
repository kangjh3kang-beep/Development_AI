import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, sep } from "node:path";

import { describe, expect, it } from "vitest";

import { __stripCommentsForScan } from "@/lib/source-invariant";

/**
 * ★**플랫폼에서 현장앱으로 가는 링크는 전부 진입 정책을 거친다** — 축은
 * **「(fieldapp) 라우트를 가리키는 링크를 그리는 곳」**이다(파생형).
 *
 * ## 왜 이 락을 새로 만드나 (2026-09-08 적대 리뷰 B-1·M-1)
 *
 * 형제 락(`field-app-launch.wiring.test.ts`)의 축은 **「`window.open` 을 담은 파일」**이었다.
 * 그 축은 **이 결함이 사는 층에 닿지 않는다** — 결함은 «창을 잘못 연다» 가 아니라
 * **«창을 열지 **않고** 그냥 이동한다»** 이고, 그런 파일에는 `window.open` 이 **없다.**
 *
 * 실제로 그 축으로는 두 곳을 놓쳤고 리뷰가 실행으로 잡았다:
 *
 *   components/layout/WorkspaceNavBar.tsx   ← ★**데스크톱 내비**(lg:block). 신고자 모집단이다.
 *                                              사이드바는 MobileSidebarToggle 안에서만 렌더되고
 *                                              그것은 전부 lg:hidden — **모바일 전용**이었다.
 *   components/sales/SalesSiteList.tsx:189  ← 같은 헤더 85줄 아래의 「현장앱 진입」
 *
 * > **축 하나가 틀리자 그 위의 모든 성실함이 잘못된 모집단을 향했다.**
 *
 * ## 두 갈래를 함께 잠근다
 *
 * ①**직접 링크** — href 리터럴이 `(fieldapp)` 라우트를 가리키면 `FieldAppLaunchLink` 여야 한다.
 * ②**레지스트리 경유** — `NavNode` 를 링크로 그리는 렌더러는 `launch` 를 **해석**해야 한다.
 *   렌더러가 새로 생기면(모바일/데스크톱 말고 명령 팔레트 등) 자동으로 걸린다.
 */

const WEB_ROOT = join(__dirname, "..");

/** 현장앱 셸 **안쪽**은 대상이 아니다 — 앱 내 이동은 새 창을 열면 안 된다. */
const INTRA_APP = [join("components", "sales-app") + sep, join("app", "[locale]", "(fieldapp)") + sep];

const SKIP_DIRS = new Set(["node_modules", ".next", "dist", "build", "coverage", "e2e", "public"]);

function sourceFiles(dir: string, acc: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue;
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      sourceFiles(full, acc);
      continue;
    }
    if (!/\.(ts|tsx)$/.test(name)) continue;
    if (/\.(test|spec)\.tsx?$/.test(name)) continue;
    acc.push(full);
  }
  return acc;
}

function codeOnly(src: string, file: string): string {
  return __stripCommentsForScan(src, file)
    .split("\n")
    .filter((l) => {
      const t = l.trim();
      return !t.startsWith("//") && !t.startsWith("*");
    })
    .join("\n");
}

const files = sourceFiles(WEB_ROOT);
const rel = (f: string) => f.slice(WEB_ROOT.length + 1);
const isIntraApp = (f: string) => INTRA_APP.some((p) => rel(f).startsWith(p));

/**
 * `href=` 와 `(fieldapp)` 라우트가 **같은 줄**에 있는 렌더 줄.
 *
 * ★처음엔 `href=\{[^}]*\/sales\/sites` 로 썼다가 **조회기가 죽었다** — 템플릿 리터럴
 *   `` href={`/${locale}/sales/sites`} `` 의 `${locale}` 안에 `}` 가 있어 `[^}]*` 가 넘지 못한다.
 *   **공허 진리 가드가 그것을 잡았다**(매칭 0건 → 빨강). 가드가 없었으면 "위반 0" 으로 초록이었다.
 */
const FIELDAPP_HREF = /href=[\s\S]*\/sales\/sites/;

describe("현장앱 진입 — 플랫폼 쪽 링크는 전부 진입 정책을 거친다(파생형)", () => {
  it("★공허 진리 가드 — 모집단이 비어 있지 않다", () => {
    expect(files.length).toBeGreaterThan(200);
    const anyHref = files.filter((f) => FIELDAPP_HREF.test(codeOnly(readFileSync(f, "utf8"), f)));
    // 하나도 없으면 아래 판정 전체가 공허하다.
    expect(anyHref.length).toBeGreaterThan(0);
  });

  it("① 직접 링크 — 플랫폼 쪽에서 (fieldapp) 로 가는 href 는 FieldAppLaunchLink 로 그린다", () => {
    const offenders: string[] = [];
    for (const f of files) {
      if (isIntraApp(f)) continue; // 앱 내 이동은 대상 아님
      const code = codeOnly(readFileSync(f, "utf8"), f);
      for (const line of code.split("\n")) {
        if (!FIELDAPP_HREF.test(line)) continue;
        if (line.includes("FieldAppLaunchLink")) continue;
        offenders.push(`${rel(f)}: ${line.trim().slice(0, 100)}`);
      }
    }
    expect(
      offenders,
      `플랫폼에서 현장앱으로 가는 링크가 진입 정책을 안 거친다:\n  ${offenders.join("\n  ")}`,
    ).toEqual([]);
  });

  it("★② 대조군 — 앱 **내부**(sales-app)에는 그런 href 가 실재하고, 그것은 위반이 아니다", () => {
    // 이게 없으면 ①의 "위반 0" 이 «그런 href 자체가 없어서» 인지 구별되지 않는다.
    const intra = files
      .filter(isIntraApp)
      .filter((f) => FIELDAPP_HREF.test(codeOnly(readFileSync(f, "utf8"), f)));
    expect(intra.length).toBeGreaterThan(0);
  });

  it("③ 레지스트리 경유 — NavNode 를 링크로 그리는 렌더러는 `launch` 를 해석한다", () => {
    // 축: 「NavNode 를 링크로 그리는 파일」 = NavNode 를 참조하고 <Link 를 렌더한다.
    const renderers = files.filter((f) => {
      const code = codeOnly(readFileSync(f, "utf8"), f);
      return code.includes("NavNode") && code.includes("<Link");
    });

    // 공허 진리 가드 — 렌더러가 0개면 아래가 무의미하다.
    expect(renderers.length).toBeGreaterThan(1);

    const missing = renderers
      .filter((f) => !codeOnly(readFileSync(f, "utf8"), f).includes("shouldInterceptFieldAppClick"))
      .map(rel);

    expect(
      missing,
      `NavNode 를 링크로 그리는데 앱형 라우트 정책을 해석하지 않는다:\n  ${missing.join("\n  ")}`,
    ).toEqual([]);
  });

  it("★④ 클릭 정책은 **한 벌**이다 — 소비처가 각자 수식키를 재구현하지 않는다", () => {
    // 리뷰 M-3: 공용화가 「창을 여는 함수」까지만 가고 「무엇을 가로챌지」는 두 벌로 남아 있었다
    // (한쪽은 defaultPrevented·button 을 보고 다른 쪽은 안 봤다).
    const consumers = files.filter((f) =>
      codeOnly(readFileSync(f, "utf8"), f).includes("launchFieldApp("),
    );
    expect(consumers.length).toBeGreaterThan(2); // 공허 진리 가드

    const handRolled = consumers
      .filter((f) => !rel(f).startsWith(join("lib", "field-app-launch")))
      .filter((f) => {
        const code = codeOnly(readFileSync(f, "utf8"), f);
        // 자기 손으로 수식키를 열거하면서 공용 판정을 안 쓰는 형태.
        return /metaKey|ctrlKey|shiftKey|altKey/.test(code) && !code.includes("shouldInterceptFieldAppClick");
      })
      .map(rel);

    expect(
      handRolled,
      `클릭 가로채기 판정이 두 벌이다 — shouldInterceptFieldAppClick 을 쓰라:\n  ${handRolled.join("\n  ")}`,
    ).toEqual([]);
  });
});
