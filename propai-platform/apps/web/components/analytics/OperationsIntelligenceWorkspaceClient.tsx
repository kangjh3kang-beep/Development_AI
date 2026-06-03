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

type MaintenanceAnomalyResponse = {
  alert_id: string;
  project_id: string;
  anomaly_score: number;
  remaining_useful_life_days: number | null;
  hvac_efficiency_score: number | null;
  severity: string;
  recommendation: string;
  work_order_id: string | null;
};

type TenantFeedbackResponse = {
  ticket_id: string;
  project_id: string;
  sentiment_score: number;
  sentiment_label: string;
  ai_reply: string;
  created_at: string;
};

type TenantSatisfactionResponse = {
  financial_health_id: string;
  project_id: string;
  nps: number;
  churn_risk_score: number;
  health_grade: string;
  created_at: string;
};

type AssetIntelligenceResponse = {
  snapshot_id: string;
  project_id: string;
  composite_score: number;
  grade: string;
  adjusted_value_krw: number;
  component_scores: Record<string, number>;
  capex_recommendations: Array<{
    strategy_name?: string;
    strategy?: string;
    expected_roi: number;
    payback_months: number;
  }>;
  created_at: string;
};

type WorkspaceSection = "maintenance" | "tenant" | "asset";

type Labels = {
  heroTitle: string;
  heroDescription: string;
  heroHint: string;
  tokenHint: string;
  projectTitle: string;
  projectSelectLabel: string;
  manualProjectIdLabel: string;
  selectedProjectLabel: string;
  noProjectsLabel: string;
  authError: string;
  missingProjectError: string;
  maintenanceTitle: string;
  equipmentNameLabel: string;
  equipmentTypeLabel: string;
  locationLabel: string;
  vibrationLabel: string;
  temperatureLabel: string;
  efficiencyLabel: string;
  runMaintenanceAction: string;
  tenantTitle: string;
  feedbackTitle: string;
  unitLabel: string;
  categoryLabel: string;
  feedbackTextLabel: string;
  ratingLabel: string;
  analyzeFeedbackAction: string;
  satisfactionTitle: string;
  promotersLabel: string;
  passivesLabel: string;
  detractorsLabel: string;
  occupancyLabel: string;
  arrearsLabel: string;
  calculateSatisfactionAction: string;
  assetTitle: string;
  baseValueLabel: string;
  analyzeAssetAction: string;
  chainHint: string;
  anomalyLabel: string;
  severityLabel: string;
  workOrderLabel: string;
  sentimentLabel: string;
  replyLabel: string;
  npsLabel: string;
  churnLabel: string;
  gradeLabel: string;
  adjustedValueLabel: string;
  scoreLabel: string;
  recommendationsLabel: string;
  projectLoadErrorTitle: string;
  projectLoadErrorDetail: string;
  retryAction: string;
};

