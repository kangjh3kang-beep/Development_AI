"use client";

import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, CardTitle, Input } from "@propai/ui";
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
  authError: string;
  contextTitle: string;
  contextHint: string;
  inspectTitle: string;
  imageUrlsLabel: string;
  flightIdLabel: string;
  inspectAction: string;
  missingImagesError: string;
  projectFallback: string;
  selectedProjectLabel: string;
  imagesProcessedLabel: string;
  defectsFoundLabel: string;
  severityLabel: string;
  detectedDefectsLabel: string;
  projectLoadErrorTitle: string;
  projectLoadErrorDetail: string;
  retryAction: string;
};

const COMMON_LABELS: Labels = {
  heroTitle: "Project drone live workspace",
  heroDescription:
    "Run persisted drone inspection for the current project path through the live inspection API.",
  heroHint:
    "This route uses the project id from the URL directly and submits image URLs to `POST /drone/inspect`.",
  tokenHint:
    "Live API calls require NEXT_PUBLIC_API_ACCESS_TOKEN or localStorage.propai_access_token.",
  authError: "API authentication is required for live workspace calls.",
  contextTitle: "Project context",
  contextHint:
    "The inspection is bound to the routed project id. Provide real image URLs and an optional flight id.",
  inspectTitle: "Drone inspection input",
  imageUrlsLabel: "Image URLs (newline or comma separated)",
  flightIdLabel: "Flight ID",
  inspectAction: "Run project inspection",
  missingImagesError: "At least one image URL is required.",
  projectFallback: "Project metadata could not be loaded from the live API.",
  selectedProjectLabel: "Current project",
  imagesProcessedLabel: "Images processed",
  defectsFoundLabel: "Defects found",
  severityLabel: "Severity summary",
  detectedDefectsLabel: "Detected defects",
  projectLoadErrorTitle: "Project metadata unavailable",
  projectLoadErrorDetail:
    "The routed project context failed to load from the live API. Retry to restore the inspection target metadata.",
  retryAction: "Retry",
};

const LABELS: Record<Locale, Labels> = {
  ko: COMMON_LABELS,
  en: COMMON_LABELS,
  "zh-CN": COMMON_LABELS,
};

