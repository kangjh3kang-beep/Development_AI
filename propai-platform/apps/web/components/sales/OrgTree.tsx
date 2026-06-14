"use client";

/**
 * 분양 조직도 — ltree 계층 트리 + 노드 추가/이동.
 * 백엔드: GET /sales/org/tree · POST /sales/org/nodes · PATCH /sales/org/nodes/{id}/move
 */

import { useCallback, useEffect, useState } from "react";
import { salesApi } from "@/lib/salesApi";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";

interface Node { id: string; path: string; node_type: string; display_name?: string | null }

const NODE_TYPES: { value: string; label: string }[] = [
  { value: "AGENCY", label: "분양대행사" },
  { value: "SUBAGENCY", label: "대대행" },
  { value: "GM_DIRECTOR", label: "총괄본부장" },
  { value: "DIRECTOR", label: "본부장" },
  { value: "TEAM_LEADER", label: "팀장" },
  { value: "MEMBER", label: "팀원" },
];
const LABEL: Record<string, string> = Object.fromEntries(NODE_TYPES.map((t) => [t.value, t.label]));
const fcls = "rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1.5 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]";

export default function OrgTree({ siteCode }: { siteCode: string }) {
  const api = salesApi(siteCode);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [parentId, setParentId] = useState("");
  const [nodeType, setNodeType] = useState("DIRECTOR");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  // loaded: 조직도를 한 번 불러왔는지 표시(false면 '불러오는 중' 회색 자리표시를 보여줌).
  const [loaded, setLoaded] = useState(false);
  type Ov = { members: number; totals: { contracts: number; customers: number; work_logs: number }; roster: { node_id: string; name: string; role_label: string; assigned: boolean; contracts: number; customers: number; work_logs: number; tax_type?: string }[] };
  const [ov, setOv] = useState<Ov | null>(null);
  // #5 해촉/정산 — 노드 수수료 정산 명세(기발생−기지급=미지급, 세금분개).
  type Settle = { tax_type: string; contracts: number; earned_gross: number; paid_gross: number; outstanding_gross: number; settlement: { withholding: number; vat: number; net: number; total_paid: number } };
  const [settle, setSettle] = useState<{ name: string; data: Settle } | null>(null);

  const load = useCallback(() => {
    // 조직도를 다 불러오면(성공/실패 무관) 자리표시를 걷어낸다.
    api.get<Node[]>("/org/tree").then((r) => setNodes(r || [])).catch(() => setNodes([])).finally(() => setLoaded(true));
    api.get<Ov>("/org/team-overview").then((r) => setOv(r)).catch(() => setOv(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteCode]);
  useEffect(() => { load(); }, [load]);
  const setTax = async (nodeId: string, taxType: string) => {
    try { await api.post("/commission/tax-pref", { node_id: nodeId, tax_type: taxType }); load(); }
    catch { alert("세금유형 저장 실패(권한 확인)"); }
  };
  // P2-3 인원배정: 같은 조직 사용자를 이메일로 노드에 배정/해제(미배정 해소).
  const assignUser = async (nodeId: string) => {
    const email = prompt("배정할 사용자의 이메일(같은 조직 가입자)")?.trim();
    if (!email) return;
    try { const r = await api.post<{ name: string }>(`/org/nodes/${nodeId}/assign`, { email }); alert(`배정 완료: ${r?.name ?? email}`); load(); }
    catch (e) { alert(e instanceof Error && e.message ? e.message : "배정 실패"); }
  };
  const unassignUser = async (nodeId: string) => {
    if (!confirm("이 인원 배정을 해제할까요? (노드·실적은 유지)")) return;
    try { await api.post(`/org/nodes/${nodeId}/unassign`, {}); load(); }
    catch (e) { alert(e instanceof Error && e.message ? e.message : "해제 실패"); }
  };
  const loadSettle = async (nodeId: string, name: string) => {
    try { const d = await api.get<Settle>(`/commission/settle-summary?node_id=${nodeId}`); setSettle({ name, data: d }); }
    catch (e) { alert(e instanceof Error && e.message ? e.message : "정산 명세 조회 실패"); }
  };
  const won = (n: number) => `${(n || 0).toLocaleString()}원`;

  const tree = nodes.slice().sort((a, b) => a.path.localeCompare(b.path));
  const depth = (p: string) => p.split(".").length - 1;

  const addNode = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      await api.post("/org/nodes", { node_type: nodeType, parent_id: parentId || undefined, display_name: name.trim() });
      setName(""); load();
    } catch { alert("노드 추가 실패(권한을 확인하세요)"); }
    finally { setBusy(false); }
  };
  const move = async (id: string, newParent: string) => {
    if (!newParent) return;
    try { await api.patch(`/org/nodes/${id}/move`, { new_parent_id: newParent }); load(); }
    catch { alert("이동 실패(권한/순환 확인)"); }
  };
  const seedDefault = async () => {
    if (!confirm("기본조직(대행사→본부장→5팀×10명)을 생성할까요? 빈 조직에서만 가능합니다.")) return;
    setBusy(true);
    try {
      const r = await api.post<{ ok: boolean; total?: number; note?: string }>("/org/seed-default", {});
      if (r?.ok) load(); else alert(r?.note || "생성 실패");
    } catch { alert("기본조직 생성 실패(권한을 확인하세요)."); }
    finally { setBusy(false); }
  };

  // 처음 불러오는 중이면 회색 자리표시(스켈레톤)로 빈 화면 깜빡임을 막는다.
  if (!loaded) return <SkeletonLoader count={3} itemClassName="h-16 rounded-xl mb-3" />;
  return (
    <div className="space-y-4">
      {/* P2-3 팀 현황(내 하위 조직 활동 집계) */}
      {ov && ov.members > 0 && (
        <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
          <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
            <span className="font-bold text-[var(--text-secondary)]">팀 현황(하위 조직)</span>
            <span className="text-[var(--text-tertiary)]">관리대상 <b className="text-[var(--text-primary)]">{ov.members}</b>명</span>
            <span className="text-[var(--text-tertiary)]">계약 <b className="text-[var(--accent-strong)]">{ov.totals.contracts}</b></span>
            <span className="text-[var(--text-tertiary)]">고객 <b className="text-[var(--accent-strong)]">{ov.totals.customers}</b></span>
            <span className="text-[var(--text-tertiary)]">업무일지 <b className="text-[var(--accent-strong)]">{ov.totals.work_logs}</b></span>
          </div>
          <div className="max-h-40 overflow-auto">
            <table className="w-full text-[11px]">
              <thead><tr className="text-[var(--text-hint)]"><th className="text-left font-medium">직급</th><th className="text-left font-medium">이름</th><th className="text-center font-medium">인원</th><th className="text-right font-medium">계약</th><th className="text-right font-medium">고객</th><th className="text-right font-medium">업무일지</th><th className="text-right font-medium">수수료세금</th><th className="text-center font-medium">정산</th></tr></thead>
              <tbody>
                {ov.roster.slice(0, 30).map((r, i) => (
                  <tr key={i} className="border-t border-[var(--line)]/50">
                    <td className="py-0.5 text-[var(--text-tertiary)]">{r.role_label}</td>
                    <td className="text-[var(--text-secondary)]">{r.name}{!r.assigned && <span className="ml-1 text-[9px] text-[var(--text-hint)]">(미배정)</span>}</td>
                    <td className="text-center">
                      {r.assigned ? (
                        <button onClick={() => unassignUser(r.node_id)} className="rounded border border-[var(--line)] px-1.5 py-0.5 text-[9px] text-[var(--text-tertiary)]" title="배정 해제">해제</button>
                      ) : (
                        <button onClick={() => assignUser(r.node_id)} className="rounded border border-[var(--accent-strong)] px-1.5 py-0.5 text-[9px] font-bold text-[var(--accent-strong)]">배정</button>
                      )}
                    </td>
                    <td className="text-right text-[var(--text-primary)]">{r.contracts}</td>
                    <td className="text-right text-[var(--text-primary)]">{r.customers}</td>
                    <td className="text-right text-[var(--text-primary)]">{r.work_logs}</td>
                    <td className="text-right"><select value={r.tax_type || "WITHHOLDING"} onChange={(e) => setTax(r.node_id, e.target.value)} className="rounded border border-[var(--line)] bg-[var(--surface-strong)] px-1 py-0.5 text-[10px] text-[var(--text-secondary)]"><option value="WITHHOLDING">3.3% 원천</option><option value="VAT">부가세10%</option></select></td>
                    <td className="text-center"><button onClick={() => loadSettle(r.node_id, r.name)} className="rounded border border-[var(--line)] px-1.5 py-0.5 text-[9px] font-bold text-[var(--text-secondary)]" title="해촉/정산 명세">정산</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-1 text-[10px] text-[var(--text-hint)]">근태·수수료·단체메시지는 각 전용 탭(수수료·방문 데스크·소셜)에서 관리합니다.</p>
        </div>
      )}

      {/* 노드 추가 */}
      <div className="flex flex-wrap items-end gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
        <label className="flex flex-col gap-1"><span className="text-[10px] text-[var(--text-tertiary)]">상위(부모)</span>
          <select value={parentId} onChange={(e) => setParentId(e.target.value)} className={`${fcls} w-44`}>
            <option value="">최상위(대행사)</option>
            {tree.map((n) => <option key={n.id} value={n.id}>{"·".repeat(depth(n.path))}{LABEL[n.node_type] ?? n.node_type} {n.display_name ?? ""}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1"><span className="text-[10px] text-[var(--text-tertiary)]">직급</span>
          <select value={nodeType} onChange={(e) => setNodeType(e.target.value)} className={`${fcls} w-32`}>
            {NODE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </label>
        <label className="flex flex-1 flex-col gap-1"><span className="text-[10px] text-[var(--text-tertiary)]">이름</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="예: 김본부" className={`${fcls} min-w-[140px]`} onKeyDown={(e) => { if (e.key === "Enter") void addNode(); }} />
        </label>
        <button onClick={addNode} disabled={busy} className="rounded-lg bg-[var(--accent-strong)] px-4 py-2 text-sm font-black text-white disabled:opacity-50">＋ 추가</button>
      </div>

      {/* 트리 */}
      <div className="space-y-1 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
        {tree.length === 0 && (
          <div className="flex flex-col items-start gap-2">
            <p className="text-sm text-[var(--text-secondary)]">조직 노드가 없습니다. 위에서 최상위(대행사)부터 추가하거나, 기본조직을 한 번에 생성하세요.</p>
            <button onClick={seedDefault} disabled={busy}
              className="rounded-lg border border-[var(--accent-strong)] px-3 py-1.5 text-xs font-black text-[var(--accent-strong)] hover:bg-[var(--accent-soft)] disabled:opacity-50">
              🏢 기본조직 생성 (대행사→본부장→5팀×10명)
            </button>
          </div>
        )}
        {tree.map((n) => (
          <div key={n.id} className="flex flex-wrap items-center gap-2 rounded-lg py-1 text-sm hover:bg-[var(--surface)]" style={{ paddingLeft: `${depth(n.path) * 18}px` }}>
            <span className="rounded bg-[var(--surface-strong)] px-1.5 py-0.5 text-xs font-semibold text-[var(--accent-strong)]">{LABEL[n.node_type] ?? n.node_type}</span>
            <span className="font-semibold text-[var(--text-primary)]">{n.display_name ?? "-"}</span>
            <select value="" onChange={(e) => move(n.id, e.target.value)} className="ml-auto rounded border border-[var(--line)] bg-[var(--surface-strong)] px-1.5 py-0.5 text-[11px] text-[var(--text-secondary)]" title="상위 이동">
              <option value="">이동…</option>
              {tree.filter((x) => x.id !== n.id && !x.path.startsWith(n.path)).map((x) => (
                <option key={x.id} value={x.id}>→ {LABEL[x.node_type] ?? x.node_type} {x.display_name ?? ""} 하위로</option>
              ))}
            </select>
          </div>
        ))}
      </div>
      <p className="text-[11px] text-[var(--text-hint)]">계층(대행사＞대대행＞총괄본부장＞본부장＞팀장＞팀원)은 수수료 2단 배분의 기준이 됩니다. 이동 시 하위 조직도 함께 이동합니다.</p>

      {/* #5 해촉/정산 명세 모달 */}
      {settle && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setSettle(null)}>
          <div className="mx-4 w-full max-w-md rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5 shadow-[var(--shadow-lg)]" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="font-black text-[var(--text-primary)]">해촉/정산 명세 — {settle.name}</h3>
              <button onClick={() => setSettle(null)} className="text-[var(--text-tertiary)]">✕</button>
            </div>
            <div className="space-y-1.5 text-sm">
              <div className="flex justify-between"><span className="text-[var(--text-secondary)]">계약 기여</span><b className="text-[var(--text-primary)]">{settle.data.contracts}건</b></div>
              <div className="flex justify-between"><span className="text-[var(--text-secondary)]">기발생 수수료</span><b className="text-[var(--text-primary)]">{won(settle.data.earned_gross)}</b></div>
              <div className="flex justify-between"><span className="text-[var(--text-secondary)]">기지급</span><b className="text-emerald-400">{won(settle.data.paid_gross)}</b></div>
              <div className="flex justify-between border-t border-[var(--line)] pt-1.5"><span className="font-bold text-[var(--text-primary)]">미지급 정산액</span><b className="text-[var(--accent-strong)]">{won(settle.data.outstanding_gross)}</b></div>
              <div className="mt-2 rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] p-2.5 text-xs">
                <p className="mb-1 font-bold text-[var(--text-secondary)]">{settle.data.tax_type === "VAT" ? "부가세 10%(세금계산서)" : "원천징수 3.3%(사업소득)"}</p>
                {settle.data.tax_type === "VAT" ? (
                  <>
                    <div className="flex justify-between"><span className="text-[var(--text-tertiary)]">부가세</span><span>{won(settle.data.settlement.vat)}</span></div>
                    <div className="flex justify-between"><span className="text-[var(--text-tertiary)]">지급총액(공급가+부가세)</span><b>{won(settle.data.settlement.total_paid)}</b></div>
                  </>
                ) : (
                  <>
                    <div className="flex justify-between"><span className="text-[var(--text-tertiary)]">원천징수(3.3%)</span><span className="text-rose-400">−{won(settle.data.settlement.withholding)}</span></div>
                    <div className="flex justify-between"><span className="text-[var(--text-tertiary)]">실수령</span><b className="text-[var(--accent-strong)]">{won(settle.data.settlement.net)}</b></div>
                  </>
                )}
              </div>
              <p className="mt-1 text-[10px] text-[var(--text-hint)]">※ 환수(계약취소)분 제외·기발생 기준. 자금이체는 시스템이 수행하지 않습니다(명세 산출).</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
