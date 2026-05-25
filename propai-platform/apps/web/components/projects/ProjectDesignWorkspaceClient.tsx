"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, CardTitle, Input, Select } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { ApiClientError, apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";

type ProjectResponse = {
  id: string;
  name: string;
  status: string;
  address: string | null;
  total_area_sqm: number | null;
  created_at: string;
  updated_at: string;
};

type FloorPlanResponse = {
  design_id: string;
  file_url: string;
  room_count: number;
  generation_method: string;
  vision_validation?: {
    detected_rooms?: number;
    expected_rooms?: number;
    confidence?: number;
    match?: boolean;
  };
};

type BIMQuantityResponse = {
  id: string;
  project_id: string;
  total_volume_m3: number;
  total_area_sqm: number;
  material_breakdown: Array<Record<string, unknown>>;
  element_count: number;
  ifc_version: string;
  created_at: string;
};

type CarbonCalculationResponse = {
  total_embodied_carbon: number;
  total_operational_carbon: number;
  total_carbon: number;
  breakdown: Array<Record<string, unknown>>;
  reduction_tips: string[];
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
  floorPlanTitle: string;
  areaLabel: string;
  roomCountLabel: string;
  styleLabel: string;
  generateFloorPlanAction: string;
  ifcTitle: string;
  totalAreaLabel: string;
  floorsLabel: string;
  structureLabel: string;
  generateIfcAction: string;
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
  missingAreaError: string;
  missingRoomCountError: string;
  missingFloorsError: string;
  placeholder: string;
  projectLoadErrorTitle: string;
  projectLoadErrorDetail: string;
  retryAction: string;
};

const COMMON_LABELS: Labels = {
  heroTitle: "Project design live workspace",
  heroDescription:
    "Generate floor-plan outputs and auto-IFC analysis for the current project route through the live design and BIM APIs.",
  heroHint:
    "This route binds the project id from the URL to `POST /design/floor-plan`, `POST /bim/generate-ifc`, and `POST /bim/carbon`.",
  tokenHint:
    "Live API calls require NEXT_PUBLIC_API_ACCESS_TOKEN or localStorage.propai_access_token.",
  authError: "API authentication is required for live workspace calls.",
  contextTitle: "Project context",
  contextHint:
    "Project metadata is loaded from the live API and used to prefill area-driven generation settings.",
  projectFallback: "Project metadata could not be loaded from the live API.",
  floorPlanTitle: "Floor plan generation",
  areaLabel: "Area (sqm)",
  roomCountLabel: "Room count",
  styleLabel: "Style",
  generateFloorPlanAction: "Generate floor plan",
  ifcTitle: "Auto IFC and carbon analysis",
  totalAreaLabel: "Total area (sqm)",
  floorsLabel: "Floors",
  structureLabel: "Structure type",
  generateIfcAction: "Generate IFC and carbon",
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
  missingAreaError: "A positive area value is required.",
  missingRoomCountError: "A positive room count is required.",
  missingFloorsError: "A positive floor count is required.",
  placeholder:
    "Submit floor-plan or IFC generation to validate the design and BIM response chain for this project route.",
  projectLoadErrorTitle: "Project metadata unavailable",
  projectLoadErrorDetail:
    "The routed project context failed to load from the live API. Retry to restore design autofill and status context.",
  retryAction: "Retry",
};

