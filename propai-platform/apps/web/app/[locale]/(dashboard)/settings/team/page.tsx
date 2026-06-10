"use client";

/**
 * 팀 관리 — 개인 로그인 + 팀 배정.
 * 팀장(유료 구독자): 팀 생성·멤버 승인/제거·사용량 한도·모니터링.
 * 일반회원: 팀장 ID(이메일)로 가입 신청 → 승인 시 팀 자원·quota 공유.
 */

import { useCallback, useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";

/* eslint-disable @typescript-eslint/no-explicit-any */

type Member = {
  user_id: string; email: string; name?: string; status: string; role: string;
  usage_limit_krw: number; requested_at?: string;
};
type MineResp = { role: "owner" | "member" | "none"; team?: any; members?: Member[]; status?: string };
type UsageRow = { user_id: string; email: string; role: string; usage_limit_krw: number; tokens: number; cost_krw: number };

const won = (n: number) => `${Math.round(n || 0).toLocaleString("ko-KR")}원`;

export default function TeamPage() {
  const [mine, setMine] = useState<MineResp | null>(null);
  const [usage, setUsage] = useState<UsageRow[]>([]);
  const [name, setName] = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const m = await apiClient.get<MineResp>("/teams/mine", { useMock: false });
      setMine(m);
      if (m.role === "owner") {
        try {
          const u = await apiClient.get<{ members: UsageRow[] }>("/teams/usage?days=30", { useMock: false });
          setUsage(u.members || []);
        } catch { /* noop */ }
      }
    } catch { setMsg("팀 정보를 불러오지 못했습니다."); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const act = async (fn: () => Promise<any>, ok: string) => {
    setBusy(true); setMsg("");
    try { const r = await fn(); setMsg(r?.error ? r.error : ok); await load(); }
    catch { setMsg("처리 실패 — 권한/입력을 확인하세요."); }
    finally { setBusy(false); }
  };

  const createTeam = () => act(() => apiClient.post("/teams/create", { body: { name }, useMock: false }), "팀이 생성되었습니다.");
  const joinTeam = () => act(() => apiClient.post("/teams/join", { body: { owner_email: ownerEmail }, useMock: false }), "가입 신청 완료 — 팀장 승인 대기 중입니다.");
  const approve = (uid: string) => act(() => apiClient.post(`/teams/members/${uid}/approve`, { useMock: false }), "승인되었습니다.");
  const remove = (uid: string) => act(() => apiClient.delete(`/teams/members/${uid}`, { useMock: false }), "제거되었습니다.");
  const setLimit = (uid: string, limit: number) => act(() => apiClient.put("/teams/members/limit", { body: { user_id: uid, limit_krw: limit }, useMock: false }), "사용량 한도가 설정되었습니다.");

  const usageMap = Object.fromEntries(usage.map((u) => [u.user_id, u]));

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-1 pb-20">
      <div className="cc-bracketed relative overflow-hidden rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-6">
        <div className="cc-grid-bg opacity-50" />
        <i className="cc-bracket cc-bracket--tl" /><i className="cc-bracket cc-bracket--br" />
        <div className="relative z-10">
          <span className="cc-meta">TEAM · WORKSPACE</span>
          <h1 className="text-2xl font-black text-[var(--text-primary)]">팀 관리 <span className="text-[var(--accent-strong)]">_</span></h1>
          <p className="text-sm text-[var(--text-secondary)]">개인 로그인 + 팀 배정 — 멤버는 자기 계정으로 로그인하되 팀의 프로젝트·사용량을 공유합니다.</p>
        </div>
      </div>
      {msg && <div className="rounded-xl border border-[var(--data-accent-line)] bg-[var(--data-accent-soft)] px-4 py-2.5 text-sm text-[var(--text-secondary)]">{msg}</div>}

      {/* 미소속 — 팀 생성 또는 가입 신청 */}
      {mine?.role === "none" && (
        <div className="grid gap-4 md:grid-cols-2">
          <section className="cc-panel"><div className="cc-panel__body space-y-3">
            <h2 className="text-sm font-bold text-[var(--text-primary)]">팀 만들기 (유료 구독자)</h2>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="팀 이름"
              className="w-full rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)]" />
            <button onClick={createTeam} disabled={busy || !name.trim()} className="w-full rounded-lg bg-[var(--accent-strong)] px-4 py-2 text-sm font-bold text-white disabled:opacity-50">팀 생성</button>
          </div></section>
          <section className="cc-panel"><div className="cc-panel__body space-y-3">
            <h2 className="text-sm font-bold text-[var(--text-primary)]">팀 가입 신청</h2>
            <input value={ownerEmail} onChange={(e) => setOwnerEmail(e.target.value)} placeholder="팀장 ID(이메일) 검색"
              className="w-full rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)]" />
            <button onClick={joinTeam} disabled={busy || !ownerEmail.trim()} className="w-full rounded-lg border border-[var(--accent-strong)]/40 bg-[var(--accent-soft)] px-4 py-2 text-sm font-bold text-[var(--accent-strong)] disabled:opacity-50">가입 신청</button>
          </div></section>
        </div>
      )}

      {/* 소속 멤버 */}
      {mine?.role === "member" && (
        <section className="cc-panel"><div className="cc-panel__body">
          <h2 className="text-sm font-bold text-[var(--text-primary)]">소속 팀: {mine.team?.name}</h2>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">상태: {mine.status === "approved" ? "✅ 승인됨 — 팀 자원 공유 중" : "⏳ 승인 대기 중"}</p>
        </div></section>
      )}

      {/* 팀장 — 멤버 관리 */}
      {mine?.role === "owner" && (
        <section className="cc-panel"><div className="cc-panel__body">
          <h2 className="mb-3 text-sm font-bold text-[var(--text-primary)]">팀: {mine.team?.name} · 멤버 ({mine.members?.length ?? 0})</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-[10px] uppercase tracking-[0.1em] text-[var(--text-hint)]">
                <th className="pb-2">계정</th><th className="pb-2">상태</th><th className="pb-2 text-right">사용량(30일)</th><th className="pb-2 text-right">한도(원)</th><th className="pb-2 text-right">관리</th>
              </tr></thead>
              <tbody>
                {(mine.members ?? []).map((m) => {
                  const u = usageMap[m.user_id];
                  return (
                    <tr key={m.user_id} className="border-t border-[var(--line)]">
                      <td className="py-2 font-medium text-[var(--text-primary)]">{m.email}{m.role === "owner" && " (팀장)"}</td>
                      <td className="py-2">{m.status === "approved" ? <span className="text-emerald-400">승인</span> : m.status === "pending" ? <span className="text-amber-400">대기</span> : m.status}</td>
                      <td className="py-2 text-right cc-num text-[var(--text-secondary)]">{u ? won(u.cost_krw) : "-"}</td>
                      <td className="py-2 text-right">
                        {m.role !== "owner" && m.status === "approved" ? (
                          <input type="number" defaultValue={m.usage_limit_krw || 0}
                            onBlur={(e) => { const v = Number(e.target.value || 0); if (v !== m.usage_limit_krw) setLimit(m.user_id, v); }}
                            className="cc-num w-24 rounded-md border border-[var(--line-strong)] bg-[var(--surface)] px-2 py-1 text-right text-xs" title="0=무제한" />
                        ) : "-"}
                      </td>
                      <td className="py-2 text-right">
                        {m.status === "pending" && <button onClick={() => approve(m.user_id)} disabled={busy} className="mr-1 rounded-md bg-[var(--accent-strong)] px-2 py-1 text-[11px] font-bold text-white">승인</button>}
                        {m.role !== "owner" && <button onClick={() => remove(m.user_id)} disabled={busy} className="rounded-md border border-rose-500/30 px-2 py-1 text-[11px] font-bold text-rose-400">제거</button>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-[10px] text-[var(--text-hint)]">※ 한도(원)=멤버 30일 사용 상한(0=무제한). 멤버는 자기 계정으로 로그인하며 팀의 프로젝트·구독 사용량을 공유합니다.</p>
        </div></section>
      )}
    </div>
  );
}
