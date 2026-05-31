"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, CardTitle, Input } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { ApiClientError, apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
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
  valuation_narrative?: string | null;
  comparable_explanation?: string | null;
  market_position?: string | null;
  appreciation_outlook?: string | null;
  investment_recommendation?: string | null;
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

const EN_LABELS: Labels = {
  heroTitle: "Project finance live workspace",
  heroDescription:
    "Run a persisted AVM valuation and a jeonse risk analysis for the current project path.",
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

const KO_LABELS: Labels = {
  heroTitle: "프로젝트 금융분석 라이브 워크스페이스",
  heroDescription:
    "AVM 시세 추정과 전세 위험도 분석을 실행합니다.",
  heroHint:
    "현재 프로젝트 ID를 기반으로 AVM 시세 추정 및 전세 위험도 분석을 연쇄 실행합니다.",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "라이브 워크스페이스 호출에 API 인증이 필요합니다.",
  contextTitle: "프로젝트 컨텍스트",
  contextHint:
    "프로젝트 ID는 현재 경로에서 가져옵니다. 주소와 면적은 제출 전 수정할 수 있습니다.",
  projectIdLabel: "프로젝트 ID",
  projectNameLabel: "프로젝트명",
  projectStatusLabel: "상태",
  projectUpdatedLabel: "수정일",
  formTitle: "금융분석 입력",
  addressLabel: "주소",
  areaLabel: "면적 (㎡)",
  buildingAgeLabel: "건물 연식 (년)",
  floorLabel: "층",
  totalFloorsLabel: "총층수",
  lawdCodeLabel: "법정동 코드",
  pnuLabel: "PNU",
  jeonsePriceLabel: "전세금 (원)",
  submitAction: "AVM + 위험분석 실행",
  missingAddressError: "주소를 입력해 주세요.",
  missingAreaError: "양수의 면적 값이 필요합니다.",
  missingJeonsePriceError: "양수의 전세금 값이 필요합니다.",
  avmTitle: "AVM 시세 추정",
  avmEstimateLabel: "추정 시세",
  avmUnitPriceLabel: "㎡당 가격",
  avmConfidenceLabel: "신뢰도",
  avmComparablesLabel: "비교사례 수",
  avmModelLabel: "모델 버전",
  jeonseTitle: "전세 위험도",
  jeonseRatioLabel: "전세 비율",
  jeonseRiskLabel: "위험 등급",
  jeonseScoreLabel: "위험 점수",
  jeonseFactorsLabel: "위험 요인",
  placeholder:
    "양식을 제출하여 AVM 시세 추정 및 전세 위험도 응답 체인을 검증하세요.",
  projectFallback: "라이브 API에서 프로젝트 메타데이터를 불러올 수 없습니다.",
  projectLoadErrorTitle: "프로젝트 메타데이터 조회 불가",
  projectLoadErrorDetail:
    "프로젝트 정보를 불러오지 못했습니다. 재시도하여 자동 입력 및 프로젝트 메타데이터를 복원하세요.",
  retryAction: "재시도",
};

const LABELS: Record<Locale, Labels> = {
  ko: KO_LABELS,
  en: EN_LABELS,
  "zh-CN": KO_LABELS,
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
  const labels = LABELS[locale] || LABELS["ko"];
  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const markStageComplete = useProjectContextStore((s) => s.markStageComplete);
  const addAnalysisResult = useProjectContextStore((s) => s.addAnalysisResult);

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

  // Pre-fill from site analysis context (capillary network)
  useEffect(() => {
    if (!siteAnalysis) return;
    setForm((current) => ({
      ...current,
      address: current.address || siteAnalysis.address || "",
      areaSqm:
        current.areaSqm ||
        (siteAnalysis.landAreaSqm != null
          ? String(siteAnalysis.landAreaSqm)
          : ""),
      pnu: current.pnu || siteAnalysis.pnu || "",
    }));
  }, [siteAnalysis]);

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

      // 프로젝트 컨텍스트에 결과 저장
      markStageComplete("finance");
      addAnalysisResult({
        module: "finance",
        completedAt: new Date().toISOString(),
        summary: {
          estimatedPrice: avm.estimated_price,
          riskLevel: risk.risk_level,
          jeonseRatio: risk.jeonse_ratio,
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
      <Card className="rounded-[var(--radius-2xl)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
        <CardContent className="p-4 sm:p-6 lg:p-8">
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-[rgba(14,116,144,0.1)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--accent-strong)]">
              {labels.heroTitle}
            </span>
            <span className="rounded-full border border-[var(--line)] px-4 py-2 text-xs font-medium text-[var(--text-secondary)]">
              {runtimeConfig.mode === "live" ? "LIVE" : "HYBRID"}
            </span>
          </div>
          <h3 className="mt-5 text-xl sm:text-2xl lg:text-3xl font-bold text-[var(--text-primary)]">
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
        <CardContent className="grid gap-5 p-6 lg:grid-cols-[0.95fr_1.05fr]">
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
                  label="Created"
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

        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
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
                <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                  <p className="text-sm leading-7 text-[var(--text-secondary)]">
                    {riskResult.analysis}
                  </p>
                </div>
                <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                  <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                    {labels.jeonseFactorsLabel}
                  </p>
                  {riskResult.factors.length ? (
                    <ul className="mt-3 space-y-2 text-sm leading-7 text-[var(--text-secondary)]">
                      {riskResult.factors.map((factor, index) => (
                        <li key={`${factor.factor ?? "factor"}-${index}`}>
                          {factor.factor ?? "factor"}:{" "}
                          {factor.detail ?? JSON.stringify(factor)}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-3 text-sm leading-7 text-[var(--text-tertiary)]">
                      -
                    </p>
                  )}
                </div>
                {/* 7 Jeonse Risk Patterns */}
                <JeonseRiskPatterns riskScore={riskResult.risk_score} factors={riskResult.factors} />
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

type JeonseRiskPattern = {
  name: string;
  description: string;
};

const JEONSE_RISK_PATTERNS: JeonseRiskPattern[] = [
  { name: "적금 미보유", description: "임대인의 전세보증금 반환 능력이 불확실한 경우" },
  { name: "건물 소유권 분쟁", description: "소유권에 대한 법적 분쟁이 존재하는 경우" },
  { name: "명의 도용", description: "임대인의 실제 소유자 확인이 불가하거나 위조된 경우" },
  { name: "과다 전세금", description: "시세 대비 전세금이 비정상적으로 높은 경우" },
  { name: "다중 전세 설정", description: "동일 물건에 복수의 전세권이 설정된 경우" },
  { name: "대출 담보 설정", description: "근저당 등 담보 설정 금액이 과다한 경우" },
  { name: "미등기 채권", description: "등기부에 반영되지 않은 채권이 존재하는 경우" },
];

function derivePatternRiskLevel(
  patternIndex: number,
  riskScore: number,
  factors: JeonseRiskFactor[],
): "높음" | "중간" | "낮음" {
  // Check if any returned factor matches this pattern
  const patternName = JEONSE_RISK_PATTERNS[patternIndex].name;
  const matchedFactor = factors.find(
    (f) =>
      f.factor?.includes(patternName) ||
      f.detail?.includes(patternName),
  );

  if (matchedFactor && matchedFactor.score != null) {
    if (matchedFactor.score >= 0.7) return "높음";
    if (matchedFactor.score >= 0.4) return "중간";
    return "낮음";
  }

  // Heuristic: derive from overall risk score with pattern-specific weighting
  const highThreshold = 0.6;
  const medThreshold = 0.35;
  // Some patterns are inherently higher risk
  const highRiskPatterns = [3, 4, 5]; // 과다 전세금, 다중 전세, 대출 담보
  const adjustedScore = highRiskPatterns.includes(patternIndex)
    ? riskScore * 1.15
    : riskScore;

  if (adjustedScore >= highThreshold) return "높음";
  if (adjustedScore >= medThreshold) return "중간";
  return "낮음";
}

function JeonseRiskPatterns({
  riskScore,
  factors,
}: {
  riskScore: number;
  factors: JeonseRiskFactor[];
}) {
  const LEVEL_STYLES: Record<string, { bg: string; text: string; border: string }> = {
    "높음": { bg: "bg-red-500/10", text: "text-red-500", border: "border-red-500/20" },
    "중간": { bg: "bg-amber-500/10", text: "text-amber-500", border: "border-amber-500/20" },
    "낮음": { bg: "bg-emerald-500/10", text: "text-emerald-500", border: "border-emerald-500/20" },
  };

  return (
    <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
      <p className="text-xs font-bold uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
        전세 사기 7대 위험 패턴 분석
      </p>
      <div className="mt-4 grid gap-2">
        {JEONSE_RISK_PATTERNS.map((pattern, index) => {
          const level = derivePatternRiskLevel(index, riskScore, factors);
          const style = LEVEL_STYLES[level];
          return (
            <div
              key={pattern.name}
              className={`flex items-center justify-between rounded-xl border p-3 ${style.border} ${style.bg}`}
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-[var(--text-primary)]">
                  <span className="text-[var(--text-hint)] mr-2">
                    {index + 1}.
                  </span>
                  {pattern.name}
                </p>
                <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                  {pattern.description}
                </p>
              </div>
              <span
                className={`shrink-0 rounded-lg px-3 py-1 text-xs font-bold ${style.text} ${style.bg}`}
              >
                {level}
              </span>
            </div>
          );
        })}
      </div>
    </div>
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
