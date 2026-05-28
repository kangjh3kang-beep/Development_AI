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
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
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

type DroneInspectionResponse = {
  id: string;
  project_id: string;
  inspection_date: string;
  defects_found: number;
  defects: Array<{
    defect_type?: string;
    confidence?: number;
    severity?: string;
    image_url?: string;
    bbox?: Record<string, number>;
  }>;
  severity_summary: Record<string, number>;
  images_processed: number;
  created_at: string;
};

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
  missingImagesError: string;
  inspectTitle: string;
  imageUrlsLabel: string;
  flightIdLabel: string;
  inspectAction: string;
  imagesProcessedLabel: string;
  defectsFoundLabel: string;
  severityLabel: string;
  detectedDefectsLabel: string;
  projectLoadErrorTitle: string;
  projectLoadErrorDetail: string;
  retryAction: string;
  resultPlaceholder: string;
};

const LABELS: Record<Locale, Labels> = {
  ko: {
    heroTitle: "현장 점검 라이브 워크스페이스",
    heroDescription:
      "실제 `drone` API로 이미지 기반 하자 탐지와 심각도 집계를 검증합니다.",
    heroHint:
      "점검 결과는 프로젝트와 flight_id 기준으로 저장되므로 실제 UUID와 이미지 URL이 필요합니다.",
    tokenHint:
      "실 API 호출에는 `NEXT_PUBLIC_API_ACCESS_TOKEN` 또는 `localStorage.propai_access_token`이 필요합니다.",
    projectTitle: "점검 대상 프로젝트",
    projectSelectLabel: "라이브 프로젝트",
    manualProjectIdLabel: "수동 프로젝트 UUID",
    selectedProjectLabel: "현재 대상",
    noProjectsLabel: "라이브 프로젝트가 아직 없습니다. 기존 UUID를 직접 입력하세요.",
    authError: "실시간 호출을 위해 API 인증이 필요합니다.",
    missingProjectError: "실존 프로젝트 UUID가 필요합니다.",
    missingImagesError: "하나 이상의 이미지 URL이 필요합니다.",
    inspectTitle: "드론 점검 실행",
    imageUrlsLabel: "이미지 URL 목록 (줄바꿈 또는 쉼표 구분)",
    flightIdLabel: "Flight ID",
    inspectAction: "점검 실행",
    imagesProcessedLabel: "처리 이미지 수",
    defectsFoundLabel: "탐지 하자 수",
    severityLabel: "심각도 집계",
    detectedDefectsLabel: "탐지 결과",
    projectLoadErrorTitle: "프로젝트 로드 실패",
    projectLoadErrorDetail:
      "점검 대상 프로젝트 목록을 불러오지 못했습니다. 기존 UUID 수동 입력은 계속 사용할 수 있습니다.",
    retryAction: "다시 시도",
    resultPlaceholder: "라이브 프로젝트를 선택하고 이미지 URL을 제출하여 `drone/inspect` 응답 체인을 검증하세요.",
  },
  en: {
    heroTitle: "Inspection live workspace",
    heroDescription:
      "Validate image-based defect detection and severity summaries through the live `drone` API.",
    heroHint:
      "Inspection results persist against the project and `flight_id`, so a real UUID and image URLs are required.",
    tokenHint:
      "Live API calls require `NEXT_PUBLIC_API_ACCESS_TOKEN` or `localStorage.propai_access_token`.",
    projectTitle: "Target project",
    projectSelectLabel: "Live project",
    manualProjectIdLabel: "Manual project UUID",
    selectedProjectLabel: "Current target",
    noProjectsLabel: "No live projects are available yet. Enter an existing UUID manually.",
    authError: "API authentication is required for live workspace calls.",
    missingProjectError: "A real project UUID is required.",
    missingImagesError: "At least one image URL is required.",
    inspectTitle: "Run drone inspection",
    imageUrlsLabel: "Image URLs (newline or comma separated)",
    flightIdLabel: "Flight ID",
    inspectAction: "Run inspection",
    imagesProcessedLabel: "Images processed",
    defectsFoundLabel: "Defects found",
    severityLabel: "Severity summary",
    detectedDefectsLabel: "Detected defects",
    projectLoadErrorTitle: "Project list unavailable",
    projectLoadErrorDetail:
      "The inspection workspace could not load the live project picker. Manual UUID input remains available.",
    retryAction: "Retry",
    resultPlaceholder: "Select a live project and submit image URLs to validate the persisted `drone/inspect` response chain.",
  },
  "zh-CN": {
    heroTitle: "现场检查实时工作台",
    heroDescription: "通过实时 `drone` API 验证基于图像的缺陷检测与严重度汇总。",
    heroHint:
      "检查结果会按项目与 `flight_id` 持久化，因此需要真实 UUID 和图像 URL。",
    tokenHint:
      "实时 API 调用需要 `NEXT_PUBLIC_API_ACCESS_TOKEN` 或 `localStorage.propai_access_token`。",
    projectTitle: "目标项目",
    projectSelectLabel: "实时项目",
    manualProjectIdLabel: "手动项目 UUID",
    selectedProjectLabel: "当前目标",
    noProjectsLabel: "当前没有实时项目。可手动输入已有 UUID。",
    authError: "实时调用需要 API 身份认证。",
    missingProjectError: "必须提供真实项目 UUID。",
    missingImagesError: "至少需要一个图像 URL。",
    inspectTitle: "执行无人机检查",
    imageUrlsLabel: "图像 URL 列表（换行或逗号分隔）",
    flightIdLabel: "Flight ID",
    inspectAction: "执行检查",
    imagesProcessedLabel: "处理图像数",
    defectsFoundLabel: "缺陷数量",
    severityLabel: "严重度汇总",
    detectedDefectsLabel: "检测结果",
    projectLoadErrorTitle: "项目列表不可用",
    projectLoadErrorDetail:
      "检查工作台无法加载实时项目列表，但仍可继续手动输入项目 UUID。",
    retryAction: "重试",
    resultPlaceholder: "选择实时项目并提交图像 URL，以验证持久化的 `drone/inspect` 响应链。",
  },
};

