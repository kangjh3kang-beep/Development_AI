"use client";

/**
 * EsgExtendedPanelsSection — "확장 ESG 분석" 접힘 섹션(배선 캠페인 1차 — ESG 클러스터 5건).
 *
 * 배경: 배선설계도 P2 트리아지(_workspace/TRIAGE_wiring_p2_2026-07-11.md) ② 프론트 배선
 * 후보 16건 중 re100·lcc·eu-taxonomy·climate·energy 5개 라우터는 백엔드 서비스가 이미
 * 완성돼 있는데 화면이 없어 아무도 호출하지 못했다. 이 섹션은 ProjectEsgWorkspaceClient
 * 하단에 additive로 붙어 5개를 각 소형 패널로 노출한다(기존 GRESB/LCA 흐름은 무수정).
 *
 * 기본 접힘(AdvancedDrawer) — 화면을 어지럽히지 않고, 필요할 때만 펼쳐 쓴다.
 *
 * SSOT 커밋 판정(무날조 — 매칭 안 되면 표시만, 커밋 안 함):
 *   esgData는 {embodiedCarbonKg, operationalCarbonKg, totalCarbonPerSqm} 3필드만 가진
 *   전과정평가(LCA) 전용 슬롯이다. 5개 라우터 응답 중 이 3필드와 물리량·단위·의미가
 *   정확히 일치하는 값은 하나도 없다(아래 라우터별 근거) — 그래서 5개 패널 전부
 *   updateEsgData를 호출하지 않는다:
 *   - RE100: total_emissions_tco2eq는 "연간 전력 사용 기반" K-ETS 배출량(tCO2e/년)이라
 *     단위(kg vs t)도 다르고, LCA의 "건물 전과정 운영탄소"와 산출 모델 자체가 다르다.
 *   - LCC: 전부 원화 비용/NPV 지표 — 탄소 지표 없음.
 *   - EU Taxonomy: 응답은 적합성 판정/기준 충족표일 뿐 탄소 총량 산출값이 없다
 *     (embodied_carbon_kgco2e_m2는 응답이 아니라 *입력* 필드).
 *   - 기후리스크: 위험점수/기대손실액 — 탄소 지표 없음.
 *   - 에너지인증: 에너지수요(kWh)·자립률 — 탄소(kgCO2e) 환산계수를 이 엔드포인트가
 *     제공하지 않으므로 임의 환산은 발명(무날조 위반)이라 커밋하지 않는다.
 */

import { useMemo, type ReactNode } from "react";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { AdvancedDrawer } from "@/components/common/AdvancedDrawer";
import { EvidencePanel } from "@/components/common/EvidencePanel";
import { adaptEvidence, type BackendEvidence, type BackendLegalRef } from "@/lib/evidence/adaptEvidence";
import { apiClient } from "@/lib/api-client";
import {
  ExtendedEsgPanel,
  type ExtendedEsgFormField,
} from "@/components/projects/ExtendedEsgPanel";
import {
  buildEsgExtendedContext,
  buildRe100Body,
  buildLccBody,
  buildEuTaxonomyBody,
  buildClimateBody,
  buildEnergyCertificationBody,
  re100InitialValues,
  lccInitialValues,
  euTaxonomyInitialValues,
  climateInitialValues,
  energyCertificationInitialValues,
  // 표시 포맷 헬퍼(lib로 이동 — QA F1: 단위테스트 가능하도록 순수 로직 파일에 위치).
  formatWon,
  formatPercent01,
  formatPercent100,
  formatTco2e,
  formatNumber,
} from "@/lib/esg-extended-panels";

function Tile({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-[var(--radius-xl)] bg-[var(--surface)] p-4">
      <p className="text-[11px] uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-2 text-sm font-semibold text-[var(--text-primary)]">{value}</p>
    </div>
  );
}

