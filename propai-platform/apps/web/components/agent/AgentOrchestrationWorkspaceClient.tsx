"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, CardContent, CardTitle, Input, Select } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { ApiClientError, apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";
import { useProjectStore } from "@/store/use-project-store";

type DomainKey = "asset" | "development" | "transaction" | "finance";
type ApprovalStatus = "not-required" | "pending" | "approved" | "rejected";
type RecommendationStatus = "proceed" | "proceed-with-conditions" | "escalate";
type AuditScope = "project" | "tenant";
type ApprovalStatusFilter = "pending" | "approved" | "rejected" | "all";

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

type DomainAgentRunResponse = {
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
};

type DomainMultiAnalysisResponse = {
  items: DomainAgentRunResponse[];
  portfolio_summary: string;
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
  heroHint: string;
  tokenHint: string;
  projectTitle: string;
  projectHint: string;
  projectSelectLabel: string;
  manualProjectIdLabel: string;
  currentProjectLabel: string;
  noProjectsLabel: string;
  authError: string;
  missingProjectError: string;
  domainSelectionError: string;
  projectLoadError: string;
  configurationTitle: string;
  questionLabel: string;
  focusDomainLabel: string;
  approvalRoleLabel: string;
  occupancyRateLabel: string;
  ltvLabel: string;
  scheduleBufferLabel: string;
  preLeasingLabel: string;
  orchestrationDomainsLabel: string;
  runFocusedAction: string;
  runOrchestrationAction: string;
  focusedTitle: string;
  focusedEmpty: string;
  portfolioTitle: string;
  portfolioEmpty: string;
  portfolioSummaryLabel: string;
  projectIdLabel: string;
  domainLabel: string;
  statusLabel: string;
  confidenceLabel: string;
  recommendationLabel: string;
  approvalLabel: string;
  findingsLabel: string;
  noFindingsLabel: string;
  totalRunsLabel: string;
  approvalsRequiredLabel: string;
  recommendationLabels: Record<RecommendationStatus, string>;
  approvalStatusLabels: Record<ApprovalStatus, string>;
  domainLabels: Record<DomainKey, string>;
  approvalRoleOptions: Array<{
    label: string;
    value: string;
  }>;
};

