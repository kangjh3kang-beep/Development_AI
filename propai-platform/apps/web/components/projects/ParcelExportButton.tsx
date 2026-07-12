"use client";

/**
 * 구획도(필지 경계) 다운로드 버튼 — POST /api/v1/zoning/parcel-boundaries/export.
 * 현재 SSOT 필지(단일/다필지)를 GeoJSON·PNG·PDF로 내려받는다. blob fetch(기존 BOQ/PDF 패턴).
 * VWorld 지적 폴리곤 기반(참고용·법적 측량도 아님).
 */

import { useCallback, useState } from "react";
import { Download } from "lucide-react";
import { apiV1BaseUrl } from "@/lib/api-client";

type Fmt = "geojson" | "png" | "pdf";
const FMT_LABEL: Record<Fmt, string> = { geojson: "GeoJSON", png: "PNG", pdf: "PDF" };
const FMT_EXT: Record<Fmt, string> = { geojson: "geojson", png: "png", pdf: "pdf" };

export function ParcelExportButton({
  parcels, address, pnu, className = "",
}: {
  /** SSOT 필지(다필지). 각 항목 {pnu?, address?} */
  parcels?: { pnu?: string | null; address?: string | null }[] | null;
  address?: string | null;
  pnu?: string | null;
  className?: string;
}) {
  const [busy, setBusy] = useState<Fmt | null>(null);
  const [error, setError] = useState("");

  const list = (parcels ?? [])
    .map((p) => ({ pnu: p.pnu || undefined, address: p.address || undefined }))
    .filter((p) => p.pnu || p.address);
  const hasTarget = list.length > 0 || !!pnu || !!address;

  const download = useCallback(async (fmt: Fmt) => {
    if (busy) return;
    setBusy(fmt); setError("");
    try {
      const token = typeof window !== "undefined"
        ? window.localStorage.getItem("propai_access_token") ?? "" : "";
      const body = list.length > 0
        ? { parcels: list, format: fmt }
        : { address: address ?? undefined, pnu: pnu ?? undefined, format: fmt };
      const res = await fetch(`${apiV1BaseUrl()}/zoning/parcel-boundaries/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify(body),
      });
      const ct = res.headers.get("content-type") ?? "";
      // 에러는 JSON(detail) — 빈 파일 다운로드 방지(정직 표기).
      if (!res.ok || (fmt !== "geojson" && ct.includes("application/json"))) {
        let msg = `다운로드 실패 (HTTP ${res.status})`;
        try { const j = await res.json(); msg = j?.detail || j?.message || msg; } catch { /* noop */ }
        throw new Error(msg);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `구획도_${list.length || 1}필지.${FMT_EXT[fmt]}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "다운로드에 실패했습니다.");
    } finally {
      setBusy(null);
    }
  }, [busy, list, address, pnu]);

  if (!hasTarget) return null;

  return (
    <div className={`flex flex-col gap-1 ${className}`}>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="inline-flex items-center gap-1 text-[11px] font-bold text-[var(--text-secondary)]">
          <Download className="size-3.5" aria-hidden /> 구획도 다운로드
        </span>
        {(Object.keys(FMT_LABEL) as Fmt[]).map((f) => (
          <button key={f} onClick={() => download(f)} disabled={!!busy}
            className="rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2.5 py-1 text-[11px] font-bold text-[var(--text-primary)] transition hover:border-[var(--accent-strong)] disabled:opacity-50">
            {busy === f ? "내려받는 중…" : FMT_LABEL[f]}
          </button>
        ))}
      </div>
      {error && <p className="text-[10px] text-[var(--status-error)]">{error}</p>}
    </div>
  );
}
