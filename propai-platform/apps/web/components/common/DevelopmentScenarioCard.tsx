"use client";

/**
 * 다각도 개발방식 시뮬레이션 카드.
 *
 * 단일/다필지에 대해 정책별(지구단위·도시개발·가로주택·모아주택·역세권 등) 적용요건을
 * 판정하고 예상 용적률·기부채납·실현성을 산정해 최적 사업방안을 제안한다.
 * 다필지는 인접성(통합개발 가능여부)을 함께 판정한다. opt-in 실행 + 캐싱.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiClient } from "@/lib/api-client";

function hashStr(s: string): string {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

type Magdo = {
  consent_required?: string; consent_threshold_pct?: number;
  claimable_remainder_pct?: number; basis?: string; note?: string;
};
type MagdoSummary = {
  applicable: boolean; scheme?: string; consent_required?: string;
  consent_threshold_pct?: number; claimable_remainder_pct?: number;
  basis?: string; note?: string;
  parcel_estimate?: {
    total_parcels: number; consent_needed_parcels: number;
    claimable_parcels_max: number; assumption: string;
  } | null;
};
type Scenario = {
  scheme: string; applicable: string; est_far: number | null;
  contribution_pct: number | null; requirements?: string[];
  pros?: string[]; cons?: string[]; notes?: string; magdo?: Magdo | null;
};
type SimResult = {
  site: {
    multi?: boolean; parcel_count?: number; primary_zone?: string;
    total_area_sqm?: number | null; near_station?: boolean; near_station_m?: number | null;
    integration_feasible?: boolean;
    adjacency?: { contiguous: boolean | null; components: number | null; note: string };
    buildings?: {
      buildings_found?: number; old_count?: number; old_ratio?: number | null;
      avg_age?: number | null; oldest_age?: number | null; total_units?: number | null;
      owner_types?: string[] | null;
    } | null;
  };
  scenarios: Scenario[];
  recommended: { scheme: string; est_far?: number | null; reason?: string };
  magdo_summary?: MagdoSummary | null;
  ai?: { generated?: boolean; summary?: string; best_scheme?: string; why?: string; alternatives?: string[]; cautions?: string[] } | null;
};

const APP_STYLE: Record<string, string> = {
  가능: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
  조건부: "border-amber-500/30 bg-amber-500/10 text-amber-400",
  불가: "border-[var(--line-strong)] bg-[var(--surface-strong)] text-[var(--text-tertiary)]",
};

export function DevelopmentScenarioCard({
  address,
  parcels,
  className = "",
}: {
  address?: string;
  parcels?: string[];
  className?: string;
}) {
  const list = useMemo(() => (parcels || []).map((s) => s.trim()).filter(Boolean), [parcels]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<SimResult | null>(null);

  const cacheKey = useMemo(() => {
    try { return `propai_scenario_${hashStr((address || "") + "|" + list.join("|"))}`; }
    catch { return ""; }
  }, [address, list]);

  useEffect(() => {
    if (!cacheKey || typeof window === "undefined") { setResult(null); return; }
    try {
      const raw = window.localStorage.getItem(cacheKey);
      if (raw) { setResult(JSON.parse(raw)); return; }
    } catch { /* noop */ }
    setResult(null);
  }, [cacheKey]);

  const run = useCallback(async () => {
    const target = address || list[0];
    if (!target) { setError("주소를 먼저 선택하세요."); return; }
    setLoading(true); setError(""); setResult(null);
    try {
      const r = await apiClient.post<SimResult>("/development-methods/scenarios", {
        body: { address: target, parcels: list.length > 1 ? list : undefined, use_llm: true },
        useMock: false, timeoutMs: 150000,
      });
      setResult(r);
      try { if (cacheKey) window.localStorage.setItem(cacheKey, JSON.stringify(r)); } catch { /* quota */ }
    } catch {
      setError("개발 시나리오 분석에 실패했습니다. 잠시 후 다시 시도하세요.");
    } finally {
      setLoading(false);
    }
  }, [address, list, cacheKey]);

  const site = result?.site;
  const adj = site?.adjacency;

  return (
    <div className={`rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-5 ${className}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-black text-[var(--text-primary)]">🏗 최적 개발방식 시뮬레이션</p>
          <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
            지구단위·도시개발·가로주택·모아주택·역세권 등 정책 적용요건을 판정해 최적 사업방안을 제안합니다(다필지 인접성 포함).
          </p>
        </div>
        <button onClick={run} disabled={loading || (!address && !list.length)}
          className="rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50">
          {loading ? "시뮬레이션 중…" : result ? "다시 분석" : "시나리오 분석 실행"}
        </button>
      </div>
      {error && <p className="mt-2 text-xs font-semibold text-rose-500">{error}</p>}

      {result && site && (
        <div className="mt-4 space-y-4">
          {/* 부지 요약 + 인접성 */}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="rounded-lg bg-[var(--accent-soft)] px-2 py-0.5 font-bold text-[var(--accent-strong)]">{site.primary_zone || "용도미상"}</span>
            {site.total_area_sqm != null && <span className="text-[var(--text-secondary)]">{site.total_area_sqm.toLocaleString()}㎡</span>}
            {site.near_station != null && <span className="text-[var(--text-secondary)]">역세권 {site.near_station ? "○" : "✕"}{site.near_station_m != null ? ` (${site.near_station_m}m)` : ""}</span>}
            {site.multi && adj && (
              <span className={`rounded-lg border px-2 py-0.5 font-bold ${adj.contiguous === true ? "border-emerald-500/30 text-emerald-400" : adj.contiguous === false ? "border-rose-500/30 text-rose-400" : "border-amber-500/30 text-amber-400"}`}>
                {adj.contiguous === true ? "🔗 통합개발 가능" : adj.contiguous === false ? "✂ 통합개발 불가" : "❔ 인접성 미상"}
              </span>
            )}
            {site.buildings && (site.buildings.buildings_found ?? 0) > 0 && (
              <span className="text-[var(--text-secondary)]">
                노후도 {site.buildings.old_ratio != null ? `${Math.round(site.buildings.old_ratio * 100)}%` : "-"}
                {site.buildings.avg_age != null ? ` · 평균 ${site.buildings.avg_age}년` : ""}
                {site.buildings.total_units ? ` · ${site.buildings.total_units}세대` : ""}
                {site.buildings.owner_types?.length ? ` · ${site.buildings.owner_types.join("/")}` : ""}
              </span>
            )}
          </div>

          {/* 추천 */}
          <div className="rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/5 p-4">
            <p className="text-xs font-black text-[var(--accent-strong)]">📌 추천 사업방안: {result.ai?.best_scheme || result.recommended.scheme}</p>
            {(result.ai?.why || result.recommended.reason) && (
              <p className="mt-1 text-sm leading-relaxed text-[var(--text-primary)]">{result.ai?.why || result.recommended.reason}</p>
            )}
            {result.ai?.summary && <p className="mt-1.5 text-xs leading-relaxed text-[var(--text-secondary)]">{result.ai.summary}</p>}
            {(result.ai?.cautions?.length ?? 0) > 0 && (
              <ul className="mt-1.5 space-y-0.5 text-[11px] text-amber-500">
                {result.ai!.cautions!.map((c, i) => <li key={i}>⚠ {c}</li>)}
              </ul>
            )}
          </div>

          {/* 매도청구 요약 */}
          {result.magdo_summary && (
            <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-4">
              <p className="text-xs font-black text-[var(--text-primary)]">⚖ 매도청구 분석 {result.magdo_summary.scheme ? `· ${result.magdo_summary.scheme}` : ""}</p>
              {result.magdo_summary.applicable ? (
                <div className="mt-2 space-y-1.5 text-xs text-[var(--text-secondary)]">
                  <p>동의 요건: <b className="text-[var(--text-primary)]">{result.magdo_summary.consent_required}</b></p>
                  <p>
                    동의 임계 <b className="text-[var(--accent-strong)]">{result.magdo_summary.consent_threshold_pct}%</b> 충족 시
                    {" "}미동의 잔여 <b className="text-rose-400">~{result.magdo_summary.claimable_remainder_pct}%</b> 매도청구 가능
                  </p>
                  {result.magdo_summary.parcel_estimate && (
                    <p className="text-[11px] text-[var(--text-tertiary)]">
                      다필지 추정: 총 {result.magdo_summary.parcel_estimate.total_parcels}필지 중 동의 필요 ~{result.magdo_summary.parcel_estimate.consent_needed_parcels}필지,
                      매도청구 가능 최대 {result.magdo_summary.parcel_estimate.claimable_parcels_max}필지
                      <span className="block opacity-70">({result.magdo_summary.parcel_estimate.assumption})</span>
                    </p>
                  )}
                  <p className="text-[11px] text-[var(--text-tertiary)]">근거: {result.magdo_summary.basis} · {result.magdo_summary.note}</p>
                </div>
              ) : (
                <p className="mt-1 text-xs text-[var(--text-secondary)]">{result.magdo_summary.note}</p>
              )}
            </div>
          )}

          {/* 시나리오 목록 */}
          <div className="space-y-2">
            {result.scenarios.map((s, i) => (
              <div key={i} className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-3.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-bold text-[var(--text-primary)]">{s.scheme}</p>
                  <div className="flex items-center gap-2 text-[11px]">
                    {s.est_far != null && <span className="font-bold text-[var(--accent-strong)]">예상 용적 {s.est_far}%</span>}
                    {s.contribution_pct != null && s.contribution_pct > 0 && <span className="text-[var(--text-tertiary)]">기부채납 ~{s.contribution_pct}%</span>}
                    <span className={`rounded-full border px-2 py-0.5 font-bold ${APP_STYLE[s.applicable] || APP_STYLE["불가"]}`}>{s.applicable}</span>
                  </div>
                </div>
                {s.notes && <p className="mt-1 text-[11px] text-[var(--text-secondary)]">{s.notes}</p>}
                {s.applicable !== "불가" && (
                  <div className="mt-1.5 grid gap-1 text-[11px] md:grid-cols-2">
                    {(s.requirements?.length ?? 0) > 0 && (
                      <p className="text-[var(--text-tertiary)]">요건: {s.requirements!.join(" · ")}</p>
                    )}
                    {(s.pros?.length ?? 0) > 0 && (
                      <p className="text-emerald-500">장점: {s.pros!.join(" · ")}</p>
                    )}
                    {s.magdo && (
                      <p className="text-rose-400 md:col-span-2">
                        ⚖ 매도청구: 동의 {s.magdo.consent_threshold_pct}% 충족 시 잔여 ~{s.magdo.claimable_remainder_pct}% 청구 가능 ({s.magdo.basis})
                      </p>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
