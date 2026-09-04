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

import { apiClient, apiErrorMessage } from "@/lib/api-client";
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
        // ★공용 클라이언트를 **경유한다**. 손수 `fetch` + `Authorization` 을 조립하면
        //   `api-client` 의 **401 → refresh → 1회 재시도**가 붙지 않아, 액세스 토큰이
        //   만료된 60분 뒤부터 **다운로드만** 실패한다(화면의 다른 조회는 갱신을 받아 살아
        //   있으므로 «다운로드 기능이 깨졌다» 로 보인다 — 사용자 신고가 정확히 그것이었다:
        //   `유효하지 않은 토큰: Signature has expired.`).
        const blob = await apiClient.download("/registry/rights-report", {
          method: "POST",
          body: {
            items: items.map((b) => ({ jibun: b.jibun, result: b.result })),
            project_address: projectAddress || undefined,
            format,
          },
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `등기권리분석보고서.${format}`;
        a.click();
        URL.revokeObjectURL(url);
      } catch (e) {
        // ★서버가 준 사유를 **그대로** 보여 준다(상한 초과 등) — `ApiClientError.message` 는
        //   모든 실패에서 같은 상수라 그것을 띄우면 원인이 사라진다.
        setError(apiErrorMessage(e, "보고서를 만들지 못했습니다"));
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
