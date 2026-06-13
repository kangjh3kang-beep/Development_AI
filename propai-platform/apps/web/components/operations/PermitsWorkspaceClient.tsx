"use client";

import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, CardTitle, Input } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { ApiClientError, apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";

/* ------------------------------------------------------------------ */
/*  Types                                                             */
/* ------------------------------------------------------------------ */

type ComplianceCheckResponse = {
  project_id?: string;
  address?: string;
  zoning_district?: string;
  results?: ComplianceItem[];
  overall_status?: string;
  summary?: string;
  checked_at?: string;
};

type ComplianceItem = {
  category?: string;
  rule?: string;
  status?: string;
  detail?: string;
  [key: string]: unknown;
};

/* ------------------------------------------------------------------ */
/*  Labels (ko primary)                                               */
/* ------------------------------------------------------------------ */

type Labels = {
  heroTitle: string;
  heroDescription: string;
  heroHint: string;
  tokenHint: string;
  authError: string;
  formTitle: string;
  addressLabel: string;
  zoningLabel: string;
  projectTypeLabel: string;
  floorCountLabel: string;
  submitAction: string;
  missingAddressError: string;
  summaryTitle: string;
  overallStatusLabel: string;
  checkedAtLabel: string;
  resultsTitle: string;
  categoryLabel: string;
  ruleLabel: string;
  statusLabel: string;
  detailLabel: string;
  placeholder: string;
  loadErrorTitle: string;
  loadErrorDetail: string;
  retryAction: string;
};

const KO_LABELS: Labels = {
  heroTitle: "인허가 라이브 작업 공간",
  heroDescription:
    "건축 허가 신청 내역을 조회하고, 실시간 건축법규 준수 여부를 AI로 점검합니다.",
  heroHint:
    "",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "라이브 작업 공간 호출을 위해 API 인증이 필요합니다.",
  formTitle: "인허가 점검 입력",
  addressLabel: "대지 주소",
  zoningLabel: "용도지역",
  projectTypeLabel: "프로젝트 유형",
  floorCountLabel: "층수",
  submitAction: "인허가 적합성 점검",
  missingAddressError: "주소를 입력해 주세요.",
  summaryTitle: "점검 요약",
  overallStatusLabel: "종합 판정",
  checkedAtLabel: "점검 일시",
  resultsTitle: "항목별 점검 결과",
  categoryLabel: "분류",
  ruleLabel: "규정",
  statusLabel: "판정",
  detailLabel: "상세",
  placeholder: "양식을 제출하면 건축법규 준수 점검 결과가 표시됩니다.",
  loadErrorTitle: "데이터 로드 실패",
  loadErrorDetail: "API로부터 데이터를 불러오지 못했습니다. 다시 시도해 주세요.",
  retryAction: "재시도",
};

const EN_LABELS: Labels = {
  heroTitle: "Permits Live Workspace",
  heroDescription:
    "Query permit applications and run real-time building-compliance checks via AI.",
  heroHint:
    "Calls POST /building-compliance/check to verify permit eligibility for the project.",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "API authentication is required for live workspace calls.",
  formTitle: "Compliance check input",
  addressLabel: "Site address",
  zoningLabel: "Zoning district",
  projectTypeLabel: "Project type",
  floorCountLabel: "Floor count",
  submitAction: "Run compliance check",
  missingAddressError: "Address is required.",
  summaryTitle: "Check summary",
  overallStatusLabel: "Overall status",
  checkedAtLabel: "Checked at",
  resultsTitle: "Item-level results",
  categoryLabel: "Category",
  ruleLabel: "Rule",
  statusLabel: "Status",
  detailLabel: "Detail",
  placeholder: "Submit the form to see building-compliance check results.",
  loadErrorTitle: "Data load failed",
  loadErrorDetail: "Failed to load data from the API. Please retry.",
  retryAction: "Retry",
};

const LABELS: Record<Locale, Labels> = {
  ko: KO_LABELS,
  en: EN_LABELS,
  "zh-CN": KO_LABELS,
};

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

function formatDate(locale: string, value: string) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function extractErrorMessage(error: unknown, authMessage: string) {
  if (error instanceof ApiClientError) {
    if (error.status === 401 || error.status === 403) return authMessage;
    return `API 요청이 상태 ${error.status}(으)로 실패했습니다.`;
  }
  if (error instanceof Error) return error.message;
  return "요청에 실패했습니다.";
}

function statusBadge(status?: string) {
  if (!status) return "bg-[var(--surface-soft)] text-[var(--text-secondary)]";
  const s = status.toLowerCase();
  if (s === "pass" || s === "approved" || s === "compliant")
    return "bg-emerald-500/15 text-emerald-500";
  if (s === "warning" || s === "review")
    return "bg-amber-500/15 text-amber-500";
  return "bg-red-500/15 text-red-500";
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

export function PermitsWorkspaceClient({
  locale,
}: {
  locale: Locale;
}) {
  const labels = LABELS[locale] || LABELS["ko"];
  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  const [workspaceError, setWorkspaceError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<ComplianceCheckResponse | null>(null);

  const [form, setForm] = useState({
    address: "",
    zoning: "제2종일반주거지역",
    projectType: "신축",
    floorCount: "15",
  });

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");

    const address = form.address.trim();
    if (!address) {
      setWorkspaceError(labels.missingAddressError);
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await apiClient.post<ComplianceCheckResponse>(
        "/permits/compliance-check",
        {
          useMock: false,
          body: {
            address,
            zoning_district: form.zoning,
            project_type: form.projectType,
            floor_count: Number(form.floorCount) || undefined,
          },
        },
      );
      setResult(res);
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
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
              {runtimeConfig.mode === "live" ? "LIVE" : "HYBRID"}
            </span>
          </div>
          <h3 className="mt-5 text-3xl font-bold text-[var(--text-primary)]">
            {labels.heroDescription}
          </h3>
          <p className="mt-4 max-w-3xl text-sm leading-8 text-[var(--text-secondary)]">
            {labels.heroHint}
          </p>
          {!canUseLiveApi && (
            <p className="mt-3 max-w-3xl text-sm leading-8 text-[var(--text-tertiary)]">
            {labels.tokenHint}
          </p>
          )}
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

      {/* Form */}
      <Card>
        <CardContent className="p-6">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
            {labels.formTitle}
          </p>
          <form className="mt-4 grid gap-3" onSubmit={handleSubmit}>
            <ProjectAddressInput
              value={form.address}
              onChange={(address) => setForm((c) => ({ ...c, address }))}
              label={labels.addressLabel}
              placeholder={labels.addressLabel}
            />
            <div className="grid gap-3 md:grid-cols-3">
              <Input
                value={form.zoning}
                onChange={(e) =>
                  setForm((c) => ({ ...c, zoning: e.target.value }))
                }
                placeholder={labels.zoningLabel}
              />
              <Input
                value={form.projectType}
                onChange={(e) =>
                  setForm((c) => ({ ...c, projectType: e.target.value }))
                }
                placeholder={labels.projectTypeLabel}
              />
              <Input
                type="number"
                value={form.floorCount}
                onChange={(e) =>
                  setForm((c) => ({ ...c, floorCount: e.target.value }))
                }
                placeholder={labels.floorCountLabel}
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

      {/* Results */}
      <div className="grid gap-6 xl:grid-cols-2">
        {/* Summary */}
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.summaryTitle}
            </p>
            {result ? (
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <MetricTile
                  label={labels.overallStatusLabel}
                  value={result.overall_status ?? "-"}
                />
                <MetricTile
                  label={labels.checkedAtLabel}
                  value={
                    result.checked_at
                      ? formatDate(locale, result.checked_at)
                      : "-"
                  }
                />
                {result.summary && (
                  <div className="col-span-full rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                    <p className="text-sm leading-7 text-[var(--text-secondary)]">
                      {result.summary}
                    </p>
                  </div>
                )}
              </div>
            ) : (
              <div className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
                {labels.placeholder}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Item results */}
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.resultsTitle}
            </p>
            {result?.results && result.results?.length > 0 ? (
              <div className="mt-4 space-y-3">
                {(result.results ?? []).map((item, idx) => (
                  <div
                    key={`${item.category ?? "item"}-${idx}`}
                    className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-4"
                  >
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-semibold text-[var(--text-primary)]">
                        {item.category ?? "-"}
                      </p>
                      <span
                        className={`rounded-full px-3 py-1 text-xs font-bold ${statusBadge(item.status)}`}
                      >
                        {item.status ?? "-"}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-[var(--text-tertiary)]">
                      {item.rule ?? ""}
                    </p>
                    {item.detail && (
                      <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                        {item.detail}
                      </p>
                    )}
                  </div>
                ))}
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
