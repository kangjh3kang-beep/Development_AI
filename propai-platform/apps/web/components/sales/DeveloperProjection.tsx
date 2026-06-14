"use client";

/**
 * 분양관리요약(관리자) — 시행사 통합 관제.
 *  ① 포트폴리오 집계(방문·계약·분양률·수수료, 개인정보 차단)
 *  ② 시행사 통합회계(연결결산): 보유 현장 ERP 원장을 유기적으로 합산(매출−비용−수수료=손익)
 *  ③ 현장별 드릴다운: 담당자·근태·계약·매출·수수료·방문·광고·회계 + 회계항목 직접 등록
 * 백엔드: GET /sales/projection/summary · GET /sales/projection/accounting-rollup ·
 *         GET /sales/admin/site-detail · POST /sales/accounting/entry (현장 헤더=site_id UUID 허용)
 */

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { salesApi, salesGlobal, won } from "@/lib/salesApi";

interface SiteSummary {
  site_id: string; site_name: string; status: string;
  visitors: number; contracts_cnt: number; contract_amt: number;
  sold_ratio: number; commission_paid: number; commission_due: number;
}
interface ByType { label: string; amount: number; type?: string }
interface RollupSite { site_id: string; site_name: string; status: string; revenue: number; cost_total: number; commission: number; profit_estimate: number; by_type: ByType[] }
interface Rollup { consolidated: { revenue: number; cost_total: number; commission: number; profit_estimate: number; by_type: ByType[] }; sites: RollupSite[]; note: string }

const STATUS: Record<string, string> = { PREP: "준비중", OPEN: "분양중", CLOSED: "분양종료" };
const ENTRY_TYPES = [
  { v: "LABOR", l: "인건비" }, { v: "EXPENSE", l: "경비" }, { v: "UTILITY", l: "공과금" },
  { v: "AD", l: "광고비" }, { v: "ETC", l: "기타" },
];
const fcls = "rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1.5 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]";

