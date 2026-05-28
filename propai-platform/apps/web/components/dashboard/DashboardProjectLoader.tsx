"use client";

import { useEffect, useState } from "react";
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
  projects: ProjectSummary[];
};

const FALLBACK_PROJECTS: readonly ProjectSummary[] = [
  { id: "demo-gangnam", name: "강남 게이트웨이 복합시설", status: "AI 설계 단계", value: "12,940", tag: "ULTRA", progress: 68 },
  { id: "demo-songdo", name: "송도 이노베이션 루프", status: "사업 타당성 검토", value: "8,210", tag: "CORE", progress: 42 },
];

export function DashboardProjectLoader({ locale }: { locale: string }) {
  const [projects, setProjects] = useState<readonly ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function fetchProjects() {
      try {
        const res = await (async () => ({} as ProjectsResponse))();
        if (!cancelled && res.projects?.length) {
          setProjects(
            res.projects.map((p: any) => ({
              id: p.id ?? p.project_id ?? "",
              name: p.name ?? p.project_name ?? "Untitled",
              status: p.status ?? "진행중",
              value: p.value ?? "0",
              tag: p.tag ?? p.type ?? "CORE",
              progress: p.progress ?? 0,
            })),
          );
        } else if (!cancelled) {
          setProjects(FALLBACK_PROJECTS);
        }
      } catch {
        if (!cancelled) setProjects(FALLBACK_PROJECTS);
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

  return <ProjectCardGrid locale={locale} projects={projects} />;
}
