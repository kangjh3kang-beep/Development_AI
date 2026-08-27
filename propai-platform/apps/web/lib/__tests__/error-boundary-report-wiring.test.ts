/**
 * **모든** 에러 경계가 공용 보고기(`reportBoundaryError`)를 태우는지 잠근다.
 *
 * 【왜 이 락이 필요한가 — 2026-08-27 실측】
 * `app/global-error.tsx` 는 `trackEvent("js_error", …)` 를 **부르고 있었는데 배달되지 않았다.**
 * `trackEvent` 는 링버퍼에 넣기만 하고, 실제 전송(`flush`)을 구동하는 것은
 * ①`ring.length >= 20` ②`initEventCollector()` 안에서 등록되는 타이머·`pagehide`·
 * `visibilitychange` ③`teardownEventCollector` **뿐**이다(`event-collector.ts` 파생형 전수).
 * 그런데 `global-error.tsx` 는 `<html>` 을 직접 렌더한다 = **루트 레이아웃을 대체**한다 =
 * `AppStateBridge`(→`useGrowthEvents`→`initEventCollector`)가 마운트되지 않는다.
 * → 1건짜리 오류는 임계 20 에 영원히 미달하고 구동자도 없어 **영영 안 나갔다**(3모집단 실측).
 *
 * ★그래서 이 락은 **두 방향을 다 건다.** 한쪽만 걸면 반대 방향이 원리적으로 탐지 불가다:
 *   (정) 모든 경계가 `reportBoundaryError` 를 **실행되는 줄에서** 부른다
 *   (역) 어떤 경계도 `trackEvent` 를 **직접** 부르지 않는다 ← 이것이 결함이 살던 자리다
 *
 * ★파생의 축: `app/**\/error.tsx` + `app/global-error.tsx`(**파일 단위**). 새 경계는 자동 편입.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

import { __stripCommentsForScan } from "@/lib/source-invariant";

const WEB_ROOT = join(__dirname, "..", "..");
const APP = join(WEB_ROOT, "app");

function walk(dir: string, out: string[] = []): string[] {
  let entries: string[] = [];
  try {
    entries = readdirSync(dir);
  } catch {
    return out;
  }
  for (const e of entries) {
    const p = join(dir, e);
    if (statSync(p).isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

const files = walk(APP).filter((f) => /[\\/](error|global-error)\.tsx$/.test(f));
const code = (f: string) => __stripCommentsForScan(readFileSync(f, "utf8"), f);

describe("에러 경계 — 오류 보고 전수 배선", () => {
  it("전제: 에러 경계를 실제로 찾았다(공허한 초록 방지)", () => {
    expect(files.length, "에러 경계를 하나도 못 찾았다 — 조회기가 죽었다").toBeGreaterThan(5);
  });

  it("★(정) 모든 경계가 실행되는 줄에서 공용 보고기를 호출한다", () => {
    const missing = files
      .filter((f) => !/reportBoundaryError\s*\(/.test(code(f)))
      .map((f) => relative(WEB_ROOT, f));
    expect(
      missing,
      `오류 보고가 배선되지 않은 경계 — 그 라우트의 실패는 성장루프에 **한 건도** 안 남는다:\n${missing.join("\n")}`,
    ).toEqual([]);
  });

  it("★(역) 어떤 경계도 trackEvent 를 직접 부르지 않는다 — 결함이 살던 자리", () => {
    const bypass = files
      .filter((f) => /\btrackEvent\s*\(/.test(code(f)))
      .map((f) => relative(WEB_ROOT, f));
    expect(
      bypass,
      "경계가 trackEvent 를 직접 부른다 — 수집기가 없는 문서(global-error)에서는 배달 구동자가\n" +
        `없어 그 이벤트가 영영 링버퍼에 갇힌다. reportBoundaryError 를 써라:\n${bypass.join("\n")}`,
    ).toEqual([]);
  });

  it("★scope 가 경계마다 **서로 다르다** — 같으면 analyzer 가 라우트를 못 가른다", () => {
    const scopes = files.map((f) => {
      const m = /reportBoundaryError\s*\(\s*"([^"]+)"/.exec(code(f));
      return { file: relative(WEB_ROOT, f), scope: m?.[1] ?? null };
    });
    const nullish = scopes.filter((s) => !s.scope).map((s) => s.file);
    expect(nullish, `scope 리터럴을 못 읽었다:\n${nullish.join("\n")}`).toEqual([]);

    const seen = new Map<string, string[]>();
    for (const s of scopes) seen.set(s.scope!, [...(seen.get(s.scope!) ?? []), s.file]);
    const dupes = [...seen.entries()].filter(([, v]) => v.length > 1);
    expect(
      dupes.map(([k, v]) => `${k}: ${v.join(", ")}`),
      "두 경계가 같은 scope 를 쓴다 — 어느 화면이 깨졌는지 구별할 수 없다",
    ).toEqual([]);
    // 공허 진리 가드: 파생이 실제로 파일 수만큼 스코프를 뽑았는가.
    expect(seen.size).toBe(files.length);
  });
});
