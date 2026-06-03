"use client";

import { useEffect, useState } from "react";
import { salesApi } from "@/lib/salesApi";

interface Node { id: string; path: string; node_type: string; display_name?: string }
const LABEL: Record<string, string> = {
  AGENCY: "분양대행사", SUBAGENCY: "대대행", GM_DIRECTOR: "총괄본부장",
  DIRECTOR: "본부장", TEAM_LEADER: "팀장", MEMBER: "팀원",
};

export default function OrgTree({ siteCode }: { siteCode: string }) {
  const [nodes, setNodes] = useState<Node[]>([]);
  useEffect(() => {
    salesApi(siteCode).get<Node[]>("/org/tree").then(setNodes).catch(() => setNodes([]));
  }, [siteCode]);
  const tree = nodes.slice().sort((a, b) => a.path.localeCompare(b.path));
  return (
    <div className="space-y-1 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
      {tree.length === 0 && <p className="text-sm text-[var(--text-secondary)]">조직 노드가 없습니다.</p>}
      {tree.map((n) => (
        <div key={n.id} className="flex items-center text-sm"
          style={{ paddingLeft: `${(n.path.split(".").length - 1) * 18}px` }}>
          <span className="mr-2 rounded bg-[var(--surface-strong)] px-1.5 py-0.5 text-xs font-semibold text-[var(--accent-strong)]">
            {LABEL[n.node_type] ?? n.node_type}
          </span>
          <span className="text-[var(--text-primary)]">{n.display_name ?? "-"}</span>
        </div>
      ))}
    </div>
  );
}
