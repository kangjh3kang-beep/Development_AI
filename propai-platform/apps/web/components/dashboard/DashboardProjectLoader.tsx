"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useProjectStore } from "@/store/useProjectStore";
import { ProjectCardGrid } from "@/components/dashboard/DashboardDynamicElements";

// 프로젝트 단계 → 표시 라벨/진행률 매핑(관리목록 ProjectsOverviewClient와 동일 단계 체계).
const _PHASE_LABEL: Record<string, string> = {
  draft: "초안", planning: "기획", design: "설계", permit: "인허가",
  construction: "시공", completed: "완료", archived: "보관",
};
const _PHASE_PROGRESS: Record<string, number> = {
  draft: 5, planning: 20, design: 45, permit: 65,
  construction: 85, completed: 100, archived: 100,
};
// 삭제/보관 상태는 대시보드 활성 진행 단계에서 제외(이중 방어).
const _HIDDEN_STATUS = new Set(["archived", "deleted"]);

export function DashboardProjectLoader({ locale }: { locale: string }) {
  const projects = useProjectStore((s) => s.projects);
  const syncing = useProjectStore((s) => s.syncing);
  const syncFromBackend = useProjectStore((s) => s.syncFromBackend);

  // 관리목록과 동일 권위 소스(백엔드 /projects, is_deleted 필터)로 재동기화.
  // 삭제는 deleteProject가 백엔드 소프트삭제 + 로컬 제거를 일관 처리하므로,
  // 동일 스토어를 구독하면 삭제분이 대시보드에서도 즉시 제외된다.
  useEffect(() => {
    void syncFromBackend();
  }, [syncFromBackend]);

  // 방어적 삭제필터 → 최신순(createdAt desc) → 상위 6개.
  const cards = projects
    .filter((p) => !_HIDDEN_STATUS.has(p.status))
    .slice()
    .sort((a, b) => (b.createdAt || "").localeCompare(a.createdAt || ""))
    .slice(0, 6)
    .map((p) => ({
      id: p.id,
      name: p.name || "Untitled",
      status: _PHASE_LABEL[p.status] || p.status || "진행중",
      value: p.area || "0",
      tag: p.type || "CORE",
      progress: _PHASE_PROGRESS[p.status] ?? 0,
    }));

  if (syncing && projects.length === 0) {
    return (
      <div className="grid gap-6 sm:grid-cols-2">
        {[1, 2].map((i) => (
          <div
            key={i}
            className="h-[200px] animate-pulse rounded-[2rem] bg-[var(--surface-soft)] border border-[var(--line)]"
          />
        ))}
      </div>
    );
  }

  // 빈상태 — 진행 중 프로젝트가 없을 때 프로젝트 생성 유도(목업 대체).
  if (cards.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 rounded-[2rem] border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] px-8 py-14 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-[var(--accent-strong)]">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9.5 12 4l9 5.5" /><path d="M5 11v8a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-8" /></svg>
        </div>
        <div className="space-y-1">
          <p className="text-base font-bold text-[var(--text-primary)]">진행 중인 프로젝트가 없습니다</p>
          <p className="text-sm text-[var(--text-secondary)]">새 프로젝트를 생성해 부지분석부터 시작하세요.</p>
        </div>
        <Link
          href={`/${locale}/projects/new`}
          className="mt-1 inline-flex items-center gap-2 rounded-xl bg-gradient-to-br from-[var(--accent-strong)] to-[var(--accent)] px-6 py-2.5 text-sm font-bold text-white shadow-[var(--shadow-glow)] transition-all hover:scale-[1.03] active:scale-[0.97]"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14" /><path d="M5 12h14" /></svg>
          프로젝트 생성
        </Link>
      </div>
    );
  }

  return <ProjectCardGrid locale={locale} projects={cards} />;
}
