"use client";

/**
 * 다기간 DCF 월별 현금흐름 패널(베팅 B) + 엑셀 다운로드.
 * 컨텍스트(공사비·수지·부지)에서 기본값을 채우고, /api/v2/feasibility/cashflow 로 월별
 * 현금흐름·IRR·NPV·최대 자금소요를 산정. 은행제출용 정밀 사업성.
 */

import { useState } from "react";
import { Card, CardContent } from "@propai/ui";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";

type Row = { month: number; phase: string; inflow: number; outflow: number; net: number; cumulative: number };
type Summary = {
  total_months: number; total_inflow: number; total_outflow: number; net_profit: number;
  profit_rate_pct: number; peak_negative_cashflow: number; equity_amount: number;
  bridge_loan_amount: number; pf_loan_amount: number; irr_annual_pct: number | null;
  npv_won: number; discount_rate_annual_pct: number;
};
type CashflowResult = { rows: Row[]; summary: Summary };

const eok = (won: number | null | undefined) =>
  won != null ? `${(won / 1e8).toLocaleString(undefined, { maximumFractionDigits: 1 })}억` : "—";

/** v2 절대 URL(엑셀 blob 다운로드용) — apiClient 규칙과 동일 호스트 매핑. */
function v2Url(path: string): string {
  if (typeof window !== "undefined") {
    const h = window.location.hostname;
    if (h === "4t8t.net" || h === "www.4t8t.net" || h.endsWith(".pages.dev") || h === "propai.kr")
      return `https://api.4t8t.net/api/v2${path}`;
    return `http://localhost:8000/api/v2${path}`;
  }
  return `https://api.4t8t.net/api/v2${path}`;
}

