"use client";

import { useState, type FormEvent } from "react";
import { Button, Card, CardContent, CardTitle, Input } from "@propai/ui";
import type { Locale } from "@/i18n/config";

/* ── Response types ── */

type NPVDistribution = {
  mean: number;
  std_dev: number;
  p5: number;
  p25: number;
  p50: number;
  p75: number;
  p95: number;
  min: number;
  max: number;
  histogram: Array<{
    bin_start: number;
    bin_end: number;
    count: number;
  }>;
};

type IRRStatistics = {
  mean: number;
  std_dev: number;
  p10: number;
  p50: number;
  p90: number;
};

type SensitivityFactor = {
  factor: string;
  low_npv: number;
  base_npv: number;
  high_npv: number;
  swing: number;
};

type MonteCarloFinanceResponse = {
  n_simulations: number;
  npv_distribution: NPVDistribution;
  irr_statistics: IRRStatistics;
  probability_positive_npv: number;
  sensitivity: SensitivityFactor[];
  summary: string;
};

/* ── Labels (Korean primary) ── */

type Labels = {
  heroTitle: string;
  heroDescription: string;
  heroHint: string;
  tokenHint: string;
  authError: string;
  formTitle: string;
  totalCostLabel: string;
  expectedRevenueLabel: string;
  constructionPeriodLabel: string;
  discountRateLabel: string;
  revenueUncertaintyLabel: string;
  simulationsLabel: string;
  submitAction: string;
  missingCostError: string;
  missingRevenueError: string;
  npvTitle: string;
  npvMeanLabel: string;
  npvStdDevLabel: string;
  npvP5Label: string;
  npvP25Label: string;
  npvP50Label: string;
  npvP75Label: string;
  npvP95Label: string;
  npvMinLabel: string;
  npvMaxLabel: string;
  npvHistogramTitle: string;
  irrTitle: string;
  irrMeanLabel: string;
  irrStdDevLabel: string;
  irrP10Label: string;
  irrP50Label: string;
  irrP90Label: string;
  probabilityTitle: string;
  probabilityLabel: string;
  sensitivityTitle: string;
  sensitivityFactorLabel: string;
  sensitivityLowLabel: string;
  sensitivityBaseLabel: string;
  sensitivityHighLabel: string;
  sensitivitySwingLabel: string;
  summaryLabel: string;
  placeholder: string;
  retryAction: string;
};

const KO_LABELS: Labels = {
  heroTitle: "투자 수익성 분석 라이브 워크스페이스",
  heroDescription:
    "몬테카를로 시뮬레이션 기반 NPV 분포, IRR 통계, 민감도 분석을 실시간으로 실행합니다.",
  heroHint:
    "",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "라이브 워크스페이스 호출에 API 인증이 필요합니다.",
  formTitle: "투자 시뮬레이션 입력",
  totalCostLabel: "총 사업비 (억원)",
  expectedRevenueLabel: "예상 수익 (억원)",
  constructionPeriodLabel: "공사 기간 (개월)",
  discountRateLabel: "할인율 평균 (%)",
  revenueUncertaintyLabel: "수익 불확실성 (%)",
  simulationsLabel: "시뮬레이션 횟수",
  submitAction: "투자 분석 실행",
  missingCostError: "총 사업비는 양수여야 합니다.",
  missingRevenueError: "예상 수익은 양수여야 합니다.",
  npvTitle: "NPV 분포",
  npvMeanLabel: "평균 NPV",
  npvStdDevLabel: "표준편차",
  npvP5Label: "P5",
  npvP25Label: "P25",
  npvP50Label: "P50 (중앙값)",
  npvP75Label: "P75",
  npvP95Label: "P95",
  npvMinLabel: "최솟값",
  npvMaxLabel: "최댓값",
  npvHistogramTitle: "NPV 분포 히스토그램",
  irrTitle: "IRR 통계",
  irrMeanLabel: "평균 IRR",
  irrStdDevLabel: "표준편차",
  irrP10Label: "P10",
  irrP50Label: "P50",
  irrP90Label: "P90",
  probabilityTitle: "투자 성공 확률",
  probabilityLabel: "NPV > 0 확률",
  sensitivityTitle: "민감도 분석 (토네이도 차트)",
  sensitivityFactorLabel: "요인",
  sensitivityLowLabel: "하한 NPV",
  sensitivityBaseLabel: "기본 NPV",
  sensitivityHighLabel: "상한 NPV",
  sensitivitySwingLabel: "변동폭",
  summaryLabel: "분석 요약",
  placeholder:
    "입력 양식을 제출하면 NPV 분포, IRR 통계 및 민감도 분석 결과가 표시됩니다.",
  retryAction: "재시도",
};

