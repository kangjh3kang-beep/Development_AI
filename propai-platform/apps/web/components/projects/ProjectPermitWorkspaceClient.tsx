"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, CardTitle, Input } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { LegalRefChip } from "@/components/common/LegalRefChip";
import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { NumberInput } from "@/components/common/NumberInput";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { ApiClientError, apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import type { Locale } from "@/i18n/config";

/* ── Response types ── */

type ProjectResponse = {
  id: string;
  name: string;
  status: string;
  address: string | null;
  total_area_sqm: number | null;
  building_type: string | null;
  created_at: string;
  updated_at: string;
};

/** 백엔드 legal_reference_registry 직렬화 레코드(WP-P additive — 구버전 응답엔 없음). */
type LegalRef = {
  key?: string;
  law_name: string;
  article?: string | null;
  title?: string | null;
  url?: string | null;
  url_status?: string;
};

type ComplianceCheckResponse = {
  overall_status: "pass" | "fail" | "warning";
  checks: Array<{
    rule_code: string;
    rule_name: string;
    status: "pass" | "fail" | "warning";
    detail: string;
    regulation_ref: string;
    /** WP-P: 항목별 법령 근거 칩(옵셔널 가드 — 구버전 응답 무손상). */
    legal_refs?: LegalRef[];
  }>;
  summary: string;
  /** WP-P: 응답 레벨 법령 근거(공통 인허가 + 위반항목 합산). */
  legal_refs?: LegalRef[];
};

type ChecklistItem = {
  id: string;
  stage: string;
  document_name: string;
  required: boolean;
  submitted: boolean;
  deadline: string | null;
  note: string | null;
};

type LifecycleChecklistResponse = {
  project_id: string;
  phase: string;
  items: ChecklistItem[];
};

/* ── Permit stage model ── */

type PermitStage = {
  key: string;
  label: string;
  status: "completed" | "current" | "pending";
};

const DEFAULT_STAGES: PermitStage[] = [
  { key: "pre-review", label: "사전검토", status: "pending" },
  { key: "building-permit", label: "건축허가", status: "pending" },
  { key: "construction-start", label: "착공신고", status: "pending" },
  { key: "use-approval", label: "사용승인", status: "pending" },
];

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
  buildingTypeLabel: string;
  addressLabel: string;
  areaLabel: string;
  floorsLabel: string;
  submitAction: string;
  missingAddressError: string;
  missingAreaError: string;
  stagesTitle: string;
  complianceTitle: string;
  complianceOverallLabel: string;
  complianceRuleLabel: string;
  complianceStatusLabel: string;
  complianceDetailLabel: string;
  complianceRefLabel: string;
  complianceSummaryLabel: string;
  checklistTitle: string;
  checklistDocLabel: string;
  checklistStageLabel: string;
  checklistRequiredLabel: string;
  checklistSubmittedLabel: string;
  checklistDeadlineLabel: string;
  checklistNoteLabel: string;
  submittedText: string;
  notSubmittedText: string;
  requiredText: string;
  optionalText: string;
  passText: string;
  failText: string;
  warningText: string;
  infoText: string;
  placeholder: string;
  projectFallback: string;
  projectLoadErrorTitle: string;
  projectLoadErrorDetail: string;
  retryAction: string;
};

