"use client";

import { useEffect, useRef, useSyncExternalStore } from "react";
import { useAccessibility } from "@/hooks/useAccessibility";

type OfflineBannerProps = {
  labels: {
    onlineTitle: string;
    offlineTitle: string;
    onlineDescription: string;
    offlineDescription: string;
    cachedTitle: string;
    cachedDescription: string;
    cachedAtLabel: string;
  };
  cachedAt?: string;
  forceOffline?: boolean;
};

export function OfflineBanner({
  labels,
  cachedAt,
  forceOffline = false,
}: OfflineBannerProps) {
  const { announceToScreenReader } = useAccessibility();
  const previousOnlineRef = useRef<boolean | null>(null);
  const networkOnline = useSyncExternalStore(
    (onStoreChange) => {
      window.addEventListener("online", onStoreChange);
      window.addEventListener("offline", onStoreChange);

      return () => {
        window.removeEventListener("online", onStoreChange);
        window.removeEventListener("offline", onStoreChange);
      };
    },
    () => window.navigator.onLine,
    () => true,
  );

  const isOnline = forceOffline ? false : networkOnline;

  useEffect(() => {
    if (previousOnlineRef.current === null) {
      previousOnlineRef.current = isOnline;
      return;
    }

    if (previousOnlineRef.current !== isOnline) {
      announceToScreenReader(isOnline ? labels.onlineTitle : labels.offlineTitle);
      previousOnlineRef.current = isOnline;
    }
  }, [announceToScreenReader, isOnline, labels.offlineTitle, labels.onlineTitle]);

  return (
    <section className="grid gap-4 md:grid-cols-[1.1fr_0.9fr]">
      <div
        role="status"
        aria-live="polite"
        className={`rounded-[var(--radius-xl)] border px-5 py-4 ${
          isOnline
            ? "border-[rgba(14,116,144,0.24)] bg-[rgba(14,116,144,0.08)]"
            : "border-[rgba(217,119,6,0.26)] bg-[rgba(217,119,6,0.12)]"
        }`}
      >
        <p className="text-sm font-semibold text-[var(--text-primary)]">
          {isOnline ? labels.onlineTitle : labels.offlineTitle}
        </p>
        <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
          {isOnline ? labels.onlineDescription : labels.offlineDescription}
        </p>
      </div>
      <div className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-soft)] px-5 py-4">
        <p className="text-sm font-semibold text-[var(--text-primary)]">
          {labels.cachedTitle}
        </p>
        <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
          {labels.cachedDescription}
        </p>
        {cachedAt ? (
          <p className="mt-3 text-xs font-medium text-[var(--text-tertiary)]">
            {labels.cachedAtLabel}: {cachedAt}
          </p>
        ) : null}
      </div>
    </section>
  );
}
