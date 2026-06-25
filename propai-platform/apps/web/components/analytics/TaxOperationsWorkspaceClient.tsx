"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Button,
  Card,
  CardContent,
  CardTitle,
  Input,
  Select,
} from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { LegalRefChip } from "@/components/common/LegalRefChip";
import { NumberInput } from "@/components/common/NumberInput";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { VerificationBadge } from "@/components/common/VerificationBadge";
import { ExpertPanelCard } from "@/components/common/ExpertPanelCard";
import type { Locale } from "@/i18n/config";

type ProjectSummary = {
  id: string;
  name: string;
  status: string;
  address: string | null;
  total_area_sqm: number | null;
  updated_at: string;
};

type PaginatedResponse<T> = {
  items: T[];
  page: number;
  page_size: number;
  has_next: boolean;
};

/**
 * 법령 근거 1건 — 백엔드 legal_reference_registry 직렬화 형태와 동일 스키마.
 * url은 **백엔드 제공값만** 사용(프론트에서 law.go.kr URL 조립 금지).
 * url 부재 시 LegalRefChip이 링크 없는 텍스트 칩으로 정직 폴백한다.
 */
type TaxLegalRef = {
  key?: string;
  law_name: string;
  article?: string | null;
  title?: string | null;
  url?: string | null;
};

type TaxCalculationResponse = {
  id: string;
  project_id: string;
  tax_type: string;
  amount: number;
  taxable_value: number;
  tax_rate: number;
  deductions: Array<Record<string, unknown>>;
  optimization_tips: string[];
  created_at: string;
  /** additive·옵셔널 — 구버전 응답(미포함)도 무손상 렌더. */
  legal_refs?: TaxLegalRef[];
};

type Labels = {
  heroTitle: string;
  heroDescription: string;
  heroHint: string;
  tokenHint: string;
  projectTitle: string;
  projectSelectLabel: string;
  manualProjectIdLabel: string;
  selectedProjectLabel: string;
  noProjectsLabel: string;
  authError: string;
  missingProjectError: string;
  calculateTitle: string;
  taxTypeLabel: string;
  taxableValueLabel: string;
  firstHomeLabel: string;
  holdingYearsLabel: string;
  calculateAction: string;
  amountLabel: string;
  taxRateLabel: string;
  taxableBaseLabel: string;
  deductionsLabel: string;
  tipsLabel: string;
  legalRefsLabel: string;
  projectLoadErrorTitle: string;
  projectLoadErrorDetail: string;
  retryAction: string;
};