const KO_LABELS: Labels = {
  heroTitle: "인허가 관리 라이브 작업 공간",
  heroDescription:
    "건축 인허가 진행 현황, 법규 적합성 검사 및 제출 서류 체크리스트를 실시간으로 관리합니다.",
  heroHint:
    "",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "라이브 작업 공간 호출에 API 인증이 필요합니다.",
  contextTitle: "프로젝트 컨텍스트",
  contextHint:
    "프로젝트 ID는 현재 라우트에서 가져옵니다. 건물 유형과 면적은 제출 전 수정할 수 있습니다.",
  projectIdLabel: "프로젝트 ID",
  projectNameLabel: "프로젝트명",
  projectStatusLabel: "상태",
  projectUpdatedLabel: "최근 수정일",
  formTitle: "인허가 검토 입력",
  buildingTypeLabel: "건물 유형",
  addressLabel: "주소",
  areaLabel: "면적 (㎡)",
  floorsLabel: "층수",
  submitAction: "인허가 검토 실행",
  missingAddressError: "주소는 필수 입력 항목입니다.",
  missingAreaError: "양수의 면적 값이 필요합니다.",
  stagesTitle: "인허가 진행 프로세스",
  complianceTitle: "법규 적합성 검사",
  complianceOverallLabel: "종합 판정",
  complianceRuleLabel: "규정 항목",
  complianceStatusLabel: "판정",
  complianceDetailLabel: "상세 내용",
  complianceRefLabel: "근거 법령",
  complianceSummaryLabel: "검토 요약",
  checklistTitle: "필수 서류 체크리스트",
  checklistDocLabel: "서류명",
  checklistStageLabel: "단계",
  checklistRequiredLabel: "필수 여부",
  checklistSubmittedLabel: "제출 여부",
  checklistDeadlineLabel: "마감일",
  checklistNoteLabel: "비고",
  submittedText: "제출 완료",
  notSubmittedText: "미제출",
  requiredText: "필수",
  optionalText: "선택",
  passText: "적합",
  failText: "부적합",
  warningText: "주의",
  infoText: "참고",
  placeholder:
    "입력 양식을 제출하면 법규 적합성 검사 및 서류 체크리스트가 표시됩니다.",
  projectFallback: "라이브 API에서 프로젝트 메타데이터를 로드하지 못했습니다.",
  projectLoadErrorTitle: "프로젝트 메타데이터 불가",
  projectLoadErrorDetail:
    "라이브 API에서 라우트 프로젝트 컨텍스트를 로드하지 못했습니다. 재시도하여 자동 입력과 메타데이터를 복원하세요.",
  retryAction: "재시도",
};

