"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { ApiClientError, apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";

/* ------------------------------------------------------------------ */
/*  Types                                                             */
/* ------------------------------------------------------------------ */

type ProjectResponse = {
  id: string;
  name: string;
  status: string;
  address: string | null;
  total_area_sqm: number | null;
  created_at: string;
  updated_at: string;
};

/* ------------------------------------------------------------------ */
/*  Labels                                                            */
/* ------------------------------------------------------------------ */

type Labels = {
  heroTitle: string;
  heroDescription: string;
  heroHint: string;
  tokenHint: string;
  authError: string;
  tenantsTitle: string;
  projectNameLabel: string;
  addressLabel: string;
  statusLabel: string;
  areaLabel: string;
  updatedLabel: string;
  leaseStatusLabel: string;
  paymentOverviewTitle: string;
  totalProjectsLabel: string;
  activeLabel: string;
  vacantLabel: string;
  placeholder: string;
  loadErrorTitle: string;
  loadErrorDetail: string;
  retryAction: string;
};

const KO_LABELS: Labels = {
  heroTitle: "임차인 관리 라이브 워크스페이스",
  heroDescription:
    "프로젝트 기반 임차인 목록을 조회하고 임대 현황 및 결제 개요를 확인합니다.",
  heroHint:
    "GET /projects API를 호출하여 프로젝트(임차인) 데이터를 실시간으로 불러옵니다.",
  tokenHint:
    "라이브 API 호출에는 NEXT_PUBLIC_API_ACCESS_TOKEN 또는 localStorage.propai_access_token이 필요합니다.",
  authError: "라이브 워크스페이스 호출을 위해 API 인증이 필요합니다.",
  tenantsTitle: "임차인 목록",
  projectNameLabel: "프로젝트명",
  addressLabel: "주소",
  statusLabel: "상태",
  areaLabel: "면적 (sqm)",
  updatedLabel: "최종 수정일",
  leaseStatusLabel: "임대 상태",
  paymentOverviewTitle: "결제 현황 개요",
  totalProjectsLabel: "전체 프로젝트",
  activeLabel: "운영 중",
  vacantLabel: "공실",
  placeholder: "프로젝트(임차인) 데이터가 로드되면 여기에 표시됩니다.",
  loadErrorTitle: "데이터 로드 실패",
  loadErrorDetail:
    "API로부터 프로젝트 목록을 불러오지 못했습니다. 다시 시도해 주세요.",
  retryAction: "재시도",
};

const EN_LABELS: Labels = {
  heroTitle: "Tenant Management Live Workspace",
  heroDescription:
    "View project-based tenant lists, lease status, and payment overview.",
  heroHint:
    "Calls GET /projects API to fetch project (tenant) data in real-time.",
  tokenHint:
    "Live API calls require NEXT_PUBLIC_API_ACCESS_TOKEN or localStorage.propai_access_token.",
  authError: "API authentication is required for live workspace calls.",
  tenantsTitle: "Tenant list",
  projectNameLabel: "Project name",
  addressLabel: "Address",
  statusLabel: "Status",
  areaLabel: "Area (sqm)",
  updatedLabel: "Last updated",
  leaseStatusLabel: "Lease status",
  paymentOverviewTitle: "Payment overview",
  totalProjectsLabel: "Total projects",
  activeLabel: "Active",
  vacantLabel: "Vacant",
  placeholder: "Tenant data will appear here once loaded.",
  loadErrorTitle: "Data load failed",
  loadErrorDetail: "Failed to load project list from the API. Please retry.",
  retryAction: "Retry",
};

const LABELS: Record<Locale, Labels> = {
  ko: KO_LABELS,
  en: EN_LABELS,
  "zh-CN": KO_LABELS,
};

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

function formatDate(locale: string, value: string) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function extractErrorMessage(error: unknown, authMessage: string) {
  if (error instanceof ApiClientError) {
    if (error.status === 401 || error.status === 403) return authMessage;
    return `API 요청이 상태 ${error.status}(으)로 실패했습니다.`;
  }
  if (error instanceof Error) return error.message;
  return "요청에 실패했습니다.";
}

