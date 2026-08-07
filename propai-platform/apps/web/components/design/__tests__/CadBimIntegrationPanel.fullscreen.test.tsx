/**
 * CAD·BIM 전체화면 **조건 배선** 계약.
 *
 * ★왜 따로 필요한가 — 층위 사다리 계약(`__tests__/layer-ladder.contract.test.tsx`)은
 *   이 파일 텍스트에 `z-[9990]` 이 **존재하는지**만 본다(소스 grep). 그래서 독립 변이
 *   검증에서 `fullscreen ?` → `!fullscreen ?` **조건 반전이 생존**했다 — 문자열은 엉뚱한
 *   분기에 그대로 남아 검사를 통과하기 때문이다.
 *
 *   결과는 사용자가 바로 겪는 버그다: 전체화면 버튼을 누르면 오히려 줄어들고, 평상시에
 *   전체화면 상태가 된다. **그걸 잡는 테스트가 하나도 없었다.**
 *
 * ★소스 검사로는 원리적으로 못 잡는다(조건을 뒤집어도 토큰 구성은 같다).
 *   그래서 실제로 **렌더하고 토글해서** 무엇이 붙고 떨어지는지 본다.
 *
 * ★★R1 봉합 — 첫 판은 **문서 전역에서 `z-[9990]` 개수만** 셌다. 그 오라클은 그 1개가
 *   *어느 요소*에서 왔는지 묻지 않아, 전체화면 조건을 죽이고 z 를 **버튼에 옮기면**
 *   0→1→0 이 그대로 성립했다(전체화면이 완전히 죽었는데 전수 1901 초록). 게다가
 *   **전체화면을 만드는 실체는 기하**(`fixed inset-0 h-screen w-screen`)인데 그건 아예
 *   보지 않아, 기하를 걷어내거나 `hidden` 을 붙여도 살아남았다.
 *
 *   내가 이 PR 에서 **새로 추가한 규율 20**("처방을 적용한 범위 = 결함이 사는 범위인지
 *   확인하라")을 그 PR 안에서 어긴 것이다. 그래서 오라클을 **버튼이 사는 래퍼에 결속**하고
 *   z·기하·가시성을 함께 본다.
 */
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CadBimIntegrationPanel } from "@/components/design/CadBimIntegrationPanel";
import { SATONG_CONTENT_Z } from "@/lib/satong-map-z";

// ★계약 상수에 결속한다(리터럴로 적으면 계약값이 바뀌어도 옛 값을 조용히 본다).
const FULLSCREEN_Z = `z-[${SATONG_CONTENT_Z.appFullscreen}]`;

// ★z 하나만 보면 "클래스는 붙었는데 전체화면이 아닌" 상태를 놓친다. 뷰포트를 덮는 실체는
//   이 기하 토큰들이다 — 실제로 이걸 안 보던 판이 기하 제거 변이에 뚫렸다.
const GEOMETRY = ["fixed", "inset-0", "h-screen", "w-screen"];

/** 전체화면 클래스를 받는 **그 요소** — 토글 버튼의 직계 부모(뷰포트 래퍼)다. */
function viewport(): HTMLElement {
  const el = screen.getByTestId("cadbim-fullscreen").parentElement;
  if (!el) throw new Error("전체화면 버튼의 뷰포트 래퍼를 찾지 못했다 — 구조가 바뀌었다");
  return el;
}

describe("CAD·BIM 전체화면 — 조건 배선", () => {
  it("★평상시엔 아니고, 토글하면 뷰포트를 실제로 덮는다(조건 반전·기하 소실 감지)", () => {
    render(<CadBimIntegrationPanel projectId="test-project" dictionary={{}} />);

    const button = screen.getByTestId("cadbim-fullscreen");
    // ★공허 진리 방지 — 버튼이 실제로 있고 초기 상태가 '꺼짐'이어야 이 검사가 의미를 갖는다.
    expect(button).toHaveAttribute("aria-pressed", "false");
    expect(viewport().className).not.toContain(FULLSCREEN_Z);

    fireEvent.click(button);

    expect(screen.getByTestId("cadbim-fullscreen")).toHaveAttribute("aria-pressed", "true");
    const on = viewport().className.split(/\s+/);
    expect(on).toContain(FULLSCREEN_Z);
    for (const token of GEOMETRY) expect(on).toContain(token);
    expect(on).not.toContain("hidden");
    // 계약 z 를 다른 요소로 옮겨 이 검사를 만족시키는 우회를 막는다.
    expect(document.querySelectorAll(`[class*="${FULLSCREEN_Z}"]`)).toHaveLength(1);

    // 되돌리면 사라져야 한다 — 한 방향만 보면 "항상 켜짐" 변이를 놓친다.
    fireEvent.click(screen.getByTestId("cadbim-fullscreen"));
    expect(viewport().className).not.toContain(FULLSCREEN_Z);
    expect(document.querySelectorAll(`[class*="${FULLSCREEN_Z}"]`)).toHaveLength(0);
  });

  // ★jsdom 으로는 닫을 수 없는 것을 초록 안에 남긴다(규율 13 — 무잠금과 미수정을 섞지 않는다).
  //   `/projects/[id]/cad`·`/bim` 은 framer-motion 의 `transform` 이 **컨테이닝 블록**을
  //   만들어 `fixed` 가 뷰포트가 아닌 그 조상 기준이 될 수 있다. 레이아웃이 없는 jsdom 은
  //   이걸 원리적으로 판정하지 못한다 — 실제 브라우저 검증이 필요하다.
  it.todo("★`/projects/[id]/cad`·`/bim` 에서 전체화면이 뷰포트 기준인지(브라우저 검증 필요)");
});
