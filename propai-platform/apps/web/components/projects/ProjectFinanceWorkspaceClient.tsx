"use client";

import { useEffect, useState, type FormEvent } from "react";
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

type AVMValuationResponse = {
  id: string;
  project_id: string;
  estimated_price: number;
  price_per_sqm: number;
  confidence_score: number;
  comparable_count: number;
  model_version: string;
  created_at: string;
};

type JeonseRiskFactor = {
  factor?: string;
  score?: number;
  detail?: string;
  [key: string]: unknown;
};

type JeonseRiskResponse = {
  jeonse_ratio: number;
  risk_level: string;
  risk_score: number;
  analysis: string;
  factors: JeonseRiskFactor[];
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
  addressLabel: string;
  areaLabel: string;
  buildingAgeLabel: string;
  floorLabel: string;
  totalFloorsLabel: string;
  lawdCodeLabel: string;
  pnuLabel: string;
  jeonsePriceLabel: string;
  submitAction: string;
  missingAddressError: string;
  missingAreaError: string;
  missingJeonsePriceError: string;
  avmTitle: string;
  avmEstimateLabel: string;
  avmUnitPriceLabel: string;
  avmConfidenceLabel: string;
  avmComparablesLabel: string;
  avmModelLabel: string;
  jeonseTitle: string;
  jeonseRatioLabel: string;
  jeonseRiskLabel: string;
  jeonseScoreLabel: string;
  jeonseFactorsLabel: string;
  placeholder: string;
  projectFallback: string;
  projectLoadErrorTitle: string;
  projectLoadErrorDetail: string;
  retryAction: string;
};

const COMMON_LABELS: Labels = {
  heroTitle: "Project finance live workspace",
  heroDescription:
    "Run a persisted AVM valuation and a jeonse risk analysis for the current project path.",
  heroHint:
    "This page uses the route project id directly and chains `POST /avm` with `POST /finance/jeonse-risk`.",
  tokenHint:
    "Live API calls require NEXT_PUBLIC_API_ACCESS_TOKEN or localStorage.propai_access_token.",
  authError: "API authentication is required for live workspace calls.",
  contextTitle: "Project context",
  contextHint:
    "The project id comes from the current route. Address and area can be adjusted before submission.",
  projectIdLabel: "Project ID",
  projectNameLabel: "Project name",
  projectStatusLabel: "Status",
  projectUpdatedLabel: "Updated",
  formTitle: "Finance analysis input",
  addressLabel: "Address",
  areaLabel: "Area (sqm)",
  buildingAgeLabel: "Building age (years)",
  floorLabel: "Floor",
  totalFloorsLabel: "Total floors",
  lawdCodeLabel: "LAWD code",
  pnuLabel: "PNU",
  jeonsePriceLabel: "Jeonse price (KRW)",
  submitAction: "Run finance analysis",
  missingAddressError: "Address is required.",
  missingAreaError: "A positive area value is required.",
  missingJeonsePriceError: "A positive jeonse price is required.",
  avmTitle: "AVM valuation",
  avmEstimateLabel: "Estimated price",
  avmUnitPriceLabel: "Price per sqm",
  avmConfidenceLabel: "Confidence",
  avmComparablesLabel: "Comparables",
  avmModelLabel: "Model version",
  jeonseTitle: "Jeonse risk",
  jeonseRatioLabel: "Jeonse ratio",
  jeonseRiskLabel: "Risk level",
  jeonseScoreLabel: "Risk score",
  jeonseFactorsLabel: "Risk factors",
  placeholder:
    "Submit the form to validate the persisted AVM and jeonse risk response chain.",
  projectFallback: "Project metadata could not be loaded from the live API.",
  projectLoadErrorTitle: "Project metadata unavailable",
  projectLoadErrorDetail:
    "The routed project context failed to load from the live API. Retry to restore autofill and project metadata.",
  retryAction: "Retry",
};

