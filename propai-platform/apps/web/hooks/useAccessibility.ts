"use client";

import {
  useCallback,
  useMemo,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import {
  type AnnouncementMode,
  useAccessibilityAnnouncer,
} from "@/components/ui/AccessibilityProvider";

const focusableSelector = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(", ");

/**
 * 컨테이너 안의 포커스 가능 요소.
 *
 * ## ★2026-08-22 — `offsetParent !== null` 을 걷어냈다(실제 결함)
 *
 * 종전 필터는 가시성 판정에 `offsetParent` 를 썼는데, **`position: fixed` 요소는 사양상
 * `offsetParent` 가 `null`** 이다(MDN: *"returns null when the element has position: fixed"*).
 * 모달은 대부분 fixed 다 — 즉 **이 함수가 정확히 자기 사용처에서 0개를 돌려줬다.**
 * 그러면 `trapFocus` 는 `preventDefault()` 만 하고 끝나 **Tab 이 순환하는 게 아니라
 * 아예 죽는다**(키보드 사용자가 모달 안에서 이동조차 못 한다). jsdom 만의 문제가 아니다.
 *
 * ★그래서 가시성 대신 **접근성 트리에서 빠졌는가**로 판정한다 — `disabled` · `hidden` ·
 *   `aria-hidden="true"`. 이 셋은 fixed 여부와 무관하고 jsdom 에서도 관측 가능하다.
 * ★한계를 밝힌다: `display:none` 조상으로 가려진 요소는 여기서 못 거른다(레이아웃이 필요).
 *   실무상 모달 내부는 열렸을 때 보이므로 수용하고, 대신 **틀린 판정으로 Tab 을 죽이는
 *   쪽**(종전)이 아니라 **여분을 포함하는 쪽**으로 실패한다.
 */
function getFocusableElements(container: HTMLElement) {
  return Array.from(
    container.querySelectorAll<HTMLElement>(focusableSelector),
  ).filter((element) => {
    if (element.hasAttribute("disabled")) return false;
    if (element.hidden) return false;
    if (element.getAttribute("aria-hidden") === "true") return false;
    return true;
  });
}

export function trapFocus(
  container: HTMLElement,
  event: KeyboardEvent | ReactKeyboardEvent<HTMLElement>,
) {
  if (event.key !== "Tab") {
    return;
  }

  const focusableElements = getFocusableElements(container);

  if (focusableElements.length === 0) {
    event.preventDefault();
    return;
  }

  const firstElement = focusableElements[0];
  const lastElement = focusableElements[focusableElements.length - 1];
  const currentElement = document.activeElement;

  // ★포커스가 **컨테이너 밖**에 있으면 되돌린다(2026-08-22 추가).
  //
  //   종전엔 이 가지가 없어서, 현재 요소가 첫째도 마지막도 아니면 `preventDefault` 도
  //   이동도 하지 않고 **네이티브 Tab 이 그대로 나갔다.** 그러면 트랩이 뚫린다.
  //
  //   포커스가 컨테이너 밖으로 나가는 건 예외 상황이 아니라 **평범한 조작**이다:
  //     · 모달 안의 **글자를 마우스로 클릭**하면(버튼이 아닌 곳) 포커스가 `<body>` 로 간다
  //     · 포커스를 갖고 있던 요소가 **조건부 렌더로 사라지면**(예: 저장 성공 후 입력창이
  //       사라지고 "닫기"만 남는 화면) 그 순간 `activeElement` 가 `<body>` 가 된다
  //   그 뒤 Tab 한 번이면 배경 페이지로 빠져나갔다 — 계약이 *"가둔다"* 라고 말하는데
  //   실제로는 안 가두고 있었다.
  if (!container.contains(currentElement)) {
    event.preventDefault();
    (event.shiftKey ? lastElement : firstElement).focus();
    return;
  }

  if (event.shiftKey && currentElement === firstElement) {
    event.preventDefault();
    lastElement.focus();
    return;
  }

  if (!event.shiftKey && currentElement === lastElement) {
    event.preventDefault();
    firstElement.focus();
  }
}

export function useAccessibility() {
  const { announce } = useAccessibilityAnnouncer();

  const announceToScreenReader = useCallback(
    (message: string, mode: AnnouncementMode = "polite") => {
      announce(message, mode);
    },
    [announce],
  );

  return useMemo(
    () => ({
      announceToScreenReader,
      trapFocus,
    }),
    [announceToScreenReader],
  );
}