const LABELS: Record<Locale, Labels> = {
  ko: {
    heroTitle: "영역별 AI 통합 분석",
    heroDescription:
      "자산, 개발, 거래, 금융 영역의 AI 분석을 실제 `/agents/domain` API에 연결해 승인 필요 상태와 권고안을 한 화면에서 검증합니다.",
    heroHint:
      "단건 심화 분석과 여러 영역 통합 분석을 같은 프로젝트 컨텍스트에서 바로 비교할 수 있습니다.",
    tokenHint:
      "분석을 위해 로그인이 필요합니다.",
    projectTitle: "프로젝트 컨텍스트",
    projectHint:
      "라이브 프로젝트를 선택하거나 기존 프로젝트 UUID를 직접 입력해 AI 분석 실행 대상을 고정합니다.",
    projectSelectLabel: "라이브 프로젝트",
    manualProjectIdLabel: "수동 프로젝트 UUID",
    currentProjectLabel: "현재 대상",
    noProjectsLabel: "라이브 프로젝트가 없으면 기존 UUID를 직접 입력하세요.",
    authError: "실시간 호출을 위해 API 인증이 필요합니다.",
    missingProjectError: "실존 프로젝트 UUID가 필요합니다.",
    domainSelectionError: "통합 분석에 포함할 영역을 하나 이상 선택해야 합니다.",
    projectLoadError: "프로젝트 목록을 불러오지 못했습니다.",
    configurationTitle: "실행 구성",
    questionLabel: "투자 판단 질문",
    focusDomainLabel: "단건 분석 도메인",
    approvalRoleLabel: "승인 역할",
    occupancyRateLabel: "점유율",
    ltvLabel: "LTV",
    scheduleBufferLabel: "일정 버퍼(월)",
    preLeasingLabel: "선임대 비율",
    orchestrationDomainsLabel: "통합 분석 범위",
    runFocusedAction: "단건 분석",
    runOrchestrationAction: "통합 분석 실행",
    focusedTitle: "단건 분석 결과",
    focusedEmpty: "아직 단건 분석 결과가 없습니다.",
    portfolioTitle: "여러 영역 통합 분석",
    portfolioEmpty: "통합 분석을 실행하면 영역별 권고안과 승인 상태가 여기에 표시됩니다.",
    portfolioSummaryLabel: "포트폴리오 요약",
    projectIdLabel: "프로젝트 ID",
    domainLabel: "도메인",
    statusLabel: "상태",
    confidenceLabel: "신뢰도",
    recommendationLabel: "권고",
    approvalLabel: "승인",
    findingsLabel: "핵심 신호",
    noFindingsLabel: "추가 신호 없음",
    totalRunsLabel: "완료 도메인",
    approvalsRequiredLabel: "승인 필요",
    recommendationLabels: {
      proceed: "진행",
      "proceed-with-conditions": "조건부 진행",
      escalate: "상위 검토",
    },
    approvalStatusLabels: {
      "not-required": "불필요",
      pending: "대기",
      approved: "승인",
      rejected: "반려",
    },
    domainLabels: {
      asset: "자산 관리",
      development: "개발 실행",
      transaction: "거래 전략",
      finance: "자본 구조",
    },
    approvalRoleOptions: [
      { label: "Manager", value: "manager" },
      { label: "Investment Committee", value: "investment-committee" },
      { label: "Risk Committee", value: "risk-committee" },
    ],
  },
  en: {
    heroTitle: "Domain agent orchestration workspace",
    heroDescription:
      "Connect asset, development, transaction, and finance agents to the live `/agents/domain` workflow and inspect approval-gated recommendations in one surface.",
    heroHint:
      "Run a focused deep-dive and a multi-domain orchestration against the same project context to compare outcomes immediately.",
    tokenHint:
      "Login required for analysis.",
    projectTitle: "Project context",
    projectHint:
      "Choose a live project or enter an existing project UUID to pin the analysis target.",
    projectSelectLabel: "Live project",
    manualProjectIdLabel: "Manual project UUID",
    currentProjectLabel: "Current target",
    noProjectsLabel: "If no live project is available, enter an existing UUID manually.",
    authError: "API authentication is required for live workspace calls.",
    missingProjectError: "A real project UUID is required.",
    domainSelectionError: "Select at least one domain for orchestration.",
    projectLoadError: "The project list could not be loaded.",
    configurationTitle: "Execution setup",
    questionLabel: "Investment question",
    focusDomainLabel: "Focused domain",
    approvalRoleLabel: "Approval role",
    occupancyRateLabel: "Occupancy rate",
    ltvLabel: "LTV",
    scheduleBufferLabel: "Schedule buffer (months)",
    preLeasingLabel: "Pre-leasing ratio",
    orchestrationDomainsLabel: "Multi-domain coverage",
    runFocusedAction: "Run focused analysis",
    runOrchestrationAction: "Run orchestration",
    focusedTitle: "Focused result",
    focusedEmpty: "No focused agent run has been executed yet.",
    portfolioTitle: "Multi-domain orchestration",
    portfolioEmpty:
      "Run orchestration to render domain recommendations and approval states here.",
    portfolioSummaryLabel: "Portfolio summary",
    projectIdLabel: "Project ID",
    domainLabel: "Domain",
    statusLabel: "Status",
    confidenceLabel: "Confidence",
    recommendationLabel: "Recommendation",
    approvalLabel: "Approval",
    findingsLabel: "Signals",
    noFindingsLabel: "No additional signals",
    totalRunsLabel: "Completed domains",
    approvalsRequiredLabel: "Approvals required",
    recommendationLabels: {
      proceed: "Proceed",
      "proceed-with-conditions": "Proceed with conditions",
      escalate: "Escalate",
    },
    approvalStatusLabels: {
      "not-required": "Not required",
      pending: "Pending",
      approved: "Approved",
      rejected: "Rejected",
    },
    domainLabels: {
      asset: "Asset management",
      development: "Development execution",
      transaction: "Transaction strategy",
      finance: "Capital structure",
    },
    approvalRoleOptions: [
      { label: "Manager", value: "manager" },
      { label: "Investment Committee", value: "investment-committee" },
      { label: "Risk Committee", value: "risk-committee" },
    ],
  },
  "zh-CN": {
    heroTitle: "领域智能体编排工作区",
    heroDescription:
      "将资产、开发、交易、金融智能体接入实时 `/agents/domain` 工作流，并在同一界面查看需要审批的建议结果。",
    heroHint:
      "可在同一项目上下文中对比单领域深度分析与多领域编排输出。",
    tokenHint:
      "分析需要登录。",
    projectTitle: "项目上下文",
    projectHint:
      "选择实时项目或手动输入已有项目 UUID，以固定分析目标。",
    projectSelectLabel: "实时项目",
    manualProjectIdLabel: "手动项目 UUID",
    currentProjectLabel: "当前目标",
    noProjectsLabel: "如果当前没有实时项目，请手动输入已有 UUID。",
    authError: "实时工作区调用需要 API 身份认证。",
    missingProjectError: "必须提供真实项目 UUID。",
    domainSelectionError: "编排执行至少要选择一个领域。",
    projectLoadError: "无法加载项目列表。",
    configurationTitle: "执行配置",
    questionLabel: "投资判断问题",
    focusDomainLabel: "单领域分析",
    approvalRoleLabel: "审批角色",
    occupancyRateLabel: "出租率",
    ltvLabel: "LTV",
    scheduleBufferLabel: "工期缓冲（月）",
    preLeasingLabel: "预租比例",
    orchestrationDomainsLabel: "多领域范围",
    runFocusedAction: "执行单领域分析",
    runOrchestrationAction: "执行编排",
    focusedTitle: "单领域结果",
    focusedEmpty: "尚未执行单领域分析。",
    portfolioTitle: "多领域编排",
    portfolioEmpty: "执行编排后，这里会显示各领域建议与审批状态。",
    portfolioSummaryLabel: "组合摘要",
    projectIdLabel: "项目 ID",
    domainLabel: "领域",
    statusLabel: "状态",
    confidenceLabel: "置信度",
    recommendationLabel: "建议",
    approvalLabel: "审批",
    findingsLabel: "关键信号",
    noFindingsLabel: "没有额外信号",
    totalRunsLabel: "完成领域数",
    approvalsRequiredLabel: "需要审批",
    recommendationLabels: {
      proceed: "继续推进",
      "proceed-with-conditions": "附条件推进",
      escalate: "升级审查",
    },
    approvalStatusLabels: {
      "not-required": "不需要",
      pending: "待审批",
      approved: "已审批",
      rejected: "已驳回",
    },
    domainLabels: {
      asset: "资产管理",
      development: "开发执行",
      transaction: "交易策略",
      finance: "资本结构",
    },
    approvalRoleOptions: [
      { label: "Manager", value: "manager" },
      { label: "Investment Committee", value: "investment-committee" },
      { label: "Risk Committee", value: "risk-committee" },
    ],
  },
};

const DOMAIN_ORDER: DomainKey[] = [
  "asset",
  "development",
  "transaction",
  "finance",
];

const PROJECT_QUERY_UI = {
  en: {
    detail:
      "The live project picker failed to load. Manual UUID input remains available.",
    retry: "Retry",
  },
  ko: {
    detail:
      "라이브 프로젝트 선택 목록을 불러오지 못했습니다. 수동 UUID 입력은 계속 사용할 수 있습니다.",
    retry: "다시 시도",
  },
  "zh-CN": {
    detail: "实时项目选择列表加载失败，但仍可继续手动输入项目 UUID。",
    retry: "重试",
  },
} as const;

