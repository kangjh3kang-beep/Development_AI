"use client";

import { useCallback, useEffect, useState } from "react";
import { salesApi, won } from "@/lib/salesApi";
import { NumberInput } from "@/components/common/NumberInput";

interface Invoice { id: string; direction?: string; supply_amount?: number; vat_amount?: number; status?: string; item?: string }
const IN = "rounded-lg border border-[var(--line-strong)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)]";
const BTN = "rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-sm font-bold text-white disabled:opacity-50";

export default function TaxPanel({ siteCode }: { siteCode: string }) {
  const api = salesApi(siteCode);
  const [g, setG] = useState<{ satisfied: boolean; hug: boolean; trust_mgmt_agency: boolean } | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [inv, setInv] = useState<{ counterparty_biz_no: string; supply_amount: number | null; vat_amount: number | null; item: string }>({ counterparty_biz_no: "", supply_amount: null, vat_amount: null, item: "분양대금" });
  const [period, setPeriod] = useState(new Date().toISOString().slice(0, 7));
  const [wh, setWh] = useState<{ gross: number; withholding: number } | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const errText = (e: unknown) => (e instanceof Error && e.message ? e.message : "요청에 실패했습니다.");

  const load = useCallback(() => {
    api.get<{ satisfied: boolean; hug: boolean; trust_mgmt_agency: boolean }>("/guarantee/check").then(setG).catch(() => setG(null));
    api.get<Invoice[]>("/tax/invoices-list").then(setInvoices).catch(() => setInvoices([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteCode]);
  useEffect(() => { load(); }, [load]);

  const issue = async () => {
    setMsg(null);
    if (!inv.counterparty_biz_no) { setMsg({ ok: false, text: "상대 사업자번호를 입력하세요." }); return; }
    try {
      await api.post("/tax/invoices", { direction: "ISSUE", counterparty_biz_no: inv.counterparty_biz_no,
        supply_amount: inv.supply_amount ?? 0, vat_amount: inv.vat_amount ?? 0, item: inv.item });
      setInv({ counterparty_biz_no: "", supply_amount: null, vat_amount: null, item: "분양대금" });
      setMsg({ ok: true, text: "세금계산서 발행(DRAFT) 완료" }); load();
    } catch (e) { setMsg({ ok: false, text: errText(e) }); }
  };
  const queryWh = async () => {
    setMsg(null);
    try {
      const r = await api.get<{ gross: number; withholding: number }>(`/tax/withholding-statements?period=${period}`);
      setWh(r);
    } catch (e) { setMsg({ ok: false, text: errText(e) }); }
  };

  return (
    <div className="space-y-5">
      {msg && (
        <p className={`rounded-lg px-3 py-2 text-sm font-semibold ${msg.ok ? "bg-emerald-500/10 text-emerald-400" : "bg-rose-500/10 text-rose-400"}`}>
          {msg.text}
        </p>
      )}
      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
        <h3 className="mb-2 font-bold text-[var(--text-primary)]">선분양 보증 요건</h3>
        {g ? (
          <p className={`text-sm font-semibold ${g.satisfied ? "text-emerald-400" : "text-rose-400"}`}>
            {g.satisfied ? "충족" : "미충족"} — HUG 분양보증: {g.hug ? "O" : "X"} / 신탁(관리+대리사무): {g.trust_mgmt_agency ? "O" : "X"}
          </p>
        ) : <p className="text-sm text-[var(--text-tertiary)]">조회 중…</p>}
      </div>

      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
        <h3 className="mb-3 font-bold text-[var(--text-primary)]">세금계산서 발행</h3>
        <div className="flex flex-wrap items-end gap-2">
          <input value={inv.counterparty_biz_no} onChange={(e) => setInv({ ...inv, counterparty_biz_no: e.target.value })} placeholder="상대 사업자번호" className={IN} />
          <NumberInput value={inv.supply_amount} onChange={(n) => setInv({ ...inv, supply_amount: n })} placeholder="공급가액" className={IN} />
          <NumberInput value={inv.vat_amount} onChange={(n) => setInv({ ...inv, vat_amount: n })} placeholder="VAT" className={IN} />
          <input value={inv.item} onChange={(e) => setInv({ ...inv, item: e.target.value })} placeholder="품목" className={IN} />
          <button onClick={issue} className={BTN}>발행(DRAFT)</button>
        </div>
        <table className="mt-3 w-full text-sm">
          <thead><tr className="border-b border-[var(--line)] text-left text-[var(--text-secondary)]"><th className="py-1">구분</th><th>품목</th><th className="text-right">공급가</th><th className="text-right">VAT</th><th>상태</th></tr></thead>
          <tbody>
            {invoices.map((i) => (
              <tr key={i.id} className="border-b border-[var(--line)] text-[var(--text-primary)]">
                <td className="py-1">{i.direction}</td><td>{i.item}</td>
                <td className="text-right">{won(i.supply_amount || 0)}</td><td className="text-right">{won(i.vat_amount || 0)}</td>
                <td className="text-[var(--text-secondary)]">{i.status}</td>
              </tr>
            ))}
            {invoices.length === 0 && <tr><td colSpan={5} className="py-3 text-[var(--text-tertiary)]">발행 내역 없음</td></tr>}
          </tbody>
        </table>
      </div>

      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
        <h3 className="mb-3 font-bold text-[var(--text-primary)]">지급명세서(원천징수 집계)</h3>
        <div className="flex flex-wrap items-end gap-2">
          <input value={period} onChange={(e) => setPeriod(e.target.value)} placeholder="YYYY-MM" className={`${IN} w-32`} />
          <button onClick={queryWh} className={BTN}>집계 조회</button>
        </div>
        {wh && (
          <p className="mt-2 text-sm text-[var(--text-primary)]">
            {period} — 지급총액 <b>{won(wh.gross)}</b> / 원천징수 <b className="text-amber-400">{won(wh.withholding)}</b>
          </p>
        )}
      </div>
    </div>
  );
}