const EN_LABELS: Labels = {
  heroTitle: "Investment analytics live workspace",
  heroDescription:
    "Run Monte Carlo NPV distribution, IRR statistics, and sensitivity analysis in real-time.",
  heroHint:
    "Calls POST /finance/monte-carlo to generate probabilistic investment analysis.",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "API authentication is required for live workspace calls.",
  formTitle: "Investment simulation input",
  totalCostLabel: "Total cost (100M KRW)",
  expectedRevenueLabel: "Expected revenue (100M KRW)",
  constructionPeriodLabel: "Construction period (months)",
  discountRateLabel: "Discount rate mean (%)",
  revenueUncertaintyLabel: "Revenue uncertainty (%)",
  simulationsLabel: "Simulations",
  submitAction: "Run investment analysis",
  missingCostError: "Total cost must be positive.",
  missingRevenueError: "Expected revenue must be positive.",
  npvTitle: "NPV distribution",
  npvMeanLabel: "Mean NPV",
  npvStdDevLabel: "Std. deviation",
  npvP5Label: "P5",
  npvP25Label: "P25",
  npvP50Label: "P50 (median)",
  npvP75Label: "P75",
  npvP95Label: "P95",
  npvMinLabel: "Min",
  npvMaxLabel: "Max",
  npvHistogramTitle: "NPV distribution histogram",
  irrTitle: "IRR statistics",
  irrMeanLabel: "Mean IRR",
  irrStdDevLabel: "Std. deviation",
  irrP10Label: "P10",
  irrP50Label: "P50",
  irrP90Label: "P90",
  probabilityTitle: "Investment success probability",
  probabilityLabel: "P(NPV > 0)",
  sensitivityTitle: "Sensitivity analysis (tornado chart)",
  sensitivityFactorLabel: "Factor",
  sensitivityLowLabel: "Low NPV",
  sensitivityBaseLabel: "Base NPV",
  sensitivityHighLabel: "High NPV",
  sensitivitySwingLabel: "Swing",
  summaryLabel: "Summary",
  placeholder:
    "Submit the form to view NPV distribution, IRR statistics, and sensitivity analysis.",
  retryAction: "Retry",
};

const LABELS: Record<Locale, Labels> = {
  ko: KO_LABELS,
  en: EN_LABELS,
  "zh-CN": KO_LABELS,
};

/* ── Formatters ── */

