"use client";

import { useEffect } from "react";
import { trackEvent } from "@/lib/growth/event-collector";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  // 자가성장 엔진: 대시보드 렌더 에러를 js_error 로 계측(논블로킹·UI 영향 없음).
  useEffect(() => {
    try {
      trackEvent("js_error", {
        severity: "error",
        payload: {
          scope: "dashboard-error",
          message: error?.message ?? "",
          digest: error?.digest ?? null,
          stack: error?.stack ? error.stack.slice(0, 2000) : null,
        },
      });
    } catch {
      /* noop */
    }
  }, [error]);

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-6 p-8">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-red-500/10 text-red-400">
        <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>
      </div>
      <h2 className="text-2xl font-black text-[var(--text-primary)]">페이지 오류</h2>
      <p className="text-sm text-[var(--text-secondary)] max-w-md text-center">
        이 페이지에서 오류가 발생했습니다. 잠시 후 다시 시도해주세요.
      </p>
      <p className="text-xs text-[var(--text-hint)]">{error.message}</p>
      <button
        onClick={reset}
        className="rounded-xl bg-[var(--accent-strong)] px-6 py-3 text-sm font-black text-[#0a0f14] hover:brightness-110 transition-all"
      >
        다시 시도
      </button>
    </div>
  );
}
