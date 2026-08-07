/**
 * CAD·BIM 전체화면 **조건 배선** 계약.
 *
 * ★왜 따로 필요한가 — 층위 사다리 계약은 이 파일 텍스트에 `z-[9990]` 이 **존재하는지**만
 *   본다(소스 grep). 그래서 `fullscreen ?` → `!fullscreen ?` **조건 반전이 생존**했다.
 *   사용자가 바로 겪는 버그인데(버튼을 누르면 오히려 줄어들고 평상시에 전체화면)
 *   그걸 잡는 테스트가 하나도 없었다. 소스 검사로는 원리적으로 못 잡는다 — 조건을 뒤집어도
 *   토큰 구성이 같기 때문이다. 그래서 **렌더하고 토글해서** 본다.
 *
 * ★★두 번 연속 "골대만 한 칸 옮긴" 봉합을 했다(적대검증 R1·R2 실증):
 *   ① 문서 전역에서 `z-[9990]` **개수만** 셌다 → 배선을 죽이고 z 를 **버튼에** 붙이면 통과
 *   ② 버튼의 `parentElement` 로 옮겼다 → 버튼만 감싸는 **래퍼를 하나 끼우면** 통과
 *      (전체화면이 완전히 죽은 채 전수 1901 초록)
 *   둘 다 **오라클이 요소가 아니라 "구조상의 위치"에 결속**돼 있어서다. 위치는 변이자가
 *   자유롭게 옮길 수 있다. 그래서 지금은 뷰포트 자신의 `data-testid` 에 결속하고,
 *   그 요소가 **토글 버튼을 품고 있는지**까지 확인한다(testid 를 미끼로 옮기는 우회 차단).
 *
 * ★이 오라클의 천장(면역을 주장하지 않는다 — 규율 C-11):
 *   jsdom 에는 **Tailwind CSS 가 없다.** 유틸리티 클래스의 실효 기하를 `getComputedStyle`
 *   로 해석할 수 없으므로, 여기서 확인 가능한 것은 **토큰의 존재/부재와 인라인 style** 까지다.
 *   `!important` 로 상쇄하거나 CSS 레이어로 무효화하는 형태는 **원리적으로 못 잡는다** —
 *   그건 실제 브라우저 검증의 몫이다(아래 `it.todo`).
 */
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CadBimIntegrationPanel } from "@/components/design/CadBimIntegrationPanel";
import { SATONG_CONTENT_Z } from "@/lib/satong-map-z";

// ★계약 상수에 결속한다(리터럴로 적으면 계약값이 바뀌어도 옛 값을 조용히 본다).
const FULLSCREEN_Z = `z-[${SATONG_CONTENT_Z.appFullscreen}]`;

/**
 * 뷰포트를 덮는 최소 조건. `h-screen w-screen` 은 **`fixed inset-0` 만으로 등가**라
 * 요구하지 않는다 — 요구했더니 그 둘을 지운 **정상적 단순화가 위양성**으로 막혔다.
 */
const GEOMETRY = ["fixed", "inset-0"];

/** 안 보이게 만드는 흔한 표기들. `hidden` 하나만 보면 나머지로 전부 우회된다. */
const INVISIBLE = ["hidden", "invisible", "opacity-0", "scale-0", "pointer-events-none"];

/** 전체화면 클래스를 받는 **그 요소**. 위치가 아니라 자기 식별자로 찾는다. */
function viewport(): HTMLElement {
  return screen.getByTestId("cadbim-viewport");
}
function toggle(): HTMLElement {
  return screen.getByTestId("cadbim-fullscreen");
}

describe("CAD·BIM 전체화면 — 조건 배선", () => {
  it("★평상시엔 아니고, 토글하면 뷰포트가 실제로 화면을 덮는다", () => {
    render(<CadBimIntegrationPanel projectId="test-project" dictionary={{}} />);

    // ★공허 진리 방지 — 버튼이 실제로 있고 초기 상태가 '꺼짐'이어야 이 검사가 의미를 갖는다.
    expect(toggle()).toHaveAttribute("aria-pressed", "false");
    expect(viewport().className).not.toContain(FULLSCREEN_Z);

    fireEvent.click(toggle());

    expect(toggle()).toHaveAttribute("aria-pressed", "true");

    const vp = viewport();
    // ★testid 를 미끼 요소로 옮기는 우회 차단 — 뷰포트는 토글 버튼을 품고 있어야 한다.
    expect(vp).toContainElement(toggle());

    const cls = vp.className.split(/\s+/);
    expect(cls).toContain(FULLSCREEN_Z);
    for (const token of GEOMETRY) expect(cls).toContain(token);
    for (const token of INVISIBLE) expect(cls).not.toContain(token);

    // ★인라인 style 로 클래스를 상쇄하는 우회(이 저장소의 z SSOT 가 인라인 표기를 권장하므로
    //   실제로 일어날 수 있는 형태다) — 계약을 무너뜨리는 값이 박혀 있지 않아야 한다.
    expect(vp.style.display).not.toBe("none");
    expect(vp.style.visibility).not.toBe("hidden");
    expect(vp.style.opacity).not.toBe("0");
    expect(["", "fixed"]).toContain(vp.style.position);

    // 계약 z 를 다른 요소로 옮겨 검사를 만족시키는 우회를 막는다.
    expect(document.querySelectorAll(`[class*="${FULLSCREEN_Z}"]`)).toHaveLength(1);

    // 되돌리면 사라져야 한다 — 한 방향만 보면 "항상 켜짐" 변이를 놓친다.
    fireEvent.click(toggle());
    expect(viewport().className).not.toContain(FULLSCREEN_Z);
    expect(document.querySelectorAll(`[class*="${FULLSCREEN_Z}"]`)).toHaveLength(0);
  });

  // ★jsdom 으로 닫을 수 없는 것을 초록 안에 정직하게 남긴다(규율 13).
  //   사유는 framer-motion 이 아니다 — 그건 재확인 없이 인계문서 문구를 옮겨 적은 것이었고,
  //   실측 결과 `/bim` 에는 framer-motion 이 **아예 없으며** jsdom 도 인라인 transform 은
  //   읽는다. 진짜 사유는 **jsdom 에 Tailwind 가 없다**는 것이다: 위 검사는 토큰 존재까지고,
  //   `!important` 상쇄·CSS 레이어 무효화·조상 `transform` 이 만드는 컨테이닝 블록은
  //   실제 브라우저에서만 판정된다. 이 부채는 이 테스트 **전체**에 걸린다.
  it.todo("★실제 브라우저에서 전체화면이 뷰포트를 덮는지(jsdom 은 Tailwind 를 해석 못 한다)");
});
