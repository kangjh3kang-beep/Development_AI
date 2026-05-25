"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Button,
  Card,
  CardContent,
  CardTitle,
  Input,
  Select,
} from "@propai/ui";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { ApiClientError, apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";

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

type AICostBreakdownItem = {
  service_name: string;
  model_name: string;
  request_count: number;
  total_tokens: number;
  total_cost_usd: number;
};

type AICostDashboardResponse = {
  month: string;
  total_cost_usd: number;
  total_tokens: number;
  by_service: AICostBreakdownItem[];
};

type AICostBudgetResponse = {
  budget_id: string;
  endpoint: string;
  month: string;
  monthly_budget_usd: number;
  alert_threshold_ratio: number;
  created_at: string;
};

type AIBudgetGateResponse = {
  endpoint: string;
  monthly_budget_usd: number;
  current_cost_usd: number;
  remaining_budget_usd: number;
  allowed: boolean;
};

type PortalPostResponse = {
  listing_id: string;
  project_id: string;
  portal_name: string;
  listing_external_id: string;
  listing_url: string | null;
  status: string;
  view_count: number;
  inquiry_count: number;
  created_at: string;
};

type PortalBatchPostResponse = {
  items: PortalPostResponse[];
  success_count: number;
};

type PortalMarketPortal = {
  portal_name: string;
  listing_count: number;
  average_inquiry_count: number;
};

type PortalMarketDataResponse = {
  region_code: string;
  active_listing_count: number;
  average_price_krw: number;
  average_area_sqm: number;
  average_inquiry_count: number;
  top_portals: PortalMarketPortal[];
};

type InvestorReportVariant = {
  report_id: string;
  target_language: string;
  title: string;
  quality_score: number | null;
  translated_text: string;
};

type InvestorReportResponse = {
  project_id: string;
  report_type: string;
  variants: InvestorReportVariant[];
  generated_sections: string[];
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
  manualProjectNameLabel: string;
  selectedProjectLabel: string;
  aiCostsTitle: string;
  aiCostsEmpty: string;
  budgetTitle: string;
  budgetEndpointLabel: string;
  budgetAmountLabel: string;
  budgetThresholdLabel: string;
  saveBudgetAction: string;
  reportsTitle: string;
  reportsLanguagesLabel: string;
  reportsHighlightsLabel: string;
  reportsRisksLabel: string;
  reportsSectionsLabel: string;
  generateReportAction: string;
  portalsTitle: string;
  marketTitle: string;
  regionCodeLabel: string;
  propertyTypeLabel: string;
  priceLabel: string;
  areaLabel: string;
  titleLabel: string;
  descriptionLabel: string;
  portalsLabel: string;
  publishAction: string;
  authError: string;
  missingProjectError: string;
  monthLabel: string;
  totalCostLabel: string;
  totalTokensLabel: string;
  trackedServicesLabel: string;
  remainingBudgetLabel: string;
  portalViewsLabel: string;
  portalInquiriesLabel: string;
  reportQualityLabel: string;
  generatedSectionsLabel: string;
  noProjectsLabel: string;
  projectLoadErrorTitle: string;
  projectLoadErrorDetail: string;
  aiCostsLoadErrorTitle: string;
  aiCostsLoadErrorDetail: string;
  marketLoadErrorTitle: string;
  marketLoadErrorDetail: string;
  retryAction: string;
  listingsLabel: string;
  avgPriceLabel: string;
  avgAreaLabel: string;
  requestsLabel: string;
  tokensLabel: string;
};

const LABELS: Record<Locale, Labels> = {
  ko: {
    heroTitle: "투자 운영 컨트롤타워",
    heroDescription:
      "AI 비용, 투자자 다국어 리포트, 포털 게재를 실제 Part G API에 연결해 검증합니다.",
    heroHint:
      "프로젝트 FK가 필요한 작업은 live 프로젝트를 선택하거나 실제 UUID를 직접 입력해야 합니다.",
    tokenHint:
      "실 API 호출에는 `NEXT_PUBLIC_API_ACCESS_TOKEN` 또는 `localStorage.propai_access_token`이 필요합니다.",
    projectTitle: "프로젝트 컨텍스트",
    projectHint:
      "라이브 프로젝트를 불러와 선택하거나, 기존 프로젝트 UUID를 직접 지정할 수 있습니다.",
    projectSelectLabel: "라이브 프로젝트",
    manualProjectIdLabel: "수동 프로젝트 UUID",
    manualProjectNameLabel: "수동 프로젝트명",
    selectedProjectLabel: "현재 컨텍스트",
    aiCostsTitle: "AI 비용 현황",
    aiCostsEmpty: "이번 달 집계된 AI 사용 로그가 없습니다.",
    budgetTitle: "예산 게이트 설정",
    budgetEndpointLabel: "대상 엔드포인트",
    budgetAmountLabel: "월 예산(USD)",
    budgetThresholdLabel: "경보 비율",
    saveBudgetAction: "예산 저장",
    reportsTitle: "투자자 리포트 생성",
    reportsLanguagesLabel: "대상 언어(쉼표 구분)",
    reportsHighlightsLabel: "투자 포인트",
    reportsRisksLabel: "리스크 포인트",
    reportsSectionsLabel: "포함 섹션",
    generateReportAction: "리포트 생성",
    portalsTitle: "포털 게재 실행",
    marketTitle: "권역 시장 데이터",
    regionCodeLabel: "권역 코드",
    propertyTypeLabel: "자산 유형",
    priceLabel: "호가(원)",
    areaLabel: "면적(㎡)",
    titleLabel: "게재 제목",
    descriptionLabel: "게재 설명",
    portalsLabel: "포털 목록",
    publishAction: "일괄 게재",
    authError: "실시간 호출을 위해 API 인증이 필요합니다.",
    missingProjectError: "실존 프로젝트 UUID와 프로젝트명이 모두 필요합니다.",
    monthLabel: "집계 월",
    totalCostLabel: "총 비용",
    totalTokensLabel: "총 토큰",
    trackedServicesLabel: "추적 서비스",
    remainingBudgetLabel: "잔여 예산",
    portalViewsLabel: "조회수",
    portalInquiriesLabel: "문의수",
    reportQualityLabel: "품질 점수",
    generatedSectionsLabel: "생성 섹션",
    noProjectsLabel:
      "라이브 프로젝트가 아직 없습니다. 생성된 UUID를 알고 있다면 직접 입력하면 됩니다.",
    projectLoadErrorTitle: "프로젝트 로드 실패",
    projectLoadErrorDetail:
      "프로젝트 선택 목록을 불러오지 못했습니다. 수동 UUID 입력은 계속 사용할 수 있습니다.",
    aiCostsLoadErrorTitle: "AI 비용 집계 실패",
    aiCostsLoadErrorDetail:
      "실시간 비용 대시보드를 가져오지 못했습니다. 예산 저장 이후 다시 새로고침할 수 있습니다.",
    marketLoadErrorTitle: "시장 데이터 로드 실패",
    marketLoadErrorDetail:
      "선택한 권역의 포털 시장 데이터를 불러오지 못했습니다. 권역 코드를 유지한 채 재시도할 수 있습니다.",
    retryAction: "다시 시도",
    listingsLabel: "등록 수",
    avgPriceLabel: "평균 호가",
    avgAreaLabel: "평균 면적",
    requestsLabel: "요청",
    tokensLabel: "토큰",
  },
  en: {
    heroTitle: "Investment operations control tower",
    heroDescription:
      "Connect AI costs, multilingual investor reports, and portal posting to the live Part G APIs.",
    heroHint:
      "Project-linked actions require a live project selection or a real existing project UUID.",
    tokenHint:
      "Live API calls require `NEXT_PUBLIC_API_ACCESS_TOKEN` or `localStorage.propai_access_token`.",
    projectTitle: "Project context",
    projectHint:
      "Load live projects for selection or enter an existing project UUID manually.",
    projectSelectLabel: "Live project",
    manualProjectIdLabel: "Manual project UUID",
    manualProjectNameLabel: "Manual project name",
    selectedProjectLabel: "Current context",
    aiCostsTitle: "AI cost dashboard",
    aiCostsEmpty: "No AI usage has been recorded for the current month.",
    budgetTitle: "Budget gate setup",
    budgetEndpointLabel: "Endpoint",
    budgetAmountLabel: "Monthly budget (USD)",
    budgetThresholdLabel: "Alert ratio",
    saveBudgetAction: "Save budget",
    reportsTitle: "Generate investor report",
    reportsLanguagesLabel: "Target languages (comma separated)",
    reportsHighlightsLabel: "Investment highlights",
    reportsRisksLabel: "Risk factors",
    reportsSectionsLabel: "Included sections",
    generateReportAction: "Generate report",
    portalsTitle: "Publish to portals",
    marketTitle: "Regional market data",
    regionCodeLabel: "Region code",
    propertyTypeLabel: "Property type",
    priceLabel: "Asking price (KRW)",
    areaLabel: "Area (sqm)",
    titleLabel: "Listing title",
    descriptionLabel: "Listing description",
    portalsLabel: "Portal list",
    publishAction: "Publish batch",
    authError: "API authentication is required for live workspace calls.",
    missingProjectError: "A real project UUID and project name are both required.",
    monthLabel: "Month",
    totalCostLabel: "Total cost",
    totalTokensLabel: "Total tokens",
    trackedServicesLabel: "Tracked services",
    remainingBudgetLabel: "Remaining budget",
    portalViewsLabel: "Views",
    portalInquiriesLabel: "Inquiries",
    reportQualityLabel: "Quality score",
    generatedSectionsLabel: "Generated sections",
    noProjectsLabel:
      "No live projects are available yet. You can still enter a known project UUID manually.",
    projectLoadErrorTitle: "Project list unavailable",
    projectLoadErrorDetail:
      "The live project picker could not be loaded. Manual UUID targeting remains available.",
    aiCostsLoadErrorTitle: "AI cost dashboard unavailable",
    aiCostsLoadErrorDetail:
      "The live AI cost aggregates failed to load. You can retry after saving a budget gate.",
    marketLoadErrorTitle: "Market data unavailable",
    marketLoadErrorDetail:
      "Regional portal market data failed to load. Retry with the current region code.",
    retryAction: "Retry",
    listingsLabel: "Listings",
    avgPriceLabel: "Avg. price",
    avgAreaLabel: "Avg. area",
    requestsLabel: "requests",
    tokensLabel: "tokens",
  },
  "zh-CN": {
    heroTitle: "投资运营控制台",
    heroDescription:
      "将 AI 成本、多语言投资者报告和门户发布直接绑定到 Part G 实时 API。",
    heroHint:
      "带项目外键的操作需要选择实时项目，或手动输入真实存在的项目 UUID。",
    tokenHint:
      "实时 API 调用需要 `NEXT_PUBLIC_API_ACCESS_TOKEN` 或 `localStorage.propai_access_token`。",
    projectTitle: "项目上下文",
    projectHint: "可加载实时项目进行选择，也可手动输入已有项目 UUID。",
    projectSelectLabel: "实时项目",
    manualProjectIdLabel: "手动项目 UUID",
    manualProjectNameLabel: "手动项目名称",
    selectedProjectLabel: "当前上下文",
    aiCostsTitle: "AI 成本看板",
    aiCostsEmpty: "本月尚无 AI 使用记录。",
    budgetTitle: "预算闸门设置",
    budgetEndpointLabel: "目标接口",
    budgetAmountLabel: "月预算（USD）",
    budgetThresholdLabel: "预警比例",
    saveBudgetAction: "保存预算",
    reportsTitle: "生成投资者报告",
    reportsLanguagesLabel: "目标语言（逗号分隔）",
    reportsHighlightsLabel: "投资亮点",
    reportsRisksLabel: "风险因素",
    reportsSectionsLabel: "包含章节",
    generateReportAction: "生成报告",
    portalsTitle: "门户批量发布",
    marketTitle: "区域市场数据",
    regionCodeLabel: "区域代码",
    propertyTypeLabel: "资产类型",
    priceLabel: "报价（韩元）",
    areaLabel: "面积（平方米）",
    titleLabel: "发布标题",
    descriptionLabel: "发布说明",
    portalsLabel: "门户列表",
    publishAction: "批量发布",
    authError: "实时调用需要 API 身份认证。",
    missingProjectError: "必须提供真实项目 UUID 和项目名称。",
    monthLabel: "统计月份",
    totalCostLabel: "总成本",
    totalTokensLabel: "总 Token",
    trackedServicesLabel: "服务数",
    remainingBudgetLabel: "剩余预算",
    portalViewsLabel: "浏览量",
    portalInquiriesLabel: "咨询量",
    reportQualityLabel: "质量评分",
    generatedSectionsLabel: "生成章节",
    noProjectsLabel: "当前还没有实时项目。若已知真实项目 UUID，可直接手动输入。",
    projectLoadErrorTitle: "项目列表不可用",
    projectLoadErrorDetail:
      "无法加载实时项目选择列表，但仍可继续手动输入项目 UUID。",
    aiCostsLoadErrorTitle: "AI 成本看板不可用",
    aiCostsLoadErrorDetail:
      "实时 AI 成本聚合加载失败。保存预算闸门后可再次重试。",
    marketLoadErrorTitle: "市场数据不可用",
    marketLoadErrorDetail:
      "无法加载当前区域的门户市场数据，可保留区域代码后重试。",
    retryAction: "重试",
    listingsLabel: "列表数量",
    avgPriceLabel: "平均价格",
    avgAreaLabel: "平均面积",
    requestsLabel: "请求次数",
    tokensLabel: "Token数",
  },
};

const PROPERTY_TYPE_OPTIONS = [
  { label: "Mixed Use", value: "mixed_use" },
  { label: "Office", value: "office" },
  { label: "Residential", value: "residential" },
  { label: "Logistics", value: "logistics" },
];

function formatCurrency(locale: string, value: number, currency: string) {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    maximumFractionDigits: currency === "USD" ? 2 : 0,
  }).format(value);
}

