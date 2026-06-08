"use client";

/**
 * 적격심사 사정율 시뮬레이터(베팅) — 복수예비가 추첨 메커니즘 몬테카를로.
 * 기초금액에서 예정가격 분포·적격확률 곡선·적정 투찰가를 산출(공식 규칙 기반, 데이터 불요).
 */

import { useState } from "react";
import { apiClient } from "@/lib/api-client";
import { NumberInput } from "@/components/common/NumberInput";

type Calibrated = {
  empirical_band: { min_pct: number; avg_pct: number; max_pct: number; count?: number };
  calibrated_bid_rate_pct: number; calibrated_bid_price: number; calibrated_win_prob: number; basis?: string;
};
type SimResult = {
  base_price: number; floor_rate_pct: number; variation_pct: number;
  yega_p10_rate: number; yega_p50_rate: number; yega_p90_rate: number;
  recommended_bid_rate_pct: number; recommended_bid_price: number; target_win_prob: number;
  calibrated?: Calibrated | null;
  curve: Array<{ bid_rate: number; bid_price: number; p_valid: number }>;
  note?: string; error?: string;
};

const won = (v: number) => `${(v / 1e8).toLocaleString(undefined, { maximumFractionDigits: 2 })}억`;

export function G2bEstimateSimPanel() {
  const [baseEok, setBaseEok] = useState(100);
  const [bidType, setBidType] = useState("공사");
  const [target, setTarget] = useState(85);
  const [res, setRes] = useState<SimResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const run = async () => {
    setBusy(true); setErr(null);
    try {
      const r = await apiClient.post<SimResult>("/g2b/estimate-simulation", {
        body: { base_price: baseEok * 1e8, bid_type: bidType, target_win_prob: target / 100, calibrate: true },
      });
      if (r.error) setErr(r.error); else setRes(r);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "시뮬레이션 실패");
    } finally { setBusy(false); }
  };

  const maxP = 1;

  return (
    <div className="cc-panel cc-bracketed p-6">
      <i className="cc-bracket cc-bracket--tl" />
      <i className="cc-bracket cc-bracket--tr" />
      <i className="cc-bracket cc-bracket--bl" />
      <i className="cc-bracket cc-bracket--br" />
      <div className="mb-1 flex items-center gap-2">
        <span className="cc-meta">MONTE-CARLO · BID SIM</span>
      </div>
      <h3 className="text-base font-bold text-[var(--text-primary)]">적격심사 사정율 시뮬레이터</h3>
      <p className="mt-0.5 text-xs text-[var(--text-secondary)]">복수예비가 15개 중 4개 추첨→예정가격 분포→낙찰하한율→적격확률 기반 적정 투찰가 산출.</p>

      <div className="mt-4 flex flex-wrap items-end gap-3">
        <label className="text-xs text-[var(--text-secondary)]">기초금액(억)
          <NumberInput allowDecimal value={baseEok} onChange={(n) => setBaseEok(n ?? 0)}
            className="mt-1 h-9 w-28 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 text-sm text-[var(--text-primary)]" />
        </label>
        <label className="text-xs text-[var(--text-secondary)]">공종
          <select value={bidType} onChange={(e) => setBidType(e.target.value)}
            className="mt-1 h-9 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 text-sm text-[var(--text-primary)]">
            {["공사", "용역", "물품"].map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label className="text-xs text-[var(--text-secondary)]">목표 적격확률(%)
          <input type="number" value={target} onChange={(e) => setTarget(Number(e.target.value))}
            className="mt-1 h-9 w-24 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 text-sm text-[var(--text-primary)]" />
        </label>
        <button type="button" onClick={run} disabled={busy}
          className="h-9 rounded-lg bg-[var(--accent-strong)] px-4 text-sm font-bold text-white disabled:opacity-50">
          {busy ? "시뮬레이션…" : "시뮬레이션 실행"}
        </button>
      </div>

      {err && <p className="mt-2 text-xs font-semibold text-[var(--status-error)]">{err}</p>}

      {res && (
        <div className="mt-5 space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {res.calibrated ? (
              <Tile label="실적보정 적정율" value={`${res.calibrated.calibrated_bid_rate_pct}%`} sub={`${won(res.calibrated.calibrated_bid_price)} · 적격 ${Math.round(res.calibrated.calibrated_win_prob * 100)}%`} accent />
            ) : (
              <Tile label="적정 투찰율" value={`${res.recommended_bid_rate_pct}%`} accent />
            )}
            <Tile label="메커니즘 적정율" value={`${res.recommended_bid_rate_pct}%`} sub={won(res.recommended_bid_price)} />
            <Tile label="낙찰하한율" value={`${res.floor_rate_pct}%`} />
            <Tile label="예정가격(중앙)" value={`${(res.yega_p50_rate * 100).toFixed(1)}%`} sub={`p10~p90 ${(res.yega_p10_rate * 100).toFixed(1)}~${(res.yega_p90_rate * 100).toFixed(1)}%`} />
          </div>
          {res.calibrated && (
            <p className="text-[11px] text-[var(--text-secondary)]">
              실적 낙찰가율(최저 {res.calibrated.empirical_band.min_pct}% · 평균 {res.calibrated.empirical_band.avg_pct}% · 최고 {res.calibrated.empirical_band.max_pct}%
              {res.calibrated.empirical_band.count ? `, ${res.calibrated.empirical_band.count}건` : ""}) 기반 보정 — 메커니즘 적정율과 실적 분포를 결합.
            </p>
          )}

          <div>
            <p className="mb-2 text-xs font-bold text-[var(--text-secondary)]">투찰율별 적격(낙찰가능) 확률</p>
            <div className="flex items-end gap-0.5 h-28">
              {(res.curve ?? []).filter((_, i) => i % 2 === 0).map((c) => (
                <div key={c.bid_rate} className="group relative flex-1" title={`${(c.bid_rate * 100).toFixed(2)}% → ${(c.p_valid * 100).toFixed(0)}%`}>
                  <div className="w-full rounded-t bg-[var(--accent-strong)]"
                    style={{ height: `${(c.p_valid / maxP) * 100}%`, opacity: c.bid_rate * 100 >= res.recommended_bid_rate_pct ? 1 : 0.4 }} />
                </div>
              ))}
            </div>
            <div className="mt-1 flex justify-between text-[10px] text-[var(--text-hint)]">
              <span>{(res.curve[0]?.bid_rate * 100).toFixed(1)}%</span>
              <span>투찰율 →</span>
              <span>100%</span>
            </div>
          </div>
          {res.note && <p className="text-[10px] text-[var(--text-hint)]">{res.note}</p>}
        </div>
      )}
    </div>
  );
}

function Tile({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: boolean }) {
  return (
    <div className="cc-panel px-4 py-3">
      <p className="cc-label">{label}</p>
      <p className={`cc-num mt-1 text-lg font-[1000] ${accent ? "text-[var(--accent-strong)]" : "text-[var(--text-primary)]"}`}>{value}</p>
      {sub ? <p className="mt-0.5 text-[10px] text-[var(--text-secondary)]">{sub}</p> : null}
    </div>
  );
}
