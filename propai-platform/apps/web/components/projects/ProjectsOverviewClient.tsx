"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Construction } from "lucide-react";
import { Button, Card, CardContent } from "@propai/ui";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import type {
  ProjectCard,
  ProjectModuleKey,
} from "@/mocks/types";
import { useAppStore } from "@/store/use-app-store";
import { useProjectStore } from "@/store/use-project-store";
import { useProjectStore as useProjectListStore } from "@/store/useProjectStore";
import { ConfirmDeleteModal } from "@/components/common/ConfirmDeleteModal";

const _PHASE_LABEL: Record<string, string> = {
  draft: "초안", planning: "기획", design: "설계", permit: "인허가",
  construction: "시공", completed: "완료", archived: "보관",
};

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

export function ProjectsOverviewClient({
  locale,
  labels,
  moduleLabels,
}: ProjectsOverviewClientProps) {
  const projectViewMode = useAppStore((state) => state.projectViewMode);
  const setProjectViewMode = useAppStore((state) => state.setProjectViewMode);
  const currentProjectId = useProjectStore((state) => state.currentProjectId);
  const setCurrentProject = useProjectStore((state) => state.setCurrentProject);

  // 단일출처: 백엔드 동기화 스토어(드롭다운과 공유) — 마이그레이션 포함
  const listProjects = useProjectListStore((s) => s.projects);
  const syncing = useProjectListStore((s) => s.syncing);
  const syncFromBackend = useProjectListStore((s) => s.syncFromBackend);
  const deleteProject = useProjectListStore((s) => s.deleteProject);

  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);

  useEffect(() => {
    void syncFromBackend();
  }, [syncFromBackend]);

  const cards: ProjectCard[] = listProjects.map((p) => ({
    id: p.id,
    name: p.name || p.address || "(이름 없음)",
    // 다필지 통합 프로젝트: "대표지번 외 N필지" 표기(단일/미설정이면 대표지번만)
    location: p.address
      ? (p.parcelCount && p.parcelCount > 1 ? `${p.address} 외 ${p.parcelCount - 1}필지` : p.address)
      : "-",
    phase: _PHASE_LABEL[p.status] || p.status,
    updatedAt: p.createdAt,
    nextAction: "부지분석 이어가기",
    modules: ["design", "finance", "report"],
  }));
  /**
   * ★"마지막 업데이트"는 **데이터의 시각**이지 렌더 시각이 아니다.
   *
   * 종전엔 `new Date().toISOString()` 이었다 — 즉 라벨은 *"마지막 업데이트"* 라고 말하면서
   * **화면을 그린 순간**을 보여 줬다. 값이 라벨의 약속과 다르다(거짓 근거).
   *
   * 그리고 그것은 **하이드레이션 불일치**를 만든다: 서버가 그린 시각과 클라이언트가
   * 하이드레이트한 시각이 다르므로 같은 자리의 텍스트가 갈린다(React #418).
   * ★로컬 프로덕션 빌드에서 변이로 확정했다 — 이 한 줄만 상수로 고정하니
   *   `/ko/projects` 의 #418 이 1→0 이 되고, 같은 배치의 다른 라우트(양성 대조군)는 1을 유지했다.
   * ★이 결함은 저장 상태와 무관하다 — localStorage 가 비어 있어도 재현된다.
   *
   * 이제 목록에서 **가장 최근 시각**을 파생한다. 없으면 `null` — 없는 것을 지어내지 않는다.
   */
  const latestUpdatedAt = cards.reduce<string | null>(
    (acc, c) => (c.updatedAt && (acc === null || c.updatedAt > acc) ? c.updatedAt : acc),
    null,
  );
  const projectsData = { projects: cards, total: cards.length, updatedAt: latestUpdatedAt };
  const hasProjects = cards.length > 0;
  const isLoading = syncing && !hasProjects;
  const isError = false;
  const errorDetail: string | null = null;

  return (
    <section className="grid grid-cols-1 gap-6 min-w-0">
      <div className="flex flex-wrap items-center justify-between gap-4 px-2">
        <div className="flex flex-wrap items-center gap-4">
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
          {/* 목록 메타: 총 N건 + 실시간 동기화 상태 */}
          <div className="flex items-center gap-3">
            <span className="cc-chip-data">
              <span className="cc-num">{projectsData.total}</span> UNITS
            </span>
            <span className="cc-live"><i />{syncing ? "SYNCING" : "LIVE"}</span>
          </div>
        </div>
        {projectsData.updatedAt && (
          <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">
            {labels.lastUpdatedLabel}:{" "}
            <span className="cc-num text-[var(--text-secondary)]">{formatDate(locale, projectsData.updatedAt)}</span>
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
        {isLoading ? (
          <SkeletonLoader
            count={4}
            className={projectViewMode === "grid" ? "md:grid-cols-2" : undefined}
            itemClassName="h-72 rounded-[var(--radius-md)]"
          />
        ) : null}
        {isError ? (
          <Card className="rounded-[var(--radius-2xl)] border-[var(--line-strong)] bg-[var(--surface-strong)] md:col-span-2 overflow-hidden">
            <CardContent className="p-12 text-center flex flex-col items-center">
              <div className="h-16 w-16 rounded-3xl bg-[var(--status-error)]/10 flex items-center justify-center text-[var(--status-error)] mb-6 font-bold text-2xl">!</div>
              <h3 className="text-2xl font-[1000] text-[var(--text-primary)] tracking-tighter">
                {labels.errorStateTitle}
              </h3>
              <p className="mt-4 text-sm font-medium text-[var(--text-secondary)] max-w-md">
                {labels.errorStateDescription}
              </p>
              {errorDetail ? (
                <p className="mt-4 text-xs font-black bg-[var(--status-error)]/5 px-4 py-2 rounded-xl text-[var(--status-error)] italic">
                  {errorDetail}
                </p>
              ) : null}
              <div className="mt-8">
                <Button
                  onClick={() => {
                    void syncFromBackend();
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
        {!isLoading && !hasProjects ? (
          <div className="cc-bracketed cc-panel md:col-span-2">
            <div className="cc-grid-bg cc-grid-bg--radial" />
            <i className="cc-bracket cc-bracket--tl" />
            <i className="cc-bracket cc-bracket--tr" />
            <i className="cc-bracket cc-bracket--bl" />
            <i className="cc-bracket cc-bracket--br" />
            <div className="relative z-10 p-12 text-center flex flex-col items-center">
              <span className="cc-label mb-6">NO ACTIVE PROJECTS</span>
              <div className="h-20 w-20 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] flex items-center justify-center text-[var(--text-hint)] mb-8 shadow-[var(--shadow-lg)] border border-[var(--line)]">
                <Construction className="size-9" aria-hidden />
              </div>
              <h3 className="text-2xl font-[1000] text-[var(--text-primary)] tracking-tighter">
                {labels.emptyStateTitle}
              </h3>
              <p className="mt-4 text-sm font-medium text-[var(--text-secondary)]">
                {labels.emptyStateDescription}
              </p>
            </div>
          </div>
        ) : null}
        {hasProjects ? (projectsData.projects ?? []).map((project) => {
          const isSelected = currentProjectId === project.id;

          return (
            <div
              key={project.id}
              className={`cc-bracketed cc-interactive cc-panel group flex ${isSelected ? 'ring-2 ring-[var(--accent-strong)]/50 border-[var(--data-accent-line)]' : ''}`}
            >
              <div className="cc-grid-bg opacity-50" />
              <i className="cc-bracket cc-bracket--tl" />
              <i className="cc-bracket cc-bracket--tr" />
              <i className="cc-bracket cc-bracket--bl" />
              <i className="cc-bracket cc-bracket--br" />
              <div className="relative z-10 p-10 flex flex-col w-full">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="space-y-1.5">
                  <p className="cc-label tracking-[0.28em]">
                    {project.location}
                  </p>
                  <h3 className="text-3xl font-[1000] text-[var(--text-primary)] tracking-tighter group-hover:text-[var(--accent-strong)] transition-colors">
                    {project.name}
                  </h3>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <span className="cc-chip-data">
                    {project.phase}
                  </span>
                  {isSelected && (
                    <span className="rounded-2xl border border-[var(--accent-strong)]/20 bg-[var(--accent-strong)]/10 px-4 py-1.5 text-[10px] font-black uppercase tracking-widest text-[var(--accent-strong)] italic">
                      {labels.selectedLabel}
                    </span>
                  )}
                </div>
              </div>

              <div className="mt-8 flex-1 grid gap-4">
                <div className="flex items-center justify-between py-3 border-b border-[var(--line)]">
                  <span className="cc-label">{labels.lastUpdatedLabel}</span>
                  <span className="cc-num text-xs text-[var(--text-secondary)]">{formatDate(locale, project.updatedAt)}</span>
                </div>
                <div className="flex flex-col gap-2">
                  <span className="cc-label">{labels.nextActionLabel}</span>
                  <p className="text-sm font-bold text-[var(--text-primary)] leading-tight">
                    {project.nextAction}
                  </p>
                </div>
              </div>

              <div className="mt-8">
                <p className="cc-label tracking-[0.28em] mb-4">
                  {labels.modulesLabel}
                </p>
                <div className="flex flex-wrap gap-2">
                  {(project.modules ?? []).map((moduleKey) => (
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
                  href={`/${locale}/projects/${project.id}/site-analysis`}
                  className="flex-[1.2] flex h-14 items-center justify-center gap-2 whitespace-nowrap rounded-3xl bg-[var(--accent-strong)] px-5 text-xs font-black uppercase tracking-wider text-white shadow-[var(--shadow-glow)] transition-all hover:scale-[1.02] active:scale-95"
                >
                  {labels.openProjectLabel}
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="shrink-0"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                </Link>
                <button
                  type="button"
                  title="프로젝트 삭제(이름 입력 확인 필요)"
                  onClick={() => setDeleteTarget({ id: project.id, name: project.name })}
                  className="h-14 w-14 shrink-0 rounded-3xl border border-[var(--status-error)]/30 text-[var(--status-error)] transition-colors hover:bg-[var(--status-error)]/10"
                >
                  ✕
                </button>
              </div>
              </div>
            </div>
          );
        }) : null}
      </div>

      <ConfirmDeleteModal
        open={deleteTarget !== null}
        name={deleteTarget?.name ?? ""}
        title="프로젝트 삭제"
        // ★문구를 사실과 맞춘다 — 백엔드는 `is_deleted` 플래그만 세우는 **소프트 삭제**라
        //   "백엔드에서도 제거되며"는 거짓이었다. 화면에서 되돌릴 수 없는 것은 사실이므로
        //   그 부분은 유지하고, 서버 기록이 남는다는 사실을 숨기지 않는다.
        description="삭제하면 목록에서 사라지고 이 브라우저의 분석 데이터(스냅샷·토지조서)도 함께 정리됩니다. 화면에서는 되돌릴 수 없습니다(서버 기록은 보관됩니다). 아래 프로젝트명을 그대로 입력해야 삭제됩니다."
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) {
            void deleteProject(deleteTarget.id);
            if (currentProjectId === deleteTarget.id) setCurrentProject("");
          }
          setDeleteTarget(null);
        }}
      />
    </section>
  );
}