export function CashflowDcfPanel() {
  const cost = useProjectContextStore((s) => s.costData);
  const feas = useProjectContextStore((s) => s.feasibilityData);
  const site = useProjectContextStore((s) => s.siteAnalysis);

  // 기본값(억원). 컨텍스트 → 폴백.
  const [landEok, setLandEok] = useState<number>(() => Math.round(((site?.estimatedValue ?? 0) / 1e8) * 10) / 10 || 100);
  const [conEok, setConEok] = useState<number>(() => Math.round(((cost?.totalConstructionCostWon ?? feas?.totalCostWon ?? 0) / 1e8) * 10) / 10 || 180);
  const [revEok, setRevEok] = useState<number>(() => Math.round(((feas?.totalRevenueWon ?? 0) / 1e8) * 10) / 10 || 400);
  const [conMonths, setConMonths] = useState(24);
  const [saleStart, setSaleStart] = useState(6);
  const [equityPct, setEquityPct] = useState(30);
  const [discPct, setDiscPct] = useState(6);

  const [result, setResult] = useState<CashflowResult | null>(null);
  const [busy, setBusy] = useState<"" | "calc" | "excel">("");
  const [error, setError] = useState<string | null>(null);

  const body = () => ({
    land_cost_won: landEok * 1e8,
    construction_cost_won: conEok * 1e8,
    total_revenue_won: revEok * 1e8,
    construction_months: conMonths,
    sale_start_month: saleStart,
    equity_ratio: equityPct / 100,
    discount_rate_annual: discPct / 100,
  });

  const calc = async () => {
    setBusy("calc"); setError(null);
    try {
      const r = await apiClient.postV2<CashflowResult>("/feasibility/cashflow", { body: body() });
      setResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "현금흐름 산정 실패");
    } finally { setBusy(""); }
  };

  const downloadExcel = async () => {
    setBusy("excel"); setError(null);
    try {
      const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")?.trim()) || "";
      const res = await fetch(v2Url("/feasibility/cashflow/excel"), {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify(body()),
      });
      if (!res.ok) throw new Error(`다운로드 실패 (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "propai_cashflow_dcf.xlsx";
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "엑셀 다운로드 실패");
    } finally { setBusy(""); }
  };

  const s = result?.summary;
  const numCls = "h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 text-sm text-[var(--text-primary)]";

  return (
    <Card>
      <CardContent className="p-6 space-y-5">
        <div>
          <h3 className="text-base font-bold text-[var(--text-primary)]">다기간 DCF 현금흐름 (월별)</h3>
          <p className="mt-0.5 text-xs text-[var(--text-secondary)]">월별 현금흐름·IRR·NPV·최대 자금소요(peak)를 산정합니다. 값은 공사비·수지 분석에서 자동 연동되며 수정 가능합니다.</p>
        </div>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {([
            ["토지비(억)", landEok, setLandEok],
            ["공사비(억)", conEok, setConEok],
            ["분양수입(억)", revEok, setRevEok],
            ["공사기간(월)", conMonths, setConMonths],
            ["분양시작(월)", saleStart, setSaleStart],
            ["자기자본(%)", equityPct, setEquityPct],
            ["할인율(%)", discPct, setDiscPct],
          ] as Array<[string, number, (n: number) => void]>).map(([label, val, setter]) => (
            <label key={label} className="text-xs text-[var(--text-secondary)]">
              {label}
              <input type="number" className={`${numCls} mt-1`} value={val}
                onChange={(e) => setter(Number(e.target.value))} />
            </label>
          ))}
        </div>

        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={calc} disabled={busy !== ""}
            className="h-9 rounded-lg bg-[var(--accent-strong)] px-4 text-sm font-bold text-white disabled:opacity-50">
            {busy === "calc" ? "산정 중…" : "현금흐름 계산"}
          </button>
          <button type="button" onClick={downloadExcel} disabled={busy !== ""}
            className="h-9 rounded-lg border border-[var(--border)] px-4 text-sm font-semibold text-[var(--text-primary)] disabled:opacity-50">
            {busy === "excel" ? "생성 중…" : "엑셀 다운로드 ↓"}
          </button>
        </div>

        {error && <p className="text-xs font-semibold text-red-500">{error}</p>}

        {s && (
          <>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Tile label="IRR(연)" value={s.irr_annual_pct != null ? `${s.irr_annual_pct}%` : "산정불가"} accent />
              <Tile label={`NPV(할인 ${s.discount_rate_annual_pct}%)`} value={eok(s.npv_won)} />
              <Tile label="순이익" value={eok(s.net_profit)} sub={`수익률 ${s.profit_rate_pct}%`} />
              <Tile label="최대 자금소요(peak)" value={eok(s.peak_negative_cashflow)} sub={`자기자본 ${eok(s.equity_amount)}`} />
            </div>

            <div className="max-h-[360px] overflow-auto rounded-xl border border-[var(--line)]">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-[var(--surface-soft)]">
                  <tr className="text-[var(--text-hint)]">
                    {["월", "단계", "유입", "유출", "순현금", "누적"].map((h) => (
                      <th key={h} className="px-3 py-2 text-right font-bold first:text-left">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result!.rows.map((r) => (
                    <tr key={r.month} className="border-t border-[var(--line)]">
                      <td className="px-3 py-1.5 text-[var(--text-secondary)]">{r.month}</td>
                      <td className="px-3 py-1.5 text-[var(--text-secondary)]">{r.phase}</td>
                      <td className="px-3 py-1.5 text-right text-[var(--text-primary)]">{r.inflow ? eok(r.inflow) : "-"}</td>
                      <td className="px-3 py-1.5 text-right text-[var(--text-primary)]">{r.outflow ? eok(r.outflow) : "-"}</td>
                      <td className={`px-3 py-1.5 text-right font-semibold ${r.net < 0 ? "text-red-500" : "text-emerald-600"}`}>{eok(r.net)}</td>
                      <td className={`px-3 py-1.5 text-right ${r.cumulative < 0 ? "text-red-500" : "text-[var(--text-primary)]"}`}>{eok(r.cumulative)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function Tile({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: boolean }) {
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3">
      <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">{label}</p>
      <p className={`mt-1 text-lg font-[1000] ${accent ? "text-[var(--accent-strong)]" : "text-[var(--text-primary)]"}`}>{value}</p>
      {sub ? <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">{sub}</p> : null}
    </div>
  );
}