function formatDate(locale: string, value: string) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function splitCommaValues(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
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

export function InvestmentOperationsWorkspaceClient({
  locale,
}: {
  locale: Locale;
}) {
  const [isMounted, setIsMounted] = useState(false);
  const labels = LABELS[locale];

  useEffect(() => {
    setIsMounted(true);
  }, []);

  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [manualProjectId, setManualProjectId] = useState("");
  const [manualProjectName, setManualProjectName] = useState("");
  const [workspaceError, setWorkspaceError] = useState("");
  const [savedBudget, setSavedBudget] = useState<AICostBudgetResponse | null>(null);
  const [budgetGate, setBudgetGate] = useState<AIBudgetGateResponse | null>(null);
  const [generatedReport, setGeneratedReport] =
    useState<InvestorReportResponse | null>(null);
  const [publishedListings, setPublishedListings] =
    useState<PortalBatchPostResponse | null>(null);
  const [isSavingBudget, setIsSavingBudget] = useState(false);
  const [isGeneratingReport, setIsGeneratingReport] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);

  const [budgetForm, setBudgetForm] = useState({
    endpoint: "reports/investor/generate",
    monthlyBudgetUsd: "150",
    alertThresholdRatio: "0.8",
  });
  const [reportForm, setReportForm] = useState({
    assetType: "mixed_use",
    targetLanguages: "ko,en,ja",
    highlights: "역세권 수요, 리포지셔닝 업사이드, 안정적 현금흐름",
    risks: "공사비 상승, 인허가 지연",
    includeSections: "executive-summary,market,financials,esg,risks",
  });
  const [portalForm, setPortalForm] = useState({
    regionCode: "11-680",
    propertyType: "mixed_use",
    priceKrw: "12500000000",
    areaSqm: "",
    title: "홍대 복합자산 투자 기회",
    description:
      "핵심 상권 접근성과 리포지셔닝 여력이 높은 복합 개발 자산입니다.",
    portals: "naver,zigbang,dabang",
  });

  const projectsQuery = useQuery({
    queryKey: ["projects", "live-picker"],
    enabled: canUseLiveApi,
    queryFn: () =>
      apiClient.get<PaginatedResponse<ProjectSummary>>(
        "/projects?page=1&page_size=20",
        { useMock: false },
      ),
  });

  const aiCostsQuery = useQuery({
    queryKey: ["ai-costs", "dashboard"],
    enabled: canUseLiveApi,
    queryFn: () =>
      apiClient.get<AICostDashboardResponse>("/ai-costs/dashboard", {
        useMock: false,
      }),
  });

  const marketDataQuery = useQuery({
    queryKey: ["portals", "market-data", portalForm.regionCode],
    enabled: canUseLiveApi && portalForm.regionCode.trim().length > 0,
    queryFn: () =>
      apiClient.get<PortalMarketDataResponse>(
        `/portals/market-data/${encodeURIComponent(portalForm.regionCode.trim())}`,
        { useMock: false },
      ),
  });

  useEffect(() => {
    if (!selectedProjectId && projectsQuery.data?.items.length) {
      setSelectedProjectId(projectsQuery.data.items[0].id);
    }
  }, [projectsQuery.data, selectedProjectId]);

  const selectedProject =
    projectsQuery.data?.items.find((project) => project.id === selectedProjectId) ??
    null;

  useEffect(() => {
    if (selectedProject?.total_area_sqm && !portalForm.areaSqm) {
      setPortalForm((current) => ({
        ...current,
        areaSqm: String(selectedProject.total_area_sqm),
      }));
    }
  }, [portalForm.areaSqm, selectedProject]);

  const activeProjectId = manualProjectId.trim() || selectedProject?.id || "";
  const activeProjectName =
    manualProjectName.trim() || selectedProject?.name || "";
  const projectQueryError = projectsQuery.error
    ? extractErrorMessage(projectsQuery.error, labels.authError)
    : "";
  const aiCostsQueryError = aiCostsQuery.error
    ? extractErrorMessage(aiCostsQuery.error, labels.authError)
    : "";
  const marketDataQueryError = marketDataQuery.error
    ? extractErrorMessage(marketDataQuery.error, labels.authError)
    : "";

  async function handleSaveBudget(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");
    setIsSavingBudget(true);

    const endpoint = budgetForm.endpoint.trim().replace(/^\/+/, "");

    try {
      const budget = await apiClient.post<AICostBudgetResponse>(
        "/ai-costs/budget",
        {
          useMock: false,
          body: {
            endpoint,
            monthly_budget_usd: Number(budgetForm.monthlyBudgetUsd),
            alert_threshold_ratio: Number(budgetForm.alertThresholdRatio),
          },
        },
      );
      const gate = await apiClient.get<AIBudgetGateResponse>(
        `/ai-costs/budget-gate/${endpoint}`,
        { useMock: false },
      );
      setSavedBudget(budget);
      setBudgetGate(gate);
      await aiCostsQuery.refetch();
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsSavingBudget(false);
    }
  }

  async function handleGenerateReport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");

    if (!activeProjectId || !activeProjectName) {
      setWorkspaceError(labels.missingProjectError);
      return;
    }

    setIsGeneratingReport(true);

    try {
      const result = await apiClient.post<InvestorReportResponse>(
        "/reports/investor/generate",
        {
          useMock: false,
          body: {
            project_id: activeProjectId,
            project_name: activeProjectName,
            asset_type: reportForm.assetType,
            target_languages: splitCommaValues(reportForm.targetLanguages),
            investment_highlights: splitCommaValues(reportForm.highlights),
            risks: splitCommaValues(reportForm.risks),
            include_sections: splitCommaValues(reportForm.includeSections),
          },
        },
      );
      setGeneratedReport(result);
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsGeneratingReport(false);
    }
  }

  async function handlePublishPortals(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");

    if (!activeProjectId || !activeProjectName) {
      setWorkspaceError(labels.missingProjectError);
      return;
    }

    setIsPublishing(true);

    try {
      const result = await apiClient.post<PortalBatchPostResponse>(
        "/portals/post-all",
        {
          useMock: false,
          body: {
            project_id: activeProjectId,
            project_name: activeProjectName,
            region_code: portalForm.regionCode.trim(),
            property_type: portalForm.propertyType,
            price_krw: Number(portalForm.priceKrw),
            area_sqm: Number(portalForm.areaSqm),
            title: portalForm.title.trim(),
            description: portalForm.description.trim(),
            portals: splitCommaValues(portalForm.portals),
            images: [],
          },
        },
      );
      setPublishedListings(result);
      await marketDataQuery.refetch();
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsPublishing(false);
    }
  }

  if (!isMounted) {
    return <SkeletonLoader count={5} />;
  }

  return (
    <section className="grid gap-6">
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
          {!canUseLiveApi ? (
            <div className="mt-6 rounded-[var(--radius-xl)] border border-dashed border-[var(--line)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
              {labels.authError}
            </div>
          ) : null}
          {workspaceError ? (
            <div className="mt-6 rounded-[var(--radius-xl)] border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] p-5 text-sm leading-7 text-[var(--spot)]">
              {workspaceError}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="grid gap-5 p-6 lg:grid-cols-[1.3fr_0.7fr]">
          <div className="grid gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.projectTitle}
              </p>
              <CardTitle className="mt-2 text-xl">{labels.projectHint}</CardTitle>
            </div>
            {projectsQuery.isLoading ? (
              <SkeletonLoader count={1} itemClassName="h-14" />
            ) : (
              <div className="grid gap-3">
                {projectsQuery.isError ? (
                  <WorkspaceQueryErrorCard
                    title={labels.projectLoadErrorTitle}
                    description={labels.projectLoadErrorDetail}
                    message={projectQueryError}
                    actionLabel={labels.retryAction}
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
                        projectsQuery.data?.items.length
                          ? labels.projectSelectLabel
                          : labels.noProjectsLabel,
                      value: "",
                      disabled: true,
                    },
                    ...(projectsQuery.data?.items.map((project) => ({
                      label: project.name,
                      value: project.id,
                    })) ?? []),
                  ]}
                />
              </div>
            )}
            <div className="grid gap-3 md:grid-cols-2">
              <Input
                value={manualProjectId}
                onChange={(event) => setManualProjectId(event.target.value)}
                placeholder={labels.manualProjectIdLabel}
              />
              <Input
                value={manualProjectName}
                onChange={(event) => setManualProjectName(event.target.value)}
                placeholder={labels.manualProjectNameLabel}
              />
            </div>
          </div>
          <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.selectedProjectLabel}
            </p>
            <p className="mt-3 text-sm font-semibold text-[var(--text-primary)]">
              {activeProjectName || "-"}
            </p>
            <p className="mt-2 break-all text-xs text-[var(--text-tertiary)]">
              {activeProjectId || "-"}
            </p>
            {selectedProject?.address ? (
              <p className="mt-3 text-sm text-[var(--text-secondary)]">
                {selectedProject.address}
              </p>
            ) : null}
            {selectedProject ? (
              <p className="mt-2 text-xs text-[var(--text-tertiary)]">
                {selectedProject.status} ·{" "}
                {formatDate(locale, selectedProject.updated_at)}
              </p>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <Card>
          <CardContent className="p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                  {labels.aiCostsTitle}
                </p>
                <CardTitle className="mt-2 text-xl">
                  {aiCostsQuery.data?.month ?? labels.monthLabel}
                </CardTitle>
              </div>
              <span className="rounded-full bg-[var(--surface-soft)] px-3 py-1 text-xs font-medium text-[var(--accent-strong)]">
                {aiCostsQuery.data?.by_service.length ?? 0}
              </span>
            </div>

            {aiCostsQuery.isLoading ? (
              <div className="mt-5">
                <SkeletonLoader count={3} itemClassName="h-24" />
              </div>
            ) : null}

            {aiCostsQuery.isError ? (
              <div className="mt-5">
                <WorkspaceQueryErrorCard
                  title={labels.aiCostsLoadErrorTitle}
                  description={labels.aiCostsLoadErrorDetail}
                  message={aiCostsQueryError}
                  actionLabel={labels.retryAction}
                  onRetry={() => {
                    void aiCostsQuery.refetch();
                  }}
                />
              </div>
            ) : null}

            {aiCostsQuery.data ? (
              <div className="mt-5 grid gap-4 md:grid-cols-2">
                <SummaryTile
                  label={labels.totalCostLabel}
                  value={formatCurrency(
                    locale,
                    aiCostsQuery.data.total_cost_usd,
                    "USD",
                  )}
                />
                <SummaryTile
                  label={labels.totalTokensLabel}
                  value={aiCostsQuery.data.total_tokens.toLocaleString(locale)}
                />
                <SummaryTile
                  label={labels.trackedServicesLabel}
                  value={String(aiCostsQuery.data.by_service.length)}
                />
                <SummaryTile
                  label={labels.remainingBudgetLabel}
                  value={
                    budgetGate
                      ? formatCurrency(locale, budgetGate.remaining_budget_usd, "USD")
                      : "-"
                  }
                />
              </div>
            ) : null}

            {!aiCostsQuery.isLoading && !aiCostsQuery.isError && !aiCostsQuery.data ? (
              <div className="mt-5 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm text-[var(--text-secondary)]">
                {labels.aiCostsEmpty}
              </div>
            ) : null}

            {aiCostsQuery.data?.by_service.length ? (
              <div className="mt-6 space-y-3">
                {aiCostsQuery.data.by_service.map((item) => (
                  <div
                    key={`${item.service_name}-${item.model_name}`}
                    className="rounded-[var(--radius-md)] border border-[var(--line)] p-4"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-[var(--text-primary)]">
                          {item.service_name}
                        </p>
                        <p className="text-xs text-[var(--text-tertiary)]">
                          {item.model_name}
                        </p>
                      </div>
                      <p className="text-sm font-semibold text-[var(--accent-strong)]">
                        {formatCurrency(locale, item.total_cost_usd, "USD")}
                      </p>
                    </div>
                    <p className="mt-2 text-xs text-[var(--text-tertiary)]">
                      {item.request_count.toLocaleString(locale)} {labels.requestsLabel} ·{" "}
                      {item.total_tokens.toLocaleString(locale)} {labels.tokensLabel}
                    </p>
                  </div>
                ))}
              </div>
            ) : null}

            <form className="mt-6 grid gap-3" onSubmit={handleSaveBudget}>
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.budgetTitle}
              </p>
              <Input
                value={budgetForm.endpoint}
                onChange={(event) =>
                  setBudgetForm((current) => ({
                    ...current,
                    endpoint: event.target.value,
                  }))
                }
                placeholder={labels.budgetEndpointLabel}
              />
              <div className="grid gap-3 md:grid-cols-2">
                <Input
                  type="number"
                  min="1"
                  step="0.01"
                  value={budgetForm.monthlyBudgetUsd}
                  onChange={(event) =>
                    setBudgetForm((current) => ({
                      ...current,
                      monthlyBudgetUsd: event.target.value,
                    }))
                  }
                  placeholder={labels.budgetAmountLabel}
                />
                <Input
                  type="number"
                  min="0.1"
                  max="1"
                  step="0.05"
                  value={budgetForm.alertThresholdRatio}
                  onChange={(event) =>
                    setBudgetForm((current) => ({
                      ...current,
                      alertThresholdRatio: event.target.value,
                    }))
                  }
                  placeholder={labels.budgetThresholdLabel}
                />
              </div>
              <Button type="submit" disabled={!canUseLiveApi || isSavingBudget}>
                {isSavingBudget
                  ? `${labels.saveBudgetAction}...`
                  : labels.saveBudgetAction}
              </Button>
            </form>

            {savedBudget ? (
              <div className="mt-5 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
                <p className="font-semibold text-[var(--text-primary)]">
                  {savedBudget.endpoint}
                </p>
                <p>
                  {formatCurrency(locale, savedBudget.monthly_budget_usd, "USD")} ·{" "}
                  {(savedBudget.alert_threshold_ratio * 100).toFixed(0)}%
                </p>
                <p className="text-xs text-[var(--text-tertiary)]">
                  {savedBudget.month} · {formatDate(locale, savedBudget.created_at)}
                </p>
                {budgetGate ? (
                  <p className="mt-2 text-xs text-[var(--text-tertiary)]">
                    {labels.remainingBudgetLabel}:{" "}
                    {formatCurrency(locale, budgetGate.remaining_budget_usd, "USD")}
                  </p>
                ) : null}
              </div>
            ) : null}
          </CardContent>
        </Card>

        <div className="grid gap-6">
          <Card>
            <CardContent className="p-6">
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.reportsTitle}
              </p>
              <form className="mt-5 grid gap-3" onSubmit={handleGenerateReport}>
                <Select
                  label={labels.propertyTypeLabel}
                  value={reportForm.assetType}
                  onValueChange={(value) =>
                    setReportForm((current) => ({
                      ...current,
                      assetType: value,
                    }))
                  }
                  options={PROPERTY_TYPE_OPTIONS}
                />
                <Input
                  value={reportForm.targetLanguages}
                  onChange={(event) =>
                    setReportForm((current) => ({
                      ...current,
                      targetLanguages: event.target.value,
                    }))
                  }
                  placeholder={labels.reportsLanguagesLabel}
                />
                <Input
                  value={reportForm.highlights}
                  onChange={(event) =>
                    setReportForm((current) => ({
                      ...current,
                      highlights: event.target.value,
                    }))
                  }
                  placeholder={labels.reportsHighlightsLabel}
                />
                <Input
                  value={reportForm.risks}
                  onChange={(event) =>
                    setReportForm((current) => ({
                      ...current,
                      risks: event.target.value,
                    }))
                  }
                  placeholder={labels.reportsRisksLabel}
                />
                <Input
                  value={reportForm.includeSections}
                  onChange={(event) =>
                    setReportForm((current) => ({
                      ...current,
                      includeSections: event.target.value,
                    }))
                  }
                  placeholder={labels.reportsSectionsLabel}
                />
                <Button
                  type="submit"
                  disabled={!canUseLiveApi || isGeneratingReport}
                >
                  {isGeneratingReport
                    ? `${labels.generateReportAction}...`
                    : labels.generateReportAction}
                </Button>
              </form>

              {generatedReport ? (
                <div className="mt-5 space-y-3">
                  <p className="text-xs text-[var(--text-tertiary)]">
                    {labels.generatedSectionsLabel}:{" "}
                    {generatedReport.generated_sections.join(", ")}
                  </p>
                  {generatedReport.variants.map((variant) => (
                    <div
                      key={variant.report_id}
                      className="rounded-[var(--radius-md)] border border-[var(--line)] p-4"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-[var(--text-primary)]">
                            {variant.title}
                          </p>
                          <p className="text-xs text-[var(--text-tertiary)]">
                            {variant.target_language.toUpperCase()}
                          </p>
                        </div>
                        <span className="rounded-full bg-[rgba(14,116,144,0.1)] px-3 py-1 text-xs font-medium text-[var(--accent-strong)]">
                          {labels.reportQualityLabel}:{" "}
                          {variant.quality_score?.toFixed(2) ?? "-"}
                        </span>
                      </div>
                      <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                        {variant.translated_text}
                      </p>
                    </div>
                  ))}
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                    {labels.portalsTitle}
                  </p>
                  <CardTitle className="mt-2 text-xl">
                    {labels.marketTitle}
                  </CardTitle>
                </div>
                <span className="rounded-full bg-[var(--surface-soft)] px-3 py-1 text-xs font-medium text-[var(--accent-strong)]">
                  {portalForm.regionCode}
                </span>
              </div>

              {marketDataQuery.isLoading ? (
                <div className="mt-5">
                  <SkeletonLoader count={2} itemClassName="h-24" />
                </div>
              ) : null}

              {marketDataQuery.isError ? (
                <div className="mt-5">
                  <WorkspaceQueryErrorCard
                    title={labels.marketLoadErrorTitle}
                    description={labels.marketLoadErrorDetail}
                    message={marketDataQueryError}
                    actionLabel={labels.retryAction}
                    onRetry={() => {
                      void marketDataQuery.refetch();
                    }}
                  />
                </div>
              ) : null}

              {marketDataQuery.data ? (
                <div className="mt-5 grid gap-4 md:grid-cols-2">
                  <SummaryTile
                    label={labels.listingsLabel}
                    value={marketDataQuery.data.active_listing_count.toLocaleString(locale)}
                  />
                  <SummaryTile
                    label={labels.portalInquiriesLabel}
                    value={marketDataQuery.data.average_inquiry_count.toFixed(1)}
                  />
                  <SummaryTile
                    label={labels.avgPriceLabel}
                    value={formatCurrency(
                      locale,
                      marketDataQuery.data.average_price_krw,
                      "KRW",
                    )}
                  />
                  <SummaryTile
                    label={labels.avgAreaLabel}
                    value={`${marketDataQuery.data.average_area_sqm.toFixed(1)} ㎡`}
                  />
                </div>
              ) : null}

              <form className="mt-6 grid gap-3" onSubmit={handlePublishPortals}>
                <div className="grid gap-3 md:grid-cols-2">
                  <Input
                    value={portalForm.regionCode}
                    onChange={(event) =>
                      setPortalForm((current) => ({
                        ...current,
                        regionCode: event.target.value,
                      }))
                    }
                    placeholder={labels.regionCodeLabel}
                  />
                  <Select
                    label={labels.propertyTypeLabel}
                    value={portalForm.propertyType}
                    onValueChange={(value) =>
                      setPortalForm((current) => ({
                        ...current,
                        propertyType: value,
                      }))
                    }
                    options={PROPERTY_TYPE_OPTIONS}
                  />
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <Input
                    type="number"
                    min="1"
                    step="1"
                    value={portalForm.priceKrw}
                    onChange={(event) =>
                      setPortalForm((current) => ({
                        ...current,
                        priceKrw: event.target.value,
                      }))
                    }
                    placeholder={labels.priceLabel}
                  />
                  <Input
                    type="number"
                    min="1"
                    step="0.1"
                    value={portalForm.areaSqm}
                    onChange={(event) =>
                      setPortalForm((current) => ({
                        ...current,
                        areaSqm: event.target.value,
                      }))
                    }
                    placeholder={labels.areaLabel}
                  />
                </div>
                <Input
                  value={portalForm.title}
                  onChange={(event) =>
                    setPortalForm((current) => ({
                      ...current,
                      title: event.target.value,
                    }))
                  }
                  placeholder={labels.titleLabel}
                />
                <textarea
                  className="min-h-28 rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3 text-sm text-[var(--text-primary)] outline-none transition placeholder:text-[var(--text-hint)] focus:border-[var(--accent)]"
                  value={portalForm.description}
                  onChange={(event) =>
                    setPortalForm((current) => ({
                      ...current,
                      description: event.target.value,
                    }))
                  }
                  placeholder={labels.descriptionLabel}
                />
                <Input
                  value={portalForm.portals}
                  onChange={(event) =>
                    setPortalForm((current) => ({
                      ...current,
                      portals: event.target.value,
                    }))
                  }
                  placeholder={labels.portalsLabel}
                />
                <Button type="submit" disabled={!canUseLiveApi || isPublishing}>
                  {isPublishing
                    ? `${labels.publishAction}...`
                    : labels.publishAction}
                </Button>
              </form>

              {marketDataQuery.data?.top_portals.length ? (
                <div className="mt-5 space-y-3">
                  {marketDataQuery.data.top_portals.map((portal) => (
                    <div
                      key={portal.portal_name}
                      className="rounded-[var(--radius-md)] border border-[var(--line)] p-4"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <p className="text-sm font-semibold text-[var(--text-primary)]">
                          {portal.portal_name}
                        </p>
                        <span className="text-xs text-[var(--text-tertiary)]">
                          {portal.listing_count.toLocaleString(locale)} {labels.listingsLabel}
                        </span>
                      </div>
                      <p className="mt-2 text-xs text-[var(--text-tertiary)]">
                        {labels.portalInquiriesLabel}:{" "}
                        {portal.average_inquiry_count.toFixed(1)}
                      </p>
                    </div>
                  ))}
                </div>
              ) : null}

              {publishedListings ? (
                <div className="mt-5 space-y-3">
                  {publishedListings.items.map((listing) => (
                    <div
                      key={listing.listing_id}
                      className="rounded-[var(--radius-md)] bg-[var(--surface-soft)] p-4"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <p className="text-sm font-semibold text-[var(--text-primary)]">
                          {listing.portal_name}
                        </p>
                        <span className="rounded-full bg-[rgba(14,116,144,0.1)] px-3 py-1 text-xs font-medium text-[var(--accent-strong)]">
                          {listing.status}
                        </span>
                      </div>
                      <p className="mt-2 text-xs text-[var(--text-tertiary)]">
                        {labels.portalViewsLabel}:{" "}
                        {listing.view_count.toLocaleString(locale)} ·{" "}
                        {labels.portalInquiriesLabel}:{" "}
                        {listing.inquiry_count.toLocaleString(locale)}
                      </p>
                      <p className="mt-2 break-all text-xs text-[var(--text-tertiary)]">
                        {listing.listing_url || listing.listing_external_id}
                      </p>
                    </div>
                  ))}
                </div>
              ) : null}
            </CardContent>
          </Card>
        </div>
      </div>
    </section>
  );
}

function SummaryTile({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
      <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-3 text-xl font-semibold text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}
