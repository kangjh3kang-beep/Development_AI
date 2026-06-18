"use client";

import { useCallback, useEffect, useState } from "react";
import { salesApi, won } from "@/lib/salesApi";
import { NumberInput } from "@/components/common/NumberInput";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";

interface Overdue { id: string; overdue_days?: number; amount?: number }
interface ContractOpt { id: string; label: string; status?: string }
// 입금 큐 행 — GET /payments/unmatched(미대사) 및 ?status=MATCHED(매칭완료) 공용 형식.
interface Unmatched { id: string; method?: string; amount: number; paid_at: string | null; raw_ref?: string | null; contract?: string | null }
// 입금 대사(webhook) 응답계약 — 백엔드 PaymentIngestResponse 와 1:1(SSOT). 분기마다 같은 키집합.
// allocated=회차 실제 충당 합계, unapplied=충당 못 한 잔여. status: MATCHED/UNMATCHED/SURPLUS(과오납).
interface PaymentIngestResponse { matched: boolean; status: string; duplicate?: boolean; contract?: string | null; allocated: number; unapplied: number }
const IN = "rounded-lg border border-[var(--line-strong)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)]";
const BTN = "rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-sm font-bold text-white disabled:opacity-50";

export default function PaymentsPanel({ siteCode }: { siteCode: string }) {
  const api = salesApi(siteCode);
  const [va, setVa] = useState({ contract_id: "", bank: "국민", va_number: "", holder: "" });
  const [pay, setPay] = useState<{ va_number: string; amount: number | null }>({ va_number: "", amount: null });
  const [overdue, setOverdue] = useState<Overdue[]>([]);
  const [contracts, setContracts] = useState<ContractOpt[]>([]);
  const [unmatched, setUnmatched] = useState<Unmatched[]>([]);
  // 매칭완료(MATCHED) 입금 목록 — 회차별 정확 역배분(reverse)의 실제 대상이라 화면에 노출한다.
  const [matched, setMatched] = useState<Unmatched[]>([]);
  const [msg, setMsg] = useState("");
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(() => {
    api.get<Overdue[]>("/payments/overdue").then(setOverdue).catch(() => setOverdue([])).finally(() => setLoaded(true));
    // 계약 선택기 목록(원시 UUID 수기입력 대체).
    api.get<ContractOpt[]>("/contracts").then((r) => setContracts(r || [])).catch(() => setContracts([]));
    // 미대사 입금 큐(취소·수동매칭 대상).
    api.get<{ items: Unmatched[] }>("/payments/unmatched").then((r) => setUnmatched(r.items || [])).catch(() => setUnmatched([]));
    // 매칭완료 입금 목록(회차별 역배분 취소 대상). 같은 엔드포인트의 status 필터 재사용.
    api.get<{ items: Unmatched[] }>("/payments/unmatched?status=MATCHED").then((r) => setMatched(r.items || [])).catch(() => setMatched([]));
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
    // 입금 대사 응답 전체(allocated/unapplied/status 포함)로 정확히 타이핑한다 — allocated==0 이면
    // '회차 충당' 문구를 쓰지 않고 과오납(SURPLUS)/미매칭을 정직하게 안내한다(loan 의 disbursed/
    // repaid/outstanding 노출과 대칭). matched 만으론 과오납을 구분 못 해 거짓 표기될 수 있었다.
    const r = await api.post<PaymentIngestResponse>("/payments/webhook", { va_number: pay.va_number, amount: pay.amount ?? 0 });
    if (r.allocated > 0) {
      setMsg(`입금 대사 완료 — 회차 충당 ${won(r.allocated)}${r.unapplied > 0 ? ` · 미충당 잔여 ${won(r.unapplied)}` : ""}`);
    } else if (r.status === "SURPLUS") {
      // VA 는 있으나 모든 회차가 완납 → 회차에 못 들어간 과오납. '회차 충당' 문구 금지.
      setMsg(`과오납(SURPLUS) — 충당된 회차 없음, 미충당 잔여 ${won(r.unapplied)}원(환급/재배정 대상)`);
    } else {
      setMsg(`미매칭 — 수동 대사 큐로 이동 (미충당 ${won(r.unapplied)})`);
    }
    setPay({ va_number: "", amount: null }); load();
  };
  // 연체이자 즉시 재계산 — 일배치를 기다리지 않고 현재 현장 미납 회차를 지금 기준으로 재산정.
  const [recalc, setRecalc] = useState(false);
  const runOverdue = async () => {
    setRecalc(true); setMsg("");
    try {
      const r = await api.post<{ rows: number; as_of: string; locked: boolean }>("/payments/run-overdue");
      setMsg(r.locked ? `연체 재계산 완료 — ${r.rows}건 (기준 ${r.as_of})` : "일배치가 산정 중입니다 — 곧 반영됩니다.");
      load();
    } catch { setMsg("연체 재계산 실패(권한 확인)."); }
    finally { setRecalc(false); }
  };
  // 입금 취소/반려 — 충당했던 회차 납입액을 (다회차면 회차별 정확히) 되돌리고 REVERSED 로 전이.
  // 사유 입력은 prompt 대신 모달로 통일(수동매칭 모달과 일관된 UX). reverseTarget 설정 시 모달 표시.
  const [reverseTarget, setReverseTarget] = useState<Unmatched | null>(null);
  const onReversed = () => { setReverseTarget(null); setMsg("입금 취소/반려 처리 완료(REVERSED)."); load(); };
  // 수동매칭 — 자동충당 못 한 미대사 입금을 운영자가 올바른 계약·회차에 직접 충당한다.
  const [matchTarget, setMatchTarget] = useState<Unmatched | null>(null);
  const onMatched = () => { setMatchTarget(null); setMsg("수동매칭 완료(회차 충당)."); load(); };

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
        <div className="mb-3 flex items-center justify-between gap-2">
          <h3 className="font-bold text-[var(--text-primary)]">연체 현황 ({overdue.length})</h3>
          <button onClick={runOverdue} disabled={recalc} className={`${BTN} text-xs`}>{recalc ? "재계산 중…" : "연체 즉시 재계산"}</button>
        </div>
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
        {/* 미대사 입금 큐 — 가상계좌 미발견으로 자동충당되지 못한 입금. 취소(반려)로 종료 가능. */}
        <div className="mt-4 border-t border-[var(--line)] pt-3">
          <h4 className="mb-2 text-sm font-bold text-[var(--text-primary)]">미대사 입금 ({unmatched.length})</h4>
          <ul className="space-y-1.5">
            {unmatched.map((u) => (
              <li key={u.id} className="flex items-center justify-between gap-2 text-sm">
                <span className="text-[var(--text-secondary)]">{won(u.amount)} <span className="text-[10px] text-[var(--text-tertiary)]">{u.paid_at?.slice(0, 10) ?? "-"}{u.method ? ` · ${u.method}` : ""}</span></span>
                <span className="flex gap-1.5">
                  <button onClick={() => setMatchTarget(u)} className="rounded-lg border border-[var(--line-strong)] px-2 py-1 text-xs font-semibold text-[var(--accent-strong)] hover:bg-[var(--surface-strong)]">수동매칭</button>
                  <button onClick={() => setReverseTarget(u)} className="rounded-lg border border-[var(--line-strong)] px-2 py-1 text-xs font-semibold text-rose-400 hover:bg-[var(--surface-strong)]">취소/반려</button>
                </span>
              </li>
            ))}
            {unmatched.length === 0 && <li className="text-[var(--text-tertiary)] text-xs">미대사 입금 없음</li>}
          </ul>
        </div>
        {/* 매칭완료 입금 — 회차에 충당된 입금. 취소(반려) 시 다회차 분산분도 회차별 정확히 역배분된다. */}
        <div className="mt-4 border-t border-[var(--line)] pt-3">
          <h4 className="mb-2 text-sm font-bold text-[var(--text-primary)]">매칭완료 입금 ({matched.length})</h4>
          <ul className="space-y-1.5">
            {matched.map((m) => (
              <li key={m.id} className="flex items-center justify-between gap-2 text-sm">
                <span className="text-[var(--text-secondary)]">{won(m.amount)} <span className="text-[10px] text-[var(--text-tertiary)]">{m.paid_at?.slice(0, 10) ?? "-"}{m.method ? ` · ${m.method}` : ""}</span></span>
                <button onClick={() => setReverseTarget(m)} className="rounded-lg border border-[var(--line-strong)] px-2 py-1 text-xs font-semibold text-rose-400 hover:bg-[var(--surface-strong)]">취소/반려(역배분)</button>
              </li>
            ))}
            {matched.length === 0 && <li className="text-[var(--text-tertiary)] text-xs">매칭완료 입금 없음</li>}
          </ul>
        </div>
      </div>
    </div>
    {matchTarget && (
      <ManualMatchModal api={api} contracts={contracts} payment={matchTarget}
        onClose={() => setMatchTarget(null)} onMatched={onMatched} />
    )}
    {reverseTarget && (
      <ReverseModal api={api} payment={reverseTarget}
        onClose={() => setReverseTarget(null)} onReversed={onReversed} />
    )}
   </div>
  );
}