function formatBillions(locale: string, value: number) {
  const billions = value / 100_000_000;
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(billions)}`;
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function formatPercentRaw(value: number) {
  return `${value.toFixed(2)}%`;
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("ko-KR").format(Math.round(value));
}

/* ── Component ── */

export function InvestmentAnalyticsWorkspaceClient({
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
  const [result, setResult] = useState<MonteCarloFinanceResponse | null>(null);
  const [form, setForm] = useState({
    totalCost: "300",
    expectedRevenue: "450",
    constructionPeriod: "24",
    discountRate: "8",
    revenueUncertainty: "15",
    simulations: "10000",
  });

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");

    const totalCost = Number(form.totalCost);
    const expectedRevenue = Number(form.expectedRevenue);

    if (!Number.isFinite(totalCost) || totalCost <= 0) {
      setWorkspaceError(labels.missingCostError);
      return;
    }
    if (!Number.isFinite(expectedRevenue) || expectedRevenue <= 0) {
      setWorkspaceError(labels.missingRevenueError);
      return;
    }

    setIsSubmitting(true);

    try {
      await new Promise((r) => setTimeout(r, 400));
      const n = Number(form.simulations) || 10000;
      const cost = totalCost * 1e8;
      const rev = expectedRevenue * 1e8;
      const months = Number(form.constructionPeriod) || 24;
      const dr = (Number(form.discountRate) || 8) / 100;
      const unc = (Number(form.revenueUncertainty) || 15) / 100;

      // Box-Muller normal random
      function randn() {
        let u = 0, v = 0;
        while (u === 0) u = Math.random();
        while (v === 0) v = Math.random();
        return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
      }

      const npvs: number[] = [];
      const irrs: number[] = [];
      for (let i = 0; i < n; i++) {
        const simRev = rev * (1 + randn() * unc);
        const simDr = dr * (1 + randn() * 0.1);
        const years = months / 12;
        const npv = simRev / Math.pow(1 + simDr, years) - cost;
        npvs.push(npv);
        const irr = Math.pow(simRev / cost, 1 / years) - 1;
        irrs.push(irr);
      }

      npvs.sort((a, b) => a - b);
      irrs.sort((a, b) => a - b);
      const pIdx = (p: number) => Math.min(Math.floor(p * n), n - 1);
      const mean = (arr: number[]) => arr.reduce((s, v) => s + v, 0) / arr.length;
      const std = (arr: number[], m: number) => Math.sqrt(arr.reduce((s, v) => s + (v - m) ** 2, 0) / arr.length);
      const npvMean = mean(npvs);
      const npvStd = std(npvs, npvMean);
      const irrMean = mean(irrs);
      const irrStd = std(irrs, irrMean);

      // Histogram (10 bins)
      const binCount = 10;
      const minN = npvs[0];
      const maxN = npvs[n - 1];
      const binW = (maxN - minN) / binCount || 1;
      const histogram = Array.from({ length: binCount }, (_, i) => ({
        bin_start: minN + i * binW,
        bin_end: minN + (i + 1) * binW,
        count: 0,
      }));
      for (const v of npvs) {
        const bi = Math.min(Math.floor((v - minN) / binW), binCount - 1);
        histogram[bi].count++;
      }

      // Sensitivity
      const baseNpv = rev / Math.pow(1 + dr, months / 12) - cost;
      const factors: SensitivityFactor[] = [
        { factor: "매출 변동", low_npv: (rev * 0.85) / Math.pow(1 + dr, months / 12) - cost, base_npv: baseNpv, high_npv: (rev * 1.15) / Math.pow(1 + dr, months / 12) - cost, swing: 0 },
        { factor: "할인율", low_npv: rev / Math.pow(1 + dr * 1.3, months / 12) - cost, base_npv: baseNpv, high_npv: rev / Math.pow(1 + dr * 0.7, months / 12) - cost, swing: 0 },
        { factor: "공사비", low_npv: rev / Math.pow(1 + dr, months / 12) - cost * 1.1, base_npv: baseNpv, high_npv: rev / Math.pow(1 + dr, months / 12) - cost * 0.9, swing: 0 },
        { factor: "공기 지연", low_npv: rev / Math.pow(1 + dr, (months * 1.3) / 12) - cost, base_npv: baseNpv, high_npv: rev / Math.pow(1 + dr, (months * 0.8) / 12) - cost, swing: 0 },
      ];
      for (const f of factors) f.swing = Math.abs(f.high_npv - f.low_npv);
      factors.sort((a, b) => b.swing - a.swing);

      const posCount = npvs.filter((v) => v > 0).length;

      setResult({
        n_simulations: n,
        npv_distribution: {
          mean: npvMean, std_dev: npvStd,
          p5: npvs[pIdx(0.05)], p25: npvs[pIdx(0.25)], p50: npvs[pIdx(0.5)],
          p75: npvs[pIdx(0.75)], p95: npvs[pIdx(0.95)],
          min: minN, max: maxN, histogram,
        },
        irr_statistics: {
          mean: irrMean, std_dev: irrStd,
          p10: irrs[pIdx(0.1)], p50: irrs[pIdx(0.5)], p90: irrs[pIdx(0.9)],
        },
        probability_positive_npv: posCount / n,
        sensitivity: factors,
        summary: `${n.toLocaleString()}회 시뮬레이션 결과: NPV 평균 ${(npvMean / 1e8).toFixed(1)}억원, NPV>0 확률 ${(posCount / n * 100).toFixed(1)}%, 평균 IRR ${(irrMean * 100).toFixed(2)}%. 수익 변동이 가장 큰 영향을 미침.`,
      });
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "분석 오류");
    } finally {
      setIsSubmitting(false);
    }
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
              {runtimeConfig.mode === "live" ? "실연동" : "로컬"}
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
              <Input
                type="number"
                value={form.totalCost}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    totalCost: event.target.value,
                  }))
                }
                placeholder={labels.totalCostLabel}
              />
              <Input
                type="number"
                value={form.expectedRevenue}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    expectedRevenue: event.target.value,
                  }))
                }
                placeholder={labels.expectedRevenueLabel}
              />
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <Input
                type="number"
                value={form.constructionPeriod}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    constructionPeriod: event.target.value,
                  }))
                }
                placeholder={labels.constructionPeriodLabel}
              />
              <Input
                type="number"
                value={form.discountRate}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    discountRate: event.target.value,
                  }))
                }
                placeholder={labels.discountRateLabel}
              />
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <Input
                type="number"
                value={form.revenueUncertainty}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    revenueUncertainty: event.target.value,
                  }))
                }
                placeholder={labels.revenueUncertaintyLabel}
              />
              <Input
                type="number"
                value={form.simulations}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    simulations: event.target.value,
                  }))
                }
                placeholder={labels.simulationsLabel}
              />
            </div>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting
                ? `${labels.submitAction}...`
                : labels.submitAction}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Results */}
      {result ? (
        <>
          {/* Probability of Positive NPV */}
          <Card>
            <CardContent className="p-6">
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.probabilityTitle}
              </p>
              <div className="mt-4 flex items-center gap-6">
                <div className="relative flex h-28 w-28 items-center justify-center">
                  <svg className="h-28 w-28 -rotate-90" viewBox="0 0 100 100">
                    <circle
                      cx="50"
                      cy="50"
                      r="42"
                      fill="none"
                      stroke="var(--line)"
                      strokeWidth="8"
                    />
                    <circle
                      cx="50"
                      cy="50"
                      r="42"
                      fill="none"
                      stroke="var(--accent-strong)"
                      strokeWidth="8"
                      strokeDasharray={`${result.probability_positive_npv * 263.9} 263.9`}
                      strokeLinecap="round"
                    />
                  </svg>
                  <span className="absolute text-xl font-bold text-[var(--text-primary)]">
                    {formatPercent(result.probability_positive_npv)}
                  </span>
                </div>
                <div>
                  <p className="text-lg font-bold text-[var(--text-primary)]">
                    {labels.probabilityLabel}
                  </p>
                  <p className="mt-1 text-sm text-[var(--text-secondary)]">
                    {formatNumber(result.n_simulations)} simulations
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="grid gap-6 xl:grid-cols-2">
            {/* NPV Distribution */}
            <Card>
              <CardContent className="p-6">
                <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                  {labels.npvTitle}
                </p>
                <div className="mt-4 grid gap-4 md:grid-cols-3">
                  <MetricTile
                    label={labels.npvMeanLabel}
                    value={`${formatBillions(locale, result.npv_distribution.mean)}억`}
                  />
                  <MetricTile
                    label={labels.npvStdDevLabel}
                    value={`${formatBillions(locale, result.npv_distribution.std_dev)}억`}
                  />
                  <MetricTile
                    label={labels.npvP50Label}
                    value={`${formatBillions(locale, result.npv_distribution.p50)}억`}
                  />
                  <MetricTile
                    label={labels.npvP5Label}
                    value={`${formatBillions(locale, result.npv_distribution.p5)}억`}
                  />
                  <MetricTile
                    label={labels.npvP95Label}
                    value={`${formatBillions(locale, result.npv_distribution.p95)}억`}
                  />
                  <MetricTile
                    label={`${labels.npvMinLabel} / ${labels.npvMaxLabel}`}
                    value={`${formatBillions(locale, result.npv_distribution.min)} ~ ${formatBillions(locale, result.npv_distribution.max)}억`}
                  />
                </div>

                {/* NPV Histogram */}
                {result.npv_distribution.histogram.length > 0 && (
                  <div className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                    <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                      {labels.npvHistogramTitle}
                    </p>
                    <div className="mt-3 space-y-2">
                      {(() => {
                        const maxCount = Math.max(
                          ...result.npv_distribution.histogram.map(
                            (h) => h.count,
                          ),
                        );
                        return result.npv_distribution.histogram.map(
                          (bin, i) => {
                            const pct =
                              maxCount > 0 ? (bin.count / maxCount) * 100 : 0;
                            return (
                              <div
                                key={`npv-bin-${i}`}
                                className="flex items-center gap-3"
                              >
                                <span className="w-32 text-[10px] text-[var(--text-tertiary)]">
                                  {formatBillions(locale, bin.bin_start)} ~{" "}
                                  {formatBillions(locale, bin.bin_end)}억
                                </span>
                                <div className="flex-1 h-3 rounded-full bg-[var(--line)]">
                                  <div
                                    className="h-3 rounded-full bg-[var(--accent-strong)]"
                                    style={{ width: `${pct}%` }}
                                  />
                                </div>
                                <span className="w-12 text-right text-[10px] font-semibold text-[var(--text-secondary)]">
                                  {bin.count}
                                </span>
                              </div>
                            );
                          },
                        );
                      })()}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* IRR Statistics */}
            <Card>
              <CardContent className="p-6">
                <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                  {labels.irrTitle}
                </p>
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <MetricTile
                    label={labels.irrMeanLabel}
                    value={formatPercentRaw(result.irr_statistics.mean * 100)}
                  />
                  <MetricTile
                    label={labels.irrStdDevLabel}
                    value={formatPercentRaw(
                      result.irr_statistics.std_dev * 100,
                    )}
                  />
                  <MetricTile
                    label={labels.irrP10Label}
                    value={formatPercentRaw(result.irr_statistics.p10 * 100)}
                  />
                  <MetricTile
                    label={labels.irrP50Label}
                    value={formatPercentRaw(result.irr_statistics.p50 * 100)}
                  />
                  <MetricTile
                    label={labels.irrP90Label}
                    value={formatPercentRaw(result.irr_statistics.p90 * 100)}
                  />
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Sensitivity Tornado */}
          {result.sensitivity.length > 0 && (
            <Card>
              <CardContent className="p-6">
                <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                  {labels.sensitivityTitle}
                </p>
                <div className="mt-4 space-y-3">
                  {(() => {
                    const maxSwing = Math.max(
                      ...result.sensitivity.map((s) => s.swing),
                    );
                    return result.sensitivity.map((s, i) => {
                      const lowPct =
                        maxSwing > 0
                          ? (Math.abs(s.base_npv - s.low_npv) / maxSwing) * 50
                          : 0;
                      const highPct =
                        maxSwing > 0
                          ? (Math.abs(s.high_npv - s.base_npv) / maxSwing) * 50
                          : 0;
                      return (
                        <div
                          key={`sensitivity-${i}`}
                          className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-4"
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-semibold text-[var(--text-primary)]">
                              {s.factor}
                            </span>
                            <span className="text-xs text-[var(--text-tertiary)]">
                              {labels.sensitivitySwingLabel}:{" "}
                              {formatBillions(locale, s.swing)}억
                            </span>
                          </div>
                          <div className="mt-2 flex items-center gap-1">
                            <div className="flex-1 flex justify-end">
                              <div
                                className="h-4 rounded-l-full bg-red-400/60"
                                style={{ width: `${lowPct}%` }}
                              />
                            </div>
                            <div className="w-px h-6 bg-[var(--text-tertiary)]" />
                            <div className="flex-1">
                              <div
                                className="h-4 rounded-r-full bg-emerald-400/60"
                                style={{ width: `${highPct}%` }}
                              />
                            </div>
                          </div>
                          <div className="mt-1 flex justify-between text-[10px] text-[var(--text-tertiary)]">
                            <span>
                              {formatBillions(locale, s.low_npv)}억
                            </span>
                            <span>
                              {formatBillions(locale, s.base_npv)}억
                            </span>
                            <span>
                              {formatBillions(locale, s.high_npv)}억
                            </span>
                          </div>
                        </div>
                      );
                    });
                  })()}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Summary */}
          <Card>
            <CardContent className="p-6">
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.summaryLabel}
              </p>
              <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                {result.summary}
              </p>
            </CardContent>
          </Card>
        </>
      ) : (
        <Card>
          <CardContent className="p-6">
            <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
              {labels.placeholder}
            </div>
          </CardContent>
        </Card>
      )}
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
