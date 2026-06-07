"use client";

/**
 * 등기부(소유관계) 일괄 조회/다운로드 — 단/다필지.
 *
 * /registry/bulk 호출. 상용 등기부 API(REGISTRY_API_*) 설정 시 필지별 소유자·근저당·
 * PDF 다운로드 링크를 제공하고, 미설정 시 안내 메시지를 표시한다.
 */

import { useCallback, useState } from "react";
import { apiClient } from "@/lib/api-client";

type RegItem = {
  pnu?: string | null; address?: string | null; status: string;
  owner?: string; registry_office?: string; doc_title?: string; issued?: string;
  pdf_base64?: string; has_pdf?: boolean; summary?: string; pdf_url?: string; message?: string;
};
type RegResult = { configured: boolean; provider?: string; count: number; results: RegItem[]; message?: string };

function downloadBase64Pdf(b64: string, name: string) {
  try {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const url = URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
    const a = document.createElement("a");
    a.href = url; a.download = name; a.click();
    URL.revokeObjectURL(url);
  } catch { /* noop */ }
}

export function RegistryBulkButton({ addresses, className = "" }: { addresses: string[]; className?: string }) {
  const list = addresses.map((s) => s.trim()).filter(Boolean);
  const [loading, setLoading] = useState(false);
  const [res, setRes] = useState<RegResult | null>(null);

  const run = useCallback(async () => {
    if (!list.length) return;
    setLoading(true); setRes(null);
    try {
      const r = await apiClient.post<RegResult>("/registry/bulk", {
        body: { addresses: list }, useMock: false, timeoutMs: 120000,
      });
      setRes(r);
    } catch {
      setRes({ configured: false, count: 0, results: [], message: "등기부 조회 요청에 실패했습니다." });
    } finally {
      setLoading(false);
    }
  }, [list]);

  if (!list.length) return null;

  return (
    <div className={`rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4 ${className}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-black text-[var(--text-primary)]">📑 등기부 일괄 조회/다운로드 ({list.length}필지)</p>
          <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">필지별 소유자·근저당·지분 + 등기부 PDF (상용 등기부 API 연동)</p>
        </div>
        <button onClick={run} disabled={loading}
          className="rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50">
          {loading ? "조회 중…" : "등기부 일괄 조회"}
        </button>
      </div>

      {res && !res.configured && (
        <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-[11px] text-amber-400">
          ⚙ {res.message || "등기부 발급 API 미설정"} <br />
          <span className="text-[var(--text-tertiary)]">대법원 IROS는 공개 API가 없어 상용 등기부 API(CODEF 등) 키 설정이 필요합니다(발급 건당 과금). 키 설정 시 자동 활성화됩니다.</span>
        </div>
      )}

      {res && res.configured && (
        <div className="mt-3 space-y-2">
          {(res.results ?? []).map((it, i) => (
            <div key={i} className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] p-3 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="font-bold text-[var(--text-primary)]">{i + 1}. {it.address || it.pnu}</span>
                {it.has_pdf && it.pdf_base64 ? (
                  <button onClick={() => downloadBase64Pdf(it.pdf_base64!, `등기부_${it.address || i + 1}.pdf`)}
                    className="rounded-md bg-[var(--accent-strong)] px-2 py-0.5 text-[10px] font-bold text-white">등기부 PDF 다운로드 ↓</button>
                ) : it.pdf_url ? (
                  <a href={it.pdf_url} target="_blank" rel="noopener noreferrer" className="rounded-md bg-[var(--accent-strong)] px-2 py-0.5 text-[10px] font-bold text-white">PDF ↗</a>
                ) : it.status !== "ok" ? (
                  <span className="text-[10px] text-amber-400">{it.status}</span>
                ) : null}
              </div>
              {it.status === "ok" && (
                <p className="mt-1 text-[var(--text-secondary)]">
                  {it.doc_title ? `${it.doc_title} · ` : ""}소유자 {it.owner || "-"}
                  {it.registry_office ? ` · ${it.registry_office}` : ""}
                </p>
              )}
              {it.status !== "ok" && it.message && (
                <p className="mt-1 text-[11px] text-[var(--text-tertiary)]">{it.message}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
