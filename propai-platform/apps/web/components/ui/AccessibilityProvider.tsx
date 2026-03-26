"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { Locale } from "@/i18n/config";

export type AnnouncementMode = "polite" | "assertive";

type AccessibilityContextValue = {
  announce: (message: string, mode?: AnnouncementMode) => void;
};

const AccessibilityContext = createContext<AccessibilityContextValue | null>(
  null,
);

type AccessibilityProviderProps = {
  children: React.ReactNode;
  locale: Locale;
  announcerLabel: string;
};

export function AccessibilityProvider({
  children,
  locale,
  announcerLabel,
}: AccessibilityProviderProps) {
  const [message, setMessage] = useState("");
  const [mode, setMode] = useState<AnnouncementMode>("polite");

  const announce = useCallback(
    (nextMessage: string, nextMode: AnnouncementMode = "polite") => {
      setMode(nextMode);
      setMessage("");

      window.requestAnimationFrame(() => {
        setMessage(nextMessage);
      });
    },
    [],
  );

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  useEffect(() => {
    const reducedMotionQuery = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    );
    const contrastQuery = window.matchMedia("(prefers-contrast: high)");

    const syncAttributes = () => {
      document.documentElement.dataset.reducedMotion = reducedMotionQuery.matches
        ? "true"
        : "false";
      document.documentElement.dataset.highContrast = contrastQuery.matches
        ? "true"
        : "false";
    };

    syncAttributes();
    reducedMotionQuery.addEventListener("change", syncAttributes);
    contrastQuery.addEventListener("change", syncAttributes);

    return () => {
      reducedMotionQuery.removeEventListener("change", syncAttributes);
      contrastQuery.removeEventListener("change", syncAttributes);
    };
  }, []);

  const value = useMemo(
    () => ({
      announce,
    }),
    [announce],
  );

  return (
    <AccessibilityContext.Provider value={value}>
      <div
        id="sr-announcer"
        className="sr-only"
        aria-live={mode}
        aria-atomic="true"
        role="status"
        aria-label={announcerLabel}
      >
        {message}
      </div>
      {children}
    </AccessibilityContext.Provider>
  );
}

export function useAccessibilityAnnouncer() {
  const context = useContext(AccessibilityContext);

  if (!context) {
    throw new Error("AccessibilityProvider 내부에서만 사용할 수 있습니다.");
  }

  return context;
}