const LABELS: Record<Locale, Labels> = {
  ko: {
    heroTitle: "설계 AI 및 BIM 라이브 워크스페이스",
    heroDescription: "현재 프로젝트의 평면도 생성 및 자동 IFC 분석을 AI 엔진을 통해 실시간으로 수행합니다.",
    heroHint: "본 화면은 프로젝트 ID를 기반으로 `평면도 생성`, `IFC 물량 산출`, `탄소 배출량 분석` API와 가동됩니다.",
    tokenHint: "라이브 API 호출에는 NEXT_PUBLIC_API_ACCESS_TOKEN 또는 로컬 보안 토큰이 필요합니다.",
    authError: "라이브 워크스페이스 기능을 사용하기 위해 API 인증이 필요합니다.",
    contextTitle: "프로젝트 컨텍스트",
    contextHint: "라이브 API에서 로드된 프로젝트 메타데이터를 기반으로 최적화된 설계 설정을 자동으로 제안합니다.",
    projectFallback: "라이브 API에서 프로젝트 메타데이터를 불러오지 못했습니다.",
    floorPlanTitle: "AI 평면도 생성",
    areaLabel: "면적 (m²)",
    roomCountLabel: "방 개수",
    styleLabel: "디자인 스타일",
    generateFloorPlanAction: "평면도 생성 시작",
    ifcTitle: "자동 IFC 및 탄소 배출 분석",
    totalAreaLabel: "연면적 (m²)",
    floorsLabel: "층수",
    structureLabel: "구조 형식",
    generateIfcAction: "BIM 수량 및 탄소 분석 실행",
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
    missingAreaError: "양의 면적 값을 입력해주세요.",
    missingRoomCountError: "양의 방 개수를 입력해주세요.",
    missingFloorsError: "양의 층수 값을 입력해주세요.",
    placeholder: "평면도 생성 또는 IFC 분석을 실행하여 실시간 응답 체인을 확인하세요.",
    projectLoadErrorTitle: "데이터 로드 실패",
    projectLoadErrorDetail: "프로젝트 컨텍스트를 불러오지 못했습니다. 다시 시도하여 상태를 갱신하세요.",
    retryAction: "다시 시도",
  },
  en: COMMON_LABELS,
  "zh-CN": {
    heroTitle: "设计 AI 和 BIM 实时工作区",
    heroDescription: "通过 AI 引擎实时生成当前项目的平面图并进行自动 IFC 分析。",
    heroHint: "此页面基于项目 ID 驱动“平面图生成”、“IFC 工程量计算”和“碳排放分析” API。",
    tokenHint: "实时 API 调用需要 NEXT_PUBLIC_API_ACCESS_TOKEN 或本地安全令牌。",
    authError: "使用实时工作区功能需要 API 身份验证。",
    contextTitle: "项目上下文",
    contextHint: "基于从实时 API 加载的项目元数据，自动建议优化的设计设置。",
    projectFallback: "无法从实时 API 加载项目元数据。",
    floorPlanTitle: "AI 平面图生成",
    areaLabel: "面积 (m²)",
    roomCountLabel: "房间数量",
    styleLabel: "设计风格",
    generateFloorPlanAction: "开始生成平面图",
    ifcTitle: "自动 IFC 和碳排放分析",
    totalAreaLabel: "总建筑面积 (m²)",
    floorsLabel: "层数",
    structureLabel: "结构形式",
    generateIfcAction: "执行 BIM 工程量和碳分析",
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
    missingAreaError: "请输入正数面积值。",
    missingRoomCountError: "请输入正数房间数量。",
    missingFloorsError: "请输入正数层数值。",
    placeholder: "执行平面图生成或 IFC 分析以查看实时响应链。",
    projectLoadErrorTitle: "数据加载失败",
    projectLoadErrorDetail: "无法加载项目上下文。请重试以更新状态。",
    retryAction: "重试",
  },
};

const STYLE_OPTIONS = [
  { label: "Modern", value: "modern" },
  { label: "Minimal", value: "minimal" },
  { label: "Classic", value: "classic" },
];

