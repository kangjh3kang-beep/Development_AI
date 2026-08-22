/**
 * 모달 포커스 생명주기 — `#697` 이 미룬 부채(착수 시점 **13표면 전부 0/13**).
 *
 * ★`trapFocus` 는 이미 있었는데 **소비처가 0** 이었다. 빠진 것은 알고리즘이 아니라
 *   **생명주기**(언제 잡고 언제 돌려주나)다 — 그래서 감싸기만 한다(구현 두 벌 금지).
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { useRef, useState } from "react";
import { describe, expect, it } from "vitest";

import { useModalFocus } from "@/hooks/useModalFocus";

function Harness({ startOpen = true }: { startOpen?: boolean }) {
  const [open, setOpen] = useState(startOpen);
  const ref = useRef<HTMLDivElement>(null);
  useModalFocus(ref, open);
  return (
    <div>
      <button type="button" data-testid="opener" onClick={() => setOpen(true)}>열기</button>
      {open && (
        <div ref={ref} role="dialog" tabIndex={-1}>
          <button type="button" data-testid="first">첫</button>
          <button type="button" data-testid="mid">중간</button>
          <button type="button" data-testid="last">끝</button>
          <button type="button" data-testid="close" onClick={() => setOpen(false)}>닫기</button>
        </div>
      )}
    </div>
  );
}

describe("useModalFocus", () => {
  it("★열리면 내부 **첫 포커스 가능 요소**로 옮긴다", () => {
    render(<Harness />);
    expect(document.activeElement).toBe(screen.getByTestId("first"));
  });

  it("★Tab 을 모달 안에 가둔다 — 마지막에서 Tab 하면 첫 요소로 돈다", () => {
    render(<Harness />);
    screen.getByTestId("close").focus();          // 내부 마지막 요소
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(screen.getByTestId("first"));
  });

  it("★Shift+Tab 은 첫 요소에서 마지막으로 돈다(역방향)", () => {
    render(<Harness />);
    screen.getByTestId("first").focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(screen.getByTestId("close"));
  });

  it("★대조군 — Tab 이 아닌 키는 포커스를 옮기지 않는다(판별력)", () => {
    render(<Harness />);
    const mid = screen.getByTestId("mid");
    mid.focus();
    fireEvent.keyDown(document, { key: "Enter" });
    fireEvent.keyDown(document, { key: "a" });
    expect(document.activeElement).toBe(mid);
  });

  it("★닫히면 **열기 전** 눌렀던 요소로 돌아간다", () => {
    render(<Harness startOpen={false} />);
    const opener = screen.getByTestId("opener");
    opener.focus();
    fireEvent.click(opener);
    expect(document.activeElement).toBe(screen.getByTestId("first")); // 열림 → 내부로
    fireEvent.click(screen.getByTestId("close"));
    expect(document.activeElement).toBe(opener);                      // 닫힘 → 복귀
  });

  it("★대조군 — 닫혀 있으면 아무것도 하지 않는다(포커스를 훔치지 않는다)", () => {
    render(<Harness startOpen={false} />);
    const opener = screen.getByTestId("opener");
    opener.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(opener);
  });

  it("★★근본 회귀 — `position: fixed` 컨테이너에서도 트랩이 동작한다", () => {
    // 종전 `getFocusableElements` 는 가시성을 `offsetParent !== null` 로 봤는데,
    // **fixed 요소는 사양상 offsetParent 가 null** 이다(MDN). 모달은 대부분 fixed 이므로
    // 이 함수가 **정확히 자기 사용처에서 0개**를 돌려줬고, trapFocus 는 preventDefault 만
    // 하고 끝나 **Tab 이 순환이 아니라 죽었다**. jsdom 만의 문제가 아니다.
    render(<Harness />);
    const dialog = screen.getByRole("dialog");
    dialog.style.position = "fixed";     // 실사용 형태를 재현
    screen.getByTestId("close").focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(
      document.activeElement,
      "fixed 모달에서 Tab 이 순환하지 않는다 — offsetParent 판정이 되살아났나",
    ).toBe(screen.getByTestId("first"));
  });
});