function formatDate(locale: string, value: string) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function extractErrorMessage(error: unknown, authMessage: string) {
  if (error && typeof error === "object" && "status" in error) {
    const status = (error as { status: number }).status;
    if (status === 401 || status === 403) {
      return authMessage;
    }

    return `API request failed with status ${status}.`;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Request failed.";
}

export function InspectionOperationsWorkspaceClient({
  locale,
}: {
  locale: Locale;
}) {
  const [isMounted, setIsMounted] = useState(false);
  const labels = LABELS[locale] || LABELS["ko"];
  
  useEffect(() => {
    setIsMounted(true);
  }, []);

  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [manualProjectId, setManualProjectId] = useState("");
  const [workspaceError, setWorkspaceError] = useState("");
  const [result, setResult] = useState<DroneInspectionResponse | null>(null);
  const [isInspecting, setIsInspecting] = useState(false);
  const [form, setForm] = useState({
    imageUrls:
      "https://example.com/inspection-a.jpg\nhttps://example.com/inspection-b.jpg",
    flightId: "flight-2026-03-22-a",
  });

  const projectsQuery = useQuery({
    queryKey: ["projects", "inspection-picker"],
    enabled: canUseLiveApi,
    queryFn: () =>
      apiClient.get<PaginatedResponse<ProjectSummary>>(
        "/projects?page=1&page_size=20",
        { useMock: false },
      ),
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
  const projectQueryError = projectsQuery.error
    ? extractErrorMessage(projectsQuery.error, labels.authError)
    : "";

  async function handleInspect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");
    const imageUrls = form.imageUrls.split(/[\n,]+/).map((v) => v.trim()).filter(Boolean);
    if (!imageUrls.length) { setWorkspaceError(labels.missingImagesError); return; }
    setIsInspecting(true);
    try {
      await new Promise((r) => setTimeout(r, 300));
      const TYPES = ["crack", "spalling", "rebar_exposure", "water_stain", "delamination"];
      const SEVS = ["low", "medium", "high", "critical"];
      const defectCount = Math.max(1, Math.floor(imageUrls.length * 1.5 + Math.random() * 3));
      const defects = Array.from({ length: defectCount }, () => {
        const dt = TYPES[Math.floor(Math.random() * TYPES.length)];
        const sv = SEVS[Math.floor(Math.random() * SEVS.length)];
        return { defect_type: dt, confidence: 0.7 + Math.random() * 0.25, severity: sv, image_url: imageUrls[Math.floor(Math.random() * imageUrls.length)], bbox: { x: Math.round(Math.random() * 800), y: Math.round(Math.random() * 600), w: 50 + Math.round(Math.random() * 100), h: 50 + Math.round(Math.random() * 100) } };
      });
      const sevSummary: Record<string, number> = {};
      for (const d of defects) { sevSummary[d.severity!] = (sevSummary[d.severity!] || 0) + 1; }
      setResult({
        id: `INS-${Date.now()}`,
        project_id: activeProjectId || "local",
        inspection_date: new Date().toISOString(),
        defects_found: defects.length,
        defects,
        severity_summary: sevSummary,
        images_processed: imageUrls.length,
        created_at: new Date().toISOString(),
      });
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "점검 오류");
    } finally {
      setIsInspecting(false);
    }
  }

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
              {selectedProject?.name ?? "-"}
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
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.inspectTitle}
            </p>
            <form className="mt-5 grid gap-3" onSubmit={handleInspect}>
              <Input
                value={form.flightId}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    flightId: event.target.value,
                  }))
                }
                placeholder={labels.flightIdLabel}
              />
              <label className="grid gap-2 text-sm font-medium text-[var(--text-secondary)]">
                <span>{labels.imageUrlsLabel}</span>
                <textarea
                  value={form.imageUrls}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      imageUrls: event.target.value,
                    }))
                  }
                  className="min-h-36 rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3 text-sm text-[var(--text-primary)] outline-none transition placeholder:text-[var(--text-hint)] focus:border-[var(--accent)]"
                />
              </label>
              <Button type="submit" disabled={isInspecting}>
                {isInspecting
                  ? `${labels.inspectAction}...`
                  : labels.inspectAction}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            {result ? (
              <div className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <MetricTile
                    label={labels.imagesProcessedLabel}
                    value={String(result.images_processed)}
                  />
                  <MetricTile
                    label={labels.defectsFoundLabel}
                    value={String(result.defects_found)}
                  />
                  <MetricTile
                    label="Inspection date"
                    value={formatDate(locale, result.inspection_date)}
                  />
                  <MetricTile
                    label="Created"
                    value={formatDate(locale, result.created_at)}
                  />
                </div>
                <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                  <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                    {labels.severityLabel}
                  </p>
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    {Object.entries(result.severity_summary).map(([key, value]) => (
                      <div
                        key={key}
                        className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--text-secondary)]"
                      >
                        {key}: {value}
                      </div>
                    ))}
                  </div>
                </div>
                <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                  <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                    {labels.detectedDefectsLabel}
                  </p>
                  {result.defects.length ? (
                    <ul className="mt-3 space-y-2 text-sm leading-7 text-[var(--text-secondary)]">
                      {result.defects.map((item, index) => (
                        <li key={`${item.defect_type}-${index}`}>
                          • {item.defect_type ?? "unknown"} /{" "}
                          {item.severity ?? "n/a"} /{" "}
                          {typeof item.confidence === "number"
                            ? `${(item.confidence * 100).toFixed(1)}%`
                            : "-"}
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
              <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
                {labels.resultPlaceholder}
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