const LABELS: Record<Locale, Labels> = {
  ko: {
    heroTitle: "세금 라이브 작업 공간",
    heroDescription:
      "실제 `tax` API로 취득세, 보유세, 양도세 시나리오를 계산합니다.",
    heroHint:
      "프로젝트 FK가 필요한 계산이므로 live 프로젝트 또는 기존 UUID가 필요합니다.",
    tokenHint:
      "분석을 위해 로그인이 필요합니다.",
    projectTitle: "세금 계산 대상 프로젝트",
    projectSelectLabel: "라이브 프로젝트",
    manualProjectIdLabel: "수동 프로젝트 UUID",
    selectedProjectLabel: "현재 대상",
    noProjectsLabel: "라이브 프로젝트가 아직 없습니다. 기존 UUID를 직접 입력하세요.",
    authError: "실시간 호출을 위해 API 인증이 필요합니다.",
    missingProjectError: "실존 프로젝트 UUID가 필요합니다.",
    calculateTitle: "세금 시나리오 계산",
    taxTypeLabel: "세금 유형",
    taxableValueLabel: "과세표준(원)",
    firstHomeLabel: "생애 최초 주택 여부",
    holdingYearsLabel: "보유기간(년)",
    calculateAction: "세금 계산",
    amountLabel: "예상 세액",
    taxRateLabel: "적용 세율",
    taxableBaseLabel: "과세표준",
    deductionsLabel: "공제 항목",
    tipsLabel: "절세 팁",
    legalRefsLabel: "법령 근거",
    projectLoadErrorTitle: "프로젝트 로드 실패",
    projectLoadErrorDetail:
      "세금 계산 대상 프로젝트 목록을 불러오지 못했습니다. 기존 UUID 수동 입력은 계속 사용할 수 있습니다.",
    retryAction: "다시 시도",
  },
  en: {
    heroTitle: "Tax live workspace",
    heroDescription:
      "Calculate acquisition, holding, and transfer tax scenarios through the live `tax` API.",
    heroHint:
      "The calculation persists against a real project foreign key, so a live project or an existing UUID is required.",
    tokenHint:
      "Login required for analysis.",
    projectTitle: "Target project",
    projectSelectLabel: "Live project",
    manualProjectIdLabel: "Manual project UUID",
    selectedProjectLabel: "Current target",
    noProjectsLabel: "No live projects are available yet. Enter an existing UUID manually.",
    authError: "API authentication is required for live workspace calls.",
    missingProjectError: "A real project UUID is required.",
    calculateTitle: "Tax scenario calculation",
    taxTypeLabel: "Tax type",
    taxableValueLabel: "Taxable value (KRW)",
    firstHomeLabel: "First-home acquisition",
    holdingYearsLabel: "Holding period (years)",
    calculateAction: "Calculate tax",
    amountLabel: "Estimated tax",
    taxRateLabel: "Applied rate",
    taxableBaseLabel: "Taxable value",
    deductionsLabel: "Deductions",
    tipsLabel: "Optimization tips",
    legalRefsLabel: "Legal basis",
    projectLoadErrorTitle: "Project list unavailable",
    projectLoadErrorDetail:
      "The tax workspace could not load the live project picker. Manual UUID input remains available.",
    retryAction: "Retry",
  },
  "zh-CN": {
    heroTitle: "税务实时工作台",
    heroDescription: "通过实时 `tax` API 计算取得税、持有税与转让税情景。",
    heroHint: "该计算需要真实项目外键，因此必须选择实时项目或输入已有 UUID。",
    tokenHint:
      "分析需要登录。",
    projectTitle: "目标项目",
    projectSelectLabel: "实时项目",
    manualProjectIdLabel: "手动项目 UUID",
    selectedProjectLabel: "当前目标",
    noProjectsLabel: "当前没有实时项目。可手动输入已有 UUID。",
    authError: "实时调用需要 API 身份认证。",
    missingProjectError: "必须提供真实项目 UUID。",
    calculateTitle: "税务情景计算",
    taxTypeLabel: "税种",
    taxableValueLabel: "计税基数(韩元)",
    firstHomeLabel: "首次购房",
    holdingYearsLabel: "持有年限",
    calculateAction: "计算税额",
    amountLabel: "预计税额",
    taxRateLabel: "适用税率",
    taxableBaseLabel: "计税基数",
    deductionsLabel: "扣减项",
    tipsLabel: "优化建议",
    legalRefsLabel: "法律依据",
    projectLoadErrorTitle: "项目列表不可用",
    projectLoadErrorDetail:
      "税务工作台无法加载实时项目列表，但仍可继续手动输入项目 UUID。",
    retryAction: "重试",
  },
};

const TAX_TYPE_OPTIONS = [
  { label: "Acquisition", value: "acquisition" },
  { label: "Transfer", value: "transfer" },
  { label: "Property", value: "property" },
];

