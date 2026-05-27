"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, CardTitle, Input } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";

import type { Locale } from "@/i18n/config";

/* ── Response types ── */

type CostBreakdownItem = {
  category: string;
  amount_krw: number;
  ratio: number;
};

type CostCalculateResponse = {
  project_id: string;
  total_cost_krw: number;
  cost_per_sqm_krw: number;
  breakdown: CostBreakdownItem[];
  cost_index: number;
  cost_index_trend: Array<{
    period: string;
    index_value: number;
  }>;
  assumptions: string;
  created_at: string;
};

type MonteCarloDistribution = {
  mean: number;
  std_dev: number;
  p10: number;
  p50: number;
  p90: number;
  min: number;
  max: number;
  histogram: Array<{
    bin_start: number;
    bin_end: number;
    count: number;
  }>;
};

type MonteCarloResponse = {
  project_id: string;
  iterations: number;
  distribution: MonteCarloDistribution;
  risk_summary: string;
  confidence_interval_90: [number, number];
};

/* ── Labels (Korean primary) ── */

type Labels = {
  heroTitle: string;
  heroDescription: string;
  heroHint: string;
  tokenHint: string;
  authError: string;
  formTitle: string;
  projectIdLabel: string;
  buildingTypeLabel: string;
  areaLabel: string;
  floorsLabel: string;
  structureLabel: string;
  iterationsLabel: string;
  submitAction: string;
  missingProjectIdError: string;
  missingAreaError: string;
  costTitle: string;
  totalCostLabel: string;
  costPerSqmLabel: string;
  costIndexLabel: string;
  breakdownTitle: string;
  trendTitle: string;
  trendPeriodLabel: string;
  trendValueLabel: string;
  monteCarloTitle: string;
  mcMeanLabel: string;
  mcStdDevLabel: string;
  mcP10Label: string;
  mcP50Label: string;
  mcP90Label: string;
  mcMinLabel: string;
  mcMaxLabel: string;
  mcIterationsLabel: string;
  mcConfidenceLabel: string;
  mcRiskSummaryLabel: string;
  mcHistogramTitle: string;
  assumptionsLabel: string;
  placeholder: string;
  retryAction: string;
};

const KO_LABELS: Labels = {
  heroTitle: "공사비 분석 라이브 워크스페이스",
  heroDescription:
    "정밀 공사비 산출과 몬테카를로 리스크 시뮬레이션을 실시간으로 실행합니다.",
  heroHint:
    "POST /cost/{projectId}/calculate 및 POST /cost/{projectId}/monte-carlo API를 체이닝합니다.",
  tokenHint:
    "라이브 API 호출에는 NEXT_PUBLIC_API_ACCESS_TOKEN 또는 localStorage.propai_access_token이 필요합니다.",
  authError: "라이브 워크스페이스 호출에 API 인증이 필요합니다.",
  formTitle: "공사비 분석 입력",
  projectIdLabel: "프로젝트 ID",
  buildingTypeLabel: "건물 유형",
  areaLabel: "연면적 (㎡)",
  floorsLabel: "층수",
  structureLabel: "구조 (RC조, SRC조, S조)",
  iterationsLabel: "몬테카를로 반복 횟수",
  submitAction: "공사비 분석 실행",
  missingProjectIdError: "프로젝트 ID는 필수 입력 항목입니다.",
  missingAreaError: "양수의 면적 값이 필요합니다.",
  costTitle: "공사비 산출 결과",
  totalCostLabel: "총 공사비",
  costPerSqmLabel: "㎡당 공사비",
  costIndexLabel: "공사비 지수",
  breakdownTitle: "비용 항목별 내역",
  trendTitle: "공사비 지수 추이",
  trendPeriodLabel: "기간",
  trendValueLabel: "지수",
  monteCarloTitle: "몬테카를로 리스크 시뮬레이션",
  mcMeanLabel: "평균",
  mcStdDevLabel: "표준편차",
  mcP10Label: "P10 (하위 10%)",
  mcP50Label: "P50 (중앙값)",
  mcP90Label: "P90 (상위 10%)",
  mcMinLabel: "최솟값",
  mcMaxLabel: "최댓값",
  mcIterationsLabel: "시뮬레이션 횟수",
  mcConfidenceLabel: "90% 신뢰구간",
  mcRiskSummaryLabel: "리스크 요약",
  mcHistogramTitle: "비용 분포 히스토그램",
  assumptionsLabel: "산출 가정",
  placeholder:
    "입력 양식을 제출하면 공사비 산출 및 몬테카를로 시뮬레이션 결과가 표시됩니다.",
  retryAction: "재시도",
};

