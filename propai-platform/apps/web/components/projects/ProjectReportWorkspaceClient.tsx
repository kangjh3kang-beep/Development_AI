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
  authError: string;
  contextTitle: string;
  contextHint: string;
  projectIdLabel: string;
  projectNameLabel: string;
  projectStatusLabel: string;
  projectUpdatedLabel: string;
  formTitle: string;
  projectNameInputLabel: string;
  assetTypeLabel: string;
  languagesLabel: string;
  highlightsLabel: string;
  risksLabel: string;
  sectionsLabel: string;
  submitAction: string;
  missingProjectNameError: string;
  missingLanguagesError: string;
  reportTitle: string;
  reportTypeLabel: string;
  generatedSectionsLabel: string;
  reportLanguageLabel: string;
  reportQualityLabel: string;
  reportBodyLabel: string;
  placeholder: string;
  projectFallback: string;
  projectLoadErrorTitle: string;
  projectLoadErrorDetail: string;
  retryAction: string;
};

const COMMON_LABELS: Labels = {
  heroTitle: "Project report live workspace",
  heroDescription:
    "Generate multilingual investor reports for the current project through the live reports API.",
  heroHint:
    "This page binds the route project id to `POST /reports/investor/generate` and keeps the output on-screen for review.",
  tokenHint:
    "Live API calls require NEXT_PUBLIC_API_ACCESS_TOKEN or localStorage.propai_access_token.",
  authError: "API authentication is required for live workspace calls.",
  contextTitle: "Project context",
  contextHint:
    "The report request uses the route project id directly. Project name and content prompts can be adjusted before generation.",
  projectIdLabel: "Project ID",
  projectNameLabel: "Project name",
  projectStatusLabel: "Status",
  projectUpdatedLabel: "Updated",
  formTitle: "Investor report request",
  projectNameInputLabel: "Report project name",
  assetTypeLabel: "Asset type",
  languagesLabel: "Target languages",
  highlightsLabel: "Investment highlights",
  risksLabel: "Risk factors",
  sectionsLabel: "Included sections",
  submitAction: "Generate investor report",
  missingProjectNameError: "A project name is required.",
  missingLanguagesError: "At least one target language is required.",
  reportTitle: "Generated report variants",
  reportTypeLabel: "Report type",
  generatedSectionsLabel: "Generated sections",
  reportLanguageLabel: "Language",
  reportQualityLabel: "Quality score",
  reportBodyLabel: "Report body",
  placeholder:
    "Generate a live investor report to validate multilingual output for this project path.",
  projectFallback: "Project metadata could not be loaded from the live API.",
  projectLoadErrorTitle: "Project metadata unavailable",
  projectLoadErrorDetail:
    "The routed project context failed to load from the live API. Retry to restore project naming and status context.",
  retryAction: "Retry",
};

const LABELS: Record<Locale, Labels> = {
  ko: COMMON_LABELS,
  en: COMMON_LABELS,
  "zh-CN": COMMON_LABELS,
};

const ASSET_TYPE_OPTIONS = [
  { label: "Office", value: "office" },
  { label: "Residential", value: "residential" },
  { label: "Mixed-use", value: "mixed_use" },
  { label: "Logistics", value: "logistics" },
];

