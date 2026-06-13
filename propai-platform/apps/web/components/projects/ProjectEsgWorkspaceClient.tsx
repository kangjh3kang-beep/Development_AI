"use client";

import { useCallback, useState, type FormEvent } from "react";
import { Button, Card, CardContent, CardTitle, Input } from "@propai/ui";
import { ApiClientError, apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useStageAutoRecalc } from "@/hooks/useStageAutoRecalc";
import { AnalysisVerdict } from "@/components/analysis/AnalysisVerdict";
import { ExpertPanelCard } from "@/components/common/ExpertPanelCard";
import { LegalRefChip } from "@/components/common/LegalRefChip";
import { NumberInput } from "@/components/common/NumberInput";
import { SiteDataGate } from "@/components/projects/SiteDataGate";
import type { Locale } from "@/i18n/config";

/* ── Response Types ── */

/** 백엔드 legal_reference_registry 직렬화 레코드 — url은 백엔드 제공값만 사용. */
type LegalRefItem = {
  key: string;
  law_name: string;
  article?: string | null;
  title?: string | null;
  url?: string | null;
  url_status?: string;
};

type LcaCalculationResponse = {
  project_id: string;
  embodied_carbon_kgco2e: number;
  operational_carbon_kgco2e: number;
  total_carbon_kgco2e: number;
  carbon_per_sqm_kgco2e: number;
  floor_area_sqm: number;
  material_breakdown: Array<{
    material: string;
    carbon_kgco2e: number;
    percentage: number;
  }>;
  whole_life?: {
    stages?: Record<string, { gwp_kgco2e: number; label: string; excluded_from_total?: boolean }>;
    embodied_total_kgco2e?: number;
    operational_b6_kgco2e?: number;
    whole_life_total_kgco2e?: number;
    standard?: string;
    basis?: string;
  };
  epd_coverage?: string;
  gwp_basis?: string;
  ai_analysis?: string;
  /** 인증/ZEB 법령 근거(additive) — 구버전 응답에는 없으므로 옵셔널 가드 렌더. */
  legal_refs?: LegalRefItem[];
};

type CarbonFootprintItem = {
  name: string;
  quantity_kg: number;
  carbon_kgco2e: number;
  epd_source?: string;
};

type CarbonFootprintResponse = {
  total_carbon_kgco2e: number;
  items: CarbonFootprintItem[];
  ai_analysis?: string;
};

type LowCarbonAlternative = {
  alternative_name: string;
  carbon_reduction_percent: number;
  carbon_kgco2e: number;
  cost_impact_percent: number;
  description?: string;
};

type LowCarbonAlternativesResponse = {
  original_material: string;
  original_carbon_kgco2e: number;
  alternatives: LowCarbonAlternative[];
  ai_recommendation?: string;
};

/* ── Labels ── */

type Labels = {
  heroTitle: string;
  heroDescription: string;
  heroHint: string;
  tokenHint: string;
  authError: string;
  lcaFormTitle: string;
  floorAreaLabel: string;
  materialNameLabel: string;
  materialQtyLabel: string;
  addMaterialAction: string;
  removeMaterialAction: string;
  submitLcaAction: string;
  lcaResultTitle: string;
  embodiedCarbonLabel: string;
  operationalCarbonLabel: string;
  totalCarbonLabel: string;
  carbonPerSqmLabel: string;
  materialBreakdownLabel: string;
  epdFormTitle: string;
  epdMaterialNameLabel: string;
  epdQuantityLabel: string;
  epdUnitLabel: string;
  submitEpdAction: string;
  epdResultTitle: string;
  epdTotalLabel: string;
  alternativesFormTitle: string;
  altMaterialLabel: string;
  altQuantityLabel: string;
  submitAltAction: string;
  altResultTitle: string;
  altNameLabel: string;
  altReductionLabel: string;
  altCostImpactLabel: string;
  legalRefsLabel: string;
  placeholder: string;
};

