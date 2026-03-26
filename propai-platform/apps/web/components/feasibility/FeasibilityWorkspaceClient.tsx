"use client";

import { type FormEvent, useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, CardContent, CardTitle, Input } from "@propai/ui";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { ApiClientError, apiClient } from "@/lib/api-client";

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

type FeasibilityAnalysisResponse = {
  id: string;
  project_id: string;
  scenario_name: string | null;
  npv: number;
  irr: number;
  payback_period_months: number;
  total_investment_krw: number;
  total_revenue_krw: number;
  risk_score: number;
  discount_rate: number;
  annual_growth_rate: number;
  analysis_years: number;
  exit_value_krw: number;
  cashflows: Array<{
    year: number;
    revenue_krw: number;
    operating_cost_krw: number;
    net_cashflow_krw: number;
    discounted_cashflow_krw: number;
  }>;
  assumptions: Record<string, unknown>;
  created_at: string;
};

const DEFAULT_FORM = {
  scenarioName: "base-case",
  totalInvestmentKrw: "1500000000",
  annualRevenueKrw: "280000000",
  annualOperatingCostKrw: "95000000",
  discountRate: "0.05",
  annualGrowthRate: "0.02",
  analysisYears: "10",
  exitValueKrw: "1800000000",
};

function getQueryErrorMessage(error: unknown) {
  if (error instanceof ApiClientError && (error.status === 401 || error.status === 403)) {
    return "API authentication is required for live feasibility analysis.";
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Request failed.";
}

function formatKrw(value: number) {
  return new Intl.NumberFormat("ko-KR", {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
  }).format(value);
}

export function FeasibilityWorkspaceClient() {
  const queryClient = useQueryClient();
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [formState, setFormState] = useState(DEFAULT_FORM);
  const [submissionError, setSubmissionError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [report, setReport] = useState<FeasibilityAnalysisResponse | null>(null);

  const projectsQuery = useQuery({
    queryKey: ["feasibility", "projects"],
    queryFn: () =>
      apiClient.get<PaginatedResponse<ProjectSummary>>("/projects?page=1&page_size=20", {
        useMock: false,
      }),
  });

  useEffect(() => {
    if (selectedProjectId || !projectsQuery.data?.items.length) {
      return;
    }

    setSelectedProjectId(projectsQuery.data.items[0].id);
  }, [projectsQuery.data?.items, selectedProjectId]);

  const latestReportQuery = useQuery({
    queryKey: ["feasibility", "latest", selectedProjectId],
    enabled: Boolean(selectedProjectId),
    queryFn: async () => {
      try {
        return await apiClient.get<FeasibilityAnalysisResponse>(
          `/finance/feasibility/${selectedProjectId}/latest`,
          { useMock: false },
        );
      } catch (error) {
        if (error instanceof ApiClientError && error.status === 404) {
          return null;
        }
        throw error;
      }
    },
  });

  useEffect(() => {
    if (latestReportQuery.data) {
      setReport(latestReportQuery.data);
    }
  }, [latestReportQuery.data]);

  const projectsErrorMessage = projectsQuery.error
    ? getQueryErrorMessage(projectsQuery.error)
    : "";
  const latestReportErrorMessage = latestReportQuery.error
    ? getQueryErrorMessage(latestReportQuery.error)
    : "";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmissionError("");

    if (!selectedProjectId) {
      setSubmissionError("Select a live project before running feasibility.");
      return;
    }

    setIsSubmitting(true);
    try {
      const nextReport = await apiClient.post<FeasibilityAnalysisResponse>(
        "/finance/feasibility",
        {
          useMock: false,
          body: {
            project_id: selectedProjectId,
            scenario_name: formState.scenarioName,
            total_investment_krw: Number(formState.totalInvestmentKrw),
            annual_revenue_krw: Number(formState.annualRevenueKrw),
            annual_operating_cost_krw: Number(formState.annualOperatingCostKrw),
            discount_rate: Number(formState.discountRate),
            annual_growth_rate: Number(formState.annualGrowthRate),
            analysis_years: Number(formState.analysisYears),
            exit_value_krw: Number(formState.exitValueKrw),
          },
        },
      );
      queryClient.setQueryData(
        ["feasibility", "latest", selectedProjectId],
        nextReport,
      );
      setReport(nextReport);
    } catch (error) {
      setSubmissionError(getQueryErrorMessage(error));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 p-6 font-sans dark:bg-slate-950 md:p-10">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-slate-500 dark:text-slate-400">
              Live underwriting
            </p>
            <h1 className="mt-3 text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white">
              Feasibility and LCC
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-7 text-slate-500 dark:text-slate-400">
              Run persisted feasibility scenarios against live project context and
              inspect NPV, IRR, payback, and annual cashflow assumptions.
            </p>
          </div>
        </header>

        {projectsQuery.isError ? (
          <WorkspaceQueryErrorCard
            title="Project list unavailable"
            description="The live feasibility project picker failed to load. Retry after restoring API connectivity or access token state."
            message={projectsErrorMessage}
            actionLabel="Retry"
            onRetry={() => {
              void projectsQuery.refetch();
            }}
          />
        ) : null}

        <div className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
          <Card className="rounded-[1.5rem] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <CardContent className="p-6">
              <CardTitle className="text-xl text-slate-900 dark:text-slate-100">
                Scenario inputs
              </CardTitle>
              <form className="mt-5 grid gap-4" onSubmit={handleSubmit}>
                {projectsQuery.isLoading ? (
                  <SkeletonLoader count={1} itemClassName="h-12" />
                ) : (
                  <label className="grid gap-2 text-sm font-medium text-slate-700 dark:text-slate-200">
                    Live project
                    <select
                      className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-blue-400 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
                      value={selectedProjectId}
                      onChange={(event) => {
                        setSelectedProjectId(event.target.value);
                        setSubmissionError("");
                      }}
                    >
                      <option value="" disabled>
                        Select a project
                      </option>
                      {(projectsQuery.data?.items ?? []).map((project) => (
                        <option key={project.id} value={project.id}>
                          {project.name}
                        </option>
                      ))}
                    </select>
                  </label>
                )}

                <label className="grid gap-2 text-sm font-medium text-slate-700 dark:text-slate-200">
                  Scenario name
                  <Input
                    value={formState.scenarioName}
                    onChange={(event) =>
                      setFormState((current) => ({
                        ...current,
                        scenarioName: event.target.value,
                      }))
                    }
                  />
                </label>

                <div className="grid gap-4 md:grid-cols-2">
                  <label className="grid gap-2 text-sm font-medium text-slate-700 dark:text-slate-200">
                    Total investment (KRW)
                    <Input
                      value={formState.totalInvestmentKrw}
                      onChange={(event) =>
                        setFormState((current) => ({
                          ...current,
                          totalInvestmentKrw: event.target.value,
                        }))
                      }
                    />
                  </label>
                  <label className="grid gap-2 text-sm font-medium text-slate-700 dark:text-slate-200">
                    Annual revenue (KRW)
                    <Input
                      value={formState.annualRevenueKrw}
                      onChange={(event) =>
                        setFormState((current) => ({
                          ...current,
                          annualRevenueKrw: event.target.value,
                        }))
                      }
                    />
                  </label>
                  <label className="grid gap-2 text-sm font-medium text-slate-700 dark:text-slate-200">
                    Annual operating cost (KRW)
                    <Input
                      value={formState.annualOperatingCostKrw}
                      onChange={(event) =>
                        setFormState((current) => ({
                          ...current,
                          annualOperatingCostKrw: event.target.value,
                        }))
                      }
                    />
                  </label>
                  <label className="grid gap-2 text-sm font-medium text-slate-700 dark:text-slate-200">
                    Exit value (KRW)
                    <Input
                      value={formState.exitValueKrw}
                      onChange={(event) =>
                        setFormState((current) => ({
                          ...current,
                          exitValueKrw: event.target.value,
                        }))
                      }
                    />
                  </label>
                  <label className="grid gap-2 text-sm font-medium text-slate-700 dark:text-slate-200">
                    Discount rate
                    <Input
                      value={formState.discountRate}
                      onChange={(event) =>
                        setFormState((current) => ({
                          ...current,
                          discountRate: event.target.value,
                        }))
                      }
                    />
                  </label>
                  <label className="grid gap-2 text-sm font-medium text-slate-700 dark:text-slate-200">
                    Annual growth rate
                    <Input
                      value={formState.annualGrowthRate}
                      onChange={(event) =>
                        setFormState((current) => ({
                          ...current,
                          annualGrowthRate: event.target.value,
                        }))
                      }
                    />
                  </label>
                </div>

                <label className="grid gap-2 text-sm font-medium text-slate-700 dark:text-slate-200">
                  Analysis years
                  <Input
                    value={formState.analysisYears}
                    onChange={(event) =>
                      setFormState((current) => ({
                        ...current,
                        analysisYears: event.target.value,
                      }))
                    }
                  />
                </label>

                {submissionError ? (
                  <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
                    {submissionError}
                  </div>
                ) : null}

                <Button type="submit" disabled={isSubmitting || projectsQuery.isLoading}>
                  {isSubmitting ? "Analyzing..." : "Run live feasibility"}
                </Button>
              </form>
            </CardContent>
          </Card>

          <div className="space-y-6">
            {latestReportQuery.isError ? (
              <WorkspaceQueryErrorCard
                title="Saved feasibility snapshot unavailable"
                description="The latest feasibility read model failed. Retry after restoring API connectivity or access token state."
                message={latestReportErrorMessage}
                actionLabel="Retry"
                onRetry={() => {
                  void latestReportQuery.refetch();
                }}
              />
            ) : null}

            {report ? (
              <>
                <div className="grid gap-4 md:grid-cols-4">
                  <Card className="rounded-[1.5rem] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
                    <CardContent className="p-6">
                      <p className="text-sm text-slate-500 dark:text-slate-400">NPV</p>
                      <p className="mt-3 text-2xl font-bold text-blue-600 dark:text-blue-400">
                        {formatKrw(report.npv)}
                      </p>
                    </CardContent>
                  </Card>
                  <Card className="rounded-[1.5rem] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
                    <CardContent className="p-6">
                      <p className="text-sm text-slate-500 dark:text-slate-400">IRR</p>
                      <p className="mt-3 text-2xl font-bold text-emerald-600 dark:text-emerald-400">
                        {(report.irr * 100).toFixed(2)}%
                      </p>
                    </CardContent>
                  </Card>
                  <Card className="rounded-[1.5rem] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
                    <CardContent className="p-6">
                      <p className="text-sm text-slate-500 dark:text-slate-400">Payback</p>
                      <p className="mt-3 text-2xl font-bold text-orange-500">
                        {report.payback_period_months}m
                      </p>
                    </CardContent>
                  </Card>
                  <Card className="rounded-[1.5rem] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
                    <CardContent className="p-6">
                      <p className="text-sm text-slate-500 dark:text-slate-400">Risk score</p>
                      <p className="mt-3 text-2xl font-bold text-slate-900 dark:text-slate-100">
                        {(report.risk_score * 100).toFixed(1)}
                      </p>
                    </CardContent>
                  </Card>
                </div>

                <Card className="rounded-[1.5rem] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
                  <CardContent className="p-6">
                    <CardTitle className="text-lg text-slate-900 dark:text-slate-100">
                      Cashflow scenario
                    </CardTitle>
                    <div className="mt-6 h-[360px] w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={report.cashflows}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
                          <XAxis dataKey="year" stroke="#64748b" />
                          <YAxis stroke="#64748b" />
                          <Tooltip />
                          <Legend />
                          <Bar dataKey="revenue_krw" name="Revenue" fill="#34d399" />
                          <Bar dataKey="operating_cost_krw" name="OPEX" fill="#f59e0b" />
                          <Bar dataKey="net_cashflow_krw" name="Net cashflow" fill="#3b82f6" />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </CardContent>
                </Card>
              </>
            ) : latestReportQuery.isLoading ? (
              <SkeletonLoader count={2} itemClassName="h-40" />
            ) : (
              <Card className="rounded-[1.5rem] border-dashed border-slate-300 bg-white/80 shadow-none dark:border-slate-700 dark:bg-slate-900/70">
                <CardContent className="p-8 text-center">
                  <CardTitle className="text-lg text-slate-900 dark:text-slate-100">
                    No feasibility snapshot yet
                  </CardTitle>
                  <p className="mt-3 text-sm leading-7 text-slate-500 dark:text-slate-400">
                    Run the live scenario once to persist NPV, IRR, payback, and
                    annual cashflow assumptions for this project.
                  </p>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
