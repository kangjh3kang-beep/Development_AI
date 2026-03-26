"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, CardContent, CardTitle, Input, Select } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { ApiClientError, apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";
import { useProjectStore } from "@/store/use-project-store";

type AuditScope = "project" | "tenant";
type ApprovalStatus = "pending" | "approved" | "rejected" | "not-required";
type ApprovalStatusFilter = "pending" | "approved" | "rejected" | "all";
type RoleFilter = "all" | "manager" | "investment-committee" | "risk-committee";
type DomainKey = "asset" | "development" | "transaction" | "finance";
type RecommendationStatus = "proceed" | "proceed-with-conditions" | "escalate";

type ProjectSummary = {
  id: string;
  name: string;
  status: string;
  address: string | null;
  total_area_sqm: number | null;
  updated_at: string;
};

type PaginatedResponse<T> = {
  items: T[];
  page: number;
  page_size: number;
  has_next: boolean;
};

type DomainAgentHistoryItemResponse = {
  task_id: string;
  project_id: string;
  domain: DomainKey;
  status: string;
  confidence_score: number;
  recommendation: RecommendationStatus;
  findings: Array<{
    factor?: string;
    impact?: string;
  }>;
  approval_required: boolean;
  approval_status: ApprovalStatus;
  approver_role: string | null;
  narrative: string | null;
  created_at: string;
};

type DomainAgentHistoryResponse = {
  items: DomainAgentHistoryItemResponse[];
};

type DomainAgentApprovalQueueItemResponse = {
  approval_id: string;
  task_id: string;
  project_id: string;
  domain: DomainKey;
  approver_role: string;
  status: ApprovalStatus | string;
  rationale: string | null;
  recommendation: RecommendationStatus;
  confidence_score: number;
  created_at: string;
  decided_at?: string | null;
};

type DomainAgentApprovalQueueResponse = {
  items: DomainAgentApprovalQueueItemResponse[];
};

type DomainAgentApprovalBatchDecisionResponse = {
  items: DomainAgentApprovalQueueItemResponse[];
  updated_count: number;
};

type Labels = {
  heroTitle: string;
  heroDescription: string;
  tokenHint: string;
  projectTitle: string;
  projectHint: string;
  projectSelectLabel: string;
  manualProjectIdLabel: string;
  currentProjectLabel: string;
  missingProjectError: string;
  authError: string;
  projectLoadError: string;
  approvalTitle: string;
  approvalEmpty: string;
  approvalErrorTitle: string;
  approvalErrorDetail: string;
  historyTitle: string;
  historyEmpty: string;
  historyErrorTitle: string;
  historyErrorDetail: string;
  retry: string;
  pendingLabel: string;
  approvedLabel: string;
  rejectedLabel: string;
  projectIdLabel: string;
  statusLabel: string;
  confidenceLabel: string;
  recommendationLabel: string;
  approverRoleLabel: string;
  rationaleLabel: string;
  createdLabel: string;
  decidedLabel: string;
  narrativeLabel: string;
  decisionNoteLabel: string;
  decisionNotePlaceholder: string;
  approveAction: string;
  rejectAction: string;
  bulkTitle: string;
  bulkDescription: string;
  bulkNoteLabel: string;
  bulkNotePlaceholder: string;
  approveAllAction: string;
  rejectAllAction: string;
  goToAgentAction: string;
  auditTitle: string;
  auditDescription: string;
  scopeLabel: string;
  statusFilterLabel: string;
  approverRoleFilterLabel: string;
  limitLabel: string;
  scopeOptions: Array<{ label: string; value: AuditScope }>;
  statusOptions: Array<{ label: string; value: ApprovalStatusFilter }>;
  roleOptions: Array<{ label: string; value: RoleFilter }>;
  limitOptions: Array<{ label: string; value: string }>;
  recommendationLabels: Record<RecommendationStatus, string>;
  approvalStatusLabels: Record<ApprovalStatus, string>;
  domainLabels: Record<DomainKey, string>;
};

