"use client";

/**
 * 규제 다이제스트 카드 — 토지이음 등가 규제정보를 한 카드에 surface(법령엔진 연계).
 * POST /zoning/comprehensive → district_legal_refs(지역지구별 규제법령집)·action_restriction_detail
 * (도로조건·건축선·고시정보)·mixed_zone_assessment(혼재 용도지역 면적가중). opt-in+localStorage 캐시.
 * SiteCanvas '규제' 탭 — 그간 만든 토지이음 백엔드 작업(P1~P4+혼재)을 사용자에게 가시화.
 */

import { useEffect, useState } from "react";
import { ScrollText, ExternalLink } from "lucide-react";
import { apiClient } from "@/lib/api-client";

type LegalRef = { key: string; law_name: string; article?: string | null; url?: string | null; url_status?: string };
type Resp = {
  zone_type?: string; zone_type_secondary?: string;
  land_use_plan?: { district_legal_refs?: LegalRef[]; district_legal_unmatched?: string[] };
  action_restriction_detail?: {
    road_conditions?: { status?: string; note?: string };
    building_line?: { setback_m?: number | null; note?: string };
    gosi_info?: { list_url?: string; categories?: string[] };
  };
  mixed_zone_assessment?: { is_mixed?: boolean; blended_bcr_pct?: number | null; blended_far_pct?: number | null; rule?: string; note?: string } | null;
};

function hash(s: string): string {
  let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

export function RegulationDigestCard({ address }: { address?: string | null }) {
  const [res, setRes] = useState<Resp | null>(null);
  const [loading, setLoading] = useState(false);
  const key = address ? `propai_reg_digest_${hash(address.trim())}` : "";

  useEffect(() => {
    if (!key || typeof window === "undefined") { setRes(null); return; }
    try { const raw = window.localStorage.getItem(key); setRes(raw ? JSON.parse(raw) : null); } catch { setRes(null); }
  }, [key]);

  async function run() {
    if (!address?.trim() || loading) return;
    setLoading(true);
    try {
      const r = await apiClient.post<Resp>("/zoning/comprehensive", { body: { address: address.trim() }, useMock: false, timeoutMs: 50000 });
      setRes(r);
      try { if (key) window.localStorage.setItem(key, JSON.stringify(r)); } catch { /* quota */ }
    } catch { /* graceful */ } finally { setLoading(false); }
  }

  if (!address?.trim()) return null;
  const refs = res?.land_use_plan?.district_legal_refs ?? [];
  const ard = res?.action_restriction_detail;
  const mz = res?.mixed_zone_assessment;

  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--text-primary)]">
          <ScrollText className="size-4 text-[var(--accent-strong)]" aria-hidden /> 규제법령집 · 행위제한(토지이음)
        </p>
        <button onClick={run} disabled={loading}
          className="rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2.5 py-1 text-[11px] font-bold text-[var(--text-primary)] hover:border-[var(--accent-strong)] disabled:opacity-50">
          {loading ? "조회 중…" : res ? "다시 조회" : "규제법령 조회"}
        </button>
      </div>

      {res && (
        <div className="mt-3 space-y-3">
          {/* 혼재 용도지역 */}
          {mz?.is_mixed && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-2.5 text-[11px]">
              <p className="font-bold text-amber-600">혼재 용도지역(둘 이상)</p>
              <p className="mt-0.5 leading-relaxed text-[var(--text-secondary)]">
                {res.zone_type} + {res.zone_type_secondary}
                {mz.blended_far_pct != null && ` · 면적가중 건폐 ${mz.blended_bcr_pct}%/용적 ${mz.blended_far_pct}%`}
                {` (${mz.rule})`}
              </p>
            </div>
          )}
          {/* 지역지구별 규제법령집 */}
          {refs.length > 0 && (
            <div>
              <p className="text-[11px] font-bold text-[var(--text-secondary)]">지역지구별 규제법령집 ({refs.length}조문)</p>
              <div className="mt-1 flex flex-wrap gap-1">
                {refs.map((r) => {
                  const label = `${r.law_name}${r.article ? ` ${r.article}` : ""}`;
                  return r.url && r.url_status === "verified" ? (
                    <a key={r.key} href={r.url} target="_blank" rel="noopener noreferrer"
                      className="inline-flex items-center gap-0.5 rounded-md border border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/5 px-1.5 py-0.5 text-[10px] font-bold text-[var(--accent-strong)] hover:bg-[var(--accent-strong)]/10">
                      {label} <ExternalLink className="size-2.5" aria-hidden />
                    </a>
                  ) : (
                    <span key={r.key} className="rounded-md border border-[var(--line)] px-1.5 py-0.5 text-[10px] text-[var(--text-tertiary)]">{label}</span>
                  );
                })}
              </div>
            </div>
          )}
          {/* 도로조건·건축선·고시 */}
          {ard && (
            <div className="grid grid-cols-1 gap-1.5 text-[11px] sm:grid-cols-3">
              <div className="rounded-lg border border-[var(--line)] bg-[var(--surface)] p-2">
                <p className="text-[10px] text-[var(--text-hint)]">도로조건(접도)</p>
                <p className="font-bold text-[var(--text-primary)]">{ard.road_conditions?.status ?? "—"}</p>
              </div>
              <div className="rounded-lg border border-[var(--line)] bg-[var(--surface)] p-2">
                <p className="text-[10px] text-[var(--text-hint)]">건축선 후퇴</p>
                <p className="font-bold text-[var(--text-primary)]">{ard.building_line?.setback_m != null ? `${ard.building_line.setback_m}m` : "—"}</p>
              </div>
              {ard.gosi_info?.list_url && (
                <a href={ard.gosi_info.list_url} target="_blank" rel="noopener noreferrer"
                  className="rounded-lg border border-[var(--line)] bg-[var(--surface)] p-2 hover:border-[var(--accent-strong)]">
                  <p className="text-[10px] text-[var(--text-hint)]">고시정보</p>
                  <p className="inline-flex items-center gap-0.5 font-bold text-[var(--accent-strong)]">열람 <ExternalLink className="size-2.5" aria-hidden /></p>
                </a>
              )}
            </div>
          )}
        </div>
      )}
      {!res && !loading && (
        <p className="mt-2 text-[11px] text-[var(--text-hint)]">버튼을 눌러 이 부지의 지역지구별 규제법령·도로조건·건축선·고시정보를 조회합니다.</p>
      )}
    </div>
  );
}
