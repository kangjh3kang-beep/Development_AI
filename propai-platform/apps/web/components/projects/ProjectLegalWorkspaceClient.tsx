"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, CardTitle, Input } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import type { Locale } from "@/i18n/config";

/* ── Response Types ── */

type ProjectResponse = {
  id: string;
  name: string;
  status: string;
  address: string | null;
  total_area_sqm: number | null;
  created_at: string;
  updated_at: string;
};

type ComplianceCheckResponse = {
  address: string;
  zone_code: string;
  zone_name?: string;
  bcr_limit: number;
  bcr_planned: number;
  bcr_pass: boolean;
  far_limit: number;
  far_planned: number;
  far_pass: boolean;
  height_limit_m: number;
  height_planned_m: number;
  height_pass: boolean;
  overall_pass: boolean;
  remarks?: string;
  ai_analysis?: string;
};

/* ── Labels ── */

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
  zoneCodeLabel: string;
  plannedBcrLabel: string;
  plannedFarLabel: string;
  plannedHeightLabel: string;
  plannedFloorsLabel: string;
  submitAction: string;
  missingAddressError: string;
  missingZoneCodeError: string;
  complianceTitle: string;
  bcrLabel: string;
  farLabel: string;
  heightLabel: string;
  limitLabel: string;
  plannedLabel: string;
  passLabel: string;
  failLabel: string;
  overallLabel: string;
  regulationTitle: string;
  placeholder: string;
  projectFallback: string;
  projectLoadErrorTitle: string;
  projectLoadErrorDetail: string;
  retryAction: string;
};

const KO_LABELS: Labels = {
  heroTitle: "법규 검토 라이브 워크스페이스",
  heroDescription:
    "현재 프로젝트의 건축 법규 적합성을 실시간으로 검토합니다.",
  heroHint:
    "주소와 건축 계획을 입력하면 법규 적합 여부를 자동 검토합니다.",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "라이브 워크스페이스 호출을 위해 API 인증이 필요합니다.",
  contextTitle: "프로젝트 컨텍스트",
  contextHint:
    "현재 라우트에서 프로젝트 ID를 가져옵니다. 주소와 용도지역은 제출 전 수정 가능합니다.",
  projectIdLabel: "프로젝트 ID",
  projectNameLabel: "프로젝트명",
  projectStatusLabel: "상태",
  projectUpdatedLabel: "최종 수정",
  formTitle: "법규 검토 입력",
  addressLabel: "주소",
  zoneCodeLabel: "용도지역 코드",
  plannedBcrLabel: "계획 건폐율 (%)",
  plannedFarLabel: "계획 용적률 (%)",
  plannedHeightLabel: "계획 높이 (m)",
  plannedFloorsLabel: "계획 층수",
  submitAction: "법규 검토 실행",
  missingAddressError: "주소를 입력해 주세요.",
  missingZoneCodeError: "용도지역 코드를 입력해 주세요.",
  complianceTitle: "건축 규제 검토 결과",
  bcrLabel: "건폐율 (대지 중 건물 면적 비율)",
  farLabel: "용적률 (대지 대비 건물 총면적 비율)",
  heightLabel: "높이 제한",
  limitLabel: "제한",
  plannedLabel: "계획",
  passLabel: "적합",
  failLabel: "부적합",
  overallLabel: "종합 판정",
  regulationTitle: "규제 체크리스트",
  placeholder:
    "폼을 제출하면 건축 법규 적합성 검토 결과가 표시됩니다.",
  projectFallback: "라이브 API에서 프로젝트 메타데이터를 불러올 수 없습니다.",
  projectLoadErrorTitle: "프로젝트 메타데이터 로드 실패",
  projectLoadErrorDetail:
    "라이브 API에서 프로젝트 컨텍스트를 가져오지 못했습니다. 재시도하여 자동 입력을 복원하세요.",
  retryAction: "재시도",
};