const EN_LABELS: Labels = {
  heroTitle: "Permit management live workspace",
  heroDescription:
    "Track permit progress, run compliance checks, and manage required document checklists in real-time.",
  heroHint:
    "Chains GET /projects, POST /building-compliance/check, and POST /lifecycle/construction/checklist.",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "API authentication is required for live workspace calls.",
  contextTitle: "Project context",
  contextHint:
    "The project id comes from the current route. Building type and area can be adjusted before submission.",
  projectIdLabel: "Project ID",
  projectNameLabel: "Project name",
  projectStatusLabel: "Status",
  projectUpdatedLabel: "Updated",
  formTitle: "Permit review input",
  buildingTypeLabel: "Building type",
  addressLabel: "Address",
  areaLabel: "Area (sqm)",
  floorsLabel: "Floors",
  submitAction: "Run permit review",
  missingAddressError: "Address is required.",
  missingAreaError: "A positive area value is required.",
  stagesTitle: "Permit progress tracker",
  complianceTitle: "Compliance check",
  complianceOverallLabel: "Overall",
  complianceRuleLabel: "Rule",
  complianceStatusLabel: "Status",
  complianceDetailLabel: "Detail",
  complianceRefLabel: "Regulation",
  complianceSummaryLabel: "Summary",
  checklistTitle: "Required documents checklist",
  checklistDocLabel: "Document",
  checklistStageLabel: "Stage",
  checklistRequiredLabel: "Required",
  checklistSubmittedLabel: "Submitted",
  checklistDeadlineLabel: "Deadline",
  checklistNoteLabel: "Note",
  submittedText: "Submitted",
  notSubmittedText: "Not submitted",
  requiredText: "Required",
  optionalText: "Optional",
  passText: "Pass",
  failText: "Fail",
  warningText: "Warning",
  infoText: "Info",
  placeholder:
    "Submit the form to view compliance results and the document checklist.",
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

function statusBadgeClass(
  status: "pass" | "fail" | "warning" | string,
): string {
  switch (status) {
    case "pass":
    case "completed":
      return "bg-emerald-100 text-emerald-700 border-emerald-200";
    case "fail":
      return "bg-red-100 text-red-700 border-red-200";
    case "warning":
    case "current":
      return "bg-amber-100 text-amber-700 border-amber-200";
    default:
      return "bg-gray-100 text-gray-500 border-gray-200";
  }
}

/* ── Component ── */

export function ProjectPermitWorkspaceClient({
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

  const [workspaceError, setWorkspaceError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [stages, setStages] = useState<PermitStage[]>(DEFAULT_STAGES);
  const [complianceResult, setComplianceResult] =
    useState<ComplianceCheckResponse | null>(null);
  const [checklistResult, setChecklistResult] =
    useState<LifecycleChecklistResponse | null>(null);
  const [form, setForm] = useState({
    buildingType: "공동주택",
    address: "",
    areaSqm: "",
    floors: "15",
  });

  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const designData = useProjectContextStore((s) => s.designData);

  const projectQuery = useQuery({
    queryKey: ["projects", "detail", projectId, "permit-live"],
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
      buildingType:
        current.buildingType || projectQuery.data.building_type || "공동주택",
    }));
  }, [projectQuery.data]);

  // ★다필지 통합면적 우선: 프로젝트 레코드 total_area_sqm은 대표(단일) 면적일 수 있어
  //   다필지 부지에서 인허가 가능규모(건축면적·연면적) 산정이 1필지 기준으로 축소된다.
  //   부지분석 SSOT의 통합면적(effectiveLandAreaSqm)으로 폼 대지면적을 보정해
  //   /building-compliance/check가 전체 필지 통합 기준으로 가능규모를 산정하게 한다.
  //   단일필지면 effectiveLandAreaSqm=landAreaSqm이라 무회귀.
  // ★LOW fix(수동편집 클로버 방지): 같은 통합면적은 1회만 보정한다. 보정 후 사용자가 폼 면적을
  //   수동조정했는데 siteAnalysis가 무관한 이유로 다시 바뀌어도 같은 eff면 재보정하지 않는다.
  //   통합면적 자체가 변하면(필지 추가 등) 새 eff로 1회 보정(그 변화는 반영이 타당).
  const lastAppliedAreaRef = useRef<number | null>(null);
  useEffect(() => {
    const isMulti = (siteAnalysis?.parcelCount ?? 1) > 1;
    if (!isMulti) return;
    const eff = effectiveLandAreaSqm(siteAnalysis);
    if (eff == null || eff <= 0) return;
    if (lastAppliedAreaRef.current === eff) return;
    lastAppliedAreaRef.current = eff;
    setForm((current) =>
      current.areaSqm === String(eff)
        ? current
        : { ...current, areaSqm: String(eff) },
    );
  }, [siteAnalysis]);

  const projectError = projectQuery.error
    ? extractErrorMessage(projectQuery.error, labels.authError)
    : "";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");

    const address = form.address.trim();
    const areaSqm = Number(form.areaSqm);

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
      const [compliance, checklist] = await Promise.all([
        apiClient.post<ComplianceCheckResponse>("/building-compliance/check", {
          useMock: false,
          body: {
            project_id: projectId,
            building_type: form.buildingType,
            address,
            area_sqm: areaSqm,
            floors: Number(form.floors) || undefined,
            // 부지분석 용도지역 + (있으면) 설계값 → 설계 전 검토/설계 정합 검증 자동 분기
            zone_code: siteAnalysis?.zoneCode || undefined,
            planned_bcr: designData?.bcr ?? undefined,
            planned_far: designData?.far ?? undefined,
          },
        }),
        apiClient.post<LifecycleChecklistResponse>(
          "/lifecycle/construction/checklist",
          {
            useMock: false,
            body: {
              project_id: projectId,
              building_type: form.buildingType,
            },
          },
        ),
      ]);

      setComplianceResult(compliance);
      setChecklistResult(checklist);

      // Derive stages from checklist / compliance
      const submittedStages = new Set(
        checklist.items
          .filter((item) => item.submitted)
          .map((item) => item.stage),
      );
      const updatedStages = DEFAULT_STAGES.map((stage, i) => {
        if (submittedStages.has(stage.key)) {
          return { ...stage, status: "completed" as const };
        }
        // First non-completed becomes current
        const allPreviousComplete = DEFAULT_STAGES.slice(0, i).every((s) =>
          submittedStages.has(s.key),
        );
        if (allPreviousComplete && !submittedStages.has(stage.key)) {
          return { ...stage, status: "current" as const };
        }
        return stage;
      });
      // Ensure only one "current"
      let foundCurrent = false;
      const finalStages = updatedStages.map((s) => {
        if (s.status === "current") {
          if (foundCurrent) return { ...s, status: "pending" as const };
          foundCurrent = true;
        }
        return s;
      });
      setStages(finalStages);
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsSubmitting(false);
    }
  }

  function statusText(status: string) {
    switch (status) {
      case "pass":
        return labels.passText;
      case "fail":
        return labels.failText;
      case "warning":
        return labels.warningText;
      case "info":
        return labels.infoText;
      default:
        return status;
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
                  value={form.buildingType}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      buildingType: event.target.value,
                    }))
                  }
                  placeholder={labels.buildingTypeLabel}
                />
                <ProjectAddressInput
                  value={form.address}
                  onChange={(address) => setForm((current) => ({ ...current, address }))}
                  label={labels.addressLabel}
                  placeholder={labels.addressLabel}
                />
                <div className="grid gap-3 md:grid-cols-2">
                  <NumberInput
                    allowDecimal
                    value={form.areaSqm === "" ? null : Number(form.areaSqm)}
                    onChange={(n) =>
                      setForm((current) => ({
                        ...current,
                        areaSqm: n != null ? String(n) : "",
                      }))
                    }
                    placeholder={labels.areaLabel}
                    className="flex h-11 w-full rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
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

      {/* Permit Stages */}
      <Card>
        <CardContent className="p-6">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
            {labels.stagesTitle}
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
            {stages.map((stage, i, arr) => (
              <div
                key={stage.key}
                className="flex flex-1 items-center gap-4 min-w-[120px]"
              >
                <div className="flex flex-col items-center gap-3 flex-1 text-center">
                  <div
                    className={`flex h-12 w-12 items-center justify-center rounded-full border-2 text-sm font-bold transition-all ${
                      stage.status === "completed"
                        ? "bg-[var(--accent-strong)] border-[var(--accent-strong)] text-white"
                        : stage.status === "current"
                          ? "border-[var(--accent-strong)] text-[var(--accent-strong)] bg-[rgba(14,116,144,0.1)] animate-pulse"
                          : "border-[var(--line)] text-[var(--text-tertiary)]"
                    }`}
                  >
                    {stage.status === "completed" ? "\u2713" : i + 1}
                  </div>
                  <span
                    className={`text-sm font-semibold ${
                      stage.status === "current"
                        ? "text-[var(--accent-strong)]"
                        : stage.status === "completed"
                          ? "text-[var(--text-primary)]"
                          : "text-[var(--text-tertiary)]"
                    }`}
                  >
                    {stage.label}
                  </span>
                </div>
                {i < arr.length - 1 && (
                  <div
                    className={`mb-8 h-0.5 flex-1 ${
                      stage.status === "completed"
                        ? "bg-[var(--accent-strong)]"
                        : "bg-[var(--line)]"
                    }`}
                  />
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Compliance + Checklist */}
      <div className="grid gap-6 xl:grid-cols-2">
        {/* Compliance */}
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.complianceTitle}
            </p>
            {complianceResult ? (
              <div className="mt-4 space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`rounded-full border px-4 py-1.5 text-xs font-bold ${statusBadgeClass(complianceResult.overall_status)}`}
                  >
                    {labels.complianceOverallLabel}:{" "}
                    {statusText(complianceResult.overall_status)}
                  </span>
                  {/* WP-P: 판정 옆 법령 근거 칩 — 백엔드 legal_refs[]가 있을 때만(옵셔널 가드, 구버전 무손상).
                      url은 백엔드 레지스트리 제공값만 사용(LegalRefChip이 무링크 텍스트 폴백). */}
                  {(complianceResult.legal_refs ?? []).map((ref, j) => (
                    <LegalRefChip
                      key={`overall-ref-${ref.key ?? j}`}
                      lawName={ref.law_name}
                      article={ref.article}
                      title={ref.title}
                      url={ref.url}
                    />
                  ))}
                </div>
                <div className="space-y-3">
                  {(complianceResult.checks ?? []).map((check, i) => (
                    <div
                      key={`check-${i}`}
                      className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-4"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-semibold text-[var(--text-primary)]">
                            {check.rule_name}
                          </p>
                          <p className="mt-1 text-xs text-[var(--text-tertiary)]">
                            {check.rule_code}
                          </p>
                          <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
                            {check.detail}
                          </p>
                          <p className="mt-1 text-xs text-[var(--text-tertiary)]">
                            {labels.complianceRefLabel}: {check.regulation_ref}
                          </p>
                          {/* WP-P: 룰 카드별 법령 원문 칩 — legal_refs 있을 때만 렌더(옵셔널 가드).
                              기존 regulation_ref 텍스트는 그대로 유지(additive). */}
                          {(check.legal_refs ?? []).length > 0 && (
                            <div className="mt-2 flex flex-wrap gap-1.5">
                              {(check.legal_refs ?? []).map((ref, j) => (
                                <LegalRefChip
                                  key={`check-${i}-ref-${ref.key ?? j}`}
                                  lawName={ref.law_name}
                                  article={ref.article}
                                  title={ref.title}
                                  url={ref.url}
                                />
                              ))}
                            </div>
                          )}
                        </div>
                        <span
                          className={`shrink-0 rounded-full border px-3 py-1 text-[10px] font-bold ${statusBadgeClass(check.status)}`}
                        >
                          {statusText(check.status)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                  <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                    {labels.complianceSummaryLabel}
                  </p>
                  <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
                    {complianceResult.summary}
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

        {/* Checklist */}
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.checklistTitle}
            </p>
            {checklistResult ? (
              <div className="mt-4 space-y-3">
                {(checklistResult.items ?? []).map((item) => (
                  <div
                    key={item.id}
                    className="flex items-center justify-between rounded-[var(--radius-xl)] bg-[var(--surface-soft)] px-5 py-4 transition-all hover:bg-[var(--surface)]"
                  >
                    <div className="flex items-center gap-4 min-w-0">
                      <span
                        className={`flex h-6 w-6 items-center justify-center rounded-lg border text-xs font-bold ${
                          item.submitted
                            ? "border-emerald-300 bg-emerald-50 text-emerald-600"
                            : "border-[var(--line)] text-transparent"
                        }`}
                      >
                        {item.submitted ? "\u2713" : ""}
                      </span>
                      <div className="min-w-0">
                        <p
                          className={`text-sm font-semibold truncate ${
                            item.submitted
                              ? "text-[var(--text-primary)]"
                              : "text-[var(--text-secondary)]"
                          }`}
                        >
                          {item.document_name}
                        </p>
                        <p className="text-xs text-[var(--text-tertiary)]">
                          {item.stage}
                          {item.deadline ? ` | ${item.deadline}` : ""}
                          {item.note ? ` | ${item.note}` : ""}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {item.required && (
                        <span className="rounded-full bg-amber-50 border border-amber-200 px-2 py-0.5 text-[10px] font-bold text-amber-600">
                          {labels.requiredText}
                        </span>
                      )}
                      <span
                        className={`text-[10px] font-bold uppercase tracking-widest ${
                          item.submitted
                            ? "text-emerald-600"
                            : "text-[var(--text-tertiary)]"
                        }`}
                      >
                        {item.submitted
                          ? labels.submittedText
                          : labels.notSubmittedText}
                      </span>
                    </div>
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
