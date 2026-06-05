"use client";

import { useCallback, useEffect, useState } from "react";
import { salesApi, won } from "@/lib/salesApi";
import { NumberInput } from "@/components/common/NumberInput";

interface Program { id: string; bank_name?: string; guarantee_type?: string; status: string }
interface Agreement { id: string; approved_amount?: number; status: string; program_id?: string }
const IN = "rounded-lg border border-[var(--line-strong)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)]";
const BTN = "rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-sm font-bold text-white disabled:opacity-50";

export default function LoanPanel({ siteCode }: { siteCode: string }) {
  const api = salesApi(siteCode);
  const [programs, setPrograms] = useState<Program[]>([]);
  const [agreements, setAgreements] = useState<Agreement[]>([]);
  const [prog, setProg] = useState({ bank_name: "", guarantee_type: "HUG" });
  const [ag, setAg] = useState<{ contract_ext_id: string; program_id: string; approved_amount: number | null }>({ contract_ext_id: "", program_id: "", approved_amount: null });
  const [dis, setDis] = useState<{ agreement_id: string; installment_seq: string; amount: number | null }>({ agreement_id: "", installment_seq: "", amount: null });
  const [msg, setMsg] = useState("");

  const load = useCallback(() => {
    api.get<Program[]>("/loan/programs").then(setPrograms).catch(() => setPrograms([]));
    api.get<Agreement[]>("/loan/agreements").then(setAgreements).catch(() => setAgreements([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteCode]);
  useEffect(() => { load(); }, [load]);

  const addProg = async () => { if (!prog.bank_name) return; await api.post("/loan/programs", { ...prog, status: "ACTIVE" }); setProg({ bank_name: "", guarantee_type: "HUG" }); load(); };
  const addAg = async () => { if (!ag.contract_ext_id || !ag.program_id) return; await api.post("/loan/agreements", { contract_ext_id: ag.contract_ext_id, program_id: ag.program_id, approved_amount: ag.approved_amount ?? 0, status: "APPROVED" }); setAg({ contract_ext_id: "", program_id: "", approved_amount: null }); load(); };
  const disburse = async () => {
    if (!dis.agreement_id) return;
    await api.post("/loan/disburse", { agreement_id: dis.agreement_id, installment_seq: Number(dis.installment_seq), amount: dis.amount ?? 0 });
    setMsg("실행 기록 완료(회차 납입처리)"); setDis({ agreement_id: "", installment_seq: "", amount: null }); load();
  };

  return (
    <div className="space-y-5">
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
          <h3 className="mb-3 font-bold text-[var(--text-primary)]">대출 협약(은행)</h3>
          <div className="flex flex-wrap items-end gap-2">
            <input value={prog.bank_name} onChange={(e) => setProg({ ...prog, bank_name: e.target.value })} placeholder="은행명" className={IN} />
            <select value={prog.guarantee_type} onChange={(e) => setProg({ ...prog, guarantee_type: e.target.value })} className={IN}>
              {["HUG", "HF", "NONE"].map((g) => <option key={g} value={g}>{g}</option>)}
            </select>
            <button onClick={addProg} className={BTN}>협약 추가</button>
          </div>
          <ul className="mt-3 space-y-1 text-sm text-[var(--text-secondary)]">
            {programs.map((p) => <li key={p.id}>· {p.bank_name} ({p.guarantee_type}) — {p.status} <span className="text-[10px] text-[var(--text-tertiary)]">{p.id.slice(0, 8)}</span></li>)}
          </ul>
        </div>
        <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
          <h3 className="mb-3 font-bold text-[var(--text-primary)]">차주 약정</h3>
          <div className="flex flex-col gap-2">
            <input value={ag.contract_ext_id} onChange={(e) => setAg({ ...ag, contract_ext_id: e.target.value })} placeholder="계약 ID" className={IN} />
            <input value={ag.program_id} onChange={(e) => setAg({ ...ag, program_id: e.target.value })} placeholder="협약 ID" className={IN} />
            <NumberInput value={ag.approved_amount} onChange={(n) => setAg({ ...ag, approved_amount: n })} placeholder="승인액(원)" className={IN} />
            <button onClick={addAg} className={BTN}>약정 추가</button>
          </div>
          <ul className="mt-3 space-y-1 text-sm text-[var(--text-secondary)]">
            {agreements.map((a) => <li key={a.id}>· {won(a.approved_amount || 0)} — {a.status} <span className="text-[10px] text-[var(--text-tertiary)]">{a.id.slice(0, 8)}</span></li>)}
          </ul>
        </div>
      </div>
      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
        <h3 className="mb-3 font-bold text-[var(--text-primary)]">중도금 실행(회차 납입처리)</h3>
        <div className="flex flex-wrap items-end gap-2">
          <input value={dis.agreement_id} onChange={(e) => setDis({ ...dis, agreement_id: e.target.value })} placeholder="약정 ID" className={IN} />
          <input value={dis.installment_seq} onChange={(e) => setDis({ ...dis, installment_seq: e.target.value })} type="number" placeholder="회차" className={`${IN} w-20`} />
          <NumberInput value={dis.amount} onChange={(n) => setDis({ ...dis, amount: n })} placeholder="금액(원)" className={IN} />
          <button onClick={disburse} className={BTN}>실행 기록</button>
        </div>
        {msg && <p className="mt-2 text-sm font-semibold text-emerald-400">{msg}</p>}
        <p className="mt-1 text-[11px] text-[var(--text-tertiary)]">※ 은행 실행분 기록(method=LOAN). 자금이체는 시스템이 수행하지 않습니다.</p>
      </div>
    </div>
  );
}
