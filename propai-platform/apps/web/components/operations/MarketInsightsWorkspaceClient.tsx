"use client";

import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, Input } from "@propai/ui";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { ApiClientError, apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";

/* ------------------------------------------------------------------ */
/*  Types                                                             */
/* ------------------------------------------------------------------ */

type AVMEstimateResponse = {
  id?: string;
  project_id?: string;
  estimated_price?: number;
  price_per_sqm?: number;
  confidence_score?: number;
  comparable_count?: number;
  model_version?: string;
  created_at?: string;
};

type TransactionItem = {
  deal_amount?: number;
  deal_year?: string;
  deal_month?: string;
  deal_day?: string;
  area_sqm?: number;
  floor?: number;
  apt_name?: string;
  dong?: string;
  [key: string]: unknown;
};

type TransactionsResponse = {
  items?: TransactionItem[];
  total_count?: number;
};

/* ------------------------------------------------------------------ */
/*  Labels                                                            */
/* ------------------------------------------------------------------ */

type Labels = {
  heroTitle: string;
  heroDescription: string;
  heroHint: string;
  tokenHint: string;
  authError: string;
  avmFormTitle: string;
  addressLabel: string;
  areaSqmLabel: string;
  submitAvmAction: string;
  missingAddressError: string;
  missingAreaError: string;
  txFormTitle: string;
  lawdCdLabel: string;
  dealYmLabel: string;
  submitTxAction: string;
  missingLawdCdError: string;
  avmResultTitle: string;
  estimatedPriceLabel: string;
  pricePerSqmLabel: string;
  confidenceLabel: string;
  comparablesLabel: string;
  modelLabel: string;
  txResultTitle: string;
  aptNameLabel: string;
  dealAmountLabel: string;
  areaLabel: string;
  floorLabel: string;
  dealDateLabel: string;
  placeholder: string;
};

const KO_LABELS: Labels = {
  heroTitle: "마켓 인사이트 라이브 워크스페이스",
  heroDescription:
    "AVM 시세 추정과 최근 실거래 데이터를 조합하여 시장 동향을 분석합니다.",
  heroHint:
    "POST /avm/estimate로 시세를 추정하고, GET /external/transactions/apt로 실거래 내역을 조회합니다.",
  tokenHint:
    "라이브 API 호출에는 NEXT_PUBLIC_API_ACCESS_TOKEN 또는 localStorage.propai_access_token이 필요합니다.",
  authError: "라이브 워크스페이스 호출을 위해 API 인증이 필요합니다.",
  avmFormTitle: "AVM 시세 추정 입력",
  addressLabel: "주소",
  areaSqmLabel: "면적 (sqm)",
  submitAvmAction: "시세 추정 실행",
  missingAddressError: "주소를 입력해 주세요.",
  missingAreaError: "양수인 면적 값을 입력해 주세요.",
  txFormTitle: "실거래 조회 입력",
  lawdCdLabel: "법정동 코드 (lawd_cd)",
  dealYmLabel: "거래 년월 (YYYYMM)",
  submitTxAction: "실거래 조회 실행",
  missingLawdCdError: "법정동 코드를 입력해 주세요.",
  avmResultTitle: "AVM 시세 추정 결과",
  estimatedPriceLabel: "추정 시세",
  pricePerSqmLabel: "sqm당 가격",
  confidenceLabel: "신뢰도",
  comparablesLabel: "비교 사례 수",
  modelLabel: "모델 버전",
  txResultTitle: "최근 실거래 내역",
  aptNameLabel: "단지명",
  dealAmountLabel: "거래가 (만원)",
  areaLabel: "면적",
  floorLabel: "층",
  dealDateLabel: "거래일",
  placeholder: "양식을 제출하면 결과가 표시됩니다.",
};

const EN_LABELS: Labels = {
  heroTitle: "Market Insights Live Workspace",
  heroDescription:
    "Combine AVM valuation estimates with recent transaction data to analyze market trends.",
  heroHint:
    "Calls POST /avm/estimate for valuation and GET /external/transactions/apt for transaction data.",
  tokenHint:
    "Live API calls require NEXT_PUBLIC_API_ACCESS_TOKEN or localStorage.propai_access_token.",
  authError: "API authentication is required for live workspace calls.",
  avmFormTitle: "AVM estimate input",
  addressLabel: "Address",
  areaSqmLabel: "Area (sqm)",
  submitAvmAction: "Run AVM estimate",
  missingAddressError: "Address is required.",
  missingAreaError: "A positive area value is required.",
  txFormTitle: "Transaction query input",
  lawdCdLabel: "District code (lawd_cd)",
  dealYmLabel: "Deal month (YYYYMM)",
  submitTxAction: "Query transactions",
  missingLawdCdError: "District code is required.",
  avmResultTitle: "AVM estimate result",
  estimatedPriceLabel: "Estimated price",
  pricePerSqmLabel: "Price per sqm",
  confidenceLabel: "Confidence",
  comparablesLabel: "Comparables",
  modelLabel: "Model version",
  txResultTitle: "Recent transactions",
  aptNameLabel: "Complex name",
  dealAmountLabel: "Deal amount (10K KRW)",
  areaLabel: "Area",
  floorLabel: "Floor",
  dealDateLabel: "Deal date",
  placeholder: "Submit the form to see results.",
};

const LABELS: Record<Locale, Labels> = {
  ko: KO_LABELS,
  en: EN_LABELS,
  "zh-CN": KO_LABELS,
};

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

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

function extractErrorMessage(error: unknown, authMessage: string) {
  if (error instanceof ApiClientError) {
    if (error.status === 401 || error.status === 403) return authMessage;
    return `API 요청이 상태 ${error.status}(으)로 실패했습니다.`;
  }
  if (error instanceof Error) return error.message;
  return "요청에 실패했습니다.";
}

function MetricTile({ label, value }: { label: string; value: string }) {
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

/* ------------------------------------------------------------------ */
/*  Component                                                         */
/* ------------------------------------------------------------------ */

export function MarketInsightsWorkspaceClient({
  locale,
}: {
  locale: Locale;
}) {
  const labels = LABELS[locale] || LABELS["ko"];
  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  const [workspaceError, setWorkspaceError] = useState("");
  const [isSubmittingAvm, setIsSubmittingAvm] = useState(false);
  const [avmResult, setAvmResult] = useState<AVMEstimateResponse | null>(null);

  const [avmForm, setAvmForm] = useState({
    address: "",
    areaSqm: "84",
  });

  const [txForm, setTxForm] = useState({
    lawdCd: "11680",
    dealYm: "202504",
  });

  const txQuery = useQuery({
    queryKey: ["transactions", txForm.lawdCd, txForm.dealYm],
    enabled: false,
  });

  const [txResult, setTxResult] = useState<TransactionsResponse | null>(null);
  const [isSubmittingTx, setIsSubmittingTx] = useState(false);

  async function handleAvmSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");

    const address = avmForm.address.trim();
    if (!address) {
      setWorkspaceError(labels.missingAddressError);
      return;
    }
    const areaSqm = Number(avmForm.areaSqm);
    if (!Number.isFinite(areaSqm) || areaSqm <= 0) {
      setWorkspaceError(labels.missingAreaError);
      return;
    }

    setIsSubmittingAvm(true);
    try {
      const res = await apiClient.post<AVMEstimateResponse>("/avm/estimate", {
        useMock: false,
        body: { address, area_sqm: areaSqm },
      });
      setAvmResult(res);
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsSubmittingAvm(false);
    }
  }

  async function handleTxSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");

    if (!txForm.lawdCd.trim()) {
      setWorkspaceError(labels.missingLawdCdError);
      return;
    }

    setIsSubmittingTx(true);
    try {
      const res = await apiClient.get<TransactionsResponse>(
        `/external/transactions/apt?lawd_cd=${txForm.lawdCd.trim()}&deal_ym=${txForm.dealYm.trim()}`,
        { useMock: false },
      );
      setTxResult(res);
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsSubmittingTx(false);
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
          {!canUseLiveApi && (
            <div className="mt-6 rounded-[var(--radius-xl)] border border-dashed border-[var(--line)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
              {labels.authError}
            </div>
          )}
          {workspaceError && (
            <div className="mt-6 rounded-[var(--radius-xl)] border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] p-5 text-sm leading-7 text-[var(--spot)]">
              {workspaceError}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Two forms */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* AVM Form */}
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.avmFormTitle}
            </p>
            <form className="mt-4 grid gap-3" onSubmit={handleAvmSubmit}>
              <Input
                value={avmForm.address}
                onChange={(e) =>
                  setAvmForm((c) => ({ ...c, address: e.target.value }))
                }
                placeholder={labels.addressLabel}
              />
              <Input
                type="number"
                value={avmForm.areaSqm}
                onChange={(e) =>
                  setAvmForm((c) => ({ ...c, areaSqm: e.target.value }))
                }
                placeholder={labels.areaSqmLabel}
              />
              <Button
                type="submit"
                disabled={!canUseLiveApi || isSubmittingAvm}
              >
                {isSubmittingAvm
                  ? `${labels.submitAvmAction}...`
                  : labels.submitAvmAction}
              </Button>
            </form>
          </CardContent>
        </Card>

        {/* Transaction Form */}
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.txFormTitle}
            </p>
            <form className="mt-4 grid gap-3" onSubmit={handleTxSubmit}>
              <Input
                value={txForm.lawdCd}
                onChange={(e) =>
                  setTxForm((c) => ({ ...c, lawdCd: e.target.value }))
                }
                placeholder={labels.lawdCdLabel}
              />
              <Input
                value={txForm.dealYm}
                onChange={(e) =>
                  setTxForm((c) => ({ ...c, dealYm: e.target.value }))
                }
                placeholder={labels.dealYmLabel}
              />
              <Button
                type="submit"
                disabled={!canUseLiveApi || isSubmittingTx}
              >
                {isSubmittingTx
                  ? `${labels.submitTxAction}...`
                  : labels.submitTxAction}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>

      {/* AVM Results */}
      <Card>
        <CardContent className="p-6">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
            {labels.avmResultTitle}
          </p>
          {avmResult ? (
            <div className="mt-4 grid gap-4 md:grid-cols-3">
              <MetricTile
                label={labels.estimatedPriceLabel}
                value={
                  avmResult.estimated_price != null
                    ? formatCurrency(locale, avmResult.estimated_price)
                    : "-"
                }
              />
              <MetricTile
                label={labels.pricePerSqmLabel}
                value={
                  avmResult.price_per_sqm != null
                    ? formatCurrency(locale, avmResult.price_per_sqm)
                    : "-"
                }
              />
              <MetricTile
                label={labels.confidenceLabel}
                value={
                  avmResult.confidence_score != null
                    ? formatPercent(avmResult.confidence_score)
                    : "-"
                }
              />
              <MetricTile
                label={labels.comparablesLabel}
                value={
                  avmResult.comparable_count != null
                    ? String(avmResult.comparable_count)
                    : "-"
                }
              />
              <MetricTile
                label={labels.modelLabel}
                value={avmResult.model_version ?? "-"}
              />
            </div>
          ) : (
            <div className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
              {labels.placeholder}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Transaction Results */}
      <Card>
        <CardContent className="p-6">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
            {labels.txResultTitle}
          </p>
          {txResult?.items && txResult.items.length > 0 ? (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)]">
                    <th className="pb-3 pr-4">{labels.aptNameLabel}</th>
                    <th className="pb-3 pr-4">{labels.dealAmountLabel}</th>
                    <th className="pb-3 pr-4">{labels.areaLabel}</th>
                    <th className="pb-3 pr-4">{labels.floorLabel}</th>
                    <th className="pb-3">{labels.dealDateLabel}</th>
                  </tr>
                </thead>
                <tbody>
                  {txResult.items.map((tx, idx) => (
                    <tr
                      key={idx}
                      className="border-t border-[var(--line)]"
                    >
                      <td className="py-3 pr-4 font-semibold text-[var(--text-primary)]">
                        {tx.apt_name ?? "-"}
                      </td>
                      <td className="py-3 pr-4 text-[var(--text-secondary)]">
                        {tx.deal_amount != null
                          ? tx.deal_amount.toLocaleString()
                          : "-"}
                      </td>
                      <td className="py-3 pr-4 text-[var(--text-secondary)]">
                        {tx.area_sqm != null ? `${tx.area_sqm} sqm` : "-"}
                      </td>
                      <td className="py-3 pr-4 text-[var(--text-secondary)]">
                        {tx.floor != null ? `${tx.floor}F` : "-"}
                      </td>
                      <td className="py-3 text-[var(--text-secondary)]">
                        {tx.deal_year ?? ""}.{tx.deal_month ?? ""}.
                        {tx.deal_day ?? ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
