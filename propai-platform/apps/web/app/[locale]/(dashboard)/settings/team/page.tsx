"use client";

/**
 * MY PAGE — 내 구독·사용량 + 팀 관리(개인 로그인 + 팀 배정).
 * 팀장(유료 구독자): 팀을 여러 개 생성·삭제, 멤버 초대(동의식)·가입승인·제거·사용량 한도·모니터링.
 * 일반회원: 팀장 ID(이메일)로 가입 신청 → 승인 시 합류. 또는 팀장 초대를 동의/거절.
 * 멤버는 자기 계정으로 로그인하되 팀의 프로젝트·구독 사용량을 공유합니다.
 */

import { useCallback, useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { BillingMeter } from "@/components/billing/BillingMeter";

/* eslint-disable @typescript-eslint/no-explicit-any */

type Member = {
  user_id: string; email: string; name?: string; status: string; role: string;
  usage_limit_krw: number; requested_at?: string;
};
type OwnedTeam = { id: string; name: string; members: Member[] };
type Membership = { team_id: string; team_name?: string; owner_email?: string; status: string };
type MineResp = { can_create: boolean; owned: OwnedTeam[]; memberships: Membership[] };
type UsageRow = { user_id: string; email: string; role: string; usage_limit_krw: number; tokens: number; cost_krw: number };

const won = (n: number) => `${Math.round(n || 0).toLocaleString("ko-KR")}원`;
const STATUS_LABEL: Record<string, string> = {
  approved: "✅ 승인됨 — 팀 자원 공유 중", pending: "⏳ 가입 승인 대기 중",
  invited: "📩 팀장 초대 도착 — 동의하면 합류", rejected: "거절됨",
};

export default function TeamPage() {
  const [mine, setMine] = useState<MineResp | null>(null);
  const [usageByTeam, setUsageByTeam] = useState<Record<string, UsageRow[]>>({});
  const [name, setName] = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [inviteEmail, setInviteEmail] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const m = await apiClient.get<MineResp>("/teams/mine", { useMock: false });
      setMine(m);
      const map: Record<string, UsageRow[]> = {};
      await Promise.all((m.owned || []).map(async (t) => {
        try {
          const u = await apiClient.get<{ members: UsageRow[] }>(`/teams/${t.id}/usage?days=30`, { useMock: false });
          map[t.id] = u.members || [];
        } catch { map[t.id] = []; }
      }));
      setUsageByTeam(map);
    } catch { setMsg("팀 정보를 불러오지 못했습니다."); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const act = async (fn: () => Promise<any>, ok: string) => {
    setBusy(true); setMsg("");
    try { const r = await fn(); setMsg(r?.error ? r.error : ok); await load(); }
    catch { setMsg("처리 실패 — 권한/입력을 확인하세요."); }
    finally { setBusy(false); }
  };

  const createTeam = () => act(() => apiClient.post("/teams/create", { body: { name }, useMock: false }), "팀이 생성되었습니다.").then(() => setName(""));
  const joinTeam = () => act(() => apiClient.post("/teams/join", { body: { owner_email: ownerEmail }, useMock: false }), "가입 신청 완료 — 팀장 승인 대기 중입니다.").then(() => setOwnerEmail(""));
  const deleteTeam = (tid: string, nm: string) => { if (!confirm(`'${nm}' 팀을 삭제할까요? 멤버는 개인 워크스페이스로 복원됩니다.`)) return; act(() => apiClient.delete(`/teams/${tid}`, { useMock: false }), "팀이 삭제되었습니다."); };
  const invite = (tid: string) => { const email = (inviteEmail[tid] || "").trim(); if (!email) return; act(() => apiClient.post(`/teams/${tid}/invite`, { body: { email }, useMock: false }), "초대를 보냈습니다 — 상대 동의 시 합류합니다.").then(() => setInviteEmail((p) => ({ ...p, [tid]: "" }))); };
  const approve = (tid: string, uid: string) => act(() => apiClient.post(`/teams/${tid}/members/${uid}/approve`, { useMock: false }), "승인되었습니다.");
  const remove = (tid: string, uid: string) => act(() => apiClient.delete(`/teams/${tid}/members/${uid}`, { useMock: false }), "제거되었습니다.");
  const setLimit = (tid: string, uid: string, limit: number) => act(() => apiClient.put(`/teams/${tid}/members/limit`, { body: { user_id: uid, limit_krw: limit }, useMock: false }), "사용량 한도가 설정되었습니다.");
  const acceptInvite = (tid: string) => act(() => apiClient.post(`/teams/${tid}/accept`, { useMock: false }), "초대를 수락했습니다 — 팀에 합류했습니다.");
  const declineInvite = (tid: string) => act(() => apiClient.post(`/teams/${tid}/decline`, { useMock: false }), "초대를 거절했습니다.");

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-1 pb-20">
      <div className="cc-bracketed relative overflow-hidden rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-6">
        <div className="cc-grid-bg opacity-50" />
        <i className="cc-bracket cc-bracket--tl" /><i className="cc-bracket cc-bracket--br" />
        <div className="relative z-10">
          <span className="cc-meta">MY PAGE · 구독 · 팀</span>
          <h1 className="text-2xl font-black text-[var(--text-primary)]">MY PAGE <span className="text-[var(--accent-strong)]">_</span></h1>
          <p className="text-sm text-[var(--text-secondary)]">내 구독·사용량 + 팀 생성 → 팀 관리 → 팀원 관리. 멤버는 자기 계정으로 로그인하되 팀의 프로젝트·사용량을 공유합니다.</p>
        </div>
      </div>

      {/* 내 구독·사용량 */}
      <BillingMeter />
      {msg && <div className="rounded-xl border border-[var(--data-accent-line)] bg-[var(--data-accent-soft)] px-4 py-2.5 text-sm text-[var(--text-secondary)]">{msg}</div>}

      {/* 내 소속/초대 — 멤버 시점 */}
      {(mine?.memberships?.length ?? 0) > 0 && (
        <section className="cc-panel"><div className="cc-panel__body space-y-2">
          <h2 className="text-sm font-bold text-[var(--text-primary)]">내 소속·초대</h2>
          {mine!.memberships.map((ms) => (
            <div key={ms.team_id} className="flex items-center justify-between gap-3 rounded-lg border border-[var(--line)] px-3 py-2">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-[var(--text-primary)]">{ms.team_name || "팀"}{ms.owner_email && <span className="text-[var(--text-hint)]"> · 팀장 {ms.owner_email}</span>}</p>
                <p className="text-xs text-[var(--text-secondary)]">{STATUS_LABEL[ms.status] || ms.status}</p>
              </div>
              {ms.status === "invited" && (
                <div className="flex shrink-0 gap-1">
                  <button onClick={() => acceptInvite(ms.team_id)} disabled={busy} className="rounded-md bg-[var(--accent-strong)] px-3 py-1 text-[11px] font-bold text-white disabled:opacity-50">동의·합류</button>
                  <button onClick={() => declineInvite(ms.team_id)} disabled={busy} className="rounded-md border border-rose-500/30 px-3 py-1 text-[11px] font-bold text-rose-400 disabled:opacity-50">거절</button>
                </div>
              )}
            </div>
          ))}
        </div></section>
      )}

      {/* 팀 생성 / 가입 신청 */}
      <div className="grid gap-4 md:grid-cols-2">
        {mine?.can_create && (
          <section className="cc-panel"><div className="cc-panel__body space-y-3">
            <h2 className="text-sm font-bold text-[var(--text-primary)]">팀 만들기 (유료 구독자 · 여러 개 가능)</h2>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="팀 이름"
              className="w-full rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)]" />
            <button onClick={createTeam} disabled={busy || !name.trim()} className="w-full rounded-lg bg-[var(--accent-strong)] px-4 py-2 text-sm font-bold text-white disabled:opacity-50">팀 생성</button>
          </div></section>
        )}
        <section className="cc-panel"><div className="cc-panel__body space-y-3">
          <h2 className="text-sm font-bold text-[var(--text-primary)]">팀 가입 신청</h2>
          <input value={ownerEmail} onChange={(e) => setOwnerEmail(e.target.value)} placeholder="팀장 ID(이메일) 검색"
            className="w-full rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)]" />
          <button onClick={joinTeam} disabled={busy || !ownerEmail.trim()} className="w-full rounded-lg border border-[var(--accent-strong)]/40 bg-[var(--accent-soft)] px-4 py-2 text-sm font-bold text-[var(--accent-strong)] disabled:opacity-50">가입 신청</button>
        </div></section>
      </div>

      {/* 팀장 — 소유 팀별 멤버 관리 */}
      {(mine?.owned ?? []).map((team) => {
        const usageMap = Object.fromEntries((usageByTeam[team.id] || []).map((u) => [u.user_id, u]));
        return (
          <section key={team.id} className="cc-panel"><div className="cc-panel__body">
            <div className="mb-3 flex items-center justify-between gap-2">
              <h2 className="text-sm font-bold text-[var(--text-primary)]">팀: {team.name} · 멤버 ({team.members?.length ?? 0})</h2>
              <button onClick={() => deleteTeam(team.id, team.name)} disabled={busy} className="rounded-md border border-rose-500/30 px-2.5 py-1 text-[11px] font-bold text-rose-400 disabled:opacity-50">팀 삭제</button>
            </div>

            {/* 초대 */}
            <div className="mb-3 flex gap-2">
              <input value={inviteEmail[team.id] || ""} onChange={(e) => setInviteEmail((p) => ({ ...p, [team.id]: e.target.value }))} placeholder="초대할 회원 ID(이메일)"
                className="flex-1 rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-1.5 text-sm text-[var(--text-primary)]" />
              <button onClick={() => invite(team.id)} disabled={busy || !(inviteEmail[team.id] || "").trim()} className="shrink-0 rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-xs font-bold text-white disabled:opacity-50">초대</button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-left text-[10px] uppercase tracking-[0.1em] text-[var(--text-hint)]">
                  <th className="pb-2">계정</th><th className="pb-2">상태</th><th className="pb-2 text-right">사용량(30일)</th><th className="pb-2 text-right">한도(원)</th><th className="pb-2 text-right">관리</th>
                </tr></thead>
                <tbody>
                  {(team.members ?? []).map((m) => {
                    const u = usageMap[m.user_id];
                    const stLabel = m.status === "approved" ? <span className="text-emerald-400">승인</span>
                      : m.status === "pending" ? <span className="text-amber-400">가입대기</span>
                      : m.status === "invited" ? <span className="text-sky-400">초대중</span> : <span>{m.status}</span>;
                    return (
                      <tr key={m.user_id} className="border-t border-[var(--line)]">
                        <td className="py-2 font-medium text-[var(--text-primary)]">{m.email}{m.role === "owner" && " (팀장)"}</td>
                        <td className="py-2">{stLabel}</td>
                        <td className="py-2 text-right cc-num text-[var(--text-secondary)]">{u ? won(u.cost_krw) : "-"}</td>
                        <td className="py-2 text-right">
                          {m.role !== "owner" && m.status === "approved" ? (
                            <input type="number" defaultValue={m.usage_limit_krw || 0}
                              onBlur={(e) => { const v = Number(e.target.value || 0); if (v !== m.usage_limit_krw) setLimit(team.id, m.user_id, v); }}
                              className="cc-num w-24 rounded-md border border-[var(--line-strong)] bg-[var(--surface)] px-2 py-1 text-right text-xs" title="0=무제한" />
                          ) : "-"}
                        </td>
                        <td className="py-2 text-right">
                          {m.status === "pending" && <button onClick={() => approve(team.id, m.user_id)} disabled={busy} className="mr-1 rounded-md bg-[var(--accent-strong)] px-2 py-1 text-[11px] font-bold text-white">승인</button>}
                          {m.role !== "owner" && <button onClick={() => remove(team.id, m.user_id)} disabled={busy} className="rounded-md border border-rose-500/30 px-2 py-1 text-[11px] font-bold text-rose-400">제거</button>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-[10px] text-[var(--text-hint)]">※ 한도(원)=멤버 30일 사용 상한(0=무제한). 초대는 상대 동의 후 합류하며, 멤버는 자기 계정으로 로그인하되 팀의 프로젝트·구독 사용량을 공유합니다.</p>
          </div></section>
        );
      })}
    </div>
  );
}
