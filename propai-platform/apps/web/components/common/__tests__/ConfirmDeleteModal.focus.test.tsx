/**
 * 실제 모달 표면에서 포커스 생명주기가 **작동한다** — 훅이 소비처 0 이 되지 않게.
 *
 * ★`trapFocus` 는 만들어 두고 **아무도 안 써서** 결함(offsetParent)이 드러나지 않았다.
 *   같은 실수를 반복하지 않도록, 훅을 만든 커밋에서 **실제 표면 하나를 태운다**.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDeleteModal } from "@/components/common/ConfirmDeleteModal";

function open() {
  return render(
    <ConfirmDeleteModal
      open
      name="테스트 프로젝트"
      description="되돌릴 수 없습니다."
      onCancel={vi.fn()}
      onConfirm={vi.fn()}
    />,
  );
}

describe("ConfirmDeleteModal — 포커스 생명주기(실표면)", () => {
  it("★autoFocus 대상(확인 입력창)을 **빼앗지 않는다**", () => {
    // ★이 표면은 저자가 입력창에 `autoFocus` 를 걸어 뒀다. 훅이 '첫 포커스 요소'(복사 버튼)로
    //   옮기면 그건 개선이 아니라 **회귀**다 — 사용자가 바로 타이핑할 수 없게 된다.
    open();
    expect(document.activeElement?.tagName).toBe("INPUT");
  });

  it("★Tab 이 모달 안에서 **순환**한다 — 마지막에서 첫 요소로", () => {
    // ★판별력: 훅이 없으면 jsdom 은 Tab 으로 포커스를 옮기지 않으므로 마지막에 머문다.
    //   (초판은 `contains()` 만 봐서 훅을 지워도 통과했다 — autoFocus 때문에 이미 안에 있었다.)
    const { container } = open();
    const dialog = screen.getByRole("dialog");
    const focusables = Array.from(
      dialog.querySelectorAll<HTMLElement>('a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'),
    ).filter((el) => !el.hasAttribute("disabled"));
    expect(focusables.length, "포커스 가능 요소가 없다 — 픽스처가 깨졌다").toBeGreaterThan(1);

    const last = focusables[focusables.length - 1];
    last.focus();
    expect(document.activeElement).toBe(last);
    fireEvent.keyDown(document, { key: "Tab" });
    expect(
      document.activeElement,
      "마지막에서 Tab 했는데 첫 요소로 돌지 않았다 — 트랩이 배선되지 않았다",
    ).toBe(focusables[0]);
    expect(container).toBeTruthy();
  });

  it("★대조군 — Tab 이 아닌 키는 포커스를 옮기지 않는다(판별력)", () => {
    open();
    const before = document.activeElement;
    fireEvent.keyDown(document, { key: "Enter" });
    expect(document.activeElement).toBe(before);
  });
});