const STRUCTURE_OPTIONS = [
  { label: "RC", value: "RC" },
  { label: "SRC", value: "SRC" },
  { label: "SC", value: "SC" },
];

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
  const labels = LABELS[locale];
  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  const [workspaceError, setWorkspaceError] = useState("");
  const [isGeneratingPlan, setIsGeneratingPlan] = useState(false);
  const [isGeneratingIfc, setIsGeneratingIfc] = useState(false);
  const [floorPlanResult, setFloorPlanResult] = useState<FloorPlanResponse | null>(
    null,
  );
  const [bimResult, setBimResult] = useState<BIMQuantityResponse | null>(null);
  const [carbonResult, setCarbonResult] =
    useState<CarbonCalculationResponse | null>(null);
  const [planForm, setPlanForm] = useState({
    areaSqm: "",
    roomCount: "3",
    style: "modern",
  });
  const [ifcForm, setIfcForm] = useState({
    totalAreaSqm: "",
    floors: "12",
    structureType: "RC",
  });

  const projectQuery = useQuery({
    queryKey: ["projects", "detail", projectId, "design-live"],
    enabled: canUseLiveApi,
    queryFn: () =>
      apiClient.get<ProjectResponse>(`/projects/${projectId}`, {
        useMock: false,
      }),
  });

  useEffect(() => {
    if (projectQuery.data?.total_area_sqm == null) {
      return;
    }

    const totalArea = String(projectQuery.data.total_area_sqm);
    setPlanForm((current) => ({
      ...current,
      areaSqm: current.areaSqm || totalArea,
    }));
    setIfcForm((current) => ({
      ...current,
      totalAreaSqm: current.totalAreaSqm || totalArea,
    }));
  }, [projectQuery.data]);

  const projectError = projectQuery.error
    ? extractErrorMessage(projectQuery.error, labels.authError)
    : "";

  async function handleGenerateFloorPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");

    const areaSqm = Number(planForm.areaSqm);
    const roomCount = Number(planForm.roomCount);

    if (!Number.isFinite(areaSqm) || areaSqm <= 0) {
      setWorkspaceError(labels.missingAreaError);
      return;
    }

    if (!Number.isFinite(roomCount) || roomCount <= 0) {
      setWorkspaceError(labels.missingRoomCountError);
      return;
    }

    setIsGeneratingPlan(true);

    try {
      const response = await apiClient.post<FloorPlanResponse>(
        "/design/floor-plan",
        {
          useMock: false,
          body: {
            project_id: projectId,
            area_sqm: areaSqm,
            room_count: roomCount,
            style: planForm.style,
          },
        },
      );

      setFloorPlanResult(response);
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsGeneratingPlan(false);
    }
  }

  async function handleGenerateIfc(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");

    const totalAreaSqm = Number(ifcForm.totalAreaSqm);
    const floors = Number(ifcForm.floors);

    if (!Number.isFinite(totalAreaSqm) || totalAreaSqm <= 0) {
      setWorkspaceError(labels.missingAreaError);
      return;
    }

    if (!Number.isFinite(floors) || floors <= 0) {
      setWorkspaceError(labels.missingFloorsError);
      return;
    }

    setIsGeneratingIfc(true);

    try {
      const bim = await apiClient.post<BIMQuantityResponse>("/bim/generate-ifc", {
        useMock: false,
        body: {
          project_id: projectId,
          total_area_sqm: totalAreaSqm,
          floors,
          structure_type: ifcForm.structureType,
        },
      });

      const carbon = await apiClient.post<CarbonCalculationResponse>(
        "/bim/carbon",
        {
          useMock: false,
          body: {
            project_id: projectId,
            material_breakdown: bim.material_breakdown,
            total_area_sqm: bim.total_area_sqm,
          },
        },
      );

      setBimResult(bim);
      setCarbonResult(carbon);
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsGeneratingIfc(false);
    }
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
          {workspaceError ? (
            <div className="mt-6 rounded-[var(--radius-xl)] border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] p-5 text-sm leading-7 text-[var(--spot)]">
              {workspaceError}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="grid gap-5 p-6 lg:grid-cols-[0.95fr_1.05fr]">
          <div className="grid gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.contextTitle}
              </p>
              <CardTitle className="mt-2 text-xl">{labels.contextHint}</CardTitle>
            </div>
            {projectQuery.isLoading ? (
              <SkeletonLoader count={1} itemClassName="h-28" />
            ) : (
              <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                <p className="text-sm font-semibold text-[var(--text-primary)]">
                  {projectQuery.data?.name ?? labels.projectFallback}
                </p>
                <p className="mt-2 break-all text-xs text-[var(--text-tertiary)]">
                  {projectId}
                </p>
                {projectQuery.data?.address ? (
                  <p className="mt-3 text-sm text-[var(--text-secondary)]">
                    {projectQuery.data.address}
                  </p>
                ) : null}
                {projectQuery.data ? (
                  <p className="mt-2 text-xs text-[var(--text-tertiary)]">
                    {projectQuery.data.status} ·{" "}
                    {formatDate(locale, projectQuery.data.updated_at)}
                  </p>
                ) : null}
              </div>
            )}
          </div>

          <div className="grid gap-4">
            <Card className="bg-[var(--surface-soft)] shadow-none">
              <CardContent className="p-5">
                <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                  {labels.floorPlanTitle}
                </p>
                <form className="mt-4 grid gap-3" onSubmit={handleGenerateFloorPlan}>
                  <div className="grid gap-3 md:grid-cols-2">
                    <Input
                      type="number"
                      value={planForm.areaSqm}
                      onChange={(event) =>
                        setPlanForm((current) => ({
                          ...current,
                          areaSqm: event.target.value,
                        }))
                      }
                      placeholder={labels.areaLabel}
                    />
                    <Input
                      type="number"
                      value={planForm.roomCount}
                      onChange={(event) =>
                        setPlanForm((current) => ({
                          ...current,
                          roomCount: event.target.value,
                        }))
                      }
                      placeholder={labels.roomCountLabel}
                    />
                  </div>
                  <Select
                    label={labels.styleLabel}
                    value={planForm.style}
                    onValueChange={(value) =>
                      setPlanForm((current) => ({
                        ...current,
                        style: value,
                      }))
                    }
                    options={STYLE_OPTIONS}
                  />
                  <Button type="submit" disabled={!canUseLiveApi || isGeneratingPlan}>
                    {isGeneratingPlan
                      ? `${labels.generateFloorPlanAction}...`
                      : labels.generateFloorPlanAction}
                  </Button>
                </form>
              </CardContent>
            </Card>

            <Card className="bg-[var(--surface-soft)] shadow-none">
              <CardContent className="p-5">
                <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                  {labels.ifcTitle}
                </p>
                <form className="mt-4 grid gap-3" onSubmit={handleGenerateIfc}>
                  <div className="grid gap-3 md:grid-cols-2">
                    <Input
                      type="number"
                      value={ifcForm.totalAreaSqm}
                      onChange={(event) =>
                        setIfcForm((current) => ({
                          ...current,
                          totalAreaSqm: event.target.value,
                        }))
                      }
                      placeholder={labels.totalAreaLabel}
                    />
                    <Input
                      type="number"
                      value={ifcForm.floors}
                      onChange={(event) =>
                        setIfcForm((current) => ({
                          ...current,
                          floors: event.target.value,
                        }))
                      }
                      placeholder={labels.floorsLabel}
                    />
                  </div>
                  <Select
                    label={labels.structureLabel}
                    value={ifcForm.structureType}
                    onValueChange={(value) =>
                      setIfcForm((current) => ({
                        ...current,
                        structureType: value,
                      }))
                    }
                    options={STRUCTURE_OPTIONS}
                  />
                  <Button type="submit" disabled={!canUseLiveApi || isGeneratingIfc}>
                    {isGeneratingIfc
                      ? `${labels.generateIfcAction}...`
                      : labels.generateIfcAction}
                  </Button>
                </form>
              </CardContent>
            </Card>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.floorPlanResultTitle}
            </p>
            {floorPlanResult ? (
              <div className="mt-4 space-y-4">
                <MetricTile
                  label={labels.generationMethodLabel}
                  value={floorPlanResult.generation_method}
                />
                <MetricTile
                  label={labels.fileUrlLabel}
                  value={floorPlanResult.file_url}
                />
                <MetricTile
                  label={labels.roomCountLabel}
                  value={String(floorPlanResult.room_count)}
                />
                {floorPlanResult.vision_validation ? (
                  <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
                    detected: {String(floorPlanResult.vision_validation.detected_rooms)} /{" "}
                    expected: {String(floorPlanResult.vision_validation.expected_rooms)} /{" "}
                    confidence:{" "}
                    {typeof floorPlanResult.vision_validation.confidence === "number"
                      ? floorPlanResult.vision_validation.confidence.toFixed(2)
                      : "-"}{" "}
                    / match: {String(Boolean(floorPlanResult.vision_validation.match))}
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
                {labels.placeholder}
              </div>
            )}
          </CardContent>
        </Card>

        <div className="grid gap-6">
          <Card>
            <CardContent className="p-6">
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.bimResultTitle}
              </p>
              {bimResult ? (
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <MetricTile
                    label={labels.totalAreaLabel}
                    value={formatNumber(locale, bimResult.total_area_sqm)}
                  />
                  <MetricTile
                    label={labels.totalVolumeLabel}
                    value={formatNumber(locale, bimResult.total_volume_m3)}
                  />
                  <MetricTile
                    label={labels.elementCountLabel}
                    value={String(bimResult.element_count)}
                  />
                  <MetricTile
                    label={labels.ifcVersionLabel}
                    value={bimResult.ifc_version}
                  />
                  <MetricTile
                    label="Created"
                    value={formatDate(locale, bimResult.created_at)}
                  />
                  <MetricTile
                    label="Materials"
                    value={String(bimResult.material_breakdown.length)}
                  />
                </div>
              ) : (
                <div className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
                  {labels.placeholder}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6">
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.carbonTitle}
              </p>
              {carbonResult ? (
                <div className="mt-4 space-y-4">
                  <div className="grid gap-4 md:grid-cols-3">
                    <MetricTile
                      label={labels.totalCarbonLabel}
                      value={formatNumber(locale, carbonResult.total_carbon)}
                    />
                    <MetricTile
                      label={labels.embodiedCarbonLabel}
                      value={formatNumber(locale, carbonResult.total_embodied_carbon)}
                    />
                    <MetricTile
                      label={labels.operationalCarbonLabel}
                      value={formatNumber(locale, carbonResult.total_operational_carbon)}
                    />
                  </div>
                  <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                    <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                      {labels.reductionTipsLabel}
                    </p>
                    {carbonResult.reduction_tips.length ? (
                      <ul className="mt-3 space-y-2 text-sm leading-7 text-[var(--text-secondary)]">
                        {carbonResult.reduction_tips.map((tip) => (
                          <li key={tip}>{tip}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-3 text-sm leading-7 text-[var(--text-tertiary)]">
                        -
                      </p>
                    )}
                  </div>
                </div>
              ) : (
                <div className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
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
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
      <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-3 break-all text-sm font-semibold text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}