const EN_LABELS: Labels = {
  heroTitle: "Legal compliance live workspace",
  heroDescription:
    "Run a real-time building compliance check for the current project.",
  heroHint:
    "Automatically verifies BCR, FAR, height limits and other building regulations via API.",
  tokenHint:
    "Live API calls require NEXT_PUBLIC_API_ACCESS_TOKEN or localStorage.propai_access_token.",
  authError: "API authentication is required for live workspace calls.",
  contextTitle: "Project context",
  contextHint:
    "The project ID comes from the current route. Address and zone code can be adjusted before submission.",
  projectIdLabel: "Project ID",
  projectNameLabel: "Project name",
  projectStatusLabel: "Status",
  projectUpdatedLabel: "Updated",
  formTitle: "Compliance check input",
  addressLabel: "Address",
  zoneCodeLabel: "Zone code",
  plannedBcrLabel: "Planned BCR (%)",
  plannedFarLabel: "Planned FAR (%)",
  plannedHeightLabel: "Planned height (m)",
  plannedFloorsLabel: "Planned floors",
  submitAction: "Run compliance check",
  missingAddressError: "Address is required.",
  missingZoneCodeError: "Zone code is required.",
  complianceTitle: "Building compliance results",
  bcrLabel: "BCR",
  farLabel: "FAR",
  heightLabel: "Height limit",
  limitLabel: "Limit",
  plannedLabel: "Planned",
  passLabel: "Pass",
  failLabel: "Fail",
  overallLabel: "Overall result",
  regulationTitle: "Regulation checklist",
  placeholder:
    "Submit the form to validate the building compliance check results.",
  projectFallback: "Project metadata could not be loaded from the live API.",
  projectLoadErrorTitle: "Project metadata unavailable",
  projectLoadErrorDetail:
    "The routed project context failed to load from the live API. Retry to restore autofill.",
  retryAction: "Retry",
};

const LABELS: Record<Locale, Labels> = {
  ko: KO_LABELS,
  en: EN_LABELS,
  "zh-CN": KO_LABELS,
};

/* ── Helpers ── */

function formatPercent(value: number) {
  return `${value.toFixed(1)}%`;
}