const AGENT_READ_UI = {
  en: {
    historyTitle: "Execution history",
    historyEmpty: "No persisted domain-agent runs are stored for the active project yet.",
    historyErrorTitle: "Execution history unavailable",
    historyErrorDetail:
      "The persisted domain-agent history query failed. Retry after restoring API connectivity or access token state.",
    approvalTitle: "Approval queue",
    approvalEmpty: "No persisted approvals are queued for the active project.",
    approvalErrorTitle: "Approval queue unavailable",
    approvalErrorDetail:
      "The persisted domain-agent approval queue query failed. Retry after restoring API connectivity or access token state.",
    retry: "Retry",
    approveAction: "Approve",
    rejectAction: "Reject",
    decisionNoteLabel: "Decision note (optional)",
    decisionNotePlaceholder:
      "Capture why this queue item is being approved or rejected.",
    createdLabel: "Created",
    approverRoleLabel: "Approver role",
    rationaleLabel: "Rationale",
    narrativeLabel: "Narrative",
  },
  ko: {
    historyTitle: "실행 이력",
    historyEmpty: "현재 프로젝트에는 저장된 영역별 AI 분석 실행 이력이 없습니다.",
    historyErrorTitle: "실행 이력을 불러올 수 없습니다.",
    historyErrorDetail:
      "저장된 영역별 AI 분석 이력 조회가 실패했습니다. API 연결 또는 액세스 토큰 상태를 복구한 뒤 다시 시도하세요.",
    approvalTitle: "승인 큐",
    approvalEmpty: "현재 프로젝트에 대기 중인 승인 항목이 없습니다.",
    approvalErrorTitle: "승인 큐를 불러올 수 없습니다.",
    approvalErrorDetail:
      "저장된 승인 큐 조회가 실패했습니다. API 연결 또는 액세스 토큰 상태를 복구한 뒤 다시 시도하세요.",
    retry: "다시 시도",
    approveAction: "승인",
    rejectAction: "반려",
    createdLabel: "생성 시각",
    approverRoleLabel: "승인 역할",
    rationaleLabel: "사유",
    narrativeLabel: "내러티브",
  },
  "zh-CN": {
    historyTitle: "执行历史",
    historyEmpty: "当前项目还没有已保存的领域智能体执行记录。",
    historyErrorTitle: "无法加载执行历史。",
    historyErrorDetail:
      "已保存的领域智能体历史查询失败。恢复 API 连通性或访问令牌状态后可重试。",
    approvalTitle: "审批队列",
    approvalEmpty: "当前项目没有待处理的审批记录。",
    approvalErrorTitle: "无法加载审批队列。",
    approvalErrorDetail:
      "已保存的审批队列查询失败。恢复 API 连通性或访问令牌状态后可重试。",
    retry: "重试",
    approveAction: "批准",
    rejectAction: "拒绝",
    createdLabel: "创建时间",
    approverRoleLabel: "审批角色",
    rationaleLabel: "原因",
    narrativeLabel: "摘要",
  },
} as const;

const APPROVAL_DECISION_UI = {
  itemLabel: "Decision note (optional)",
  itemPlaceholder: "Capture why this queue item is being approved or rejected.",
  bulkTitle: "Bulk approval actions",
  bulkDescription:
    "Apply one approval decision across all pending items for the active project.",
  bulkLabel: "Bulk decision note (optional)",
  bulkPlaceholder: "Add a shared note for the entire pending approval batch.",
  approveAllAction: "Approve all pending",
  rejectAllAction: "Reject all pending",
  pendingCountLabel: "Pending items",
} as const;

const AUDIT_FILTER_UI = {
  title: "Approval audit filters",
  description:
    "Switch between the active project and a tenant-wide queue, then inspect pending or resolved approvals.",
  scopeLabel: "Scope",
  statusLabel: "Approval status",
  limitLabel: "Records",
  decidedLabel: "Decided",
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
  limitOptions: [
    { label: "6", value: "6" },
    { label: "12", value: "12" },
    { label: "20", value: "20" },
  ],
} as const;