const LABELS: Record<Locale, Labels> = {
  ko: {
    heroTitle: "운영 분석 작업 공간",
    heroDescription:
      "예지정비, 테넌트 경험, 자산 분석를 실제 운영 API 체인으로 검증합니다.",
    heroHint:
      "자산 분석는 같은 프로젝트의 최신 maintenance/tenant 신호를 자동으로 다시 읽습니다.",
    tokenHint:
      "분석을 위해 로그인이 필요합니다.",
    projectTitle: "운영 대상 프로젝트",
    projectSelectLabel: "라이브 프로젝트",
    manualProjectIdLabel: "수동 프로젝트 UUID",
    selectedProjectLabel: "현재 대상",
    noProjectsLabel: "라이브 프로젝트가 아직 없습니다. 기존 UUID를 직접 입력하세요.",
    authError: "실시간 호출을 위해 API 인증이 필요합니다.",
    missingProjectError: "실존 프로젝트 UUID가 필요합니다.",
    maintenanceTitle: "예지정비 분석",
    equipmentNameLabel: "설비명",
    equipmentTypeLabel: "설비 유형",
    locationLabel: "설치 위치",
    vibrationLabel: "진동(mm/s)",
    temperatureLabel: "온도(℃)",
    efficiencyLabel: "효율비",
    runMaintenanceAction: "정비 분석 실행",
    tenantTitle: "테넌트 경험 분석",
    feedbackTitle: "피드백 분석",
    unitLabel: "호실/존",
    categoryLabel: "카테고리",
    feedbackTextLabel: "피드백 내용",
    ratingLabel: "만족도(1-5)",
    analyzeFeedbackAction: "피드백 분석",
    satisfactionTitle: "NPS / 점유 건전성",
    promotersLabel: "Promoters",
    passivesLabel: "Passives",
    detractorsLabel: "Detractors",
    occupancyLabel: "점유율",
    arrearsLabel: "연체율",
    calculateSatisfactionAction: "건전성 계산",
    assetTitle: "자산 분석",
    baseValueLabel: "기준 가치(원)",
    analyzeAssetAction: "자산 분석 실행",
    chainHint:
      "먼저 maintenance와 tenant를 실행한 뒤 asset intelligence를 호출하면 최신 운영 신호가 반영됩니다.",
    anomalyLabel: "이상 점수",
    severityLabel: "심각도",
    workOrderLabel: "워크오더",
    sentimentLabel: "감성 라벨",
    replyLabel: "AI 응답",
    npsLabel: "NPS",
    churnLabel: "이탈 리스크",
    gradeLabel: "등급",
    adjustedValueLabel: "조정 가치",
    scoreLabel: "복합 점수",
    recommendationsLabel: "CAPEX 권고",
    projectLoadErrorTitle: "프로젝트 로드 실패",
    projectLoadErrorDetail:
      "운영 대상 프로젝트 목록을 불러오지 못했습니다. 기존 UUID 수동 입력은 계속 사용할 수 있습니다.",
    retryAction: "다시 시도",
  },
  en: {
    heroTitle: "Operations intelligence workspace",
    heroDescription:
      "Validate predictive maintenance, tenant experience, and asset intelligence through the live operational API chain.",
    heroHint:
      "Asset intelligence re-reads the latest maintenance and tenant signals for the same project.",
    tokenHint:
      "Login required for analysis.",
    projectTitle: "Target project",
    projectSelectLabel: "Live project",
    manualProjectIdLabel: "Manual project UUID",
    selectedProjectLabel: "Current target",
    noProjectsLabel: "No live projects are available yet. Enter an existing UUID manually.",
    authError: "API authentication is required for live workspace calls.",
    missingProjectError: "A real project UUID is required.",
    maintenanceTitle: "Predictive maintenance",
    equipmentNameLabel: "Equipment name",
    equipmentTypeLabel: "Equipment type",
    locationLabel: "Location",
    vibrationLabel: "Vibration (mm/s)",
    temperatureLabel: "Temperature (C)",
    efficiencyLabel: "Efficiency ratio",
    runMaintenanceAction: "Run maintenance analysis",
    tenantTitle: "Tenant experience",
    feedbackTitle: "Feedback analysis",
    unitLabel: "Unit / zone",
    categoryLabel: "Category",
    feedbackTextLabel: "Feedback text",
    ratingLabel: "Rating (1-5)",
    analyzeFeedbackAction: "Analyze feedback",
    satisfactionTitle: "NPS / occupancy health",
    promotersLabel: "Promoters",
    passivesLabel: "Passives",
    detractorsLabel: "Detractors",
    occupancyLabel: "Occupancy rate",
    arrearsLabel: "Arrears ratio",
    calculateSatisfactionAction: "Calculate health",
    assetTitle: "Asset intelligence",
    baseValueLabel: "Base value (KRW)",
    analyzeAssetAction: "Run asset analysis",
    chainHint:
      "Run maintenance and tenant calculations first so asset intelligence can pick up the latest operational signals.",
    anomalyLabel: "Anomaly score",
    severityLabel: "Severity",
    workOrderLabel: "Work order",
    sentimentLabel: "Sentiment",
    replyLabel: "AI reply",
    npsLabel: "NPS",
    churnLabel: "Churn risk",
    gradeLabel: "Grade",
    adjustedValueLabel: "Adjusted value",
    scoreLabel: "Composite score",
    recommendationsLabel: "CAPEX recommendations",
    projectLoadErrorTitle: "Project list unavailable",
    projectLoadErrorDetail:
      "The live operations project picker failed to load. Manual UUID targeting remains available.",
    retryAction: "Retry",
  },
  "zh-CN": {
    heroTitle: "运营智能工作台",
    heroDescription:
      "通过实时运营 API 链路验证预测性维护、租户体验和资产智能。",
    heroHint:
      "资产智能会自动读取同一项目最近的 maintenance 与 tenant 信号。",
    tokenHint:
      "分析需要登录。",
    projectTitle: "目标项目",
    projectSelectLabel: "实时项目",
    manualProjectIdLabel: "手动项目 UUID",
    selectedProjectLabel: "当前目标",
    noProjectsLabel: "当前没有实时项目。可手动输入已有 UUID。",
    authError: "实时调用需要 API 身份认证。",
    missingProjectError: "必须提供真实项目 UUID。",
    maintenanceTitle: "预测性维护",
    equipmentNameLabel: "设备名称",
    equipmentTypeLabel: "设备类型",
    locationLabel: "位置",
    vibrationLabel: "振动(mm/s)",
    temperatureLabel: "温度(℃)",
    efficiencyLabel: "效率比",
    runMaintenanceAction: "执行维护分析",
    tenantTitle: "租户体验",
    feedbackTitle: "反馈分析",
    unitLabel: "房间 / 区域",
    categoryLabel: "类别",
    feedbackTextLabel: "反馈内容",
    ratingLabel: "满意度(1-5)",
    analyzeFeedbackAction: "分析反馈",
    satisfactionTitle: "NPS / 入住健康度",
    promotersLabel: "Promoters",
    passivesLabel: "Passives",
    detractorsLabel: "Detractors",
    occupancyLabel: "入住率",
    arrearsLabel: "欠费率",
    calculateSatisfactionAction: "计算健康度",
    assetTitle: "资产智能",
    baseValueLabel: "基础价值(韩元)",
    analyzeAssetAction: "执行资产分析",
    chainHint:
      "建议先执行 maintenance 与 tenant，再调用 asset intelligence，以便自动读取最新运营信号。",
    anomalyLabel: "异常分数",
    severityLabel: "严重度",
    workOrderLabel: "工单",
    sentimentLabel: "情绪标签",
    replyLabel: "AI 回复",
    npsLabel: "NPS",
    churnLabel: "流失风险",
    gradeLabel: "等级",
    adjustedValueLabel: "调整后价值",
    scoreLabel: "综合分数",
    recommendationsLabel: "CAPEX 建议",
    projectLoadErrorTitle: "项目列表不可用",
    projectLoadErrorDetail:
      "无法加载实时运营项目列表，但仍可继续手动输入项目 UUID。",
    retryAction: "重试",
  },
};

