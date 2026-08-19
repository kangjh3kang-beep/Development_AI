/**
 * **모든** 에러 경계가 청크 자동복구를 태우는지 잠근다.
 *
 * 【왜 전수인가】청크 404 는 어느 라우트에서든 난다. 한 경계만 배선하면 그 라우트 밖에서는
 * 사용자가 여전히 **낫지 않는 "다시 시도"** 를 누른다. 그리고 새 경계가 추가될 때
 * 아무도 이 배선을 기억하지 못한다 — 그래서 **목록이 아니라 파일에서 파생**한다.
 *
 * ★파생의 축: `app/**\/error.tsx` + `app/global-error.tsx` (**파일 단위**).
 *   새 경계가 생기면 자동으로 이 검사 대상에 들어온다.
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

function boundaries(): string[] {
  return walk(APP).filter((f) => /[\\/](error|global-error)\.tsx$/.test(f));
}

describe("에러 경계 — 청크 자동복구 전수 배선", () => {
  const files = boundaries();

  it("전제: 에러 경계를 실제로 찾았다(공허한 초록 방지)", () => {
    expect(files.length, "에러 경계를 하나도 못 찾았다 — 조회기가 죽었다").toBeGreaterThan(5);
  });

  it("★모든 경계가 실행되는 줄에서 복구를 호출한다", () => {
    const missing: string[] = [];
    for (const f of files) {
      // ★주석에 적어 놓고 안 부르는 것을 통과시키지 않는다(소스 검사는 주석에 뚫린다).
      const src = __stripCommentsForScan(readFileSync(f, "utf8"), f);
      if (!/tryRecoverFromChunkError\s*\(/.test(src)) missing.push(relative(WEB_ROOT, f));
    }
    expect(
      missing,
      `청크 복구가 배선되지 않은 에러 경계 — 그 라우트에서는 사용자가 낫지 않는 버튼을 누른다:\n${missing.join("\n")}`,
    ).toEqual([]);
  });
});
