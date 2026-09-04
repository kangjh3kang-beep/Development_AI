"use client";

/**
 * 등기부(소유관계) 일괄 조회/다운로드 — 단/다필지.
 * 하이픈(Hyphen) API 1순위 연동 + 비상 등기부 PDF 직접 업로드 지원.
 */

import { useCallback, useState } from "react";
import { AlertTriangle, FileUp, Files, Settings } from "lucide-react";
import { ApiClientError, apiClient } from "@/lib/api-client";
import { idempotencyHeaders } from "@/lib/idempotency";
import { RegistryUploadModal } from "./RegistryUploadModal";

type RegItem = {
  pnu?: string | null; address?: string | null; status: string;
  owner?: string; registry_office?: string; doc_title?: string; issued?: string;
  pdf_base64?: string; has_pdf?: boolean; summary?: string; pdf_url?: string; message?: string;
  // 어느 구분의 물건을 열람했는지 + 요청한 구분·동/호로 특정하지 못한 경우의 고지.
  // 필지당 1,200원이 과금되는 경로라 "다른 물건을 받았을 수 있다"는 사실이 반드시 보여야 한다.
  realty_gubun?: string | null; select_note?: string | null;
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
  const [isModalOpen, setIsModalOpen] = useState(false);

  const run = useCallback(async () => {
    if (!list.length) return;
    setLoading(true); setRes(null);
    try {
      const items = list.map((a) => ({ address: a }));
      const r = await apiClient.post<RegResult>("/registry/bulk", {
        body: { items }, useMock: false, timeoutMs: 120000,
        headers: idempotencyHeaders("registry.bulk", { items }),
      });
      setRes(r);
    } catch (err) {
      // ★멱등 가드가 새로 만드는 상태를 "조회 실패"로 뭉뚱그리면 안 된다.
      //   409 = 같은 요청이 **아직 처리 중**이다(중복 청구를 막으려고 두 번째를 안 받았다).
      //   타임아웃(120초) 뒤 다시 누르면 서버가 아직 돌고 있어 실제로 이 경로가 나온다 —
      //   여기서 "실패했습니다"라고 하면 사용자는 또 누르고, 매번 같은 답을 받는다.
      //   422 = 같은 키를 **다른 필지 묶음**에 재사용했다(정상적으로는 안 나온다 — 키를
      //   묶음 시그니처로 갱신하므로. 나오면 그건 우리 배선 결함이라 문구로 드러낸다).
      const status = err instanceof ApiClientError ? err.status : 0;
      const message =
        status === 409
          ? "같은 조회가 아직 처리 중입니다. 잠시 후 결과를 확인하세요(중복 청구를 막기 위해 다시 실행하지 않았습니다)."
          : status === 422
            ? "요청 식별키가 다른 내용으로 재사용되었습니다. 페이지를 새로고침한 뒤 다시 시도하세요."
            : "등기부 조회 요청에 실패했습니다.";
      setRes({ configured: false, count: 0, results: [], message });
    } finally {
      setLoading(false);
    }
  }, [list]);

  if (!list.length) return null;

  return (
    <div className={`rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4 ${className}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--text-primary)]">
            <Files className="size-4" aria-hidden /> 등기부 일괄 조회/다운로드 ({list.length}필지)
          </p>
          <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
            하이픈(Hyphen) 등기부 API 1순위 연동 + 비상 등기부 PDF 직접 업로드
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsModalOpen(true)}
            className="flex items-center gap-1 rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-xs font-bold text-[var(--text-primary)] hover:bg-[var(--surface-soft)]"
          >
            <FileUp className="size-3.5" /> 비상 PDF 업로드
          </button>
          <button
            onClick={run}
            disabled={loading}
            className="rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50"
          >
            {loading ? "조회 중…" : "등기부 일괄 조회"}
          </button>
        </div>
      </div>

      {res && !res.configured && (
        <div className="mt-3 rounded-lg border border-[var(--status-warning)]/30 bg-[var(--status-warning)]/10 p-3 text-[11px] text-[var(--status-warning)]">
          <span className="inline-flex items-center gap-1 font-bold">
            <Settings className="size-3.5" aria-hidden /> {res.message || "등기부 발급 API 미설정"}
          </span> <br />
          <span className="mt-1 block text-[var(--text-tertiary)]">
            하이픈(Hyphen) HKey 키 설정 시 자동 연동됩니다. API가 미설정 상태이거나 장기간 접속 지연 발생 시 상단의 <strong>[비상 PDF 업로드]</strong> 버튼을 통해 등기부등본 PDF를 직접 첨부해 주세요.
          </span>
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
                  <span className="text-[10px] text-[var(--status-warning)]">{it.status}</span>
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
              {/* 요청과 다른 물건을 조회했을 수 있다는 고지 — 과금 경로이므로 행마다 노출한다. */}
              {it.select_note && (
                <p role="status" className="mt-1.5 flex items-start gap-1.5 rounded-md border border-[var(--status-warning)]/30 bg-[var(--status-warning)]/10 px-2 py-1 text-[11px] font-bold leading-relaxed text-[var(--text-primary)] break-keep">
                  <AlertTriangle className="mt-0.5 size-3 shrink-0 text-[var(--status-warning)]" aria-hidden />
                  <span>
                    {it.select_note}
                    {it.realty_gubun && (
                      <span className="ml-1 font-normal text-[var(--text-secondary)]">(열람 구분: {it.realty_gubun})</span>
                    )}
                  </span>
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      <RegistryUploadModal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} />
    </div>
  );
}
