/**
 * **모든** 에러 경계가 공용 보고기(`reportBoundaryError`)를 태우는지 잠근다.
 *
 * 【왜 이 락이 필요한가 — 2026-08-27 실측】
 * `app/global-error.tsx` 는 `trackEvent("js_error", …)` 를 **부르고 있었는데 배달되지 않았다.**
 * `trackEvent` 는 링버퍼에 넣기만 하고, 전송(`flush`)을 구동하는 것은 ①`ring.length >= 20`
 * ②`initEventCollector()` 안에서 등록되는 타이머·`pagehide`·`visibilitychange` ③`teardown` **뿐**이다.
 * 그런데 `global-error.tsx` 는 `<html>` 을 직접 렌더한다 = 루트 레이아웃을 대체한다 =
 * `AppStateBridge`(→`initEventCollector`)가 마운트되지 않는다 → 1건은 임계 20 에 영원히 미달.
 *
 * ★**파생의 축은 「파일명」이 아니라 「에러 경계」다.**
 * 초판은 `error.tsx` 파일명으로만 파생해서 **클래스 경계 2개를 통째로 놓쳤다**(독립 리뷰 적발):
 *   · `components/common/MapShell.tsx` — 오류를 **가둔다**(상위 `error.tsx` 로 전파 안 됨).
 *     즉 거기서 보고하지 않으면 **아무도** 보고하지 않는다. 소비처 8곳(지도·타일 = 최빈 파손면)
 *   · `components/projects/HubErrorBoundary.tsx` — `console.error` 만 남긴다(브라우저 밖으로 안 나감)
 * 그래서 축을 **`getDerivedStateFromError`/`componentDidCatch` 를 가진 파일 ∪ `error.tsx`** 로 넓힌다.
 *
 * ★이 파일이 잠그지 **못하는** 것(정직하게 — 다른 층이 맡는다):
 * 소스 문자열 검사는 **死코드와 실행줄을 구별하지 못한다**(`if (false) report(…)` 는 여기서 초록).
 * 그 층은 경계를 **실제로 렌더하는** `lib/growth/__tests__/boundary-render-delivery.test.tsx` 가 잠근다.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

import { __stripCommentsForScan } from "@/lib/source-invariant";

const WEB_ROOT = join(__dirname, "..", "..");

function walk(dir: string, out: string[] = []): string[] {
  let entries: string[] = [];
  try {
    entries = readdirSync(dir);
  } catch {
    return out;
  }
  for (const e of entries) {
    if (e === "node_modules" || e === ".next") continue;
    const p = join(dir, e);
    if (statSync(p).isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

// ★파일당 여러 번 읽히므로 메모이즈한다(축을 `lib` 까지 넓히며 대상이 282파일 늘었다).
const _codeCache = new Map<string, string>();
const code = (f: string): string => {
  const hit = _codeCache.get(f);
  if (hit !== undefined) return hit;
  const v = __stripCommentsForScan(readFileSync(f, "utf8"), f);
  _codeCache.set(f, v);
  return v;
};

/** ★파생: 파일명이 경계이거나, **오류 경계 훅을 구현한** 파일. 새 경계는 자동 편입된다. */
// ★`lib` 도 넣는다 — 보고기를 부르는 곳이 `app`/`components` 밖에도 있다
//   (`lib/chunk-recovery.ts` 가 자동복구 직전에 보고한다).
const CANDIDATES = [join(WEB_ROOT, "app"), join(WEB_ROOT, "components"), join(WEB_ROOT, "lib")].flatMap(
  (d) => walk(d),
);
const boundaries = CANDIDATES.filter((f) => {
  if (!/\.tsx$/.test(f)) return false;
  if (/[\\/](error|global-error)\.tsx$/.test(f)) return true;
  return /\b(getDerivedStateFromError|componentDidCatch)\s*[(<]/.test(code(f));
});

/** 임포트 **선언**만 본다 — `trackEvent(` 문자열 검사는 별칭 임포트로 우회된다(독립 리뷰 실증). */
function importsFrom(src: string, mod: string): boolean {
  const re = new RegExp(
    String.raw`(?:^|\n)\s*import[\s\S]{0,400}?from\s*["']${mod.replace(/[/@-]/g, "\\$&")}["']`,
  );
  return re.test(src) || new RegExp(String.raw`require\(\s*["']${mod.replace(/[/@-]/g, "\\$&")}["']`).test(src);
}

describe("에러 경계 — 오류 보고 전수 배선", () => {
  it("전제: 에러 경계를 실제로 찾았다(공허한 초록 방지)", () => {
    expect(
      boundaries.length,
      "에러 경계를 하나도 못 찾았다 — 조회기가 죽었다",
    ).toBeGreaterThan(5);
  });

  it("★전제: 파생 축이 **클래스 경계까지** 잡는다(파일명 축으로 좁아지면 실패)", () => {
    const names = boundaries.map((f) => relative(WEB_ROOT, f));
    // 이 둘은 파일명이 `error.tsx` 가 **아니다** — 축이 좁아지면 즉시 빠진다.
    expect(names).toContain("components/common/MapShell.tsx");
    expect(names).toContain("components/projects/HubErrorBoundary.tsx");
  });

  it("★(정) 모든 경계가 공용 보고기를 호출한다(소스 층 — 死코드는 렌더 락이 본다)", () => {
    const missing = boundaries
      .filter((f) => !/reportBoundaryError\s*\(/.test(code(f)))
      .map((f) => relative(WEB_ROOT, f));
    expect(
      missing,
      `오류 보고가 배선되지 않은 경계 — 그 라우트의 실패는 성장루프에 **한 건도** 안 남는다:\n${missing.join("\n")}`,
    ).toEqual([]);
  });

  it("★(역) 보고하는 **모든 파일**이 수집기를 직접 임포트하지 않는다 — 별칭 우회까지 막는다", () => {
    // ★모집단을 `경계` 가 아니라 **「보고기를 부르는 파일 전수」**로 넓힌다.
    //   `lib/chunk-recovery.ts` 는 경계가 아니지만 자동복구 직전에 보고한다(2026-08-27) —
    //   좁은 축에서는 그 파일이 `trackEvent` 를 직접 불러도 **아무것도 막지 않았다**.
    // ★**정의를 호출로 세지 않는다**: `report-boundary-error.ts` 자신은 당연히 수집기를
    //   임포트한다(그게 그 파일의 일이다). 초판은 그것을 위반으로 신고했다 — **위양성도 결함이다.**
    //   ★오늘 같은 형태로 세 번 데였다(`record_event` 정의 · 동명의 다른 함수 · 여기).
    const reporters = CANDIDATES.filter(
      (f) =>
        /\.tsx?$/.test(f) &&
        /reportBoundaryError\s*\(/.test(code(f)) &&
        // ★테스트 파일은 제외한다 — 배달을 단언하는 **정당한** 테스트가 collector 를 임포트하는데,
        //   그것을 위반으로 신고하면 정상 코드를 막는다(위양성도 결함이다).
        !/__tests__|\.(test|spec)\./.test(f) &&
        !/export\s+function\s+reportBoundaryError/.test(code(f)),
    );
    expect(
      reporters.some((f) => f.endsWith("chunk-recovery.ts")),
      "보고기 호출부 파생이 `lib/chunk-recovery.ts` 를 못 잡았다 — 축이 좁아졌다",
    ).toBe(true);
    const leaked = reporters
      .filter((f) => importsFrom(code(f), "@/lib/growth/event-collector"))
      .map((f) => relative(WEB_ROOT, f));
    expect(
      leaked,
      `보고하는 파일이 수집기를 직접 임포트한다 — 배달 구동자 없는 문서에서 그 이벤트는\n영영 링버퍼에 갇힌다. reportBoundaryError 를 써라:\n${leaked.join("\n")}`,
    ).toEqual([]);

    const bypass = boundaries
      .filter((f) => importsFrom(code(f), "@/lib/growth/event-collector"))
      .map((f) => relative(WEB_ROOT, f));
    expect(
      bypass,
      "경계가 event-collector 를 직접 임포트한다 — `trackEvent` 를 (별칭으로라도) 부르면 수집기가\n" +
        "없는 문서에서 배달 구동자가 없어 그 이벤트는 영영 링버퍼에 갇힌다. reportBoundaryError 를 써라:\n" +
        `${bypass.join("\n")}`,
    ).toEqual([]);
  });

  it("★scope 가 경계마다 **서로 다르다** — 같으면 어느 화면이 깨졌는지 조회로 못 가른다", () => {
    const scopes = boundaries.map((f) => ({
      file: relative(WEB_ROOT, f),
      scope: /reportBoundaryError\s*\(\s*"([^"]+)"/.exec(code(f))?.[1] ?? null,
    }));
    const nullish = scopes.filter((s) => !s.scope).map((s) => s.file);
    expect(nullish, `scope 리터럴을 못 읽었다:\n${nullish.join("\n")}`).toEqual([]);

    const seen = new Map<string, string[]>();
    for (const s of scopes) seen.set(s.scope!, [...(seen.get(s.scope!) ?? []), s.file]);
    const dupes = [...seen.entries()].filter(([, v]) => v.length > 1);
    expect(
      dupes.map(([k, v]) => `${k}: ${v.join(", ")}`),
      "두 경계가 같은 scope 를 쓴다 — 어느 화면이 깨졌는지 구별할 수 없다",
    ).toEqual([]);
  });
});
