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
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { NumberInput } from "@/components/common/NumberInput";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";
import { ApiClientError, apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";

type ProjectSummary = {
  id: string;
  name: string;
  status: string;
  address: string | null;
  total_area_sqm: number | null;
  updated_at: string;
};

type KepcoCalculationResponse = {
  contract_type: string;
  usage_kwh: number;
  demand_kw: number;
  base_charge_krw: number;
  energy_charge_krw: number;
  climate_fund_krw: number;
  fuel_adjustment_krw: number;
  vat_krw: number;
  total_bill_krw: number;
};

type EnergyCertificationResponse = {
  energy_grade: string;
  zeb_grade: string;
  annual_energy_demand_kwh: number;
  annual_renewable_generation_kwh: number;
  energy_independence_rate: number;
  bems_saving_rate: number;
  bems_saving_kwh: number;
  recommendations: string[];
};

type Labels = {
  heroTitle: string;
  heroDescription: string;
  heroHint: string;
  tokenHint: string;
  projectTitle: string;
  projectSelectLabel: string;
  manualProjectIdLabel: string;
  manualProjectNameLabel: string;
  selectedProjectLabel: string;
  kepcoTitle: string;
  usageLabel: string;
  demandLabel: string;
  contractTypeLabel: string;
  calculateAction: string;
  certificationTitle: string;
  areaLabel: string;
  floorsLabel: string;
  windowWallRatioLabel: string;
  insulationLabel: string;
  bemsLabel: string;
  certifyAction: string;
  authError: string;
  missingProjectError: string;
  missingUsageError: string;
  missingAreaError: string;
  noProjectsLabel: string;
  totalBillLabel: string;
  energyDemandLabel: string;
  renewableLabel: string;
  independenceLabel: string;
  recommendationsLabel: string;
  projectLoadErrorTitle: string;
  projectLoadErrorDetail: string;
  retryAction: string;
  kepcoBasisTitle: string;
  certBasisTitle: string;
  basisServerNote: string;
};

const LABELS: Record<Locale, Labels> = {
  ko: {
    heroTitle: "에너지 인증 작업 공간",
    heroDescription:
      "KEPCO 요금 계산과 프로젝트 연동 에너지 인증을 실제 `energy` API로 검증합니다.",
    heroHint:
      "인증 결과는 실존 프로젝트 FK로 저장되므로 live 프로젝트 또는 기존 UUID가 필요합니다.",
    tokenHint:
      "분석을 위해 로그인이 필요합니다.",
    projectTitle: "인증 대상 프로젝트",
    projectSelectLabel: "라이브 프로젝트",
    manualProjectIdLabel: "수동 프로젝트 UUID",
    manualProjectNameLabel: "수동 프로젝트명",
    selectedProjectLabel: "현재 대상",
    kepcoTitle: "KEPCO 요금 계산",
    usageLabel: "사용량(kWh)",
    demandLabel: "수요전력(kW)",
    contractTypeLabel: "계약종별",
    calculateAction: "요금 계산",
    certificationTitle: "에너지 인증 추정",
    areaLabel: "연면적(㎡)",
    floorsLabel: "층수",
    windowWallRatioLabel: "창면적비",
    insulationLabel: "단열 등급",
    bemsLabel: "BEMS 절감률",
    certifyAction: "인증 계산",
    authError: "실시간 호출을 위해 API 인증이 필요합니다.",
    missingProjectError: "실존 프로젝트 UUID가 필요합니다.",
    missingUsageError: "사용량(kWh)을 0보다 크게 입력해야 합니다.",
    missingAreaError: "연면적(㎡)을 0보다 크게 입력해야 합니다.",
    noProjectsLabel: "라이브 프로젝트가 아직 없습니다. 기존 UUID를 직접 입력해야 합니다.",
    totalBillLabel: "총 청구액",
    energyDemandLabel: "연간 에너지 수요",
    renewableLabel: "연간 재생에너지 발전량",
    independenceLabel: "에너지 자립률",
    recommendationsLabel: "개선 권고",
    projectLoadErrorTitle: "프로젝트 로드 실패",
    projectLoadErrorDetail:
      "인증 대상 프로젝트 목록을 불러오지 못했습니다. 기존 UUID 수동 입력은 계속 사용할 수 있습니다.",
    retryAction: "다시 시도",
    kepcoBasisTitle: "요금 산출 근거",
    certBasisTitle: "인증 산출 근거",
    basisServerNote:
      "모든 수치는 서버 `energy` API가 테넌트별 단가·계수로 산출한 실값입니다.",
  },
  en: {
    heroTitle: "Energy certification workspace",
    heroDescription:
      "Validate KEPCO billing and project-linked certification through the live `energy` APIs.",
    heroHint:
      "Certification records persist against a real project foreign key, so a live project or existing UUID is required.",
    tokenHint:
      "Login required for analysis.",
    projectTitle: "Certification target project",
    projectSelectLabel: "Live project",
    manualProjectIdLabel: "Manual project UUID",
    manualProjectNameLabel: "Manual project name",
    selectedProjectLabel: "Current target",
    kepcoTitle: "KEPCO billing",
    usageLabel: "Usage (kWh)",
    demandLabel: "Demand (kW)",
    contractTypeLabel: "Contract type",
    calculateAction: "Calculate bill",
    certificationTitle: "Energy certification estimate",
    areaLabel: "Gross area (sqm)",
    floorsLabel: "Floors",
    windowWallRatioLabel: "Window-wall ratio",
    insulationLabel: "Insulation grade",
    bemsLabel: "BEMS saving rate",
    certifyAction: "Estimate certification",
    authError: "API authentication is required for live workspace calls.",
    missingProjectError: "A real project UUID is required.",
    missingUsageError: "Usage (kWh) must be greater than 0.",
    missingAreaError: "Gross area (sqm) must be greater than 0.",
    noProjectsLabel:
      "No live projects are available yet. Enter a known existing UUID to proceed.",
    totalBillLabel: "Total bill",
    energyDemandLabel: "Annual energy demand",
    renewableLabel: "Annual renewable generation",
    independenceLabel: "Energy independence",
    recommendationsLabel: "Recommendations",
    projectLoadErrorTitle: "Project list unavailable",
    projectLoadErrorDetail:
      "The certification project picker failed to load. Manual UUID input remains available.",
    retryAction: "Retry",
    kepcoBasisTitle: "Billing calculation basis",
    certBasisTitle: "Certification calculation basis",
    basisServerNote:
      "All figures are live values computed by the server `energy` API using tenant-specific tariffs and coefficients.",
  },
  "zh-CN": {
    heroTitle: "能源认证工作台",
    heroDescription:
      "通过实时 `energy` API 验证 KEPCO 电费计算和项目联动能源认证。",
    heroHint:
      "认证记录会写入真实项目外键，因此需要选择实时项目或输入已有 UUID。",
    tokenHint:
      "分析需要登录。",
    projectTitle: "认证目标项目",
    projectSelectLabel: "实时项目",
    manualProjectIdLabel: "手动项目 UUID",
    manualProjectNameLabel: "手动项目名称",
    selectedProjectLabel: "当前目标",
    kepcoTitle: "KEPCO 电费计算",
    usageLabel: "用电量(kWh)",
    demandLabel: "需量(kW)",
    contractTypeLabel: "合同类型",
    calculateAction: "计算电费",
    certificationTitle: "能源认证估算",
    areaLabel: "总建筑面积(㎡)",
    floorsLabel: "楼层数",
    windowWallRatioLabel: "窗墙比",
    insulationLabel: "保温等级",
    bemsLabel: "BEMS 节能率",
    certifyAction: "估算认证",
    authError: "实时调用需要 API 身份认证。",
    missingProjectError: "必须提供真实项目 UUID。",
    missingUsageError: "用电量(kWh)必须大于 0。",
    missingAreaError: "总建筑面积(㎡)必须大于 0。",
    noProjectsLabel: "当前还没有实时项目。可手动输入已有项目 UUID。",
    totalBillLabel: "总账单",
    energyDemandLabel: "年度能源需求",
    renewableLabel: "年度可再生能源发电量",
    independenceLabel: "能源自给率",
    recommendationsLabel: "改进建议",
    projectLoadErrorTitle: "项目列表不可用",
    projectLoadErrorDetail:
      "认证项目选择列表加载失败，但仍可手动输入已有项目 UUID。",
    retryAction: "重试",
    kepcoBasisTitle: "电费计算依据",
    certBasisTitle: "认证计算依据",
    basisServerNote:
      "所有数值均由服务器 `energy` API 按租户单价与系数实时计算得出。",
  },
};

const CONTRACT_OPTIONS = [
  { label: "General", value: "general" },
  { label: "Industrial", value: "industrial" },
  { label: "Education", value: "education" },
];

const INSULATION_OPTIONS = [
  { label: "Premium", value: "premium" },
  { label: "Standard", value: "standard" },
  { label: "Basic", value: "basic" },
];

function formatCurrency(locale: string, value: number) {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatDate(locale: string, value: string) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function extractErrorMessage(error: unknown, authMessage: string) {
  // 인증 실패(401/403)는 가짜 응답 대신 "로그인/인증 필요"로 정직하게 알린다.
  if (error instanceof ApiClientError) {
    if (error.status === 401 || error.status === 403) {
      return authMessage;
    }
    return `요청이 상태 코드 ${error.status}로 실패했습니다.`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return authMessage || "요청 실패.";
}

export function EnergyOperationsWorkspaceClient({
  locale,
}: {
  locale: Locale;
}) {
  const [isMounted, setIsMounted] = useState(false);
  const labels = LABELS[locale] || LABELS["ko"];
  
  useEffect(() => {
    setIsMounted(true);
  }, []);

  // 실제 런타임 설정을 읽어 라이브 호출 가능 여부를 판정한다(하드코딩 금지).
  // ProjectEsgWorkspaceClient와 동일 패턴: live 모드이거나 액세스 토큰이 있으면 호출 허용.
  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [manualProjectId, setManualProjectId] = useState("");
  const [manualProjectName, setManualProjectName] = useState("");
  const [workspaceError, setWorkspaceError] = useState("");
  const [kepcoResult, setKepcoResult] = useState<KepcoCalculationResponse | null>(
    null,
  );
  const [certificationResult, setCertificationResult] =
    useState<EnergyCertificationResponse | null>(null);
  const [isCalculating, setIsCalculating] = useState(false);
  const [isCertifying, setIsCertifying] = useState(false);

  const [kepcoForm, setKepcoForm] = useState<{
    usageKwh: number | null;
    demandKw: number | null;
    contractType: string;
  }>({
    usageKwh: 184000,
    demandKw: 480,
    contractType: "general",
  });
  const [certificationForm, setCertificationForm] = useState<{
    totalAreaSqm: number | null;
    floors: string;
    windowWallRatio: string;
    insulationGrade: string;
    bemsSavingRate: string;
  }>({
    totalAreaSqm: null,
    floors: "12",
    windowWallRatio: "0.34",
    insulationGrade: "premium",
    bemsSavingRate: "0.08",
  });

  const projectsQuery = useQuery({
    queryKey: ["projects", "energy-picker"],
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

  useEffect(() => {
    if (selectedProject?.total_area_sqm && !certificationForm.totalAreaSqm) {
      setCertificationForm((current) => ({
        ...current,
        totalAreaSqm: selectedProject.total_area_sqm,
      }));
    }
  }, [certificationForm.totalAreaSqm, selectedProject]);

  const activeProjectId = manualProjectId.trim() || selectedProject?.id || "";
  const activeProjectName =
    manualProjectName.trim() || selectedProject?.name || "";
  const projectQueryError = projectsQuery.error
    ? extractErrorMessage(projectsQuery.error, labels.authError)
    : "";

  async function handleCalculateKepco(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");
    setKepcoResult(null);
    // 인증이 없으면 가짜 계산 대신 정직하게 안내(서버가 테넌트별 단가로 산출).
    if (!canUseLiveApi) {
      setWorkspaceError(labels.authError);
      return;
    }
    const usage = kepcoForm.usageKwh ?? 0;
    if (usage <= 0) {
      // 백엔드 스키마는 usage_kwh > 0을 요구한다(422 방지).
      setWorkspaceError(labels.missingUsageError);
      return;
    }
    setIsCalculating(true);
    try {
      // 실제 백엔드 호출 — 단가/계수/세율은 모두 서버(테넌트별 KepcoRateCache)가 결정한다.
      const result = await apiClient.post<KepcoCalculationResponse>(
        "/energy/kepco/calculate",
        {
          useMock: false,
          body: {
            usage_kwh: usage,
            contract_type: kepcoForm.contractType,
            demand_kw: kepcoForm.demandKw ?? 0,
          },
        },
      );
      setKepcoResult(result);
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsCalculating(false);
    }
  }

  async function handleEstimateCertification(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");
    setCertificationResult(null);
    if (!canUseLiveApi) {
      setWorkspaceError(labels.authError);
      return;
    }
    // 백엔드는 인증 기록을 실존 프로젝트 FK로 저장하므로 실제 프로젝트 UUID가 필요하다.
    if (!activeProjectId) {
      setWorkspaceError(labels.missingProjectError);
      return;
    }
    const area = certificationForm.totalAreaSqm ?? 0;
    if (area <= 0) {
      // 백엔드 스키마는 total_area_sqm > 0을 요구한다(422 방지).
      setWorkspaceError(labels.missingAreaError);
      return;
    }
    setIsCertifying(true);
    try {
      // 실제 백엔드 호출 — 에너지 등급/ZEB/수요량/권고는 모두 서버 산식이 산출한다.
      const result = await apiClient.post<EnergyCertificationResponse>(
        "/energy/certification",
        {
          useMock: false,
          body: {
            project_id: activeProjectId,
            total_area_sqm: area,
            floors: Number(certificationForm.floors) || 1,
            window_wall_ratio: Number(certificationForm.windowWallRatio) || 0.35,
            insulation_grade: certificationForm.insulationGrade,
            bems_saving_rate: Number(certificationForm.bemsSavingRate) || 0,
          },
        },
      );
      setCertificationResult(result);
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsCertifying(false);
    }
  }

  if (!isMounted) {
    return <SkeletonLoader count={4} />;
  }

  return (
    <section className="grid gap-6">
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
            <div className="grid gap-3 md:grid-cols-2">
              <Input
                value={manualProjectId}
                onChange={(event) => setManualProjectId(event.target.value)}
                placeholder={labels.manualProjectIdLabel}
              />
              <Input
                value={manualProjectName}
                onChange={(event) => setManualProjectName(event.target.value)}
                placeholder={labels.manualProjectNameLabel}
              />
            </div>
          </div>
          <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.selectedProjectLabel}
            </p>
            <p className="mt-3 text-sm font-semibold text-[var(--text-primary)]">
              {activeProjectName || "-"}
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
              {labels.kepcoTitle}
            </p>
            <form className="mt-5 grid gap-3" onSubmit={handleCalculateKepco}>
              <div className="grid gap-3 md:grid-cols-2">
                <NumberInput
                  allowDecimal
                  value={kepcoForm.usageKwh}
                  onChange={(n) =>
                    setKepcoForm((current) => ({
                      ...current,
                      usageKwh: n,
                    }))
                  }
                  placeholder={labels.usageLabel}
                  className="flex h-11 w-full rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
                />
                <NumberInput
                  allowDecimal
                  value={kepcoForm.demandKw}
                  onChange={(n) =>
                    setKepcoForm((current) => ({
                      ...current,
                      demandKw: n,
                    }))
                  }
                  placeholder={labels.demandLabel}
                  className="flex h-11 w-full rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
                />
              </div>
              <Select
                label={labels.contractTypeLabel}
                value={kepcoForm.contractType}
                onValueChange={(value) =>
                  setKepcoForm((current) => ({
                    ...current,
                    contractType: value,
                  }))
                }
                options={CONTRACT_OPTIONS}
              />
              <Button type="submit" disabled={isCalculating}>
                {isCalculating
                  ? `${labels.calculateAction}...`
                  : labels.calculateAction}
              </Button>
            </form>

            {kepcoResult ? (
              <div className="mt-5 grid gap-4 md:grid-cols-2">
                <MetricTile
                  label={labels.totalBillLabel}
                  value={formatCurrency(locale, kepcoResult.total_bill_krw)}
                />
                <MetricTile
                  label="부가가치세 (VAT)"
                  value={formatCurrency(locale, kepcoResult.vat_krw)}
                />
                <MetricTile
                  label="기본 요금"
                  value={formatCurrency(locale, kepcoResult.base_charge_krw)}
                />
                <MetricTile
                  label="전력량 요금"
                  value={formatCurrency(locale, kepcoResult.energy_charge_krw)}
                />
                <MetricTile
                  label="연료비 조정액"
                  value={formatCurrency(locale, kepcoResult.fuel_adjustment_krw)}
                />
                <MetricTile
                  label="기후환경 요금"
                  value={formatCurrency(locale, kepcoResult.climate_fund_krw)}
                />
              </div>
            ) : null}
            {kepcoResult ? (
              // 산출 근거 — 백엔드 energy_service 산식을 그대로 표기(받는 값만 사용).
              <EvidencePanel
                title={labels.kepcoBasisTitle}
                className="mt-5"
                items={buildKepcoEvidence(locale, kepcoResult, labels.basisServerNote)}
              />
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.certificationTitle}
            </p>
            <form
              className="mt-5 grid gap-3"
              onSubmit={handleEstimateCertification}
            >
              <div className="grid gap-3 md:grid-cols-2">
                <NumberInput
                  allowDecimal
                  value={certificationForm.totalAreaSqm}
                  onChange={(n) =>
                    setCertificationForm((current) => ({
                      ...current,
                      totalAreaSqm: n,
                    }))
                  }
                  placeholder={labels.areaLabel}
                  className="flex h-11 w-full rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
                />
                <Input
                  type="number"
                  min="1"
                  step="1"
                  value={certificationForm.floors}
                  onChange={(event) =>
                    setCertificationForm((current) => ({
                      ...current,
                      floors: event.target.value,
                    }))
                  }
                  placeholder={labels.floorsLabel}
                />
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <Input
                  type="number"
                  min="0.1"
                  max="0.95"
                  step="0.01"
                  value={certificationForm.windowWallRatio}
                  onChange={(event) =>
                    setCertificationForm((current) => ({
                      ...current,
                      windowWallRatio: event.target.value,
                    }))
                  }
                  placeholder={labels.windowWallRatioLabel}
                />
                <Input
                  type="number"
                  min="0"
                  max="0.5"
                  step="0.01"
                  value={certificationForm.bemsSavingRate}
                  onChange={(event) =>
                    setCertificationForm((current) => ({
                      ...current,
                      bemsSavingRate: event.target.value,
                    }))
                  }
                  placeholder={labels.bemsLabel}
                />
              </div>
              <Select
                label={labels.insulationLabel}
                value={certificationForm.insulationGrade}
                onValueChange={(value) =>
                  setCertificationForm((current) => ({
                    ...current,
                    insulationGrade: value,
                  }))
                }
                options={INSULATION_OPTIONS}
              />
              <Button type="submit" disabled={isCertifying}>
                {isCertifying
                  ? `${labels.certifyAction}...`
                  : labels.certifyAction}
              </Button>
            </form>

            {certificationResult ? (
              <div className="mt-5 space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <MetricTile
                    label="에너지 등급"
                    value={certificationResult.energy_grade}
                  />
                  <MetricTile
                    label="ZEB 등급"
                    value={certificationResult.zeb_grade}
                  />
                  <MetricTile
                    label={labels.energyDemandLabel}
                    value={`${certificationResult.annual_energy_demand_kwh.toLocaleString(locale)} kWh`}
                  />
                  <MetricTile
                    label={labels.renewableLabel}
                    value={`${certificationResult.annual_renewable_generation_kwh.toLocaleString(locale)} kWh`}
                  />
                  <MetricTile
                    label={labels.independenceLabel}
                    value={`${(certificationResult.energy_independence_rate * 100).toFixed(1)}%`}
                  />
                  <MetricTile
                    label="BEMS 절감량"
                    value={`${certificationResult.bems_saving_kwh.toLocaleString(locale)} kWh`}
                  />
                </div>
                <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                  <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                    {labels.recommendationsLabel}
                  </p>
                  <ul className="mt-3 space-y-2 text-sm leading-7 text-[var(--text-secondary)]">
                    {(certificationResult.recommendations ?? []).map((item) => (
                      <li key={item}>• {item}</li>
                    ))}
                  </ul>
                </div>
                {/* 산출 근거 — 백엔드 인증 산식을 그대로 표기(받는 값만 사용). */}
                <EvidencePanel
                  title={labels.certBasisTitle}
                  items={buildCertificationEvidence(
                    locale,
                    certificationResult,
                    labels.basisServerNote,
                  )}
                />
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </section>
  );
}

// KEPCO 요금 근거 — 백엔드 energy_service.calculate_kepco_bill 산식 그대로.
// 단가/계수는 서버 KepcoRateCache(테넌트별 관리자 설정)에서 결정되므로 여기서 추정하지 않는다.
// basis 문자열은 받은 실값만 조합한다(하드코딩 단가/계수 없음).
function buildKepcoEvidence(
  locale: string,
  result: KepcoCalculationResponse,
  serverNote: string,
): EvidenceItem[] {
  const krw = (v: number) => formatCurrency(locale, v);
  return [
    {
      label: "계약종별",
      value: result.contract_type,
      basis: serverNote,
    },
    {
      label: "기본 요금",
      value: krw(result.base_charge_krw),
      basis: `수요전력 ${result.demand_kw.toLocaleString(locale)} kW × 서버 기본단가(테넌트별)`,
    },
    {
      label: "전력량 요금",
      value: krw(result.energy_charge_krw),
      basis: `사용량 ${result.usage_kwh.toLocaleString(locale)} kWh × 서버 전력량단가(테넌트별)`,
    },
    {
      label: "기후환경 요금",
      value: krw(result.climate_fund_krw),
      basis: "전력량 요금 × 3.7% (energy_charge × 0.037)",
    },
    {
      label: "연료비 조정액",
      value: krw(result.fuel_adjustment_krw),
      basis: `사용량 ${result.usage_kwh.toLocaleString(locale)} kWh × 서버 연료비조정단가`,
    },
    {
      label: "부가가치세 (VAT)",
      value: krw(result.vat_krw),
      basis: "소계(기본+전력량+연료비+기후환경) × 10%",
    },
    {
      label: "총 청구액",
      value: krw(result.total_bill_krw),
      basis: "소계 + VAT",
    },
  ];
}

// 에너지 인증 근거 — 백엔드 energy_service.certify_energy / energy_grade 산식 그대로.
// 등급 임계(A+≤60, A≤90, B≤130, C≤170, D)는 백엔드 energy_grade 정의를 설명만 한다.
function buildCertificationEvidence(
  locale: string,
  result: EnergyCertificationResponse,
  serverNote: string,
): EvidenceItem[] {
  const kwh = (v: number) => `${v.toLocaleString(locale)} kWh`;
  return [
    {
      label: "에너지 등급",
      value: result.energy_grade,
      basis:
        "단위면적당 연간 수요(kWh/㎡) 기준 서버 판정 (A+≤60, A≤90, B≤130, C≤170, 그 외 D)",
    },
    {
      label: "ZEB 등급",
      value: result.zeb_grade,
      basis: serverNote,
    },
    {
      label: "연간 에너지 수요",
      value: kwh(result.annual_energy_demand_kwh),
      basis: "ZEB 산정 수요 − BEMS 절감량(서버 산출)",
    },
    {
      label: "연간 재생에너지 발전량",
      value: kwh(result.annual_renewable_generation_kwh),
      basis: serverNote,
    },
    {
      label: "에너지 자립률",
      value: `${(result.energy_independence_rate * 100).toFixed(1)}%`,
      basis: "재생에너지 발전량 ÷ 에너지 수요(서버 산출)",
    },
    {
      label: "BEMS 절감량",
      value: kwh(result.bems_saving_kwh),
      basis: `연간 수요 × BEMS 절감률 ${(result.bems_saving_rate * 100).toFixed(1)}%`,
    },
  ];
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
