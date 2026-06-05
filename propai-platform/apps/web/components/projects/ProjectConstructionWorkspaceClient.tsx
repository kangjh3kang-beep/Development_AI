"use client";

import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, CardTitle, Input } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { NumberInput } from "@/components/common/NumberInput";
import { ApiClientError, apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";

/* ── Response Types ── */

type CostItem = {
  work_code: string;
  description: string;
  unit: string;
  quantity: number;
  unit_rate_krw: number;
  total_krw: number;
};

type CostCalculationResponse = {
  project_id: string;
  items: CostItem[];
  total_cost_krw: number;
  vat_krw: number;
  grand_total_krw: number;
  ai_analysis?: string;
};

type ChecklistItem = {
  category: string;
  item: string;
  required: boolean;
  description?: string;
};

type ConstructionChecklistResponse = {
  project_id: string;
  project_type: string;
  checklist: ChecklistItem[];
  total_items: number;
  ai_recommendations?: string;
};

type RiskFactor = {
  category: string;
  risk_level: string;
  score: number;
  description?: string;
};

type RiskAssessmentResponse = {
  overall_score: number;
  overall_level: string;
  factors: RiskFactor[];
  ai_analysis?: string;
};

/* ── Labels ── */

type Labels = {
  heroTitle: string;
  heroDescription: string;
  heroHint: string;
  tokenHint: string;
  authError: string;
  formTitle: string;
  costTitle: string;
  costWorkCodeLabel: string;
  costDescLabel: string;
  costUnitLabel: string;
  costQtyLabel: string;
  costRateLabel: string;
  addItemAction: string;
  removeItemAction: string;
  submitCostAction: string;
  checklistTitle: string;
  projectTypeLabel: string;
  projectCostLabel: string;
  floorCountLabel: string;
  excavationDepthLabel: string;
  submitChecklistAction: string;
  riskTitle: string;
  riskOverallLabel: string;
  riskLevelLabel: string;
  riskFactorsLabel: string;
  totalCostLabel: string;
  vatLabel: string;
  grandTotalLabel: string;
  categoryLabel: string;
  requiredLabel: string;
  placeholder: string;
  retryAction: string;
  projectLoadErrorTitle: string;
  projectLoadErrorDetail: string;
};

const KO_LABELS: Labels = {
  heroTitle: "시공관리 라이브 작업 공간",
  heroDescription:
    "공사비 산출, 시공 체크리스트, 리스크 평가를 실시간으로 수행합니다.",
  heroHint:
    "원가 산출 API, 시공 체크리스트 생성, 리스크 평가를 연계하여 종합 시공관리를 지원합니다.",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "라이브 작업 공간 호출을 위해 API 인증이 필요합니다.",
  formTitle: "공사비 항목 입력",
  costTitle: "공사비 산출 결과",
  costWorkCodeLabel: "공종 코드",
  costDescLabel: "내용",
  costUnitLabel: "단위",
  costQtyLabel: "수량",
  costRateLabel: "단가 (원)",
  addItemAction: "항목 추가",
  removeItemAction: "삭제",
  submitCostAction: "공사비 산출 실행",
  checklistTitle: "시공 체크리스트",
  projectTypeLabel: "프로젝트 유형",
  projectCostLabel: "총 공사비 (원)",
  floorCountLabel: "층수",
  excavationDepthLabel: "굴착 깊이 (m)",
  submitChecklistAction: "체크리스트 생성",
  riskTitle: "리스크 평가",
  riskOverallLabel: "종합 점수",
  riskLevelLabel: "리스크 등급",
  riskFactorsLabel: "리스크 요인",
  totalCostLabel: "합계",
  vatLabel: "부가세",
  grandTotalLabel: "총계",
  categoryLabel: "분류",
  requiredLabel: "필수",
  placeholder: "폼을 제출하면 결과가 표시됩니다.",
  retryAction: "재시도",
  projectLoadErrorTitle: "리스크 평가 로드 실패",
  projectLoadErrorDetail:
    "리스크 평가 데이터를 가져오지 못했습니다. 재시도하세요.",
};

const EN_LABELS: Labels = {
  heroTitle: "Construction management live workspace",
  heroDescription:
    "Run cost calculations, construction checklists, and risk assessments in real time.",
  heroHint:
    "Chains cost calculation API, construction checklist generation, and risk assessment for comprehensive management.",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "API authentication is required for live workspace calls.",
  formTitle: "Cost item input",
  costTitle: "Cost calculation results",
  costWorkCodeLabel: "Work code",
  costDescLabel: "Description",
  costUnitLabel: "Unit",
  costQtyLabel: "Quantity",
  costRateLabel: "Unit rate (KRW)",
  addItemAction: "Add item",
  removeItemAction: "Remove",
  submitCostAction: "Run cost calculation",
  checklistTitle: "Construction checklist",
  projectTypeLabel: "Project type",
  projectCostLabel: "Total cost (KRW)",
  floorCountLabel: "Floor count",
  excavationDepthLabel: "Excavation depth (m)",
  submitChecklistAction: "Generate checklist",
  riskTitle: "Risk assessment",
  riskOverallLabel: "Overall score",
  riskLevelLabel: "Risk level",
  riskFactorsLabel: "Risk factors",
  totalCostLabel: "Subtotal",
  vatLabel: "VAT",
  grandTotalLabel: "Grand total",
  categoryLabel: "Category",
  requiredLabel: "Required",
  placeholder: "Submit the form to see results.",
  retryAction: "Retry",
  projectLoadErrorTitle: "Risk assessment unavailable",
  projectLoadErrorDetail:
    "Risk assessment data failed to load. Retry to restore.",
};

const LABELS: Record<Locale, Labels> = {
  ko: KO_LABELS,
  en: EN_LABELS,
  "zh-CN": KO_LABELS,
};

/* ── Helpers ── */

function formatCurrency(value: number) {
  return new Intl.NumberFormat("ko-KR", {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
  }).format(value);
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

type CostFormItem = {
  work_code: string;
  description: string;
  unit: string;
  quantity: string;
  unit_rate_krw: string;
};

const EMPTY_COST_ITEM: CostFormItem = {
  work_code: "",
  description: "",
  unit: "m2",
  quantity: "",
  unit_rate_krw: "",
};

/* ── Component ── */

export function ProjectConstructionWorkspaceClient({
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
  const [isSubmittingCost, setIsSubmittingCost] = useState(false);
  const [isSubmittingChecklist, setIsSubmittingChecklist] = useState(false);
  const [costResult, setCostResult] =
    useState<CostCalculationResponse | null>(null);
  const [checklistResult, setChecklistResult] =
    useState<ConstructionChecklistResponse | null>(null);

  const [costItems, setCostItems] = useState<CostFormItem[]>([
    { ...EMPTY_COST_ITEM, work_code: "RC01", description: "철근콘크리트 공사", unit: "m3", quantity: "500", unit_rate_krw: "180000" },
    { ...EMPTY_COST_ITEM, work_code: "ST01", description: "철골 공사", unit: "ton", quantity: "120", unit_rate_krw: "2500000" },
  ]);

  const [checklistForm, setChecklistForm] = useState({
    projectType: "아파트",
    projectCost: "50000000000",
    floorCount: "25",
    excavationDepth: "12",
  });

  /* Risk assessment query */
  const riskQuery = useQuery({
    queryKey: ["lifecycle", "risk", projectId],
    enabled: canUseLiveApi,
    queryFn: () =>
      apiClient.get<RiskAssessmentResponse>("/lifecycle/risk/assessment", {
        useMock: false,
      }),
  });

  const riskError = riskQuery.error
    ? extractErrorMessage(riskQuery.error, labels.authError)
    : "";

  function addCostItem() {
    setCostItems((current) => [...current, { ...EMPTY_COST_ITEM }]);
  }

  function removeCostItem(index: number) {
    setCostItems((current) => current.filter((_, i) => i !== index));
  }

  function updateCostItem(
    index: number,
    field: keyof CostFormItem,
    value: string,
  ) {
    setCostItems((current) =>
      current.map((item, i) =>
        i === index ? { ...item, [field]: value } : item,
      ),
    );
  }

  async function handleCostSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");
    setIsSubmittingCost(true);

    try {
      const items = costItems.map((item) => ({
        work_code: item.work_code.trim(),
        description: item.description.trim(),
        unit: item.unit.trim(),
        quantity: Number(item.quantity) || 0,
        unit_rate_krw: Number(item.unit_rate_krw) || 0,
      }));

      const result = await apiClient.post<CostCalculationResponse>(
        `/cost/${projectId}/calculate`,
        {
          useMock: false,
          body: { items },
        },
      );
      setCostResult(result);
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsSubmittingCost(false);
    }
  }

  async function handleChecklistSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");
    setIsSubmittingChecklist(true);

    try {
      const result = await apiClient.post<ConstructionChecklistResponse>(
        "/lifecycle/construction/checklist",
        {
          useMock: false,
          body: {
            project_id: projectId,
            project_type: checklistForm.projectType.trim(),
            project_cost_krw: Number(checklistForm.projectCost) || 0,
            floor_count: Number(checklistForm.floorCount) || 0,
            excavation_depth_m: Number(checklistForm.excavationDepth) || 0,
          },
        },
      );
      setChecklistResult(result);
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsSubmittingChecklist(false);
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
          {workspaceError ? (
            <div className="mt-6 rounded-[var(--radius-xl)] border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] p-5 text-sm leading-7 text-[var(--spot)]">
              {workspaceError}
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* Cost Calculation Form + Results */}
      <Card>
        <CardContent className="p-6">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
            {labels.formTitle}
          </p>
          <form className="mt-4 grid gap-4" onSubmit={handleCostSubmit}>
            {costItems.map((item, index) => (
              <div
                key={index}
                className="grid gap-3 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-4 md:grid-cols-6"
              >
                <Input
                  value={item.work_code}
                  onChange={(e) =>
                    updateCostItem(index, "work_code", e.target.value)
                  }
                  placeholder={labels.costWorkCodeLabel}
                />
                <Input
                  value={item.description}
                  onChange={(e) =>
                    updateCostItem(index, "description", e.target.value)
                  }
                  placeholder={labels.costDescLabel}
                  className="md:col-span-2"
                />
                <Input
                  value={item.unit}
                  onChange={(e) =>
                    updateCostItem(index, "unit", e.target.value)
                  }
                  placeholder={labels.costUnitLabel}
                />
                <NumberInput
                  allowDecimal
                  value={item.quantity === "" ? null : Number(item.quantity)}
                  onChange={(n) =>
                    updateCostItem(index, "quantity", n != null ? String(n) : "")
                  }
                  placeholder={labels.costQtyLabel}
                  className="flex h-11 w-full rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
                />
                <div className="flex gap-2">
                  <NumberInput
                    value={item.unit_rate_krw === "" ? null : Number(item.unit_rate_krw)}
                    onChange={(n) =>
                      updateCostItem(index, "unit_rate_krw", n != null ? String(n) : "")
                    }
                    placeholder={labels.costRateLabel}
                    className="flex-1 flex h-11 w-full rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
                  />
                  {costItems.length > 1 && (
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => removeCostItem(index)}
                      className="shrink-0"
                    >
                      {labels.removeItemAction}
                    </Button>
                  )}
                </div>
              </div>
            ))}
            <div className="flex gap-3">
              <Button type="button" variant="secondary" onClick={addCostItem}>
                {labels.addItemAction}
              </Button>
              <Button
                type="submit"
                disabled={!canUseLiveApi || isSubmittingCost}
              >
                {isSubmittingCost
                  ? `${labels.submitCostAction}...`
                  : labels.submitCostAction}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Cost Results */}
      <Card>
        <CardContent className="p-6">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
            {labels.costTitle}
          </p>
          {costResult ? (
            <div className="mt-4 space-y-4">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[var(--line)] text-left text-xs uppercase tracking-widest text-[var(--text-tertiary)]">
                      <th className="py-3 pr-4">{labels.costWorkCodeLabel}</th>
                      <th className="py-3 pr-4">{labels.costDescLabel}</th>
                      <th className="py-3 pr-4">{labels.costUnitLabel}</th>
                      <th className="py-3 pr-4 text-right">
                        {labels.costQtyLabel}
                      </th>
                      <th className="py-3 pr-4 text-right">
                        {labels.costRateLabel}
                      </th>
                      <th className="py-3 text-right">{labels.totalCostLabel}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {costResult.items.map((item, i) => (
                      <tr
                        key={`${item.work_code}-${i}`}
                        className="border-b border-[var(--line)]"
                      >
                        <td className="py-3 pr-4 font-mono text-[var(--text-secondary)]">
                          {item.work_code}
                        </td>
                        <td className="py-3 pr-4 text-[var(--text-primary)]">
                          {item.description}
                        </td>
                        <td className="py-3 pr-4 text-[var(--text-secondary)]">
                          {item.unit}
                        </td>
                        <td className="py-3 pr-4 text-right text-[var(--text-secondary)]">
                          {item.quantity.toLocaleString()}
                        </td>
                        <td className="py-3 pr-4 text-right text-[var(--text-secondary)]">
                          {formatCurrency(item.unit_rate_krw)}
                        </td>
                        <td className="py-3 text-right font-semibold text-[var(--text-primary)]">
                          {formatCurrency(item.total_krw)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="grid gap-4 md:grid-cols-3">
                <MetricTile
                  label={labels.totalCostLabel}
                  value={formatCurrency(costResult.total_cost_krw)}
                />
                <MetricTile
                  label={labels.vatLabel}
                  value={formatCurrency(costResult.vat_krw)}
                />
                <MetricTile
                  label={labels.grandTotalLabel}
                  value={formatCurrency(costResult.grand_total_krw)}
                />
              </div>
              {costResult.ai_analysis ? (
                <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                  <p className="text-sm leading-7 text-[var(--text-secondary)]">
                    {costResult.ai_analysis}
                  </p>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
              {labels.placeholder}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-2">
        {/* Checklist */}
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.checklistTitle}
            </p>
            <form
              className="mt-4 grid gap-3"
              onSubmit={handleChecklistSubmit}
            >
              <Input
                value={checklistForm.projectType}
                onChange={(e) =>
                  setChecklistForm((c) => ({
                    ...c,
                    projectType: e.target.value,
                  }))
                }
                placeholder={labels.projectTypeLabel}
              />
              <div className="grid gap-3 md:grid-cols-3">
                <NumberInput
                  value={checklistForm.projectCost === "" ? null : Number(checklistForm.projectCost)}
                  onChange={(n) =>
                    setChecklistForm((c) => ({
                      ...c,
                      projectCost: n != null ? String(n) : "",
                    }))
                  }
                  placeholder={labels.projectCostLabel}
                  className="flex h-11 w-full rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
                />
                <Input
                  type="number"
                  value={checklistForm.floorCount}
                  onChange={(e) =>
                    setChecklistForm((c) => ({
                      ...c,
                      floorCount: e.target.value,
                    }))
                  }
                  placeholder={labels.floorCountLabel}
                />
                <Input
                  type="number"
                  value={checklistForm.excavationDepth}
                  onChange={(e) =>
                    setChecklistForm((c) => ({
                      ...c,
                      excavationDepth: e.target.value,
                    }))
                  }
                  placeholder={labels.excavationDepthLabel}
                />
              </div>
              <Button
                type="submit"
                disabled={!canUseLiveApi || isSubmittingChecklist}
              >
                {isSubmittingChecklist
                  ? `${labels.submitChecklistAction}...`
                  : labels.submitChecklistAction}
              </Button>
            </form>
            {checklistResult ? (
              <div className="mt-4 grid gap-3">
                {checklistResult.checklist.map((item, i) => (
                  <div
                    key={`${item.category}-${i}`}
                    className="flex items-center justify-between gap-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] px-5 py-4"
                  >
                    <div className="space-y-1">
                      <p className="text-sm font-medium text-[var(--text-primary)]">
                        {item.item}
                      </p>
                      <p className="text-xs text-[var(--text-tertiary)]">
                        {labels.categoryLabel}: {item.category}
                      </p>
                      {item.description ? (
                        <p className="text-xs text-[var(--text-secondary)]">
                          {item.description}
                        </p>
                      ) : null}
                    </div>
                    {item.required && (
                      <span className="shrink-0 rounded-lg bg-[rgba(239,68,68,0.1)] px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-[var(--error)]">
                        {labels.requiredLabel}
                      </span>
                    )}
                  </div>
                ))}
                {checklistResult.ai_recommendations ? (
                  <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                    <p className="text-sm leading-7 text-[var(--text-secondary)]">
                      {checklistResult.ai_recommendations}
                    </p>
                  </div>
                ) : null}
              </div>
            ) : null}
          </CardContent>
        </Card>

        {/* Risk Assessment */}
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.riskTitle}
            </p>
            {riskError ? (
              <div className="mt-4">
                <WorkspaceQueryErrorCard
                  title={labels.projectLoadErrorTitle}
                  description={labels.projectLoadErrorDetail}
                  message={riskError}
                  actionLabel={labels.retryAction}
                  onRetry={() => {
                    void riskQuery.refetch();
                  }}
                />
              </div>
            ) : riskQuery.isLoading ? (
              <SkeletonLoader count={1} itemClassName="h-40 mt-4" />
            ) : riskQuery.data ? (
              <div className="mt-4 space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <MetricTile
                    label={labels.riskOverallLabel}
                    value={`${riskQuery.data.overall_score}/100`}
                  />
                  <MetricTile
                    label={labels.riskLevelLabel}
                    value={riskQuery.data.overall_level}
                  />
                </div>
                <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                  <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                    {labels.riskFactorsLabel}
                  </p>
                  {riskQuery.data.factors.length ? (
                    <div className="mt-3 grid gap-3">
                      {riskQuery.data.factors.map((factor, i) => (
                        <div
                          key={`${factor.category}-${i}`}
                          className="flex items-center justify-between rounded-[var(--radius-xl)] bg-[var(--surface)] px-4 py-3"
                        >
                          <div className="space-y-1">
                            <p className="text-sm font-medium text-[var(--text-primary)]">
                              {factor.category}
                            </p>
                            {factor.description ? (
                              <p className="text-xs text-[var(--text-secondary)]">
                                {factor.description}
                              </p>
                            ) : null}
                          </div>
                          <span
                            className={`shrink-0 rounded-lg px-3 py-1 text-[10px] font-bold uppercase tracking-widest ${
                              factor.risk_level === "high"
                                ? "bg-[rgba(239,68,68,0.1)] text-[var(--error)]"
                                : factor.risk_level === "medium"
                                  ? "bg-[rgba(217,119,6,0.1)] text-[var(--spot)]"
                                  : "bg-[rgba(14,116,144,0.1)] text-[var(--accent-strong)]"
                            }`}
                          >
                            {factor.risk_level} ({factor.score})
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-3 text-sm text-[var(--text-tertiary)]">
                      -
                    </p>
                  )}
                </div>
                {riskQuery.data.ai_analysis ? (
                  <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                    <p className="text-sm leading-7 text-[var(--text-secondary)]">
                      {riskQuery.data.ai_analysis}
                    </p>
                  </div>
                ) : null}
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