function formatDate(locale: string, value: string) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function splitList(value: string) {
  return value
    .split(/[\n,]+/)
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

export function ProjectReportWorkspaceClient({
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
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<InvestorReportResponse | null>(null);
  const [form, setForm] = useState({
    projectName: "",
    assetType: "office",
    targetLanguages: "ko,en",
    highlights: "Prime location\nStrong tenant demand",
    risks: "Interest-rate volatility\nExecution timeline pressure",
    sections: "executive-summary,market,financials,esg,risks",
  });

  const projectQuery = useQuery({
    queryKey: ["projects", "detail", projectId, "report-live"],
    enabled: canUseLiveApi,
    queryFn: () =>
      apiClient.get<ProjectResponse>(`/projects/${projectId}`, {
        useMock: false,
      }),
  });

  useEffect(() => {
    if (!projectQuery.data?.name) {
      return;
    }

    setForm((current) => ({
      ...current,
      projectName: current.projectName || projectQuery.data.name,
    }));
  }, [projectQuery.data]);

  const projectError = projectQuery.error
    ? extractErrorMessage(projectQuery.error, labels.authError)
    : "";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");

    const projectName = form.projectName.trim();
    const targetLanguages = splitList(form.targetLanguages);

    if (!projectName) {
      setWorkspaceError(labels.missingProjectNameError);
      return;
    }

    if (!targetLanguages.length) {
      setWorkspaceError(labels.missingLanguagesError);
      return;
    }

    setIsSubmitting(true);

    try {
      const response = await apiClient.post<InvestorReportResponse>(
        "/reports/investor/generate",
        {
          useMock: false,
          body: {
            project_id: projectId,
            project_name: projectName,
            asset_type: form.assetType,
            target_languages: targetLanguages,
            investment_highlights: splitList(form.highlights),
            risks: splitList(form.risks),
            include_sections: splitList(form.sections),
          },
        },
      );

      setResult(response);
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsSubmitting(false);
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
        <CardContent className="grid gap-5 p-6 lg:grid-cols-[0.9fr_1.1fr]">
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
                <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                  {labels.projectIdLabel}
                </p>
                <p className="mt-2 break-all text-sm font-semibold text-[var(--text-primary)]">
                  {projectId}
                </p>
                <p className="mt-4 text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                  {labels.projectNameLabel}
                </p>
                <p className="mt-2 text-sm text-[var(--text-secondary)]">
                  {projectQuery.data?.name ?? labels.projectFallback}
                </p>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <MetricTile
                    label={labels.projectStatusLabel}
                    value={projectQuery.data?.status ?? "-"}
                  />
                  <MetricTile
                    label={labels.projectUpdatedLabel}
                    value={
                      projectQuery.data?.updated_at
                        ? formatDate(locale, projectQuery.data.updated_at)
                        : "-"
                    }
                  />
                </div>
              </div>
            )}
          </div>

          <Card className="bg-[var(--surface-soft)] shadow-none">
            <CardContent className="p-5">
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.formTitle}
              </p>
              <form className="mt-4 grid gap-3" onSubmit={handleSubmit}>
                <Input
                  value={form.projectName}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      projectName: event.target.value,
                    }))
                  }
                  placeholder={labels.projectNameInputLabel}
                />
                <Select
                  label={labels.assetTypeLabel}
                  value={form.assetType}
                  onValueChange={(value) =>
                    setForm((current) => ({
                      ...current,
                      assetType: value,
                    }))
                  }
                  options={ASSET_TYPE_OPTIONS}
                />
                <label className="grid gap-2 text-sm font-medium text-[var(--text-secondary)]">
                  <span>{labels.languagesLabel}</span>
                  <textarea
                    value={form.targetLanguages}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        targetLanguages: event.target.value,
                      }))
                    }
                    className="min-h-20 rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--text-primary)] outline-none transition placeholder:text-[var(--text-hint)] focus:border-[var(--accent)]"
                  />
                </label>
                <label className="grid gap-2 text-sm font-medium text-[var(--text-secondary)]">
                  <span>{labels.highlightsLabel}</span>
                  <textarea
                    value={form.highlights}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        highlights: event.target.value,
                      }))
                    }
                    className="min-h-24 rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--text-primary)] outline-none transition placeholder:text-[var(--text-hint)] focus:border-[var(--accent)]"
                  />
                </label>
                <label className="grid gap-2 text-sm font-medium text-[var(--text-secondary)]">
                  <span>{labels.risksLabel}</span>
                  <textarea
                    value={form.risks}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        risks: event.target.value,
                      }))
                    }
                    className="min-h-24 rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--text-primary)] outline-none transition placeholder:text-[var(--text-hint)] focus:border-[var(--accent)]"
                  />
                </label>
                <label className="grid gap-2 text-sm font-medium text-[var(--text-secondary)]">
                  <span>{labels.sectionsLabel}</span>
                  <textarea
                    value={form.sections}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        sections: event.target.value,
                      }))
                    }
                    className="min-h-20 rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--text-primary)] outline-none transition placeholder:text-[var(--text-hint)] focus:border-[var(--accent)]"
                  />
                </label>
                <Button type="submit" disabled={!canUseLiveApi || isSubmitting}>
                  {isSubmitting
                    ? `${labels.submitAction}...`
                    : labels.submitAction}
                </Button>
              </form>
            </CardContent>
          </Card>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-6">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
            {labels.reportTitle}
          </p>
          {result ? (
            <div className="mt-4 space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <MetricTile label={labels.reportTypeLabel} value={result.report_type} />
                <MetricTile
                  label={labels.generatedSectionsLabel}
                  value={result.generated_sections.join(", ")}
                />
              </div>
              <div className="space-y-4">
                {result.variants.map((variant) => (
                  <div
                    key={variant.report_id}
                    className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5"
                  >
                    <div className="grid gap-3 md:grid-cols-3">
                      <MetricTile
                        label={labels.reportLanguageLabel}
                        value={variant.target_language}
                      />
                      <MetricTile
                        label={labels.reportQualityLabel}
                        value={
                          variant.quality_score == null
                            ? "-"
                            : `${variant.quality_score.toFixed(2)}`
                        }
                      />
                      <MetricTile label="Title" value={variant.title} />
                    </div>
                    <p className="mt-4 text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                      {labels.reportBodyLabel}
                    </p>
                    <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-[var(--text-secondary)]">
                      {variant.translated_text}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
              {labels.placeholder}
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
    <div className="rounded-[var(--radius-xl)] bg-[var(--surface)] p-4">
      <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-2 text-sm font-semibold text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}