const LABELS: Record<Locale, Labels> = {
  ko: COMMON_LABELS,
  en: COMMON_LABELS,
  "zh-CN": COMMON_LABELS,
};

function formatCurrency(locale: string, value: number) {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

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

export function ProjectFinanceWorkspaceClient({
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
  const [avmResult, setAvmResult] = useState<AVMValuationResponse | null>(null);
  const [riskResult, setRiskResult] = useState<JeonseRiskResponse | null>(null);
  const [form, setForm] = useState({
    address: "",
    areaSqm: "",
    buildingAgeYears: "5",
    floor: "8",
    totalFloors: "18",
    lawdCd: "",
    pnu: "",
    jeonsePrice: "1800000000",
  });

  const projectQuery = useQuery({
    queryKey: ["projects", "detail", projectId, "finance-live"],
    enabled: canUseLiveApi,
    queryFn: () =>
      apiClient.get<ProjectResponse>(`/projects/${projectId}`, {
        useMock: false,
      }),
  });

  useEffect(() => {
    if (!projectQuery.data) {
      return;
    }

    setForm((current) => ({
      ...current,
      address: current.address || projectQuery.data.address || "",
      areaSqm:
        current.areaSqm ||
        (projectQuery.data.total_area_sqm != null
          ? String(projectQuery.data.total_area_sqm)
          : ""),
    }));
  }, [projectQuery.data]);

  const projectError = projectQuery.error
    ? extractErrorMessage(projectQuery.error, labels.authError)
    : "";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");

    const address = form.address.trim();
    const areaSqm = Number(form.areaSqm);
    const jeonsePrice = Number(form.jeonsePrice);

    if (!address) {
      setWorkspaceError(labels.missingAddressError);
      return;
    }

    if (!Number.isFinite(areaSqm) || areaSqm <= 0) {
      setWorkspaceError(labels.missingAreaError);
      return;
    }

    if (!Number.isFinite(jeonsePrice) || jeonsePrice <= 0) {
      setWorkspaceError(labels.missingJeonsePriceError);
      return;
    }

    setIsSubmitting(true);

    try {
      const avm = await apiClient.post<AVMValuationResponse>("/avm", {
        useMock: false,
        body: {
          project_id: projectId,
          address,
          area_sqm: areaSqm,
          building_age_years: Number(form.buildingAgeYears) || undefined,
          floor: Number(form.floor) || undefined,
          total_floors: Number(form.totalFloors) || undefined,
          lawd_cd: form.lawdCd.trim() || undefined,
          pnu: form.pnu.trim() || undefined,
        },
      });

      const risk = await apiClient.post<JeonseRiskResponse>(
        "/finance/jeonse-risk",
        {
          useMock: false,
          body: {
            project_id: projectId,
            address,
            jeonse_price: jeonsePrice,
            sale_price: avm.estimated_price,
          },
        },
      );

      setAvmResult(avm);
      setRiskResult(risk);
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsSubmitting(false);
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
                  {labels.projectIdLabel}
                </p>
                <p className="mt-2 break-all text-sm font-semibold text-[var(--foreground)]">
                  {projectId}
                </p>
                <p className="mt-4 text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.5)]">
                  {labels.projectNameLabel}
                </p>
                <p className="mt-2 text-sm text-[rgba(19,33,47,0.76)]">
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
              <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.5)]">
                {labels.formTitle}
              </p>
              <form className="mt-4 grid gap-3" onSubmit={handleSubmit}>
                <Input
                  value={form.address}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      address: event.target.value,
                    }))
                  }
                  placeholder={labels.addressLabel}
                />
                <div className="grid gap-3 md:grid-cols-2">
                  <Input
                    type="number"
                    value={form.areaSqm}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        areaSqm: event.target.value,
                      }))
                    }
                    placeholder={labels.areaLabel}
                  />
                  <Input
                    type="number"
                    value={form.jeonsePrice}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        jeonsePrice: event.target.value,
                      }))
                    }
                    placeholder={labels.jeonsePriceLabel}
                  />
                </div>
                <div className="grid gap-3 md:grid-cols-3">
                  <Input
                    type="number"
                    value={form.buildingAgeYears}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        buildingAgeYears: event.target.value,
                      }))
                    }
                    placeholder={labels.buildingAgeLabel}
                  />
                  <Input
                    type="number"
                    value={form.floor}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        floor: event.target.value,
                      }))
                    }
                    placeholder={labels.floorLabel}
                  />
                  <Input
                    type="number"
                    value={form.totalFloors}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        totalFloors: event.target.value,
                      }))
                    }
                    placeholder={labels.totalFloorsLabel}
                  />
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <Input
                    value={form.lawdCd}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        lawdCd: event.target.value,
                      }))
                    }
                    placeholder={labels.lawdCodeLabel}
                  />
                  <Input
                    value={form.pnu}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        pnu: event.target.value,
                      }))
                    }
                    placeholder={labels.pnuLabel}
                  />
                </div>
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

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.5)]">
              {labels.avmTitle}
            </p>
            {avmResult ? (
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <MetricTile
                  label={labels.avmEstimateLabel}
                  value={formatCurrency(locale, avmResult.estimated_price)}
                />
                <MetricTile
                  label={labels.avmUnitPriceLabel}
                  value={formatCurrency(locale, avmResult.price_per_sqm)}
                />
                <MetricTile
                  label={labels.avmConfidenceLabel}
                  value={formatPercent(avmResult.confidence_score)}
                />
                <MetricTile
                  label={labels.avmComparablesLabel}
                  value={String(avmResult.comparable_count)}
                />
                <MetricTile
                  label={labels.avmModelLabel}
                  value={avmResult.model_version}
                />
                <MetricTile
                  label="Created"
                  value={formatDate(locale, avmResult.created_at)}
                />
              </div>
            ) : (
              <div className="mt-4 rounded-[1.5rem] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[rgba(19,33,47,0.68)]">
                {labels.placeholder}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.5)]">
              {labels.jeonseTitle}
            </p>
            {riskResult ? (
              <div className="mt-4 space-y-4">
                <div className="grid gap-4 md:grid-cols-3">
                  <MetricTile
                    label={labels.jeonseRatioLabel}
                    value={formatPercent(riskResult.jeonse_ratio)}
                  />
                  <MetricTile
                    label={labels.jeonseRiskLabel}
                    value={riskResult.risk_level}
                  />
                  <MetricTile
                    label={labels.jeonseScoreLabel}
                    value={formatPercent(riskResult.risk_score)}
                  />
                </div>
                <div className="rounded-[1.5rem] bg-[var(--surface-soft)] p-5">
                  <p className="text-sm leading-7 text-[rgba(19,33,47,0.76)]">
                    {riskResult.analysis}
                  </p>
                </div>
                <div className="rounded-[1.5rem] bg-[var(--surface-soft)] p-5">
                  <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.5)]">
                    {labels.jeonseFactorsLabel}
                  </p>
                  {riskResult.factors.length ? (
                    <ul className="mt-3 space-y-2 text-sm leading-7 text-[rgba(19,33,47,0.72)]">
                      {riskResult.factors.map((factor, index) => (
                        <li key={`${factor.factor ?? "factor"}-${index}`}>
                          {factor.factor ?? "factor"}:{" "}
                          {factor.detail ?? JSON.stringify(factor)}
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
              <div className="mt-4 rounded-[1.5rem] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[rgba(19,33,47,0.68)]">
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
    <div className="rounded-[1.5rem] bg-white/80 p-4">
      <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.5)]">
        {label}
      </p>
      <p className="mt-2 text-sm font-semibold text-[var(--foreground)]">
        {value}
      </p>
    </div>
  );
}
