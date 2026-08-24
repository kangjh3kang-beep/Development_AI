"use client";

/**
 * 등기 **권리분석 보고서** 다운로드(PDF/DOCX).
 *
 * 일괄분석 결과를 정본 보고서 엔진(`/registry/rights-report`)에 보내 문서로 받는다.
 * **새로 조회하지 않는다** — 이미 받은 결과를 형식화할 뿐이라 발급 과금이 없다.
 *
 * 【고지】미분석 필지는 보고서에서 **빠지지 않고** §미분석 섹션에 사유와 함께 남는다.
 * 빼면 문서가 "N필지 전부 안전"이라고 말하게 된다 — 없는 안전을 만드는 것이다.
 * 그래서 버튼 옆에도 분모를 적는다(분석 N / 전체 M).
 */

import { useCallback, useState } from "react";
import { FileText, Loader2 } from "lucide-react";

import { apiClient } from "@/lib/api-client";
import { isAnalyzed, type BatchOutcome } from "@/lib/registry-analyze";

type Fmt = "pdf" | "docx";

export function RegistryRightsReportButton({
  items,
  projectAddress,
  className = "",
}: {
  items: readonly BatchOutcome[];
  projectAddress?: string | null;
  className?: string;
}) {
  const [busy, setBusy] = useState<Fmt | null>(null);
  const [error, setError] = useState("");

  const total = items.length;
  const analyzed = items.filter(isAnalyzed).length;

  const run = useCallback(
    async (format: Fmt) => {
      setBusy(format);
      setError("");
      try {
        const token =
          typeof window !== "undefined" ? localStorage.getItem("propai_access_token") ?? "" : "";
        // ★기존 보고서 다운로드(ReportDownloadMenu)와 **같은 경로 규칙**을 쓴다.
        //   `NEXT_PUBLIC_API_URL` 을 직접 읽으면 프록시 경유 배포에서 URL 이 어긋난다.
        const baseUrl = apiClient.getRuntimeConfig().apiBaseUrl || "/api/proxy";
        const res = await fetch(`${baseUrl}/registry/rights-report`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            items: items.map((b) => ({ jibun: b.jibun, result: b.result })),
            project_address: projectAddress || undefined,
            format,
          }),
        });
        if (!res.ok) {
          // 서버가 사유를 주면 **그 사유를** 보여 준다(상한 초과 등) — 코드만 보이면 못 고친다.
          let msg = `보고서 생성 실패 (HTTP ${res.status})`;
          try {
            const j = await res.json();
            if (j?.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
          } catch {
            /* JSON 아님 — 기본 메시지 유지 */
          }
          throw new Error(msg);
        }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `등기권리분석보고서.${format}`;
        a.click();
        URL.revokeObjectURL(url);
      } catch (e) {
        setError(e instanceof Error ? e.message : "보고서를 만들지 못했습니다");
      } finally {
        setBusy(null);
      }
    },
    [items, projectAddress],
  );

  return (
    <div className={className}>
      <div className="flex flex-wrap items-center gap-1.5">
        {(["pdf", "docx"] as const).map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => void run(f)}
            disabled={busy !== null || total === 0}
            data-testid={`rights-report-${f}`}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--line-strong)] bg-[var(--surface-strong)] px-3 py-1.5 text-[11px] font-bold text-[var(--text-primary)] disabled:opacity-50"
          >
            {busy === f ? (
              <Loader2 className="size-3.5 animate-spin" aria-hidden />
            ) : (
              <FileText className="size-3.5" aria-hidden />
            )}
            권리분석 보고서 {f.toUpperCase()}
          </button>
        ))}
      </div>

      {/* ★분모를 적는다 — "보고서 받기"만 있으면 전 필지가 담긴 줄 안다. */}
      {total > 0 && (
        <p className="mt-1 text-[10px] text-[var(--text-hint)]" data-testid="rights-report-scope">
          {analyzed < total
            ? `분석 ${analyzed} / 전체 ${total}필지 — 미분석 ${total - analyzed}필지는 보고서에 사유와 함께 별도 표기됩니다`
            : `전체 ${total}필지 분석 완료`}
        </p>
      )}

      {error && (
        <p className="mt-1 text-[10px] font-bold text-[var(--status-error)]" data-testid="rights-report-error">
          {error}
        </p>
      )}
    </div>
  );
}