export default function DeveloperProjection() {
  const [sites, setSites] = useState<SiteSummary[]>([]);
  const [roll, setRoll] = useState<Rollup | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<string | null>(null);

  const loadRoll = useCallback(() => {
    salesGlobal.get<Rollup>("/projection/accounting-rollup").then(setRoll).catch(() => setRoll(null));
  }, []);
  useEffect(() => {
    salesGlobal.get<SiteSummary[]>("/projection/summary")
      .then((s) => setSites(s || [])).catch(() => setSites([])).finally(() => setLoading(false));
    loadRoll();
  }, [loadRoll]);

  const t = useMemo(() => {
    const sum = (f: (s: SiteSummary) => number) => sites.reduce((a, s) => a + (f(s) || 0), 0);
    const avgSold = sites.length ? sites.reduce((a, s) => a + (s.sold_ratio || 0), 0) / sites.length : 0;
    return { count: sites.length, visitors: sum((s) => s.visitors), contracts: sum((s) => s.contracts_cnt), amt: sum((s) => s.contract_amt), paid: sum((s) => s.commission_paid), avgSold };
  }, [sites]);

  const sorted = sites.slice().sort((a, b) => (b.sold_ratio || 0) - (a.sold_ratio || 0));
  const con = roll?.consolidated;

  return (
    <div className="space-y-5">
      {/* ① 포트폴리오 집계 계기판 */}
      <section className="cc-bracketed relative overflow-hidden rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] shadow-[var(--shadow-md)]">
        <div className="cc-grid-bg opacity-40" />
        <i className="cc-bracket cc-bracket--tl" /><i className="cc-bracket cc-bracket--tr" />
        <i className="cc-bracket cc-bracket--bl" /><i className="cc-bracket cc-bracket--br" />
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

      {/* ② 시행사 통합회계(연결결산) — 현장 ERP 원장 유기적 합산 */}
      {con && (
        <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
          <div className="mb-3 flex items-center justify-between">
            <span className="cc-meta">CONSOLIDATED P&amp;L · 통합회계(연결결산)</span>
            <span className="text-[10px] text-[var(--text-hint)]">현장 ERP 원장 단일출처 합산</span>
          </div>
          <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl bg-[var(--line-subtle)] sm:grid-cols-4">
            {[
              ["매출(계약)", won(con.revenue), "text-[var(--text-primary)]"],
              ["회계비용", won(con.cost_total), "text-[var(--text-secondary)]"],
              ["수수료배분", won(con.commission), "text-[var(--text-secondary)]"],
              ["손익(개략)", won(con.profit_estimate), con.profit_estimate >= 0 ? "text-[var(--success)]" : "text-[var(--error)]"],
            ].map(([k, v, cls]) => (
              <div key={k} className="bg-[var(--surface-soft)] px-4 py-3 text-center">
                <p className="cc-label text-[0.6rem] text-[var(--text-tertiary)]">{k}</p>
                <p className={`mt-1 cc-num text-base font-black ${cls}`}>{v}</p>
              </div>
            ))}
          </div>
          {con.by_type.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {con.by_type.map((b) => (
                <span key={b.label} className="sa-chip sa-chip--muted text-[11px]">{b.label} <b className="ml-1 text-[var(--text-primary)]">{won(b.amount)}</b></span>
              ))}
            </div>
          )}
          <p className="mt-2 text-[10px] text-[var(--text-hint)]">{roll?.note}</p>
        </section>
      )}

      {/* ③ 현장별 — 클릭 시 통합 관리 드릴다운(담당자·근태·회계 + 회계 등록) */}
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
                <th className="cc-label px-3 py-2.5 text-right">수수료지급</th><th className="cc-label px-3 py-2.5 text-right">관리</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((s) => {
                const tone = s.status === "OPEN" ? "sa-chip--success" : s.status === "CLOSED" ? "sa-chip--muted" : "sa-chip--warning";
                const isOpen = open === s.site_id;
                return (
                <Fragment key={s.site_id}>
                <tr className="border-b border-[var(--line)] transition-colors hover:bg-[var(--surface)]">
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
                  <td className="px-3 py-2.5 text-right">
                    <button onClick={() => setOpen(isOpen ? null : s.site_id)} className="rounded-lg border border-[var(--line)] px-2 py-1 text-[11px] font-bold text-[var(--accent-strong)] hover:bg-[var(--accent-soft)]">{isOpen ? "닫기" : "관리 ▾"}</button>
                  </td>
                </tr>
                {isOpen && (
                  <tr key={`${s.site_id}-d`} className="border-b border-[var(--line)] bg-[var(--surface)]">
                    <td colSpan={8} className="px-3 py-3"><SiteManagePanel siteId={s.site_id} onSaved={loadRoll} /></td>
                  </tr>
                )}
                </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-[11px] text-[var(--text-hint)]">※ 개인정보(고객·방문객 명단, 계좌, 차주 식별정보)는 시행사 투영에서 제외됩니다. 집계·회계 지표만 표시.</p>
    </div>
  );
}

/** 현장 1곳 통합 관리 드릴다운 — 담당자·근태·계약·매출·수수료·방문·광고·회계 + 회계항목 등록. */
function SiteManagePanel({ siteId, onSaved }: { siteId: string; onSaved: () => void }) {
  // X-Site-Code 헤더에 site_id(UUID)를 넘기면 백엔드 resolve_site 가 UUID로 현장을 해석한다.
  const api = useMemo(() => salesApi(siteId), [siteId]);
  type Detail = { staff_assigned: number; contracts: number; revenue: number; commission: number; visitors: number; attendance_today: number; ad_budget: number; accounting: { by_type: ByType[]; cost_total: number }; profit_estimate: number };
  const [d, setD] = useState<Detail | null>(null);
  const [err, setErr] = useState(false);
  const [et, setEt] = useState("LABOR");
  const [amt, setAmt] = useState("");
  const [memo, setMemo] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get<Detail>("/admin/site-detail").then(setD).catch(() => setErr(true));
  }, [api]);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    const n = Math.round(Number(amt));
    if (!n || n <= 0) { alert("금액(양수)을 입력하세요."); return; }
    setBusy(true);
    try {
      await api.post("/accounting/entry", { entry_type: et, amount: n, memo: memo.trim() || undefined });
      setAmt(""); setMemo(""); load(); onSaved();
    } catch { alert("회계 등록 실패(권한을 확인하세요)."); }
    finally { setBusy(false); }
  };

  if (err) return <p className="text-xs text-[var(--text-hint)]">상세를 불러올 수 없습니다(현장 접근 권한 확인).</p>;
  if (!d) return <p className="text-xs text-[var(--text-tertiary)]">현장 상세를 불러오는 중…</p>;
  const metric = (k: string, v: string) => (
    <div className="rounded-lg bg-[var(--surface-soft)] px-3 py-2 text-center"><p className="cc-label text-[0.55rem] text-[var(--text-tertiary)]">{k}</p><p className="mt-0.5 cc-num text-sm font-bold text-[var(--text-primary)]">{v}</p></div>
  );
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-8">
        {metric("담당자", `${d.staff_assigned}명`)}
        {metric("오늘출근", `${d.attendance_today}명`)}
        {metric("계약", `${d.contracts}건`)}
        {metric("매출", won(d.revenue))}
        {metric("수수료", won(d.commission))}
        {metric("방문", `${d.visitors}`)}
        {metric("광고예산", won(d.ad_budget))}
        {metric("손익", won(d.profit_estimate))}
      </div>
      {/* 회계 원장 — 항목별 비용 + 직접 등록 */}
      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="cc-label text-[0.6rem] text-[var(--text-tertiary)]">회계 원장 · 비용 {won(d.accounting.cost_total)}</span>
          {d.accounting.by_type.map((b) => (
            <span key={b.type || b.label} className="sa-chip sa-chip--muted text-[10px]">{b.label} {won(b.amount)}</span>
          ))}
          {d.accounting.by_type.length === 0 && <span className="text-[11px] text-[var(--text-hint)]">등록된 회계 항목이 없습니다.</span>}
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1"><span className="text-[10px] text-[var(--text-tertiary)]">항목</span>
            <select value={et} onChange={(e) => setEt(e.target.value)} className={`${fcls} w-28`}>
              {ENTRY_TYPES.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1"><span className="text-[10px] text-[var(--text-tertiary)]">금액(원)</span>
            <input value={amt} onChange={(e) => setAmt(e.target.value.replace(/[^0-9]/g, ""))} placeholder="예: 3000000" className={`${fcls} w-32`} inputMode="numeric" />
          </label>
          <label className="flex flex-1 flex-col gap-1"><span className="text-[10px] text-[var(--text-tertiary)]">메모</span>
            <input value={memo} onChange={(e) => setMemo(e.target.value)} placeholder="예: 6월 사무실 임대료" className={`${fcls} min-w-[140px]`} onKeyDown={(e) => { if (e.key === "Enter") void save(); }} />
          </label>
          <button onClick={save} disabled={busy} className="rounded-lg bg-[var(--accent-strong)] px-4 py-2 text-sm font-black text-white disabled:opacity-50">＋ 회계등록</button>
        </div>
      </div>
      {/* 급여(근태×단가) + 광고 ROI */}
      <PayrollAdSection siteId={siteId} onPosted={() => { load(); onSaved(); }} />
    </div>
  );
}

