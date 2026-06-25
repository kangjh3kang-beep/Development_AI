"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, Input } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { ApiClientError, apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
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

type ComplianceCheckResponse = {
  project_id?: string;
  address?: string;
  results?: ComplianceItem[];
  overall_status?: string;
  summary?: string;
  checked_at?: string;
};

type ComplianceItem = {
  category?: string;
  rule?: string;
  status?: string;
  detail?: string;
  [key: string]: unknown;
};

type ApprovalItem = {
  projectId: string;
  projectName: string;
  stage: "pending" | "in-review" | "approved" | "rejected";
  complianceStatus?: string;
  summary?: string;
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
  formTitle: string;
  addressLabel: string;
  zoningLabel: string;
  submitAction: string;
  missingAddressError: string;
  workflowTitle: string;
  pendingLabel: string;
  inReviewLabel: string;
  approvedLabel: string;
  rejectedLabel: string;
  projectsTitle: string;
  projectNameLabel: string;
  statusLabel: string;
  complianceLabel: string;
  stageLabel: string;
  placeholder: string;
  loadErrorTitle: string;
  loadErrorDetail: string;
  retryAction: string;
};

const KO_LABELS: Labels = {
  heroTitle: "결재 관리 라이브 작업 공간",
  heroDescription:
    "프로젝트 목록과 건축법규 준수 점검을 결합하여 결재 워크플로 현황을 추적합니다.",
  heroHint:
    "",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "라이브 작업 공간 호출을 위해 API 인증이 필요합니다.",
  formTitle: "결재 점검 입력",
  addressLabel: "대지 주소",
  zoningLabel: "용도지역",
  submitAction: "결재 점검 실행",
  missingAddressError: "주소를 입력해 주세요.",
  workflowTitle: "결재 워크플로 현황",
  pendingLabel: "대기",
  inReviewLabel: "심사 중",
  approvedLabel: "승인 완료",
  rejectedLabel: "반려",
  projectsTitle: "프로젝트별 결재 현황",
  projectNameLabel: "프로젝트명",
  statusLabel: "프로젝트 상태",
  complianceLabel: "준수 판정",
  stageLabel: "결재 단계",
  placeholder: "프로젝트 데이터가 로드되면 결재 현황이 표시됩니다.",
  loadErrorTitle: "데이터 로드 실패",
  loadErrorDetail:
    "API로부터 프로젝트 목록을 불러오지 못했습니다. 다시 시도해 주세요.",
  retryAction: "재시도",
};

