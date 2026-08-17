/**
 * VWorld 키가 **브라우저로 새는 배관**을 되살리지 못하게 잠근다.
 *
 * 【실장애 2026-08-17 · 내가 세 번 오판한 건】
 * `NEXT_PUBLIC_VWORLD_API_KEY` 는 **읽는 클라이언트 코드가 0개**인데 배관만 남아 있었다
 * (`Dockerfile.web` 의 ARG/ENV · compose build arg · `.env.example`).
 * 값이 비어 있어 실제 노출은 없었지만 두 가지가 실재했다:
 *   (1) **누가 `.env` 에 값을 넣는 순간 조용히 번들로 인라인**된다 — 코드 변경 0 으로 유출.
 *   (2) 빈 값 자체가 결함을 만들었다 — `if (!KEY) return null` 이 항상 null 을 반환해
 *       AVM 항공영상이 아예 렌더되지 않았다.
 *
 * 【노출 여부는 어디서 판정되나 — 내가 세 번 틀린 지점】
 *   ✗ 저장소 `.env`        — 실효값이 아니다
 *   ✗ 런타임 컨테이너 env  — `NEXT_PUBLIC_*` 는 **빌드타임 인라인**이라 런타임 env 와 무관
 *   ✓ **빌드 산출물**(이미지에 구워진 값 · 정적 청크)
 * 그래서 이 락은 env 값이 아니라 **배관의 존재**를 본다 — 값은 환경마다 다르지만
 * 배관은 저장소에 있고, 배관이 없으면 값이 무엇이든 샐 수 없다.
 */
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const PLATFORM_ROOT = join(__dirname, "..", "..", "..", "..");
const KEY = "NEXT_PUBLIC_VWORLD_API_KEY";

/** 배관이 있을 수 있는 자리 — 손으로 고르지 않고 빌드/배포 정의 전부를 본다. */
const PLUMBING_FILES = [
  "Dockerfile.web",
  "docker-compose.yml",
  "docker-compose.prod.yml",
  ".env.example",
];

function readIfExists(rel: string): string | null {
  const p = join(PLATFORM_ROOT, rel);
  return existsSync(p) ? readFileSync(p, "utf8") : null;
}

/** 주석 줄을 뺀 **실행되는 줄**만 남긴다(`#` 주석 — Dockerfile·compose·env 공통). */
function effectiveLines(src: string): string[] {
  return src
    .split("\n")
    .filter((l) => !l.trim().startsWith("#"))
    .filter((l) => l.trim().length > 0);
}

describe("VWorld 공개키 배관이 되살아나지 않는다", () => {
  it("전제: 검사 대상 파일이 실제로 존재한다(공허한 초록 방지)", () => {
    const found = PLUMBING_FILES.filter((f) => readIfExists(f) !== null);
    expect(
      found.length,
      `빌드/배포 정의를 하나도 못 찾았다 — 조회기가 죽었다(찾은 것: ${found.join(", ")})`,
    ).toBeGreaterThan(2);
  });

  it(`★${KEY} 배관이 실행되는 줄에 없다`, () => {
    const violations: string[] = [];
    for (const f of PLUMBING_FILES) {
      const src = readIfExists(f);
      if (src === null) continue;
      for (const line of effectiveLines(src)) {
        if (line.includes(KEY)) violations.push(`${f}: ${line.trim()}`);
      }
    }
    expect(
      violations,
      `공개키 배관이 되살아났다 — 값을 넣는 순간 브라우저 번들로 인라인된다:\n${violations.join("\n")}`,
    ).toEqual([]);
  });

  it("대조군: 살아 있는 다른 NEXT_PUBLIC 배관은 위반으로 잡히지 않는다", () => {
    // ★위양성도 결함이다. 이 락은 "NEXT_PUBLIC 전부 금지"가 아니라 **VWorld 키만** 막는다.
    //   대조군이 0 이면 두 모집단이 갈리지 않아 이 락은 아무것도 구분하지 못한다.
    const compose = readIfExists("docker-compose.yml") ?? "";
    const liveOtherPublic = effectiveLines(compose).filter(
      (l) => l.includes("NEXT_PUBLIC_") && !l.includes(KEY),
    );
    expect(
      liveOtherPublic.length,
      "다른 NEXT_PUBLIC 배관이 0 건 — 대조군이 없어 이 락이 무엇을 구분하는지 알 수 없다",
    ).toBeGreaterThan(0);
  });

  it("★클라이언트 코드가 이 키를 읽지 않는다 (배관을 지운 근거)", () => {
    // 배관 제거의 전제는 "소비처 0" 이다. 그 전제가 깨지면 화면이 조용히 죽으므로
    // 배관보다 **소비처**를 먼저 잠근다.
    const webRoot = join(__dirname, "..", "..");
    const stack: string[] = [join(webRoot, "app"), join(webRoot, "components"), join(webRoot, "lib")];
    const readers: string[] = [];
    while (stack.length) {
      const dir = stack.pop() as string;
      let entries: string[] = [];
      try {
        entries = readdirSync(dir);
      } catch {
        continue;
      }
      for (const e of entries) {
        const p = join(dir, e);
        if (statSync(p).isDirectory()) {
          if (e !== "node_modules") stack.push(p);
          continue;
        }
        if (!/\.(ts|tsx)$/.test(p) || /\.(test|spec)\.tsx?$/.test(p)) continue;
        const src = readFileSync(p, "utf8");
        // `process.env.NEXT_PUBLIC_VWORLD_API_KEY` 로 **읽는** 코드만 위반이다
        // (주석·문자열 언급은 아니다 — 이 파일 자신도 이름을 언급한다).
        if (new RegExp(`process\\.env\\.${KEY}`).test(src)) readers.push(p);
      }
    }
    expect(
      readers,
      `배관을 지웠는데 이 키를 읽는 코드가 있다 — 화면이 조용히 죽는다:\n${readers.join("\n")}`,
    ).toEqual([]);
  });
});