const KO_LABELS: Labels = {
  heroTitle: "ESG 분석 라이브 작업 공간",
  heroDescription:
    "전과정 탄소 배출 분석(LCA), EPD 탄소 발자국, 저탄소 대안을 실시간으로 산출합니다.",
  heroHint:
    "LCA 탄소 산출, EPD 기반 탄소 발자국 계산, 저탄소 대체 자재 추천을 연계 수행합니다.",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "라이브 작업 공간 호출을 위해 API 인증이 필요합니다.",
  lcaFormTitle: "전과정 탄소산출(LCA) 입력",
  floorAreaLabel: "연면적 (m2)",
  materialNameLabel: "자재명",
  materialQtyLabel: "수량 (kg)",
  addMaterialAction: "자재 추가",
  removeMaterialAction: "삭제",
  submitLcaAction: "전과정 탄소산출(LCA) 실행",
  lcaResultTitle: "전과정 탄소산출(LCA) 결과",
  embodiedCarbonLabel: "체화 탄소",
  operationalCarbonLabel: "운영 탄소",
  totalCarbonLabel: "총 탄소",
  carbonPerSqmLabel: "m2당 탄소",
  materialBreakdownLabel: "자재별 탄소 배출",
  epdFormTitle: "자재 환경성적(EPD) 탄소 발자국 입력",
  epdMaterialNameLabel: "자재명",
  epdQuantityLabel: "수량 (kg)",
  epdUnitLabel: "단위",
  submitEpdAction: "자재 환경성적(EPD) 탄소 발자국 산출",
  epdResultTitle: "자재 환경성적(EPD) 탄소 발자국 결과",
  epdTotalLabel: "총 탄소 발자국",
  alternativesFormTitle: "저탄소 대안 검색",
  altMaterialLabel: "대상 자재명",
  altQuantityLabel: "수량 (kg)",
  submitAltAction: "저탄소 대안 조회",
  altResultTitle: "저탄소 대안 결과",
  altNameLabel: "대안 자재",
  altReductionLabel: "탄소 저감률",
  altCostImpactLabel: "비용 영향",
  legalRefsLabel: "인증 법령 근거",
  placeholder: "폼을 제출하면 결과가 표시됩니다.",
};

const EN_LABELS: Labels = {
  heroTitle: "ESG analysis live workspace",
  heroDescription:
    "Calculate life-cycle carbon assessment (LCA), EPD carbon footprint, and low-carbon alternatives in real time.",
  heroHint:
    "Chains LCA carbon calculation, EPD-based carbon footprint, and low-carbon material recommendations.",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "API authentication is required for live workspace calls.",
  lcaFormTitle: "LCA carbon calculation input",
  floorAreaLabel: "Floor area (sqm)",
  materialNameLabel: "Material name",
  materialQtyLabel: "Quantity (kg)",
  addMaterialAction: "Add material",
  removeMaterialAction: "Remove",
  submitLcaAction: "Run LCA calculation",
  lcaResultTitle: "LCA carbon calculation results",
  embodiedCarbonLabel: "Embodied carbon",
  operationalCarbonLabel: "Operational carbon",
  totalCarbonLabel: "Total carbon",
  carbonPerSqmLabel: "Carbon per sqm",
  materialBreakdownLabel: "Material carbon breakdown",
  epdFormTitle: "EPD carbon footprint input",
  epdMaterialNameLabel: "Material name",
  epdQuantityLabel: "Quantity (kg)",
  epdUnitLabel: "Unit",
  submitEpdAction: "Calculate EPD footprint",
  epdResultTitle: "EPD carbon footprint results",
  epdTotalLabel: "Total carbon footprint",
  alternativesFormTitle: "Low-carbon alternatives search",
  altMaterialLabel: "Target material",
  altQuantityLabel: "Quantity (kg)",
  submitAltAction: "Find alternatives",
  altResultTitle: "Low-carbon alternatives",
  altNameLabel: "Alternative",
  altReductionLabel: "Carbon reduction",
  altCostImpactLabel: "Cost impact",
  legalRefsLabel: "Certification legal basis",
  placeholder: "Submit the form to see results.",
};