// 취소/반려 모달 — 사유를 입력받아 POST /payments/{id}/reverse. MATCHED 면 회차별(allocations) 정확 역배분.
function ReverseModal({ api, payment, onClose, onReversed }: {
  api: ReturnType<typeof salesApi>;
  payment: { id: string; amount: number };
  onClose: () => void; onReversed: () => void;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const submit = async () => {
    setBusy(true); setErr("");
    try {
      await api.post<{ status: string; reversed: boolean }>(`/payments/${payment.id}/reverse`, { reason: reason || undefined });
      onReversed();
    } catch { setErr("취소 실패(권한·대출실행분 확인)."); }
    finally { setBusy(false); }
  };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-5" onClick={(e) => e.stopPropagation()}>
        <h3 className="mb-1 font-bold text-[var(--text-primary)]">입금 취소/반려 — {won(payment.amount)}</h3>
        <p className="mb-3 text-[11px] text-[var(--text-tertiary)]">충당했던 회차 납입액을 되돌립니다(다회차 분산 입금은 회차별 정확히 역배분). 자금이동은 없습니다.</p>
        <div className="flex flex-col gap-2">
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="취소/반려 사유(선택)" className={IN} />
          {err && <p className="text-xs text-rose-400">{err}</p>}
          <div className="mt-1 flex justify-end gap-2">
            <button onClick={onClose} className="rounded-lg border border-[var(--line-strong)] px-3 py-1.5 text-sm text-[var(--text-secondary)]">닫기</button>
            <button onClick={submit} disabled={busy} className={BTN}>{busy ? "처리 중…" : "취소/반려 확정"}</button>
          </div>
        </div>
      </div>
    </div>
  );
}

