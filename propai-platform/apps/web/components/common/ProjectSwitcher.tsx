"use client";

/**
 * 프로젝트 선택기 — CAD/BIM 스튜디오 등 독립 메뉴에서 대상 프로젝트를 고른다.
 * 선택 시 프로젝트 컨텍스트(스냅샷·분석 복원)로 전환 → 하위 워크스페이스가 해당 프로젝트로 동작.
 */

import { useEffect } from "react";
import { useProjectStore } from "@/store/useProjectStore";
import { useProjectContextStore } from "@/store/useProjectContextStore";

export function ProjectSwitcher({ onSelect }: { onSelect?: (projectId: string) => void }) {
  const projects = useProjectStore((s) => s.projects);
  const syncFromBackend = useProjectStore((s) => s.syncFromBackend);
  const activeId = useProjectContextStore((s) => s.projectId);
  const setProject = useProjectContextStore((s) => s.setProject);

  useEffect(() => {
    if (!projects.length) void syncFromBackend();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] px-5 py-4">
      <span className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)]">대상 프로젝트</span>
      <select
        value={activeId || ""}
        onChange={(e) => {
          const id = e.target.value;
          const p = projects.find((x) => x.id === id);
          if (p) { setProject(p.id, p.name, p.status); onSelect?.(p.id); }
        }}
        className="min-w-[260px] flex-1 rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-4 py-2.5 text-sm font-semibold text-[var(--text-primary)] outline-none"
      >
        <option value="">프로젝트를 선택하세요</option>
        {projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}{p.address ? ` — ${p.address}` : ""}
          </option>
        ))}
      </select>
      {!projects.length && (
        <span className="text-[11px] text-[var(--text-hint)]">프로젝트가 없습니다 — ‘프로젝트 관리’에서 먼저 생성하세요.</span>
      )}
    </div>
  );
}
