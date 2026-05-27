"use client";

import { useState, type FormEvent } from "react";
import { Button, Card, CardContent, Input } from "@propai/ui";
import { ApiClientError, apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";

/* ------------------------------------------------------------------ */
/*  Types                                                             */
/* ------------------------------------------------------------------ */

type RegulationAnalysisResponse = {
  address?: string;
  zoning_district?: string;
  building_coverage_ratio?: { max: number; unit: string };
  floor_area_ratio?: { max: number; unit: string };
  height_limit?: { value: number; unit: string };
  parking_standard?: { description: string };
  applicable_laws?: Array<{
    law: string;
    article: string;
    impact: string;
    level: string;
  }>;
  special_zones?: string[];
  recommendations?: string[];
  summary?: string;
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
  formTitle: string;
  addressLabel: string;
  pnuLabel: string;
  zoningLabel: string;
  submitAction: string;
  missingAddressError: string;
  restrictionsTitle: string;
  buildingCoverageLabel: string;
  floorAreaRatioLabel: string;
  heightLimitLabel: string;
  parkingStandardLabel: string;
  lawsTitle: string;
  specialZonesTitle: string;
  recommendationsTitle: string;
  summaryTitle: string;
  placeholder: string;
};

const KO_LABELS: Labels = {
  heroTitle: "규제 분석 라이브 워크스페이스",
  heroDescription:
    "해당 토지에 적용되는 건축 규제(건폐율, 용적률, 높이 제한, 주차 기준)를 AI로 분석합니다.",
  heroHint:
    "POST /building-compliance/check API를 호출하여 규제 분석 결과를 반환합니다.",
  tokenHint:
    "라이브 API 호출에는 NEXT_PUBLIC_API_ACCESS_TOKEN 또는 localStorage.propai_access_token이 필요합니다.",
  authError: "라이브 워크스페이스 호출을 위해 API 인증이 필요합니다.",
  formTitle: "규제 분석 입력",
  addressLabel: "주소",
  pnuLabel: "PNU 코드 (선택)",
  zoningLabel: "용도지역",
  submitAction: "규제 분석 실행",
  missingAddressError: "주소를 입력해 주세요.",
  restrictionsTitle: "건축 제한 요약",
  buildingCoverageLabel: "건폐율 한도",
  floorAreaRatioLabel: "용적률 한도",
  heightLimitLabel: "높이 제한",
  parkingStandardLabel: "주차 기준",
  lawsTitle: "적용 법규",
  specialZonesTitle: "해당 특별구역",
  recommendationsTitle: "규제 대응 전략",
  summaryTitle: "AI 규제 종합 분석",
  placeholder: "양식을 제출하면 규제 분석 결과가 표시됩니다.",
};

const EN_LABELS: Labels = {
  heroTitle: "Regulations Live Workspace",
  heroDescription:
    "Analyze building regulations (coverage ratio, FAR, height limit, parking standards) via AI.",
  heroHint:
    "Calls POST /building-compliance/check to return regulation analysis.",
  tokenHint:
    "Live API calls require NEXT_PUBLIC_API_ACCESS_TOKEN or localStorage.propai_access_token.",
  authError: "API authentication is required for live workspace calls.",
  formTitle: "Regulation analysis input",
  addressLabel: "Address",
  pnuLabel: "PNU code (optional)",
  zoningLabel: "Zoning district",
  submitAction: "Run regulation analysis",
  missingAddressError: "Address is required.",
  restrictionsTitle: "Building restriction summary",
  buildingCoverageLabel: "Building coverage limit",
  floorAreaRatioLabel: "Floor area ratio limit",
  heightLimitLabel: "Height limit",
  parkingStandardLabel: "Parking standard",
  lawsTitle: "Applicable laws",
  specialZonesTitle: "Special zones",
  recommendationsTitle: "Regulatory response strategies",
  summaryTitle: "AI regulation analysis",
  placeholder: "Submit the form to see regulation analysis results.",
};

const LABELS: Record<Locale, Labels> = {
  ko: KO_LABELS,
  en: EN_LABELS,
  "zh-CN": KO_LABELS,
};

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

function extractErrorMessage(error: unknown, authMessage: string) {
  if (error instanceof ApiClientError) {
    if (error.status === 401 || error.status === 403) return authMessage;
    return `API 요청이 상태 ${error.status}(으)로 실패했습니다.`;
  }
  if (error instanceof Error) return error.message;
  return "요청에 실패했습니다.";
}

function levelBadge(level: string) {
  const l = level.toLowerCase();
  if (l === "high") return "bg-red-500/15 text-red-500";
  if (l === "medium") return "bg-amber-500/15 text-amber-500";
  return "bg-emerald-500/15 text-emerald-500";
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[var(--radius-xl)] bg-[var(--surface)] p-4">
      <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-2 text-lg font-bold text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Component                                                         */
/* ------------------------------------------------------------------ */

export function RegulationsWorkspaceClient({
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
  const [result, setResult] = useState<RegulationAnalysisResponse | null>(null);

  const [form, setForm] = useState({
    address: "",
    pnu: "",
    zoning: "제2종일반주거지역",
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
      const res = await apiClient.post<RegulationAnalysisResponse>(
        "/building-compliance/check",
        {
          useMock: false,
          body: {
            address,
            pnu: form.pnu.trim() || undefined,
            zoning_district: form.zoning,
            analysis_type: "regulation",
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

      {/* Form */}
      <Card>
        <CardContent className="p-6">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
            {labels.formTitle}
          </p>
          <form className="mt-4 grid gap-3" onSubmit={handleSubmit}>
            <Input
              value={form.address}
              onChange={(e) =>
                setForm((c) => ({ ...c, address: e.target.value }))
              }
              placeholder={labels.addressLabel}
            />
            <div className="grid gap-3 md:grid-cols-2">
              <Input
                value={form.pnu}
                onChange={(e) =>
                  setForm((c) => ({ ...c, pnu: e.target.value }))
                }
                placeholder={labels.pnuLabel}
              />
              <Input
                value={form.zoning}
                onChange={(e) =>
                  setForm((c) => ({ ...c, zoning: e.target.value }))
                }
                placeholder={labels.zoningLabel}
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

      {/* Restrictions grid */}
      {result ? (
        <>
          <div className="grid gap-4 md:grid-cols-4">
            <MetricTile
              label={labels.buildingCoverageLabel}
              value={
                result.building_coverage_ratio
                  ? `${result.building_coverage_ratio.max}${result.building_coverage_ratio.unit}`
                  : "-"
              }
            />
            <MetricTile
              label={labels.floorAreaRatioLabel}
              value={
                result.floor_area_ratio
                  ? `${result.floor_area_ratio.max}${result.floor_area_ratio.unit}`
                  : "-"
              }
            />
            <MetricTile
              label={labels.heightLimitLabel}
              value={
                result.height_limit
                  ? `${result.height_limit.value}${result.height_limit.unit}`
                  : "-"
              }
            />
            <MetricTile
              label={labels.parkingStandardLabel}
              value={result.parking_standard?.description ?? "-"}
            />
          </div>

          {/* Applicable laws */}
          {result.applicable_laws && result.applicable_laws.length > 0 && (
            <Card>
              <CardContent className="p-6">
                <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                  {labels.lawsTitle}
                </p>
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)]">
                        <th className="pb-3 pr-4">법률</th>
                        <th className="pb-3 pr-4">조항</th>
                        <th className="pb-3 pr-4">영향</th>
                        <th className="pb-3">영향도</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.applicable_laws.map((law, idx) => (
                        <tr
                          key={`${law.law}-${idx}`}
                          className="border-t border-[var(--line)]"
                        >
                          <td className="py-3 pr-4 font-semibold text-[var(--text-primary)]">
                            {law.law}
                          </td>
                          <td className="py-3 pr-4 text-[var(--text-secondary)]">
                            {law.article}
                          </td>
                          <td className="py-3 pr-4 text-[var(--text-secondary)]">
                            {law.impact}
                          </td>
                          <td className="py-3">
                            <span
                              className={`rounded-full px-2 py-1 text-[10px] font-bold ${levelBadge(law.level)}`}
                            >
                              {law.level.toUpperCase()}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Special zones */}
          {result.special_zones && result.special_zones.length > 0 && (
            <Card>
              <CardContent className="p-6">
                <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                  {labels.specialZonesTitle}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {result.special_zones.map((zone, idx) => (
                    <span
                      key={idx}
                      className="rounded-full border border-amber-500/20 bg-amber-500/10 px-3 py-1.5 text-xs font-bold text-amber-500"
                    >
                      {zone}
                    </span>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Recommendations */}
          {result.recommendations && result.recommendations.length > 0 && (
            <Card>
              <CardContent className="p-6">
                <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                  {labels.recommendationsTitle}
                </p>
                <ul className="mt-3 space-y-2 text-sm leading-7 text-[var(--text-secondary)]">
                  {result.recommendations.map((r, idx) => (
                    <li key={idx} className="flex items-start gap-2">
                      <span className="mt-1 text-emerald-500">-</span>
                      {r}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          {/* AI summary */}
          {result.summary && (
            <Card className="border-[var(--accent-strong)]/20 bg-[var(--accent-strong)]/5">
              <CardContent className="p-6">
                <p className="text-xs uppercase tracking-[0.24em] text-[var(--accent-strong)]">
                  {labels.summaryTitle}
                </p>
                <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                  {result.summary}
                </p>
              </CardContent>
            </Card>
          )}
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
