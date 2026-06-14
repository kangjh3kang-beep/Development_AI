"use client";

/**
 * 동·호 추첨 모드 — 추첨그룹·대상자(수기/Excel/계약자명부/청약당첨자)·순번 즉석추첨(무작위 동호 공개)·seed 감사.
 * 청약→당첨→동·호배정 흐름 연결: 청약 당첨자 명부를 당첨 우선순위 순번대로 추첨 대상자로 자동 시드.
 * 백엔드: /sales/draw/groups(목록·생성)·/{id}/candidates(+excel·from-customers·from-winners)·/{id}/candidates/{cid}/draw·/status
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { salesApi } from "@/lib/salesApi";

interface Group { id: string; name: string; status: string; candidates: number; drawn: number }
interface Ann { id: string; announce_no?: string; status: string }
interface RosterItem { id: string; seq: number; name: string; phone?: string; assigned_unit_id?: string | null; assigned_label?: string | null; seed?: string | null; done: boolean; contract_id?: string | null }
interface Status { group_id: string; name: string; candidates: number; drawn: number; remaining_units: number; roster: RosterItem[] }
interface DrawResult { candidate: { seq: number; name: string }; assigned_unit: { dong?: string; ho?: string }; seed: string; pool_size: number; remaining_after: number }

export default function DrawMode({ siteCode }: { siteCode: string }) {
  const api = salesApi(siteCode);
  const [groups, setGroups] = useState<Group[]>([]);
  const [gid, setGid] = useState<string>("");
  const [st, setSt] = useState<Status | null>(null);
  const [newName, setNewName] = useState("");
  const [manual, setManual] = useState("");
  const [anns, setAnns] = useState<Ann[]>([]);
  const [annId, setAnnId] = useState("");
  const [busy, setBusy] = useState(false);
  const [reveal, setReveal] = useState<DrawResult | null>(null);
  const [rolling, setRolling] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadGroups = useCallback(() => {
    api.get<Group[]>("/draw/groups").then((g) => setGroups(g || [])).catch(() => setGroups([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteCode]);
  const loadStatus = useCallback((g: string) => {
    if (!g) { setSt(null); return; }
    api.get<Status>(`/draw/groups/${g}/status`).then(setSt).catch(() => setSt(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteCode]);

  useEffect(() => { loadGroups(); }, [loadGroups]);
  useEffect(() => { loadStatus(gid); }, [gid, loadStatus]);
  useEffect(() => {
    api.get<Ann[]>("/subscription/announcements").then((a) => setAnns(a || [])).catch(() => setAnns([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteCode]);

  const createGroup = async () => {
    if (!newName.trim()) return;
    setBusy(true);
    try {
      const r = await api.post<{ id: string }>("/draw/groups", { name: newName.trim() });
      setNewName(""); loadGroups(); if (r?.id) setGid(r.id);
    } catch { alert("그룹 생성 실패(권한 확인)"); } finally { setBusy(false); }
  };
  const addManual = async () => {
    const rows = manual.split("\n").map((l) => l.trim()).filter(Boolean).map((line) => {
      const [name, phone] = line.split(/[,\t]/).map((s) => s.trim());
      return { name, phone };
    });
    if (!rows.length) return;
    setBusy(true);
    try { await api.post(`/draw/groups/${gid}/candidates`, { rows }); setManual(""); loadStatus(gid); loadGroups(); }
    catch { alert("대상자 등록 실패"); } finally { setBusy(false); }
  };
  const fromCustomers = async () => {
    if (!confirm("계약자/고객 명부 전체를 추첨 대상자로 등록할까요?")) return;
    setBusy(true);
    try { const r = await api.post<{ added: number }>(`/draw/groups/${gid}/candidates/from-customers`, {}); alert(`${r?.added ?? 0}명 등록`); loadStatus(gid); }
    catch { alert("명부 등록 실패"); } finally { setBusy(false); }
  };
  // 청약→당첨→동·호배정 연계: 선택 공고의 당첨자를 당첨 우선순위 순번대로 추첨 대상자로 시드.
  const fromWinners = async () => {
    if (!annId) { alert("청약 공고를 선택하세요"); return; }
    setBusy(true);
    try {
      const r = await api.post<{ added: number; note?: string }>(`/draw/groups/${gid}/candidates/from-winners`, { announcement_id: annId });
      alert(r?.note ? r.note : `청약 당첨자 ${r?.added ?? 0}명을 추첨 대상자로 등록(당첨 우선순위 순번)`);
      loadStatus(gid); loadGroups();
    } catch (e) { alert(e instanceof Error && e.message ? e.message : "당첨자 등록 실패"); } finally { setBusy(false); }
  };
  const uploadExcel = async (file: File) => {
    setBusy(true);
    try {
      const fd = new FormData(); fd.append("file", file);
      const r = await api.post<{ added: number }>(`/draw/groups/${gid}/candidates/excel`, fd as unknown as Record<string, unknown>);
      alert(`엑셀 ${r?.added ?? 0}명 등록`); loadStatus(gid);
    } catch { alert("엑셀 업로드 실패(.xlsx, 1행 헤더: 이름/연락처)"); } finally { setBusy(false); if (fileRef.current) fileRef.current.value = ""; }
  };
  // 즉석추첨 — 대상자가 누르면 무작위 동호 공개(룰렛 애니메이션 후 결과).
  const draw = async (cid: string) => {
    if (busy || rolling) return;
    setRolling(true); setReveal(null);
    try {
      const r = await api.post<DrawResult>(`/draw/groups/${gid}/candidates/${cid}/draw`, {});
      // 공개 연출(0.9s 룰렛 후 결과 표시).
      setTimeout(() => { setReveal(r); setRolling(false); loadStatus(gid); loadGroups(); }, 900);
    } catch (e) {
      setRolling(false);
      alert(e instanceof Error && e.message ? e.message : "추첨 실패");
    }
  };

  // 추첨 배정(HOLD) 당첨자 → 계약 생성(청약→당첨→동·호배정→계약 완결).
  const makeContract = async (cid: string) => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await api.post<{ existing?: boolean; stage?: string }>(`/draw/groups/${gid}/candidates/${cid}/contract`, {});
      alert(r?.existing ? "이미 계약이 생성된 세대입니다." : `계약 생성 완료(${r?.stage ?? "RESERVED"}) — 수납·대출 화면에서 이어집니다.`);
      loadStatus(gid);
    } catch (e) { alert(e instanceof Error && e.message ? e.message : "계약 생성 실패"); } finally { setBusy(false); }
  };

  const nextTurn = st?.roster.find((r) => !r.done);
  const progress = st && st.candidates ? Math.round((st.drawn / st.candidates) * 100) : 0;

  return (
    <div className="space-y-4">
      {/* 그룹 선택/생성 */}
      <div className="flex flex-wrap items-end gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
        <label className="flex flex-col gap-1"><span className="text-[10px] text-[var(--text-tertiary)]">추첨그룹</span>
          <select value={gid} onChange={(e) => setGid(e.target.value)} className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1.5 text-sm">
            <option value="">— 그룹 선택 —</option>
            {groups.map((g) => <option key={g.id} value={g.id}>{g.name} ({g.drawn}/{g.candidates})</option>)}
          </select>
        </label>
        <label className="flex flex-1 flex-col gap-1"><span className="text-[10px] text-[var(--text-tertiary)]">새 그룹</span>
          <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="예: 1차 추첨" className="min-w-[140px] rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1.5 text-sm" onKeyDown={(e) => { if (e.key === "Enter") void createGroup(); }} />
        </label>
        <button onClick={createGroup} disabled={busy} className="rounded-lg bg-[var(--accent-strong)] px-4 py-2 text-sm font-black text-white disabled:opacity-50">＋ 그룹 생성</button>
      </div>

      {!gid ? (
        <p className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-6 text-sm text-[var(--text-secondary)]">추첨그룹을 선택하거나 새로 생성하세요. 그룹별로 대상자를 등록하고 순번대로 즉석추첨합니다.</p>
      ) : (
        <>
          {/* 대상자 등록(3방식) */}
          <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
            <p className="mb-2 cc-label text-[0.6rem] text-[var(--text-tertiary)]">대상자 등록</p>
            <div className="flex flex-wrap items-start gap-2">
              <div className="flex flex-1 flex-col gap-1">
                <textarea value={manual} onChange={(e) => setManual(e.target.value)} rows={2} placeholder="수기: 한 줄에 한 명 (이름,연락처)" className="w-full rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1.5 text-sm" />
                <button onClick={addManual} disabled={busy || !manual.trim()} className="self-start rounded-lg border border-[var(--line)] px-3 py-1.5 text-xs font-bold text-[var(--text-secondary)] disabled:opacity-50">수기 등록</button>
              </div>
              <div className="flex flex-col gap-1">
                <input ref={fileRef} type="file" accept=".xlsx" onChange={(e) => e.target.files?.[0] && uploadExcel(e.target.files[0])} className="text-xs" />
                <button onClick={fromCustomers} disabled={busy} className="rounded-lg border border-[var(--line)] px-3 py-1.5 text-xs font-bold text-[var(--text-secondary)] disabled:opacity-50">계약자명부 전체</button>
              </div>
            </div>
            {/* 청약→당첨→동·호배정 연계: 당첨자 명부를 당첨 우선순위 순번대로 시드 */}
            <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-[var(--line)] pt-2">
              <span className="text-[10px] text-[var(--text-tertiary)]">🎟️ 청약 연계</span>
              <select value={annId} onChange={(e) => setAnnId(e.target.value)} className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1.5 text-xs">
                <option value="">청약 공고 선택…</option>
                {anns.map((a) => <option key={a.id} value={a.id}>{a.announce_no ?? a.id.slice(0, 8)} · {a.status}</option>)}
              </select>
              <button onClick={fromWinners} disabled={busy || !annId} className="rounded-lg border border-[var(--accent-strong)] px-3 py-1.5 text-xs font-bold text-[var(--accent-strong)] disabled:opacity-50">당첨자 시드</button>
              <span className="text-[10px] text-[var(--text-hint)]">당첨 우선순위(순위·가점)대로 추첨 대상자 자동 등록</span>
            </div>
          </div>

          {/* 진행률 */}
          {st && (
            <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="font-bold text-[var(--text-secondary)]">{st.name}</span>
                <span className="text-[var(--text-tertiary)]">완료 {st.drawn}/{st.candidates} · 남은세대 {st.remaining_units}</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-[var(--surface-strong)]">
                <div className="h-2 rounded-full bg-[var(--accent-strong)] transition-all" style={{ width: `${progress}%` }} />
              </div>
            </div>
          )}

          {/* 순번 추첨 패널 */}
          <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
            <p className="mb-2 cc-label text-[0.6rem] text-[var(--text-tertiary)]">순번 추첨 (즉석·무작위)</p>
            {nextTurn && (
              <div className="mb-3 flex items-center justify-between gap-2 rounded-lg border border-[var(--accent-strong)] bg-[var(--accent-soft)] p-3">
                <span className="text-sm font-black text-[var(--text-primary)]">▶ 지금 차례: #{nextTurn.seq} {nextTurn.name}</span>
                <button onClick={() => draw(nextTurn.id)} disabled={rolling || busy}
                  className="rounded-lg bg-[var(--accent-strong)] px-5 py-2.5 text-sm font-black text-white disabled:opacity-60">
                  {rolling ? "🎲 추첨 중…" : "🎲 추첨하기"}
                </button>
              </div>
            )}
            <div className="max-h-64 space-y-1 overflow-auto">
              {(st?.roster ?? []).map((r) => (
                <div key={r.id} className={`flex items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-sm ${r.done ? "bg-[var(--surface)]" : nextTurn?.id === r.id ? "bg-[var(--accent-soft)]" : ""}`}>
                  <span className="text-[var(--text-secondary)]">#{r.seq} {r.name}</span>
                  {r.done ? (
                    <span className="flex items-center gap-2">
                      <b className="text-[var(--accent-strong)]">{r.assigned_label}</b>
                      {r.seed && <span className="font-mono text-[9px] text-[var(--text-hint)]" title="추첨 seed(감사·재현검증)">seed {r.seed.slice(0, 8)}</span>}
                      {r.contract_id ? (
                        <span className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-bold text-emerald-400">계약완료</span>
                      ) : (
                        <button onClick={() => makeContract(r.id)} disabled={busy}
                          className="rounded-md border border-[var(--accent-strong)] px-2 py-0.5 text-[10px] font-bold text-[var(--accent-strong)] disabled:opacity-50">계약 생성</button>
                      )}
                    </span>
                  ) : <span className="text-[10px] text-[var(--text-hint)]">대기</span>}
                </div>
              ))}
              {(!st || st.roster.length === 0) && <p className="text-xs text-[var(--text-hint)]">대상자를 먼저 등록하세요.</p>}
            </div>
          </div>
        </>
      )}

      {/* 추첨 공개 모달 */}
      {(rolling || reveal) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => !rolling && setReveal(null)}>
          <div className="mx-4 w-full max-w-sm rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-6 text-center shadow-[var(--shadow-lg)]">
            {rolling ? (
              <>
                <div className="mb-3 text-4xl animate-bounce">🎲</div>
                <p className="text-lg font-black text-[var(--text-primary)]">추첨 중…</p>
                <p className="mt-1 text-xs text-[var(--text-tertiary)]">남은 동·호 중 무작위 배정</p>
              </>
            ) : reveal ? (
              <>
                <p className="text-xs text-[var(--text-tertiary)]">#{reveal.candidate.seq} {reveal.candidate.name} 님 당첨</p>
                <p className="my-3 text-3xl font-black text-[var(--accent-strong)]">{reveal.assigned_unit.dong}동 {reveal.assigned_unit.ho}호</p>
                <p className="font-mono text-[10px] text-[var(--text-hint)]">seed {reveal.seed} · 후보 {reveal.pool_size} · 남은 {reveal.remaining_after}</p>
                <button onClick={() => setReveal(null)} className="mt-4 w-full rounded-lg bg-[var(--accent-strong)] px-4 py-2 text-sm font-black text-white">확인</button>
              </>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
