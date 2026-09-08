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

/**
 * ★락이 요구하는 **호출 형태** — 락과 탐지 테스트가 **같은 심볼**을 쓴다.
 *
 * 종전엔 탐지 테스트가 이 문자열을 **다시 선언**했다. 그래서 락의 판정식을 약화시켜도
 * 탐지 테스트는 자기 사본을 보고 초록이었다 — `String.includes` 의 동작을 단언한 것이지
 * **가드를 단언한 것이 아니었다**(2026-09-08 적대 리뷰 MAJOR-1, 변이로 실증).
 * ⇒ 상수 하나로 묶어 **약화가 곧 빨강**이 되게 한다.
 */
const CALL_SHAPE = "shouldInterceptFieldAppClick(";

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
 * ★**(fieldapp) 라우트 집합을 디렉토리에서 파생시킨다** (2026-09-08 적대 리뷰 NM-2(d)).
 *
 * 종전엔 독스트링이 *"축은 「(fieldapp) 라우트를 가리키는 링크」"* 라 **선언**해 놓고
 * 구현은 문자열 `/sales/sites` **하나**였다 — **선언은 파생형, 구현은 목록형**이었다.
 * `(fieldapp)` 아래 새 `page.tsx` 가 생기면 그 라우트로 가는 링크가 전부 감시망 밖이었다.
 */
function fieldAppRouteSegments(base = join(WEB_ROOT, "app", "[locale]", "(fieldapp)")): string[] {
  const segs = new Set<string>();
  const walk = (dir: string, parts: string[]) => {
    for (const name of readdirSync(dir)) {
      const full = join(dir, name);
      if (statSync(full).isDirectory()) {
        // 동적 세그먼트([siteId])와 라우트 그룹((...))은 경로 리터럴에 안 나타난다.
        walk(full, name.startsWith("[") || name.startsWith("(") ? parts : [...parts, name]);
      } else if (name === "page.tsx" && parts.length) {
        segs.add("/" + parts.join("/"));
      }
    }
  };
  walk(base, []);
  return [...segs];
}

/** 라우트 세그먼트 중 **가장 짧은 접두**들 — 하위 경로까지 한 번에 덮는다. */
const FIELDAPP_ROUTES = (() => {
  const all = fieldAppRouteSegments().sort((a, b) => a.length - b.length);
  return all.filter((r) => !all.some((o) => o !== r && r.startsWith(o + "/")));
})();

/** `href=` 와 (fieldapp) 라우트가 **같은 줄**에 있는 렌더 줄. */
function isFieldAppHrefLine(line: string): boolean {
  return line.includes("href=") && FIELDAPP_ROUTES.some((r) => line.includes(r));
}