// 수동매칭 모달 — 미대사 입금을 운영자가 계약·회차를 골라 직접 충당한다(POST /payments/{id}/manual-match).
function ManualMatchModal({ api, contracts, payment, onClose, onMatched }: {
  api: ReturnType<typeof salesApi>;
  contracts: { id: string; label: string; status?: string }[];
  payment: { id: string; amount: number };
  onClose: () => void; onMatched: () => void;
}) {
  const [cid, setCid] = useState("");
  const [insts, setInsts] = useState<InstRow[]>([]);
  const [iid, setIid] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const pickContract = async (id: string) => {
    setCid(id); setIid(""); setInsts([]); setErr("");
    if (!id) return;
    try {
      const r = await api.get<{ installments: InstRow[] }>(`/payments/installments?contract_id=${id}`);
      setInsts(r.installments || []);
    } catch { setErr("회차 조회 실패(계약 확인)."); }
  };
  const submit = async () => {
    if (!cid || !iid) { setErr("계약과 회차를 선택하세요."); return; }
    setBusy(true); setErr("");
    try {
      await api.post(`/payments/${payment.id}/manual-match`, { contract_id: cid, installment_id: iid });
      onMatched();
    } catch { setErr("수동매칭 실패(권한·중복 대사 확인)."); }
    finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-5" onClick={(e) => e.stopPropagation()}>
        <h3 className="mb-1 font-bold text-[var(--text-primary)]">수동매칭 — {won(payment.amount)}</h3>
        <p className="mb-3 text-[11px] text-[var(--text-tertiary)]">자동충당되지 못한 입금을 올바른 계약·회차에 직접 충당합니다.</p>
        <div className="flex flex-col gap-2">
          <select value={cid} onChange={(e) => pickContract(e.target.value)} className={IN}>
            <option value="">계약 선택…</option>
            {contracts.map((c) => <option key={c.id} value={c.id}>{c.label}{c.status ? ` (${c.status})` : ""}</option>)}
          </select>
          <select value={iid} onChange={(e) => setIid(e.target.value)} disabled={!insts.length} className={IN}>
            <option value="">회차 선택…</option>
            {insts.map((it) => (
              <option key={it.installment_id} value={it.installment_id}>
                {it.seq}회차 · {it.kind_label} · 미납 {won(it.unpaid)}
              </option>
            ))}
          </select>
          {err && <p className="text-xs text-rose-400">{err}</p>}
          <div className="mt-1 flex justify-end gap-2">
            <button onClick={onClose} className="rounded-lg border border-[var(--line-strong)] px-3 py-1.5 text-sm text-[var(--text-secondary)]">취소</button>
            <button onClick={submit} disabled={busy} className={BTN}>{busy ? "충당 중…" : "충당"}</button>
          </div>
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
  installment_id: string;
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