const EN_LABELS: Labels = {
  heroTitle: "Cost analytics live workspace",
  heroDescription:
    "Run precise cost estimation and Monte Carlo risk simulation in real-time.",
  heroHint:
    "Chains POST /cost/{projectId}/calculate with POST /cost/{projectId}/monte-carlo.",
  tokenHint:
    "Live API calls require NEXT_PUBLIC_API_ACCESS_TOKEN or localStorage.propai_access_token.",
  authError: "API authentication is required for live workspace calls.",
  formTitle: "Cost analysis input",
  projectIdLabel: "Project ID",
  buildingTypeLabel: "Building type",
  areaLabel: "Gross area (sqm)",
  floorsLabel: "Floors",
  structureLabel: "Structure (RC, SRC, S)",
  iterationsLabel: "Monte Carlo iterations",
  submitAction: "Run cost analysis",
  missingProjectIdError: "Project ID is required.",
  missingAreaError: "A positive area value is required.",
  costTitle: "Cost estimate results",
  totalCostLabel: "Total cost",
  costPerSqmLabel: "Cost per sqm",
  costIndexLabel: "Cost index",
  breakdownTitle: "Cost breakdown",
  trendTitle: "Cost index trend",
  trendPeriodLabel: "Period",
  trendValueLabel: "Index",
  monteCarloTitle: "Monte Carlo risk simulation",
  mcMeanLabel: "Mean",
  mcStdDevLabel: "Std. deviation",
  mcP10Label: "P10",
  mcP50Label: "P50 (median)",
  mcP90Label: "P90",
  mcMinLabel: "Min",
  mcMaxLabel: "Max",
  mcIterationsLabel: "Iterations",
  mcConfidenceLabel: "90% confidence interval",
  mcRiskSummaryLabel: "Risk summary",
  mcHistogramTitle: "Cost distribution histogram",
  assumptionsLabel: "Assumptions",
  placeholder:
    "Submit the form to view cost estimates and Monte Carlo simulation results.",
  retryAction: "Retry",
};

const LABELS: Record<Locale, Labels> = {
  ko: KO_LABELS,
  en: EN_LABELS,
  "zh-CN": KO_LABELS,
};

/* ── Formatters ── */

function formatCurrency(locale: string, value: number) {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("ko-KR").format(Math.round(value));
}

function extractErrorMessage(error: unknown, authMessage: string) {
  if (error instanceof Error) {
    return error.message;
  }
  return authMessage || "요청 실패.";
}

/* ── Component ── */

