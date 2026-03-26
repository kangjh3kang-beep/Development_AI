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

function getFocusableElements(container: HTMLElement) {
  return Array.from(
    container.querySelectorAll<HTMLElement>(focusableSelector),
  ).filter((element) => {
    return !element.hasAttribute("disabled") && element.offsetParent !== null;
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
