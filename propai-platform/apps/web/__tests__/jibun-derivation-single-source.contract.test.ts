/**
 * 지번 **파생**은 `lib/pnu.ts` 한 곳에서만 한다 — **4벌째를 원천 차단한다.**
 *
 * ## 왜 생겼나 (2026-08-21 · 지번 실종 7세대)
 *
 * 같은 필지가 화면마다 다르게 보였다. 원인은 데이터가 아니라 **표시 구현이 세 벌**이었고,
 * 그중 하나(`preferredEntryAddress`)는 **`pnu` 를 매개변수로 받지도 않았다**:
 *
 *   · `parcelDisplayAddress(address, pnu)` — 파생 ○
 *   · `joinAddressJibun(addr, jibun, …)`   — 결합 ○
 *   · `preferredEntryAddress(e)`           — 파생 ✗   ← 인테이크 목록·통합분석 payload
 *
 * `#719` 는 주석에 *"구현 두 벌 금지"* 라고 **적기만 했다.** 글로 적은 규칙은 다음 사람을
 * 막지 못한다 — 표시층 수정이 **여섯 번** 반복된 이유다.
 *
 * ## 무엇을 잠그나
 *
 * 지번 파생의 **원시 연산**은 `jibunFromPnu`(PNU 19자리 → 본번-부번, 산 접두) 하나뿐이다.
 * 이것을 `lib/pnu.ts` **밖에서** 부르는 순간 그것이 곧 **네 번째 구현**이다.
 * 그래서 "밖에서 쓰지 않는다"를 잠근다. 라벨이 필요하면 `parcelDisplayAddress` ·
 * `parcelShortLabel` · `joinAddressJibun` **중 하나를 쓰라**는 뜻이다.
 *
 * ★소스 문자열 검사가 아니라 **구문(AST)** 으로 본다 — 주석·문자열에 뚫리지 않는다
 *   (이 저장소가 그 변이로 두 번 관통당했다).
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve, sep } from "node:path";

import ts from "typescript";
import { describe, expect, it } from "vitest";

const ROOT = resolve(process.cwd());
const ROOTS = ["components", "app", "lib", "store"];
/** 파생 원시함수를 **정당하게** 소유한 단일 모듈. */
const OWNER = join("lib", "pnu.ts");
const PRIMITIVE = "jibunFromPnu";

const TEST_FILE = /(^|[\\/])__tests__[\\/]|\.(test|spec)\.tsx?$/;

function walk(dir: string, out: string[] = []): string[] {
  let names: string[];
  try { names = readdirSync(dir); } catch { return out; }
  for (const name of names) {
    if (name === "node_modules" || name.startsWith(".")) continue;
    const full = join(dir, name);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (/\.tsx?$/.test(name) && !TEST_FILE.test(full)) out.push(full);
  }
  return out;
}

/** 이 파일이 **코드로**(주석·문자열 아님) 그 식별자를 참조하는가. */
function referencesIdentifier(src: string, file: string, name: string): boolean {
  const sf = ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true);
  let hit = false;
  const visit = (n: ts.Node) => {
    if (hit) return;
    if (ts.isIdentifier(n) && n.text === name) { hit = true; return; }
    ts.forEachChild(n, visit);
  };
  ts.forEachChild(sf, visit);
  return hit;
}

const files = ROOTS.flatMap((r) => walk(join(ROOT, r)))
  .map((f) => ({ rel: relative(ROOT, f), src: readFileSync(f, "utf8") }));

describe("지번 파생 단일 출처", () => {
  it("스캐너가 살아 있다(공허한 참 방지)", () => {
    // ★이 하한이 없으면 "위반 0"이 참인 이유가 "대상 0개"일 수 있다.
    expect(files.length).toBeGreaterThan(200);
    // ★대조군 — 정당한 소유자는 실제로 이 원시함수를 **쓰고 있어야** 한다.
    //   (소유자마저 안 쓰면 식별자 이름이 바뀐 것이고, 아래 위반검사는 공허해진다.)
    const owner = files.find((f) => f.rel === OWNER || f.rel.endsWith(sep + OWNER));
    expect(owner, `${OWNER} 를 찾지 못했다 — 경로가 바뀌었나`).toBeDefined();
    expect(referencesIdentifier(owner!.src, owner!.rel, PRIMITIVE)).toBe(true);
  });

  it(`${PRIMITIVE} 을 ${OWNER} 밖에서 쓰지 않는다 — 그것이 곧 네 번째 구현이다`, () => {
    const violators = files
      .filter((f) => !(f.rel === OWNER || f.rel.endsWith(sep + OWNER)))
      .filter((f) => referencesIdentifier(f.src, f.rel, PRIMITIVE))
      .map((f) => f.rel);

    expect(violators, [
      "지번을 **직접 파생**하는 코드가 lib/pnu.ts 밖에 생겼다.",
      "그것이 네 번째 표시 구현이고, 화면마다 지번이 갈리는 결함이 여기서 다시 시작된다.",
      "라벨이 필요하면 parcelDisplayAddress · parcelShortLabel · joinAddressJibun 중 하나를 쓰라.",
      "정말 새 파생 규칙이 필요하면 lib/pnu.ts 안에 두고 이 목록이 아니라 그 파일을 늘려라.",
    ].join("\n")).toEqual([]);
  });
});
