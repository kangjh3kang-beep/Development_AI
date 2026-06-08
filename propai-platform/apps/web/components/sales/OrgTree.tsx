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

  const load = useCallback(() => {
    // 조직도를 다 불러오면(성공/실패 무관) 자리표시를 걷어낸다.
    api.get<Node[]>("/org/tree").then((r) => setNodes(r || [])).catch(() => setNodes([])).finally(() => setLoaded(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteCode]);
  useEffect(() => { load(); }, [load]);

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

  // 처음 불러오는 중이면 회색 자리표시(스켈레톤)로 빈 화면 깜빡임을 막는다.
  if (!loaded) return <SkeletonLoader count={3} itemClassName="h-16 rounded-xl mb-3" />;
  return (
    <div className="space-y-4">
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
        {tree.length === 0 && <p className="text-sm text-[var(--text-secondary)]">조직 노드가 없습니다. 위에서 최상위(대행사)부터 추가하세요.</p>}
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
    </div>
  );
}