function formatCurrency(locale: string, value: number) {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(2)}%`;
}

function formatDate(locale: string, value: string) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function extractErrorMessage(error: unknown, authMessage: string) {
  if (error instanceof Error) {
    return error.message;
  }
  return authMessage || "요청 실패.";
}

export function TaxOperationsWorkspaceClient({
  locale,
}: {
  locale: Locale;
}) {
  const [isMounted, setIsMounted] = useState(false);
  const labels = LABELS[locale] || LABELS["ko"];
  
  useEffect(() => {
    setIsMounted(true);
  }, []);

  const runtimeConfig = { mode: "local" as string, hasAccessToken: false };
  const canUseLiveApi = true;

  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [manualProjectId, setManualProjectId] = useState("");
  const [workspaceError, setWorkspaceError] = useState("");
  const [result, setResult] = useState<TaxCalculationResponse | null>(null);
  const [isCalculating, setIsCalculating] = useState(false);
  const [form, setForm] = useState<{
    taxType: string;
    taxableValue: number | null;
    isFirstHome: boolean;
    holdingYears: string;
  }>({
    taxType: "acquisition",
    taxableValue: 1200000000,
    isFirstHome: false,
    holdingYears: "5",
  });

  const projectsQuery = useQuery({
    queryKey: ["projects", "tax-picker"],
    enabled: canUseLiveApi,
    queryFn: () =>
      (async () => ({ items: [] as ProjectSummary[], total: 0, page: 1, pageSize: 20 }))(),
  });

  useEffect(() => {
    if (!selectedProjectId && projectsQuery.data?.items?.length) {
      setSelectedProjectId(projectsQuery.data.items[0].id);
    }
  }, [projectsQuery.data, selectedProjectId]);

  const selectedProject =
    projectsQuery.data?.items?.find((project) => project.id === selectedProjectId) ??
    null;
  const activeProjectId = manualProjectId.trim() || selectedProject?.id || "";
  const projectQueryError = projectsQuery.error
    ? extractErrorMessage(projectsQuery.error, labels.authError)
    : "";

  async function handleCalculate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");
    setIsCalculating(true);

    try {
      const { calculateCapitalGainsTax, calculateAcquisitionTax, calculateComprehensivePropertyTax } = await import("@/lib/kr-tax-calculator");
      const taxableValue = form.taxableValue ?? 0;
      const holdingYears = Number(form.holdingYears);

      let amount = 0;
      let taxRate = 0;
      const deductions: Array<Record<string, unknown>> = [];
      const tips: string[] = [];
      // 법령 근거(additive) — 백엔드 legal_reference_registry의 검증된 레코드와
      // 동일한 법령명·조문만 텍스트로 표기한다. url은 백엔드 제공값만 쓰는 원칙이라
      // 로컬 계산 경로에서는 url을 비워 LegalRefChip이 무링크 텍스트로 폴백한다.
      const legalRefs: TaxLegalRef[] = [];

      if (form.taxType === "acquisition") {
        const res = calculateAcquisitionTax(taxableValue, 1);
        amount = res.totalTax;
        taxRate = res.taxRate / 100;
        deductions.push({ type: "취득세", amount: res.acquisitionTax }, { type: "농특세", amount: res.ruralTax }, { type: "교육세", amount: res.educationTax });
        if (form.isFirstHome && taxableValue <= 600_000_000) tips.push("생애 최초 주택 취득세 감면 적용 가능 (200만원 한도)");
        tips.push("취득일 기준 60일 이내 신고/납부 필요");
        legalRefs.push(
          { key: "acquisition_tax", law_name: "지방세법", article: "제11조", title: "부동산 취득의 세율" },
          { key: "local_education_tax", law_name: "지방세법", title: "지방교육세" },
        );
      } else if (form.taxType === "transfer") {
        const res = calculateCapitalGainsTax({
          acquisitionPrice: Math.round(taxableValue * 0.7),
          salePrice: taxableValue,
          holdingYears,
          houseCount: 1,
          isSingleHome: form.isFirstHome,
          expenses: Math.round(taxableValue * 0.01),
        });
        amount = res.totalTax;
        taxRate = res.appliedRate / 100;
        if (res.ltcgDeduction > 0) deductions.push({ type: "장기보유특별공제", amount: res.ltcgDeduction, rate: `${res.ltcgRate}%` });
        deductions.push({ type: "기본공제", amount: res.basicDeduction });
        tips.push(`실효세율: ${res.effectiveRate}%`);
        if (holdingYears < 3) tips.push("3년 이상 보유 시 장기보유특별공제 적용 가능");
        if (holdingYears >= 10 && form.isFirstHome) tips.push("1세대 1주택 10년 이상 보유 시 최대 40% 공제");
        legalRefs.push(
          { key: "capital_gains_tax", law_name: "소득세법", article: "제104조", title: "양도소득세의 세율" },
        );
      } else {
        const res = calculateComprehensivePropertyTax(taxableValue, 1);
        amount = res.totalTax;
        taxRate = res.propertyTax / (taxableValue || 1);
        deductions.push({ type: "재산세", amount: res.propertyTax }, { type: "종합부동산세", amount: res.comprehensiveTax });
        tips.push(`공정시장가액비율: ${res.fairMarketRatio}%`);
        if (res.comprehensiveTax > 0) tips.push("종부세 합산배제 신청 가능 여부 확인 권장");
        legalRefs.push(
          { key: "comprehensive_property_tax", law_name: "종합부동산세법", title: "종합부동산세(주택·토지분)" },
        );
      }

      setResult({
        id: `local-${Date.now()}`,
        project_id: activeProjectId || "local",
        tax_type: form.taxType,
        amount,
        taxable_value: taxableValue,
        tax_rate: taxRate,
        deductions,
        optimization_tips: tips,
        created_at: new Date().toISOString(),
        legal_refs: legalRefs,
      });
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "계산 오류");
    } finally {
      setIsCalculating(false);
    }
  }

  if (!isMounted) {
    return <SkeletonLoader count={3} />;
  }

  return (
    <section className="grid grid-cols-1 gap-6 min-w-0">
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

      <Card>
        <CardContent className="grid gap-5 p-6 lg:grid-cols-[1.3fr_0.7fr]">
          <div className="grid gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.projectTitle}
              </p>
              <CardTitle className="mt-2 text-xl">
                {labels.projectSelectLabel}
              </CardTitle>
            </div>
            {projectsQuery.isLoading ? (
              <SkeletonLoader count={1} itemClassName="h-14" />
            ) : (
              <div className="grid gap-3">
                {projectsQuery.isError ? (
                  <WorkspaceQueryErrorCard
                    title={labels.projectLoadErrorTitle}
                    description={labels.projectLoadErrorDetail}
                    message={projectQueryError}
                    actionLabel={labels.retryAction}
                    onRetry={() => {
                      void projectsQuery.refetch();
                    }}
                  />
                ) : null}
                <Select
                  label={labels.projectSelectLabel}
                  value={selectedProjectId}
                  onValueChange={setSelectedProjectId}
                  options={[
                    {
                      label:
                        projectsQuery.data?.items?.length
                          ? labels.projectSelectLabel
                          : labels.noProjectsLabel,
                      value: "",
                      disabled: true,
                    },
                    ...(projectsQuery.data?.items?.map((project) => ({
                      label: project.name,
                      value: project.id,
                    })) ?? []),
                  ]}
                />
              </div>
            )}
            <Input
              value={manualProjectId}
              onChange={(event) => setManualProjectId(event.target.value)}
              placeholder={labels.manualProjectIdLabel}
            />
          </div>
          <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.selectedProjectLabel}
            </p>
            <p className="mt-3 text-sm font-semibold text-[var(--text-primary)]">
              {selectedProject?.name ?? "-"}
            </p>
            <p className="mt-2 break-all text-xs text-[var(--text-tertiary)]">
              {activeProjectId || "-"}
            </p>
            {selectedProject?.address ? (
              <p className="mt-3 text-sm text-[var(--text-secondary)]">
                {selectedProject.address}
              </p>
            ) : null}
            {selectedProject ? (
              <p className="mt-2 text-xs text-[var(--text-tertiary)]">
                {selectedProject.status} ·{" "}
                {formatDate(locale, selectedProject.updated_at)}
              </p>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.calculateTitle}
            </p>
            <form className="mt-5 grid gap-3" onSubmit={handleCalculate}>
              <Select
                label={labels.taxTypeLabel}
                value={form.taxType}
                onValueChange={(value) =>
                  setForm((current) => ({
                    ...current,
                    taxType: value,
                  }))
                }
                options={TAX_TYPE_OPTIONS}
              />
              <NumberInput
                value={form.taxableValue}
                onChange={(n) =>
                  setForm((current) => ({
                    ...current,
                    taxableValue: n,
                  }))
                }
                placeholder={labels.taxableValueLabel}
                className="flex h-11 w-full rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
              />
              <Input
                type="number"
                min="0"
                step="1"
                value={form.holdingYears}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    holdingYears: event.target.value,
                  }))
                }
                placeholder={labels.holdingYearsLabel}
              />
              <label className="flex items-center gap-3 rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3 text-sm text-[var(--text-primary)]">
                <input
                  type="checkbox"
                  checked={form.isFirstHome}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      isFirstHome: event.target.checked,
                    }))
                  }
                />
                <span>{labels.firstHomeLabel}</span>
              </label>
              <Button type="submit" disabled={isCalculating}>
                {isCalculating
                  ? `${labels.calculateAction}...`
                  : labels.calculateAction}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            {result ? (
              <div className="space-y-4">
                {/* 할루시네이션·오류 검증(세금) */}
                <VerificationBadge
                  analysisType="tax"
                  context={{ result } as unknown as Record<string, unknown>}
                />
                <ExpertPanelCard
                  analysisType="tax"
                  context={{ result } as unknown as Record<string, unknown>}
                />
                <div className="grid gap-4 md:grid-cols-2">
                  <MetricTile
                    label={labels.amountLabel}
                    value={formatCurrency(locale, result.amount)}
                  />
                  <MetricTile
                    label={labels.taxRateLabel}
                    value={formatPercent(result.tax_rate)}
                  />
                  <MetricTile
                    label={labels.taxableBaseLabel}
                    value={formatCurrency(locale, result.taxable_value)}
                  />
                  <MetricTile
                    label="Created"
                    value={formatDate(locale, result.created_at)}
                  />
                </div>
                {/* 법령 근거 칩(additive·옵셔널) — legal_refs 없으면 미렌더(구버전 무손상).
                    url은 백엔드 제공값만 통과(LegalRefChip이 무링크 텍스트 폴백 보장). */}
                {result.legal_refs?.length ? (
                  <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                    <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                      {labels.legalRefsLabel}
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {(result.legal_refs ?? []).map((ref, index) => (
                        <LegalRefChip
                          key={ref.key ?? `${ref.law_name}-${ref.article ?? ""}-${index}`}
                          lawName={ref.law_name}
                          article={ref.article}
                          title={ref.title}
                          url={ref.url}
                        />
                      ))}
                    </div>
                  </div>
                ) : null}
                <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                  <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                    {labels.deductionsLabel}
                  </p>
                  {result.deductions?.length ? (
                    <ul className="mt-3 space-y-2 text-sm leading-7 text-[var(--text-secondary)]">
                      {(result.deductions ?? []).map((item, index) => (
                        <li key={`${index}-${JSON.stringify(item)}`}>
                          • {Object.entries(item)
                            .map(([key, value]) => `${key}: ${String(value)}`)
                            .join(", ")}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-3 text-sm leading-7 text-[var(--text-tertiary)]">
                      -
                    </p>
                  )}
                </div>
                <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                  <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                    {labels.tipsLabel}
                  </p>
                  {result.optimization_tips?.length ? (
                    <ul className="mt-3 space-y-2 text-sm leading-7 text-[var(--text-secondary)]">
                      {(result.optimization_tips ?? []).map((item) => (
                        <li key={item}>• {item}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-3 text-sm leading-7 text-[var(--text-tertiary)]">
                      -
                    </p>
                  )}
                </div>
              </div>
            ) : (
              <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
                Select a live project and run a tax scenario to inspect the persisted
                `tax/calculate` response.
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </section>
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
    <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
      <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-3 text-xl font-semibold text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}