/** 급여 자동산정(근태×단가) + 회계 인건비 전기 + 광고 ROI. */
function PayrollAdSection({ siteId, onPosted }: { siteId: string; onPosted: () => void }) {
  const api = useMemo(() => salesApi(siteId), [siteId]);
  const thisMonth = new Date().toISOString().slice(0, 7);
  type PayStaff = { staff_id: string; name: string; position?: string | null; days: number; hours: number; wage_type: string; wage_label: string; base_wage: number; amount: number; wage_set: boolean };
  type Payroll = { year_month: string; staff: PayStaff[]; headcount: number; total_payroll: number; note: string };
  type Roi = { budget: number; spend: number; leads: number; visitors: number; contracts: number; cost_per_lead: number; cost_per_visitor: number; cost_per_contract: number; note: string };
  const [ym, setYm] = useState(thisMonth);
  const [pay, setPay] = useState<Payroll | null>(null);
  const [roi, setRoi] = useState<Roi | null>(null);
  const [busy, setBusy] = useState(false);

  const loadPay = useCallback((m: string) => { api.get<Payroll>(`/payroll?ym=${m}`).then(setPay).catch(() => setPay(null)); }, [api]);
  useEffect(() => { loadPay(ym); api.get<Roi>("/ad/roi").then(setRoi).catch(() => setRoi(null)); }, [loadPay, ym, api]);

  const setWage = async (staffId: string, wageType: string, baseWage: number) => {
    try { await api.post("/staff/wage", { staff_id: staffId, wage_type: wageType, base_wage: baseWage }); loadPay(ym); }
    catch { alert("단가 저장 실패(권한 확인)."); }
  };
  const post = async () => {
    if (!pay || pay.total_payroll <= 0) { alert("산정 급여가 0원입니다(단가·근태 확인)."); return; }
    if (!confirm(`${ym} 급여 ${won(pay.total_payroll)}을 회계 인건비로 전기할까요?`)) return;
    setBusy(true);
    try {
      const r = await api.post<{ ok: boolean; reason?: string }>("/payroll/post", { ym });
      if (r?.ok) { alert("회계 인건비로 전기되었습니다."); onPosted(); } else alert(r?.reason || "전기 실패");
    } catch { alert("전기 실패(권한 확인)."); }
    finally { setBusy(false); }
  };

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {/* 급여 */}
      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <span className="cc-label text-[0.6rem] text-[var(--text-tertiary)]">급여(근태×단가) {pay ? `· 합계 ${won(pay.total_payroll)}` : ""}</span>
          <div className="flex items-center gap-1">
            <input type="month" value={ym} onChange={(e) => setYm(e.target.value)} className={`${fcls} px-1 py-0.5 text-xs`} />
            <button onClick={post} disabled={busy || !pay || pay.total_payroll <= 0} className="rounded-lg border border-[var(--accent-strong)] px-2 py-1 text-[11px] font-bold text-[var(--accent-strong)] disabled:opacity-40">인건비 전기</button>
          </div>
        </div>
        {!pay || pay.staff.length === 0 ? (
          <p className="text-[11px] text-[var(--text-hint)]">직원/근태 데이터가 없습니다. 직원 등록·출퇴근 기록 후 산정됩니다.</p>
        ) : (
          <div className="max-h-44 overflow-auto">
            <table className="w-full text-[11px]">
              <thead><tr className="text-[var(--text-hint)]"><th className="text-left font-medium">직원</th><th className="text-right font-medium">출근</th><th className="text-right font-medium">시간</th><th className="text-left font-medium">단가</th><th className="text-right font-medium">급여</th></tr></thead>
              <tbody>
                {pay.staff.slice(0, 30).map((p) => (
                  <tr key={p.staff_id} className="border-t border-[var(--line)]/50">
                    <td className="py-0.5 text-[var(--text-secondary)]">{p.name}{!p.wage_set && <span className="ml-1 text-[9px] text-[var(--warning)]">단가미설정</span>}</td>
                    <td className="text-right text-[var(--text-primary)]">{p.days}일</td>
                    <td className="text-right text-[var(--text-tertiary)]">{p.hours}h</td>
                    <td>
                      <div className="flex items-center gap-1">
                        <select defaultValue={p.wage_type} onChange={(e) => setWage(p.staff_id, e.target.value, p.base_wage)} className="rounded border border-[var(--line)] bg-[var(--surface-strong)] px-1 py-0.5 text-[10px]">
                          <option value="DAILY">일급</option><option value="HOURLY">시급</option><option value="MONTHLY">월급</option>
                        </select>
                        <input defaultValue={p.base_wage || ""} placeholder="단가" onBlur={(e) => { const v = Math.round(Number(e.target.value.replace(/[^0-9]/g, ""))); if (v !== p.base_wage) void setWage(p.staff_id, p.wage_type, v); }} className="w-16 rounded border border-[var(--line)] bg-[var(--surface-strong)] px-1 py-0.5 text-[10px]" inputMode="numeric" />
                      </div>
                    </td>
                    <td className="text-right font-bold text-[var(--text-primary)]">{won(p.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {/* 광고 ROI */}
      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
        <div className="mb-2"><span className="cc-label text-[0.6rem] text-[var(--text-tertiary)]">광고 ROI(집행비 대비 효율)</span></div>
        {!roi ? <p className="text-[11px] text-[var(--text-hint)]">광고 데이터가 없습니다.</p> : (
          <div className="space-y-2">
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-lg bg-[var(--surface)] px-2 py-1.5"><p className="cc-label text-[0.5rem] text-[var(--text-tertiary)]">예산</p><p className="cc-num text-xs font-bold text-[var(--text-primary)]">{won(roi.budget)}</p></div>
              <div className="rounded-lg bg-[var(--surface)] px-2 py-1.5"><p className="cc-label text-[0.5rem] text-[var(--text-tertiary)]">실집행</p><p className="cc-num text-xs font-bold text-[var(--text-primary)]">{won(roi.spend)}</p></div>
              <div className="rounded-lg bg-[var(--surface)] px-2 py-1.5"><p className="cc-label text-[0.5rem] text-[var(--text-tertiary)]">계약</p><p className="cc-num text-xs font-bold text-[var(--text-primary)]">{roi.contracts}건</p></div>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <span className="sa-chip sa-chip--muted text-[10px]">리드 {roi.leads} · 건당 {won(roi.cost_per_lead)}</span>
              <span className="sa-chip sa-chip--muted text-[10px]">방문 {roi.visitors} · 건당 {won(roi.cost_per_visitor)}</span>
              <span className="sa-chip sa-chip--muted text-[10px]">계약 건당 {won(roi.cost_per_contract)}</span>
            </div>
            <p className="text-[10px] text-[var(--text-hint)]">{roi.note}</p>
          </div>
        )}
      </div>
    </div>
  );
}
