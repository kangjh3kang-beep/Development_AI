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
        className={`rounded-[1.5rem] border px-5 py-4 ${
          isOnline
            ? "border-[rgba(14,116,144,0.24)] bg-[rgba(14,116,144,0.08)]"
            : "border-[rgba(217,119,6,0.26)] bg-[rgba(217,119,6,0.12)]"
        }`}
      >
        <p className="text-sm font-semibold text-[var(--foreground)]">
          {isOnline ? labels.onlineTitle : labels.offlineTitle}
        </p>
        <p className="mt-2 text-sm leading-7 text-[rgba(19,33,47,0.76)]">
          {isOnline ? labels.onlineDescription : labels.offlineDescription}
        </p>
      </div>
      <div className="rounded-[1.5rem] border border-[var(--line)] bg-[var(--surface-soft)] px-5 py-4">
        <p className="text-sm font-semibold text-[var(--foreground)]">
          {labels.cachedTitle}
        </p>
        <p className="mt-2 text-sm leading-7 text-[rgba(19,33,47,0.76)]">
          {labels.cachedDescription}
        </p>
        {cachedAt ? (
          <p className="mt-3 text-xs font-medium text-[rgba(19,33,47,0.62)]">
            {labels.cachedAtLabel}: {cachedAt}
          </p>
        ) : null}
      </div>
    </section>
  );
}
