"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, CardTitle, Input, Select } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { NumberInput } from "@/components/common/NumberInput";
import { ApiClientError, apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
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

type GeometryResponse = {
  project_id: string;
  format: string;
  total_elements: number;
  geometries: Array<{
    id: string;
    type: string;
  }>;
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
  generateTitle: string;
  totalAreaLabel: string;
  floorsLabel: string;
  structureLabel: string;
  generateAction: string;
  resultTitle: string;
  totalVolumeLabel: string;
  elementCountLabel: string;
  ifcVersionLabel: string;
  geometryTitle: string;
  geometryFormatLabel: string;
  geometryTypesLabel: string;
  missingAreaError: string;
  missingFloorsError: string;
  placeholder: string;
  projectLoadErrorTitle: string;
  projectLoadErrorDetail: string;
  retryAction: string;
};

const EN_LABELS: Labels = {
  heroTitle: "Project BIM live workspace",
  heroDescription:
    "Generate BIM quantities and load Three.js geometry summaries for the current project route through the live BIM APIs.",
  heroHint:
    "",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "API authentication is required for live workspace calls.",
  contextTitle: "Project context",
  contextHint:
    "Project metadata is loaded from the live API and used to prefill area-driven BIM generation settings.",
  projectFallback: "Project metadata could not be loaded from the live API.",
  generateTitle: "BIM generation input",
  totalAreaLabel: "Total area (sqm)",
  floorsLabel: "Floors",
  structureLabel: "Structure type",
  generateAction: "Generate BIM quantities",
  resultTitle: "BIM quantity result",
  totalVolumeLabel: "Total volume",
  elementCountLabel: "Element count",
  ifcVersionLabel: "IFC version",
  geometryTitle: "Three.js geometry summary",
  geometryFormatLabel: "Format",
  geometryTypesLabel: "Geometry types",
  missingAreaError: "A positive area value is required.",
  missingFloorsError: "A positive floor count is required.",
  placeholder:
    "Generate BIM quantities to validate the BIM and geometry response chain for this project route.",
  projectLoadErrorTitle: "Project metadata unavailable",
  projectLoadErrorDetail:
    "The routed project context failed to load from the live API. Retry to restore BIM autofill and route metadata.",
  retryAction: "Retry",
};

const KO_LABELS: Labels = {
  heroTitle: "프로젝트 BIM 라이브 작업 공간",
  heroDescription:
    "현재 프로젝트의 BIM 물량을 산출하고 3D 형상 요약을 불러옵니다.",
  heroHint:
    "프로젝트 ID를 기반으로 IFC 생성 및 Three.js 형상 데이터를 조회합니다.",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "라이브 작업 공간 호출에 API 인증이 필요합니다.",
  contextTitle: "프로젝트 컨텍스트",
  contextHint:
    "프로젝트 메타데이터가 라이브 API에서 로드되어 BIM 생성 설정에 자동 반영됩니다.",
  projectFallback: "라이브 API에서 프로젝트 메타데이터를 불러올 수 없습니다.",
  generateTitle: "BIM 생성 입력",
  totalAreaLabel: "총면적 (㎡)",
  floorsLabel: "층수",
  structureLabel: "구조 유형",
  generateAction: "BIM 물량 산출",
  resultTitle: "BIM 물량 산출 결과",
  totalVolumeLabel: "총 체적",
  elementCountLabel: "요소 수",
  ifcVersionLabel: "IFC 버전",
  geometryTitle: "Three.js 형상 요약",
  geometryFormatLabel: "형식",
  geometryTypesLabel: "형상 유형",
  missingAreaError: "양수의 면적 값이 필요합니다.",
  missingFloorsError: "양수의 층수 값이 필요합니다.",
  placeholder:
    "BIM 물량을 산출하여 이 프로젝트 경로의 BIM 및 형상 응답 체인을 검증하세요.",
  projectLoadErrorTitle: "프로젝트 메타데이터 조회 불가",
  projectLoadErrorDetail:
    "프로젝트 정보를 불러오지 못했습니다. 재시도하여 BIM 자동 입력을 복원하세요.",
  retryAction: "재시도",
};

const LABELS: Record<Locale, Labels> = {
  ko: KO_LABELS,
  en: EN_LABELS,
  "zh-CN": KO_LABELS,
};

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

export function ProjectBimWorkspaceClient({
  locale,
  projectId,
}: {
  locale: Locale;
  projectId: string;
}) {
  const labels = LABELS[locale] || LABELS["ko"];
  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  // 부지분석/설계 데이터 연동
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const designData = useProjectContextStore((s) => s.designData);
  const updateDesignData = useProjectContextStore((s) => s.updateDesignData);
  const markStageComplete = useProjectContextStore((s) => s.markStageComplete);
  const addAnalysisResult = useProjectContextStore((s) => s.addAnalysisResult);

  const [workspaceError, setWorkspaceError] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [bimResult, setBimResult] = useState<BIMQuantityResponse | null>(null);
  const [geometryResult, setGeometryResult] = useState<GeometryResponse | null>(null);
  const [form, setForm] = useState({
    totalAreaSqm: "",
    floors: "12",
    structureType: "RC",
  });

  const projectQuery = useQuery({
    queryKey: ["projects", "detail", projectId, "bim-live"],
    enabled: canUseLiveApi,
    queryFn: () =>
      apiClient.get<ProjectResponse>(`/projects/${projectId}`, {
        useMock: false,
      }),
  });

  // 프로젝트 메타데이터 → 폼 자동 반영
  useEffect(() => {
    const totalAreaSqm = projectQuery.data?.total_area_sqm;
    if (totalAreaSqm == null) return;
    setForm((current) => ({
      ...current,
      totalAreaSqm: current.totalAreaSqm || String(totalAreaSqm),
    }));
  }, [projectQuery.data]);

  // 부지분석/설계 데이터 → 폼 자동 반영
  useEffect(() => {
    setForm((current) => {
      const area = designData?.totalGfaSqm ?? siteAnalysis?.landAreaSqm;
      const floors = designData?.floorCount;
      return {
        ...current,
        totalAreaSqm: current.totalAreaSqm || (area ? String(area) : ""),
        floors: current.floors === "12" && floors ? String(floors) : current.floors,
      };
    });
  }, [siteAnalysis, designData]);

  const geometryTypeSummary = useMemo(() => {
    if (!geometryResult) {
      return [];
    }

    const counts = geometryResult.geometries.reduce<Record<string, number>>(
      (accumulator, geometry) => {
        accumulator[geometry.type] = (accumulator[geometry.type] ?? 0) + 1;
        return accumulator;
      },
      {},
    );

    return Object.entries(counts)
      .sort((left, right) => right[1] - left[1])
      .slice(0, 6);
  }, [geometryResult]);

  const projectError = projectQuery.error
    ? extractErrorMessage(projectQuery.error, labels.authError)
    : "";

  async function handleGenerate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");

    const totalAreaSqm = Number(form.totalAreaSqm);
    const floors = Number(form.floors);

    if (!Number.isFinite(totalAreaSqm) || totalAreaSqm <= 0) {
      setWorkspaceError(labels.missingAreaError);
      return;
    }

    if (!Number.isFinite(floors) || floors <= 0) {
      setWorkspaceError(labels.missingFloorsError);
      return;
    }

    setIsGenerating(true);

    try {
      const bim = await apiClient.post<BIMQuantityResponse>("/bim/generate-ifc", {
        useMock: false,
        body: {
          project_id: projectId,
          total_area_sqm: totalAreaSqm,
          floors,
          structure_type: form.structureType,
        },
      });

      setBimResult(bim);

      // 프로젝트 컨텍스트에 BIM 결과 저장
      updateDesignData({
        totalGfaSqm: bim.total_area_sqm,
        floorCount: Number(form.floors),
        buildingType: form.structureType,
        bcr: null,
        far: null,
      });
      markStageComplete("bim");
      addAnalysisResult({
        module: "bim",
        completedAt: new Date().toISOString(),
        summary: {
          totalVolume: bim.total_volume_m3,
          elementCount: bim.element_count,
          ifcVersion: bim.ifc_version,
        },
      });

      try {
        const geometry = await apiClient.get<GeometryResponse>(
          `/bim/threejs/${projectId}`,
          {
            useMock: false,
          },
        );
        setGeometryResult(geometry);
      } catch (error) {
        setWorkspaceError(extractErrorMessage(error, labels.authError));
      }
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsGenerating(false);
    }
  }

  return (
    <section className="grid gap-6">
      <Card className="rounded-[var(--radius-2xl)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
        <CardContent className="p-8">
          <div className="flex flex-wrap items-center gap-3">
            <span className="cc-meta">BIM WORKSPACE</span>
            <span className="rounded-full bg-[rgba(14,116,144,0.1)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--accent-strong)]">
              {labels.heroTitle}
            </span>
            {runtimeConfig.mode === "live" ? (
              <span className="cc-live"><i />LIVE</span>
            ) : (
              <span className="cc-chip-data">HYBRID</span>
            )}
          </div>
          <h3 className="mt-5 text-3xl font-bold text-[var(--text-primary)]">
            {labels.heroDescription}
          </h3>
          <p className="mt-4 max-w-3xl text-sm leading-8 text-[var(--text-secondary)]">
            {labels.heroHint}
          </p>
          {siteAnalysis?.address && (
            <p className="mt-2 text-xs text-emerald-500 flex items-center gap-1.5">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
              부지분석 연동: {siteAnalysis.address}
              {designData?.totalGfaSqm && ` · 연면적 ${designData.totalGfaSqm.toLocaleString()}m²`}
              {designData?.floorCount && ` · ${designData.floorCount}층`}
            </p>
          )}
          {!canUseLiveApi && (
            <p className="mt-3 max-w-3xl text-sm leading-8 text-[var(--text-tertiary)]">
              {labels.tokenHint}
            </p>
          )}
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
              <p className="cc-label">
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

          <Card className="bg-[var(--surface-soft)] shadow-none">
            <CardContent className="p-5">
              <p className="cc-label">
                {labels.generateTitle}
              </p>
              <form className="mt-4 grid gap-3" onSubmit={handleGenerate}>
                <div className="grid gap-3 md:grid-cols-2">
                  <NumberInput
                    allowDecimal
                    value={form.totalAreaSqm === "" ? null : Number(form.totalAreaSqm)}
                    onChange={(n) =>
                      setForm((current) => ({
                        ...current,
                        totalAreaSqm: n != null ? String(n) : "",
                      }))
                    }
                    placeholder={labels.totalAreaLabel}
                    className="flex h-11 w-full rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
                  />
                  <Input
                    type="number"
                    value={form.floors}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        floors: event.target.value,
                      }))
                    }
                    placeholder={labels.floorsLabel}
                  />
                </div>
                <Select
                  label={labels.structureLabel}
                  value={form.structureType}
                  onValueChange={(value) =>
                    setForm((current) => ({
                      ...current,
                      structureType: value,
                    }))
                  }
                  options={STRUCTURE_OPTIONS}
                />
                <Button type="submit" disabled={!canUseLiveApi || isGenerating}>
                  {isGenerating
                    ? `${labels.generateAction}...`
                    : labels.generateAction}
                </Button>
              </form>
            </CardContent>
          </Card>
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <Card>
          <CardContent className="p-6">
            <p className="cc-label">
              {labels.resultTitle}
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
                  value={String(bimResult.material_breakdown?.length)}
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
            <p className="cc-label">
              {labels.geometryTitle}
            </p>
            {geometryResult ? (
              <div className="mt-4 space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <MetricTile
                    label={labels.geometryFormatLabel}
                    value={geometryResult.format}
                  />
                  <MetricTile
                    label={labels.elementCountLabel}
                    value={String(geometryResult.total_elements)}
                  />
                </div>
                <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                  <p className="cc-label">
                    {labels.geometryTypesLabel}
                  </p>
                  {geometryTypeSummary.length ? (
                    <ul className="mt-3 space-y-2 text-sm leading-7 text-[var(--text-secondary)]">
                      {geometryTypeSummary.map(([type, count]) => (
                        <li key={type}>
                          {type}: {count}
                        </li>
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
    <div className="cc-bracketed rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
      <i className="cc-bracket cc-bracket--tl" />
      <i className="cc-bracket cc-bracket--br" />
      <p className="cc-label">
        {label}
      </p>
      <p className="cc-num mt-3 break-all text-sm font-semibold">
        {value}
      </p>
    </div>
  );
}
