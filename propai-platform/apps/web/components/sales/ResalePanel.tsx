"use client";

import { useCallback, useEffect, useState } from "react";
import { salesApi } from "@/lib/salesApi";

interface Report { id: string; status: string; due_date?: string }
interface Transfer { id: string; transfer_type?: string; allowed?: boolean; reason?: string; decided_at?: string }
const IN = "rounded-lg border border-[var(--line-strong)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)]";
const BTN = "rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-sm font-bold text-white disabled:opacity-50";

export default function ResalePanel({ siteCode }: { siteCode: string }) {
  const api = salesApi(siteCode);
  const [reports, setReports] = useState<Report[]>([]);
  const [transfers, setTransfers] = useState<Transfer[]>([]);
  const [rc, setRc] = useState("");
  const [tf, setTf] = useState({ contract_id: "", to_customer: "", transfer_type: "RESALE" });
  const [msg, setMsg] = useState("");

  const load = useCallback(() => {
    api.get<Report[]>("/realtx/reports").then(setReports).catch(() => setReports([]));
    api.get<Transfer[]>("/resale/transfers").then(setTransfers).catch(() => setTransfers([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteCode]);
  useEffect(() => { load(); }, [load]);

  const report = async () => { if (!rc) return; await api.post("/realtx/report", { contract_id: rc }); setRc(""); setMsg("실거래신고 생성"); load(); };
  const request = async () => {
    if (!tf.contract_id) return;
    const r = await api.post<{ allowed: boolean; reason: string }>("/resale/transfer/request",
      { contract_id: tf.contract_id, to_customer: tf.to_customer || undefined, transfer_type: tf.transfer_type });
    setMsg(r.allowed ? "전매 요청 — 허용(제한 없음)" : `전매 차단 — ${r.reason}`); load();
  };
  const decide = async (id: string, allowed: boolean) => { await api.post(`/resale/transfer/${id}/decide`, { allowed, reason: allowed ? "승인" : "반려" }); load(); };

  return (
    <div className="space-y-5">
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
          <h3 className="mb-3 font-bold text-[var(--text-primary)]">실거래신고</h3>
          <div className="flex flex-wrap items-end gap-2">
            <input value={rc} onChange={(e) => setRc(e.target.value)} placeholder="계약 ID" className={`${IN} flex-1`} />
            <button onClick={report} className={BTN}>신고 생성</button>
          </div>
          <ul className="mt-3 space-y-1 text-sm text-[var(--text-secondary)]">
            {reports.map((r) => <li key={r.id}>· {r.status} — 기한 {r.due_date ?? "-"}</li>)}
            {reports.length === 0 && <li className="text-[var(--text-tertiary)]">신고 없음</li>}
          </ul>
        </div>
        <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
          <h3 className="mb-3 font-bold text-[var(--text-primary)]">전매·명의변경 요청</h3>
          <div className="flex flex-col gap-2">
            <input value={tf.contract_id} onChange={(e) => setTf({ ...tf, contract_id: e.target.value })} placeholder="계약 ID" className={IN} />
            <input value={tf.to_customer} onChange={(e) => setTf({ ...tf, to_customer: e.target.value })} placeholder="양수인 고객 ID(선택)" className={IN} />
            <div className="flex gap-2">
              <select value={tf.transfer_type} onChange={(e) => setTf({ ...tf, transfer_type: e.target.value })} className={IN}>
                <option value="RESALE">전매</option><option value="NAME_CHANGE">명의변경</option>
              </select>
              <button onClick={request} className={BTN}>요청(제한 검증)</button>
            </div>
          </div>
        </div>
      </div>
      {msg && <p className="text-sm font-semibold text-[var(--accent-strong)]">{msg}</p>}
      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
        <h3 className="mb-3 font-bold text-[var(--text-primary)]">전매 요청 심사 ({transfers.length})</h3>
        <table className="w-full text-sm">
          <thead><tr className="border-b border-[var(--line)] text-left text-[var(--text-secondary)]"><th className="py-1">유형</th><th>판정</th><th>사유</th><th>처리</th></tr></thead>
          <tbody>
            {transfers.map((t) => (
              <tr key={t.id} className="border-b border-[var(--line)]">
                <td className="py-1 text-[var(--text-primary)]">{t.transfer_type}</td>
                <td className={t.allowed ? "text-emerald-400" : "text-rose-400"}>{t.allowed ? "허용" : "차단"}</td>
                <td className="text-[var(--text-tertiary)]">{t.reason || "-"}</td>
                <td>
                  {!t.decided_at && (
                    <span className="flex gap-2">
                      <button onClick={() => decide(t.id, true)} className="text-emerald-400">승인</button>
                      <button onClick={() => decide(t.id, false)} className="text-rose-400">반려</button>
                    </span>
                  )}
                </td>
              </tr>
            ))}
            {transfers.length === 0 && <tr><td colSpan={4} className="py-3 text-[var(--text-tertiary)]">요청 없음</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