const EN_LABELS: Labels = {
  heroTitle: "Approval operations center",
  heroDescription:
    "Review pending approvals, resolved decisions, and execution history without opening the agent analysis route first.",
  tokenHint:
    "Live approval operations require NEXT_PUBLIC_API_ACCESS_TOKEN or localStorage.propai_access_token.",
  projectTitle: "Project context",
  projectHint:
    "Choose a live project or pin an existing UUID when the audit scope should stay project-specific.",
  projectSelectLabel: "Live project",
  manualProjectIdLabel: "Manual project UUID",
  currentProjectLabel: "Current target",
  missingProjectError: "A real project UUID is required for project-scoped approval actions.",
  authError: "API authentication is required for live approval operations.",
  projectLoadError: "The project list could not be loaded.",
  approvalTitle: "Approval queue and audit",
  approvalEmpty: "No approval items match the current filters.",
  approvalErrorTitle: "Approval audit unavailable",
  approvalErrorDetail:
    "The approval audit query failed. Retry after restoring API connectivity or token state.",
  historyTitle: "Execution history",
  historyEmpty: "No execution history is available for the current scope.",
  historyErrorTitle: "Execution history unavailable",
  historyErrorDetail:
    "The execution history query failed. Retry after restoring API connectivity or token state.",
  retry: "Retry",
  pendingLabel: "Pending approvals",
  approvedLabel: "Approved decisions",
  rejectedLabel: "Rejected decisions",
  projectIdLabel: "Project ID",
  statusLabel: "Status",
  confidenceLabel: "Confidence",
  recommendationLabel: "Recommendation",
  approverRoleLabel: "Approver role",
  rationaleLabel: "Rationale",
  createdLabel: "Created",
  decidedLabel: "Decided",
  narrativeLabel: "Narrative",
  decisionNoteLabel: "Decision note (optional)",
  decisionNotePlaceholder: "Capture why this item is being approved or rejected.",
  approveAction: "Approve",
  rejectAction: "Reject",
  bulkTitle: "Bulk approval actions",
  bulkDescription:
    "Apply one decision across all pending items for the active project. Tenant-wide bulk actions remain disabled by design.",
  bulkNoteLabel: "Bulk decision note (optional)",
  bulkNotePlaceholder: "Add a shared note for the current pending batch.",
  approveAllAction: "Approve all pending",
  rejectAllAction: "Reject all pending",
  goToAgentAction: "Open agent orchestration",
  auditTitle: "Audit filters",
  auditDescription:
    "Switch between active-project and tenant-wide views, then narrow the queue by status or approver role.",
  scopeLabel: "Scope",
  statusFilterLabel: "Approval status",
  approverRoleFilterLabel: "Approver role",
  limitLabel: "Records",
  scopeOptions: [
    { label: "Active project", value: "project" },
    { label: "Tenant-wide", value: "tenant" },
  ],
  statusOptions: [
    { label: "Pending only", value: "pending" },
    { label: "Approved only", value: "approved" },
    { label: "Rejected only", value: "rejected" },
    { label: "All statuses", value: "all" },
  ],
  roleOptions: [
    { label: "All roles", value: "all" },
    { label: "Manager", value: "manager" },
    { label: "Investment Committee", value: "investment-committee" },
    { label: "Risk Committee", value: "risk-committee" },
  ],
  limitOptions: [
    { label: "6", value: "6" },
    { label: "12", value: "12" },
    { label: "20", value: "20" },
  ],
  recommendationLabels: {
    proceed: "Proceed",
    "proceed-with-conditions": "Proceed with conditions",
    escalate: "Escalate",
  },
  approvalStatusLabels: {
    pending: "Pending",
    approved: "Approved",
    rejected: "Rejected",
    "not-required": "Not required",
  },
  domainLabels: {
    asset: "Asset management",
    development: "Development execution",
    transaction: "Transaction strategy",
    finance: "Capital structure",
  },
};

const LABELS: Record<Locale, Labels> = {
  en: EN_LABELS,
  ko: EN_LABELS,
  "zh-CN": EN_LABELS,
};

