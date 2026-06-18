"use client";

import { useCallback, useEffect, useState } from "react";
import { salesApi, won } from "@/lib/salesApi";
import { NumberInput } from "@/components/common/NumberInput";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";

interface Program { id: string; bank_name?: string; guarantee_type?: string; status: string }
interface Agreement { id: string; approved_amount?: number; status: string; program_id?: string }
interface ContractOpt { id: string; label: string; status?: string }
// POST /loan/repay 응답 계약(LoanRepayResponse). 키집합은 백엔드 Pydantic 과 1:1.
interface RepayResult { status: string; applied: number; fully_repaid: boolean; duplicate: boolean; disbursed: number; repaid: number; outstanding: number }
const IN = "rounded-lg border border-[var(--line-strong)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)]";
const BTN = "rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-sm font-bold text-white disabled:opacity-50";

export default function LoanPanel({ siteCode }: { siteCode: string }) {
  const api = salesApi(siteCode);
  const [programs, setPrograms] = useState<Program[]>([]);
  const [agreements, setAgreements] = useState<Agreement[]>([]);
  const [contracts, setContracts] = useState<ContractOpt[]>([]);
  // loaded: 데이터를 처음 한 번 불러왔는지 표시(false면 화면에 '불러오는 중' 자리표시를 보여줌).
  const [loaded, setLoaded] = useState(false);
  const [prog, setProg] = useState({ bank_name: "", guarantee_type: "HUG" });
  const [ag, setAg] = useState<{ contract_ext_id: string; program_id: string; approved_amount: number | null }>({ contract_ext_id: "", program_id: "", approved_amount: null });
  const [dis, setDis] = useState<{ agreement_id: string; installment_seq: string; amount: number | null }>({ agreement_id: "", installment_seq: "", amount: null });
  // 대출 상환 입력(약정·상환액·상환일 옵션) — POST /loan/repay 머니패스.
  const [rep, setRep] = useState<{ agreement_id: string; amount: number | null; repaid_at: string }>({ agreement_id: "", amount: null, repaid_at: "" });
  const [repRes, setRepRes] = useState<RepayResult | null>(null);
  const [msg, setMsg] = useState("");

  const load = useCallback(() => {
    // 첫 목록(은행 협약)을 다 불러오면(성공이든 실패든) 자리표시를 걷어낸다.
    api.get<Program[]>("/loan/programs").then(setPrograms).catch(() => setPrograms([])).finally(() => setLoaded(true));
    api.get<Agreement[]>("/loan/agreements").then(setAgreements).catch(() => setAgreements([]));
    api.get<ContractOpt[]>("/contracts").then((r) => setContracts(r || [])).catch(() => setContracts([]));
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
  // 대출 상환 기록(부분/전액) — 전액 상환 시 약정 status=REPAID 로 전이. 자금이동 없음.
  const repay = async () => {
    if (!rep.agreement_id || !rep.amount) { setMsg("약정과 상환액을 입력하세요."); return; }
    setRepRes(null); setMsg("");
    try {
      const r = await api.post<RepayResult>("/loan/repay", {
        agreement_id: rep.agreement_id,
        amount: rep.amount,
        repaid_at: rep.repaid_at || undefined,
      });
      setRepRes(r);
      setMsg(r.duplicate ? "이미 전액 상환된 약정입니다(추가 충당 없음)." : r.fully_repaid ? "전액 상환 완료(약정 상환완료 전이)." : "부분 상환 기록 완료.");
      setRep({ agreement_id: "", amount: null, repaid_at: "" }); load();
    } catch { setMsg("상환 기록 실패(약정·금액·권한 확인)."); }
  };

  // 아직 처음 불러오는 중이면 회색 자리표시(스켈레톤)를 보여줘 빈 화면 깜빡임을 막는다.
  if (!loaded) return <SkeletonLoader count={3} itemClassName="h-24 rounded-xl mb-3" />;
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
            {programs.length === 0 && <li className="text-[var(--text-tertiary)]">아직 등록된 은행 협약이 없습니다.</li>}
          </ul>
        </div>
        <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
          <h3 className="mb-3 font-bold text-[var(--text-primary)]">차주 약정</h3>
          <div className="flex flex-col gap-2">
            {contracts.length > 0 ? (
              <select value={ag.contract_ext_id} onChange={(e) => setAg({ ...ag, contract_ext_id: e.target.value })} className={IN}>
                <option value="">계약 선택…</option>
                {contracts.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
              </select>
            ) : (
              <input value={ag.contract_ext_id} onChange={(e) => setAg({ ...ag, contract_ext_id: e.target.value })} placeholder="계약 ID — 계약 생성 후 선택" className={IN} />
            )}
            <select value={ag.program_id} onChange={(e) => setAg({ ...ag, program_id: e.target.value })} className={IN}>
              <option value="">협약(은행) 선택…</option>
              {programs.map((p) => <option key={p.id} value={p.id}>{[p.bank_name, p.guarantee_type].filter(Boolean).join(" · ") || p.id.slice(0, 8)}</option>)}
            </select>
            <NumberInput value={ag.approved_amount} onChange={(n) => setAg({ ...ag, approved_amount: n })} placeholder="승인액(원)" className={IN} />
            <button onClick={addAg} className={BTN}>약정 추가</button>
          </div>
          <ul className="mt-3 space-y-1 text-sm text-[var(--text-secondary)]">
            {agreements.map((a) => <li key={a.id}>· {won(a.approved_amount || 0)} — {a.status} <span className="text-[10px] text-[var(--text-tertiary)]">{a.id.slice(0, 8)}</span></li>)}
            {agreements.length === 0 && <li className="text-[var(--text-tertiary)]">아직 등록된 차주 약정이 없습니다.</li>}
          </ul>
        </div>
      </div>
      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
        <h3 className="mb-3 font-bold text-[var(--text-primary)]">중도금 실행(회차 납입처리)</h3>
        <div className="flex flex-wrap items-end gap-2">
          <select value={dis.agreement_id} onChange={(e) => setDis({ ...dis, agreement_id: e.target.value })} className={IN}>
            <option value="">약정 선택…</option>
            {agreements.map((a) => <option key={a.id} value={a.id}>{won(a.approved_amount || 0)} · {a.status}</option>)}
          </select>
          <input value={dis.installment_seq} onChange={(e) => setDis({ ...dis, installment_seq: e.target.value })} type="number" placeholder="회차" className={`${IN} w-20`} />
          <NumberInput value={dis.amount} onChange={(n) => setDis({ ...dis, amount: n })} placeholder="금액(원)" className={IN} />
          <button onClick={disburse} className={BTN}>실행 기록</button>
        </div>
        {msg && <p className="mt-2 text-sm font-semibold text-emerald-400">{msg}</p>}
        <p className="mt-1 text-[11px] text-[var(--text-tertiary)]">※ 은행 실행분 기록(method=LOAN). 자금이체는 시스템이 수행하지 않습니다.</p>
      </div>
      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
        <h3 className="mb-3 font-bold text-[var(--text-primary)]">대출 상환(기록)</h3>
        <div className="flex flex-wrap items-end gap-2">
          <select value={rep.agreement_id} onChange={(e) => setRep({ ...rep, agreement_id: e.target.value })} className={IN}>
            <option value="">약정 선택…</option>
            {agreements.map((a) => <option key={a.id} value={a.id}>{won(a.approved_amount || 0)} · {a.status}</option>)}
          </select>
          <NumberInput value={rep.amount} onChange={(n) => setRep({ ...rep, amount: n })} placeholder="상환액(원)" className={IN} />
          <input value={rep.repaid_at} onChange={(e) => setRep({ ...rep, repaid_at: e.target.value })} type="date" className={`${IN} w-40`} title="상환일(선택)" />
          <button onClick={repay} className={BTN}>상환 기록</button>
        </div>
        {repRes && (
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] p-2.5 text-center"><p className="text-[10px] text-[var(--text-tertiary)]">실행 총액</p><p className="mt-0.5 text-sm font-black text-[var(--text-primary)]">{won(repRes.disbursed)}</p></div>
            <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] p-2.5 text-center"><p className="text-[10px] text-[var(--text-tertiary)]">상환 누적</p><p className="mt-0.5 text-sm font-black text-emerald-400">{won(repRes.repaid)}</p></div>
            <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] p-2.5 text-center"><p className="text-[10px] text-[var(--text-tertiary)]">미상환 잔액</p><p className="mt-0.5 text-sm font-black text-amber-400">{won(repRes.outstanding)}</p></div>
            <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] p-2.5 text-center"><p className="text-[10px] text-[var(--text-tertiary)]">상태</p><p className={`mt-0.5 text-sm font-black ${repRes.fully_repaid ? "text-emerald-400" : "text-sky-400"}`}>{repRes.fully_repaid ? "상환완료" : repRes.status}</p></div>
          </div>
        )}
        <p className="mt-1 text-[11px] text-[var(--text-tertiary)]">※ 상환 '기록'만 — 부분/전액 상환을 멱등 처리하며 전액 상환 시 약정이 상환완료로 전이됩니다.</p>
      </div>
    </div>
  );
}