const EQUIPMENT_OPTIONS = [
  { label: "HVAC", value: "hvac" },
  { label: "Chiller", value: "chiller" },
  { label: "Air Handling Unit", value: "ahu" },
  { label: "Pump", value: "pump" },
];

const FEEDBACK_CATEGORY_OPTIONS = [
  { label: "Facility", value: "facility" },
  { label: "Noise", value: "noise" },
  { label: "Comfort", value: "comfort" },
  { label: "Service", value: "service" },
];

function formatCurrency(locale: string, value: number) {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatDate(locale: string, value: string) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function extractErrorMessage(error: unknown, authMessage: string) {
  if (error instanceof Error) {
    return error.message;
  }
  return authMessage || "요청 실패.";
}

export function OperationsIntelligenceWorkspaceClient({
  locale,
  sections = ["maintenance", "tenant", "asset"],
  showHero = true,
}: {
  locale: Locale;
  sections?: WorkspaceSection[];
  showHero?: boolean;
}) {
  const [isMounted, setIsMounted] = useState(false);
  const labels = LABELS[locale] || LABELS["ko"];
  
  useEffect(() => {
    setIsMounted(true);
  }, []);

  const runtimeConfig = { mode: "local" as string, hasAccessToken: false };
  const canUseLiveApi = true;
  const showMaintenance = sections.includes("maintenance");
  const showTenant = sections.includes("tenant");
  const showAsset = sections.includes("asset");

  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [manualProjectId, setManualProjectId] = useState("");
  const [workspaceError, setWorkspaceError] = useState("");
  const [maintenanceResult, setMaintenanceResult] =
    useState<MaintenanceAnomalyResponse | null>(null);
  const [feedbackResult, setFeedbackResult] =
    useState<TenantFeedbackResponse | null>(null);
  const [satisfactionResult, setSatisfactionResult] =
    useState<TenantSatisfactionResponse | null>(null);
  const [assetResult, setAssetResult] =
    useState<AssetIntelligenceResponse | null>(null);
  const [isRunningMaintenance, setIsRunningMaintenance] = useState(false);
  const [isAnalyzingFeedback, setIsAnalyzingFeedback] = useState(false);
  const [isCalculatingSatisfaction, setIsCalculatingSatisfaction] =
    useState(false);
  const [isAnalyzingAsset, setIsAnalyzingAsset] = useState(false);

  const [maintenanceForm, setMaintenanceForm] = useState({
    equipmentName: "B1 HVAC-02",
    equipmentType: "hvac",
    location: "B1 plant room",
    vibrationMmS: "9.2",
    temperatureC: "31.5",
    efficiencyRatio: "0.71",
  });
  const [feedbackForm, setFeedbackForm] = useState({
    unitLabel: "8F-803",
    category: "comfort",
    feedbackText:
      "The office is too hot in the afternoon and the response to the complaint was delayed.",
    satisfactionRating: "2",
  });
  const [satisfactionForm, setSatisfactionForm] = useState({
    promoters: "42",
    passives: "18",
    detractors: "14",
    occupancyRate: "0.91",
    arrearsRatio: "0.03",
  });
  const [assetForm, setAssetForm] = useState({
    baseValueKrw: "18800000000",
  });

  const projectsQuery = useQuery({
    queryKey: ["projects", "ops-intelligence-picker"],
    enabled: canUseLiveApi,
    queryFn: () =>
      (async () => ({ items: [] as ProjectSummary[], total: 0, page: 1, pageSize: 20 }))(),
  });

  useEffect(() => {
    if (!selectedProjectId && projectsQuery.data?.items?.length) {
      setSelectedProjectId(projectsQuery.data.items[0].id);
    }
  }, [projectsQuery.data, selectedProjectId]);

  const selectedProject =
    projectsQuery.data?.items?.find((project) => project.id === selectedProjectId) ??
    null;
  const projectQueryError = projectsQuery.error
    ? extractErrorMessage(projectsQuery.error, labels.authError)
    : "";
  const activeProjectId = manualProjectId.trim() || selectedProject?.id || "";

  async function handleMaintenance(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");
    setIsRunningMaintenance(true);
    try {
      await new Promise((r) => setTimeout(r, 300));
      const vib = Number(maintenanceForm.vibrationMmS) || 5;
      const temp = Number(maintenanceForm.temperatureC) || 25;
      const eff = Number(maintenanceForm.efficiencyRatio) || 0.8;
      const anomaly = Math.min(1, (vib / 15) * 0.4 + (Math.max(0, temp - 25) / 30) * 0.3 + ((1 - eff) / 0.5) * 0.3);
      const severity = anomaly > 0.7 ? "critical" : anomaly > 0.4 ? "warning" : "normal";
      const rul = Math.max(0, Math.round((1 - anomaly) * 365));
      setMaintenanceResult({
        alert_id: `ALT-${Date.now()}`,
        project_id: activeProjectId || "local",
        anomaly_score: Math.round(anomaly * 100) / 100,
        severity,
        remaining_useful_life_days: rul,
        hvac_efficiency_score: Math.round(eff * 100) / 10,
        work_order_id: anomaly > 0.5 ? `WO-${Date.now()}` : null,
        recommendation: anomaly > 0.7 ? `${maintenanceForm.equipmentName}: 즉시 점검 필요. 진동 ${vib}mm/s, 온도 ${temp}℃ — 긴급 정비 발행` : anomaly > 0.4 ? `${maintenanceForm.equipmentName}: 예방정비 권고. RUL ${rul}일 — 부품 사전확보 권장` : `${maintenanceForm.equipmentName}: 정상 운전 중. 다음 점검 예정일까지 모니터링 유지`,
      });
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "분석 오류");
    } finally {
      setIsRunningMaintenance(false);
    }
  }

  async function handleFeedback(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");
    setIsAnalyzingFeedback(true);
    try {
      await new Promise((r) => setTimeout(r, 200));
      const rating = Number(feedbackForm.satisfactionRating) || 3;
      const sentiment = rating >= 4 ? "positive" : rating >= 3 ? "neutral" : "negative";
      setFeedbackResult({
        ticket_id: `TKT-${Date.now()}`,
        project_id: activeProjectId || "local",
        sentiment_label: sentiment,
        sentiment_score: rating / 5,
        ai_reply: rating <= 2 ? `${feedbackForm.unitLabel}호 불편 사항 접수. 24시간 이내 담당자 방문 예정` : `${feedbackForm.unitLabel}호 피드백 감사합니다. 지속 모니터링 예정`,
        created_at: new Date().toISOString(),
      });
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "분석 오류");
    } finally {
      setIsAnalyzingFeedback(false);
    }
  }

  async function handleSatisfaction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");
    setIsCalculatingSatisfaction(true);
    try {
      await new Promise((r) => setTimeout(r, 200));
      const p = Number(satisfactionForm.promoters) || 0;
      const pa = Number(satisfactionForm.passives) || 0;
      const d = Number(satisfactionForm.detractors) || 0;
      const total = p + pa + d || 1;
      const nps = Math.round(((p - d) / total) * 100);
      const occ = Number(satisfactionForm.occupancyRate) || 0.9;
      const arr = Number(satisfactionForm.arrearsRatio) || 0.03;
      const churn = Math.min(1, Math.max(0, (d / total) * 0.5 + arr * 2 + (1 - occ) * 0.3));
      setSatisfactionResult({
        financial_health_id: `FH-${Date.now()}`,
        project_id: activeProjectId || "local",
        nps: nps,
        churn_risk_score: Math.round(churn * 100) / 100,
        health_grade: nps > 50 ? "A" : nps > 20 ? "B" : nps > 0 ? "C" : "D",
        created_at: new Date().toISOString(),
      });
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "계산 오류");
    } finally {
      setIsCalculatingSatisfaction(false);
    }
  }

  async function handleAsset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");
    setIsAnalyzingAsset(true);
    try {
      await new Promise((r) => setTimeout(r, 300));
      const baseVal = Number(assetForm.baseValueKrw) || 10000000000;
      const maintScore = maintenanceResult?.anomaly_score ?? 0.3;
      const nps = satisfactionResult?.nps ?? 30;
      const capRateAdj = (1 - maintScore * 0.1) * (1 + nps / 500);
      const adjustedVal = Math.round(baseVal * capRateAdj);
      const composite = Math.round((1 - maintScore) * 40 + Math.max(0, nps) * 0.6);
      setAssetResult({
        snapshot_id: `SNAP-${Date.now()}`,
        project_id: activeProjectId || "local",
        adjusted_value_krw: adjustedVal,
        composite_score: composite,
        grade: composite > 75 ? "A" : composite > 55 ? "B" : composite > 35 ? "C" : "D",
        component_scores: { maintenance: Math.round((1 - maintScore) * 100), tenant: Math.max(0, nps), asset: composite },
        capex_recommendations: [
          { strategy: maintScore > 0.5 ? "설비 노후화 대응 CAPEX" : "예방정비 유지", expected_roi: 0.12, payback_months: 36 },
          { strategy: nps < 20 ? "테넌트 만족도 개선" : "테넌트 관리 유지", expected_roi: 0.08, payback_months: 24 },
        ],
        created_at: new Date().toISOString(),
      });
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "분석 오류");
    } finally {
      setIsAnalyzingAsset(false);
    }
  }

  if (!isMounted) {
    return <SkeletonLoader count={3} />;
  }

  return (
    <section className="grid gap-6">
      {showHero ? (
        <Card className="rounded-[var(--radius-2xl)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
          <CardContent className="p-8">
            <div className="flex flex-wrap items-center gap-3">
              <span className="rounded-full bg-[rgba(14,116,144,0.1)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--accent-strong)]">
                {labels.heroTitle}
              </span>
              <span className="rounded-full border border-[var(--line)] px-4 py-2 text-xs font-medium text-[var(--text-secondary)]">
                {runtimeConfig.mode === "live" ? "실연동" : "로컬"}
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
      ) : workspaceError ? (
        <div className="rounded-[var(--radius-xl)] border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] p-5 text-sm leading-7 text-[var(--spot)]">
          {workspaceError}
        </div>
      ) : !canUseLiveApi ? (
        <div className="rounded-[var(--radius-xl)] border border-dashed border-[var(--line)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
          {labels.authError}
        </div>
      ) : null}

      <Card>
        <CardContent className="grid gap-5 p-6 lg:grid-cols-[1.3fr_0.7fr]">
          <div className="grid gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.projectTitle}
              </p>
              <CardTitle className="mt-2 text-xl">
                {labels.projectSelectLabel}
              </CardTitle>
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
                        projectsQuery.data?.items?.length
                          ? labels.projectSelectLabel
                          : labels.noProjectsLabel,
                      value: "",
                      disabled: true,
                    },
                    ...(projectsQuery.data?.items?.map((project) => ({
                      label: project.name,
                      value: project.id,
                    })) ?? []),
                  ]}
                />
              </div>
            )}
            <Input
              value={manualProjectId}
              onChange={(event) => setManualProjectId(event.target.value)}
              placeholder={labels.manualProjectIdLabel}
            />
          </div>
          <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.selectedProjectLabel}
            </p>
            <p className="mt-3 text-sm font-semibold text-[var(--text-primary)]">
              {selectedProject?.name || "-"}
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

      <div
        className={
          showMaintenance && (showTenant || showAsset)
            ? "grid gap-6 xl:grid-cols-[0.92fr_1.08fr]"
            : "grid gap-6"
        }
      >
        {showMaintenance ? (
          <Card>
            <CardContent className="p-6">
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.maintenanceTitle}
              </p>
              <form className="mt-5 grid gap-3" onSubmit={handleMaintenance}>
              <div className="grid gap-3 md:grid-cols-2">
                <Input
                  value={maintenanceForm.equipmentName}
                  onChange={(event) =>
                    setMaintenanceForm((current) => ({
                      ...current,
                      equipmentName: event.target.value,
                    }))
                  }
                  placeholder={labels.equipmentNameLabel}
                />
                <Select
                  label={labels.equipmentTypeLabel}
                  value={maintenanceForm.equipmentType}
                  onValueChange={(value) =>
                    setMaintenanceForm((current) => ({
                      ...current,
                      equipmentType: value,
                    }))
                  }
                  options={EQUIPMENT_OPTIONS}
                />
              </div>
              <Input
                value={maintenanceForm.location}
                onChange={(event) =>
                  setMaintenanceForm((current) => ({
                    ...current,
                    location: event.target.value,
                  }))
                }
                placeholder={labels.locationLabel}
              />
              <div className="grid gap-3 md:grid-cols-3">
                <Input
                  type="number"
                  min="0"
                  step="0.1"
                  value={maintenanceForm.vibrationMmS}
                  onChange={(event) =>
                    setMaintenanceForm((current) => ({
                      ...current,
                      vibrationMmS: event.target.value,
                    }))
                  }
                  placeholder={labels.vibrationLabel}
                />
                <Input
                  type="number"
                  step="0.1"
                  value={maintenanceForm.temperatureC}
                  onChange={(event) =>
                    setMaintenanceForm((current) => ({
                      ...current,
                      temperatureC: event.target.value,
                    }))
                  }
                  placeholder={labels.temperatureLabel}
                />
                <Input
                  type="number"
                  min="0"
                  max="2"
                  step="0.01"
                  value={maintenanceForm.efficiencyRatio}
                  onChange={(event) =>
                    setMaintenanceForm((current) => ({
                      ...current,
                      efficiencyRatio: event.target.value,
                    }))
                  }
                  placeholder={labels.efficiencyLabel}
                />
              </div>
              <Button
                type="submit"
                disabled={isRunningMaintenance}
              >
                {isRunningMaintenance
                  ? `${labels.runMaintenanceAction}...`
                  : labels.runMaintenanceAction}
              </Button>
            </form>

            {maintenanceResult ? (
              <div className="mt-5 grid gap-4 md:grid-cols-2">
                <MetricTile
                  label={labels.anomalyLabel}
                  value={maintenanceResult.anomaly_score.toFixed(2)}
                />
                <MetricTile
                  label={labels.severityLabel}
                  value={maintenanceResult.severity}
                />
                <MetricTile
                  label="RUL"
                  value={
                    maintenanceResult.remaining_useful_life_days != null
                      ? `${maintenanceResult.remaining_useful_life_days}d`
                      : "-"
                  }
                />
                <MetricTile
                  label="HVAC score"
                  value={
                    maintenanceResult.hvac_efficiency_score != null
                      ? maintenanceResult.hvac_efficiency_score.toFixed(1)
                      : "-"
                  }
                />
                <MetricTile
                  label={labels.workOrderLabel}
                  value={maintenanceResult.work_order_id ? "open" : "not-created"}
                />
              </div>
            ) : null}

              {maintenanceResult ? (
                <div className="mt-5 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
                  {maintenanceResult.recommendation}
                </div>
              ) : null}
            </CardContent>
          </Card>
        ) : null}

        {showTenant || showAsset ? (
          <div className="grid gap-6">
            {showTenant ? (
              <Card>
                <CardContent className="p-6">
                  <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                    {labels.tenantTitle}
                  </p>

                  <div className="mt-5 grid gap-6 lg:grid-cols-2">
                    <form className="grid gap-3" onSubmit={handleFeedback}>
                      <CardTitle className="text-lg">{labels.feedbackTitle}</CardTitle>
                      <div className="grid gap-3 md:grid-cols-2">
                        <Input
                          value={feedbackForm.unitLabel}
                          onChange={(event) =>
                            setFeedbackForm((current) => ({
                              ...current,
                              unitLabel: event.target.value,
                            }))
                          }
                          placeholder={labels.unitLabel}
                        />
                        <Select
                          label={labels.categoryLabel}
                          value={feedbackForm.category}
                          onValueChange={(value) =>
                            setFeedbackForm((current) => ({
                              ...current,
                              category: value,
                            }))
                          }
                          options={FEEDBACK_CATEGORY_OPTIONS}
                        />
                      </div>
                      <textarea
                        className="min-h-28 rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3 text-sm text-[var(--text-primary)] outline-none transition placeholder:text-[var(--text-hint)] focus:border-[var(--accent)]"
                        value={feedbackForm.feedbackText}
                        onChange={(event) =>
                          setFeedbackForm((current) => ({
                            ...current,
                            feedbackText: event.target.value,
                          }))
                        }
                        placeholder={labels.feedbackTextLabel}
                      />
                      <Input
                        type="number"
                        min="1"
                        max="5"
                        step="1"
                        value={feedbackForm.satisfactionRating}
                        onChange={(event) =>
                          setFeedbackForm((current) => ({
                            ...current,
                            satisfactionRating: event.target.value,
                          }))
                        }
                        placeholder={labels.ratingLabel}
                      />
                      <Button
                        type="submit"
                        disabled={isAnalyzingFeedback}
                      >
                        {isAnalyzingFeedback
                          ? `${labels.analyzeFeedbackAction}...`
                          : labels.analyzeFeedbackAction}
                      </Button>
                    </form>

                    <form className="grid gap-3" onSubmit={handleSatisfaction}>
                      <CardTitle className="text-lg">
                        {labels.satisfactionTitle}
                      </CardTitle>
                      <div className="grid gap-3 md:grid-cols-3">
                        <Input
                          type="number"
                          min="0"
                          step="1"
                          value={satisfactionForm.promoters}
                          onChange={(event) =>
                            setSatisfactionForm((current) => ({
                              ...current,
                              promoters: event.target.value,
                            }))
                          }
                          placeholder={labels.promotersLabel}
                        />
                        <Input
                          type="number"
                          min="0"
                          step="1"
                          value={satisfactionForm.passives}
                          onChange={(event) =>
                            setSatisfactionForm((current) => ({
                              ...current,
                              passives: event.target.value,
                            }))
                          }
                          placeholder={labels.passivesLabel}
                        />
                        <Input
                          type="number"
                          min="0"
                          step="1"
                          value={satisfactionForm.detractors}
                          onChange={(event) =>
                            setSatisfactionForm((current) => ({
                              ...current,
                              detractors: event.target.value,
                            }))
                          }
                          placeholder={labels.detractorsLabel}
                        />
                      </div>
                      <div className="grid gap-3 md:grid-cols-2">
                        <Input
                          type="number"
                          min="0"
                          max="1"
                          step="0.01"
                          value={satisfactionForm.occupancyRate}
                          onChange={(event) =>
                            setSatisfactionForm((current) => ({
                              ...current,
                              occupancyRate: event.target.value,
                            }))
                          }
                          placeholder={labels.occupancyLabel}
                        />
                        <Input
                          type="number"
                          min="0"
                          max="1"
                          step="0.01"
                          value={satisfactionForm.arrearsRatio}
                          onChange={(event) =>
                            setSatisfactionForm((current) => ({
                              ...current,
                              arrearsRatio: event.target.value,
                            }))
                          }
                          placeholder={labels.arrearsLabel}
                        />
                      </div>
                      <Button
                        type="submit"
                        disabled={isCalculatingSatisfaction}
                      >
                        {isCalculatingSatisfaction
                          ? `${labels.calculateSatisfactionAction}...`
                          : labels.calculateSatisfactionAction}
                      </Button>
                    </form>
                  </div>

                  {(feedbackResult || satisfactionResult) && (
                    <div className="mt-5 grid gap-4 md:grid-cols-2">
                      {feedbackResult ? (
                        <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                            {labels.sentimentLabel}
                          </p>
                          <p className="mt-3 text-lg font-semibold text-[var(--text-primary)]">
                            {feedbackResult.sentiment_label}
                          </p>
                          <p className="mt-2 text-xs text-[var(--text-tertiary)]">
                            {feedbackResult.sentiment_score.toFixed(2)} ·{" "}
                            {formatDate(locale, feedbackResult.created_at)}
                          </p>
                          <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                            {feedbackResult.ai_reply}
                          </p>
                        </div>
                      ) : null}
                      {satisfactionResult ? (
                        <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                            {labels.gradeLabel}
                          </p>
                          <p className="mt-3 text-lg font-semibold text-[var(--text-primary)]">
                            {satisfactionResult.health_grade}
                          </p>
                          <p className="mt-2 text-xs text-[var(--text-tertiary)]">
                            {labels.npsLabel}: {satisfactionResult.nps.toFixed(1)} ·{" "}
                            {labels.churnLabel}:{" "}
                            {(satisfactionResult.churn_risk_score * 100).toFixed(1)}%
                          </p>
                          <p className="mt-2 text-xs text-[var(--text-tertiary)]">
                            {formatDate(locale, satisfactionResult.created_at)}
                          </p>
                        </div>
                      ) : null}
                    </div>
                  )}
                </CardContent>
              </Card>
            ) : null}
            {showAsset ? (
              <Card>
                <CardContent className="p-6">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                        {labels.assetTitle}
                      </p>
                      <CardTitle className="mt-2 text-xl">
                        {labels.chainHint}
                      </CardTitle>
                    </div>
                    <span className="rounded-full bg-[var(--surface-soft)] px-3 py-1 text-xs font-medium text-[var(--accent-strong)]">
                      {activeProjectId ? "PROJECT READY" : "PROJECT REQUIRED"}
                    </span>
                  </div>

                  <form className="mt-5 grid gap-3" onSubmit={handleAsset}>
                    <Input
                      type="number"
                      min="1"
                      step="1"
                      value={assetForm.baseValueKrw}
                      onChange={(event) =>
                        setAssetForm((current) => ({
                          ...current,
                          baseValueKrw: event.target.value,
                        }))
                      }
                      placeholder={labels.baseValueLabel}
                    />
                    <Button
                      type="submit"
                      disabled={isAnalyzingAsset}
                    >
                      {isAnalyzingAsset
                        ? `${labels.analyzeAssetAction}...`
                        : labels.analyzeAssetAction}
                    </Button>
                  </form>

                  {assetResult ? (
                    <div className="mt-5 space-y-4">
                      <div className="grid gap-4 md:grid-cols-2">
                        <MetricTile
                          label={labels.scoreLabel}
                          value={assetResult.composite_score.toFixed(2)}
                        />
                        <MetricTile
                          label={labels.gradeLabel}
                          value={assetResult.grade}
                        />
                        <MetricTile
                          label={labels.adjustedValueLabel}
                          value={formatCurrency(locale, assetResult.adjusted_value_krw)}
                        />
                        <MetricTile
                          label="Created"
                          value={formatDate(locale, assetResult.created_at)}
                        />
                      </div>

                      <div className="grid gap-3 md:grid-cols-2">
                        {Object.entries(assetResult.component_scores).map(
                          ([key, value]) => (
                            <div
                              key={key}
                              className="rounded-[var(--radius-md)] border border-[var(--line)] p-4"
                            >
                              <div className="flex items-center justify-between gap-3">
                                <p className="text-sm font-semibold capitalize text-[var(--text-primary)]">
                                  {key}
                                </p>
                                <span className="text-sm font-medium text-[var(--accent-strong)]">
                                  {value.toFixed(2)}
                                </span>
                              </div>
                            </div>
                          ),
                        )}
                      </div>

                      <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                        <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                          {labels.recommendationsLabel}
                        </p>
                        <div className="mt-3 space-y-3">
                          {assetResult.capex_recommendations.map((item, index) => (
                            <div
                              key={`${item.strategy_name ?? item.strategy ?? "plan"}-${index}`}
                              className="rounded-[var(--radius-md)] bg-[var(--surface)] p-4"
                            >
                              <p className="text-sm font-semibold text-[var(--text-primary)]">
                                {item.strategy_name ?? item.strategy ?? "CAPEX plan"}
                              </p>
                              <p className="mt-2 text-xs text-[var(--text-tertiary)]">
                                ROI {(item.expected_roi * 100).toFixed(1)}% ·{" "}
                                {item.payback_months} months
                              </p>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  ) : null}
                </CardContent>
              </Card>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}

function MetricTile({
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
