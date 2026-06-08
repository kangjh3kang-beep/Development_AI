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
  );
}