function formatPercent(locale: string, value: number) {
  return new Intl.NumberFormat(locale, {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(value);
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

export function AgentOrchestrationWorkspaceClient({
  locale,
}: {
  locale: Locale;
}) {
  const queryClient = useQueryClient();
  const labels = LABELS[locale] || LABELS["ko"];
  const readUi = (locale && AGENT_READ_UI[locale]) || AGENT_READ_UI.ko || AGENT_READ_UI.en;
  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  const currentProjectId = useProjectStore((state) => state.currentProjectId);
  const setCurrentProject = useProjectStore((state) => state.setCurrentProject);

  const [selectedProjectId, setSelectedProjectId] = useState(currentProjectId ?? "");
  const [manualProjectId, setManualProjectId] = useState("");
  const [question, setQuestion] = useState(
    "Should we proceed with underwriting for this mixed-use development under the current risk signals?",
  );
  const [focusedDomain, setFocusedDomain] = useState<DomainKey>("asset");
  const [approvalRole, setApprovalRole] = useState("manager");
  const [selectedDomains, setSelectedDomains] = useState<DomainKey[]>(DOMAIN_ORDER);
  const [contextValues, setContextValues] = useState({
    occupancyRate: "0.92",
    ltv: "0.66",
    scheduleBufferMonths: "4",
    preLeasingRatio: "0.58",
  });
  const [workspaceError, setWorkspaceError] = useState("");
  const [focusedResult, setFocusedResult] = useState<DomainAgentRunResponse | null>(
    null,
  );
  const [portfolioResult, setPortfolioResult] =
    useState<DomainMultiAnalysisResponse | null>(null);
  const [isRunningFocused, setIsRunningFocused] = useState(false);
  const [isRunningPortfolio, setIsRunningPortfolio] = useState(false);
  const [approvalActionError, setApprovalActionError] = useState("");
  const [pendingApprovalId, setPendingApprovalId] = useState("");
  const [isBulkDecisionPending, setIsBulkDecisionPending] = useState(false);
  const [approvalNotes, setApprovalNotes] = useState<Record<string, string>>({});
  const [bulkApprovalNote, setBulkApprovalNote] = useState("");
  const [auditScope, setAuditScope] = useState<AuditScope>("project");
  const [approvalStatusFilter, setApprovalStatusFilter] =
    useState<ApprovalStatusFilter>("pending");
  const [auditLimit, setAuditLimit] = useState("6");

  const projectsQuery = useQuery({
    queryKey: ["projects", "agent-orchestration-picker"],
    enabled: canUseLiveApi,
    queryFn: () =>
      apiClient.get<PaginatedResponse<ProjectSummary>>(
        "/projects?page=1&page_size=20",
        { useMock: false },
      ),
  });

  useEffect(() => {
    if (currentProjectId) {
      setSelectedProjectId(currentProjectId);
    } else if (projectsQuery.data?.items?.length && !selectedProjectId) {
      setSelectedProjectId(projectsQuery.data.items[0].id);
    }
  }, [currentProjectId, projectsQuery.data?.items, selectedProjectId]);

  useEffect(() => {
    if (!manualProjectId.trim() && selectedProjectId) {
      setCurrentProject(selectedProjectId);
    }
  }, [manualProjectId, selectedProjectId, setCurrentProject]);

  const selectedProject =
    projectsQuery.data?.items?.find((project) => project.id === selectedProjectId) ??
    null;
  const activeProjectId = manualProjectId.trim() || selectedProject?.id || "";
  const resolvedAuditProjectId = auditScope === "project" ? activeProjectId : "";

  const buildHistoryPath = () => {
    const params = new URLSearchParams();
    if (resolvedAuditProjectId) {
      params.set("project_id", resolvedAuditProjectId);
    }
    params.set("limit", auditLimit);
    return `/agents/domain/history?${params.toString()}`;
  };

  const buildApprovalsPath = () => {
    const params = new URLSearchParams();
    if (resolvedAuditProjectId) {
      params.set("project_id", resolvedAuditProjectId);
    }
    params.set("limit", auditLimit);
    if (approvalStatusFilter !== "pending") {
      params.set("status", approvalStatusFilter);
    }
    return `/agents/domain/approvals?${params.toString()}`;
  };

  useEffect(() => {
    setApprovalActionError("");
    setPendingApprovalId("");
    setIsBulkDecisionPending(false);
    setApprovalNotes({});
    setBulkApprovalNote("");
  }, [activeProjectId, auditScope, approvalStatusFilter, auditLimit]);

  const historyQuery = useQuery({
    queryKey: ["agents", "domain", "history", resolvedAuditProjectId, auditLimit],
    enabled: canUseLiveApi && (auditScope === "tenant" || Boolean(activeProjectId)),
    queryFn: () =>
      apiClient.get<DomainAgentHistoryResponse>(buildHistoryPath(), { useMock: false }),
  });

  const approvalsQuery = useQuery({
    queryKey: [
      "agents",
      "domain",
      "approvals",
      resolvedAuditProjectId,
      approvalStatusFilter,
      auditLimit,
    ],
    enabled: canUseLiveApi && (auditScope === "tenant" || Boolean(activeProjectId)),
    queryFn: () =>
      apiClient.get<DomainAgentApprovalQueueResponse>(buildApprovalsPath(), {
        useMock: false,
      }),
  });
  const projectQueryError = projectsQuery.error
    ? extractErrorMessage(projectsQuery.error, labels.authError)
    : "";
  const historyQueryError = historyQuery.error
    ? extractErrorMessage(historyQuery.error, labels.authError)
    : "";
  const approvalsQueryError = approvalsQuery.error
    ? extractErrorMessage(approvalsQuery.error, labels.authError)
    : "";
  const pendingApprovalItems =
    approvalsQuery.data?.items?.filter((item) => item.status === "pending") ?? [];
  const requiredApprovals =
    portfolioResult?.items?.filter((item) => item.approval_required).length ?? 0;
  const projectQueryUi = PROJECT_QUERY_UI[locale] ?? PROJECT_QUERY_UI.en;

  const syncApprovalStatuses = (items: DomainAgentApprovalQueueItemResponse[]) => {
    if (items.length === 0) {
      return;
    }

    const statusByTaskId = new Map(
      items.map((item) => [item.task_id, item.status as ApprovalStatus]),
    );

    setFocusedResult((current) =>
      current && statusByTaskId.has(current.task_id)
        ? {
            ...current,
            approval_status: statusByTaskId.get(current.task_id) ?? current.approval_status,
          }
        : current,
    );
    setPortfolioResult((current) =>
      current
        ? {
            ...current,
            items: (current.items ?? []).map((item) =>
              statusByTaskId.has(item.task_id)
                ? {
                    ...item,
                    approval_status:
                      statusByTaskId.get(item.task_id) ?? item.approval_status,
                  }
                : item,
            ),
          }
        : current,
    );
  };

  const toggleDomain = (domain: DomainKey) => {
    setSelectedDomains((current) =>
      current.includes(domain)
        ? current.filter((value) => value !== domain)
        : [...current, domain],
    );
  };

  const getContextPayload = () => ({
    occupancy_rate: Number(contextValues.occupancyRate || 0),
    ltv: Number(contextValues.ltv || 0),
    schedule_buffer_months: Number(contextValues.scheduleBufferMonths || 0),
    pre_leasing_ratio: Number(contextValues.preLeasingRatio || 0),
  });

  const validateExecution = (requireDomains: boolean) => {
    if (!canUseLiveApi) {
      setWorkspaceError(labels.authError);
      return false;
    }

    if (!activeProjectId) {
      setWorkspaceError(labels.missingProjectError);
      return false;
    }

    if (requireDomains && selectedDomains.length === 0) {
      setWorkspaceError(labels.domainSelectionError);
      return false;
    }

    setWorkspaceError("");
    return true;
  };

  const handleFocusedRun = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!validateExecution(false)) {
      return;
    }

    setIsRunningFocused(true);

    try {
      const response = await apiClient.post<DomainAgentRunResponse>(
        "/agents/domain/run",
        {
          body: {
            project_id: activeProjectId,
            domain: focusedDomain,
            question,
            context: getContextPayload(),
            approval_role: approvalRole,
          },
          useMock: false,
        },
      );

      setFocusedResult(response);
      setCurrentProject(activeProjectId);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["agents", "domain", "history"] }),
        queryClient.invalidateQueries({ queryKey: ["agents", "domain", "approvals"] }),
      ]);
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsRunningFocused(false);
    }
  };

  const handlePortfolioRun = async () => {
    if (!validateExecution(true)) {
      return;
    }

    setIsRunningPortfolio(true);

    try {
      const response = await apiClient.post<DomainMultiAnalysisResponse>(
        "/agents/domain/multi-analysis",
        {
          body: {
            project_id: activeProjectId,
            domains: selectedDomains,
            question,
            context: getContextPayload(),
            approval_role: approvalRole,
          },
          useMock: false,
        },
      );

      setPortfolioResult(response);
      setCurrentProject(activeProjectId);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["agents", "domain", "history"] }),
        queryClient.invalidateQueries({ queryKey: ["agents", "domain", "approvals"] }),
      ]);
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsRunningPortfolio(false);
    }
  };

  const handleApprovalDecision = async (
    approvalId: string,
    taskId: string,
    decision: "approved" | "rejected",
  ) => {
    setApprovalActionError("");
    setPendingApprovalId(approvalId);

    try {
      const response = await apiClient.post<DomainAgentApprovalQueueItemResponse>(
        `/agents/domain/approvals/${approvalId}/decision`,
        {
          body: {
            decision,
            rationale:
              approvalNotes[approvalId]?.trim() ||
              (decision === "approved"
                ? "Approved in agent workspace."
                : "Rejected in agent workspace."),
          },
          useMock: false,
        },
      );

      syncApprovalStatuses([{ ...response, task_id: taskId }]);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["agents", "domain", "history"] }),
        queryClient.invalidateQueries({ queryKey: ["agents", "domain", "approvals"] }),
      ]);
      setApprovalNotes((current) => {
        const next = { ...current };
        delete next[approvalId];
        return next;
      });
    } catch (error) {
      setApprovalActionError(extractErrorMessage(error, labels.authError));
    } finally {
      setPendingApprovalId("");
    }
  };

  const handleBulkApprovalDecision = async (decision: "approved" | "rejected") => {
    if (auditScope !== "project" || !activeProjectId || pendingApprovalItems.length === 0) {
      setApprovalActionError("No pending approvals are available for bulk action.");
      return;
    }

    setApprovalActionError("");
    setIsBulkDecisionPending(true);

    try {
      const response = await apiClient.post<DomainAgentApprovalBatchDecisionResponse>(
        "/agents/domain/approvals/decision-batch",
        {
          body: {
            project_id: activeProjectId,
            approval_ids: pendingApprovalItems.map((item) => item.approval_id),
            decision,
            rationale:
              bulkApprovalNote.trim() ||
              (decision === "approved"
                ? "Approved all pending items in agent workspace."
                : "Rejected all pending items in agent workspace."),
          },
          useMock: false,
        },
      );

      syncApprovalStatuses(response.items);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["agents", "domain", "history"] }),
        queryClient.invalidateQueries({ queryKey: ["agents", "domain", "approvals"] }),
      ]);
      setBulkApprovalNote("");
      setApprovalNotes((current) => {
        const next = { ...current };
        for (const item of response.items) {
          delete next[item.approval_id];
        }
        return next;
      });
    } catch (error) {
      setApprovalActionError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsBulkDecisionPending(false);
    }
  };

  return (
    <section className="grid gap-5">
      <Card className="bg-[var(--surface-strong)]">
        <CardContent className="p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="max-w-3xl">
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.configurationTitle}
              </p>
              <CardTitle className="mt-3 text-2xl">{labels.heroTitle}</CardTitle>
              <p className="mt-4 text-sm leading-7 text-[var(--text-secondary)]">
                {labels.heroDescription}
              </p>
              <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                {labels.heroHint}
              </p>
            </div>
            {!canUseLiveApi && (
              <div className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4 text-sm leading-7 text-[var(--text-secondary)]">
                {labels.tokenHint}
              </div>
            )}
          </div>
          {!canUseLiveApi ? (
            <p className="mt-4 text-sm font-medium text-[var(--spot)]" role="alert">
              {labels.authError}
            </p>
          ) : null}
        </CardContent>
      </Card>

      {workspaceError ? (
        <Card className="border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] shadow-none">
          <CardContent className="p-5">
            <p className="text-sm font-semibold text-[var(--spot)]" role="alert">
              {workspaceError}
            </p>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[0.92fr_1.08fr]">
        <Card>
          <CardContent className="p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <CardTitle>{labels.projectTitle}</CardTitle>
                <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
                  {labels.projectHint}
                </p>
              </div>
              <span className="rounded-full border border-[var(--line)] px-3 py-1 text-xs font-medium text-[var(--text-secondary)]">
                {labels.currentProjectLabel}: {activeProjectId || "-"}
              </span>
            </div>
            <div className="mt-5 grid gap-4">
              {projectsQuery.isLoading ? (
                <SkeletonLoader count={2} itemClassName="h-12" />
              ) : null}
              {projectsQuery.isError ? (
                <WorkspaceQueryErrorCard
                  title={labels.projectLoadError}
                  description={projectQueryUi.detail}
                  message={projectQueryError}
                  actionLabel={projectQueryUi.retry}
                  onRetry={() => {
                    void projectsQuery.refetch();
                  }}
                />
              ) : null}
              <Select
                label={labels.projectSelectLabel}
                value={selectedProjectId}
                onValueChange={setSelectedProjectId}
                options={[
                  {
                    label:
                      projectsQuery.data?.items?.length && canUseLiveApi
                        ? labels.projectSelectLabel
                        : labels.noProjectsLabel,
                    value: "",
                    disabled: true,
                  },
                  ...(projectsQuery.data?.items ?? []).map((project) => ({
                    label: `${project.name} (${project.status})`,
                    value: project.id,
                  })),
                ]}
                disabled={!canUseLiveApi || !(projectsQuery.data?.items?.length ?? 0)}
              />
              <div className="grid gap-2">
                <label
                  className="text-sm font-medium text-[var(--text-secondary)]"
                  htmlFor="agent-manual-project-id"
                >
                  {labels.manualProjectIdLabel}
                </label>
                <Input
                  id="agent-manual-project-id"
                  value={manualProjectId}
                  onChange={(event) => setManualProjectId(event.target.value)}
                  placeholder="00000000-0000-0000-0000-000000000000"
                />
              </div>
              <div className="rounded-[1.35rem] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4 text-sm leading-7 text-[var(--text-secondary)]">
                <p className="font-medium text-[var(--text-primary)]">
                  {labels.currentProjectLabel}
                </p>
                <p className="mt-2">
                  {selectedProject?.name ??
                    (manualProjectId.trim() || labels.noProjectsLabel)}
                </p>
                <p className="mt-2 text-xs text-[var(--text-tertiary)]">
                  {labels.projectIdLabel}: {activeProjectId || "-"}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <form className="grid gap-5" onSubmit={handleFocusedRun}>
              <div>
                <CardTitle>{labels.configurationTitle}</CardTitle>
              </div>
              <div className="grid gap-2">
                <label
                  className="text-sm font-medium text-[var(--text-secondary)]"
                  htmlFor="agent-question"
                >
                  {labels.questionLabel}
                </label>
                <Input
                  id="agent-question"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                />
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <Select
                  label={labels.focusDomainLabel}
                  value={focusedDomain}
                  onValueChange={(value) => setFocusedDomain(value as DomainKey)}
                  options={DOMAIN_ORDER.map((domain) => ({
                    label: labels.domainLabels[domain],
                    value: domain,
                  }))}
                />
                <Select
                  label={labels.approvalRoleLabel}
                  value={approvalRole}
                  onValueChange={setApprovalRole}
                  options={labels.approvalRoleOptions}
                />
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="grid gap-2">
                  <label
                    className="text-sm font-medium text-[var(--text-secondary)]"
                    htmlFor="agent-occupancy"
                  >
                    {labels.occupancyRateLabel}
                  </label>
                  <Input
                    id="agent-occupancy"
                    type="number"
                    min="0"
                    max="1"
                    step="0.01"
                    value={contextValues.occupancyRate}
                    onChange={(event) =>
                      setContextValues((current) => ({
                        ...current,
                        occupancyRate: event.target.value,
                      }))
                    }
                  />
                </div>
                <div className="grid gap-2">
                  <label
                    className="text-sm font-medium text-[var(--text-secondary)]"
                    htmlFor="agent-ltv"
                  >
                    {labels.ltvLabel}
                  </label>
                  <Input
                    id="agent-ltv"
                    type="number"
                    min="0"
                    max="1"
                    step="0.01"
                    value={contextValues.ltv}
                    onChange={(event) =>
                      setContextValues((current) => ({
                        ...current,
                        ltv: event.target.value,
                      }))
                    }
                  />
                </div>
                <div className="grid gap-2">
                  <label
                    className="text-sm font-medium text-[var(--text-secondary)]"
                    htmlFor="agent-buffer"
                  >
                    {labels.scheduleBufferLabel}
                  </label>
                  <Input
                    id="agent-buffer"
                    type="number"
                    min="0"
                    step="1"
                    value={contextValues.scheduleBufferMonths}
                    onChange={(event) =>
                      setContextValues((current) => ({
                        ...current,
                        scheduleBufferMonths: event.target.value,
                      }))
                    }
                  />
                </div>
                <div className="grid gap-2">
                  <label
                    className="text-sm font-medium text-[var(--text-secondary)]"
                    htmlFor="agent-preleasing"
                  >
                    {labels.preLeasingLabel}
                  </label>
                  <Input
                    id="agent-preleasing"
                    type="number"
                    min="0"
                    max="1"
                    step="0.01"
                    value={contextValues.preLeasingRatio}
                    onChange={(event) =>
                      setContextValues((current) => ({
                        ...current,
                        preLeasingRatio: event.target.value,
                      }))
                    }
                  />
                </div>
              </div>
              <div>
                <p className="text-sm font-medium text-[var(--text-secondary)]">
                  {labels.orchestrationDomainsLabel}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {DOMAIN_ORDER.map((domain) => {
                    const selected = selectedDomains.includes(domain);

                    return (
                      <button
                        key={domain}
                        type="button"
                        aria-pressed={selected}
                        onClick={() => toggleDomain(domain)}
                        className={`rounded-full px-4 py-2 text-sm font-bold transition ${
                          selected
                            ? "bg-[var(--accent-strong)] text-white shadow-[var(--shadow-glow)]"
                            : "border border-[var(--line-strong)] bg-[var(--surface-soft)] text-[var(--text-secondary)] hover:border-[var(--text-secondary)]"
                        }`}
                      >
                        {labels.domainLabels[domain]}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div className="flex flex-wrap gap-3">
                <Button disabled={isRunningFocused} type="submit">
                  {labels.runFocusedAction}
                </Button>
                <Button
                  disabled={isRunningPortfolio}
                  onClick={handlePortfolioRun}
                  type="button"
                  variant="secondary"
                >
                  {labels.runOrchestrationAction}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="p-6">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
            {AUDIT_FILTER_UI.title}
          </p>
          <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
            {AUDIT_FILTER_UI.description}
          </p>
          <div className="mt-4 flex flex-wrap gap-3">
            <Select
              label={AUDIT_FILTER_UI.scopeLabel}
              value={auditScope}
              onValueChange={(value) => setAuditScope(value as AuditScope)}
              options={[...AUDIT_FILTER_UI.scopeOptions]}
            />
            <Select
              label={AUDIT_FILTER_UI.statusLabel}
              value={approvalStatusFilter}
              onValueChange={(value) =>
                setApprovalStatusFilter(value as ApprovalStatusFilter)
              }
              options={[...AUDIT_FILTER_UI.statusOptions]}
            />
            <Select
              label={AUDIT_FILTER_UI.limitLabel}
              value={auditLimit}
              onValueChange={setAuditLimit}
              options={[...AUDIT_FILTER_UI.limitOptions]}
            />
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardContent className="p-6">
            <CardTitle>{labels.focusedTitle}</CardTitle>
            {focusedResult ? (
              <div className="mt-5 grid gap-4">
                <div className="grid gap-2 rounded-[1.35rem] bg-[var(--surface-soft)] px-4 py-4 text-sm text-[var(--text-secondary)]">
                  <p>
                    {labels.projectIdLabel}: {focusedResult.project_id}
                  </p>
                  <p>
                    {labels.domainLabel}: {labels.domainLabels[focusedResult.domain]}
                  </p>
                  <p>
                    {labels.statusLabel}: {focusedResult.status}
                  </p>
                  <p>
                    {labels.confidenceLabel}:{" "}
                    {formatPercent(locale, focusedResult.confidence_score)}
                  </p>
                  <p>
                    {labels.recommendationLabel}:{" "}
                    {labels.recommendationLabels[focusedResult.recommendation]}
                  </p>
                  <p>
                    {labels.approvalLabel}:{" "}
                    {labels.approvalStatusLabels[focusedResult.approval_status]}
                  </p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                    {labels.findingsLabel}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {focusedResult.findings?.length ? (
                      (focusedResult.findings ?? []).map((finding) => (
                        <span
                          key={`${finding.factor}-${finding.impact}`}
                          className="rounded-full border border-[var(--line)] px-3 py-1 text-xs font-medium text-[var(--text-secondary)]"
                        >
                          {[finding.factor, finding.impact].filter(Boolean).join(": ")}
                        </span>
                      ))
                    ) : (
                      <span className="text-sm text-[var(--text-tertiary)]">
                        {labels.noFindingsLabel}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <p className="mt-4 text-sm leading-7 text-[var(--text-secondary)]">
                {labels.focusedEmpty}
              </p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-6">
            <CardTitle>{labels.portfolioTitle}</CardTitle>
            {portfolioResult ? (
              <div className="mt-5 grid gap-4">
                <div className="grid gap-3 rounded-[1.35rem] bg-[var(--surface-soft)] px-4 py-4 text-sm text-[var(--text-secondary)] md:grid-cols-2">
                  <p>
                    {labels.portfolioSummaryLabel}: {portfolioResult.portfolio_summary}
                  </p>
                  <p>
                    {labels.totalRunsLabel}: {portfolioResult.items?.length}
                  </p>
                  <p>
                    {labels.approvalsRequiredLabel}: {requiredApprovals}
                  </p>
                  <p>
                    {labels.projectIdLabel}: {activeProjectId}
                  </p>
                </div>
                <ol className="grid gap-3">
                  {(portfolioResult.items ?? []).map((item) => (
                    <li
                      key={item.task_id}
                      className="rounded-[1.35rem] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-[var(--text-primary)]">
                            {labels.domainLabels[item.domain]}
                          </p>
                          <p className="mt-2 text-sm text-[var(--text-secondary)]">
                            {labels.recommendationLabel}:{" "}
                            {labels.recommendationLabels[item.recommendation]}
                          </p>
                        </div>
                        <span className="rounded-full border border-[var(--line)] px-3 py-1 text-xs font-medium text-[var(--text-secondary)]">
                          {formatPercent(locale, item.confidence_score)}
                        </span>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2 text-xs text-[var(--text-secondary)]">
                        <span className="rounded-full bg-[var(--surface-muted)] border border-[var(--line-strong)]/40 px-3 py-1 text-[11px]">
                          {labels.statusLabel}: {item.status}
                        </span>
                        <span className="rounded-full bg-[var(--surface-muted)] border border-[var(--line-strong)]/40 px-3 py-1 text-[11px]">
                          {labels.approvalLabel}:{" "}
                          {labels.approvalStatusLabels[item.approval_status]}
                        </span>
                      </div>
                    </li>
                  ))}
                </ol>
              </div>
            ) : (
              <p className="mt-4 text-sm leading-7 text-[var(--text-secondary)]">
                {labels.portfolioEmpty}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardContent className="p-6">
            <CardTitle>{readUi.historyTitle}</CardTitle>
            {historyQuery.isLoading ? (
              <div className="mt-5">
                <SkeletonLoader count={2} itemClassName="h-24" />
              </div>
            ) : null}
            {historyQuery.isError ? (
              <div className="mt-5">
                <WorkspaceQueryErrorCard
                  title={readUi.historyErrorTitle}
                  description={readUi.historyErrorDetail}
                  message={historyQueryError}
                  actionLabel={readUi.retry}
                  onRetry={() => {
                    void historyQuery.refetch();
                  }}
                />
              </div>
            ) : null}
            {historyQuery.data?.items?.length ? (
              <ol className="mt-5 grid gap-3">
                {(historyQuery.data.items ?? []).map((item) => (
                  <li
                    key={item.task_id}
                    className="rounded-[1.35rem] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-[var(--text-primary)]">
                          {labels.domainLabels[item.domain]}
                        </p>
                        <p className="mt-2 text-sm text-[var(--text-secondary)]">
                          {labels.recommendationLabel}:{" "}
                          {labels.recommendationLabels[item.recommendation]}
                        </p>
                      </div>
                      <span className="rounded-full border border-[var(--line)] px-3 py-1 text-xs font-medium text-[var(--text-secondary)]">
                        {formatPercent(locale, item.confidence_score)}
                      </span>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-[var(--text-secondary)]">
                      <span className="rounded-full bg-[var(--surface-muted)] border border-[var(--line-strong)]/40 px-3 py-1 text-[11px]">
                        {labels.statusLabel}: {item.status}
                      </span>
                      <span className="rounded-full bg-[var(--surface-muted)] border border-[var(--line-strong)]/40 px-3 py-1 text-[11px]">
                        {labels.approvalLabel}:{" "}
                        {labels.approvalStatusLabels[item.approval_status]}
                      </span>
                      <span className="rounded-full bg-[var(--surface-muted)] border border-[var(--line-strong)]/40 px-3 py-1 text-[11px]">
                        {labels.projectIdLabel}: {item.project_id}
                      </span>
                      <span className="rounded-full bg-[var(--surface-muted)] border border-[var(--line-strong)]/40 px-3 py-1 text-[11px]">
                        {readUi.createdLabel}: {new Date(item.created_at).toLocaleString(locale)}
                      </span>
                    </div>
                    {item.narrative ? (
                      <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                        {readUi.narrativeLabel}: {item.narrative}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ol>
            ) : !historyQuery.isLoading && !historyQuery.isError ? (
              <p className="mt-4 text-sm leading-7 text-[var(--text-secondary)]">
                {readUi.historyEmpty}
              </p>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <CardTitle>{readUi.approvalTitle}</CardTitle>
            {approvalActionError ? (
              <p className="mt-4 text-sm font-medium text-[var(--spot)]" role="alert">
                {approvalActionError}
              </p>
            ) : null}
            {approvalsQuery.isLoading ? (
              <div className="mt-5">
                <SkeletonLoader count={2} itemClassName="h-24" />
              </div>
            ) : null}
            {approvalsQuery.isError ? (
              <div className="mt-5">
                <WorkspaceQueryErrorCard
                  title={readUi.approvalErrorTitle}
                  description={readUi.approvalErrorDetail}
                  message={approvalsQueryError}
                  actionLabel={readUi.retry}
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
              <div className="mt-5 rounded-[1.35rem] border border-[var(--line-strong)] bg-[var(--surface-soft)]/80 backdrop-blur-md px-4 py-4">
                <p className="text-sm font-semibold text-[var(--text-primary)]">
                  {APPROVAL_DECISION_UI.bulkTitle}
                </p>
                <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
                  {APPROVAL_DECISION_UI.bulkDescription}
                </p>
                <p className="mt-3 text-xs uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
                  {APPROVAL_DECISION_UI.pendingCountLabel}: {pendingApprovalItems.length}
                </p>
                <label
                  className="mt-4 grid gap-2 text-sm font-medium text-[var(--text-secondary)]"
                  htmlFor="bulk-approval-note"
                >
                  <span>{APPROVAL_DECISION_UI.bulkLabel}</span>
                  <textarea
                    id="bulk-approval-note"
                    value={bulkApprovalNote}
                    onChange={(event) => setBulkApprovalNote(event.target.value)}
                    disabled={isBulkDecisionPending || Boolean(pendingApprovalId)}
                    placeholder={APPROVAL_DECISION_UI.bulkPlaceholder}
                    className="min-h-20 rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--text-primary)] outline-none transition placeholder:text-[var(--text-hint)] focus:border-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-60"
                  />
                </label>
                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={isBulkDecisionPending || Boolean(pendingApprovalId)}
                    onClick={() => void handleBulkApprovalDecision("approved")}
                    className="rounded-full bg-[var(--foreground)] px-4 py-2 text-sm font-medium text-white transition disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {APPROVAL_DECISION_UI.approveAllAction}
                  </button>
                  <button
                    type="button"
                    disabled={isBulkDecisionPending || Boolean(pendingApprovalId)}
                    onClick={() => void handleBulkApprovalDecision("rejected")}
                    className="rounded-full border border-[var(--line)] bg-[var(--surface)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] transition disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {APPROVAL_DECISION_UI.rejectAllAction}
                  </button>
                </div>
              </div>
            ) : null}
            {approvalsQuery.data?.items?.length ? (
              <ol className="mt-5 grid gap-3">
                {(approvalsQuery.data.items ?? []).map((item) => (
                  <li
                    key={item.approval_id}
                    className="rounded-[1.35rem] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-[var(--text-primary)]">
                          {labels.domainLabels[item.domain]}
                        </p>
                        <p className="mt-2 text-sm text-[var(--text-secondary)]">
                          {labels.recommendationLabel}:{" "}
                          {labels.recommendationLabels[item.recommendation]}
                        </p>
                      </div>
                      <span className="rounded-full border border-[var(--line)] px-3 py-1 text-xs font-medium text-[var(--text-secondary)]">
                        {labels.approvalStatusLabels[item.status as ApprovalStatus] ??
                          item.status}
                      </span>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-[var(--text-secondary)]">
                      <span className="rounded-full bg-[var(--surface-muted)] border border-[var(--line-strong)]/40 px-3 py-1 text-[11px]">
                        {readUi.approverRoleLabel}: {item.approver_role}
                      </span>
                      <span className="rounded-full bg-[var(--surface-muted)] border border-[var(--line-strong)]/40 px-3 py-1 text-[11px]">
                        {labels.projectIdLabel}: {item.project_id}
                      </span>
                      <span className="rounded-full bg-[var(--surface-muted)] border border-[var(--line-strong)]/40 px-3 py-1 text-[11px]">
                        {readUi.createdLabel}: {new Date(item.created_at).toLocaleString(locale)}
                      </span>
                      {item.decided_at ? (
                        <span className="rounded-full bg-[var(--surface-muted)] border border-[var(--line-strong)]/40 px-3 py-1 text-[11px]">
                          {AUDIT_FILTER_UI.decidedLabel}:{" "}
                          {new Date(item.decided_at).toLocaleString(locale)}
                        </span>
                      ) : null}
                    </div>
                    {item.rationale ? (
                      <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                        {readUi.rationaleLabel}: {item.rationale}
                      </p>
                    ) : null}
                    {item.status === "pending" ? (
                      <>
                        <label
                          className="mt-4 grid gap-2 text-sm font-medium text-[var(--text-secondary)]"
                          htmlFor={`approval-note-${item.approval_id}`}
                        >
                          <span>{APPROVAL_DECISION_UI.itemLabel}</span>
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
                            placeholder={APPROVAL_DECISION_UI.itemPlaceholder}
                            className="min-h-20 rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--text-primary)] outline-none transition placeholder:text-[var(--text-hint)] focus:border-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-60"
                          />
                        </label>
                        <div className="mt-4 flex flex-wrap gap-2">
                          <button
                            type="button"
                            disabled={
                              pendingApprovalId === item.approval_id || isBulkDecisionPending
                            }
                            onClick={() =>
                              void handleApprovalDecision(
                                item.approval_id,
                                item.task_id,
                                "approved",
                              )
                            }
                            className="rounded-full bg-[var(--foreground)] px-4 py-2 text-sm font-medium text-white transition disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {readUi.approveAction}
                          </button>
                          <button
                            type="button"
                            disabled={
                              pendingApprovalId === item.approval_id || isBulkDecisionPending
                            }
                            onClick={() =>
                              void handleApprovalDecision(
                                item.approval_id,
                                item.task_id,
                                "rejected",
                              )
                            }
                            className="rounded-full border border-[var(--line)] bg-[var(--surface)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] transition disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {readUi.rejectAction}
                          </button>
                        </div>
                      </>
                    ) : null}
                  </li>
                ))}
              </ol>
            ) : !approvalsQuery.isLoading && !approvalsQuery.isError ? (
              <p className="mt-4 text-sm leading-7 text-[var(--text-secondary)]">
                {readUi.approvalEmpty}
              </p>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
