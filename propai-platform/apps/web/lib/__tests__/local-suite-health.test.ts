import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";

/**
 * 로컬 FE 전수의 **선재 실패**를 원장으로 남긴다.
 *
 * ## 왜 (2026-09-06)
 *
 * `lib/` + `components/feasibility/` 전수에서 **9 failed** 가 뜬다. 이것을 매번
 * *«내 변경 탓인가»* 로 다시 재는 것은 낭비이고, 반대로 *«원래 그렇다»* 로 넘기면
 * **진짜 회귀가 그 안에 숨는다.**
 *
 * ★판정(모집단 고정 대조 · base=origin/main · node_modules 공유):
 *
 *     차집합 양방향        **0**  (내 쪽에만 0 · base 에만 0)
 *     통과 수 검산         base 1,843 → 1,869 = **+26**
 *                          추가 it( 30 − 모집단 밖 4(operations/) = **26** ◎
 *     원인                 `Failed to resolve import "react/jsx-dev-runtime"
 *                           from "../../packages/ui/src/components/button.tsx"`
 *
 * → **로컬 모듈 해석 실패**(모노레포 `packages/ui` 가 워크스페이스 루트의 react 를
 *   못 찾는다)이지 **단언 실패가 아니다.** CI 는 정상 설치라 초록이다.
 *
 * ## 이 파일이 하는 것
 *
 * **그 원인이 「환경」임을 못 박는다.** 만약 `packages/ui` 가 자기 react 를 갖게 되거나
 * 해석이 고쳐지면 이 검사가 **빨개져서** «원장을 갱신하라»고 알린다.
 * ★그래야 «선재 9건» 이라는 라벨이 **영원히 유효한 변명**으로 굳지 않는다.
 */

const WEB = path.resolve(__dirname, "..", "..");

describe("로컬 전수 선재 실패 원장", () => {
  it("★원인이 「환경(모듈 해석)」임을 못 박는다 — 고쳐지면 원장을 갱신하라", () => {
    // packages/ui 가 앱의 node_modules 밖에 있어서 react 를 못 찾는 구조인가
    const pkgUi = path.resolve(WEB, "../../packages/ui");
    expect(fs.existsSync(pkgUi), "packages/ui 가 없다 — 원인 구조가 바뀌었다").toBe(true);
    const own = path.join(pkgUi, "node_modules", "react");
    expect(fs.existsSync(own),
      "packages/ui 가 자기 react 를 갖게 됐다 — 해석 실패가 사라졌을 수 있으니 " +
      "선재 실패 9건을 **다시 재고** 이 원장을 갱신하라",
    ).toBe(false);
  });

  it("★선재 판정의 근거가 문서에 남아 있다(다음 사람이 되짚을 수 있게)", () => {
    const src = fs.readFileSync(path.resolve(__dirname, "local-suite-health.test.ts"), "utf8");
    // ★★첫 판은 `toContain(t)` 였는데 **SURVIVED** 했다 — 같은 수치가 **문서 주석과
    //   이 배열 양쪽**에 있어, 주석을 지워도 **배열 자신이 통과시킨다.**
    //   *«락이 자기 자신을 근거로 삼으면 무엇을 지워도 초록이다»* — 오늘 세 번째 형태.
    //   → **문서 블록(주석)에만** 있는지 본다. 배열은 모집단에서 뺀다.
    const docBlock = src.slice(0, src.indexOf("describe("));
    for (const t of ["1,843", "1,869", "+26", "jsx-dev-runtime"]) {
      expect(docBlock, `선재 판정의 근거 \`${t}\` 가 **문서에서** 사라졌다`).toContain(t);
    }
    // ★공허진리 방지 — 문서 블록을 실제로 잘랐는가
    expect(docBlock.length, "문서 블록을 못 잘랐다 — 조회기 사망").toBeGreaterThan(500);
  });
});