/** 백엔드 build_evidence_block 산출물(있을 때만) → EvidencePanel 렌더. */
function EvidenceBlock({
  evidence,
}: {
  evidence?: { evidence?: BackendEvidence[]; legal_refs?: BackendLegalRef[] } | null;
}) {
  if (!evidence) return null;
  const items = adaptEvidence(evidence.evidence, evidence.legal_refs);
  if (items.length === 0) return null;
  return <EvidencePanel items={items} defaultOpen={false} />;
}

/* ── ① RE100 ── */

interface Re100Response {
  re100_rate: number;
  emissions: {
    total_emissions_tco2eq: number;
    baseline_emissions_tco2eq: number;
    excess_emissions_tco2eq: number;
  };
  kts_cost: number;
  procurement_comparison: Array<{
    method: string;
    description: string;
    unit_cost_krw_mwh: number;
    total_cost_krw: number;
  }>;
  roadmap: Array<{
    target_year: number;
    target_rate: number;
    current_gap: number;
    additional_renewable_mwh: number;
    annual_increase_mwh: number;
  }>;
  summary: string;
}

function renderRe100Result(raw: unknown): ReactNode {
  const r = raw as Re100Response;
  return (
    <>
      <div className="grid gap-4 md:grid-cols-3">
        {/* re100_rate는 진짜 0.0~1.0 비율(re100.py:67 "RE100 이행률 (0.0~1.0)") — formatPercent01(×100) 정확. */}
        <Tile label="RE100 이행률" value={formatPercent01(r.re100_rate)} />
        <Tile label="총 배출량" value={formatTco2e(r.emissions?.total_emissions_tco2eq)} />
        <Tile label="K-ETS 비용" value={formatWon(r.kts_cost)} />
      </div>
      {r.summary ? (
        <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
          {r.summary}
        </div>
      ) : null}
      {(r.roadmap?.length ?? 0) > 0 ? (
        <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-4">
          <p className="mb-2 text-[11px] uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
            이행 로드맵
          </p>
          <div className="grid gap-2">
            {r.roadmap.map((item, i) => (
              <div key={i} className="flex items-center justify-between rounded-lg bg-[var(--surface)] px-3 py-2 text-xs">
                <span className="text-[var(--text-secondary)]">{item.target_year}년</span>
                {/* target_rate도 0.0~1.0(re100_tracker_service.py RE100_TARGETS: 0.60/0.90/1.00). */}
                <span className="text-[var(--text-primary)]">목표 {formatPercent01(item.target_rate)}</span>
                <span className="text-[var(--text-tertiary)]">+{formatNumber(item.additional_renewable_mwh, "MWh")}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </>
  );
}

/* ── ② LCC ── */

interface LccResponse {
  npv_total: number;
  npv_construction: number;
  npv_maintenance: number;
  npv_energy: number;
  npv_repair: number;
  real_discount_rate: number;
  analysis_period_years: number;
  alternatives?: Array<{
    alternative?: string;
    description?: string;
    npv_total_krw?: number;
  }> | null;
}

function renderLccResult(raw: unknown): ReactNode {
  const r = raw as LccResponse;
  return (
    <>
      <div className="grid gap-4 md:grid-cols-3">
        <Tile label={`LCC 총 NPV (${r.analysis_period_years}년)`} value={formatWon(r.npv_total)} />
        {/* real_discount_rate = (1+nominal_rate)/(1+inflation_rate)-1(lcc_service.py) — 0.0~1.0 소수 비율. */}
        <Tile label="실질 할인율" value={formatPercent01(r.real_discount_rate)} />
        <Tile label="건설비 NPV" value={formatWon(r.npv_construction)} />
        <Tile label="유지보수비 NPV" value={formatWon(r.npv_maintenance)} />
        <Tile label="에너지비 NPV" value={formatWon(r.npv_energy)} />
        <Tile label="대수선비 NPV" value={formatWon(r.npv_repair)} />
      </div>
      {(r.alternatives?.length ?? 0) > 0 ? (
        <div className="grid gap-2">
          {(r.alternatives ?? []).map((alt, i) => (
            <div key={i} className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] px-4 py-3 text-xs">
              <span className="font-medium text-[var(--text-primary)]">{alt.alternative ?? `대안 ${i + 1}`}</span>
              {alt.npv_total_krw != null ? (
                <span className="ml-2 text-[var(--text-secondary)]">{formatWon(alt.npv_total_krw)}</span>
              ) : null}
              {alt.description ? <p className="mt-1 text-[var(--text-tertiary)]">{alt.description}</p> : null}
            </div>
          ))}
        </div>
      ) : null}
    </>
  );
}

/* ── ③ EU Taxonomy ── */

interface EuTaxonomyResponse {
  alignment: string;
  criteria: Array<{
    name: string;
    category: string;
    passed: boolean;
    actual_value: number | string;
    threshold: number | string;
    rationale: string;
  }>;
  passed_count: number;
  total_count: number;
  recommendations: string[];
  evidence?: { evidence?: BackendEvidence[]; legal_refs?: BackendLegalRef[] } | null;
}

function renderEuTaxonomyResult(raw: unknown): ReactNode {
  const r = raw as EuTaxonomyResponse;
  return (
    <>
      <div className="grid gap-4 md:grid-cols-2">
        <Tile label="적합성 판정" value={r.alignment} />
        <Tile label="기준 충족" value={`${r.passed_count}/${r.total_count}`} />
      </div>
      {(r.criteria?.length ?? 0) > 0 ? (
        <div className="grid gap-2">
          {r.criteria.map((c, i) => (
            <div
              key={i}
              className="flex items-center justify-between rounded-lg bg-[var(--surface-soft)] px-3 py-2 text-xs"
            >
              <span className="text-[var(--text-secondary)]">
                [{c.category}] {c.name}
              </span>
              <span className={c.passed ? "font-semibold text-emerald-600" : "font-semibold text-[var(--spot)]"}>
                {c.passed ? "통과" : "미통과"} ({c.actual_value}/{c.threshold})
              </span>
            </div>
          ))}
        </div>
      ) : null}
      {(r.recommendations?.length ?? 0) > 0 ? (
        <ul className="list-disc space-y-1 pl-5 text-xs text-[var(--text-secondary)]">
          {r.recommendations.map((rec, i) => (
            <li key={i}>{rec}</li>
          ))}
        </ul>
      ) : null}
      <EvidenceBlock evidence={r.evidence} />
    </>
  );
}

/* ── ④ 기후리스크 ── */

interface ClimateResponse {
  flood_risk_score: number;
  heat_risk_score: number;
  overall_risk_level: string;
  annual_expected_loss_krw: number;
  risk_factors: Array<{ factor?: string; score?: number; impact?: string; description?: string }>;
  mitigation_tips: string[];
  insurance_recommendations: Array<{
    coverage_type: string;
    priority: string;
    annual_premium_estimate_krw: number;
    coverage_limit_krw: number;
    rationale: string;
  }>;
  evidence?: { evidence?: BackendEvidence[]; legal_refs?: BackendLegalRef[] } | null;
}

function renderClimateResult(raw: unknown): ReactNode {
  const r = raw as ClimateResponse;
  return (
    <>
      <div className="grid gap-4 md:grid-cols-2">
        <Tile label="종합 위험등급" value={r.overall_risk_level} />
        <Tile label="연간 기대손실" value={formatWon(r.annual_expected_loss_krw)} />
        <Tile label="침수위험 점수" value={formatNumber(r.flood_risk_score)} />
        <Tile label="폭염위험 점수" value={formatNumber(r.heat_risk_score)} />
      </div>
      {(r.risk_factors?.length ?? 0) > 0 ? (
        <div className="grid gap-2">
          {r.risk_factors.map((f, i) => (
            <div key={i} className="rounded-lg bg-[var(--surface-soft)] px-3 py-2 text-xs">
              {f.factor ? <span className="font-medium text-[var(--text-primary)]">{f.factor}</span> : null}
              {f.impact ? <span className="ml-2 text-[var(--text-tertiary)]">{f.impact}</span> : null}
              {f.description ? <p className="mt-1 text-[var(--text-secondary)]">{f.description}</p> : null}
            </div>
          ))}
        </div>
      ) : null}
      {(r.insurance_recommendations?.length ?? 0) > 0 ? (
        <div className="grid gap-2">
          {r.insurance_recommendations.map((ins, i) => (
            <div key={i} className="flex items-center justify-between rounded-lg bg-[var(--surface-soft)] px-3 py-2 text-xs">
              <span className="text-[var(--text-primary)]">{ins.coverage_type}</span>
              <span className="text-[var(--text-secondary)]">{formatWon(ins.annual_premium_estimate_krw)}/년</span>
            </div>
          ))}
        </div>
      ) : null}
      <EvidenceBlock evidence={r.evidence} />
    </>
  );
}

/* ── ⑤ 에너지 인증 ── */

interface EnergyCertificationResponse {
  energy_grade: string;
  zeb_grade: string;
  annual_energy_demand_kwh: number;
  annual_renewable_generation_kwh: number;
  energy_independence_rate: number;
  bems_saving_kwh: number;
  recommendations: string[];
  evidence?: { evidence?: BackendEvidence[]; legal_refs?: BackendLegalRef[] } | null;
}

function renderEnergyCertificationResult(raw: unknown): ReactNode {
  const r = raw as EnergyCertificationResponse;
  return (
    <>
      <div className="grid gap-4 md:grid-cols-2">
        <Tile label="에너지효율등급" value={r.energy_grade} />
        <Tile label="ZEB 등급" value={r.zeb_grade} />
        <Tile label="연간 에너지수요" value={formatNumber(r.annual_energy_demand_kwh, " kWh")} />
        {/* ★QA F1: 백엔드가 이미 0~100 스케일로 반환(construction_ai_service.py:244
            "independence_rate = pv_generation/total_demand*100") — formatPercent01(×100
            재곱)을 쓰면 45.3%가 "4530.0%"로 표시된다. formatPercent100으로 그대로 표시. */}
        <Tile label="에너지자립률" value={formatPercent100(r.energy_independence_rate)} />
      </div>
      {(r.recommendations?.length ?? 0) > 0 ? (
        <ul className="list-disc space-y-1 pl-5 text-xs text-[var(--text-secondary)]">
          {r.recommendations.map((rec, i) => (
            <li key={i}>{rec}</li>
          ))}
        </ul>
      ) : null}
      <EvidenceBlock evidence={r.evidence} />
    </>
  );
}

/* ── 조립: 컴포넌트 ── */

export function EsgExtendedPanelsSection({ projectId }: { projectId: string }) {
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const designData = useProjectContextStore((s) => s.designData);
  const feasibilityData = useProjectContextStore((s) => s.feasibilityData);
  const costData = useProjectContextStore((s) => s.costData);
  const esgData = useProjectContextStore((s) => s.esgData);

  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi = runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;
  const authErrorMessage = "라이브 작업 공간 호출을 위해 API 인증이 필요합니다.";

  // 프리필 컨텍스트는 SSOT 슬라이스가 바뀔 때만 재계산(불필요한 초기값 재세팅 방지).
  const ctx = useMemo(
    () =>
      buildEsgExtendedContext({
        projectId,
        siteAnalysis,
        designData,
        feasibilityData,
        costData,
        esgData,
      }),
    [projectId, siteAnalysis, designData, feasibilityData, costData, esgData],
  );

  const re100Fields: ExtendedEsgFormField[] = [
    { key: "trackingYear", label: "추적 연도", type: "number", allowDecimal: false },
    { key: "totalElectricityMwh", label: "총 전력 사용량 (MWh)", type: "number" },
    { key: "renewableElectricityMwh", label: "재생에너지 전력량 (MWh)", type: "number" },
    { key: "ktsUnitPriceKrw", label: "K-ETS 배출권 단가 (원/tCO2eq)", type: "number", allowDecimal: false },
  ];

  const lccFields: ExtendedEsgFormField[] = [
    { key: "initialConstructionCost", label: "초기 건설비 (원)", type: "number" },
    { key: "annualMaintenanceCost", label: "연간 유지보수비 (원)", type: "number" },
    { key: "annualEnergyCost", label: "연간 에너지비 (원)", type: "number" },
  ];

  const euTaxonomyFields: ExtendedEsgFormField[] = [
    { key: "primaryEnergyDemandKwhM2", label: "1차 에너지 소요량 (kWh/㎡·년)", type: "number" },
    { key: "renewableEnergyRatio", label: "재생에너지 비율 (0~1)", type: "number" },
    { key: "embodiedCarbonKgco2eM2", label: "내재탄소 (kgCO2e/㎡)", type: "number" },
    { key: "waterUsageLitersPerDay", label: "일일 물 사용량 (L/인·일)", type: "number" },
    { key: "wasteRecyclingRate", label: "건설폐기물 재활용률 (0~1)", type: "number" },
    { key: "greenRatio", label: "녹지율 (0~1)", type: "number" },
    { key: "grossFloorAreaSqm", label: "연면적 (㎡)", type: "number" },
    { key: "hasClimateRiskAssessment", label: "기후위험 평가 수행 여부", type: "boolean" },
    { key: "hasSocialSafeguards", label: "사회적 안전장치(ILO 핵심 노동기준) 준수 여부", type: "boolean" },
  ];

  const climateFields: ExtendedEsgFormField[] = [
    { key: "lat", label: "위도", type: "number" },
    { key: "lon", label: "경도", type: "number" },
    { key: "assetValueKrw", label: "자산가치 (원)", type: "number" },
    { key: "constructionPeriodMonths", label: "공사 기간 (개월)", type: "number", allowDecimal: false },
  ];

  const energyFields: ExtendedEsgFormField[] = [
    { key: "totalAreaSqm", label: "연면적 (㎡)", type: "number" },
    { key: "floors", label: "층수", type: "number", allowDecimal: false },
    { key: "windowWallRatio", label: "창면적비 (0.1~0.9)", type: "number" },
    { key: "insulationGrade", label: "단열등급", type: "text" },
    { key: "bemsSavingRate", label: "BEMS 절감률 (0~0.5)", type: "number" },
  ];

  return (
    <AdvancedDrawer label="확장 ESG 분석 (RE100·LCC·EU Taxonomy·기후리스크·에너지인증)">
      <div className="grid gap-6">
        {/* ★QA F2: 각 패널의 key는 그 패널이 실제로 쓰는 프리필 소스 필드만으로 구성한다.
            ExtendedEsgPanel의 initialValues는 useState(initialValues)로 "첫 마운트에만" 캡처되는데,
            AdvancedDrawer는 eager 마운트(펼치기 전에도 자식이 이미 마운트)라서 restoreSnapshot 등
            비동기 SSOT 하이드레이션이 늦게 도착하면 프리필이 빈 채로 고착되는 문제가 있었다.
            key가 바뀌면 React가 리마운트하며 initialValues를 최신 ctx로 재캡처한다.
            하이드레이션 도착 시 리마운트로 프리필 재캡처 — 드로어 기본 닫힘이라 사용자 편집 전
            도착이 일반적이며, 편집 후 시그니처 변경은 드묾(수용). RE100은 SSOT 프리필이 전혀
            없으므로(전력사용량은 계량값 — 프리필 불가) key도 정적으로 고정한다. */}
        <ExtendedEsgPanel
          key="re100"
          title="RE100 이행률·K-ETS 비용 추적"
          fields={re100Fields}
          initialValues={re100InitialValues()}
          buildBody={(values) => buildRe100Body(values, ctx)}
          endpoint="/re100/track"
          submitLabel="RE100 추적 실행"
          resultTitle="RE100 추적 결과"
          renderResult={renderRe100Result}
          canUseLiveApi={canUseLiveApi}
          authErrorMessage={authErrorMessage}
          placeholderMessage="폼을 제출하면 결과가 표시됩니다."
          requiredPositiveFields={["totalElectricityMwh"]}
        />

        <ExtendedEsgPanel
          key={`lcc-${ctx.constructionCostWon ?? "none"}`}
          title="생애주기비용(LCC) 산출 (ISO 15686-5)"
          fields={lccFields}
          initialValues={lccInitialValues(ctx)}
          buildBody={(values) => buildLccBody(values, ctx)}
          endpoint="/lcc/calculate"
          submitLabel="LCC 산출 실행"
          resultTitle="LCC 산출 결과"
          renderResult={renderLccResult}
          canUseLiveApi={canUseLiveApi}
          authErrorMessage={authErrorMessage}
          placeholderMessage="폼을 제출하면 결과가 표시됩니다."
          requiredPositiveFields={["initialConstructionCost"]}
        />

        <ExtendedEsgPanel
          key={`eu-taxonomy-${ctx.totalGfaSqm ?? "none"}-${ctx.embodiedCarbonPerSqm ?? "none"}`}
          title="EU Taxonomy 적합성 검증"
          fields={euTaxonomyFields}
          initialValues={euTaxonomyInitialValues(ctx)}
          buildBody={(values) => buildEuTaxonomyBody(values)}
          endpoint="/eu-taxonomy/check"
          submitLabel="EU Taxonomy 검증 실행"
          resultTitle="EU Taxonomy 검증 결과"
          renderResult={renderEuTaxonomyResult}
          canUseLiveApi={canUseLiveApi}
          authErrorMessage={authErrorMessage}
          placeholderMessage="폼을 제출하면 결과가 표시됩니다."
          requiredPositiveFields={["grossFloorAreaSqm"]}
        />

        <ExtendedEsgPanel
          key={`climate-${ctx.lat ?? "none"}-${ctx.lon ?? "none"}-${ctx.assetValueWon ?? "none"}`}
          title="기후리스크·보험 패키지 분석"
          fields={climateFields}
          initialValues={climateInitialValues(ctx)}
          buildBody={(values) => buildClimateBody(values, ctx)}
          endpoint="/climate/risk"
          submitLabel="기후리스크 분석 실행"
          resultTitle="기후리스크 분석 결과"
          renderResult={renderClimateResult}
          canUseLiveApi={canUseLiveApi}
          authErrorMessage={authErrorMessage}
          placeholderMessage="폼을 제출하면 결과가 표시됩니다."
          requiredPositiveFields={["assetValueKrw"]}
        />

        <ExtendedEsgPanel
          key={`energy-cert-${ctx.totalGfaSqm ?? "none"}-${ctx.floorCount ?? "none"}`}
          title="에너지효율등급·ZEB 인증 추정"
          fields={energyFields}
          initialValues={energyCertificationInitialValues(ctx)}
          buildBody={(values) => buildEnergyCertificationBody(values, ctx)}
          endpoint="/energy/certification"
          submitLabel="에너지 인증 추정 실행"
          resultTitle="에너지 인증 추정 결과"
          renderResult={renderEnergyCertificationResult}
          canUseLiveApi={canUseLiveApi}
          authErrorMessage={authErrorMessage}
          placeholderMessage="폼을 제출하면 결과가 표시됩니다."
          requiredPositiveFields={["totalAreaSqm"]}
        />
      </div>
    </AdvancedDrawer>
  );
}
