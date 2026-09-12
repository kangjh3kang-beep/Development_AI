/**
 * ★**prop 단독 테스트는 배선을 잠그지 않는다**(2026-09-12 · 리뷰 M4).
 *
 * `passwordSet` 게이트를 `SiteEnterModal` 단독 렌더로만 태웠더니, 실제 호출부에서
 * 그 값이 **`undefined`** 로 들어가는 것을 아무도 못 봤다 —
 * `SiteWorkspaceClient` 의 `loadRole` 이 토큰 없는 경로에서 `setRole` 을 부르지 않아
 * `role?.password_set` 이 undefined 였고, 그것이 **주 경로**(신선 딥링크·토큰 만료)다.
 * 「함수 안은 N/N CAUGHT, 배선은 무잠금」의 재발이다.
 *
 * ⇒ 축을 **호출부**로 옮긴다. 호출부를 **나열하지 않고 파생**한다 — 새 호출부가 생기면
 *   자동으로 이 락에 들어온다.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

import { __stripCommentsForScan } from "@/lib/source-invariant";

const ROOT = join(__dirname, "..", "..", "..");

function sources(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === ".next" || name.startsWith(".")) continue;
    const full = join(dir, name);
    if (statSync(full).isDirectory()) sources(full, out);
    else if (/\.tsx$/.test(name) && !/\.test\.tsx$/.test(name)) out.push(full);
  }
  return out;
}

/** 주석을 걷어낸 소스 — 블록(`/* *\/`)은 공용 헬퍼, 줄(`//`)은 여기서. */
function scannable(src: string, fileName: string): string {
  return __stripCommentsForScan(src, fileName)
    .split("\n")
    .map((l) => {
      const i = l.indexOf("//");
      // 속성 위치의 줄 주석만 대상 — 문자열 안의 `//`(URL)은 건드리지 않는다.
      return i >= 0 && !/["'`]/.test(l.slice(0, i)) ? l.slice(0, i) : l;
    })
    .join("\n");
}

/** `<SiteEnterModal … />` 요소를 **파생**으로 모은다 → [좌표, 요소 원문]. */
function elementsIn(code: string, coordPrefix: string): Array<[string, string]> {
  const hits: Array<[string, string]> = [];
  let from = 0;
  for (;;) {
    const i = code.indexOf("<SiteEnterModal", from);
    if (i === -1) break;
    const end = code.indexOf(">", i);
    hits.push([
      `${coordPrefix}:${code.slice(0, i).split("\n").length}`,
      code.slice(i, end === -1 ? code.length : end + 1),
    ]);
    from = i + 1;
  }
  return hits;
}

function callSites(): Array<[string, string]> {
  const hits: Array<[string, string]> = [];
  for (const file of sources(ROOT)) {
    const code = scannable(readFileSync(file, "utf8"), file);
    hits.push(...elementsIn(code, relative(ROOT, file)));
  }
  return hits;
}

describe("SiteEnterModal 호출부 — 게이트를 실제로 공급하는가", () => {
  it("대조군: 호출부를 **파생으로** 찾았다(공허한 초록 방지)", () => {
    const hits = callSites();
    expect(hits.length, "호출부가 0건 — 조회기가 죽었다").toBeGreaterThanOrEqual(2);
    const files = new Set(hits.map(([c]) => c.split(":")[0]));
    expect(files).toContain("components/sales-app/SiteListClient.tsx");
    expect(files).toContain("components/sales-app/SiteWorkspaceClient.tsx");
  });

  it("★★모든 호출부가 `passwordSet` 을 넘긴다 — 새 호출부가 조용히 새지 않는다", () => {
    const missing = callSites()
      .filter(([, el]) => !/\bpasswordSet\s*=/.test(el))
      .map(([coord]) => coord);
    expect(
      missing,
      "`passwordSet` 을 안 넘기는 호출부가 있다 — 그 자리에서는 자동 시도가 항상 노크한다",
    ).toEqual([]);
  });

  it("★★`SiteWorkspaceClient` 는 토큰이 없는 경로에서도 `password_set` 을 **확보**한다", () => {
    const f = join(ROOT, "components/sales-app/SiteWorkspaceClient.tsx");
    const code = scannable(readFileSync(f, "utf8"), f);
    // 그 분기(`if (!getStoredSiteToken(siteId))`)가 role 을 물어본다.
    const i = code.indexOf("if (!getStoredSiteToken(siteId))");
    expect(i, "조기 반환 분기를 못 찾았다 — 축이 죽었다").toBeGreaterThan(-1);
    const branch = code.slice(i, i + 900);
    expect(
      /\/role/.test(branch),
      "토큰 없는 경로가 `password_set` 을 확보하지 않는다 — 게이트가 주 경로에서 inert 하다",
    ).toBe(true);
    // ★그리고 확보한 값이 실제로 모달로 간다(존재만이 아니라 배선).
    expect(/passwordSet=\{[^}]*pwSet[^}]*\}/.test(code)).toBe(true);
  });
});

describe("판정식 자신 — 합성 대조군(「위반 0」이 공짜가 아님을 증명)", () => {
  it("★prop 이 **없으면** 위반으로 신고한다", () => {
    const bad = elementsIn('<SiteEnterModal locale="ko" siteId="s" open />', "synthetic.tsx");
    expect(bad).toHaveLength(1);
    expect(/\bpasswordSet\s*=/.test(bad[0][1])).toBe(false);
  });

  it("★prop 이 **주석 처리**돼 있으면 위반으로 신고한다(주석에 뚫리지 않는다)", () => {
    const src = ['<SiteEnterModal', '  siteId="s"', '  // passwordSet={x}', '  open', '/>'].join("\n");
    const el = elementsIn(scannable(src, "synthetic.tsx"), "synthetic.tsx");
    expect(el).toHaveLength(1);
    expect(/\bpasswordSet\s*=/.test(el[0][1])).toBe(false);
  });

  it("★대조군 — prop 이 있으면 통과한다(판정식이 항상-거부가 아니다)", () => {
    const ok = elementsIn('<SiteEnterModal siteId="s" passwordSet={v} open />', "synthetic.tsx");
    expect(/\bpasswordSet\s*=/.test(ok[0][1])).toBe(true);
  });
});
