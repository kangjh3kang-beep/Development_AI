"use client";

/**
 * 대량 다필지 구역 일괄 분석 패널 (F-Parcel ParcelBatchJob UI).
 *
 * 구역(bbox) 또는 PNU 목록을 비동기 배치 잡으로 제출하고, 진행률·필지별 상태(확정/모호/
 * 미발견/오류)·통합 집계(합필 경계·면적)를 폴링으로 표시한다.
 * - 부분성 1급: 일부 실패해도 전체 실패가 아니라 분류 보존.
 * - 집계 완결성: 전 필지 확정 전에는 집계 보류(held).
 * 단일 필지 검색은 기존 경로 그대로(이 패널은 대량 전용·가산).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { GlobalAddressSearch } from "@/components/common/GlobalAddressSearch";

type ItemStatus = "confirmed" | "ambiguous" | "not_found" | "error";
type BatchItem = { pnu: string; status: ItemStatus; address?: string | null; area_sqm?: number | null; reason?: string | null };
type Counts = { total: number; confirmed: number; ambiguous: number; not_found: number; error: number };
type Aggregate = { held: boolean; union_boundary?: unknown; total_area_sqm?: number | null; jurisdiction_flags?: Record<string, unknown> | null };
type BatchResult = {
  job_id: string;
  state: string;
  completeness: "partial" | "complete" | string;
  counts: Counts;
  items: BatchItem[];
  aggregate?: Aggregate | null;
  pending?: string[];
  outliers?: { pnu: string; address?: string | null; area_sqm?: number; median_sqm?: number; ratio?: number; reason?: string }[];
  page?: number;
  size?: number;
  has_next?: boolean;
};

const STATUS_STYLE: Record<ItemStatus, string> = {
  confirmed: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  ambiguous: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  not_found: "bg-[var(--surface-strong)] text-[var(--text-tertiary)] border-[var(--line-strong)]",
  error: "bg-rose-500/15 text-rose-400 border-rose-500/30",
};
const STATUS_LABEL: Record<ItemStatus, string> = {
  confirmed: "확정", ambiguous: "모호", not_found: "미발견", error: "오류",
};

export function BulkParcelBatchPanel({ className = "" }: { className?: string }) {
  const [mode, setMode] = useState<"center" | "pnu" | "bbox">("center");
  const [pnuText, setPnuText] = useState("");
  const [bbox, setBbox] = useState<[string, string, string, string]>(["", "", "", ""]);
  const [centerAddr, setCenterAddr] = useState("");
  const [radiusM, setRadiusM] = useState(500);
  const [jobId, setJobId] = useState<string | null>(null);
  const [result, setResult] = useState<BatchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);
  useEffect(() => stop, [stop]);

  const poll = useCallback(async (id: string) => {
    try {
      const r = await apiClient.get<BatchResult>(`/parcels/batch/${id}?page=1&size=200`, { useMock: false, timeoutMs: 60000 });
      setResult(r);
      // 종료 조건: 진행상태(queued/running)가 아니면 터미널.
      // state=partial 은 "전 필지 처리됐으나 일부 미확정"인 종료 상태(INV-M4) — 무한폴링 방지.
      if (!["queued", "running"].includes(r.state)) {
        stop(); setLoading(false);
      }
    } catch {
      stop(); setLoading(false); setError("진행 상태 조회에 실패했습니다.");
    }
  }, [stop]);

  const submit = useCallback(async () => {
    setError(""); setResult(null); stop();
    let body: Record<string, unknown>;
    if (mode === "center") {
      if (!centerAddr.trim()) { setError("중심 주소를 검색하세요."); return; }
      body = { center_address: centerAddr.trim(), radius_m: radiusM };
    } else if (mode === "pnu") {
      const list = pnuText.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean);
      if (list.length === 0) { setError("PNU(19자리)를 한 줄에 하나씩 입력하세요."); return; }
      body = { pnu_list: list };
    } else {
      const nums = bbox.map((x) => parseFloat(x));
      if (nums.some((n) => Number.isNaN(n))) { setError("bbox 4개 좌표(min경도,min위도,max경도,max위도)를 모두 입력하세요."); return; }
      body = { bbox: nums };
    }
    setLoading(true);
    try {
      const sub = await apiClient.post<{ job_id: string; state: string }>("/parcels/batch", { body, useMock: false, timeoutMs: 60000 });
      setJobId(sub.job_id);
      await poll(sub.job_id);
      pollRef.current = setInterval(() => void poll(sub.job_id), 1500);
    } catch {
      setLoading(false); setError("배치 제출에 실패했습니다. 입력을 확인하세요.");
    }
  }, [mode, pnuText, bbox, centerAddr, radiusM, poll, stop]);

  const cancel = useCallback(async () => {
    if (!jobId) return;
    try { await apiClient.post(`/parcels/batch/${jobId}/cancel`, { useMock: false, timeoutMs: 30000 }); } catch { /* noop */ }
    stop(); setLoading(false);
  }, [jobId, stop]);

  const c = result?.counts;
  const total = c?.total || 0;
  const pct = (n: number) => (total > 0 ? `${(n / total) * 100}%` : "0%");

  return (
    <div className={`rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-5 ${className}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-black text-[var(--text-primary)]">🗺 대량 구역 일괄 분석</p>
          <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
수백~수천 필지(주소+반경·PNU 목록·구역 bbox)를 비동기로 일괄 해석합니다. 일부 실패해도 분류는 보존되며, 전 필지 확정 시 통합 집계를 산출합니다.
          </p>
        </div>
      </div>

      {/* 입력 모드 */}
      <div className="mt-4 flex flex-wrap gap-2">
        {(["center", "pnu", "bbox"] as const).map((m) => (
          <button key={m} onClick={() => setMode(m)} disabled={loading}
            className={`rounded-lg border px-3 py-1.5 text-xs font-bold disabled:opacity-50 ${mode === m ? "border-[var(--accent-strong)]/40 bg-[var(--accent-soft)] text-[var(--accent-strong)]" : "border-[var(--line)] text-[var(--text-secondary)]"}`}>
            {m === "center" ? "주소+반경" : m === "pnu" ? "PNU 목록" : "구역(bbox)"}
          </button>
        ))}
      </div>

      {mode === "center" ? (
        <div className="mt-2 space-y-2">
          <GlobalAddressSearch
            single
            writeToContext={false}
            disabled={loading}
            placeholder="구역 중심 주소를 검색하세요"
            onChange={(entries) => setCenterAddr(entries.length > 0 ? (entries[0].jibunAddress || entries[0].fullAddress) : "")}
          />
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-bold text-[var(--text-tertiary)]">반경</span>
            {[300, 500, 1000, 2000].map((r) => (
              <button key={r} onClick={() => setRadiusM(r)} disabled={loading}
                className={`rounded-lg border px-2.5 py-1 text-[11px] font-bold disabled:opacity-50 ${radiusM === r ? "border-[var(--accent-strong)]/40 bg-[var(--accent-soft)] text-[var(--accent-strong)]" : "border-[var(--line)] text-[var(--text-secondary)]"}`}>
                {r >= 1000 ? `${r / 1000}km` : `${r}m`}
              </button>
            ))}
            {centerAddr && <span className="truncate text-[11px] text-[var(--text-hint)]" title={centerAddr}>· {centerAddr}</span>}
          </div>
        </div>
      ) : mode === "pnu" ? (
        <textarea value={pnuText} onChange={(e) => setPnuText(e.target.value)} rows={4} disabled={loading}
          placeholder="PNU(19자리)를 줄/콤마로 구분해 입력&#10;예) 4115010100102240000"
          className="mt-2 w-full rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]" />
      ) : (
        <div className="mt-2 grid grid-cols-4 gap-2">
          {(["min경도", "min위도", "max경도", "max위도"] as const).map((ph, i) => (
            <input key={i} value={bbox[i]} disabled={loading}
              onChange={(e) => setBbox((p) => { const n = [...p] as typeof p; n[i] = e.target.value; return n; })}
              placeholder={ph} inputMode="decimal"
              className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-2 text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]" />
          ))}
        </div>
      )}

      <div className="mt-3 flex items-center gap-2">
        <button onClick={() => void submit()} disabled={loading}
          className="rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50">
          {loading ? "분석 중…" : "일괄 분석 시작"}
        </button>
        {loading && (
          <button onClick={() => void cancel()} className="rounded-xl border border-[var(--line-strong)] px-3 py-2 text-xs font-bold text-[var(--text-secondary)]">
            취소
          </button>
        )}
      </div>
      {error && <p className="mt-2 text-xs font-semibold text-rose-500">{error}</p>}

      {/* 진행률 스택바 + 카운트 */}
      {result && c && (
        <div className="mt-4 space-y-3">
          <div className="flex items-center justify-between text-[11px]">
            <span className="font-bold text-[var(--text-primary)]">
              {["queued", "running"].includes(result.state)
                ? "⏳ 진행"
                : result.completeness === "complete"
                  ? "✅ 완료(전 필지 확정)"
                  : "✅ 완료(일부 미확정)"} · {result.state}
            </span>
            <span className="text-[var(--text-secondary)]">
              총 {c.total} · 확정 {c.confirmed} · 모호 {c.ambiguous} · 미발견 {c.not_found} · 오류 {c.error}
            </span>
          </div>
          <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-[var(--surface-strong)]">
            <div style={{ width: pct(c.confirmed) }} className="bg-emerald-500" />
            <div style={{ width: pct(c.ambiguous) }} className="bg-amber-500" />
            <div style={{ width: pct(c.error) }} className="bg-rose-500" />
            <div style={{ width: pct(c.not_found) }} className="bg-[var(--text-tertiary)]/40" />
          </div>

          {/* 통합 집계 */}
          <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-3 text-xs">
            {result.aggregate?.held ? (
              <p className="text-amber-500">⏳ 통합 집계 보류 — 전 필지 확정 후 합필 경계·면적을 산출합니다(미처리 {result.pending?.length ?? 0}건).</p>
            ) : result.aggregate?.total_area_sqm ? (
              <p className="text-[var(--text-primary)]">
                🧩 통합 합필 면적 <b className="text-[var(--accent-strong)]">{Math.round(result.aggregate.total_area_sqm).toLocaleString()}㎡</b>
                {result.aggregate.total_area_sqm ? ` (${Math.round(result.aggregate.total_area_sqm / 3.3058).toLocaleString()}평)` : ""}
              </p>
            ) : (
              <p className="text-[var(--text-secondary)]">집계 대기 중</p>
            )}
          </div>

          {/* 신뢰루프: 면적 이상치(검토 권고) */}
          {(result.outliers?.length ?? 0) > 0 && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-[11px]">
              <p className="font-bold text-amber-500">⚠ 면적 이상치 {result.outliers!.length}건 — 데이터 확인 권고(자동 배제 안 함)</p>
              <ul className="mt-1 space-y-0.5 text-[var(--text-secondary)]">
                {result.outliers!.slice(0, 5).map((o, i) => (
                  <li key={i} className="truncate" title={o.reason || o.pnu}>· {o.address || o.pnu} — {o.area_sqm?.toLocaleString()}㎡ ({o.ratio}×)</li>
                ))}
                {result.outliers!.length > 5 && <li className="opacity-70">…외 {result.outliers!.length - 5}건</li>}
              </ul>
            </div>
          )}

          {/* 필지별 상태 */}
          <div className="max-h-72 space-y-1 overflow-y-auto">
            {(result.items ?? []).map((it, i) => (
              <div key={i} className="flex items-center justify-between gap-2 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2.5 py-1.5 text-[11px]">
                <span className="truncate text-[var(--text-secondary)]" title={it.address || it.pnu}>{it.address || it.pnu}</span>
                <div className="flex shrink-0 items-center gap-2">
                  {it.area_sqm ? <span className="text-[var(--text-tertiary)]">{Math.round(it.area_sqm).toLocaleString()}㎡</span> : null}
                  <span className={`rounded-full border px-2 py-0.5 font-bold ${STATUS_STYLE[it.status]}`}>{STATUS_LABEL[it.status]}</span>
                </div>
              </div>
            ))}
            {result.has_next && <p className="py-1 text-center text-[10px] text-[var(--text-tertiary)]">…상위 200건 표시(전체 {c.total}건)</p>}
          </div>
        </div>
      )}
    </div>
  );
}