describe("현장앱 진입 — 플랫폼 쪽 링크는 전부 진입 정책을 거친다(파생형)", () => {
  it("★공허 진리 가드 — 모집단이 비어 있지 않다", () => {
    expect(files.length).toBeGreaterThan(200);
    const anyHref = files.filter((f) =>
      codeOnly(readFileSync(f, "utf8"), f).split("\n").some(isFieldAppHrefLine),
    );
    // 하나도 없으면 아래 판정 전체가 공허하다.
    expect(anyHref.length).toBeGreaterThan(0);
  });

  it("① 직접 링크 — 플랫폼 쪽에서 (fieldapp) 로 가는 href 는 FieldAppLaunchLink 로 그린다", () => {
    const offenders: string[] = [];
    for (const f of files) {
      if (isIntraApp(f)) continue; // 앱 내 이동은 대상 아님
      const code = codeOnly(readFileSync(f, "utf8"), f);
      for (const line of code.split("\n")) {
        if (!isFieldAppHrefLine(line)) continue;
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
      .filter((f) => codeOnly(readFileSync(f, "utf8"), f).split("\n").some(isFieldAppHrefLine));
    expect(intra.length).toBeGreaterThan(0);
  });

  it("③ 레지스트리 경유 — NavNode 를 링크로 그리는 렌더러는 `launch` 를 해석한다", () => {
    // 축: 「NavNode 를 링크로 그리는 파일」 = NavNode 를 참조하고 <Link 를 렌더한다.
    const renderers = files.filter((f) => {
      const code = codeOnly(readFileSync(f, "utf8"), f);
      return code.includes("NavNode") && code.includes("<Link");
    });

    // 공허 진리 가드 — 렌더러가 0개면 아래가 무의미하다.
    // ★실제 렌더러는 정확히 2개(SidebarNav·WorkspaceNavBar)다. `>1` 이면 하나가 사라져도
    //   가드가 조용히 무력화된다 — 못 박고, 늘어나면 **의도적으로** 갱신하게 한다.
    expect(renderers.map(rel).sort()).toEqual([
      join("components", "layout", "SidebarNav.tsx"),
      join("components", "layout", "WorkspaceNavBar.tsx"),
    ]);

    const missing = renderers
      // ★「이름이 있다」가 아니라 **호출 형태**를 요구한다(적대 리뷰 NM-2(b)).
      //   프로브 실증: `const _x = shouldInterceptFieldAppClick;` 만 두고 **호출 0** 인데 통과했다.
      .filter((f) => !codeOnly(readFileSync(f, "utf8"), f).includes(CALL_SHAPE))
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

/*
 * ★이 락이 **못 보는 축**을 초록 안에 남긴다(§B-13 — 커밋 메시지에만 적으면 드러나지 않는다).
 *   적대 리뷰가 프로브로 각각 실증했다.
 */
describe("남은 부채 — 이 축이 못 보는 것", () => {
  it.todo(
    "★렌더러 수집이 아직 **어휘 축**이다 — `NavNode` 라는 낱말을 안 쓰고 `NavSection` 만 임포트해 " +
      "`sections.flatMap(s => s.items)` 로 링크를 그리면 렌더러로 안 세어진다(프로브 실증: 5 passed). " +
      "처방은 렌더러마다 `*.appWindow.test.tsx` 형태의 **행위 락**을 두는 것 — 그러면 이 축이 필요 없어진다",
  );
  it.todo(
    "★`href` 가 **변수**면 ①이 못 본다 — `const dest = `/${locale}/sales/sites`;` … `<Link href={dest}>` " +
      "가 통과한다(프로브 실증). 축이 «같은 줄의 리터럴» 이기 때문",
  );
  it.todo(
    "★**명령형 이동**(`router.push('/…/sales/sites…')`)은 축 밖이다. 오늘 플랫폼 쪽 0건이지만 " +
      "(대조군: 현장앱 **내부**에 3건 실재 — 조회기는 살아 있다) 새로 생기면 감시망에 안 든다",
  );
});

/*
 * ★★**탐지 축을 따로 잠근다**(저장소 §가드는 3축 — 탐지·특이도·배선).
 *
 * 위 describe 는 «오늘 위반이 0건» 을 단언한다. 그런데 **판정 함수를 약화시켜도 그것은 초록이다**
 * — 위반 파일이 없으니 무엇으로 재도 0이기 때문이다. 실제로 변이로 실증했다:
 *
 *     includes("shouldInterceptFieldAppClick(") → includes("shouldInterceptFieldAppClick")
 *         ::VERDICT=SURVIVED          ← 「호출 형태」를 「이름 존재」로 되돌려도 안 잡힌다
 *     FIELDAPP_ROUTES.some(...)        → line.includes("/sales/sites")
 *         ::VERDICT=SURVIVED          ← 라우트 파생을 리터럴 하나로 되돌려도 안 잡힌다
 *
 * ⇒ **판정 함수를 합성 입력으로 직접 태운다.** 그러면 약화가 곧 빨강이 된다.
 */
describe("★탐지 축 — 판정 함수가 실제로 무엇을 가르는가", () => {
  it("★라우트 집합이 **디렉토리에서 파생**된다 — 리터럴이면 픽스처를 못 읽는다", () => {
    // ★2026-09-08 적대 리뷰 MAJOR-1(②): 종전 단언은 **프로덕션 라우트만** 입력으로 썼는데,
    //   오늘 파생 결과가 리터럴 `"/sales/sites"` 와 **완전히 같다**(실측 확인).
    //   ⇒ 「파생판」과 「리터럴판」이 같은 답을 내는 입력으로만 태우고 있었다 —
    //     **차가 0인 픽스처는 잠금이 아니다.**
    //   ⇒ **다른 세그먼트를 가진 픽스처 디렉토리**로 두 판을 가른다.
    const fx = join(WEB_ROOT, "lib", "__fixtures__", "fieldapp-routes", "(fieldapp)");
    const derived = fieldAppRouteSegments(fx);

    // 양성: 픽스처의 라우트를 **실제로 읽어 온다**(리터럴 구현은 여기서 빈 배열이 된다).
    expect(derived).toContain("/probe");
    // 접두 축약도 함께 — 하위 라우트는 상위 접두에 흡수된다.
    expect(derived).not.toContain("/sales/sites");

    // 대조군: 프로덕션 base 는 프로덕션 라우트를 준다(조회기가 base 를 실제로 쓴다).
    expect(FIELDAPP_ROUTES.some((r) => r.includes("sales"))).toBe(true);
    expect(FIELDAPP_ROUTES.length).toBeGreaterThan(0);
  });

  it("★두 모집단 — 앱 라우트 href 줄은 잡고, 무관한 href 줄은 안 잡는다", () => {
    const route = FIELDAPP_ROUTES[0]!;
    expect(isFieldAppHrefLine(`<Link href={\`/\${locale}${route}\`}>`)).toBe(true);
    // 특이도: 정상 코드를 막으면 그것도 결함이다.
    expect(isFieldAppHrefLine(`<Link href={\`/\${locale}/projects\`}>`)).toBe(false);
    expect(isFieldAppHrefLine(`const x = "${route}";`)).toBe(false); // href= 가 없다
  });

  it("★「호출 형태」와 「이름 언급」을 가른다 — 이름만 있으면 통과시키면 안 된다", () => {
    const CALL = CALL_SHAPE; // ★락이 쓰는 그 심볼 — 사본이 아니다
    const mention = "const _unused = shouldInterceptFieldAppClick; void _unused;";
    const call = "if (node.launch === 'app-window' && shouldInterceptFieldAppClick(e)) {";
    // 락이 쓰는 것과 **같은 판정**을 여기서 태운다.
    expect(call.includes(CALL)).toBe(true);
    expect(mention.includes(CALL)).toBe(false); // ★이 줄이 변이 A 를 CAUGHT 로 만든다
  });
});