function formatPercent(locale: string, value: number) {
  return new Intl.NumberFormat(locale, {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(value);
}

function formatDateTime(locale: string, value: string) {
  return new Intl.DateTimeFormat(locale === "zh-CN" ? "zh-CN" : locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function extractErrorMessage(error: unknown, authMessage: string) {
  if (error instanceof ApiClientError) {
    if (error.status === 401 || error.status === 403) {
      return authMessage;
    }
    return `API request failed with status ${error.status}.`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Request failed.";
}

function buildHistoryPath(scope: AuditScope, projectId: string | null, limit: string) {
  const params = new URLSearchParams();
  params.set("limit", limit);
  if (scope === "project" && projectId) {
    params.set("project_id", projectId);
  }
  return `/agents/domain/history?${params.toString()}`;
}

function buildApprovalsPath(
  scope: AuditScope,
  projectId: string | null,
  limit: string,
  status: ApprovalStatusFilter,
  approverRole: RoleFilter,
) {
  const params = new URLSearchParams();
  params.set("limit", limit);
  params.set("status", status);
  if (scope === "project" && projectId) {
    params.set("project_id", projectId);
  }
  if (approverRole !== "all") {
    params.set("approver_role", approverRole);
  }
  return `/agents/domain/approvals?${params.toString()}`;
}

export function ApprovalOperationsWorkspaceClient({
  locale,
}: {
  locale: Locale;
}) {
  const labels = LABELS[locale];
  const queryClient = useQueryClient();
  const currentProjectId = useProjectStore((state) => state.currentProjectId);
  const setCurrentProject = useProjectStore((state) => state.setCurrentProject);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [manualProjectId, setManualProjectId] = useState("");
  const [auditScope, setAuditScope] = useState<AuditScope>("project");
  const [approvalStatusFilter, setApprovalStatusFilter] =
    useState<ApprovalStatusFilter>("pending");
  const [approverRoleFilter, setApproverRoleFilter] = useState<RoleFilter>("all");
  const [auditLimit, setAuditLimit] = useState("12");
  const [approvalNotes, setApprovalNotes] = useState<Record<string, string>>({});
  const [bulkApprovalNote, setBulkApprovalNote] = useState("");
  const [pendingApprovalId, setPendingApprovalId] = useState<string | null>(null);
  const [isBulkDecisionPending, setIsBulkDecisionPending] = useState(false);
  const [approvalActionError, setApprovalActionError] = useState<string | null>(null);
  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  const projectsQuery = useQuery({
    queryKey: ["approval-ops", "projects"],
    queryFn: () =>
      apiClient.get<PaginatedResponse<ProjectSummary>>("/projects?page=1&page_size=20", {
        useMock: false,
      }),
    enabled: canUseLiveApi,
  });

  const activeProjectId = useMemo(
    () =>
      manualProjectId.trim() ||
      selectedProjectId ||
      currentProjectId ||
      projectsQuery.data?.items[0]?.id ||
      null,
    [currentProjectId, manualProjectId, projectsQuery.data?.items, selectedProjectId],
  );

  const historyQuery = useQuery({
    queryKey: ["approval-ops", "history", auditScope, activeProjectId, auditLimit],
    queryFn: () =>
      apiClient.get<DomainAgentHistoryResponse>(
        buildHistoryPath(auditScope, activeProjectId, auditLimit),
        { useMock: false },
      ),
    enabled: canUseLiveApi && (auditScope === "tenant" || Boolean(activeProjectId)),
  });

  const approvalsQuery = useQuery({
    queryKey: [
      "approval-ops",
      "approvals",
      auditScope,
      activeProjectId,
      auditLimit,
      approvalStatusFilter,
      approverRoleFilter,
    ],
    queryFn: () =>
      apiClient.get<DomainAgentApprovalQueueResponse>(
        buildApprovalsPath(
          auditScope,
          activeProjectId,
          auditLimit,
          approvalStatusFilter,
          approverRoleFilter,
        ),
        { useMock: false },
      ),
    enabled: canUseLiveApi && (auditScope === "tenant" || Boolean(activeProjectId)),
  });

  const approvalItems = approvalsQuery.data?.items ?? [];
  const pendingApprovalItems = approvalItems.filter((item) => item.status === "pending");
  const summary = approvalItems.reduce(
    (acc, item) => {
      if (item.status === "pending") {
        acc.pending += 1;
      } else if (item.status === "approved") {
        acc.approved += 1;
      } else if (item.status === "rejected") {
        acc.rejected += 1;
      }
      return acc;
    },
    { pending: 0, approved: 0, rejected: 0 },
  );

  const projectQueryError = projectsQuery.isError
    ? extractErrorMessage(projectsQuery.error, labels.authError)
    : null;
  const historyQueryError = historyQuery.isError
    ? extractErrorMessage(historyQuery.error, labels.authError)
    : null;
  const approvalsQueryError = approvalsQuery.isError
    ? extractErrorMessage(approvalsQuery.error, labels.authError)
    : null;

  async function refreshReadModels() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["approval-ops", "history"] }),
      queryClient.invalidateQueries({ queryKey: ["approval-ops", "approvals"] }),
    ]);
  }

  async function handleApprovalDecision(
    approvalId: string,
    taskId: string,
    decision: "approved" | "rejected",
  ) {
    if (!canUseLiveApi) {
      setApprovalActionError(labels.authError);
      return;
    }

    setPendingApprovalId(approvalId);
    setApprovalActionError(null);
    try {
      await apiClient.post(`/agents/domain/approvals/${approvalId}/decision`, {
        body: {
          task_id: taskId,
          decision,
          rationale: approvalNotes[approvalId]?.trim() || undefined,
        },
        useMock: false,
      });
      setApprovalNotes((current) => ({
        ...current,
        [approvalId]: "",
      }));
      await refreshReadModels();
    } catch (error) {
      setApprovalActionError(extractErrorMessage(error, labels.authError));
    } finally {
      setPendingApprovalId(null);
    }
  }

  async function handleBulkDecision(decision: "approved" | "rejected") {
    if (!canUseLiveApi) {
      setApprovalActionError(labels.authError);
      return;
    }
    if (!activeProjectId) {
      setApprovalActionError(labels.missingProjectError);
      return;
    }

    setIsBulkDecisionPending(true);
    setApprovalActionError(null);
    try {
      await apiClient.post<DomainAgentApprovalBatchDecisionResponse>(
        "/agents/domain/approvals/decision-batch",
        {
          body: {
            project_id: activeProjectId,
            approval_ids: pendingApprovalItems.map((item) => item.approval_id),
            decision,
            rationale: bulkApprovalNote.trim() || undefined,
          },
          useMock: false,
        },
      );
      setBulkApprovalNote("");
      await refreshReadModels();
    } catch (error) {
      setApprovalActionError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsBulkDecisionPending(false);
    }
  }

  return (
    <section className="grid gap-6">
      <Card>
        <CardContent className="grid gap-5 p-6 lg:grid-cols-[1.35fr_0.9fr]">
          <div>
            <CardTitle>{labels.heroTitle}</CardTitle>
            <p className="mt-3 text-sm leading-7 text-[rgba(19,33,47,0.72)]">
              {labels.heroDescription}
            </p>
          </div>
          <div className="rounded-[1.35rem] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4 text-sm leading-7 text-[rgba(19,33,47,0.72)]">
            <p>{labels.tokenHint}</p>
            <div className="mt-4 flex flex-wrap gap-3">
              <Link
                href={`/${locale}/agent`}
                className="rounded-full border border-[var(--line)] bg-white px-4 py-2 text-sm font-medium text-[var(--foreground)] transition hover:border-[var(--accent)] hover:text-[var(--accent-strong)]"
              >
                {labels.goToAgentAction}
              </Link>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[1.1fr_1fr]">
        <Card>
          <CardContent className="p-6">
            <CardTitle>{labels.projectTitle}</CardTitle>
            <p className="mt-3 text-sm leading-7 text-[rgba(19,33,47,0.72)]">
              {labels.projectHint}
            </p>
            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <Select
                label={labels.projectSelectLabel}
                value={selectedProjectId || activeProjectId || ""}
                onValueChange={(value) => {
                  setSelectedProjectId(value);
                  if (value) {
                    setCurrentProject(value);
                  }
                }}
                options={(projectsQuery.data?.items ?? []).map((project) => ({
                  label: project.name,
                  value: project.id,
                }))}
              />
              <label className="grid gap-2 text-sm font-medium text-[var(--foreground)]">
                <span>{labels.manualProjectIdLabel}</span>
                <Input
                  value={manualProjectId}
                  onChange={(event) => {
                    const value = event.target.value;
                    setManualProjectId(value);
                    if (value.trim()) {
                      setCurrentProject(value.trim());
                    } else if (selectedProjectId) {
                      setCurrentProject(selectedProjectId);
                    }
                  }}
                  placeholder="00000000-0000-0000-0000-000000000000"
                />
              </label>
            </div>
            {projectsQuery.isLoading ? (
              <div className="mt-5">
                <SkeletonLoader count={1} itemClassName="h-10" />
              </div>
            ) : null}
            {projectsQuery.isError ? (
              <div className="mt-5">
                <WorkspaceQueryErrorCard
                  title={labels.projectLoadError}
                  description={labels.projectHint}
                  message={projectQueryError ?? labels.projectLoadError}
                  actionLabel={labels.retry}
                  onRetry={() => {
                    void projectsQuery.refetch();
                  }}
                />
              </div>
            ) : null}
            <div className="mt-5 rounded-[1.35rem] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4 text-sm text-[rgba(19,33,47,0.74)]">
              {labels.currentProjectLabel}:{" "}
              <span className="font-semibold text-[var(--foreground)]">
                {auditScope === "tenant" ? "Tenant-wide" : activeProjectId ?? "Not selected"}
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <CardTitle>{labels.auditTitle}</CardTitle>
            <p className="mt-3 text-sm leading-7 text-[rgba(19,33,47,0.72)]">
              {labels.auditDescription}
            </p>
            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <Select
                label={labels.scopeLabel}
                value={auditScope}
                onValueChange={(value) => setAuditScope(value as AuditScope)}
                options={labels.scopeOptions}
              />
              <Select
                label={labels.statusFilterLabel}
                value={approvalStatusFilter}
                onValueChange={(value) =>
                  setApprovalStatusFilter(value as ApprovalStatusFilter)
                }
                options={labels.statusOptions}
              />
              <Select
                label={labels.approverRoleFilterLabel}
                value={approverRoleFilter}
                onValueChange={(value) => setApproverRoleFilter(value as RoleFilter)}
                options={labels.roleOptions}
              />
              <Select
                label={labels.limitLabel}
                value={auditLimit}
                onValueChange={setAuditLimit}
                options={labels.limitOptions}
              />
            </div>
          </CardContent>
        </Card>
      </div>

      {!canUseLiveApi ? (
        <p className="rounded-[1.35rem] border border-[rgba(217,119,6,0.24)] bg-[rgba(255,247,237,0.92)] px-4 py-3 text-sm font-medium text-[var(--spot)]" role="alert">
          {labels.authError}
        </p>
      ) : null}
      {auditScope === "project" && !activeProjectId ? (
        <p className="rounded-[1.35rem] border border-[rgba(217,119,6,0.24)] bg-[rgba(255,247,237,0.92)] px-4 py-3 text-sm font-medium text-[var(--spot)]" role="alert">
          {labels.missingProjectError}
        </p>
      ) : null}
      {approvalActionError ? (
        <p className="rounded-[1.35rem] border border-[rgba(217,119,6,0.24)] bg-[rgba(255,247,237,0.92)] px-4 py-3 text-sm font-medium text-[var(--spot)]" role="alert">
          {approvalActionError}
        </p>
      ) : null}

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardContent className="p-5">
            <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.52)]">
              {labels.pendingLabel}
            </p>
            <p className="mt-3 text-3xl font-semibold text-[var(--foreground)]">
              {summary.pending}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.52)]">
              {labels.approvedLabel}
            </p>
            <p className="mt-3 text-3xl font-semibold text-[var(--foreground)]">
              {summary.approved}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.52)]">
              {labels.rejectedLabel}
            </p>
            <p className="mt-3 text-3xl font-semibold text-[var(--foreground)]">
              {summary.rejected}
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardContent className="p-6">
            <CardTitle>{labels.approvalTitle}</CardTitle>
            {approvalsQuery.isLoading ? (
              <div className="mt-5">
                <SkeletonLoader count={3} itemClassName="h-28" />
              </div>
            ) : null}
            {approvalsQuery.isError ? (
              <div className="mt-5">
                <WorkspaceQueryErrorCard
                  title={labels.approvalErrorTitle}
                  description={labels.approvalErrorDetail}
                  message={approvalsQueryError ?? labels.approvalErrorTitle}
                  actionLabel={labels.retry}
                  onRetry={() => {
                    void approvalsQuery.refetch();
                  }}
                />
              </div>
            ) : null}
            {auditScope === "project" &&
            pendingApprovalItems.length > 1 &&
            !approvalsQuery.isLoading &&
            !approvalsQuery.isError ? (
              <div className="mt-5 rounded-[1.35rem] border border-[var(--line)] bg-[rgba(255,255,255,0.72)] px-4 py-4">
                <p className="text-sm font-semibold text-[var(--foreground)]">
                  {labels.bulkTitle}
                </p>
                <p className="mt-2 text-sm leading-7 text-[rgba(19,33,47,0.7)]">
                  {labels.bulkDescription}
                </p>
                <label
                  className="mt-4 grid gap-2 text-sm font-medium text-[rgba(19,33,47,0.78)]"
                  htmlFor="approval-bulk-note"
                >
                  <span>{labels.bulkNoteLabel}</span>
                  <textarea
                    id="approval-bulk-note"
                    value={bulkApprovalNote}
                    onChange={(event) => setBulkApprovalNote(event.target.value)}
                    disabled={isBulkDecisionPending || Boolean(pendingApprovalId)}
                    placeholder={labels.bulkNotePlaceholder}
                    className="min-h-20 rounded-[1rem] border border-[var(--line)] bg-white/85 px-4 py-3 text-sm text-[var(--foreground)] outline-none transition placeholder:text-[rgba(19,33,47,0.4)] focus:border-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-60"
                  />
                </label>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button
                    onClick={() => {
                      void handleBulkDecision("approved");
                    }}
                    disabled={isBulkDecisionPending || Boolean(pendingApprovalId)}
                  >
                    {labels.approveAllAction}
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => {
                      void handleBulkDecision("rejected");
                    }}
                    disabled={isBulkDecisionPending || Boolean(pendingApprovalId)}
                  >
                    {labels.rejectAllAction}
                  </Button>
                </div>
              </div>
            ) : null}
            {approvalItems.length ? (
              <ol className="mt-5 grid gap-3">
                {approvalItems.map((item) => (
                  <li
                    key={item.approval_id}
                    className="rounded-[1.35rem] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-[var(--foreground)]">
                          {labels.domainLabels[item.domain]}
                        </p>
                        <p className="mt-2 text-sm text-[rgba(19,33,47,0.7)]">
                          {labels.recommendationLabel}:{" "}
                          {labels.recommendationLabels[item.recommendation]}
                        </p>
                      </div>
                      <span className="rounded-full border border-[var(--line)] px-3 py-1 text-xs font-medium text-[rgba(19,33,47,0.72)]">
                        {labels.approvalStatusLabels[item.status as ApprovalStatus] ??
                          item.status}
                      </span>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-[rgba(19,33,47,0.72)]">
                      <span className="rounded-full bg-white px-3 py-1">
                        {labels.approverRoleLabel}: {item.approver_role}
                      </span>
                      <span className="rounded-full bg-white px-3 py-1">
                        {labels.projectIdLabel}: {item.project_id}
                      </span>
                      <span className="rounded-full bg-white px-3 py-1">
                        {labels.createdLabel}: {formatDateTime(locale, item.created_at)}
                      </span>
                      {item.decided_at ? (
                        <span className="rounded-full bg-white px-3 py-1">
                          {labels.decidedLabel}: {formatDateTime(locale, item.decided_at)}
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-3 text-sm leading-7 text-[rgba(19,33,47,0.72)]">
                      {labels.rationaleLabel}: {item.rationale ?? "n/a"}
                    </p>
                    {item.status === "pending" ? (
                      <>
                        <label
                          className="mt-4 grid gap-2 text-sm font-medium text-[rgba(19,33,47,0.78)]"
                          htmlFor={`approval-note-${item.approval_id}`}
                        >
                          <span>{labels.decisionNoteLabel}</span>
                          <textarea
                            id={`approval-note-${item.approval_id}`}
                            value={approvalNotes[item.approval_id] ?? ""}
                            onChange={(event) =>
                              setApprovalNotes((current) => ({
                                ...current,
                                [item.approval_id]: event.target.value,
                              }))
                            }
                            disabled={
                              pendingApprovalId === item.approval_id || isBulkDecisionPending
                            }
                            placeholder={labels.decisionNotePlaceholder}
                            className="min-h-20 rounded-[1rem] border border-[var(--line)] bg-white/85 px-4 py-3 text-sm text-[var(--foreground)] outline-none transition placeholder:text-[rgba(19,33,47,0.4)] focus:border-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-60"
                          />
                        </label>
                        <div className="mt-4 flex flex-wrap gap-2">
                          <Button
                            onClick={() => {
                              void handleApprovalDecision(
                                item.approval_id,
                                item.task_id,
                                "approved",
                              );
                            }}
                            disabled={
                              pendingApprovalId === item.approval_id || isBulkDecisionPending
                            }
                          >
                            {labels.approveAction}
                          </Button>
                          <Button
                            variant="secondary"
                            onClick={() => {
                              void handleApprovalDecision(
                                item.approval_id,
                                item.task_id,
                                "rejected",
                              );
                            }}
                            disabled={
                              pendingApprovalId === item.approval_id || isBulkDecisionPending
                            }
                          >
                            {labels.rejectAction}
                          </Button>
                        </div>
                      </>
                    ) : null}
                  </li>
                ))}
              </ol>
            ) : !approvalsQuery.isLoading && !approvalsQuery.isError ? (
              <p className="mt-4 text-sm leading-7 text-[rgba(19,33,47,0.68)]">
                {labels.approvalEmpty}
              </p>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <CardTitle>{labels.historyTitle}</CardTitle>
            {historyQuery.isLoading ? (
              <div className="mt-5">
                <SkeletonLoader count={2} itemClassName="h-24" />
              </div>
            ) : null}
            {historyQuery.isError ? (
              <div className="mt-5">
                <WorkspaceQueryErrorCard
                  title={labels.historyErrorTitle}
                  description={labels.historyErrorDetail}
                  message={historyQueryError ?? labels.historyErrorTitle}
                  actionLabel={labels.retry}
                  onRetry={() => {
                    void historyQuery.refetch();
                  }}
                />
              </div>
            ) : null}
            {historyQuery.data?.items.length ? (
              <ol className="mt-5 grid gap-3">
                {historyQuery.data.items.map((item) => (
                  <li
                    key={item.task_id}
                    className="rounded-[1.35rem] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-[var(--foreground)]">
                          {labels.domainLabels[item.domain]}
                        </p>
                        <p className="mt-2 text-sm text-[rgba(19,33,47,0.7)]">
                          {labels.recommendationLabel}:{" "}
                          {labels.recommendationLabels[item.recommendation]}
                        </p>
                      </div>
                      <span className="rounded-full border border-[var(--line)] px-3 py-1 text-xs font-medium text-[rgba(19,33,47,0.72)]">
                        {formatPercent(locale, item.confidence_score)}
                      </span>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-[rgba(19,33,47,0.72)]">
                      <span className="rounded-full bg-white px-3 py-1">
                        {labels.statusLabel}: {item.status}
                      </span>
                      <span className="rounded-full bg-white px-3 py-1">
                        {labels.projectIdLabel}: {item.project_id}
                      </span>
                      <span className="rounded-full bg-white px-3 py-1">
                        {labels.approverRoleLabel}: {item.approver_role ?? "n/a"}
                      </span>
                      <span className="rounded-full bg-white px-3 py-1">
                        {labels.createdLabel}: {formatDateTime(locale, item.created_at)}
                      </span>
                    </div>
                    {item.narrative ? (
                      <p className="mt-3 text-sm leading-7 text-[rgba(19,33,47,0.72)]">
                        {labels.narrativeLabel}: {item.narrative}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ol>
            ) : !historyQuery.isLoading && !historyQuery.isError ? (
              <p className="mt-4 text-sm leading-7 text-[rgba(19,33,47,0.68)]">
                {labels.historyEmpty}
              </p>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
