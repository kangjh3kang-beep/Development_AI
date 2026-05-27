"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent } from "@propai/ui";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { apiClient } from "@/lib/api-client";
import type {
  ProjectListResponse,
  ProjectModuleKey,
} from "@/mocks/types";
import { useAppStore } from "@/store/use-app-store";
import { useProjectStore } from "@/store/use-project-store";

type WorkspaceLabels = {
  viewGridLabel: string;
  viewListLabel: string;
  selectProjectLabel: string;
  selectedLabel: string;
  lastUpdatedLabel: string;
  nextActionLabel: string;
  modulesLabel: string;
  openProjectLabel: string;
  emptyStateTitle: string;
  emptyStateDescription: string;
  errorStateTitle: string;
  errorStateDescription: string;
  retryLabel: string;
};

type ProjectsOverviewClientProps = {
  locale: string;
  labels: WorkspaceLabels;
  moduleLabels: Record<ProjectModuleKey, string>;
};

function formatDate(locale: string, value: string) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function getProjectsErrorDetail(error: unknown) {
  if (error instanceof Error && error.message) {
    return error.message;
  }

  return null;
}

export function ProjectsOverviewClient({
  locale,
  labels,
  moduleLabels,
}: ProjectsOverviewClientProps) {
  const projectViewMode = useAppStore((state) => state.projectViewMode);
  const setProjectViewMode = useAppStore((state) => state.setProjectViewMode);
  const currentProjectId = useProjectStore((state) => state.currentProjectId);
  const setCurrentProject = useProjectStore((state) => state.setCurrentProject);

  const projectsQuery = useQuery({
    queryKey: ["projects", "list"],
    queryFn: () => apiClient.get<ProjectListResponse>("/projects"),
  });
  const hasProjects = (projectsQuery.data?.projects.length ?? 0) > 0;
  const errorDetail = getProjectsErrorDetail(projectsQuery.error);

  return (
    <section className="grid gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4 px-2">
        <div className="flex gap-2 p-1 bg-[var(--surface-strong)] rounded-full border border-[var(--line-strong)]">
          <button
            type="button"
            onClick={() => setProjectViewMode("grid")}
            className={`rounded-full px-6 py-2 text-xs font-black uppercase tracking-widest transition-all ${
              projectViewMode === "grid"
                ? "bg-[var(--accent-strong)] text-white shadow-[var(--shadow-glow)]"
                : "text-[var(--text-hint)] hover:text-[var(--text-primary)]"
            }`}
          >
            {labels.viewGridLabel}
          </button>
          <button
            type="button"
            onClick={() => setProjectViewMode("list")}
            className={`rounded-full px-6 py-2 text-xs font-black uppercase tracking-widest transition-all ${
              projectViewMode === "list"
                ? "bg-[var(--accent-strong)] text-white shadow-[var(--shadow-glow)]"
                : "text-[var(--text-hint)] hover:text-[var(--text-primary)]"
            }`}
          >
            {labels.viewListLabel}
          </button>
        </div>
        {projectsQuery.data && (
          <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">
            {labels.lastUpdatedLabel}:{" "}
            <span className="text-[var(--text-secondary)]">{formatDate(locale, projectsQuery.data.updatedAt)}</span>
          </p>
        )}
      </div>
      <div
        className={
          projectViewMode === "grid"
            ? "grid gap-8 md:grid-cols-2"
            : "grid gap-6"
        }
      >
        {projectsQuery.isLoading ? (
          <SkeletonLoader
            count={4}
            className={projectViewMode === "grid" ? "md:grid-cols-2" : undefined}
            itemClassName="h-72 rounded-[3.5rem]"
          />
        ) : null}
        {projectsQuery.isError ? (
          <Card className="rounded-[3.5rem] border-[var(--line-strong)] bg-[var(--surface-strong)] md:col-span-2 overflow-hidden">
            <CardContent className="p-12 text-center flex flex-col items-center">
              <div className="h-16 w-16 rounded-3xl bg-rose-500/10 flex items-center justify-center text-rose-500 mb-6 font-bold text-2xl">!</div>
              <h3 className="text-2xl font-[1000] text-[var(--text-primary)] tracking-tighter">
                {labels.errorStateTitle}
              </h3>
              <p className="mt-4 text-sm font-medium text-[var(--text-secondary)] max-w-md">
                {labels.errorStateDescription}
              </p>
              {errorDetail ? (
                <p className="mt-4 text-xs font-black bg-rose-500/5 px-4 py-2 rounded-xl text-rose-400 italic">
                  {errorDetail}
                </p>
              ) : null}
              <div className="mt-8">
                <Button
                  onClick={() => {
                    void projectsQuery.refetch();
                  }}
                  variant="secondary"
                  className="rounded-full border-[var(--line-strong)] hover:bg-[var(--accent-strong)] hover:text-white"
                >
                  {labels.retryLabel}
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : null}
        {projectsQuery.data && !hasProjects ? (
          <Card className="rounded-[3.5rem] border-[var(--line-strong)] bg-[var(--surface-strong)] md:col-span-2 overflow-hidden">
            <CardContent className="p-12 text-center flex flex-col items-center">
              <div className="h-20 w-20 rounded-[2.5rem] bg-[var(--surface-soft)] flex items-center justify-center text-[var(--text-hint)] mb-8 shadow-[var(--shadow-lg)] border border-[var(--line)]">
                 🏗️
              </div>
              <h3 className="text-2xl font-[1000] text-[var(--text-primary)] tracking-tighter">
                {labels.emptyStateTitle}
              </h3>
              <p className="mt-4 text-sm font-medium text-[var(--text-secondary)] italic">
                {labels.emptyStateDescription}
              </p>
            </CardContent>
          </Card>
        ) : null}
        {hasProjects ? projectsQuery.data?.projects.map((project) => {
          const isSelected = currentProjectId === project.id;

          return (
            <Card
              key={project.id}
              className={`group flex rounded-[3.5rem] border-[var(--line-strong)] bg-[var(--surface-strong)] transition-all duration-500 hover:shadow-[var(--shadow-2xl)] hover:border-[var(--accent-strong)]/30 overflow-hidden ${isSelected ? 'ring-2 ring-[var(--accent-strong)]/50' : ''}`}
            >
              <CardContent className="p-10 flex flex-col w-full">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="space-y-1">
                  <p className="text-[10px] font-black uppercase tracking-[0.4em] text-[var(--text-hint)]">
                    {project.location}
                  </p>
                  <h3 className="text-3xl font-[1000] text-[var(--text-primary)] tracking-tighter group-hover:text-[var(--accent-strong)] transition-colors">
                    {project.name}
                  </h3>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <span className="rounded-2xl border border-[var(--accent-strong)]/20 bg-[var(--accent-soft)] px-4 py-1.5 text-[10px] font-black uppercase tracking-widest text-[var(--accent-strong)]">
                    {project.phase}
                  </span>
                  {isSelected && (
                    <span className="rounded-2xl border border-[var(--spot)]/20 bg-[var(--spot)]/10 px-4 py-1.5 text-[10px] font-black uppercase tracking-widest text-[var(--spot)] italic">
                      {labels.selectedLabel}
                    </span>
                  )}
                </div>
              </div>
              
              <div className="mt-8 flex-1 grid gap-4">
                <div className="flex items-center justify-between py-3 border-b border-[var(--line)]">
                  <span className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">{labels.lastUpdatedLabel}</span>
                  <span className="text-xs font-bold text-[var(--text-secondary)] tracking-tight italic">{formatDate(locale, project.updatedAt)}</span>
                </div>
                <div className="flex flex-col gap-2">
                  <span className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">{labels.nextActionLabel}</span>
                  <p className="text-sm font-bold text-[var(--text-primary)] leading-tight italic decoration-[var(--line)] underline underline-offset-4 decoration-2">
                    {project.nextAction}
                  </p>
                </div>
              </div>

              <div className="mt-8">
                <p className="text-[10px] font-black uppercase tracking-[0.4em] text-[var(--text-hint)] mb-4">
                  {labels.modulesLabel}
                </p>
                <div className="flex flex-wrap gap-2">
                  {project.modules.map((moduleKey) => (
                    <span
                      key={moduleKey}
                      className="rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-1.5 text-[10px] font-black uppercase tracking-widest text-[var(--text-secondary)] group-hover:bg-[var(--surface)] transition-colors"
                    >
                      {moduleLabels[moduleKey]}
                    </span>
                  ))}
                </div>
              </div>

              <div className="mt-10 flex items-center gap-4">
                <Button
                  onClick={() => setCurrentProject(project.id)}
                  variant="secondary"
                  className="flex-1 h-14 rounded-3xl border-[var(--line-strong)] font-black text-xs uppercase tracking-widest hover:bg-[var(--surface-soft)] whitespace-nowrap"
                >
                  {labels.selectProjectLabel}
                </Button>
                <Link
                  href={`/${locale}/projects/${project.id}`}
                  className="flex-[1.2] flex h-14 items-center justify-center gap-3 rounded-3xl bg-[var(--accent-strong)] px-8 text-xs font-black uppercase tracking-[0.2em] text-white shadow-[var(--shadow-glow)] transition-all hover:scale-[1.02] active:scale-95"
                >
                  {labels.openProjectLabel}
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                </Link>
              </div>
              </CardContent>
            </Card>
          );
        }) : null}
      </div>
    </section>
  );
}