function formatDate(locale: string, value: string) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function extractErrorMessage(error: unknown, authMessage: string) {

/* ── Fallback Data (from existing legal page) ── */

const FALLBACK_COMPLIANCE = [
  { label: "건폐율", limit: "60%", current: "58.2%", progress: 97 },
  { label: "용적률", limit: "300%", current: "298.5%", progress: 99 },
  { label: "높이제한", limit: "80m", current: "75.2m", progress: 94 },
  { label: "일조권", limit: "적용", current: "충족", progress: 100 },
  { label: "조경면적", limit: "15%", current: "15.4%", progress: 100 },
];

const FALLBACK_REGULATIONS = [
  { label: "용도지역 조례 적합성 검토", checked: true, status: "Verified" },
  { label: "건축법 제 21조 준수 여부", checked: true, status: "Verified" },
  { label: "소방법 화재 안전 등급", checked: false, status: "Pending" },
  { label: "환경영향평가 대상 여부", checked: true, status: "N/A" },
  { label: "지능형 건축물 인증 요건", checked: false, status: "In Progress" },
  { label: "주차장법 시행령 적합", checked: true, status: "Verified" },
  { label: "과밀부담금 산정 완료", checked: false, status: "Pending" },
];

/* ── Component ── */

export function ProjectLegalWorkspaceClient({
  locale,
  projectId,
}: {
  locale: Locale;
  projectId: string;
}) {
  const labels = LABELS[locale] || LABELS["ko"];
  const runtimeConfig = ({ mode: "local" as string, hasAccessToken: false });
  const canUseLiveApi =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const updateComplianceData = useProjectContextStore((s) => s.updateComplianceData);
  const markStageComplete = useProjectContextStore((s) => s.markStageComplete);
  const addAnalysisResult = useProjectContextStore((s) => s.addAnalysisResult);

  const [workspaceError, setWorkspaceError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [complianceResult, setComplianceResult] =
    useState<ComplianceCheckResponse | null>(null);
  const [form, setForm] = useState({
    address: "",
    zoneCode: "",
    plannedBcr: "58.2",
    plannedFar: "298.5",
    plannedHeight: "75.2",
    plannedFloors: "25",
  });

  const projectQuery = useQuery({
    queryKey: ["projects", "detail", projectId, "legal-live"],
    enabled: canUseLiveApi,
    queryFn: () =>
      (async () => ({} as ProjectResponse))(),
  });

  useEffect(() => {
    if (!projectQuery.data) {
      return;
    }
    setForm((current) => ({
      ...current,
      address: current.address || projectQuery.data.address || "",
    }));
  }, [projectQuery.data]);

  // 부지분석에서 설정한 주소를 자동으로 불러옵니다 (모세혈관 네트워크 주소 공유 패턴)
  // siteAnalysis.address가 변경되면 아직 사용자가 입력하지 않은 경우 자동 동기화
  useEffect(() => {
    if (!siteAnalysis) return;
    setForm((current) => ({
      ...current,
      address: current.address || siteAnalysis.address || "",
      zoneCode: current.zoneCode || siteAnalysis.zoneCode || "",
    }));
  }, [siteAnalysis]);

  const projectError = projectQuery.error
    ? extractErrorMessage(projectQuery.error, labels.authError)
    : "";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");

    const address = form.address.trim();
    const zoneCode = form.zoneCode.trim();

    if (!address) {
      setWorkspaceError(labels.missingAddressError);
      return;
    }
    if (!zoneCode) {
      setWorkspaceError(labels.missingZoneCodeError);
      return;
    }

    setIsSubmitting(true);

    try {
      const result = await (async () => ({} as ComplianceCheckResponse))() || 0,
            planned_far: Number(form.plannedFar) || 0,
            planned_height_m: Number(form.plannedHeight) || 0,
            planned_floors: Number(form.plannedFloors) || 0,
          },
        },
      );
      setComplianceResult(result);

      // Update project context store (capillary network)
      const violations: string[] = [];
      if (!result.bcr_pass) violations.push("건폐율 초과");
      if (!result.far_pass) violations.push("용적률 초과");
      if (!result.height_pass) violations.push("높이제한 초과");
      updateComplianceData({
        bcrCompliant: result.bcr_pass,
        farCompliant: result.far_pass,
        heightCompliant: result.height_pass,
        violations,
      });
      markStageComplete("legal");
      addAnalysisResult({
        module: "legal",
        completedAt: new Date().toISOString(),
        summary: {
          overallPass: result.overall_pass,
          bcrPass: result.bcr_pass,
          farPass: result.far_pass,
          heightPass: result.height_pass,
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
                {/* 주소 검색 입력: 부지분석 주소를 공유하며, 이 페이지에서 변경 가능 */}
                <div className="relative">
                  <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-hint)]" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
                  <Input
                    value={form.address}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        address: event.target.value,
                      }))
                    }
                    placeholder="주소를 검색하세요 (예: 서울특별시 강남구 삼성동)"
                    className="pl-10"
                  />
                </div>
                {siteAnalysis?.address && form.address === siteAnalysis.address && (
                  <p className="text-[10px] text-[var(--text-hint)] -mt-2">
                    📍 부지분석에서 설정된 주소입니다
                  </p>
                )}
                <Input
                  value={form.zoneCode}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      zoneCode: event.target.value,
                    }))
                  }
                  placeholder={labels.zoneCodeLabel}
                />
                <div className="grid gap-3 md:grid-cols-2">
                  <Input
                    type="number"
                    value={form.plannedBcr}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        plannedBcr: event.target.value,
                      }))
                    }
                    placeholder={labels.plannedBcrLabel}
                  />
                  <Input
                    type="number"
                    value={form.plannedFar}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        plannedFar: event.target.value,
                      }))
                    }
                    placeholder={labels.plannedFarLabel}
                  />
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <Input
                    type="number"
                    value={form.plannedHeight}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        plannedHeight: event.target.value,
                      }))
                    }
                    placeholder={labels.plannedHeightLabel}
                  />
                  <Input
                    type="number"
                    value={form.plannedFloors}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        plannedFloors: event.target.value,
                      }))
                    }
                    placeholder={labels.plannedFloorsLabel}
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

      {/* Results */}
      <div className="grid gap-6 xl:grid-cols-2">
        {/* Compliance Results */}
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.complianceTitle}
            </p>
            {complianceResult ? (
              <div className="mt-4 space-y-4">
                <div className="grid gap-4 md:grid-cols-3">
                  <ComplianceMetric
                    label={labels.bcrLabel}
                    limit={formatPercent(complianceResult.bcr_limit)}
                    planned={formatPercent(complianceResult.bcr_planned)}
                    pass={complianceResult.bcr_pass}
                    passLabel={labels.passLabel}
                    failLabel={labels.failLabel}
                  />
                  <ComplianceMetric
                    label={labels.farLabel}
                    limit={formatPercent(complianceResult.far_limit)}
                    planned={formatPercent(complianceResult.far_planned)}
                    pass={complianceResult.far_pass}
                    passLabel={labels.passLabel}
                    failLabel={labels.failLabel}
                  />
                  <ComplianceMetric
                    label={labels.heightLabel}
                    limit={`${complianceResult.height_limit_m}m`}
                    planned={`${complianceResult.height_planned_m}m`}
                    pass={complianceResult.height_pass}
                    passLabel={labels.passLabel}
                    failLabel={labels.failLabel}
                  />
                </div>
                <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                  <MetricTile
                    label={labels.overallLabel}
                    value={
                      complianceResult.overall_pass
                        ? labels.passLabel
                        : labels.failLabel
                    }
                  />
                </div>
                {complianceResult.ai_analysis ? (
                  <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                    <p className="text-sm leading-7 text-[var(--text-secondary)]">
                      {complianceResult.ai_analysis}
                    </p>
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="mt-4 space-y-4">
                <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
                  {labels.placeholder}
                </div>
                {/* Fallback: hardcoded compliance data */}
                <div className="grid gap-4">
                  {FALLBACK_COMPLIANCE.map((item) => (
                    <div
                      key={item.label}
                      className="flex items-center justify-between rounded-[var(--radius-xl)] bg-[var(--surface-soft)] px-5 py-4"
                    >
                      <span className="text-xs font-semibold uppercase tracking-widest text-[var(--text-secondary)]">
                        {item.label}
                      </span>
                      <div className="flex gap-4 items-center">
                        <span className="text-xs text-[var(--text-tertiary)]">
                          {labels.limitLabel}: {item.limit}
                        </span>
                        <span className="text-sm font-bold text-[var(--text-primary)]">
                          {item.current}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Regulation Checklist */}
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.regulationTitle}
            </p>
            <div className="mt-4 grid gap-3">
              {FALLBACK_REGULATIONS.map((item) => (
                <div
                  key={item.label}
                  className="flex items-center justify-between gap-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] px-5 py-4"
                >
                  <div className="flex items-center gap-4">
                    <div
                      className={`flex h-6 w-6 items-center justify-center rounded-md border-2 ${
                        item.checked
                          ? "border-[var(--accent-strong)] bg-[var(--accent-strong)] text-white"
                          : "border-[var(--line)] text-transparent"
                      }`}
                    >
                      {item.checked && (
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          width="14"
                          height="14"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="4"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        >
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      )}
                    </div>
                    <span
                      className={`text-sm font-medium ${
                        item.checked
                          ? "text-[var(--text-primary)]"
                          : "text-[var(--text-tertiary)] italic"
                      }`}
                    >
                      {item.label}
                    </span>
                  </div>
                  <span
                    className={`text-[10px] font-bold uppercase tracking-widest px-3 py-1 rounded-lg ${
                      item.status === "Verified"
                        ? "bg-[rgba(14,116,144,0.1)] text-[var(--accent-strong)]"
                        : item.status === "Pending"
                          ? "bg-[rgba(239,68,68,0.1)] text-[var(--error)]"
                          : "bg-[var(--surface)] text-[var(--text-tertiary)]"
                    }`}
                  >
                    {item.status}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}

/* ── Sub-components ── */

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

function ComplianceMetric({
  label,
  limit,
  planned,
  pass,
  passLabel,
  failLabel,
}: {
  label: string;
  limit: string;
  planned: string;
  pass: boolean;
  passLabel: string;
  failLabel: string;
}) {
  return (
    <div className="rounded-[var(--radius-xl)] bg-[var(--surface)] p-4 space-y-2">
      <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="text-sm text-[var(--text-secondary)]">
        {limit} / {planned}
      </p>
      <span
        className={`inline-block rounded-lg px-3 py-1 text-[10px] font-bold uppercase tracking-widest ${
          pass
            ? "bg-[rgba(14,116,144,0.1)] text-[var(--accent-strong)]"
            : "bg-[rgba(239,68,68,0.1)] text-[var(--error)]"
        }`}
      >
        {pass ? passLabel : failLabel}
      </span>
    </div>
  );
}
