"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardTitle } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { ApiClientError, apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";
import { useDictionary } from "@/hooks/use-dictionary";
import { formatCurrencyKRW } from "@/lib/formatters";

// Zustand store and new components
import { useGenerationStore } from "@/store/useGenerationStore";
import { ProjectGenerationWizard } from "./ProjectGenerationWizard";
import { GenerationMonitorConsole } from "./GenerationMonitorConsole";

type ProjectResponse = {
  id: string;
  name: string;
  status: string;
  address: string | null;
  total_area_sqm: number | null;
  created_at: string;
  updated_at: string;
};

type Labels = {
  heroTitle: string;
  heroDescription: string;
  heroHint: string;
  tokenHint: string;
  authError: string;
  contextTitle: string;
  contextHint: string;
  projectFallback: string;
  floorPlanResultTitle: string;
  fileUrlLabel: string;
  generationMethodLabel: string;
  bimResultTitle: string;
  totalVolumeLabel: string;
  elementCountLabel: string;
  ifcVersionLabel: string;
  carbonTitle: string;
  totalCarbonLabel: string;
  embodiedCarbonLabel: string;
  operationalCarbonLabel: string;
  reductionTipsLabel: string;
  placeholder: string;
  projectLoadErrorTitle: string;
  projectLoadErrorDetail: string;
  retryAction: string;
  
  // New metrics labels
  estimatedCostLabel: string;
  feasibilityScoreLabel: string;
};

const COMMON_LABELS: Labels = {
  heroTitle: "Project design live workspace",
  heroDescription:
    "Generate floor-plan outputs and auto-IFC analysis for the current project route through the live design and BIM APIs.",
  heroHint:
    "This route binds the project id from the URL to the advanced orchestration engine based on Project Generation Sets.",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "API authentication is required for live workspace calls.",
  contextTitle: "Project context",
  contextHint:
    "Project metadata is loaded from the live API and used to prefill area-driven generation settings.",
  projectFallback: "Project metadata could not be loaded from the live API.",
  floorPlanResultTitle: "Floor plan result",
  fileUrlLabel: "File URL",
  generationMethodLabel: "Generation method",
  bimResultTitle: "BIM quantity result",
  totalVolumeLabel: "Total volume",
  elementCountLabel: "Element count",
  ifcVersionLabel: "IFC version",
  carbonTitle: "Carbon analysis",
  totalCarbonLabel: "Total carbon",
  embodiedCarbonLabel: "Embodied carbon",
  operationalCarbonLabel: "Operational carbon",
  reductionTipsLabel: "Reduction tips",
  placeholder:
    "Select a Project Generation Set template and submit parameters to run the AI engine chain.",
  projectLoadErrorTitle: "Project metadata unavailable",
  projectLoadErrorDetail:
    "The routed project context failed to load. Retry to restore design autofill and status context.",
  retryAction: "Retry",
  estimatedCostLabel: "Est. Construction Cost",
  feasibilityScoreLabel: "Feasibility Score",
};

