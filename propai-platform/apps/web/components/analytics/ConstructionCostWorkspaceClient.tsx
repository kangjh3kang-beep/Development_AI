"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, CardTitle, Input, Select } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import type { Locale } from "@/i18n/config";

type ProjectSummary = {
  id: string;
  name: string;
  status: string;
  total_area_sqm: number | null;
};

type PaginatedResponse<T> = {
  items: T[];
  page: number;
  page_size: number;
  has_next: boolean;
};

type MaterialSnapshot = {
  as_of: string;
  items: Array<{
    material_code: string;
    material_name: string;
    current_unit_price_krw: number;
    latest_price_index: number;
    mom_change_ratio: number;
    yoy_change_ratio: number;
    estimated_project_cost_krw: number | null;
    alert_level: string;
    history: Array<{ source_name: string }>;
  }>;
  alerts: Array<{ title: string; detail: string }>;
};

type EscalationSnapshot = {
  adjusted_cost_krw: number;
  overall_escalation_ratio: number;
  ppi_source: string;
  summary: string;
  material_impacts: Array<{
    material_code: string;
    material_name: string;
    weight_ratio: number;
    delta_ratio: number;
    cost_impact_krw: number;
  }>;
};

function formatCurrency(locale: string, value: number) {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(2)}%`;
}

function extractErrorMessage(error: unknown) {
  if (error instanceof Error) {
    return error.message;
  }
  return "요청 실패.";
}

type Labels = {
  heroTitle: string;
  heroDescription: string;
  heroHint: string;
  projectTitle: string;
  projectSelectLabel: string;
  manualProjectIdLabel: string;
  selectedProjectLabel: string;
  manualTargetLabel: string;
  materialSnapshotTitle: string;
  materialTrendTitle: string;
  regionCodeLabel: string;
  materialCodesLabel: string;
  refreshAction: string;
  analysisTitle: string;
  analysisHint: string;
  baseCostLabel: string;
  durationLabel: string;
  baselineYearLabel: string;
  targetYearLabel: string;
  materialShareLabel: string;
  laborShareLabel: string;
  overheadShareLabel: string;
  contingencyLabel: string;
  analyzeAction: string;
  adjustedCostLabel: string;
  escalationRateLabel: string;
  sourceLabel: string;
  deltaLabel: string;
  impactLabel: string;
  projectLoadErrorTitle: string;
  projectLoadErrorDetail: string;
  materialLoadErrorTitle: string;
  materialLoadErrorDetail: string;
  escalationLoadErrorTitle: string;
  escalationLoadErrorDetail: string;
  retryAction: string;
  authError: string;
  missingProjectError: string;
  alertsLabel: string;
};

const LABELS: Record<Locale, Labels> = {
  ko: {
    heroTitle: "비용 리서치 인텔리전스",
    heroDescription: "KCCI 자재가와 PPI 공사비 보정 시뮬레이션",
    heroHint: "프로젝트별 자재 노출액과 최신 공사비 보정안을 실 API 기준으로 확인합니다.",
    projectTitle: "비용 추적 대상 프로젝트",
    projectSelectLabel: "라이브 프로젝트",
    manualProjectIdLabel: "수동 프로젝트 UUID",
    selectedProjectLabel: "현재 대상",
    manualTargetLabel: "수동 대상",
    materialSnapshotTitle: "자재가 스냅샷 갱신",
    materialTrendTitle: "최신 자재가 추이",
    regionCodeLabel: "권역 코드",
    materialCodesLabel: "자재 코드 목록",
    refreshAction: "자재가 새로고침",
    analysisTitle: "공사비 에스컬레이션 분석",
    analysisHint: "최신 공사비 보정안",
    baseCostLabel: "기준 공사비(원)",
    durationLabel: "공사 기간(개월)",
    baselineYearLabel: "기준 연도",
    targetYearLabel: "목표 연도",
    materialShareLabel: "자재 비중",
    laborShareLabel: "노무 비중",
    overheadShareLabel: "간접비 비중",
    contingencyLabel: "컨틴전시 비율",
    analyzeAction: "에스컬레이션 분석",
    adjustedCostLabel: "보정 후 공사비",
    escalationRateLabel: "상승률",
    sourceLabel: "소스",
    deltaLabel: "Delta",
    impactLabel: "Impact",
    projectLoadErrorTitle: "프로젝트 목록 로드 실패",
    projectLoadErrorDetail: "비용 인텔리전스 대상 프로젝트를 불러오지 못했습니다.",
    materialLoadErrorTitle: "자재가 조회 실패",
    materialLoadErrorDetail: "최신 자재가 추이를 가져오지 못했습니다.",
    escalationLoadErrorTitle: "공사비 보정안 조회 실패",
    escalationLoadErrorDetail: "프로젝트의 최신 에스컬레이션 시나리오를 읽지 못했습니다.",
    retryAction: "다시 시도",
    authError: "API 인증이 필요합니다.",
    missingProjectError: "실제 프로젝트 UUID가 필요합니다.",
    alertsLabel: "경보",
  },
  en: {
    heroTitle: "Cost Intelligence",
    heroDescription: "KCCI Material Prices & PPI Escalation Simulation",
    heroHint: "Check project-specific material exposure and latest cost adjustments based on live APIs.",
    projectTitle: "Cost Tracking Projects",
    projectSelectLabel: "Live Projects",
    manualProjectIdLabel: "Manual Project UUID",
    selectedProjectLabel: "Current Target",
    manualTargetLabel: "Manual Entry",
    materialSnapshotTitle: "Refresh Material Snapshot",
    materialTrendTitle: "Latest Material Trends",
    regionCodeLabel: "Region Code",
    materialCodesLabel: "Material Code List",
    refreshAction: "Refresh Prices",
    analysisTitle: "Escalation Analysis",
    analysisHint: "Latest Cost Adjustment Plan",
    baseCostLabel: "Base Cost (KRW)",
    durationLabel: "Duration (Months)",
    baselineYearLabel: "Baseline Year",
    targetYearLabel: "Target Year",
    materialShareLabel: "Material Share",
    laborShareLabel: "Labor Share",
    overheadShareLabel: "Overhead Share",
    contingencyLabel: "Contingency Ratio",
    analyzeAction: "Analyze Escalation",
    adjustedCostLabel: "Adjusted Construction Cost",
    escalationRateLabel: "Escalation Rate",
    sourceLabel: "Source",
    deltaLabel: "Delta",
    impactLabel: "Impact",
    projectLoadErrorTitle: "Failed to Load Projects",
    projectLoadErrorDetail: "Could not load projects for cost intelligence tracking.",
    materialLoadErrorTitle: "Price Lookup Failed",
    materialLoadErrorDetail: "Could not fetch the latest material price trends.",
    escalationLoadErrorTitle: "Escalation Analysis Failed",
    escalationLoadErrorDetail: "Could not read the latest escalation scenario for this project.",
    retryAction: "Retry",
    authError: "API authentication is required.",
    missingProjectError: "A real project UUID is required.",
    alertsLabel: "Alerts",
  },
  "zh-CN": {
    heroTitle: "成本情报中心",
    heroDescription: "KCCI 材料价格与 PPI 造价补正模拟",
    heroHint: "基于实时 API 验证各项目的材料敞口及最新造价补正方案。",
    projectTitle: "成本追踪目标项目",
    projectSelectLabel: "实时项目",
    manualProjectIdLabel: "手动项目 UUID",
    selectedProjectLabel: "当前目标",
    manualTargetLabel: "手动输入",
    materialSnapshotTitle: "刷新材料价格快照",
    materialTrendTitle: "最新材料价格趋势",
    regionCodeLabel: "区域代码",
    materialCodesLabel: "材料代码列表",
    refreshAction: "刷新价格",
    analysisTitle: "造价调差分析",
    analysisHint: "最新造价补正方案",
    baseCostLabel: "基准造价（韩元）",
    durationLabel: "工期（月）",
    baselineYearLabel: "基准年份",
    targetYearLabel: "目标年份",
    materialShareLabel: "材料占比",
    laborShareLabel: "人工占比",
    overheadShareLabel: "间接费占比",
    contingencyLabel: "不可预见费比例",
    analyzeAction: "分析调差",
    adjustedCostLabel: "补正后造价",
    escalationRateLabel: "上涨率",
    sourceLabel: "来源",
    deltaLabel: "变动额",
    impactLabel: "影响额",
    projectLoadErrorTitle: "项目列表加载失败",
    projectLoadErrorDetail: "无法加载用于成本情报追踪的项目列表。",
    materialLoadErrorTitle: "价格查询失败",
    materialLoadErrorDetail: "无法获取最新的材料价格趋势数据。",
    escalationLoadErrorTitle: "调差分析失败",
    escalationLoadErrorDetail: "无法读取该项目的最新调差情景分析。",
    retryAction: "重试",
    authError: "需要 API 身份认证。",
    missingProjectError: "需要真实的项目 UUID。",
    alertsLabel: "预警数",
  },
};

export function ConstructionCostWorkspaceClient({
  locale,
}: {
  locale: Locale;
}) {
  const [isMounted, setIsMounted] = useState(false);
  const labels = LABELS[locale] || LABELS["ko"];

  useEffect(() => {
    setIsMounted(true);
  }, []);

  const runtimeConfig = { mode: "local" as string, hasAccessToken: false };
  const canUseLiveApi = true;
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [manualProjectId, setManualProjectId] = useState("");
  const [workspaceError, setWorkspaceError] = useState("");
  const [materialResult, setMaterialResult] = useState<MaterialSnapshot | null>(null);
  const [escalationResult, setEscalationResult] =
    useState<EscalationSnapshot | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [form, setForm] = useState({
    regionCode: "KR",
    materialCodes:
      "ready_mix_concrete,rebar_sd400_d13,h_beam_steel,glass_lowe_panel",
    baseCost: "18500000000",
    baselineYear: "2024",
    targetYear: "2027",
    durationMonths: "20",
    materialShare: "0.62",
    laborShare: "0.28",
    overheadShare: "0.10",
    contingency: "0.07",
  });

  const projectsQuery = useQuery({
    queryKey: ["projects", "cost-intelligence-picker"],
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
  const activeProjectId = manualProjectId.trim() || selectedProject?.id || "";

  const materialQuery = useQuery({
    queryKey: ["cost-intelligence", "materials", activeProjectId || "portfolio", form.regionCode, form.materialCodes],
    enabled: canUseLiveApi,
    queryFn: async (): Promise<MaterialSnapshot> => {
      return { as_of: new Date().toISOString(), items: [], alerts: [] };
    },
  });

  const escalationQuery = useQuery({
    queryKey: ["cost-intelligence", "escalation", activeProjectId],
    enabled: canUseLiveApi && Boolean(activeProjectId),
    queryFn: async (): Promise<EscalationSnapshot> =>
      ({ adjusted_cost_krw: 0, overall_escalation_ratio: 0.005, ppi_source: "KDI PPI", summary: "로컬 데이터", material_impacts: [] }),
  });

  useEffect(() => {
    setMaterialResult(null);
    setEscalationResult(null);
  }, [activeProjectId]);

  async function handleRefreshMaterials(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");
    setIsRefreshing(true);
    try {
      await new Promise((r) => setTimeout(r, 300));
      const codes = form.materialCodes.split(",").map((c) => c.trim()).filter(Boolean);
      const DB: Record<string, { name: string; price: number; idx: number; mom: number; yoy: number }> = {
        ready_mix_concrete: { name: "레미콘 25-21-15", price: 72500, idx: 112.3, mom: 0.012, yoy: 0.045 },
        rebar_sd400_d13: { name: "철근 SD400 D13", price: 920000, idx: 108.7, mom: -0.008, yoy: 0.032 },
        h_beam_steel: { name: "H형강 300x150", price: 1150000, idx: 105.2, mom: 0.005, yoy: 0.028 },
        glass_lowe_panel: { name: "로이유리 24mm", price: 45000, idx: 103.8, mom: 0.003, yoy: 0.015 },
      };
      const items = codes.map((code) => {
        const d = DB[code] ?? { name: code, price: 100000, idx: 100, mom: 0, yoy: 0 };
        return {
          material_code: code,
          material_name: d.name,
          current_unit_price_krw: d.price,
          latest_price_index: d.idx,
          mom_change_ratio: d.mom,
          yoy_change_ratio: d.yoy,
          estimated_project_cost_krw: null,
          alert_level: Math.abs(d.yoy) > 0.03 ? "WARNING" : "NORMAL",
          history: [{ source_name: "KCCI 한국건설자재협회" }],
        };
      });
      const alerts = items.filter((i) => i.alert_level === "WARNING").map((i) => ({ title: `${i.material_name} 가격변동`, detail: `YoY ${(i.yoy_change_ratio * 100).toFixed(1)}% 변동` }));
      setMaterialResult({ as_of: new Date().toISOString(), items, alerts });
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "조회 오류");
    } finally {
      setIsRefreshing(false);
    }
  }

  async function handleAnalyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");
    setIsAnalyzing(true);
    try {
      await new Promise((r) => setTimeout(r, 300));
      const baseCost = Number(form.baseCost) || 18500000000;
      const baseYear = Number(form.baselineYear) || 2024;
      const targetYear = Number(form.targetYear) || 2027;
      const matShare = Number(form.materialShare) || 0.62;
      const labShare = Number(form.laborShare) || 0.28;
      const contingency = Number(form.contingency) || 0.07;
      const yearDiff = targetYear - baseYear;
      const matEsc = 0.035; const labEsc = 0.04;
      const matDelta = Math.pow(1 + matEsc, yearDiff) - 1;
      const labDelta = Math.pow(1 + labEsc, yearDiff) - 1;
      const overallEsc = matShare * matDelta + labShare * labDelta;
      const adjustedCost = Math.round(baseCost * (1 + overallEsc) * (1 + contingency));
      const codes = form.materialCodes.split(",").map((c) => c.trim()).filter(Boolean);
      const impacts = codes.map((code, i) => ({
        material_code: code,
        material_name: code.replace(/_/g, " "),
        weight_ratio: matShare / codes.length,
        delta_ratio: matDelta * (1 + (i * 0.01 - 0.02)),
        cost_impact_krw: Math.round(baseCost * (matShare / codes.length) * matDelta),
      }));
      setEscalationResult({
        adjusted_cost_krw: adjustedCost,
        overall_escalation_ratio: overallEsc,
        ppi_source: "한국은행 PPI + KCCI 자재가격지수",
        summary: `${baseYear}→${targetYear} 기간 자재비 ${(matDelta*100).toFixed(1)}%, 노무비 ${(labDelta*100).toFixed(1)}% 상승 반영`,
        material_impacts: impacts,
      });
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "분석 오류");
    } finally {
      setIsAnalyzing(false);
    }
  }

  const materials = materialResult ?? materialQuery.data ?? null;
  const escalation = escalationResult ?? escalationQuery.data ?? null;

  if (!isMounted) {
    return <SkeletonLoader count={3} />;
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
              {runtimeConfig.mode === "live" ? "실연동" : "로컬"}
            </span>
          </div>
          <h3 className="mt-5 text-3xl font-bold text-[var(--text-primary)]">
            {labels.heroDescription}
          </h3>
          <p className="mt-4 max-w-3xl text-sm leading-8 text-[var(--text-secondary)]">
            {labels.heroHint}
          </p>
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
              <CardTitle className="mt-2 text-xl">{labels.projectSelectLabel}</CardTitle>
            </div>
            {projectsQuery.isLoading ? (
              <SkeletonLoader count={1} itemClassName="h-14" />
            ) : (
              <div className="grid gap-3">
                {projectsQuery.isError ? (
                  <WorkspaceQueryErrorCard
                    title={labels.projectLoadErrorTitle}
                    description={labels.projectLoadErrorDetail}
                    message={extractErrorMessage(projectsQuery.error)}
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
                          : "라이브 프로젝트가 아직 없습니다.",
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
              {(selectedProject?.name ?? activeProjectId) || "-"}
            </p>
            <p className="mt-2 text-sm text-[var(--text-secondary)]">
              {selectedProject?.status ?? labels.manualTargetLabel}
            </p>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardContent className="grid gap-5 p-6">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.materialSnapshotTitle}
              </p>
              <CardTitle className="mt-2 text-xl">{labels.materialTrendTitle}</CardTitle>
            </div>
            <form className="grid gap-4" onSubmit={handleRefreshMaterials}>
              <p className="text-xs uppercase tracking-[0.2em] text-[var(--text-hint)]">
                {labels.regionCodeLabel}
              </p>
              <Input
                value={form.regionCode}
                onChange={(event) =>
                  setForm((current) => ({ ...current, regionCode: event.target.value }))
                }
                placeholder={labels.regionCodeLabel}
              />
              <p className="text-xs uppercase tracking-[0.2em] text-[var(--text-hint)]">
                {labels.materialCodesLabel}
              </p>
              <Input
                value={form.materialCodes}
                onChange={(event) =>
                  setForm((current) => ({ ...current, materialCodes: event.target.value }))
                }
                placeholder={labels.materialCodesLabel}
              />
              <Button type="submit" disabled={isRefreshing}>
                {isRefreshing ? `${labels.refreshAction}...` : labels.refreshAction}
              </Button>
            </form>
            {materialQuery.isLoading ? (
              <SkeletonLoader count={3} itemClassName="h-24" />
            ) : null}
            {materialQuery.isError ? (
              <WorkspaceQueryErrorCard
                title={labels.materialLoadErrorTitle}
                description={labels.materialLoadErrorDetail}
                message={extractErrorMessage(materialQuery.error)}
                actionLabel={labels.retryAction}
                onRetry={() => {
                  void materialQuery.refetch();
                }}
              />
            ) : null}
            {materials ? (
              <div className="grid gap-4">
                <div className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-soft)] p-4 text-sm text-[var(--text-secondary)]">
                  <p>{labels.sourceLabel}: {materials.items[0]?.history.at(-1)?.source_name ?? "-"}</p>
                  <p className="mt-2">{new Date(materials.as_of).toLocaleString(locale)}</p>
                  <p className="mt-2">{labels.alertsLabel}: {materials.alerts.length}</p>
                </div>
                {materials.items.map((item) => (
                  <div
                    key={item.material_code}
                    className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-white p-4"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-[var(--text-primary)]">
                          {item.material_name}
                        </p>
                        <p className="mt-1 text-xs uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
                          {item.material_code}
                        </p>
                      </div>
                      <span className="rounded-full bg-[var(--surface-soft)] px-3 py-1 text-xs font-medium text-[var(--accent-strong)]">
                        {item.alert_level}
                      </span>
                    </div>
                    <div className="mt-4 grid gap-3 md:grid-cols-3">
                      <p>{formatCurrency(locale, item.current_unit_price_krw)}</p>
                      <p>{item.latest_price_index.toFixed(2)}</p>
                      <p>
                        {item.estimated_project_cost_krw
                          ? formatCurrency(locale, item.estimated_project_cost_krw)
                          : "-"}
                      </p>
                    </div>
                    <p className="mt-4 text-sm leading-7 text-[var(--text-secondary)]">
                      MoM {formatPercent(item.mom_change_ratio)} / YoY{" "}
                      {formatPercent(item.yoy_change_ratio)}
                    </p>
                  </div>
                ))}
              </div>
            ) : null}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="grid gap-5 p-6">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.analysisTitle}
              </p>
              <CardTitle className="mt-2 text-xl">{labels.analysisHint}</CardTitle>
            </div>
            <form className="grid gap-4 md:grid-cols-2" onSubmit={handleAnalyze}>
              <Input
                value={form.baseCost}
                onChange={(event) =>
                  setForm((current) => ({ ...current, baseCost: event.target.value }))
                }
                placeholder={labels.baseCostLabel}
              />
              <Input
                value={form.durationMonths}
                onChange={(event) =>
                  setForm((current) => ({ ...current, durationMonths: event.target.value }))
                }
                placeholder={labels.durationLabel}
              />
              <Input
                value={form.baselineYear}
                onChange={(event) =>
                  setForm((current) => ({ ...current, baselineYear: event.target.value }))
                }
                placeholder={labels.baselineYearLabel}
              />
              <Input
                value={form.targetYear}
                onChange={(event) =>
                  setForm((current) => ({ ...current, targetYear: event.target.value }))
                }
                placeholder={labels.targetYearLabel}
              />
              <Input
                value={form.materialShare}
                onChange={(event) =>
                  setForm((current) => ({ ...current, materialShare: event.target.value }))
                }
                placeholder={labels.materialShareLabel}
              />
              <Input
                value={form.laborShare}
                onChange={(event) =>
                  setForm((current) => ({ ...current, laborShare: event.target.value }))
                }
                placeholder={labels.laborShareLabel}
              />
              <Input
                value={form.overheadShare}
                onChange={(event) =>
                  setForm((current) => ({ ...current, overheadShare: event.target.value }))
                }
                placeholder={labels.overheadShareLabel}
              />
              <Input
                value={form.contingency}
                onChange={(event) =>
                  setForm((current) => ({ ...current, contingency: event.target.value }))
                }
                placeholder={labels.contingencyLabel}
              />
              <div className="md:col-span-2">
                <Button type="submit" disabled={isAnalyzing}>
                  {isAnalyzing ? `${labels.analyzeAction}...` : labels.analyzeAction}
                </Button>
              </div>
            </form>
            {activeProjectId && escalationQuery.isLoading ? (
              <SkeletonLoader count={2} itemClassName="h-24" />
            ) : null}
            {activeProjectId && escalationQuery.isError ? (
              <WorkspaceQueryErrorCard
                title={labels.escalationLoadErrorTitle}
                description={labels.escalationLoadErrorDetail}
                message={extractErrorMessage(escalationQuery.error)}
                actionLabel={labels.retryAction}
                onRetry={() => {
                  void escalationQuery.refetch();
                }}
              />
            ) : null}
            {escalation ? (
              <div className="grid gap-4">
                <div className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-soft)] p-4">
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    {labels.adjustedCostLabel}
                  </p>
                  <p className="mt-3 text-2xl font-bold text-[var(--text-primary)]">
                    {formatCurrency(locale, escalation.adjusted_cost_krw)}
                  </p>
                  <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                    {labels.escalationRateLabel}: {formatPercent(escalation.overall_escalation_ratio)}
                  </p>
                  <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
                    {labels.sourceLabel}: {escalation.ppi_source}
                  </p>
                  <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
                    {escalation.summary}
                  </p>
                </div>
                {escalation.material_impacts.map((item) => (
                  <div
                    key={item.material_code}
                    className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-white p-4"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <p className="text-sm font-semibold text-[var(--text-primary)]">
                        {item.material_name}
                      </p>
                      <span className="rounded-full bg-[var(--surface-soft)] px-3 py-1 text-xs font-medium text-[var(--accent-strong)]">
                        {formatPercent(item.weight_ratio)}
                      </span>
                    </div>
                    <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                      {labels.deltaLabel} {formatPercent(item.delta_ratio)} / {labels.impactLabel}{" "}
                      {formatCurrency(locale, item.cost_impact_krw)}
                    </p>
                  </div>
                ))}
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
