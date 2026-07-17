"use client";

import {
  useEffect,
  useId,
  useRef,
  type PropsWithChildren,
  type ReactNode,
} from "react";
import { Button } from "./button";

const focusableSelector = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(", ");

type DialogProps = PropsWithChildren<{
  open: boolean;
  title: string;
  description?: string;
  actions?: ReactNode;
  onClose: () => void;
}>;

export function Dialog({
  open,
  title,
  description,
  actions,
  children,
  onClose,
}: DialogProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const previousActiveRef = useRef<HTMLElement | null>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    if (!open) {
      return;
    }

    previousActiveRef.current = document.activeElement as HTMLElement | null;

    const panelElement = panelRef.current;
    const focusableElements = panelElement
      ? Array.from(
          panelElement.querySelectorAll<HTMLElement>(focusableSelector),
        ).filter((element) => element.offsetParent !== null)
      : [];

    (focusableElements[0] ?? panelElement)?.focus();

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    const handleTab = (event: KeyboardEvent) => {
      if (event.key !== "Tab" || !panelElement) {
        return;
      }

      const tabOrder = Array.from(
        panelElement.querySelectorAll<HTMLElement>(focusableSelector),
      ).filter((element) => element.offsetParent !== null);

      if (tabOrder.length === 0) {
        event.preventDefault();
        panelElement.focus();
        return;
      }

      const firstElement = tabOrder[0];
      const lastElement = tabOrder[tabOrder.length - 1];
      const currentElement = document.activeElement;

      if (event.shiftKey && currentElement === firstElement) {
        event.preventDefault();
        lastElement.focus();
      } else if (!event.shiftKey && currentElement === lastElement) {
        event.preventDefault();
        firstElement.focus();
      }
    };

    window.addEventListener("keydown", handleEscape);
    window.addEventListener("keydown", handleTab);

    return () => {
      window.removeEventListener("keydown", handleEscape);
      window.removeEventListener("keydown", handleTab);
      previousActiveRef.current?.focus();
    };
  }, [onClose, open]);

  if (!open) {
    return null;
  }

  return (
    <div
      aria-modal="true"
      role="dialog"
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(19,33,47,0.35)] p-4"
      onClick={onClose}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        className="w-full max-w-xl rounded-[var(--r-panel)] border border-[var(--line)] bg-[var(--surface-strong)] p-6 shadow-[0_24px_80px_rgba(19,33,47,0.18)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2
              id={titleId}
              className="text-xl font-semibold text-[var(--foreground)]"
            >
              {title}
            </h2>
            {description ? (
              <p
                id={descriptionId}
                className="mt-2 text-sm leading-7 text-[rgba(19,33,47,0.72)]"
              >
                {description}
              </p>
            ) : null}
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            닫기
          </Button>
        </div>
        <div className="mt-6">{children}</div>
        {actions ? <div className="mt-6 flex justify-end gap-3">{actions}</div> : null}
      </div>
    </div>
  );
}
