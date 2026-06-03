"use client";

import { useCallback, useEffect, useState } from "react";
import { salesApi } from "@/lib/salesApi";

interface Ann { id: string; announce_no?: string; status: string; round_id?: string }
interface Winner { id: string; win_type?: string; status: string; unit_id?: string }
const IN = "rounded-lg border border-[var(--line-strong)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)]";
const BTN = "rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-sm font-bold text-white disabled:opacity-50";

export default function SubscriptionPanel({ siteCode }: { siteCode: string }) {
  const api = salesApi(siteCode);
  const [anns, setAnns] = useState<Ann[]>([]);
  const [winners, setWinners] = useState<Winner[]>([]);
  const [rounds, setRounds] = useState<{ id: string; name: string }[]>([]);
  const [no, setNo] = useState("");
  const [rid, setRid] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(() => {
    api.get<Ann[]>("/subscription/announcements").then(setAnns).catch(() => setAnns([]));
    api.get<Winner[]>("/subscription/winners").then(setWinners).catch(() => setWinners([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteCode]);
  useEffect(() => {
    load();
    api.get<{ id: string; name: string }[]>("/rounds").then((r) => { setRounds(r || []); if (r?.[0]) setRid(r[0].id); }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteCode]);

  const create = async () => {
    if (!no) return;
    setBusy("create");
    try { await api.post("/subscription/announcements", { announce_no: no, status: "OPEN", round_id: rid || undefined }); setNo(""); load(); }
    finally { setBusy(""); }
  };
  const draw = async (id: string) => {
    setBusy(id);
    try { const r = await api.post<{ winners: number }>(`/subscription/${id}/draw`, {}); alert(`추첨 완료: ${r.winners}세대 당첨`); load(); }
    catch { alert("추첨 실패 (권한/신청자 확인)"); }
    finally { setBusy(""); }
  };

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
        <h3 className="mb-3 font-bold text-[var(--text-primary)]">입주자모집공고</h3>
        <div className="flex flex-wrap items-end gap-2">
          <input value={no} onChange={(e) => setNo(e.target.value)} placeholder="공고번호 (예: 2026-001)" className={IN} />
          {rounds.length > 0 && (
            <select value={rid} onChange={(e) => setRid(e.target.value)} className={IN}>
              {rounds.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
          )}
          <button onClick={create} disabled={busy === "create"} className={BTN}>공고 등록</button>
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl border border-[var(--line)]">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-[var(--line)] bg-[var(--surface-strong)] text-left text-[var(--text-secondary)]">
            <th className="px-3 py-2">공고번호</th><th className="px-3 py-2">상태</th><th className="px-3 py-2">당첨 추첨</th></tr></thead>
          <tbody>
            {anns.map((a) => (
              <tr key={a.id} className="border-b border-[var(--line)]">
                <td className="px-3 py-2 font-semibold text-[var(--text-primary)]">{a.announce_no ?? a.id.slice(0, 8)}</td>
                <td className="px-3 py-2 text-[var(--text-secondary)]">{a.status}</td>
                <td className="px-3 py-2">
                  <button onClick={() => draw(a.id)} disabled={busy === a.id || a.status === "DRAWN"} className={BTN}>
                    {a.status === "DRAWN" ? "추첨 완료" : busy === a.id ? "추첨 중…" : "가점·추첨 실행"}
                  </button>
                </td>
              </tr>
            ))}
            {anns.length === 0 && <tr><td colSpan={3} className="px-3 py-6 text-center text-sm text-[var(--text-secondary)]">공고가 없습니다.</td></tr>}
          </tbody>
        </table>
      </div>

      <div>
        <h3 className="mb-2 font-bold text-[var(--text-primary)]">당첨/예비 현황 ({winners.length})</h3>
        <div className="flex flex-wrap gap-2">
          {winners.map((w) => (
            <span key={w.id} className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]">
              {w.win_type} · {w.status}
            </span>
          ))}
          {winners.length === 0 && <p className="text-sm text-[var(--text-tertiary)]">당첨자 없음 (추첨 실행 전).</p>}
        </div>
      </div>
    </div>
  );
}
