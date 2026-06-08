"use client";

/**
 * 시행사 통합 포뷰 — 다현장 포트폴리오 집계(개인정보 차단).
 * 백엔드: GET /sales/projection/summary (sales_site_summary 증분 합산, PII 없음)
 */

import { useEffect, useMemo, useState } from "react";
import { salesGlobal, won } from "@/lib/salesApi";

interface SiteSummary {
  site_id: string; site_name: string; status: string;
  visitors: number; contracts_cnt: number; contract_amt: number;
  sold_ratio: number; commission_paid: number; commission_due: number;
}

const STATUS: Record<string, string> = { PREP: "준비중", OPEN: "분양중", CLOSED: "분양종료" };

export default function DeveloperProjection() {
  const [sites, setSites] = useState<SiteSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    salesGlobal.get<SiteSummary[]>("/projection/summary")
      .then((s) => setSites(s || [])).catch(() => setSites([])).finally(() => setLoading(false));
  }, []);

  const t = useMemo(() => {
    const sum = (f: (s: SiteSummary) => number) => sites.reduce((a, s) => a + (f(s) || 0), 0);
    const visitors = sum((s) => s.visitors);
    const contracts = sum((s) => s.contracts_cnt);
    const amt = sum((s) => s.contract_amt);
    const paid = sum((s) => s.commission_paid);
    const avgSold = sites.length ? sites.reduce((a, s) => a + (s.sold_ratio || 0), 0) / sites.length : 0;
    return { count: sites.length, visitors, contracts, amt, paid, avgSold };
  }, [sites]);

  const sorted = sites.slice().sort((a, b) => (b.sold_ratio || 0) - (a.sold_ratio || 0));

  return (
    <div className="space-y-5">
      {/* 포트폴리오 집계 계기판 — 시행 관제 톤(메타라벨 + 모노 수치) */}
      <section className="cc-bracketed relative overflow-hidden rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] shadow-[var(--shadow-md)]">
        <div className="cc-grid-bg opacity-40" />
        <i className="cc-bracket cc-bracket--tl" />
        <i className="cc-bracket cc-bracket--tr" />
        <i className="cc-bracket cc-bracket--bl" />
        <i className="cc-bracket cc-bracket--br" />
        <header className="relative z-10 flex items-center justify-between gap-3 border-b border-[var(--line-subtle)] px-5 py-3">
          <span className="cc-meta">PORTFOLIO · AGGREGATE</span>
          <span className="cc-live"><i />LIVE</span>
        </header>
        <div className="relative z-10 grid grid-cols-2 gap-px bg-[var(--line-subtle)] sm:grid-cols-3 lg:grid-cols-6">
          {[
            ["현장수", "SITES", `${t.count}`, false],
            ["방문(누적)", "VISITS", `${t.visitors.toLocaleString()}명`, false],
            ["계약", "DEALS", `${t.contracts.toLocaleString()}건`, false],
            ["계약액", "CONTRACT KRW", won(t.amt), true],
            ["평균 분양률", "AVG SOLD", `${(t.avgSold * 100).toFixed(1)}%`, true],
            ["수수료 지급", "COMMISSION", won(t.paid), false],
          ].map(([k, en, v, hot]) => (
            <div key={k as string} className="bg-[var(--surface-soft)] px-4 py-4 text-center">
              <p className="cc-label text-[0.6rem] text-[var(--text-tertiary)]">{en}</p>
              <p className={`mt-1.5 cc-num text-lg font-black ${hot ? "cc-num--data" : "text-[var(--text-primary)]"}`}>{v}</p>
              <p className="mt-0.5 text-[10px] text-[var(--text-tertiary)]">{k}</p>
            </div>
          ))}
        </div>
      </section>

      {/* 현장별 (분양률 순) */}
      {loading ? (
        <p className="text-sm text-[var(--text-tertiary)]">집계를 불러오는 중…</p>
      ) : sites.length === 0 ? (
        <p className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-6 text-sm text-[var(--text-secondary)]">집계된 현장이 없습니다.</p>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-[var(--line)]">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-[var(--line)] bg-[var(--surface-strong)] text-left">
                <th className="cc-label px-3 py-2.5">현장</th><th className="cc-label px-3 py-2.5">상태</th>
                <th className="cc-label px-3 py-2.5 text-right">방문</th><th className="cc-label px-3 py-2.5 text-right">계약</th>
                <th className="cc-label px-3 py-2.5 text-right">계약액</th><th className="cc-label px-3 py-2.5">분양률</th>
                <th className="cc-label px-3 py-2.5 text-right">수수료지급</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((s) => {
                const tone = s.status === "OPEN" ? "sa-chip--success" : s.status === "CLOSED" ? "sa-chip--muted" : "sa-chip--warning";
                return (
                <tr key={s.site_id} className="border-b border-[var(--line)] transition-colors hover:bg-[var(--surface)]">
                  <td className="px-3 py-2.5 font-semibold text-[var(--text-primary)]">{s.site_name}</td>
                  <td className="px-3 py-2.5"><span className={`sa-chip ${tone}`}>{STATUS[s.status] ?? s.status}</span></td>
                  <td className="cc-num px-3 py-2.5 text-right text-[var(--text-secondary)]">{(s.visitors ?? 0).toLocaleString()}</td>
                  <td className="cc-num px-3 py-2.5 text-right text-[var(--text-secondary)]">{s.contracts_cnt ?? 0}건</td>
                  <td className="cc-num px-3 py-2.5 text-right text-[var(--text-secondary)]">{won(s.contract_amt)}</td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-[var(--surface-strong)]">
                        <div className="h-1.5 rounded-full bg-[var(--data-accent)]" style={{ width: `${Math.min(100, (s.sold_ratio ?? 0) * 100)}%` }} />
                      </div>
                      <span className="cc-num text-xs font-bold text-[var(--data-accent)]">{((s.sold_ratio ?? 0) * 100).toFixed(1)}%</span>
                    </div>
                  </td>
                  <td className="cc-num px-3 py-2.5 text-right text-[var(--text-secondary)]">{won(s.commission_paid)}</td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-[11px] text-[var(--text-hint)]">※ 개인정보(고객·방문객 명단, 계좌, 차주 식별정보)는 시행사 투영에서 제외됩니다. 집계 지표만 표시.</p>
    </div>
  );
}
