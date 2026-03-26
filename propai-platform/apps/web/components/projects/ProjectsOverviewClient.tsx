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
    <section className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setProjectViewMode("grid")}
            className={`rounded-full px-4 py-2 text-sm font-medium ${
              projectViewMode === "grid"
                ? "bg-[var(--foreground)] text-white"
                : "border border-[var(--line)] bg-white/75 text-[rgba(19,33,47,0.72)]"
            }`}
          >
            {labels.viewGridLabel}
          </button>
          <button
            type="button"
            onClick={() => setProjectViewMode("list")}
            className={`rounded-full px-4 py-2 text-sm font-medium ${
              projectViewMode === "list"
                ? "bg-[var(--foreground)] text-white"
                : "border border-[var(--line)] bg-white/75 text-[rgba(19,33,47,0.72)]"
            }`}
          >
            {labels.viewListLabel}
          </button>
        </div>
        {projectsQuery.data && (
          <p className="text-sm text-[rgba(19,33,47,0.62)]">
            {labels.lastUpdatedLabel}:{" "}
            {formatDate(locale, projectsQuery.data.updatedAt)}
          </p>
        )}
      </div>
      <div
        className={
          projectViewMode === "grid"
            ? "grid gap-4 md:grid-cols-2"
            : "grid gap-4"
        }
      >
        {projectsQuery.isLoading ? (
          <SkeletonLoader
            count={3}
            className={projectViewMode === "grid" ? "md:grid-cols-2" : undefined}
            itemClassName="h-64"
          />
        ) : null}
        {projectsQuery.isError ? (
          <Card className="h-full bg-[var(--surface-strong)] md:col-span-2">
            <CardContent className="p-6">
              <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.48)]">
                {labels.modulesLabel}
              </p>
              <h3 className="mt-3 text-xl font-semibold text-[var(--foreground)]">
                {labels.errorStateTitle}
              </h3>
              <p className="mt-3 text-sm leading-7 text-[rgba(19,33,47,0.72)]">
                {labels.errorStateDescription}
              </p>
              {errorDetail ? (
                <p className="mt-3 text-sm leading-7 text-[var(--spot)]">
                  {errorDetail}
                </p>
              ) : null}
              <div className="mt-5">
                <Button
                  onClick={() => {
                    void projectsQuery.refetch();
                  }}
                  variant="secondary"
                >
                  {labels.retryLabel}
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : null}
        {projectsQuery.data && !hasProjects ? (
          <Card className="h-full bg-[var(--surface-strong)] md:col-span-2">
            <CardContent className="p-6">
              <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.48)]">
                {labels.modulesLabel}
              </p>
              <h3 className="mt-3 text-xl font-semibold text-[var(--foreground)]">
                {labels.emptyStateTitle}
              </h3>
              <p className="mt-3 text-sm leading-7 text-[rgba(19,33,47,0.72)]">
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
              className="h-full"
            >
              <CardContent className="p-6">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-sm text-[rgba(19,33,47,0.6)]">
                    {project.location}
                  </p>
                  <h3 className="mt-2 text-xl font-semibold text-[var(--foreground)]">
                    {project.name}
                  </h3>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-[rgba(14,116,144,0.1)] px-3 py-1 text-xs font-medium text-[var(--accent-strong)]">
                    {project.phase}
                  </span>
                  {isSelected && (
                    <span className="rounded-full bg-[rgba(217,119,6,0.12)] px-3 py-1 text-xs font-medium text-[var(--spot)]">
                      {labels.selectedLabel}
                    </span>
                  )}
                </div>
              </div>
              <div className="mt-5 grid gap-3 text-sm leading-6 text-[rgba(19,33,47,0.7)]">
                <p>
                  {labels.lastUpdatedLabel}: {formatDate(locale, project.updatedAt)}
                </p>
                <p>
                  {labels.nextActionLabel}: {project.nextAction}
                </p>
              </div>
              <div className="mt-5">
                <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.48)]">
                  {labels.modulesLabel}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {project.modules.map((moduleKey) => (
                    <span
                      key={moduleKey}
                      className="rounded-full border border-[var(--line)] px-3 py-1 text-xs font-medium text-[rgba(19,33,47,0.72)]"
                    >
                      {moduleLabels[moduleKey]}
                    </span>
                  ))}
                </div>
              </div>
              <div className="mt-6 flex flex-wrap gap-3">
                <Button
                  onClick={() => setCurrentProject(project.id)}
                  variant="secondary"
                >
                  {labels.selectProjectLabel}
                </Button>
                <Link
                  href={`/${locale}/projects/${project.id}`}
                  className="rounded-full bg-[var(--foreground)] px-4 py-2 text-sm font-semibold text-white"
                >
                  {labels.openProjectLabel}
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
