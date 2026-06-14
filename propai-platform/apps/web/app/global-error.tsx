"use client";

import { useEffect } from "react";
import { trackEvent } from "@/lib/growth/event-collector";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  // 자가성장 엔진: 렌더 에러를 js_error 로 계측(논블로킹·UI 영향 없음).
  useEffect(() => {
    try {
      trackEvent("js_error", {
        severity: "error",
        payload: {
          scope: "global-error",
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
    <html>
      <body>
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "center",
          justifyContent: "center", minHeight: "100vh", gap: "1.5rem",
          fontFamily: "system-ui", background: "#060b14", color: "#fff"
        }}>
          <h2 style={{ fontSize: "2rem", fontWeight: 900 }}>오류가 발생했습니다</h2>
          <p style={{ color: "#94a3b8", maxWidth: "400px", textAlign: "center" }}>
            예기치 않은 오류가 발생했습니다. 문제가 지속되면 관리자에게 문의하세요.
          </p>
          <p style={{ fontSize: "0.75rem", color: "#475569" }}>
            {error.message}
          </p>
          <button
            onClick={reset}
            style={{
              padding: "0.75rem 2rem", borderRadius: "1rem",
              background: "#14b8a6", color: "#0a0f14",
              fontWeight: 900, border: "none", cursor: "pointer"
            }}
          >
            다시 시도
          </button>
        </div>
      </body>
    </html>
  );
}