const LABELS: Record<Locale, Labels> = {
  ko: KO_LABELS,
  en: EN_LABELS,
  "zh-CN": KO_LABELS,
};

/* ── Helpers ── */

function formatCarbon(value: number) {
  return `${value.toLocaleString("ko-KR", { maximumFractionDigits: 1 })} kgCO2e`;
}

function formatPercent(value: number) {
  return `${value.toFixed(1)}%`;
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

type MaterialFormItem = { name: string; quantity: string };

/* ── Component ── */

export function ProjectEsgWorkspaceClient({
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

  const updateEsgData = useProjectContextStore((s) => s.updateEsgData);
  const markStageComplete = useProjectContextStore((s) => s.markStageComplete);
  const addAnalysisResult = useProjectContextStore((s) => s.addAnalysisResult);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  // 부지 핵심 입력(면적/주소) 준비 여부 — 없으면 데모 자재값 폼 대신 게이트로 유도(무목업).
  const hasSiteData = !!(
    (siteAnalysis?.landAreaSqm && siteAnalysis.landAreaSqm > 0) ||
    siteAnalysis?.address
  );

  const [workspaceError, setWorkspaceError] = useState("");

  /* LCA state */
  const [isSubmittingLca, setIsSubmittingLca] = useState(false);
  const [lcaResult, setLcaResult] = useState<LcaCalculationResponse | null>(
    null,
  );
  const [floorArea, setFloorArea] = useState("12500");
  const [lcaMaterials, setLcaMaterials] = useState<MaterialFormItem[]>([
    { name: "콘크리트", quantity: "850000" },
    { name: "철근", quantity: "120000" },
    { name: "유리", quantity: "45000" },
  ]);

  /* EPD state */
  const [isSubmittingEpd, setIsSubmittingEpd] = useState(false);
  const [epdResult, setEpdResult] = useState<CarbonFootprintResponse | null>(
    null,
  );
  const [epdMaterials, setEpdMaterials] = useState<
    Array<{ name: string; quantity_kg: string; unit: string }>
  >([
    { name: "콘크리트", quantity_kg: "850000", unit: "kg" },
    { name: "철근", quantity_kg: "120000", unit: "kg" },
  ]);

  /* Alternatives state */
  const [isSubmittingAlt, setIsSubmittingAlt] = useState(false);
  const [altResult, setAltResult] =
    useState<LowCarbonAlternativesResponse | null>(null);
  const [altForm, setAltForm] = useState({
    materialName: "콘크리트",
    quantityKg: "850000",
  });

  /* LCA handlers */
  function addLcaMaterial() {
    setLcaMaterials((c) => [...c, { name: "", quantity: "" }]);
  }
  function removeLcaMaterial(index: number) {
    setLcaMaterials((c) => c.filter((_, i) => i !== index));
  }
  function updateLcaMaterial(
    index: number,
    field: keyof MaterialFormItem,
    value: string,
  ) {
    setLcaMaterials((c) =>
      c.map((m, i) => (i === index ? { ...m, [field]: value } : m)),
    );
  }

  // LCA 핵심 산출(무인자) — 폼 제출과 모세혈관 자동재계산이 공유한다.
  // 현재 입력 state(자재·연면적)를 사용하므로 사용자 수정값이 보존된다.
  const runLca = useCallback(async () => {
    setWorkspaceError("");
    setIsSubmittingLca(true);

    try {
      const materialQuantities: Record<string, number> = {};
      for (const m of lcaMaterials) {
        if (m.name.trim()) {
          materialQuantities[m.name.trim()] = Number(m.quantity) || 0;
        }
      }

      const result = await apiClient.post<LcaCalculationResponse>(
        "/esg/lca/calculate",
        {
          useMock: false,
          body: {
            project_id: projectId,
            material_quantities: materialQuantities,
            floor_area_sqm: Number(floorArea) || 0,
          },
        },
      );
      setLcaResult(result);

      // Update project context store (capillary network) — esg updatedAt stamp로
      // stale 해소(자동재계산 무한루프 차단).
      updateEsgData({
        embodiedCarbonKg: result.embodied_carbon_kgco2e,
        operationalCarbonKg: result.operational_carbon_kgco2e,
        totalCarbonPerSqm: result.carbon_per_sqm_kgco2e,
      });
      markStageComplete("esg");
      addAnalysisResult({
        module: "esg",
        completedAt: new Date().toISOString(),
        summary: {
          embodiedCarbon: result.embodied_carbon_kgco2e,
          operationalCarbon: result.operational_carbon_kgco2e,
          totalCarbon: result.total_carbon_kgco2e,
          carbonPerSqm: result.carbon_per_sqm_kgco2e,
        },
      });
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsSubmittingLca(false);
    }
  }, [
    lcaMaterials,
    floorArea,
    projectId,
    updateEsgData,
    markStageComplete,
    addAnalysisResult,
    labels.authError,
  ]);

  async function handleLcaSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runLca();
  }

  // 모세혈관: 설계(업스트림)가 갱신되면 이미 산출된 LCA를 1회 자동 재계산.
  // 백엔드 호출이라 과도호출 금지 — 결과가 있고(hasResult) 제출 중이 아니며,
  // 라이브 호출 가능할 때만(enabled). 사용자 입력값(자재·연면적)은 보존.
  useStageAutoRecalc("esg", runLca, {
    enabled: canUseLiveApi && !isSubmittingLca,
    hasResult: !!lcaResult,
  });

  /* EPD handlers */
  function addEpdMaterial() {
    setEpdMaterials((c) => [...c, { name: "", quantity_kg: "", unit: "kg" }]);
  }
  function removeEpdMaterial(index: number) {
    setEpdMaterials((c) => c.filter((_, i) => i !== index));
  }

  async function handleEpdSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");
    setIsSubmittingEpd(true);

    try {
      const material_list = epdMaterials.map((m) => ({
        name: m.name.trim(),
        quantity_kg: Number(m.quantity_kg) || 0,
        unit: m.unit.trim(),
      }));

      const result = await apiClient.post<CarbonFootprintResponse>(
        "/esg/epd/carbon-footprint",
        {
          useMock: false,
          body: { material_list },
        },
      );
      setEpdResult(result);
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsSubmittingEpd(false);
    }
  }

  /* Alternatives handler */
  async function handleAltSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");
    setIsSubmittingAlt(true);

    try {
      const result = await apiClient.post<LowCarbonAlternativesResponse>(
        "/esg/epd/low-carbon-alternatives",
        {
          useMock: false,
          body: {
            material_name: altForm.materialName.trim(),
            quantity_kg: Number(altForm.quantityKg) || 0,
          },
        },
      );
      setAltResult(result);
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsSubmittingAlt(false);
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
          {workspaceError ? (
            <div className="mt-6 rounded-[var(--radius-xl)] border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] p-5 text-sm leading-7 text-[var(--spot)]">
              {workspaceError}
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* 부지 데이터준비 게이트(공용) — 부지 미입력 시 데모 자재값 폼 대신 유도(무목업). */}
      {!hasSiteData ? (
        <SiteDataGate
          locale={locale}
          projectId={projectId}
          title="ESG 분석에 부지 데이터가 필요합니다"
          description="부지면적 또는 정확한 주소(시·구·동·번지)를 입력해 설계가 산출되면 전과정 탄소(LCA)·EPD가 정확히 산출됩니다."
        />
      ) : (
      <>
      {/* ── LCA Section ── */}
      <Card>
        <CardContent className="p-6">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
            {labels.lcaFormTitle}
          </p>
          <form className="mt-4 grid gap-4" onSubmit={handleLcaSubmit}>
            <NumberInput
              allowDecimal
              value={floorArea === "" ? null : Number(floorArea)}
              onChange={(n) => setFloorArea(n != null ? String(n) : "")}
              placeholder={labels.floorAreaLabel}
              className="flex h-11 w-full rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
            />
            {lcaMaterials.map((mat, index) => (
              <div
                key={index}
                className="grid gap-3 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-4 md:grid-cols-3"
              >
                <Input
                  value={mat.name}
                  onChange={(e) =>
                    updateLcaMaterial(index, "name", e.target.value)
                  }
                  placeholder={labels.materialNameLabel}
                />
                <NumberInput
                  allowDecimal
                  value={mat.quantity === "" ? null : Number(mat.quantity)}
                  onChange={(n) =>
                    updateLcaMaterial(index, "quantity", n != null ? String(n) : "")
                  }
                  placeholder={labels.materialQtyLabel}
                  className="flex h-11 w-full rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
                />
                <div className="flex items-center gap-2">
                  {lcaMaterials.length > 1 && (
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => removeLcaMaterial(index)}
                    >
                      {labels.removeMaterialAction}
                    </Button>
                  )}
                </div>
              </div>
            ))}
            <div className="flex gap-3">
              <Button type="button" variant="secondary" onClick={addLcaMaterial}>
                {labels.addMaterialAction}
              </Button>
              <Button
                type="submit"
                disabled={!canUseLiveApi || isSubmittingLca}
              >
                {isSubmittingLca
                  ? `${labels.submitLcaAction}...`
                  : labels.submitLcaAction}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* LCA Results */}
      <Card>
        <CardContent className="p-6">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
            {labels.lcaResultTitle}
          </p>
          {lcaResult ? (
            <div className="mt-4 space-y-4">
              {/* 검증 배지 + AI 탄소 해석 통합 카드(AnalysisVerdict) — 해석만 하단에 있던 것을 검증과 동일 카드로 노출 */}
              <AnalysisVerdict
                analysisType="esg"
                context={{ lca: lcaResult, epd: epdResult } as unknown as Record<string, unknown>}
                interpretation={lcaResult.ai_analysis}
                interpretationTitle="AI 탄소 해석"
              />
              <ExpertPanelCard
                analysisType="esg"
                context={{ lca: lcaResult, epd: epdResult } as unknown as Record<string, unknown>}
              />
              <div className="grid gap-4 md:grid-cols-4">
                <MetricTile
                  label={labels.embodiedCarbonLabel}
                  value={formatCarbon(lcaResult.embodied_carbon_kgco2e)}
                />
                <MetricTile
                  label={labels.operationalCarbonLabel}
                  value={formatCarbon(lcaResult.operational_carbon_kgco2e)}
                />
                <MetricTile
                  label={labels.totalCarbonLabel}
                  value={formatCarbon(lcaResult.total_carbon_kgco2e)}
                />
                <MetricTile
                  label={labels.carbonPerSqmLabel}
                  value={formatCarbon(lcaResult.carbon_per_sqm_kgco2e)}
                />
              </div>
              {/* 인증 법령 근거 칩(additive) — 구버전 응답(legal_refs 부재)은 미렌더(무손상).
                  url은 백엔드 레지스트리 제공값만 사용(LegalRefChip이 무링크 폴백 방어). */}
              {(lcaResult.legal_refs?.length ?? 0) > 0 ? (
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[10px] uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
                    {labels.legalRefsLabel}
                  </span>
                  {(lcaResult.legal_refs ?? []).map((ref) => (
                    <LegalRefChip
                      key={ref.key}
                      lawName={ref.law_name}
                      article={ref.article}
                      title={ref.title}
                      url={ref.url}
                    />
                  ))}
                </div>
              ) : null}
              {lcaResult.material_breakdown?.length > 0 && (
                <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                  <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                    {labels.materialBreakdownLabel}
                  </p>
                  <div className="mt-3 grid gap-3">
                    {(lcaResult.material_breakdown ?? []).map((item, i) => (
                      <div
                        key={`${item.material}-${i}`}
                        className="flex items-center justify-between rounded-[var(--radius-xl)] bg-[var(--surface)] px-4 py-3"
                      >
                        <span className="text-sm font-medium text-[var(--text-primary)]">
                          {item.material}
                        </span>
                        <div className="flex gap-4 items-center">
                          <span className="text-sm text-[var(--text-secondary)]">
                            {formatCarbon(item.carbon_kgco2e)}
                          </span>
                          <span className="text-xs font-bold text-[var(--accent-strong)]">
                            {formatPercent(item.percentage)}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {lcaResult.whole_life?.stages && (
                <div className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface)] p-5">
                  <p className="text-sm font-bold text-[var(--text-primary)]">전생애 탄소 (EN 15978)</p>
                  <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-3">
                    {Object.entries(lcaResult.whole_life.stages).map(([code, st]) => (
                      <div key={code} className="flex items-center justify-between rounded-lg bg-[var(--surface-soft)] px-3 py-2 text-[11px]">
                        <span className="text-[var(--text-secondary)]">{code} <span className="text-[var(--text-tertiary)]">{st.label}</span></span>
                        <span className={`font-semibold ${st.gwp_kgco2e < 0 ? "text-emerald-600" : "text-[var(--text-primary)]"}`}>
                          {(st.gwp_kgco2e / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })} t
                        </span>
                      </div>
                    ))}
                  </div>
                  <p className="mt-3 text-[11px] text-[var(--text-secondary)]">
                    내재 {((lcaResult.whole_life.embodied_total_kgco2e ?? 0) / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })} t
                    + 운영(B6) {((lcaResult.whole_life.operational_b6_kgco2e ?? 0) / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })} t
                    = 전생애 {((lcaResult.whole_life.whole_life_total_kgco2e ?? 0) / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })} tCO₂e
                  </p>
                  {lcaResult.whole_life.basis && <p className="mt-1 text-[10px] text-[var(--text-hint)]">{lcaResult.whole_life.basis}</p>}
                  {lcaResult.epd_coverage && (
                    <p className="mt-1 text-[10px] text-[var(--text-hint)]">
                      배출계수: {lcaResult.gwp_basis || "EPD-KR 우선"} · 한국 EPD 적용 자재 {lcaResult.epd_coverage}
                    </p>
                  )}
                </div>
              )}
              {lcaResult.ai_analysis ? (
                <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                  <p className="text-sm leading-7 text-[var(--text-secondary)]">
                    {lcaResult.ai_analysis}
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
        {/* ── EPD Carbon Footprint ── */}
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.epdFormTitle}
            </p>
            <form className="mt-4 grid gap-3" onSubmit={handleEpdSubmit}>
              {epdMaterials.map((mat, index) => (
                <div
                  key={index}
                  className="grid gap-3 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-4 md:grid-cols-4"
                >
                  <Input
                    value={mat.name}
                    onChange={(e) =>
                      setEpdMaterials((c) =>
                        c.map((m, i) =>
                          i === index ? { ...m, name: e.target.value } : m,
                        ),
                      )
                    }
                    placeholder={labels.epdMaterialNameLabel}
                  />
                  <NumberInput
                    allowDecimal
                    value={mat.quantity_kg === "" ? null : Number(mat.quantity_kg)}
                    onChange={(n) =>
                      setEpdMaterials((c) =>
                        c.map((m, i) =>
                          i === index
                            ? { ...m, quantity_kg: n != null ? String(n) : "" }
                            : m,
                        ),
                      )
                    }
                    placeholder={labels.epdQuantityLabel}
                  />
                  <Input
                    value={mat.unit}
                    onChange={(e) =>
                      setEpdMaterials((c) =>
                        c.map((m, i) =>
                          i === index ? { ...m, unit: e.target.value } : m,
                        ),
                      )
                    }
                    placeholder={labels.epdUnitLabel}
                  />
                  <div className="flex items-center gap-2">
                    {epdMaterials.length > 1 && (
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={() => removeEpdMaterial(index)}
                      >
                        {labels.removeMaterialAction}
                      </Button>
                    )}
                  </div>
                </div>
              ))}
              <div className="flex gap-3">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={addEpdMaterial}
                >
                  {labels.addMaterialAction}
                </Button>
                <Button
                  type="submit"
                  disabled={!canUseLiveApi || isSubmittingEpd}
                >
                  {isSubmittingEpd
                    ? `${labels.submitEpdAction}...`
                    : labels.submitEpdAction}
                </Button>
              </div>
            </form>

            {/* EPD Results */}
            <div className="mt-6">
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.epdResultTitle}
              </p>
              {epdResult ? (
                <div className="mt-4 space-y-4">
                  <MetricTile
                    label={labels.epdTotalLabel}
                    value={formatCarbon(epdResult.total_carbon_kgco2e)}
                  />
                  <div className="grid gap-3">
                    {(epdResult.items ?? []).map((item, i) => (
                      <div
                        key={`${item.name}-${i}`}
                        className="flex items-center justify-between rounded-[var(--radius-xl)] bg-[var(--surface-soft)] px-4 py-3"
                      >
                        <div className="space-y-1">
                          <p className="text-sm font-medium text-[var(--text-primary)]">
                            {item.name}
                          </p>
                          {item.epd_source ? (
                            <p className="text-xs text-[var(--text-tertiary)]">
                              EPD: {item.epd_source}
                            </p>
                          ) : null}
                        </div>
                        <span className="text-sm font-semibold text-[var(--text-primary)]">
                          {formatCarbon(item.carbon_kgco2e)}
                        </span>
                      </div>
                    ))}
                  </div>
                  {epdResult.ai_analysis ? (
                    <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                      <p className="text-sm leading-7 text-[var(--text-secondary)]">
                        {epdResult.ai_analysis}
                      </p>
                    </div>
                  ) : null}
                </div>
              ) : (
                <div className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
                  {labels.placeholder}
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* ── Low-Carbon Alternatives ── */}
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.alternativesFormTitle}
            </p>
            <form className="mt-4 grid gap-3" onSubmit={handleAltSubmit}>
              <Input
                value={altForm.materialName}
                onChange={(e) =>
                  setAltForm((c) => ({ ...c, materialName: e.target.value }))
                }
                placeholder={labels.altMaterialLabel}
              />
              <NumberInput
                allowDecimal
                value={altForm.quantityKg === "" ? null : Number(altForm.quantityKg)}
                onChange={(n) =>
                  setAltForm((c) => ({ ...c, quantityKg: n != null ? String(n) : "" }))
                }
                placeholder={labels.altQuantityLabel}
                className="flex h-11 w-full rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
              />
              <Button
                type="submit"
                disabled={!canUseLiveApi || isSubmittingAlt}
              >
                {isSubmittingAlt
                  ? `${labels.submitAltAction}...`
                  : labels.submitAltAction}
              </Button>
            </form>

            {/* Alternatives Results */}
            <div className="mt-6">
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.altResultTitle}
              </p>
              {altResult ? (
                <div className="mt-4 space-y-4">
                  <MetricTile
                    label={altResult.original_material}
                    value={formatCarbon(altResult.original_carbon_kgco2e)}
                  />
                  <div className="grid gap-3">
                    {(altResult.alternatives ?? []).map((alt, i) => (
                      <div
                        key={`${alt.alternative_name}-${i}`}
                        className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] px-5 py-4 space-y-2"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-medium text-[var(--text-primary)]">
                            {alt.alternative_name}
                          </span>
                          <span className="text-sm font-semibold text-[var(--accent-strong)]">
                            -{formatPercent(alt.carbon_reduction_percent)}
                          </span>
                        </div>
                        <div className="flex items-center justify-between text-xs text-[var(--text-secondary)]">
                          <span>{formatCarbon(alt.carbon_kgco2e)}</span>
                          <span>
                            {labels.altCostImpactLabel}:{" "}
                            {alt.cost_impact_percent > 0 ? "+" : ""}
                            {formatPercent(alt.cost_impact_percent)}
                          </span>
                        </div>
                        {alt.description ? (
                          <p className="text-xs text-[var(--text-tertiary)]">
                            {alt.description}
                          </p>
                        ) : null}
                      </div>
                    ))}
                  </div>
                  {altResult.ai_recommendation ? (
                    <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                      <p className="text-sm leading-7 text-[var(--text-secondary)]">
                        {altResult.ai_recommendation}
                      </p>
                    </div>
                  ) : null}
                </div>
              ) : (
                <div className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
                  {labels.placeholder}
                </div>
              )}
            </div>
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
