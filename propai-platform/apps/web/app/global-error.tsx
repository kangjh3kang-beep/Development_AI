"use client";

import { useEffect } from "react";
import { reportBoundaryError } from "@/lib/growth/report-boundary-error";
import { tryRecoverFromChunkError } from "@/lib/chunk-recovery";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  // 자가성장 엔진: 렌더 에러를 js_error 로 계측(논블로킹·UI 영향 없음).
  useEffect(() => {
    // ★배포 직후 열려 있던 탭의 청크 404 는 사용자가 고칠 것이 없다 — 세션당 1회 자동 복구.
    //   복구했으면 곧 페이지가 갈리므로 이 아래는 의미가 없다(루프 방지는 헬퍼가 한다).
    if (tryRecoverFromChunkError(error)) return;
    // ★공용 보고기를 쓴다 — 여기서 trackEvent 를 직접 부르면 **배달되지 않는다.**
    //   이 파일은 <html> 을 렌더한다 = 루트 레이아웃을 대체한다 = AppStateBridge 가 없다 =
    //   initEventCollector() 가 안 돌았다 = flush 구동자가 하나도 없다(실측 배달 0건).
    reportBoundaryError("global-error", error);
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
