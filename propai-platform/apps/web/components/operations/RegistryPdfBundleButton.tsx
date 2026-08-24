"use client";

/**
 * 발급받은 등기부 PDF **일괄 다운로드** 버튼.
 *
 * 다필지 일괄분석을 돌리면 필지마다 등기부 PDF 가 발급되는데, 종전에는 행마다 `PDF ↗` 를
 * 하나씩 눌러야 했다(77필지면 77번). 한 번에 ZIP 으로 받는다.
 *
 * 【이 컴포넌트가 조심하는 것】
 * 결과를 **건수만** 말하지 않는다. 라이브 실측에서 저장된 서명 URL 중 상당수가 이미
 * 만료돼 있었다(발급 후 30일). 그냥 받으면 "77건 요청 → 41건짜리 ZIP" 이 조용히 나온다.
 * 그래서 끝나고 **무엇이 왜 빠졌는지**를 화면에 남긴다(`describeBundle`).
 */

import { useCallback, useState } from "react";
import { Download, Loader2 } from "lucide-react";

import {
  buildRegistryPdfBundle,
  describeBundle,
  saveBlob,
  type BundleResult,
  type PdfSource,
} from "@/lib/registry-pdf-bundle";

export function RegistryPdfBundleButton({
  sources,
  fileName = "등기부등본_묶음.zip",
  className = "",
}: {
  sources: readonly PdfSource[];
  fileName?: string;
  className?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<BundleResult | null>(null);
  const [error, setError] = useState("");

  const 받을수있는건수 = sources.filter((s) => (s.pdfUrl || "").trim()).length;

  const run = useCallback(async () => {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const r = await buildRegistryPdfBundle(sources);
      setResult(r);
      if (r.zip) saveBlob(r.zip, fileName);
    } catch (e) {
      // 상한 초과(4GB·65,535건) 등 — 조용히 깨진 ZIP 을 만드느니 여기서 멈춘다.
      setError(e instanceof Error ? e.message : "묶음을 만들지 못했습니다");
    } finally {
      setBusy(false);
    }
  }, [sources, fileName]);

  return (
    <div className={className}>
      <button
        type="button"
        onClick={run}
        disabled={busy || 받을수있는건수 === 0}
        data-testid="pdf-bundle-button"
        className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--line-strong)] bg-[var(--surface-strong)] px-3 py-1.5 text-[11px] font-bold text-[var(--text-primary)] disabled:opacity-50"
      >
        {busy ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : <Download className="size-3.5" aria-hidden />}
        {busy ? "묶는 중…" : `등기부 PDF 일괄 다운로드 (${받을수있는건수}건)`}
      </button>

      {/* 왜 못 누르는지 말한다 — 비활성 버튼만 두면 사용자는 고장으로 읽는다. */}
      {받을수있는건수 === 0 && (
        <p className="mt-1 text-[10px] text-[var(--text-hint)]" data-testid="pdf-bundle-empty">
          발급된 등기부 PDF 가 없습니다 — 먼저 일괄 분석을 실행하세요.
        </p>
      )}

      {error && (
        <p className="mt-1 text-[10px] font-bold text-[var(--status-error)]" data-testid="pdf-bundle-error">
          {error}
        </p>
      )}

      {result && (
        <div className="mt-1.5 text-[10px]" data-testid="pdf-bundle-summary">
          <p className="font-bold text-[var(--text-secondary)]">{describeBundle(result)}</p>
          {/* 제외된 건은 **지번까지** 보여 준다. 개수만 보면 어느 필지를 다시 받아야 할지 모른다. */}
          {result.items.some((i) => i.status !== "included") && (
            <ul className="mt-1 space-y-0.5 text-[var(--text-hint)]" data-testid="pdf-bundle-excluded">
              {result.items
                .filter((i) => i.status !== "included")
                .map((i, n) => (
                  <li key={n} className="truncate">
                    · {i.jibun} — {i.detail}
                  </li>
                ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