function formatDate(locale: string, value: string) {
  return new Intl.DateTimeFormat(locale, {
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

export function ProjectDroneWorkspaceClient({
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
  const [result, setResult] = useState<DroneInspectionResponse | null>(null);
  const [isInspecting, setIsInspecting] = useState(false);
  const [form, setForm] = useState({
    imageUrls:
      "https://example.com/project-drone-a.jpg\nhttps://example.com/project-drone-b.jpg",
    flightId: "project-flight-2026-03-22-a",
  });

  const projectQuery = useQuery({
    queryKey: ["projects", "detail", projectId, "drone-live"],
    enabled: canUseLiveApi,
    queryFn: () =>
      apiClient.get<ProjectResponse>(`/projects/${projectId}`, {
        useMock: false,
      }),
  });

  const projectError = projectQuery.error
    ? extractErrorMessage(projectQuery.error, labels.authError)
    : "";

  async function handleInspect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");

    const imageUrls = form.imageUrls
      .split(/[\n,]+/)
      .map((value) => value.trim())
      .filter(Boolean);

    if (!imageUrls.length) {
      setWorkspaceError(labels.missingImagesError);
      return;
    }

    setIsInspecting(true);

    try {
      const response = await apiClient.post<DroneInspectionResponse>(
        "/drone/inspect",
        {
          useMock: false,
          body: {
            project_id: projectId,
            image_urls: imageUrls,
            flight_id: form.flightId.trim() || undefined,
          },
        },
      );
      setResult(response);
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsInspecting(false);
    }
  }

  return (
    <section className="grid gap-6">
      <Card className="rounded-[2rem] bg-[var(--surface-strong)] shadow-[0_20px_60px_rgba(19,33,47,0.08)]">
        <CardContent className="p-8">
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-[rgba(14,116,144,0.1)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--accent-strong)]">
              {labels.heroTitle}
            </span>
            <span className="rounded-full border border-[var(--line)] px-4 py-2 text-xs font-medium text-[rgba(19,33,47,0.7)]">
              {runtimeConfig.mode === "live" ? "LIVE" : "HYBRID"}
            </span>
          </div>
          <h3 className="mt-5 text-3xl font-bold text-[var(--foreground)]">
            {labels.heroDescription}
          </h3>
          <p className="mt-4 max-w-3xl text-sm leading-8 text-[rgba(19,33,47,0.72)]">
            {labels.heroHint}
          </p>
          <p className="mt-3 max-w-3xl text-sm leading-8 text-[rgba(19,33,47,0.6)]">
            {labels.tokenHint}
          </p>
          {!canUseLiveApi ? (
            <div className="mt-6 rounded-[1.5rem] border border-dashed border-[var(--line)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[rgba(19,33,47,0.72)]">
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
            <div className="mt-6 rounded-[1.5rem] border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] p-5 text-sm leading-7 text-[var(--spot)]">
              {workspaceError}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="grid gap-5 p-6 lg:grid-cols-[0.95fr_1.05fr]">
          <div className="grid gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.5)]">
                {labels.contextTitle}
              </p>
              <CardTitle className="mt-2 text-xl">{labels.contextHint}</CardTitle>
            </div>
            {projectQuery.isLoading ? (
              <SkeletonLoader count={1} itemClassName="h-28" />
            ) : (
              <div className="rounded-[1.5rem] bg-[var(--surface-soft)] p-5">
                <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.5)]">
                  {labels.selectedProjectLabel}
                </p>
                <p className="mt-2 text-sm font-semibold text-[var(--foreground)]">
                  {projectQuery.data?.name ?? labels.projectFallback}
                </p>
                <p className="mt-2 break-all text-xs text-[rgba(19,33,47,0.56)]">
                  {projectId}
                </p>
                {projectQuery.data?.address ? (
                  <p className="mt-3 text-sm text-[rgba(19,33,47,0.72)]">
                    {projectQuery.data.address}
                  </p>
                ) : null}
                {projectQuery.data ? (
                  <p className="mt-2 text-xs text-[rgba(19,33,47,0.56)]">
                    {projectQuery.data.status} ·{" "}
                    {formatDate(locale, projectQuery.data.updated_at)}
                  </p>
                ) : null}
              </div>
            )}
          </div>

          <Card className="bg-[var(--surface-soft)] shadow-none">
            <CardContent className="p-5">
              <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.5)]">
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
                <label className="grid gap-2 text-sm font-medium text-[rgba(19,33,47,0.78)]">
                  <span>{labels.imageUrlsLabel}</span>
                  <textarea
                    value={form.imageUrls}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        imageUrls: event.target.value,
                      }))
                    }
                    className="min-h-36 rounded-[1rem] border border-[var(--line)] bg-white/85 px-4 py-3 text-sm text-[var(--foreground)] outline-none transition placeholder:text-[rgba(19,33,47,0.4)] focus:border-[var(--accent)]"
                  />
                </label>
                <Button type="submit" disabled={!canUseLiveApi || isInspecting}>
                  {isInspecting
                    ? `${labels.inspectAction}...`
                    : labels.inspectAction}
                </Button>
              </form>
            </CardContent>
          </Card>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-6">
          {result ? (
            <div className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
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
              <div className="rounded-[1.5rem] bg-[var(--surface-soft)] p-5">
                <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.5)]">
                  {labels.severityLabel}
                </p>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  {Object.entries(result.severity_summary).map(([key, value]) => (
                    <div
                      key={key}
                      className="rounded-[1rem] border border-[var(--line)] bg-white/75 px-4 py-3 text-sm text-[rgba(19,33,47,0.72)]"
                    >
                      {key}: {value}
                    </div>
                  ))}
                </div>
              </div>
              <div className="rounded-[1.5rem] bg-[var(--surface-soft)] p-5">
                <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.5)]">
                  {labels.detectedDefectsLabel}
                </p>
                {result.defects.length ? (
                  <ul className="mt-3 space-y-2 text-sm leading-7 text-[rgba(19,33,47,0.72)]">
                    {result.defects.map((item, index) => (
                      <li key={`${item.defect_type ?? "defect"}-${index}`}>
                        {item.defect_type ?? "unknown"} / {item.severity ?? "n/a"} /{" "}
                        {typeof item.confidence === "number"
                          ? `${(item.confidence * 100).toFixed(1)}%`
                          : "-"}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-3 text-sm leading-7 text-[rgba(19,33,47,0.62)]">
                    -
                  </p>
                )}
              </div>
            </div>
          ) : (
            <div className="rounded-[1.5rem] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[rgba(19,33,47,0.68)]">
              Submit the inspection form to validate the persisted `drone/inspect`
              response chain for this project route.
            </div>
          )}
        </CardContent>
      </Card>
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
    <div className="rounded-[1.5rem] bg-[var(--surface-soft)] p-5">
      <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.5)]">
        {label}
      </p>
      <p className="mt-3 text-xl font-semibold text-[var(--foreground)]">
        {value}
      </p>
    </div>
  );
}
