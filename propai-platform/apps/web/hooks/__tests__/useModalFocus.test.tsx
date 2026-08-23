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

  it("★두 번째로 열면 **그때 누른 요소**로 돌아온다 — 복귀 대상 리셋(무잠금이었다)", () => {
    // `restoreRef.current = null` 리셋(useModalFocus)이 잠겨 있지 않았다. 그 줄이 없으면
    // **처음 열 때 누른 버튼**이 영원히 복귀 대상으로 박힌다.
    // 실사용 재현: 목록에서 A의 삭제 → 취소 → B의 삭제 → 취소 → **포커스가 A로 간다.**
    function TwoOpeners() {
      const [open, setOpen] = useState(false);
      const ref = useRef<HTMLDivElement>(null);
      useModalFocus(ref, open);
      return (
        <div>
          <button type="button" data-testid="openA" onClick={() => setOpen(true)}>A</button>
          <button type="button" data-testid="openB" onClick={() => setOpen(true)}>B</button>
          {open && (
            <div ref={ref} role="dialog" tabIndex={-1}>
              <button type="button" data-testid="close" onClick={() => setOpen(false)}>닫기</button>
            </div>
          )}
        </div>
      );
    }
    render(<TwoOpeners />);
    const a = screen.getByTestId("openA");
    const b = screen.getByTestId("openB");

    a.focus();
    fireEvent.click(a);
    fireEvent.click(screen.getByTestId("close"));
    expect(document.activeElement, "첫 번째 복귀부터 틀렸다(픽스처 전제)").toBe(a);

    b.focus();
    fireEvent.click(b);
    fireEvent.click(screen.getByTestId("close"));
    expect(
      document.activeElement,
      "두 번째로 열었는데 **첫 번째** 버튼으로 돌아갔다 — 복귀 대상이 리셋되지 않는다",
    ).toBe(b);
  });

  it("★★컨테이너 **밖**에 포커스가 있어도 Tab 이 모달을 탈출하지 않는다", () => {
    // 모달 안의 글자를 마우스로 클릭하거나, 포커스를 갖던 요소가 조건부 렌더로 사라지면
    // `activeElement` 가 `<body>` 가 된다. 종전 `trapFocus` 는 현재 요소가 첫째도 마지막도
    // 아니면 **아무것도 하지 않아** 네이티브 Tab 이 그대로 배경으로 나갔다.
    render(<Harness />);
    (document.activeElement as HTMLElement | null)?.blur();
    expect(document.activeElement, "픽스처 전제: 포커스가 밖으로 나가 있어야 한다").toBe(
      document.body,
    );

    fireEvent.keyDown(document, { key: "Tab" });
    expect(
      document.activeElement,
      "포커스가 밖에 있을 때 Tab 이 모달로 회수되지 않는다 — 트랩이 뚫린다",
    ).toBe(screen.getByTestId("first"));
  });

  it("★역방향도 회수한다 — 경계는 한 쌍이다(§D.19)", () => {
    render(<Harness />);
    (document.activeElement as HTMLElement | null)?.blur();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement, "Shift+Tab 회수가 없다").toBe(screen.getByTestId("close"));
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


// ── ★중첩 트랩 (2026-08-23 · `AuctionWorkspace` 라이트박스에서 드러났다) ──────────
//
//  모달 안에서 또 하나가 열리는 표면이 있다(상세 모달 > 사진 확대 라이트박스).
//  안쪽이 **바깥 DOM 안에** 렌더되면 바깥의 `focusables` 는 안쪽 것까지 포함한다.
//
//  ★그래서 안쪽 마지막이 **바깥 마지막이 아닐 때만 우연히 동작한다** — 즉 레이아웃이
//    바뀌면 뚫린다. 실제로 `AuctionWorkspace` 전용 스펙만으로는 이 규칙을 지워도 초록이었다
//    (변이가 잡았다: 안쪽 뒤에 포커스 가능 요소가 더 있어 바깥이 경계에 닿지 않았다).
//    → **최악 배치**(안쪽 마지막 = 바깥 마지막)를 여기서 결정론적으로 태운다.

function NestedHarness({ inner }: { inner: boolean }) {
  const outerRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  useModalFocus(outerRef, true);
  useModalFocus(innerRef, inner);
  return (
    <div ref={outerRef} role="dialog" tabIndex={-1}>
      <button type="button" data-testid="o-first">바깥 첫</button>
      <button type="button" data-testid="o-mid">바깥 중간</button>
      {/* ★안쪽을 **맨 뒤**에 둔다 — 안쪽 마지막이 곧 바깥 마지막이 되는 최악 배치다. */}
      {inner && (
        <div ref={innerRef} role="dialog" aria-label="안쪽" tabIndex={-1}>
          <button type="button" data-testid="i-first">안쪽 첫</button>
          <button type="button" data-testid="i-last">안쪽 끝</button>
        </div>
      )}
    </div>
  );
}

describe("useModalFocus — 중첩 트랩", () => {
  it("★★바깥이 **한 번도 포커스를 만지지 않는다** — 결과가 같아도 경로가 다르다", () => {
    // ★이 케이스가 없으면 양보 규칙이 **잠기지 않는다**(변이로 실증: 규칙을 지워도 초록).
    //   이유는 안쪽 훅의 *"포커스가 컨테이너 밖이면 회수한다"* 분기가 결과를 **되돌려 놓기**
    //   때문이다 — 양보가 없으면 바깥이 먼저 `o-first` 로 옮기고, 안쪽이 그걸 다시 끌어온다.
    //   최종 위치는 같지만 그 사이에 **배경 요소가 focus 를 받는다**(onFocus 핸들러 발화·
    //   스크린리더 낭독·`:focus-visible` 깜빡임). 결과가 아니라 **경로**를 본다.
    render(<NestedHarness inner />);
    const oFirst = screen.getByTestId("o-first");
    const oMid = screen.getByTestId("o-mid");
    let touched = 0;
    const spy = () => { touched += 1; };
    oFirst.addEventListener("focus", spy);
    oMid.addEventListener("focus", spy);

    screen.getByTestId("i-last").focus();
    fireEvent.keyDown(document, { key: "Tab" });

    expect(
      touched,
      "안쪽에 갇혀 있는데 배경 모달 요소가 포커스를 받았다 — 바깥 트랩이 끼어들었다",
    ).toBe(0);
    // ★공허 진리 방지 — 스파이가 아예 안 붙는 구현에서도 0 이다. 대상이 살아 있는지 본다.
    oFirst.focus();
    expect(touched, "스파이가 발화하지 않는다 — 이 케이스는 아무것도 안 본다").toBe(1);
    oFirst.removeEventListener("focus", spy);
    oMid.removeEventListener("focus", spy);
  });

  it("★안쪽이 열리면 **안쪽**이 소유권을 갖는다 — 최악 배치에서도 바깥이 가로채지 않는다", () => {
    render(<NestedHarness inner />);
    const iLast = screen.getByTestId("i-last");
    iLast.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    // 양보가 없으면 바깥이 "마지막 → 첫"으로 돌려 `o-first` 가 된다.
    expect(
      document.activeElement,
      "안쪽 마지막에서 Tab 이 바깥 첫 요소로 갔다 — 중첩 양보가 죽었다",
    ).toBe(screen.getByTestId("i-first"));
  });

  it("★대조군 — 안쪽이 없으면 바깥이 정상적으로 가둔다(양보가 바깥을 죽이지 않는다)", () => {
    render(<NestedHarness inner={false} />);
    const oMid = screen.getByTestId("o-mid");
    oMid.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(
      document.activeElement,
      "안쪽이 없는데 바깥 트랩이 돌지 않았다 — 양보 규칙이 바깥을 통째로 껐다",
    ).toBe(screen.getByTestId("o-first"));
  });

  it("★포커스가 바깥으로 새면 **안쪽이 회수한다** — 양보가 회수까지 끄지 않는다", () => {
    // ★처음엔 *"포커스가 바깥에 있으면 소유권도 바깥"* 이라고 적었다가 **실측에 반증됐다**.
    //   안쪽이 열려 있는 동안에는 그것이 최상위 모달이므로, 밖으로 샌 포커스는 **회수**하는
    //   것이 옳다(모달 의미론). 양보 규칙은 *"안쪽에 포커스가 있을 때 바깥이 끼어들지 않는다"*
    //   는 뜻이지, *"안쪽이 회수를 포기한다"* 는 뜻이 아니다 — 두 조건을 갈라 둔다.
    render(<NestedHarness inner />);
    screen.getByTestId("o-mid").focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(
      document.activeElement,
      "라이트박스가 열려 있는데 포커스가 뒤쪽 모달에 남았다",
    ).toBe(screen.getByTestId("i-first"));
  });
});
