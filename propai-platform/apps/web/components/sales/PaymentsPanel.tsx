"use client";

import { useCallback, useEffect, useState } from "react";
import { salesApi, won } from "@/lib/salesApi";
import { NumberInput } from "@/components/common/NumberInput";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";

interface Overdue { id: string; overdue_days?: number; amount?: number }
interface ContractOpt { id: string; label: string; status?: string }
const IN = "rounded-lg border border-[var(--line-strong)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)]";
const BTN = "rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-sm font-bold text-white disabled:opacity-50";

export default function PaymentsPanel({ siteCode }: { siteCode: string }) {
  const api = salesApi(siteCode);
  const [va, setVa] = useState({ contract_id: "", bank: "국민", va_number: "", holder: "" });
  const [pay, setPay] = useState<{ va_number: string; amount: number | null }>({ va_number: "", amount: null });
  const [overdue, setOverdue] = useState<Overdue[]>([]);
  const [contracts, setContracts] = useState<ContractOpt[]>([]);
  const [msg, setMsg] = useState("");
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(() => {
    api.get<Overdue[]>("/payments/overdue").then(setOverdue).catch(() => setOverdue([])).finally(() => setLoaded(true));
    // 계약 선택기 목록(원시 UUID 수기입력 대체).
    api.get<ContractOpt[]>("/contracts").then((r) => setContracts(r || [])).catch(() => setContracts([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteCode]);
  useEffect(() => { load(); }, [load]);

  const issueVa = async () => {
    if (!va.contract_id || !va.va_number) { setMsg("계약 ID와 가상계좌번호가 필요합니다."); return; }
    await api.post("/payments/va/issue", va);
    setMsg("가상계좌 발급 완료"); setVa({ ...va, va_number: "", holder: "" });
  };
  const ingest = async () => {
    if (!pay.va_number || !pay.amount) return;
    const r = await api.post<{ matched: boolean }>("/payments/webhook", { va_number: pay.va_number, amount: pay.amount ?? 0 });
    setMsg(r.matched ? "입금 대사 완료(회차 충당)" : "미매칭 — 수동 대사 큐로 이동"); setPay({ va_number: "", amount: null }); load();
  };

  if (!loaded) return <SkeletonLoader count={3} itemClassName="h-24 rounded-xl mb-3" />;
  return (
   <div className="space-y-5">
    {/* #4 계약자별 통합 수납현황(납부/연체/할인/환급) */}
    <ContractSummarySection api={api} contracts={contracts} onChanged={load} />
    <div className="grid gap-5 lg:grid-cols-2">
      <div className="space-y-4">
        <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
          <h3 className="mb-3 font-bold text-[var(--text-primary)]">가상계좌 발급</h3>
          <div className="flex flex-col gap-2">
            {contracts.length > 0 ? (
              <select value={va.contract_id} onChange={(e) => setVa({ ...va, contract_id: e.target.value })} className={IN}>
                <option value="">계약 선택…</option>
                {contracts.map((c) => (
                  <option key={c.id} value={c.id}>{c.label}{c.status ? ` (${c.status})` : ""}</option>
                ))}
              </select>
            ) : (
              <input value={va.contract_id} onChange={(e) => setVa({ ...va, contract_id: e.target.value })} placeholder="계약 ID (UUID) — 계약 생성 후 선택 가능" className={IN} />
            )}
            <div className="flex gap-2">
              <input value={va.bank} onChange={(e) => setVa({ ...va, bank: e.target.value })} placeholder="은행" className={`${IN} w-24`} />
              <input value={va.va_number} onChange={(e) => setVa({ ...va, va_number: e.target.value })} placeholder="가상계좌번호" className={`${IN} flex-1`} />
            </div>
            <input value={va.holder} onChange={(e) => setVa({ ...va, holder: e.target.value })} placeholder="예금주" className={IN} />
            <button onClick={issueVa} className={BTN}>발급</button>
          </div>
        </div>
        <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
          <h3 className="mb-3 font-bold text-[var(--text-primary)]">입금 수납(대사)</h3>
          <div className="flex flex-col gap-2">
            <input value={pay.va_number} onChange={(e) => setPay({ ...pay, va_number: e.target.value })} placeholder="입금 가상계좌번호" className={IN} />
            <NumberInput value={pay.amount} onChange={(n) => setPay({ ...pay, amount: n })} placeholder="입금액(원)" className={IN} />
            <button onClick={ingest} className={BTN}>입금 대사</button>
          </div>
          <p className="mt-2 text-[11px] text-[var(--text-tertiary)]">※ 자금이동은 시스템이 수행하지 않습니다 — 입금 통지 기록·대사만.</p>
        </div>
        {msg && <p className="text-sm font-semibold text-emerald-400">{msg}</p>}
      </div>

      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
        <h3 className="mb-3 font-bold text-[var(--text-primary)]">연체 현황 ({overdue.length})</h3>
        <table className="w-full text-sm">
          <thead><tr className="border-b border-[var(--line)] text-left text-[var(--text-secondary)]"><th className="py-1">연체일수</th><th className="text-right">연체이자</th></tr></thead>
          <tbody>
            {overdue.map((o) => (
              <tr key={o.id} className="border-b border-[var(--line)] text-[var(--text-primary)]">
                <td className="py-1">{o.overdue_days ?? 0}일</td>
                <td className="text-right text-rose-400">{won(o.amount || 0)}</td>
              </tr>
            ))}
            {overdue.length === 0 && <tr><td colSpan={2} className="py-3 text-[var(--text-tertiary)]">연체 없음</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
   </div>
  );
}

type SummaryT = {
  total_price: number;
  installments: { count: number; billed: number; paid: number; unpaid: number };
  overdue: { count: number; unpaid_amount: number };
  discount: { count: number; amount: number };
  refund: { count: number; amount: number };
};

type InstRow = {
  seq: number; kind_label: string; amount: number; paid_amount: number; unpaid: number;
  due_date: string | null; paid_at: string | null; status: string;
  overdue_days: number; overdue_interest: number;
};
type InstResp = {
  installments: InstRow[]; overdue_rate: number; as_of: string;
  totals: { billed: number; paid: number; unpaid: number; overdue_interest: number };
};
// 회차 상태 배지(라벨·색).
const INST_STATUS: Record<string, { label: string; cls: string }> = {
  PAID: { label: "완납", cls: "text-emerald-400" },
  PARTIAL: { label: "부분납", cls: "text-sky-400" },
  UNPAID: { label: "납부예정", cls: "text-[var(--text-secondary)]" },
  OVERDUE: { label: "연체", cls: "text-rose-400 font-bold" },
};

// 계약자(계약) 기준 통합 수납현황 + 할인/환급 등록.
function ContractSummarySection({ api, contracts, onChanged }: {
  api: ReturnType<typeof salesApi>; contracts: { id: string; label: string; status?: string }[]; onChanged: () => void;
}) {
  const [cid, setCid] = useState("");
  const [sum, setSum] = useState<SummaryT | null>(null);
  const [inst, setInst] = useState<InstResp | null>(null);
  const [busy, setBusy] = useState(false);
  const [adj, setAdj] = useState<{ type: "DISCOUNT" | "REFUND"; amount: number | null; reason: string }>({ type: "DISCOUNT", amount: null, reason: "" });
  const [msg, setMsg] = useState("");

  const loadSummary = async (id: string) => {
    setCid(id); setSum(null); setInst(null); setMsg("");
    if (!id) return;
    try {
      // 통합현황 + 회차 스케줄을 함께 조회(계약금·중도금·잔금 회차별 상태·연체).
      const [s, i] = await Promise.all([
        api.get<SummaryT>(`/payments/contract-summary?contract_id=${id}`),
        api.get<InstResp>(`/payments/installments?contract_id=${id}`).catch(() => null),
      ]);
      setSum(s); setInst(i);
    } catch { setMsg("현황 조회 실패(계약 확인)."); }
  };
  const addAdj = async () => {
    if (!cid || !adj.amount) { setMsg("계약과 금액을 입력하세요."); return; }
    setBusy(true); setMsg("");
    try {
      await api.post("/payments/adjustment", { contract_ext_id: cid, adj_type: adj.type, amount: adj.amount, reason: adj.reason || undefined });
      setAdj({ ...adj, amount: null, reason: "" }); await loadSummary(cid); onChanged();
    } catch { setMsg("등록 실패(권한 확인)."); }
    finally { setBusy(false); }
  };

  const Card = ({ label, value, tone }: { label: string; value: string; tone?: string }) => (
    <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] p-2.5 text-center">
      <p className="text-[10px] text-[var(--text-tertiary)]">{label}</p>
      <p className={`mt-0.5 text-sm font-black ${tone || "text-[var(--text-primary)]"}`}>{value}</p>
    </div>
  );

  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
      <h3 className="mb-3 font-bold text-[var(--text-primary)]">계약자별 수납 현황</h3>
      <select value={cid} onChange={(e) => loadSummary(e.target.value)} className={`${IN} w-full`}>
        <option value="">계약자(계약) 선택…</option>
        {contracts.map((c) => <option key={c.id} value={c.id}>{c.label}{c.status ? ` (${c.status})` : ""}</option>)}
      </select>
      {sum && (
        <>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            <Card label="분양가" value={won(sum.total_price)} />
            <Card label="청구" value={won(sum.installments.billed)} />
            <Card label="납부" value={won(sum.installments.paid)} tone="text-emerald-400" />
            <Card label="미납" value={won(sum.installments.unpaid)} tone="text-amber-400" />
            <Card label={`연체(${sum.overdue.count})`} value={won(sum.overdue.unpaid_amount)} tone="text-rose-400" />
            <Card label={`할인/환급`} value={`${won(sum.discount.amount)} / ${won(sum.refund.amount)}`} />
          </div>
          {/* 회차별 납부 스케줄 — 계약금·중도금·잔금 회차의 약정일·납부·미납·상태·연체(실시간) */}
          {inst && inst.installments.length > 0 && (
            <div className="mt-3 overflow-x-auto rounded-lg border border-[var(--line)]">
              <table className="w-full text-xs">
                <thead><tr className="border-b border-[var(--line)] bg-[var(--surface-strong)] text-left text-[var(--text-secondary)]">
                  <th className="px-2 py-1.5">회차</th><th className="px-2 py-1.5">구분</th><th className="px-2 py-1.5">약정일</th>
                  <th className="px-2 py-1.5 text-right">금액</th><th className="px-2 py-1.5 text-right">납부</th>
                  <th className="px-2 py-1.5 text-right">미납</th><th className="px-2 py-1.5 text-center">상태</th>
                  <th className="px-2 py-1.5 text-right">연체</th>
                </tr></thead>
                <tbody>
                  {inst.installments.map((r) => (
                    <tr key={r.seq} className="border-b border-[var(--line)] text-[var(--text-primary)]">
                      <td className="px-2 py-1.5">{r.seq}</td>
                      <td className="px-2 py-1.5">{r.kind_label}</td>
                      <td className="px-2 py-1.5 text-[var(--text-secondary)]">{r.due_date ?? "-"}</td>
                      <td className="px-2 py-1.5 text-right">{won(r.amount)}</td>
                      <td className="px-2 py-1.5 text-right text-emerald-400">{won(r.paid_amount)}</td>
                      <td className="px-2 py-1.5 text-right text-amber-400">{won(r.unpaid)}</td>
                      <td className={`px-2 py-1.5 text-center ${INST_STATUS[r.status]?.cls ?? ""}`}>{INST_STATUS[r.status]?.label ?? r.status}</td>
                      <td className="px-2 py-1.5 text-right text-rose-400">{r.overdue_days > 0 ? `${r.overdue_days}일 · ${won(r.overdue_interest)}` : "-"}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot><tr className="bg-[var(--surface-strong)] font-bold text-[var(--text-primary)]">
                  <td className="px-2 py-1.5" colSpan={3}>합계 · 연체이율 {(inst.overdue_rate * 100).toFixed(1)}% (기준 {inst.as_of})</td>
                  <td className="px-2 py-1.5 text-right">{won(inst.totals.billed)}</td>
                  <td className="px-2 py-1.5 text-right text-emerald-400">{won(inst.totals.paid)}</td>
                  <td className="px-2 py-1.5 text-right text-amber-400">{won(inst.totals.unpaid)}</td>
                  <td className="px-2 py-1.5" />
                  <td className="px-2 py-1.5 text-right text-rose-400">{won(inst.totals.overdue_interest)}</td>
                </tr></tfoot>
              </table>
            </div>
          )}
          {inst && inst.installments.length === 0 && (
            <p className="mt-3 text-xs text-[var(--text-tertiary)]">회차 스케줄이 없습니다 — 계약 서명 시 자동 생성됩니다.</p>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-[var(--line)] pt-3">
            <select value={adj.type} onChange={(e) => setAdj({ ...adj, type: e.target.value as "DISCOUNT" | "REFUND" })} className={`${IN} py-1`}>
              <option value="DISCOUNT">할인</option><option value="REFUND">환급</option>
            </select>
            <NumberInput value={adj.amount} onChange={(n) => setAdj({ ...adj, amount: n })} placeholder="금액(원)" className={`${IN} w-32 py-1`} />
            <input value={adj.reason} onChange={(e) => setAdj({ ...adj, reason: e.target.value })} placeholder="사유(선택)" className={`${IN} flex-1 py-1`} />
            <button onClick={addAdj} disabled={busy} className={BTN}>{busy ? "등록 중…" : "등록"}</button>
          </div>
        </>
      )}
      {msg && <p className="mt-2 text-xs text-[var(--text-tertiary)]">{msg}</p>}
    </div>
  );
}
