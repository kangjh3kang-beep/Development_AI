"use client";

import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, CardTitle, Input } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { NumberInput } from "@/components/common/NumberInput";
import { UseLlmToggle } from "@/components/common/UseLlmToggle";
import { ApiClientError, apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { SiteDataGate } from "@/components/projects/SiteDataGate";
import type { Locale } from "@/i18n/config";

/* ── Response Types ── */

// ★계약 정합(실버그 수정): 과거 이 타입은 items[]/total_cost_krw/ai_analysis 등
// 백엔드에 존재하지 않는 키를 선언해 결과 패널이 통째로 빈 값이었다(무음 미렌더).
// 백엔드 정본 = POST /cost/{pid}/calculate 응답(OriginCostCalculator 12단계 집계
// + 공종별 소계 category_totals + CostInterpreter ai_* 5형제). items는 에코되지 않는다.
type CostCalculationResponse = {
  project_id: string;
  // 12단계 원가 집계(원 단위)
  direct_material_cost: number;
  direct_labor_cost: number;
  direct_expense_cost: number;
  direct_cost: number;
  indirect_labor_cost: number;
  total_labor_cost: number;
  insurance_total: number;
  safety_health: number;
  env_preserve: number;
  net_construction_cost: number;
  general_mgmt: number;
  profit: number;
  construction_cost_pre_vat: number;
  vat: number;
  total_project_cost: number;
  category_totals: Record<string, number>;
  item_count: number;
  // LLM 해석(use_llm 옵트인 시에만 채워짐 — 없으면 미렌더)
  ai_cost_analysis?: string | null;
  ai_ve_suggestions?: string | null;
  ai_material_advice?: string | null;
  ai_schedule_impact?: string | null;
  ai_risk_factors?: string | null;
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
  costMatRateLabel: string;
  costLaborRateLabel: string;
  costExpRateLabel: string;
  stageBreakdownTitle: string;
  categorySubtotalTitle: string;
  supplyPriceLabel: string;
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
  costDescLabel: "품명·규격",
  costUnitLabel: "단위",
  costQtyLabel: "수량",
  costMatRateLabel: "재료단가 (원)",
  costLaborRateLabel: "노무단가 (원)",
  costExpRateLabel: "경비단가 (원)",
  stageBreakdownTitle: "12단계 원가 분해",
  categorySubtotalTitle: "공종별 소계",
  supplyPriceLabel: "공급가액(부가세 전)",
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
  costDescLabel: "Item name/spec",
  costUnitLabel: "Unit",
  costQtyLabel: "Quantity",
  costMatRateLabel: "Material rate (KRW)",
  costLaborRateLabel: "Labor rate (KRW)",
  costExpRateLabel: "Expense rate (KRW)",
  stageBreakdownTitle: "12-stage cost breakdown",
  categorySubtotalTitle: "Subtotal by work type",
  supplyPriceLabel: "Supply price (pre-VAT)",
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

// ★계약 정합: 백엔드 계산기(OriginCostCalculator)는 재료/노무/경비 3분해 단가
// (mat_unit/labor_unit/exp_unit)를 읽는다 — 과거의 종합단가(unit_rate_krw) 단일 필드는
// 백엔드가 읽지 않아 직접공사비가 0으로 계산되던 실버그였다(간접노무비 등 12단계가
// 노무비 기반이라 분해 입력이 정확성의 전제).
type CostFormItem = {
  work_code: string;
  description: string;
  unit: string;
  quantity: string;
  mat_unit: string;
  labor_unit: string;
  exp_unit: string;
};

const EMPTY_COST_ITEM: CostFormItem = {
  work_code: "",
  description: "",
  unit: "m2",
  quantity: "",
  mat_unit: "",
  labor_unit: "",
  exp_unit: "",
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

  // 부지 핵심 입력(면적/주소) 준비 여부 — 없으면 데모 시드 폼 대신 게이트로 유도(무목업).
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const hasSiteData = !!(
    (siteAnalysis?.landAreaSqm && siteAnalysis.landAreaSqm > 0) ||
    siteAnalysis?.address
  );

  const [workspaceError, setWorkspaceError] = useState("");
  const [isSubmittingCost, setIsSubmittingCost] = useState(false);
  const [isSubmittingChecklist, setIsSubmittingChecklist] = useState(false);
  // T3: use_llm 옵트인 — 기존 동작(AI 원가 해석 항상 포함)을 보존하기 위해 기본 true로 명시 전송.
  const [useLlm, setUseLlm] = useState(true);
  const [costResult, setCostResult] =
    useState<CostCalculationResponse | null>(null);
  const [checklistResult, setChecklistResult] =
    useState<ConstructionChecklistResponse | null>(null);

  // 시작 행은 공종 예시만 제공하고 수량·단가는 비워둔다(임의 데모 단가 하드코딩 금지 — 무목업).
  const [costItems, setCostItems] = useState<CostFormItem[]>([
    { ...EMPTY_COST_ITEM, work_code: "RC01", description: "철근콘크리트 공사", unit: "m3" },
    { ...EMPTY_COST_ITEM, work_code: "ST01", description: "철골 공사", unit: "ton" },
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
      // ★백엔드 계약 키로 전송: item_name(품명)·mat/labor/exp 3분해 단가.
      const items = costItems.map((item) => ({
        work_code: item.work_code.trim(),
        item_name: item.description.trim(),
        unit: item.unit.trim(),
        quantity: Number(item.quantity) || 0,
        mat_unit: Number(item.mat_unit) || 0,
        labor_unit: Number(item.labor_unit) || 0,
        exp_unit: Number(item.exp_unit) || 0,
      }));

      const result = await apiClient.post<CostCalculationResponse>(
        `/cost/${projectId}/calculate`,
        {
          useMock: false,
          body: { items, use_llm: useLlm },
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
    <section className="grid grid-cols-1 gap-6 min-w-0">
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
          {workspaceError ? (
            <div className="mt-6 rounded-[var(--radius-xl)] border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] p-5 text-sm leading-7 text-[var(--spot)]">
              {workspaceError}
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* 부지 데이터준비 게이트(공용) — 부지 미입력 시 데모 시드 폼 대신 유도(무목업). */}
      {!hasSiteData ? (
        <SiteDataGate
          locale={locale}
          projectId={projectId}
          title="시공계획 산출에 부지 데이터가 필요합니다"
          description="부지면적 또는 정확한 주소(시·구·동·번지)를 입력하면 공사비·체크리스트·리스크가 정확히 산출됩니다."
        />
      ) : (
      <>
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
                {/* ★재료/노무/경비 3분해 단가 — 백엔드 12단계(간접노무비=노무비 기반) 정확성의 전제 */}
                <NumberInput
                  value={item.mat_unit === "" ? null : Number(item.mat_unit)}
                  onChange={(n) =>
                    updateCostItem(index, "mat_unit", n != null ? String(n) : "")
                  }
                  placeholder={labels.costMatRateLabel}
                  className="flex h-11 w-full rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
                />
                <NumberInput
                  value={item.labor_unit === "" ? null : Number(item.labor_unit)}
                  onChange={(n) =>
                    updateCostItem(index, "labor_unit", n != null ? String(n) : "")
                  }
                  placeholder={labels.costLaborRateLabel}
                  className="flex h-11 w-full rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
                />
                <div className="flex gap-2">
                  <NumberInput
                    value={item.exp_unit === "" ? null : Number(item.exp_unit)}
                    onChange={(n) =>
                      updateCostItem(index, "exp_unit", n != null ? String(n) : "")
                    }
                    placeholder={labels.costExpRateLabel}
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
            <div className="flex flex-wrap items-center gap-3">
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
              <UseLlmToggle
                checked={useLlm}
                onChange={setUseLlm}
                hint="AI 원가 해석 포함"
                disabled={isSubmittingCost}
              />
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
              {/* ★백엔드 실계약 렌더(실버그 수정): 계산기는 항목 에코 없이 12단계 집계
                  +공종별 소계를 반환한다 — 과거의 items 테이블은 항상 빈 배열이었다. */}
              <div className="grid gap-4 md:grid-cols-3">
                <MetricTile
                  label={labels.supplyPriceLabel}
                  value={formatCurrency(costResult.construction_cost_pre_vat)}
                />
                <MetricTile
                  label={labels.vatLabel}
                  value={formatCurrency(costResult.vat)}
                />
                <MetricTile
                  label={labels.grandTotalLabel}
                  value={formatCurrency(costResult.total_project_cost)}
                />
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-widest text-[var(--text-tertiary)]">
                  {labels.stageBreakdownTitle}
                </p>
                <div className="mt-2 overflow-x-auto">
                  <table className="w-full text-sm">
                    <tbody>
                      {(
                        [
                          ["직접재료비", costResult.direct_material_cost],
                          ["직접노무비", costResult.direct_labor_cost],
                          ["직접경비", costResult.direct_expense_cost],
                          ["직접공사비 소계", costResult.direct_cost],
                          ["간접노무비", costResult.indirect_labor_cost],
                          ["4대보험 등 보험료", costResult.insurance_total],
                          ["산업안전보건관리비", costResult.safety_health],
                          ["환경보전비", costResult.env_preserve],
                          ["순공사원가", costResult.net_construction_cost],
                          ["일반관리비", costResult.general_mgmt],
                          ["이윤", costResult.profit],
                        ] as const
                      ).map(([label, amount]) => (
                        <tr key={label} className="border-b border-[var(--line)]">
                          <td className="py-2 pr-4 text-[var(--text-secondary)]">{label}</td>
                          <td className="py-2 text-right font-medium text-[var(--text-primary)]">
                            {formatCurrency(amount ?? 0)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              {costResult.category_totals &&
              Object.keys(costResult.category_totals).length > 0 ? (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-widest text-[var(--text-tertiary)]">
                    {labels.categorySubtotalTitle}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {Object.entries(costResult.category_totals).map(([code, amt]) => (
                      <span
                        key={code}
                        className="rounded-full bg-[var(--surface-soft)] px-3 py-1 text-xs text-[var(--text-secondary)]"
                      >
                        <span className="font-mono">{code}</span>{" "}
                        <span className="font-semibold text-[var(--text-primary)]">
                          {formatCurrency(amt)}
                        </span>
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
              {costResult.ai_cost_analysis ? (
                <div className="space-y-3 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                  <p className="text-sm leading-7 text-[var(--text-secondary)]">
                    {costResult.ai_cost_analysis}
                  </p>
                  {(
                    [
                      ["VE 제안", costResult.ai_ve_suggestions],
                      ["자재 조언", costResult.ai_material_advice],
                      ["공정 영향", costResult.ai_schedule_impact],
                      ["리스크 요인", costResult.ai_risk_factors],
                    ] as const
                  )
                    .filter(([, text]) => !!text)
                    .map(([title, text]) => (
                      <div key={title}>
                        <p className="text-xs font-semibold text-[var(--text-tertiary)]">
                          {title}
                        </p>
                        <p className="text-sm leading-6 text-[var(--text-secondary)]">
                          {text}
                        </p>
                      </div>
                    ))}
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
                {(checklistResult.checklist ?? []).map((item, i) => (
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
                  {riskQuery.data.factors?.length ? (
                    <div className="mt-3 grid gap-3">
                      {(riskQuery.data.factors ?? []).map((factor, i) => (
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
      </>
      )}
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
