/**
 * 완성도 셀렉터의 **두 축**을 따로 잠근다 — 원리(런타임)와 배선(소스).
 *
 * ★왜(2026-08-27 독립 리뷰 MAJOR-1): `useShallow` 를 지우면 이 화면이 **무한 리렌더로 죽는데**
 *   `tsc` EXIT 0 · vitest 전부 초록 · lint 무반응이었다. 유일하게 이 컴포넌트를 임포트하는
 *   테스트는 `vi.mock` 으로 통째 대체하므로 **어떤 테스트도 셀렉터를 렌더하지 않았다.**
 *   그리고 계획서 §3「검증하지 못한 것」에도 적히지 않았다 — 무잠금인 줄도 몰랐다.
 */
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useShallow } from "zustand/react/shallow";
import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";
import ts from "typescript";

import {
  useProjectContextStore,
  selectFeasibilityCompletenessInputs,
  computeFeasibilityCompleteness,
} from "@/store/useProjectContextStore";

/** ★처방 형태 그대로 — 객체 셀렉터 + `useShallow`. */
function WithShallow() {
  const i = useProjectContextStore(useShallow(selectFeasibilityCompletenessInputs));
  return <span>{`pct:${computeFeasibilityCompleteness(i).pct}`}</span>;
}
/** ★대조군 — 같은 셀렉터를 `useShallow` **없이**. 매 렌더 새 객체라 스냅샷이 안 캐시된다. */
function WithoutShallow() {
  const i = useProjectContextStore(selectFeasibilityCompletenessInputs);
  return <span>{`pct:${computeFeasibilityCompleteness(i).pct}`}</span>;
}

describe("원리 — `useShallow` 가 무한 리렌더를 막는다(두 모집단)", () => {
  it("★`useShallow` 를 붙이면 정상 렌더된다", () => {
    const { container } = render(<WithShallow />);
    expect(container.textContent).toMatch(/^pct:\d+$/);
  });

  it("★`useShallow` 를 빼면 **던진다** — 이 대조가 없으면 위 검사가 공허하다", () => {
    // 한쪽만 단언하면 "아무것도 안 하는 구현"도 초록이다(파티션형으로 건다).
    expect(() => render(<WithoutShallow />)).toThrow(/Maximum update depth|getSnapshot/);
  });
});

/**
 * 배선 — **저장소 어디든** 이 셀렉터를 스토어에 넘길 때 `useShallow` 를 거친다.
 * ★목록형이 아니다: 모집단을 `git ls-files` 로 파생하므로 **새 소비처가 자동으로** 감시망에 든다.
 * ★판정은 정규식이 아니라 **AST** 다 — 주석·문자열에 뚫리지 않는다.
 */
const REPO_FILES = execSync("git ls-files '*.ts' '*.tsx'", { encoding: "utf8", maxBuffer: 1 << 26 })
  .split("\n")
  .filter((f) => f && !f.includes("__tests__") && !/\.test\.tsx?$/.test(f) && !f.startsWith("e2e/"));

const SELECTOR = "selectFeasibilityCompletenessInputs";

/** `useXStore(<arg>)` 의 `<arg>` 가 셀렉터를 **감싸지 않고 그대로** 넘기는 자리. */
function bareSelectorCalls(file: string, src: string): string[] {
  const sf = ts.createSourceFile(file, src, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX);
  const out: string[] = [];
  const visit = (n: ts.Node): void => {
    if (ts.isCallExpression(n) && ts.isIdentifier(n.expression) && /^use[A-Z]\w*Store$/.test(n.expression.text)) {
      const arg = n.arguments[0];
      if (arg && ts.isIdentifier(arg) && arg.text === SELECTOR) {
        out.push(`${file}:${sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1}`);
      }
    }
    ts.forEachChild(n, visit);
  };
  visit(sf);
  return out;
}
/** 감싸서 넘기는 정상 자리 — **양성 대조군**(0이면 위 검사가 공허하다). */
function wrappedSelectorCalls(file: string, src: string): string[] {
  const sf = ts.createSourceFile(file, src, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX);
  const out: string[] = [];
  const visit = (n: ts.Node): void => {
    if (ts.isCallExpression(n) && ts.isIdentifier(n.expression) && n.expression.text === "useShallow") {
      const arg = n.arguments[0];
      if (arg && ts.isIdentifier(arg) && arg.text === SELECTOR) {
        out.push(`${file}:${sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1}`);
      }
    }
    ts.forEachChild(n, visit);
  };
  visit(sf);
  return out;
}

describe("배선 — 소비처가 늘어도 자동으로 감시망에 든다(파생형)", () => {
  const scanned = REPO_FILES.map((f) => ({ f, src: readFileSync(f, "utf8") }))
    .filter(({ src }) => src.includes(SELECTOR));

  it("★양성 대조군 — 감싸서 넘기는 자리가 실재한다(0이면 아래가 공허하다)", () => {
    const wrapped = scanned.flatMap(({ f, src }) => wrappedSelectorCalls(f, src));
    expect(wrapped.length, "이 셀렉터를 쓰는 소비처가 사라졌다 — 검사가 아무것도 안 본다").toBeGreaterThan(0);
  });

  it("★맨몸으로 넘기는 자리가 없다 — 있으면 그 화면이 무한 리렌더로 죽는다", () => {
    const bare = scanned.flatMap(({ f, src }) => bareSelectorCalls(f, src)).sort();
    expect(bare, "`useShallow` 로 감싸라 — 객체를 돌려주는 셀렉터는 매 렌더 새 참조다").toEqual([]);
  });
});