const EN_LABELS: Labels = {
  heroTitle: "Approvals Live Workspace",
  heroDescription:
    "Track approval workflow by combining project list with building-compliance checks.",
  heroHint:
    "Calls GET /projects and POST /building-compliance/check for combined tracking.",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "API authentication is required for live workspace calls.",
  formTitle: "Approval check input",
  addressLabel: "Site address",
  zoningLabel: "Zoning district",
  submitAction: "Run approval check",
  missingAddressError: "Address is required.",
  workflowTitle: "Approval workflow status",
  pendingLabel: "Pending",
  inReviewLabel: "In Review",
  approvedLabel: "Approved",
  rejectedLabel: "Rejected",
  projectsTitle: "Per-project approval status",
  projectNameLabel: "Project name",
  statusLabel: "Project status",
  complianceLabel: "Compliance",
  stageLabel: "Stage",
  placeholder: "Approval status will appear once project data loads.",
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

function extractErrorMessage(error: unknown, authMessage: string) {
  if (error instanceof ApiClientError) {
    if (error.status === 401 || error.status === 403) return authMessage;
    return `API 요청이 상태 ${error.status}(으)로 실패했습니다.`;
  }
  if (error instanceof Error) return error.message;
  return "요청에 실패했습니다.";
}

function stageBadge(stage: string) {
  switch (stage) {
    case "approved":
      return "bg-emerald-500/15 text-emerald-500";
    case "in-review":
      return "bg-blue-500/15 text-blue-500";
    case "rejected":
      return "bg-red-500/15 text-red-500";
    default:
      return "bg-amber-500/15 text-amber-500";
  }
}

function stageLabel(stage: string, labels: Labels) {
  switch (stage) {
    case "approved":
      return labels.approvedLabel;
    case "in-review":
      return labels.inReviewLabel;
    case "rejected":
      return labels.rejectedLabel;
    default:
      return labels.pendingLabel;
  }
}

function deriveStage(status: string): ApprovalItem["stage"] {
  const s = status.toLowerCase();
  if (s === "active" || s === "completed" || s === "운영중") return "approved";
  if (s === "planning" || s === "pending") return "in-review";
  return "pending";
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

export function ApprovalsWorkspaceClient({
  locale,
}: {
  locale: Locale;
}) {
  const labels = LABELS[locale] || LABELS["ko"];
  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  // ★SSOT 읽기소비: 활성 프로젝트의 부지분석(siteAnalysis) 컨텍스트를 구독만 한다(write 금지).
  // siteAnalysis.address가 있으면 주소바를 자동 채우고 입력창은 숨긴다(불필요 입력 제거).
  const projectId = useProjectContextStore((s) => s.projectId);
  const _rawSite = useProjectContextStore((s) => s.siteAnalysis);
  // 활성 프로젝트일 때만 컨텍스트 부지정보 사용 — 약식 검색이 결재 폼으로 새지 않도록.
  const siteAnalysis = projectId ? _rawSite : null;

  const [workspaceError, setWorkspaceError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [complianceResult, setComplianceResult] =
    useState<ComplianceCheckResponse | null>(null);

  const [form, setForm] = useState({
    address: "",
    zoning: "제2종일반주거지역",
  });

  // 부지분석 주소(SSOT)를 결재 점검 폼 주소에 자동 채움. 사용자가 이미 입력한 값은 보존.
  useEffect(() => {
    setForm((current) => ({
      ...current,
      address: current.address || siteAnalysis?.address || "",
    }));
  }, [siteAnalysis]);

  const projectsQuery = useQuery({
    queryKey: ["projects", "approvals-workspace"],
    enabled: canUseLiveApi,
    queryFn: () =>
      apiClient.get<ProjectResponse[]>("/projects", { useMock: false }),
  });

  // GET /projects 는 PaginatedResponse({ items, ... }) 반환 — 배열/페이지네이션 양쪽 안전 흡수
  // (과거 data 를 배열로 단정해 .map 호출 시 페이지가 죽던 문제 방지).
  const rawProjects = projectsQuery.data as unknown;
  const projects = Array.isArray(rawProjects)
    ? (rawProjects as ProjectResponse[])
    : Array.isArray((rawProjects as { items?: ProjectResponse[] } | null)?.items)
      ? (rawProjects as { items: ProjectResponse[] }).items
      : [];
  const approvalItems: ApprovalItem[] = projects.map((p) => ({
    projectId: p.id,
    projectName: p.name,
    stage: deriveStage(p.status),
    complianceStatus: complianceResult?.overall_status,
    summary: complianceResult?.summary,
  }));

  const pendingCount = approvalItems.filter(
    (a) => a.stage === "pending",
  ).length;
  const inReviewCount = approvalItems.filter(
    (a) => a.stage === "in-review",
  ).length;
  const approvedCount = approvalItems.filter(
    (a) => a.stage === "approved",
  ).length;

  const queryError = projectsQuery.error
    ? extractErrorMessage(projectsQuery.error, labels.authError)
    : "";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");

    const address = form.address.trim();
    if (!address) {
      setWorkspaceError(labels.missingAddressError);
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await apiClient.post<ComplianceCheckResponse>(
        "/building-compliance/check",
        {
          useMock: false,
          body: {
            address,
            zoning_district: form.zoning,
          },
        },
      );
      setComplianceResult(res);
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="grid grid-cols-1 gap-6 min-w-0">
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
          {!canUseLiveApi && (
            <p className="mt-3 max-w-3xl text-sm leading-8 text-[var(--text-tertiary)]">
            {labels.tokenHint}
          </p>
            )}
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
          {workspaceError && (
            <div className="mt-6 rounded-[var(--radius-xl)] border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] p-5 text-sm leading-7 text-[var(--spot)]">
              {workspaceError}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Workflow summary */}
      <Card>
        <CardContent className="p-6">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
            {labels.workflowTitle}
          </p>
          {projectsQuery.isLoading ? (
            <SkeletonLoader count={1} itemClassName="h-20" />
          ) : (
            <div className="mt-4 grid gap-4 md:grid-cols-4">
              <MetricTile
                label={labels.pendingLabel}
                value={String(pendingCount)}
              />
              <MetricTile
                label={labels.inReviewLabel}
                value={String(inReviewCount)}
              />
              <MetricTile
                label={labels.approvedLabel}
                value={String(approvedCount)}
              />
              <MetricTile
                label={labels.rejectedLabel}
                value="0"
              />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Compliance check form */}
      <Card>
        <CardContent className="p-6">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
            {labels.formTitle}
          </p>
          <form className="mt-4 grid gap-3" onSubmit={handleSubmit}>
            {/* 주소 입력창: 부지분석에서 주소가 확정된 프로젝트 진입 시엔 숨김(불필요 입력 제거).
                신규(주소 미보유) 상태에서만 노출해 직접 입력 가능. SSOT 주소(siteAnalysis.address)는
                위 useEffect로 form.address에 이미 자동 채워져 제출에 그대로 사용된다. */}
            {!siteAnalysis?.address && (
              <ProjectAddressInput
                value={form.address}
                onChange={(address) => setForm((c) => ({ ...c, address }))}
                label={labels.addressLabel}
                placeholder={labels.addressLabel}
              />
            )}
            <div className="grid gap-3 md:grid-cols-2">
              <Input
                value={form.zoning}
                onChange={(e) =>
                  setForm((c) => ({ ...c, zoning: e.target.value }))
                }
                placeholder={labels.zoningLabel}
              />
            </div>
            <Button type="submit" disabled={!canUseLiveApi || isSubmitting}>
              {isSubmitting
                ? `${labels.submitAction}...`
                : labels.submitAction}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Per-project approval table */}
      <Card>
        <CardContent className="p-6">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
            {labels.projectsTitle}
          </p>
          {projectsQuery.isLoading ? (
            <SkeletonLoader count={3} itemClassName="h-14" />
          ) : approvalItems.length > 0 ? (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)]">
                    <th className="pb-3 pr-4">{labels.projectNameLabel}</th>
                    <th className="pb-3 pr-4">{labels.statusLabel}</th>
                    <th className="pb-3 pr-4">{labels.complianceLabel}</th>
                    <th className="pb-3">{labels.stageLabel}</th>
                  </tr>
                </thead>
                <tbody>
                  {approvalItems.map((item) => (
                    <tr
                      key={item.projectId}
                      className="border-t border-[var(--line)]"
                    >
                      <td className="py-3 pr-4 font-semibold text-[var(--text-primary)]">
                        {item.projectName}
                      </td>
                      <td className="py-3 pr-4 text-[var(--text-secondary)]">
                        {
                          projects.find((p) => p.id === item.projectId)
                            ?.status ?? "-"
                        }
                      </td>
                      <td className="py-3 pr-4 text-[var(--text-secondary)]">
                        {item.complianceStatus ?? "-"}
                      </td>
                      <td className="py-3">
                        <span
                          className={`rounded-full px-3 py-1 text-xs font-bold ${stageBadge(item.stage)}`}
                        >
                          {stageLabel(item.stage, labels)}
                        </span>
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

      {/* Compliance result */}
      {complianceResult && (
        <Card className="border-[var(--accent-strong)]/20 bg-[var(--accent-strong)]/5">
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--accent-strong)]">
              {labels.complianceLabel}
            </p>
            <p className="mt-2 text-sm font-semibold text-[var(--text-primary)]">
              {complianceResult.overall_status ?? "-"}
            </p>
            {complianceResult.summary && (
              <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                {complianceResult.summary}
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </section>
  );
}