const LABELS: Record<Locale, Labels> = {
  ko: {
    heroTitle: "설계 AI 및 BIM 라이브 작업 공간",
    heroDescription: "현재 프로젝트의 평면도 생성 및 자동 IFC 분석을 AI 엔진을 통해 실시간으로 수행합니다.",
    heroHint: "본 화면은 프로젝트 ID를 기반으로 프로젝트 생성세트에 맞춰 AI 평면 설계, BIM 합성, 탄소 분석을 통합 구동합니다.",
    tokenHint: "분석을 위해 로그인이 필요합니다.",
    authError: "라이브 작업 공간 기능을 사용하기 위해 API 인증이 필요합니다.",
    contextTitle: "프로젝트 컨텍스트",
    contextHint: "라이브 API에서 로드된 프로젝트 메타데이터를 기반으로 최적화된 설계 설정을 자동으로 제안합니다.",
    projectFallback: "라이브 API에서 프로젝트 메타데이터를 불러오지 못했습니다.",
    floorPlanResultTitle: "평면도 생성 결과",
    fileUrlLabel: "도면 파일 URL",
    generationMethodLabel: "생성 엔진 알고리즘",
    bimResultTitle: "BIM 수량 산출 결과",
    totalVolumeLabel: "총 체적",
    elementCountLabel: "객체(Element) 수",
    ifcVersionLabel: "IFC 버전",
    carbonTitle: "LCA 탄소 배출 분석",
    totalCarbonLabel: "총 탄소 배출량",
    embodiedCarbonLabel: "내재 탄소 (Embodied)",
    operationalCarbonLabel: "운영 탄소 (Operational)",
    reductionTipsLabel: "탄소 저감 권고안",
    placeholder: "원하는 프로젝트 생성세트 템플릿을 선택하고 변수를 조정하여 AI 통합 생성을 구동해 보세요.",
    projectLoadErrorTitle: "데이터 로드 실패",
    projectLoadErrorDetail: "프로젝트 컨텍스트를 불러오지 못했습니다. 다시 시도하여 상태를 갱신하세요.",
    retryAction: "다시 시도",
    estimatedCostLabel: "예상 총공사비",
    feasibilityScoreLabel: "사업 타당성 지수",
  },
  en: COMMON_LABELS,
  "zh-CN": {
    heroTitle: "设计 AI 和 BIM 实时工作区",
    heroDescription: "通过 AI 引擎实时生成当前项目的平面图并进行自动 IFC 分析。",
    heroHint: "此页面基于项目 ID，结合项目生成集，统一驱动 AI 平面设计、BIM 合成与碳排放分析。",
    tokenHint: "实时 API 调用需要 NEXT_PUBLIC_API_ACCESS_TOKEN 或本地安全令牌。",
    authError: "使用实时工作区功能需要 API 身份验证。",
    contextTitle: "项目上下文",
    contextHint: "基于从实时 API 加载的项目元数据，自动建议优化的设计设置。",
    projectFallback: "无法从实时 API 加载项目元数据。",
    floorPlanResultTitle: "平面图生成结果",
    fileUrlLabel: "图纸文件 URL",
    generationMethodLabel: "生成引擎算法",
    bimResultTitle: "BIM 工程量计算结果",
    totalVolumeLabel: "总体积",
    elementCountLabel: "构件 (Element) 数量",
    ifcVersionLabel: "IFC 版本",
    carbonTitle: "LCA 碳排放分析",
    totalCarbonLabel: "总碳排放量",
    embodiedCarbonLabel: "隐含碳 (Embodied)",
    operationalCarbonLabel: "运营碳 (Operational)",
    reductionTipsLabel: "碳减排建议",
    placeholder: "选择所需的项目生成集模板并调整变量，以启动 AI 综合生成链。",
    projectLoadErrorTitle: "数据加载失败",
    projectLoadErrorDetail: "无法加载项目上下文。请重试以更新状态。",
    retryAction: "重试",
    estimatedCostLabel: "预计总工程造价",
    feasibilityScoreLabel: "项目可行性指数",
  },
};

