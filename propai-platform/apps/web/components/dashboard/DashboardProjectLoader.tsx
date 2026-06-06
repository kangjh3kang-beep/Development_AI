"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiClient } from "@/lib/api-client";
import { ProjectCardGrid } from "@/components/dashboard/DashboardDynamicElements";

type ProjectSummary = {
  id: string;
  name: string;
  status: string;
  value: string;
  tag: string;
  progress: number;
};

type ProjectsResponse = {
  projects?: ProjectSummary[];
  items?: ProjectSummary[];
};

export function DashboardProjectLoader({ locale }: { locale: string }) {
  const [projects, setProjects] = useState<readonly ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function fetchProjects() {
      try {
        const res = await apiClient.get<ProjectsResponse>("/projects");
        const list = res.projects ?? res.items ?? [];
        if (!cancelled) {
          // 목업(강남/송도) 제거 — 실제 프로젝트가 없으면 빈상태를 표시한다.
          setProjects(
            list.map((p: any) => ({
              id: p.id ?? p.project_id ?? "",
              name: p.name ?? p.project_name ?? "Untitled",
              status: p.status ?? "진행중",
              value: p.value ?? "0",
              tag: p.tag ?? p.type ?? "CORE",
              progress: p.progress ?? 0,
            })),
          );
        }
      } catch {
        if (!cancelled) setProjects([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchProjects();
    return () => { cancelled = true; };
  }, []);

  if (loading) {
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
  if (projects.length === 0) {
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

  return <ProjectCardGrid locale={locale} projects={projects} />;
}
