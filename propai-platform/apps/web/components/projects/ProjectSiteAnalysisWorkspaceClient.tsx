"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, CardTitle, Input } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { ApiClientError, apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { AutoZoningBadge } from "@/components/projects/AutoZoningBadge";
import type { Locale } from "@/i18n/config";

/* ── Response types ── */

type ProjectResponse = {
  id: string;
  name: string;
  status: string;
  address: string | null;
  total_area_sqm: number | null;
  created_at: string;
  updated_at: string;
};

type AVMEstimateResponse = {
  id: string;
  project_id: string;
  estimated_price: number;
  price_per_sqm: number;
  confidence_score: number;
  comparable_count: number;
  model_version: string;
  comparables: Array<{
    address: string;
    price: number;
    area_sqm: number;
    transaction_date: string;
  }>;
  created_at: string;
};

type ParcelInfoResponse = {
  pnu: string;
  address: string;
  land_category: string;
  zoning: string;
  area_sqm: number;
  land_use_situation: string;
  official_price_per_sqm: number;
  road_side: string;
  terrain: string;
  restrictions: string[];
};

/* ── Labels (Korean primary) ── */

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
  submitAction: string;
  missingAddressError: string;
  missingAreaError: string;
  missingPnuError: string;
  avmTitle: string;
  avmEstimateLabel: string;
  avmUnitPriceLabel: string;
  avmConfidenceLabel: string;
  avmComparablesLabel: string;
  avmModelLabel: string;
  parcelTitle: string;
  parcelCategoryLabel: string;
  parcelZoningLabel: string;
  parcelAreaLabel: string;
  parcelUseSituationLabel: string;
  parcelOfficialPriceLabel: string;
  parcelRoadLabel: string;
  parcelTerrainLabel: string;
  parcelRestrictionsLabel: string;
  comparablesTitle: string;
  comparableAddressLabel: string;
  comparablePriceLabel: string;
  comparableAreaLabel: string;
  comparableDateLabel: string;
  placeholder: string;
  projectFallback: string;
  projectLoadErrorTitle: string;
  projectLoadErrorDetail: string;
  retryAction: string;
};

const KO_LABELS: Labels = {
  heroTitle: "부지 분석",
  heroDescription:
    "주소를 입력하면 시세, 용도지역, 필지 정보를 자동으로 분석합니다.",
  heroHint: "",
  tokenHint: "",
  authError: "분석을 위해 로그인이 필요합니다.",
  contextTitle: "프로젝트 정보",
  contextHint: "주소와 면적을 입력하여 분석을 시작하세요.",
  projectIdLabel: "프로젝트 ID",
  projectNameLabel: "프로젝트명",
  projectStatusLabel: "상태",
  projectUpdatedLabel: "최근 수정일",
  formTitle: "부지 분석 입력",
  addressLabel: "주소",
  areaLabel: "면적 (㎡)",
  buildingAgeLabel: "건물 연식 (년)",
  floorLabel: "층",
  totalFloorsLabel: "총 층수",
  lawdCodeLabel: "법정동 코드",
  pnuLabel: "PNU (필지 고유번호)",
  submitAction: "부지 분석 실행",
  missingAddressError: "주소는 필수 입력 항목입니다.",
  missingAreaError: "양수의 면적 값이 필요합니다.",
  missingPnuError: "PNU는 필지 정보 조회에 필수입니다.",
  avmTitle: "AVM 시세 추정",
  avmEstimateLabel: "추정 시세",
  avmUnitPriceLabel: "㎡당 단가",
  avmConfidenceLabel: "신뢰도",
  avmComparablesLabel: "비교사례 건수",
  avmModelLabel: "모델 버전",
  parcelTitle: "필지 정보",
  parcelCategoryLabel: "지목",
  parcelZoningLabel: "용도지역",
  parcelAreaLabel: "면적",
  parcelUseSituationLabel: "이용 상황",
  parcelOfficialPriceLabel: "공시지가 (㎡당)",
  parcelRoadLabel: "도로 접면",
  parcelTerrainLabel: "지형",
  parcelRestrictionsLabel: "규제사항",
  comparablesTitle: "비교 거래 사례",
  comparableAddressLabel: "주소",
  comparablePriceLabel: "거래가격",
  comparableAreaLabel: "면적",
  comparableDateLabel: "거래일",
  placeholder:
    "입력 양식을 제출하면 AVM 시세 추정 및 필지 정보가 표시됩니다.",
  projectFallback: "라이브 API에서 프로젝트 메타데이터를 로드하지 못했습니다.",
  projectLoadErrorTitle: "프로젝트 메타데이터 불가",
  projectLoadErrorDetail:
    "라이브 API에서 라우트 프로젝트 컨텍스트를 로드하지 못했습니다. 재시도하여 자동 입력과 메타데이터를 복원하세요.",
  retryAction: "재시도",
};