function formatDate(locale: string, value: string) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatNumber(locale: string, value: number) {
  return new Intl.NumberFormat(locale, {
    maximumFractionDigits: 2,
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

export function ProjectDesignWorkspaceClient({
  locale,
  projectId,
}: {
  locale: Locale;
  projectId: string;
}) {
  const { dictionary } = useDictionary(locale);
  const labels = LABELS[locale] || LABELS["ko"];
  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi = runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  const { results, isGenerating } = useGenerationStore();

  const projectQuery = useQuery({
    queryKey: ["projects", "detail", projectId, "design-live"],
    enabled: canUseLiveApi,
    queryFn: () =>
      apiClient.get<ProjectResponse>(`/projects/${projectId}`, {
        useMock: false,
      }),
  });

  const projectError = projectQuery.error
    ? extractErrorMessage(projectQuery.error, labels.authError)
    : "";

  const areaValue = projectQuery.data?.total_area_sqm || 1500;
  // Default floors calculation if empty in metadata
  const floorsValue = 12;

  if (!dictionary) {
    return <SkeletonLoader count={3} />;
  }

  return (
    <section className="grid gap-6">
      {/* ── Main Hero Dashboard Header ── */}
      <Card className="rounded-[var(--radius-2xl)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)] relative overflow-hidden group">
        <div className="absolute top-0 right-0 w-64 h-64 bg-[var(--accent-strong)]/5 blur-[80px] rounded-full transition-all duration-1000 group-hover:bg-[var(--accent-strong)]/10" />
        <CardContent className="p-8 relative z-10">
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-[var(--accent-soft)] px-4 py-2 text-[10px] font-black uppercase tracking-[0.2em] text-[var(--accent-strong)] border border-[var(--accent-strong)]/10">
              {labels.heroTitle}
            </span>
            <span className="rounded-full border border-[var(--line-strong)] px-4 py-2 text-[10px] font-black tracking-widest text-[var(--text-hint)] uppercase">
              {runtimeConfig.mode === "live" ? "LIVE ENGINE" : "HYBRID SIMULATOR"}
            </span>
          </div>
          <h3 className="mt-5 text-3xl font-black tracking-tight text-[var(--text-primary)]">
            {labels.heroDescription}
          </h3>
          <p className="mt-4 max-w-3xl text-sm leading-7 text-[var(--text-secondary)] font-medium">
            {labels.heroHint}
          </p>
          <p className="mt-3 max-w-3xl text-xs leading-6 text-[var(--text-hint)] font-mono">
            {labels.tokenHint}
          </p>
          {!canUseLiveApi ? (
            <div className="mt-6 rounded-2xl border border-dashed border-[var(--line)] bg-[var(--surface-soft)]/50 p-5 text-xs font-semibold leading-relaxed text-[var(--text-secondary)]">
              {labels.authError} (현재 매개변수 가중치 매핑이 내장된 하이브리드 시뮬레이션 엔진이 활성화되었습니다.)
            </div>
          ) : null}
          {projectError ? (
            <div className="mt-6">
              <WorkspaceQueryErrorCard
                title={labels.projectLoadErrorTitle}
                description={labels.projectLoadErrorDetail}
                message={projectError}
                actionLabel={labels.retryAction}
                onRetry={() => {
                  void projectQuery.refetch();
                }}
              />
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* ── Control Plane (Project Context & Parameter Wizard) ── */}
      <Card className="border-[var(--line-strong)]">
        <CardContent className="grid gap-8 p-6 lg:grid-cols-[0.9fr_1.1fr]">
          {/* Project Context View */}
          <div className="flex flex-col justify-between gap-6 border-b lg:border-b-0 lg:border-r border-[var(--line-strong)]/50 pb-6 lg:pb-0 lg:pr-8">
            <div className="space-y-4">
              <p className="text-[10px] font-black uppercase tracking-[0.24em] text-[var(--text-hint)]">
                {labels.contextTitle}
              </p>
              <CardTitle className="text-xl font-black text-[var(--text-primary)] leading-snug">
                {labels.contextHint}
              </CardTitle>
              {projectQuery.isLoading ? (
                <SkeletonLoader count={1} itemClassName="h-32 rounded-2xl" />
              ) : (
                <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5 relative overflow-hidden">
                  <div className="absolute top-0 right-0 w-24 h-24 bg-blue-500/5 blur-[40px] rounded-full" />
                  <p className="text-sm font-black text-[var(--text-primary)]">
                    {projectQuery.data?.name ?? "성수 IT 밸리 복합개발"}
                  </p>
                  <p className="mt-2 font-mono text-[10px] text-[var(--text-hint)] break-all select-all">
                    UUID: {projectId}
                  </p>
                  {projectQuery.data?.address && (
                    <p className="mt-3 text-xs text-[var(--text-secondary)] font-medium">
                      {projectQuery.data.address}
                    </p>
                  )}
                  <div className="mt-4 flex flex-wrap gap-4 text-[10px] font-black uppercase tracking-wider text-[var(--text-hint)]">
                    <span>STATUS: {projectQuery.data?.status || "PLANNING"}</span>
                    <span>·</span>
                    <span>AREA: {formatNumber(locale, areaValue)} ㎡</span>
                    <span>·</span>
                    <span>FLOORS: {floorsValue} EA</span>
                  </div>
                </div>
              )}
            </div>

            {/* Live Monitor Console Wires */}
            <div className="mt-4">
              <GenerationMonitorConsole dictionary={dictionary} />
            </div>
          </div>

          {/* Dynamic Generator Parameters Wizard */}
          <div>
            <ProjectGenerationWizard
              dictionary={dictionary}
              projectId={projectId}
              areaSqm={areaValue}
              floors={floorsValue}
            />
          </div>
        </CardContent>
      </Card>

      {/* ── Output Deliverables Hub ── */}
      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        {/* Floor Plan Image Deliverable */}
        <Card className="border-[var(--line-strong)]">
          <CardContent className="p-6">
            <p className="text-[10px] font-black uppercase tracking-[0.24em] text-[var(--text-hint)] mb-4">
              {labels.floorPlanResultTitle}
            </p>
            {results ? (
              <div className="space-y-4">
                <MetricTile
                  label={labels.generationMethodLabel}
                  value={results.cadFloorPlanUrl ? "AI Parametric Vector Mesh Engine" : "Hybrid Simulator"}
                />
                
                {/* 2D Vector CAD View Frame */}
                <div className="relative rounded-[2rem] border border-[var(--line-strong)] overflow-hidden aspect-[3/2] bg-[var(--surface-soft)] flex items-center justify-center group/floor">
                  <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/grid.png')] opacity-10 pointer-events-none" />
                  <img
                    src={results.cadFloorPlanUrl}
                    alt="AI Floor Plan"
                    className="object-cover w-full h-full opacity-90 transition-transform duration-700 group-hover/floor:scale-105"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/40 to-transparent pointer-events-none" />
                  <span className="absolute bottom-4 left-6 text-[10px] font-black tracking-widest text-white/95 uppercase bg-[var(--surface-strong)]/80 backdrop-blur-md px-3 py-1.5 rounded-xl border border-white/10">
                    2D VECTOR_MAP VIEW
                  </span>
                </div>

                <div className="grid gap-4.5 md:grid-cols-2">
                  <MetricTile
                    label={labels.fileUrlLabel}
                    value={results.ifcFileUrl}
                    allowSelect
                  />
                  <MetricTile
                    label={labels.ifcVersionLabel}
                    value={results.ifcVersion}
                  />
                </div>
              </div>
            ) : (
              <div className="rounded-[2rem] border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)]/50 p-8 text-center text-xs font-semibold leading-relaxed text-[var(--text-hint)] h-[240px] flex items-center justify-center">
                {labels.placeholder}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Quantities & Environmental Dashboard */}
        <div className="grid gap-6">
          {/* Business Feasibility Stat Cards */}
          {results && (
            <div className="grid gap-4.5 md:grid-cols-2">
              <Card className="bg-gradient-to-r from-[var(--surface-strong)] to-[var(--surface-soft)] border-[var(--accent-strong)]/20 shadow-[0_0_20px_rgba(45,212,191,0.05)] border-2">
                <CardContent className="p-6">
                  <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)] mb-2">
                    {labels.estimatedCostLabel}
                  </p>
                  <p className="text-3xl font-[1000] tracking-tight text-[var(--text-primary)]">
                    {formatCurrencyKRW(results.estimatedCost)}
                  </p>
                  <p className="mt-2 text-[9px] font-black text-[var(--text-hint)] uppercase tracking-wider">
                    Computed based on standard raw material index
                  </p>
                </CardContent>
              </Card>

              <Card className="bg-gradient-to-r from-[var(--surface-strong)] to-[var(--surface-soft)] border-[var(--accent-strong)]/20 shadow-[0_0_20px_rgba(45,212,191,0.05)] border-2">
                <CardContent className="p-6">
                  <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)] mb-2">
                    {labels.feasibilityScoreLabel}
                  </p>
                  <p className="text-3xl font-[1000] tracking-tight text-[var(--accent-strong)] shadow-[var(--shadow-glow)]">
                    {results.feasibilityScore} / 100
                  </p>
                  <p className="mt-2 text-[9px] font-black text-[var(--text-hint)] uppercase tracking-wider">
                    Dynamic IRR/ROI Sensitivity Weighted
                  </p>
                </CardContent>
              </Card>
            </div>
          )}

          {/* BIM Volume Results */}
          <Card className="border-[var(--line-strong)]">
            <CardContent className="p-6">
              <p className="text-[10px] font-black uppercase tracking-[0.24em] text-[var(--text-hint)] mb-4">
                {labels.bimResultTitle}
              </p>
              {results ? (
                <div className="grid gap-4 md:grid-cols-3">
                  <MetricTile
                    label="Total GFA"
                    value={`${formatNumber(locale, results.totalAreaSqm)} ㎡`}
                  />
                  <MetricTile
                    label={labels.totalVolumeLabel}
                    value={`${formatNumber(locale, results.totalVolumeM3)} ㎥`}
                  />
                  <MetricTile
                    label={labels.elementCountLabel}
                    value={`${results.elementCount} EA`}
                  />
                </div>
              ) : (
                <div className="rounded-[2rem] border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)]/50 p-6 text-center text-xs font-semibold text-[var(--text-hint)]">
                  {labels.placeholder}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Environmental Carbon LCA Results */}
          <Card className="border-[var(--line-strong)]">
            <CardContent className="p-6">
              <p className="text-[10px] font-black uppercase tracking-[0.24em] text-[var(--text-hint)] mb-4">
                {labels.carbonTitle}
              </p>
              {results ? (
                <div className="space-y-5">
                  <div className="grid gap-4.5 md:grid-cols-3">
                    <MetricTile
                      label={labels.totalCarbonLabel}
                      value={`${formatNumber(locale, results.totalCarbon)} kg CO₂-eq`}
                    />
                    <MetricTile
                      label={labels.embodiedCarbonLabel}
                      value={`${formatNumber(locale, results.embodiedCarbon)} kg CO₂-eq`}
                    />
                    <MetricTile
                      label={labels.operationalCarbonLabel}
                      value={`${formatNumber(locale, results.operationalCarbon)} kg CO₂-eq`}
                    />
                  </div>
                  
                  {/* AI Cost/Carbon Optimization reduction tips */}
                  <div className="rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-soft)]/50 p-6">
                    <p className="text-[10px] font-black uppercase tracking-[0.2em] text-[var(--text-hint)]">
                      {labels.reductionTipsLabel}
                    </p>
                    {results.reductionTips?.length ? (
                      <ul className="mt-3.5 space-y-2.5 text-xs font-medium leading-relaxed text-[var(--text-secondary)] list-inside list-disc">
                        {(results.reductionTips ?? []).map((tip, i) => (
                          <li key={i} className="hover:text-[var(--text-primary)] transition-colors">
                            {tip}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-3 text-xs leading-relaxed text-[var(--text-hint)]">-</p>
                    )}
                  </div>
                </div>
              ) : (
                <div className="rounded-[2rem] border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)]/50 p-6 text-center text-xs font-semibold text-[var(--text-hint)]">
                  {labels.placeholder}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </section>
  );
}

function MetricTile({
  label,
  value,
  allowSelect = false,
}: {
  label: string;
  value: string;
  allowSelect?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5 relative overflow-hidden group">
      <div className="absolute top-0 right-0 w-12 h-12 bg-[var(--accent-strong)]/2 blur-[20px] rounded-full" />
      <p className="text-[9px] font-black uppercase tracking-[0.24em] text-[var(--text-hint)] mb-2.5">
        {label}
      </p>
      <p className={`text-xs font-bold text-[var(--text-primary)] break-all ${allowSelect ? "select-all font-mono text-[10px]" : ""}`}>
        {value}
      </p>
    </div>
  );
}