function statusBadge(status: string) {
  const s = status.toLowerCase();
  if (s === "active" || s === "운영중" || s === "completed")
    return "bg-emerald-500/15 text-emerald-500";
  if (s === "planning" || s === "pending")
    return "bg-amber-500/15 text-amber-500";
  return "bg-[var(--surface-soft)] text-[var(--text-secondary)]";
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[var(--radius-xl)] bg-[var(--surface)] p-4">
      <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-2 text-2xl font-bold text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Component                                                         */
/* ------------------------------------------------------------------ */

export function TenantWorkspaceClient({
  locale,
}: {
  locale: Locale;
}) {
  const labels = LABELS[locale] || LABELS["ko"];
  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  const projectsQuery = useQuery({
    queryKey: ["projects", "tenant-workspace"],
    enabled: canUseLiveApi,
    queryFn: () =>
      apiClient.get<ProjectResponse[]>("/projects", { useMock: false }),
  });

  const projects = projectsQuery.data ?? [];
  const activeCount = projects.filter(
    (p) => p.status.toLowerCase() === "active" || p.status === "운영중",
  ).length;
  const vacantCount = projects.length - activeCount;

  const queryError = projectsQuery.error
    ? extractErrorMessage(projectsQuery.error, labels.authError)
    : "";

  return (
    <section className="grid gap-6">
      {/* Hero */}
      <Card className="rounded-[var(--radius-2xl)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
        <CardContent className="p-8">
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-[rgba(14,116,144,0.1)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--accent-strong)]">
              {labels.heroTitle}
            </span>
            <span className="rounded-full border border-[var(--line)] px-4 py-2 text-xs font-medium text-[var(--text-secondary)]">
              {runtimeConfig.mode === "live" ? "LIVE" : "HYBRID"}
            </span>
          </div>
          <h3 className="mt-5 text-3xl font-bold text-[var(--text-primary)]">
            {labels.heroDescription}
          </h3>
          <p className="mt-4 max-w-3xl text-sm leading-8 text-[var(--text-secondary)]">
            {labels.heroHint}
          </p>
          <p className="mt-3 max-w-3xl text-sm leading-8 text-[var(--text-tertiary)]">
            {labels.tokenHint}
          </p>
          {!canUseLiveApi && (
            <div className="mt-6 rounded-[var(--radius-xl)] border border-dashed border-[var(--line)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
              {labels.authError}
            </div>
          )}
          {queryError && (
            <div className="mt-6">
              <WorkspaceQueryErrorCard
                title={labels.loadErrorTitle}
                description={labels.loadErrorDetail}
                message={queryError}
                actionLabel={labels.retryAction}
                onRetry={() => {
                  void projectsQuery.refetch();
                }}
              />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Payment overview */}
      <Card>
        <CardContent className="p-6">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
            {labels.paymentOverviewTitle}
          </p>
          {projectsQuery.isLoading ? (
            <SkeletonLoader count={1} itemClassName="h-20" />
          ) : (
            <div className="mt-4 grid gap-4 md:grid-cols-3">
              <MetricTile
                label={labels.totalProjectsLabel}
                value={String(projects.length)}
              />
              <MetricTile
                label={labels.activeLabel}
                value={String(activeCount)}
              />
              <MetricTile
                label={labels.vacantLabel}
                value={String(vacantCount)}
              />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Tenant list */}
      <Card>
        <CardContent className="p-6">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
            {labels.tenantsTitle}
          </p>
          {projectsQuery.isLoading ? (
            <SkeletonLoader count={3} itemClassName="h-16" />
          ) : projects.length > 0 ? (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)]">
                    <th className="pb-3 pr-4">{labels.projectNameLabel}</th>
                    <th className="pb-3 pr-4">{labels.addressLabel}</th>
                    <th className="pb-3 pr-4">{labels.statusLabel}</th>
                    <th className="pb-3 pr-4">{labels.areaLabel}</th>
                    <th className="pb-3">{labels.updatedLabel}</th>
                  </tr>
                </thead>
                <tbody>
                  {projects.map((project) => (
                    <tr
                      key={project.id}
                      className="border-t border-[var(--line)]"
                    >
                      <td className="py-3 pr-4 font-semibold text-[var(--text-primary)]">
                        {project.name}
                      </td>
                      <td className="py-3 pr-4 text-[var(--text-secondary)]">
                        {project.address ?? "-"}
                      </td>
                      <td className="py-3 pr-4">
                        <span
                          className={`rounded-full px-3 py-1 text-xs font-bold ${statusBadge(project.status)}`}
                        >
                          {project.status}
                        </span>
                      </td>
                      <td className="py-3 pr-4 text-[var(--text-secondary)]">
                        {project.total_area_sqm != null
                          ? project.total_area_sqm.toLocaleString()
                          : "-"}
                      </td>
                      <td className="py-3 text-[var(--text-secondary)]">
                        {formatDate(locale, project.updated_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
              {labels.placeholder}
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