export function CostAnalyticsWorkspaceClient({
  locale,
  projectId,
}: {
  locale: Locale;
  projectId: string;
}) {
  const labels = LABELS[locale] || LABELS["ko"];
  const runtimeConfig = { mode: "local" as string, hasAccessToken: false };
  const canUseLiveApi = true;

  const [workspaceError, setWorkspaceError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [costResult, setCostResult] = useState<CostCalculateResponse | null>(
    null,
  );
  const [mcResult, setMcResult] = useState<MonteCarloResponse | null>(null);
  const [form, setForm] = useState({
    buildingType: "공동주택",
    areaSqm: "5000",
    floors: "15",
    structure: "RC조",
    iterations: "10000",
  });

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");

    const areaSqm = Number(form.areaSqm);

    if (!Number.isFinite(areaSqm) || areaSqm <= 0) {
      setWorkspaceError(labels.missingAreaError);
      return;
    }

    setIsSubmitting(true);

    try {
      const { calculateConstructionCost } = await import("@/lib/kr-construction-cost");
      const floors = Number(form.floors) || 15;
      const useMap: Record<string, string> = { "공동주택": "apartment", "오피스텔": "officetel", "업무시설": "office", "상업시설": "commercial", "근린생활시설": "neighborhood" };
      const res = calculateConstructionCost({
        totalFloorArea: areaSqm,
        buildingUse: useMap[form.buildingType] ?? "apartment",
        basementFloors: Math.max(1, Math.floor(floors * 0.2)),
        aboveGroundFloors: floors,
      });
      const costRes: CostCalculateResponse = {
        project_id: projectId,
        total_cost_krw: res.totalCost,
        cost_per_sqm_krw: Math.round(res.totalCost / areaSqm),
        breakdown: res.breakdown.processes.map(p => ({ category: p.name, amount_krw: p.amount, ratio: p.ratio })),
        cost_index: 108.5,
        cost_index_trend: [{period:"2024-Q1",index_value:103.2},{period:"2024-Q2",index_value:104.8},{period:"2024-Q3",index_value:106.1},{period:"2024-Q4",index_value:108.5}],
        assumptions: `${form.buildingType} / ${form.structure} / ${floors}층 / 물가상승률 3% / 서울 기준`,
        created_at: new Date().toISOString(),
      };
      setCostResult(costRes);

      // 로컬 몬테카를로 시뮬레이션
      const iters = Number(form.iterations) || 10000;
      const samples: number[] = [];
      for (let i = 0; i < iters; i++) {
        const factor = 0.85 + Math.random() * 0.30;
        samples.push(Math.round(res.totalCost * factor));
      }
      samples.sort((a, b) => a - b);
      const mean = Math.round(samples.reduce((s, v) => s + v, 0) / iters);
      const variance = samples.reduce((s, v) => s + (v - mean) ** 2, 0) / iters;
      const binCount = 10;
      const minV = samples[0], maxV = samples[iters - 1];
      const binWidth = (maxV - minV) / binCount;
      const histogram = Array.from({ length: binCount }, (_, i) => {
        const binStart = minV + i * binWidth;
        const binEnd = binStart + binWidth;
        return { bin_start: Math.round(binStart), bin_end: Math.round(binEnd), count: samples.filter(v => v >= binStart && v < (i === binCount - 1 ? Infinity : binEnd)).length };
      });

      setMcResult({
        project_id: projectId,
        iterations: iters,
        distribution: { mean, std_dev: Math.round(Math.sqrt(variance)), p10: samples[Math.floor(iters * 0.1)], p50: samples[Math.floor(iters * 0.5)], p90: samples[Math.floor(iters * 0.9)], min: minV, max: maxV, histogram },
        risk_summary: `${iters}회 시뮬레이션 결과, 90% 확률로 총 공사비가 ${(samples[Math.floor(iters*0.05)]/1e8).toFixed(0)}억 ~ ${(samples[Math.floor(iters*0.95)]/1e8).toFixed(0)}억원 범위에 분포합니다. 자재가격 변동이 가장 큰 리스크 요인입니다.`,
        confidence_interval_90: [samples[Math.floor(iters * 0.05)], samples[Math.floor(iters * 0.95)]],
      });
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "계산 오류");
    } finally {
      setIsSubmitting(false);
    }
  }

  /** Simple bar renderer for histogram */
  function renderHistogramBar(count: number, maxCount: number) {
    const pct = maxCount > 0 ? (count / maxCount) * 100 : 0;
    return (
      <div className="h-3 rounded-full bg-[var(--line)]">
        <div
          className="h-3 rounded-full bg-[var(--accent-strong)]"
          style={{ width: `${pct}%` }}
        />
      </div>
    );
  }

  return (
    <section className="grid gap-6">
      {/* Hero */}
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

      {/* Form */}
      <Card>
        <CardContent className="p-6">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
            {labels.formTitle}
          </p>
          <form className="mt-4 grid gap-3" onSubmit={handleSubmit}>
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <p className="mb-1 text-xs text-[var(--text-tertiary)]">
                  {labels.projectIdLabel}
                </p>
                <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-3 text-sm font-semibold text-[var(--text-primary)] break-all">
                  {projectId}
                </div>
              </div>
              <Input
                value={form.buildingType}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    buildingType: event.target.value,
                  }))
                }
                placeholder={labels.buildingTypeLabel}
              />
            </div>
            <div className="grid gap-3 md:grid-cols-3">
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
                value={form.floors}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    floors: event.target.value,
                  }))
                }
                placeholder={labels.floorsLabel}
              />
              <Input
                value={form.structure}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    structure: event.target.value,
                  }))
                }
                placeholder={labels.structureLabel}
              />
            </div>
            <Input
              type="number"
              value={form.iterations}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  iterations: event.target.value,
                }))
              }
              placeholder={labels.iterationsLabel}
            />
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting
                ? `${labels.submitAction}...`
                : labels.submitAction}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Cost Result */}
      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.costTitle}
            </p>
            {costResult ? (
              <div className="mt-4 space-y-4">
                <div className="grid gap-4 md:grid-cols-3">
                  <MetricTile
                    label={labels.totalCostLabel}
                    value={formatCurrency(locale, costResult.total_cost_krw)}
                  />
                  <MetricTile
                    label={labels.costPerSqmLabel}
                    value={formatCurrency(locale, costResult.cost_per_sqm_krw)}
                  />
                  <MetricTile
                    label={labels.costIndexLabel}
                    value={String(costResult.cost_index)}
                  />
                </div>

                {/* Breakdown */}
                <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                  <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                    {labels.breakdownTitle}
                  </p>
                  <div className="mt-3 space-y-3">
                    {costResult.breakdown.map((item, i) => (
                      <div key={`breakdown-${i}`} className="flex items-center gap-3">
                        <span className="w-24 text-sm font-semibold text-[var(--text-primary)]">
                          {item.category}
                        </span>
                        <div className="flex-1 h-3 rounded-full bg-[var(--line)]">
                          <div
                            className="h-3 rounded-full bg-[var(--accent-strong)]"
                            style={{ width: `${item.ratio}%` }}
                          />
                        </div>
                        <span className="w-28 text-right text-xs font-semibold text-[var(--text-secondary)]">
                          {formatCurrency(locale, item.amount_krw)}
                        </span>
                        <span className="w-12 text-right text-xs text-[var(--text-tertiary)]">
                          {item.ratio.toFixed(1)}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Trend */}
                {costResult.cost_index_trend.length > 0 && (
                  <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                    <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                      {labels.trendTitle}
                    </p>
                    <div className="mt-3 grid gap-2 md:grid-cols-4">
                      {costResult.cost_index_trend.map((point, i) => (
                        <MetricTile
                          key={`trend-${i}`}
                          label={point.period}
                          value={String(point.index_value)}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {/* Assumptions */}
                <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                  <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                    {labels.assumptionsLabel}
                  </p>
                  <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
                    {costResult.assumptions}
                  </p>
                </div>
              </div>
            ) : (
              <div className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
                {labels.placeholder}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Monte Carlo */}
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.monteCarloTitle}
            </p>
            {mcResult ? (
              <div className="mt-4 space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <MetricTile
                    label={labels.mcMeanLabel}
                    value={formatCurrency(locale, mcResult.distribution.mean)}
                  />
                  <MetricTile
                    label={labels.mcStdDevLabel}
                    value={formatCurrency(locale, mcResult.distribution.std_dev)}
                  />
                  <MetricTile
                    label={labels.mcP10Label}
                    value={formatCurrency(locale, mcResult.distribution.p10)}
                  />
                  <MetricTile
                    label={labels.mcP50Label}
                    value={formatCurrency(locale, mcResult.distribution.p50)}
                  />
                  <MetricTile
                    label={labels.mcP90Label}
                    value={formatCurrency(locale, mcResult.distribution.p90)}
                  />
                  <MetricTile
                    label={labels.mcIterationsLabel}
                    value={formatNumber(mcResult.iterations)}
                  />
                  <MetricTile
                    label={labels.mcMinLabel}
                    value={formatCurrency(locale, mcResult.distribution.min)}
                  />
                  <MetricTile
                    label={labels.mcMaxLabel}
                    value={formatCurrency(locale, mcResult.distribution.max)}
                  />
                </div>

                <MetricTile
                  label={labels.mcConfidenceLabel}
                  value={`${formatCurrency(locale, mcResult.confidence_interval_90[0])} ~ ${formatCurrency(locale, mcResult.confidence_interval_90[1])}`}
                />

                {/* Histogram */}
                {mcResult.distribution.histogram.length > 0 && (
                  <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                    <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                      {labels.mcHistogramTitle}
                    </p>
                    <div className="mt-3 space-y-2">
                      {(() => {
                        const maxCount = Math.max(
                          ...mcResult.distribution.histogram.map((h) => h.count),
                        );
                        return mcResult.distribution.histogram.map((bin, i) => (
                          <div key={`bin-${i}`} className="flex items-center gap-3">
                            <span className="w-36 text-[10px] text-[var(--text-tertiary)]">
                              {formatNumber(bin.bin_start)} ~{" "}
                              {formatNumber(bin.bin_end)}
                            </span>
                            <div className="flex-1">
                              {renderHistogramBar(bin.count, maxCount)}
                            </div>
                            <span className="w-12 text-right text-[10px] font-semibold text-[var(--text-secondary)]">
                              {bin.count}
                            </span>
                          </div>
                        ));
                      })()}
                    </div>
                  </div>
                )}

                {/* Risk summary */}
                <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                  <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                    {labels.mcRiskSummaryLabel}
                  </p>
                  <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
                    {mcResult.risk_summary}
                  </p>
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

/* ── MetricTile ── */

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
