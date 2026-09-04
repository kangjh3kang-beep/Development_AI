/**
 * 러너가 **모든 테스트 파일을 실제로 수집하는가**.
 *
 * 【무엇을 막나 — 2026-08-24】
 * `vitest.config.ts` 의 `include` 가 디렉토리를 **손으로 나열**하는 목록형이었다
 * (`__tests__`·`app`·`components`·`hooks`·`lib`). 그래서 `store/` 에 계약 테스트를 만들자
 * `No test files found` 가 떴다 — 그대로 커밋했으면 **한 번도 실행되지 않는 락**이
 * 초록 안에 남았을 것이다. "테스트를 썼다"가 보증으로 읽히는데 아무것도 잠그지 않는다.
 *
 * 사람이 센 목록은 곧 상한이 된다. 그래서 include 를 파생형(`**` )으로 바꿨고,
 * 이 테스트는 **그 처방이 되돌려지면** 잡는다.
 *
 * ★계보: 러너가 모집단을 가르는 형태의 프론트 판
 * (백엔드는 `testpaths` 탓에 로컬 986 vs CI 10,344 였다).
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = resolve(__dirname, "..");
const SKIP = new Set(["node_modules", ".next", "e2e", "dist", "coverage", ".turbo"]);

/** 테스트 파일이 들어 있는 **최상위 디렉토리** 집합(파생형 수집). */
function topDirsWithTests(): Set<string> {
  const out = new Set<string>();
  const walk = (dir: string, top: string | null) => {
    let entries: string[];
    try {
      entries = readdirSync(dir);
    } catch {
      return;
    }
    for (const name of entries) {
      if (SKIP.has(name)) continue;
      const full = join(dir, name);
      let st;
      try {
        st = statSync(full);
      } catch {
        continue;
      }
      if (st.isDirectory()) walk(full, top ?? name);
      else if (/\.test\.tsx?$/.test(name) && top) out.add(top);
    }
  };
  walk(ROOT, null);
  return out;
}

function includeGlobs(): string[] {
  const src = readFileSync(join(ROOT, "vitest.config.ts"), "utf8");
  const block = src.match(/include:\s*\[([\s\S]*?)\]/);
  if (!block) return [];
  return [...block[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
}

/** 이 glob 이 해당 최상위 디렉토리를 덮는가(보수적으로 판단). */
function covers(glob: string, topDir: string): boolean {
  if (glob.startsWith("**/")) return true; // 파생형 — 전부 덮는다
  return glob.split("/")[0] === topDir;
}

describe("러너 수집 범위", () => {
  it("전제: include 를 읽었고 테스트 디렉토리를 찾았다(공허한 초록 방지)", () => {
    expect(includeGlobs().length, "include 를 파싱하지 못했다").toBeGreaterThan(0);
    expect(topDirsWithTests().size, "테스트 파일을 한 개도 못 찾았다").toBeGreaterThan(2);
  });

  it("★테스트 파일이 있는 디렉토리는 **전부** 수집 범위 안에 있다", () => {
    const globs = includeGlobs();
    const orphans = [...topDirsWithTests()].filter((d) => !globs.some((g) => covers(g, d)));
    expect(orphans, `수집되지 않는 테스트 디렉토리(그 안의 락은 영영 실행되지 않는다): ${orphans.join(", ")}`)
      .toEqual([]);
  });

  it("대조군 — 존재하지 않는 디렉토리는 덮이지 않는다고 판정한다(판정기가 살아 있다)", () => {
    expect(["lib/**/*.test.ts"].some((g) => covers(g, "zzz-없는디렉토리"))).toBe(false);
    expect(["**/*.test.ts"].some((g) => covers(g, "zzz-없는디렉토리"))).toBe(true);
  });
});
