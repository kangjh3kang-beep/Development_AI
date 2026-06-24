"use client";

/**
 * 건축 예상 비용 카드 — jootek '건축 예상 비용 확인하기' 등가.
 * /site-score/envelope(건축가능 연면적) → /cost/estimate-overview(지상/지하/조경/간접 공사비 최저~최대).
 * SiteCanvas '수지' 탭. opt-in+localStorage 캐시. 무목업: 미확보 항목은 표시 안 함.
 */

import { useEffect, useState } from "react";
import { Hammer } from "lucide-react";
import { apiClient } from "@/lib/api-client";

type Envelope = { effective_gfa_sqm?: number; max_floors?: number };
type Cost = { total_gfa_sqm?: number; cost_range?: { min_won?: number; expected_won?: number; max_won?: number }; per_pyeong_won?: number; min_won?: number; expected_won?: number; max_won?: number };

function hash(s: string): string {
  let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}
const eok = (w?: number | null) => (w == null ? "—" : `${(w / 1e8).toLocaleString(undefined, { maximumFractionDigits: 1 })}억`);

export function BuildCostCard({ address, landAreaSqm, zone }: { address?: string | null; landAreaSqm?: number | null; zone?: string | null }) {
  const [cost, setCost] = useState<Cost | null>(null);
  const [gfa, setGfa] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const key = address ? `propai_buildcost_${hash(address.trim())}` : "";

  useEffect(() => {
    if (!key || typeof window === "undefined") { setCost(null); return; }
    try { const raw = window.localStorage.getItem(key); if (raw) { const o = JSON.parse(raw); setCost(o.cost); setGfa(o.gfa); } else { setCost(null); } } catch { setCost(null); }
  }, [key]);

  async function run() {
    if (loading) return;
    if (!landAreaSqm || landAreaSqm <= 0) { setError("대지면적이 필요합니다."); return; }
    setLoading(true); setError("");
    try {
      const env = await apiClient.post<Envelope>("/site-score/envelope", {
        body: { land_area_sqm: landAreaSqm, zone: zone ?? "" }, useMock: false, timeoutMs: 45000,
      });
      const g = env?.effective_gfa_sqm;
      if (!g || g <= 0) { setError("건축가능 연면적을 산정하지 못했습니다."); setLoading(false); return; }
      const floors = Math.max(1, Math.round(env?.max_floors ?? Math.max(1, g / (landAreaSqm * 0.6))));
      const c = await apiClient.post<Cost>("/cost/estimate-overview", {
        body: { total_gfa_sqm: Math.round(g), floor_count_above: floors, building_type: "apartment", structure_type: "RC" },
        useMock: false, timeoutMs: 45000,
      });
      setGfa(Math.round(g)); setCost(c);
      try { if (key) window.localStorage.setItem(key, JSON.stringify({ cost: c, gfa: Math.round(g) })); } catch { /* quota */ }
    } catch {
      setError("건축비 추정에 실패했습니다.");
    } finally { setLoading(false); }
  }

  if (!address?.trim()) return null;
  const r = cost?.cost_range ?? cost;
  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--text-primary)]">
          <Hammer className="size-4 text-[var(--accent-strong)]" aria-hidden /> 건축 예상 비용
        </p>
        <button onClick={run} disabled={loading}
          className="rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2.5 py-1 text-[11px] font-bold text-[var(--text-primary)] hover:border-[var(--accent-strong)] disabled:opacity-50">
          {loading ? "추정 중…" : cost ? "다시 추정" : "건축비 추정"}
        </button>
      </div>
      {error && <p className="mt-2 text-[11px] text-[var(--danger,#dc2626)]">{error}</p>}
      {cost && (
        <>
          <div className="mt-2.5 grid grid-cols-3 gap-2 text-center text-[11px]">
            <div><p className="text-[var(--text-hint)]">최저</p><p className="font-bold text-[var(--text-primary)]">{eok(r?.min_won)}</p></div>
            <div><p className="text-[var(--text-hint)]">예상</p><p className="font-black text-[var(--accent-strong)]">{eok(r?.expected_won)}</p></div>
            <div><p className="text-[var(--text-hint)]">최대</p><p className="font-bold text-[var(--text-primary)]">{eok(r?.max_won)}</p></div>
          </div>
          <p className="mt-2 text-[10px] text-[var(--text-hint)]">
            건축가능 연면적 {gfa?.toLocaleString()}㎡ 기준 · 평당 {cost.per_pyeong_won ? `${Math.round(cost.per_pyeong_won / 1e4).toLocaleString()}만원` : "—"} · 지상/지하/조경/간접 포함(공동주택·RC 가정).
          </p>
        </>
      )}
      {!cost && !error && (
        <p className="mt-2 text-[11px] text-[var(--text-hint)]">버튼을 눌러 건축가능 연면적 기준 공사비(최저~최대)를 추정합니다.</p>
      )}
    </div>
  );
}