const EN_LABELS: Labels = {
  heroTitle: "Site analysis live workspace",
  heroDescription:
    "Run AVM valuation and parcel info queries for real-time site value analysis.",
  heroHint:
    "",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "API authentication is required for live workspace calls.",
  contextTitle: "Project context",
  contextHint:
    "The project id comes from the current route. Address and area can be adjusted before submission.",
  projectIdLabel: "Project ID",
  projectNameLabel: "Project name",
  projectStatusLabel: "Status",
  projectUpdatedLabel: "Updated",
  formTitle: "Site analysis input",
  addressLabel: "Address",
  areaLabel: "Area (sqm)",
  buildingAgeLabel: "Building age (years)",
  floorLabel: "Floor",
  totalFloorsLabel: "Total floors",
  lawdCodeLabel: "LAWD code",
  pnuLabel: "PNU (parcel ID)",
  submitAction: "Run site analysis",
  missingAddressError: "Address is required.",
  missingAreaError: "A positive area value is required.",
  missingPnuError: "PNU is required for parcel info lookup.",
  avmTitle: "AVM valuation",
  avmEstimateLabel: "Estimated price",
  avmUnitPriceLabel: "Price per sqm",
  avmConfidenceLabel: "Confidence",
  avmComparablesLabel: "Comparables",
  avmModelLabel: "Model version",
  parcelTitle: "Parcel information",
  parcelCategoryLabel: "Land category",
  parcelZoningLabel: "Zoning",
  parcelAreaLabel: "Area",
  parcelUseSituationLabel: "Land use",
  parcelOfficialPriceLabel: "Official price (per sqm)",
  parcelRoadLabel: "Road access",
  parcelTerrainLabel: "Terrain",
  parcelRestrictionsLabel: "Restrictions",
  comparablesTitle: "Comparable transactions",
  comparableAddressLabel: "Address",
  comparablePriceLabel: "Price",
  comparableAreaLabel: "Area",
  comparableDateLabel: "Date",
  placeholder:
    "Submit the form to view AVM estimates and parcel information.",
  projectFallback: "Project metadata could not be loaded from the live API.",
  projectLoadErrorTitle: "Project metadata unavailable",
  projectLoadErrorDetail:
    "The routed project context failed to load from the live API. Retry to restore autofill and project metadata.",
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
    return `API 요청 실패: 상태 ${error.status}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "요청 실패.";
}

/* ── Component ── */

export function ProjectSiteAnalysisWorkspaceClient({
  locale,
  projectId,
}: {
  locale: Locale;
  projectId: string;
}) {
  const labels = LABELS[locale] || LABELS["ko"];
  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  const updateSiteAnalysis = useProjectContextStore((s) => s.updateSiteAnalysis);
  const markStageComplete = useProjectContextStore((s) => s.markStageComplete);
  const addAnalysisResult = useProjectContextStore((s) => s.addAnalysisResult);

  const [workspaceError, setWorkspaceError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [avmResult, setAvmResult] = useState<AVMEstimateResponse | null>(null);
  const [parcelResult, setParcelResult] = useState<ParcelInfoResponse | null>(
    null,
  );
  const [form, setForm] = useState({
    address: "",
    areaSqm: "",
    buildingAgeYears: "5",
    floor: "1",
    totalFloors: "5",
    lawdCd: "",
    pnu: "",
  });

  const projectQuery = useQuery({
    queryKey: ["projects", "detail", projectId, "site-analysis-live"],
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
    const pnu = form.pnu.trim();

    if (!address) {
      setWorkspaceError(labels.missingAddressError);
      return;
    }
    if (!Number.isFinite(areaSqm) || areaSqm <= 0) {
      setWorkspaceError(labels.missingAreaError);
      return;
    }

    setIsSubmitting(true);

    try {
      const avm = await apiClient.post<AVMEstimateResponse>("/avm/estimate", {
        useMock: false,
        body: {
          address,
          area_sqm: areaSqm,
          building_age_years: Number(form.buildingAgeYears) || undefined,
          floor: Number(form.floor) || undefined,
          total_floors: Number(form.totalFloors) || undefined,
          lawd_cd: form.lawdCd.trim() || undefined,
          pnu: pnu || undefined,
        },
      });
      setAvmResult(avm);

      let parcelZoning: string | null = null;
      if (pnu) {
        const parcel = await apiClient.post<ParcelInfoResponse>(
          "/external/parcel/info",
          {
            useMock: false,
            body: { pnu },
          },
        );
        setParcelResult(parcel);
        parcelZoning = parcel.zoning || null;
      }

      // Update project context store (capillary network)
      updateSiteAnalysis({
        estimatedValue: avm.estimated_price,
        landAreaSqm: areaSqm,
        zoneCode: parcelZoning,
        address,
        pnu: pnu || null,
      });
      markStageComplete("site-analysis");
      addAnalysisResult({
        module: "site-analysis",
        completedAt: new Date().toISOString(),
        summary: {
          estimatedPrice: avm.estimated_price,
          confidence: avm.confidence_score,
          address,
        },
      });
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

      {/* Context + Form */}
      <Card>
        <CardContent className="grid gap-5 p-6 lg:grid-cols-[0.95fr_1.05fr]">
          <div className="grid gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.contextTitle}
              </p>
              <CardTitle className="mt-2 text-xl">
                {labels.contextHint}
              </CardTitle>
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

      {/* Auto-Zoning Badge */}
      {form.address.trim().length >= 3 && (
        <Card>
          <CardContent className="p-6">
            <p className="mb-3 text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {locale === "en" ? "Auto-detected zoning" : "자동 용도지역 감지"}
            </p>
            <AutoZoningBadge address={form.address} />
          </CardContent>
        </Card>
      )}

      {/* Results */}
      <div className="grid gap-6 xl:grid-cols-2">
        {/* AVM Valuation */}
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
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
                  label={labels.projectUpdatedLabel}
                  value={formatDate(locale, avmResult.created_at)}
                />
              </div>
            ) : (
              <div className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
                {labels.placeholder}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Parcel Info */}
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.parcelTitle}
            </p>
            {parcelResult ? (
              <div className="mt-4 space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <MetricTile
                    label={labels.parcelCategoryLabel}
                    value={parcelResult.land_category}
                  />
                  <MetricTile
                    label={labels.parcelZoningLabel}
                    value={parcelResult.zoning}
                  />
                  <MetricTile
                    label={labels.parcelAreaLabel}
                    value={`${parcelResult.area_sqm.toLocaleString()} m2`}
                  />
                  <MetricTile
                    label={labels.parcelUseSituationLabel}
                    value={parcelResult.land_use_situation}
                  />
                  <MetricTile
                    label={labels.parcelOfficialPriceLabel}
                    value={formatCurrency(
                      locale,
                      parcelResult.official_price_per_sqm,
                    )}
                  />
                  <MetricTile
                    label={labels.parcelRoadLabel}
                    value={parcelResult.road_side}
                  />
                  <MetricTile
                    label={labels.parcelTerrainLabel}
                    value={parcelResult.terrain}
                  />
                </div>
                {parcelResult.restrictions.length > 0 && (
                  <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                    <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                      {labels.parcelRestrictionsLabel}
                    </p>
                    <ul className="mt-3 space-y-2 text-sm leading-7 text-[var(--text-secondary)]">
                      {parcelResult.restrictions.map((r, i) => (
                        <li key={`restriction-${i}`}>{r}</li>
                      ))}
                    </ul>
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
      </div>

      {/* Comparable Transactions */}
      {avmResult && avmResult.comparables && avmResult.comparables.length > 0 && (
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.comparablesTitle}
            </p>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--line)]">
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
                      {labels.comparableAddressLabel}
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
                      {labels.comparablePriceLabel}
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
                      {labels.comparableAreaLabel}
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
                      {labels.comparableDateLabel}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {avmResult.comparables.map((comp, i) => (
                    <tr
                      key={`comp-${i}`}
                      className="border-b border-[var(--line)] last:border-0"
                    >
                      <td className="px-4 py-3 text-[var(--text-primary)]">
                        {comp.address}
                      </td>
                      <td className="px-4 py-3 text-right font-semibold text-[var(--text-primary)]">
                        {formatCurrency(locale, comp.price)}
                      </td>
                      <td className="px-4 py-3 text-right text-[var(--text-secondary)]">
                        {comp.area_sqm.toLocaleString()} m2
                      </td>
                      <td className="px-4 py-3 text-right text-[var(--text-secondary)]">
                        {comp.transaction_date}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
