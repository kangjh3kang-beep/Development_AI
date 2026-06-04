"use client";

/**
 * 고객 CRM — AI 가망고객 예측(등급 A/B/C·다음액션) + 고객 추가 + 상담 기록.
 * 백엔드: /sales/customers · /sales/consultations · GET /sales/crm/grade-suggestions
 */

import { useCallback, useEffect, useState } from "react";
import { salesApi } from "@/lib/salesApi";

interface Pred {
  customer_id: string; name?: string | null; phone?: string | null; status?: string;
  current_grade?: string | null; score: number; suggested_grade: string; reasons: string[]; next_action: string;
}

const GRADE: Record<string, string> = {
  A: "border-rose-500/40 bg-rose-500/10 text-rose-300",
  B: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  C: "border-sky-500/40 bg-sky-500/10 text-sky-300",
};
const GLABEL: Record<string, string> = { A: "핫(A)", B: "웜(B)", C: "콜드(C)" };
const fcls = "rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1.5 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]";

export default function CrmPanel({ siteCode }: { siteCode: string }) {
  const api = salesApi(siteCode);
  const [preds, setPreds] = useState<Pred[]>([]);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get<{ customers: Pred[] }>("/crm/grade-suggestions").then((r) => setPreds(r.customers || [])).catch(() => setPreds([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteCode]);
  useEffect(() => { load(); }, [load]);

  const addCustomer = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try { await api.post("/customers", { name: name.trim(), phone_e164: phone.trim() || undefined, status: "LEAD" }); setName(""); setPhone(""); load(); }
    finally { setBusy(false); }
  };
  const applyGrade = async (p: Pred) => { await api.patch(`/customers/${p.customer_id}`, { grade: p.suggested_grade }); load(); };
  const logConsult = async (p: Pred) => {
    await api.post("/consultations", { customer_id: p.customer_id, consulted_at: new Date().toISOString(), channel: "VISIT", next_action: p.next_action });
    load();
  };
  const applyAll = async () => { for (const p of preds) await api.patch(`/customers/${p.customer_id}`, { grade: p.suggested_grade }); load(); };

  return (
    <div className="space-y-4">
      {/* 고객 추가 */}
      <div className="flex flex-wrap items-end gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
        <label className="flex flex-1 flex-col gap-1"><span className="text-[10px] text-[var(--text-tertiary)]">고객명</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="홍길동" className={`${fcls} min-w-[120px]`} /></label>
        <label className="flex flex-1 flex-col gap-1"><span className="text-[10px] text-[var(--text-tertiary)]">연락처</span>
          <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="01012345678" className={`${fcls} min-w-[120px]`} /></label>
        <button onClick={addCustomer} disabled={busy} className="rounded-lg bg-[var(--accent-strong)] px-4 py-2 text-sm font-black text-white disabled:opacity-50">＋ 고객 추가</button>
      </div>

      <div className="flex items-center justify-between">
        <h2 className="font-black text-[var(--text-primary)]">🤖 AI 가망고객 예측 ({preds.length})</h2>
        <div className="flex gap-2">
          <button onClick={load} className="rounded-lg border border-[var(--line-strong)] px-3 py-1.5 text-xs font-bold text-[var(--text-secondary)]">재예측</button>
          {preds.length > 0 && <button onClick={applyAll} className="rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-xs font-bold text-white">등급 일괄 반영</button>}
        </div>
      </div>

      {preds.length === 0 ? (
        <p className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-6 text-sm text-[var(--text-secondary)]">고객이 없습니다. 위에서 추가하거나 데스크 체크인으로 유입됩니다.</p>
      ) : (
        <div className="space-y-2">
          {preds.map((p) => (
            <div key={p.customer_id} className="flex flex-wrap items-center gap-3 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
              <span className={`rounded-full border px-2.5 py-0.5 text-xs font-black ${GRADE[p.suggested_grade] ?? ""}`}>{GLABEL[p.suggested_grade] ?? p.suggested_grade}</span>
              <span className="font-bold text-[var(--text-primary)]">{p.name || "-"}</span>
              {p.phone && <span className="text-xs text-[var(--text-tertiary)]">{p.phone}</span>}
              <span className="rounded-md bg-[var(--surface-strong)] px-2 py-0.5 text-xs font-bold text-[var(--accent-strong)]">{p.score}점</span>
              <span className="w-full text-xs text-[var(--text-secondary)] sm:w-auto sm:flex-1">
                {p.reasons.join(" · ") || "활동 이력 없음"} → <b className="text-[var(--text-primary)]">{p.next_action}</b>
              </span>
              <button onClick={() => logConsult(p)} className="rounded-lg border border-[var(--line-strong)] px-2.5 py-1 text-[11px] font-bold text-[var(--text-secondary)]">상담 기록</button>
              <button onClick={() => applyGrade(p)} className="rounded-lg bg-[var(--accent-strong)] px-2.5 py-1 text-[11px] font-bold text-white">
                등급 반영{p.current_grade ? `(현:${p.current_grade})` : ""}
              </button>
            </div>
          ))}
        </div>
      )}
      <p className="text-[11px] text-[var(--text-hint)]">예측 가중: 상담횟수·통화시간·마케팅수신동의·최근상담·방문이력 → A(핫)/B(웜)/C(콜드). 상담 기록 시 점수·등급이 갱신됩니다.</p>
    </div>
  );
}
