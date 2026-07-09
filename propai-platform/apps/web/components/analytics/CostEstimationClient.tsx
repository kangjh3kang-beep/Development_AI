"use client";

/**
 * 공사비 단계별 통합 워크플로우 — 건축개요 기반(프로젝트 연동·지상/지하/조경/간접·최저~최대).
 *
 * 단계별 구성(중복 위젯 제거·자동연동·전문용어 풀이·BIM 정밀적산 연계):
 *  Step1 프로젝트 정보(자동연동): 프로젝트명 표시(UUID 아님), 건축유형·연면적·구조·층수를 설계/부지에서 자동 로드(전부 수정 가능)
 *  Step2 개략 공사비 산정: /cost/estimate-overview 1회 호출(SSOT) → 범위·항목분해 → costData 컨텍스트(수지·ROI 연동)
 *  Step3 리스크 시뮬레이션: 몬테카를로(P10/P50/P90·히스토그램)를 Step1 자동연동값으로 구동(별도 위젯 제거·흡수)
 *  Step4 정밀 적산(BIM 연계): 개략(여기) vs 정밀(BIM) 관계 안내 + BIM·적산 스튜디오 CTA
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Construction, DraftingCompass, Link2 } from "lucide-react";
import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { NumberInput } from "@/components/common/NumberInput";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { useStageAutoRecalc } from "@/hooks/useStageAutoRecalc";
import { getZoningSpec } from "@/lib/kr-building-regulations";
import { VerificationBadge } from "@/components/common/VerificationBadge";
import { ExpertPanelCard } from "@/components/common/ExpertPanelCard";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";
import { adaptEvidence, type BackendEvidence, type BackendLegalRef } from "@/lib/evidence/adaptEvidence";
import { isValidLocale } from "@/i18n/config";

interface Overview {
  building_type: string; structure_type: string;
  total_gfa_sqm: number; gfa_above_sqm: number; gfa_below_sqm: number;
  unit_cost_per_sqm: number;
  aboveground_won: number; underground_won: number; landscape_won: number; direct_won: number;
  design_fee_won: number; supervision_fee_won: number; contingency_won: number; general_expense_won: number;
  indirect_won: number; total_won: number; per_pyeong_won: number;
  range: { min_won: number; expected_won: number; max_won: number };
  // 백엔드 /cost/estimate-overview가 반환하는 산출근거(기준단가·지상/지하/조경/간접 산식·신뢰도).
  evidence?: BackendEvidence[]; legal_refs?: BackendLegalRef[];
  items?: { name: string; spec?: string; unit?: string; quantity: number; unit_cost_won: number; cost_won: number }[];
  qto_source?: string; // bim | derived
  geometry?: {
    source: string; width_m: number; depth_m: number; floors_above: number; floors_below: number;
    footprint_sqm: number; perimeter_m: number; concrete_m3: number; rebar_ton: number; formwork_m2: number;
    structural_direct_won: number;
    items: { name: string; spec?: string; unit?: string; quantity: number; cost_won: number }[];
  };
}

interface RiskResult {
  iterations: number;
  mean: number; stdDev: number;
  p10: number; p50: number; p90: number; min: number; max: number;
  ci90: [number, number];
  histogram: { binStart: number; binEnd: number; count: number }[];
  summary: string;
}

const BUILDING_TYPES = [
  ["apartment", "아파트/공동주택"], ["officetel", "오피스텔"], ["office", "업무시설"],
  ["townhouse", "연립·다세대"], ["single_house", "단독주택"], ["warehouse", "지식산업센터/창고"],
] as const;
const STRUCTURES: [string, string][] = [
  ["RC", "철근콘크리트(RC)"], ["SRC", "철골철근콘크리트(SRC)"], ["SC", "철골(SC)"],
  ["PC", "프리캐스트(PC)"], ["목구조", "목구조"],
];

function fmtKrw(won?: number | null): string {
  if (won == null || isNaN(won)) return "-";
  const abs = Math.abs(won), sign = won < 0 ? "-" : "";
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(1)}억`;
  if (abs >= 1e4) return `${sign}${Math.round(abs / 1e4).toLocaleString()}만`;
  return `${sign}${Math.round(abs).toLocaleString()}원`;
}
function mapBuildingType(bt?: string | null): string {
  const s = (bt || "").toString();
  if (/오피스텔/.test(s)) return "officetel";
  if (/지식산업|창고|물류/.test(s)) return "warehouse";
  if (/업무|오피스(?!텔)/.test(s)) return "office";
  if (/연립|다세대|빌라/.test(s)) return "townhouse";
  if (/단독/.test(s)) return "single_house";
  return "apartment";
}

const fcls = "w-full rounded-lg border border-[var(--line-strong)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]";

/** 전문용어 풀이 — 라벨 옆 ⓘ 호버 시 쉬운 설명(접근성 title 병행). */
function Term({ label, hint }: { label: string; hint: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      {label}
      <span
        title={hint}
        className="inline-flex h-3.5 w-3.5 cursor-help items-center justify-center rounded-full bg-[var(--surface-muted)] text-[8px] font-black text-[var(--text-tertiary)]"
        aria-label={hint}
      >
        ?
      </span>
    </span>
  );
}

/** Step 헤더 — 번호·제목·진행감. */
function StepHeader({ n, title, desc, done }: { n: number; title: string; desc: string; done?: boolean }) {
  return (
    <div className="flex items-start gap-3">
      <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-black ${done ? "bg-emerald-500/20 text-emerald-400" : "bg-[var(--accent-soft)] text-[var(--accent-strong)]"}`}>
        {done ? "✓" : n}
      </span>
      <div>
        <h2 className="text-lg font-black text-[var(--text-primary)]">{title}</h2>
        <p className="mt-0.5 text-xs text-[var(--text-secondary)]">{desc}</p>
      </div>
    </div>
  );
}

const AutoBadge = () => (
  <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[9px] font-bold text-emerald-400">프로젝트에서 자동</span>
);

export function CostEstimationClient() {
  const params = useParams() as { locale?: string };
  const locale = isValidLocale(params?.locale ?? "") ? (params.locale as string) : "ko";

  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const designData = useProjectContextStore((s) => s.designData);
  const projectId = useProjectContextStore((s) => s.projectId);
  const projectName = useProjectContextStore((s) => s.projectName);
  const updateCostData = useProjectContextStore((s) => s.updateCostData);

  const [pickerAddr, setPickerAddr] = useState("");
  const [bt, setBt] = useState("apartment");
  const [gfa, setGfa] = useState(0);
  const [floorsAbove, setFloorsAbove] = useState(15);
  const [floorsBelow, setFloorsBelow] = useState(2);
  const [structure, setStructure] = useState("RC");
  const [autoGfa, setAutoGfa] = useState(false);
  const [autoBt, setAutoBt] = useState(false);
  const [autoFloors, setAutoFloors] = useState(false);
  const [result, setResult] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [editedGfa, setEditedGfa] = useState(false);

  // Step3 리스크 시뮬레이션
  const [iterations, setIterations] = useState(10000);
  const [risk, setRisk] = useState<RiskResult | null>(null);
  const [riskLoading, setRiskLoading] = useState(false);

  const hasDesign = !!designData?.totalGfaSqm;
  const hasProject = !!projectId;
  const [gfaFromSite, setGfaFromSite] = useState(false);

  // 부지면적 + 용적률로 GFA 폴백 추정(설계 미완 시 초기값 제안)
  const estimatedGfaFromSite = useMemo(() => {
    // ★다필지면 통합 면적으로 GFA 폴백을 역산(대표값 과소산출 방지).
    const land = effectiveLandAreaSqm(siteAnalysis) ?? 0;
    if (land <= 0) return 0;
    const spec = siteAnalysis?.zoneCode ? getZoningSpec(siteAnalysis.zoneCode) : null;
    const far = spec?.floorAreaRatioMax ?? 0;
    if (far <= 0) return 0;
    return Math.round((land * far) / 100);
  }, [siteAnalysis]);

  // 건축개요 자동 로드(수정한 GFA는 보존). 설계가 있으면 설계 GFA, 없으면 부지×용적률 폴백.
  useEffect(() => {
    if (!projectId) return;
    if (designData?.totalGfaSqm && !editedGfa) {
      setGfa(Math.round(designData.totalGfaSqm)); setAutoGfa(true); setGfaFromSite(false);
    } else if (!designData?.totalGfaSqm && estimatedGfaFromSite > 0 && !editedGfa) {
      setGfa(estimatedGfaFromSite); setAutoGfa(true); setGfaFromSite(true);
    }
    if (designData?.floorCount) { setFloorsAbove(designData.floorCount); setAutoFloors(true); }
    if (designData?.buildingType) { setBt(mapBuildingType(designData.buildingType)); setAutoBt(true); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, designData, estimatedGfaFromSite]);

  const calc = useCallback(async () => {
    if (!gfa || gfa <= 0) { setErr("연면적(GFA)을 입력하세요(프로젝트 선택 시 자동 반영)."); return; }
    setLoading(true); setErr(""); setRisk(null);
    try {
      const r = await apiClient.post<Overview>("/cost/estimate-overview", {
        body: { building_type: bt, total_gfa_sqm: gfa, floor_count_above: floorsAbove, floor_count_below: floorsBelow, structure_type: structure, project_id: projectId || undefined },
        useMock: false, timeoutMs: 30000,
      });
      setResult(r);
      // 수지·사업성 연동: 컨텍스트에 공사비 저장
      updateCostData({
        totalConstructionCostWon: r.total_won, perSqmWon: r.unit_cost_per_sqm, perPyeongWon: r.per_pyeong_won,
        abovegroundWon: r.aboveground_won, undergroundWon: r.underground_won, landscapeWon: r.landscape_won,
        directWon: r.direct_won, indirectWon: r.indirect_won,
        rangeMinWon: r.range.min_won, rangeMaxWon: r.range.max_won, source: "overview",
      });
    } catch {
      setErr("공사비 산정에 실패했습니다. 입력값을 확인하세요.");
    } finally { setLoading(false); }
  }, [bt, gfa, floorsAbove, floorsBelow, structure, projectId, updateCostData]);

  // 모세혈관: 부지·설계(업스트림)가 갱신되면 이미 산정된 공사비를 1회 자동 재계산.
  // 백엔드 호출이라 과도호출 금지 — 결과가 있고(hasResult) 로딩 중이 아닐 때만(enabled).
  useStageAutoRecalc("cost", calc, { enabled: !loading, hasResult: !!result });

  // Step3: 개략 산정 결과(Step2)의 기대공사비와 최저~최대 레인지를 근거로 몬테카를로 시뮬레이션.
  const runRisk = useCallback(() => {
    if (!result) return;
    setRiskLoading(true);
    try {
      const expected = result.total_won;
      // 레인지(min~max)를 ±변동폭으로 환산(없으면 ±15% 기본)
      const lo = result.range?.min_won && result.range.min_won > 0 ? result.range.min_won / expected : 0.85;
      const hi = result.range?.max_won && result.range.max_won > 0 ? result.range.max_won / expected : 1.15;
      const span = Math.max(0.02, hi - lo);
      const iters = Math.min(50000, Math.max(1000, iterations || 10000));
      const samples: number[] = [];
      for (let i = 0; i < iters; i++) {
        const factor = lo + Math.random() * span;
        samples.push(Math.round(expected * factor));
      }
      samples.sort((a, b) => a - b);
      const mean = Math.round(samples.reduce((s, v) => s + v, 0) / iters);
      const variance = samples.reduce((s, v) => s + (v - mean) ** 2, 0) / iters;
      const minV = samples[0], maxV = samples[iters - 1];
      const binCount = 10;
      const binWidth = (maxV - minV) / binCount;
      const histogram = Array.from({ length: binCount }, (_, i) => {
        const binStart = minV + i * binWidth;
        const binEnd = binStart + binWidth;
        return { binStart: Math.round(binStart), binEnd: Math.round(binEnd), count: samples.filter((v) => v >= binStart && v < (i === binCount - 1 ? Infinity : binEnd)).length };
      });
      const p05 = samples[Math.floor(iters * 0.05)];
      const p95 = samples[Math.floor(iters * 0.95)];
      setRisk({
        iterations: iters, mean, stdDev: Math.round(Math.sqrt(variance)),
        p10: samples[Math.floor(iters * 0.1)], p50: samples[Math.floor(iters * 0.5)], p90: samples[Math.floor(iters * 0.9)],
        min: minV, max: maxV, ci90: [p05, p95], histogram,
        summary: `${iters.toLocaleString()}회 시뮬레이션 결과, 90% 확률로 총 공사비가 ${fmtKrw(p05)} ~ ${fmtKrw(p95)} 범위에 분포합니다(개략 공사비 범위 기반).`,
      });
    } finally { setRiskLoading(false); }
  }, [result, iterations]);

  const breakdown = useMemo(() => result ? [
    ["지상 직접공사비", result.aboveground_won],
    ["지하 직접공사비", result.underground_won],
    ["조경", result.landscape_won],
    ["설계비", result.design_fee_won],
    ["감리비", result.supervision_fee_won],
    ["예비비(설계변경)", result.contingency_won],
    ["일반관리비", result.general_expense_won],
  ] as [string, number][] : [], [result]);

  const sectionCls = "grid gap-5 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-6";

  return (
    <section className="grid grid-cols-1 gap-8 min-w-0">
      {/* 헤더 */}
      <div>
        <div className="flex items-center gap-3 mb-1.5">
          <span className="cc-meta">COST · WORKFLOW</span>
          {result && <span className="cc-live"><i />ESTIMATED</span>}
        </div>
        <h1 className="text-2xl font-black text-[var(--text-primary)]">공사비 분석 (단계별 통합)</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          프로젝트 정보 자동연동 → 개략 공사비 산정 → 리스크 시뮬레이션 → BIM 정밀 적산 연계까지 한 흐름으로 진행합니다.
          결과는 <b className="text-[var(--text-primary)]">수지분석·투자수익성(ROI)과 자동 연동</b>됩니다. 자동 값도 모두 수정 가능합니다.
        </p>
      </div>

      {/* ───────── Step 1: 프로젝트 정보(자동연동) ───────── */}
      <div className={sectionCls}>
        <StepHeader n={1} title="프로젝트 정보 (자동연동)" desc="설계·부지 분석에서 건축개요를 자동으로 불러옵니다. 모든 값은 수정할 수 있습니다." />

        {hasProject ? (
          <div className="rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-4 py-3">
            <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">분석 대상 프로젝트</p>
            <p className="mt-1 text-base font-black text-[var(--accent-strong)]">{projectName || "이름 없는 프로젝트"}</p>
          </div>
        ) : null}

        <ProjectAddressInput value={pickerAddr} onChange={setPickerAddr} label="분석 대상 프로젝트" pickerLabel="프로젝트" placeholder="프로젝트를 선택하거나 주소를 검색하세요" />

        {!hasProject && (
          <p className="rounded-lg bg-[var(--surface-strong)] px-3 py-2 text-[11px] text-amber-400">
            프로젝트 정보 없음 — 위에서 프로젝트를 선택하거나, 부지/설계 분석을 먼저 진행하면 건축개요가 자동으로 채워집니다.
          </p>
        )}
        {hasDesign && (
          <p className="flex items-center gap-1.5 text-[11px] text-emerald-400"><Construction className="size-3.5 shrink-0" aria-hidden /> 설계(건축개요) 연동됨 — 도면/BIM 완성 시 항목별 정밀 적산으로 정확도가 향상됩니다.</p>
        )}
        {!hasDesign && gfaFromSite && !editedGfa && (
          <p className="flex items-center gap-1.5 text-[11px] text-amber-400"><DraftingCompass className="size-3.5 shrink-0" aria-hidden /> 설계 미완 — 부지면적 × 용적률로 연면적(GFA)을 추정해 초기값으로 제안합니다. 설계 완료 시 정밀 적산으로 자동 정확화됩니다.</p>
        )}

        {/* 건축개요 입력 */}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <label className="flex flex-col gap-1">
            <span className="flex items-center gap-1.5 text-[11px] font-semibold text-[var(--text-secondary)]">건축유형 {autoBt && <AutoBadge />}</span>
            <select value={bt} onChange={(e) => { setBt(e.target.value); setAutoBt(false); }} className={fcls}>{BUILDING_TYPES.map(([c, n]) => <option key={c} value={c}>{n}</option>)}</select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="flex items-center gap-1.5 text-[11px] font-semibold text-[var(--text-secondary)]">
              <Term label="연면적" hint="건물 전체 바닥면적의 합(GFA, Gross Floor Area). 지상+지하 모든 층 면적을 더한 값." />
              {autoGfa && !editedGfa && <AutoBadge />}{editedGfa && <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[9px] font-bold text-amber-400">수정됨</span>}
            </span>
            <div className="flex items-center gap-1.5"><NumberInput allowDecimal value={gfa} onChange={(n) => { setGfa(n ?? 0); setEditedGfa(true); }} className={fcls} /><span className="text-[11px] text-[var(--text-tertiary)]">㎡</span></div>
          </label>
          <label className="flex flex-col gap-1">
            <span className="flex items-center gap-1.5 text-[11px] font-semibold text-[var(--text-secondary)]">
              <Term label="구조" hint="건물 골조 방식. 철근콘크리트(RC)·철골철근콘크리트(SRC)·철골(SC)·프리캐스트(PC)·목구조 등. 구조에 따라 공사비가 달라집니다." />
              {autoBt && <AutoBadge />}
            </span>
            <select value={structure} onChange={(e) => setStructure(e.target.value)} className={fcls}>{STRUCTURES.map(([c, n]) => <option key={c} value={c}>{n}</option>)}</select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="flex items-center gap-1.5 text-[11px] font-semibold text-[var(--text-secondary)]">지상 층수 {autoFloors && <AutoBadge />}</span>
            <input type="number" value={floorsAbove} onChange={(e) => { setFloorsAbove(Number(e.target.value)); setAutoFloors(false); }} className={fcls} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold text-[var(--text-secondary)]">지하 층수</span>
            <input type="number" value={floorsBelow} onChange={(e) => setFloorsBelow(Number(e.target.value))} className={fcls} />
          </label>
        </div>
      </div>

      {/* ───────── Step 2: 개략 공사비 산정 ───────── */}
      <div className={sectionCls}>
        <StepHeader n={2} title="개략 공사비 산정" desc="건축개요로 지상·지하 공사비 + 조경·간접비(설계·감리·예비·일반관리)를 산정하고 최저~최대 예상 범위를 제시합니다." done={!!result} />

        <div className="flex flex-wrap items-center gap-3">
          <button onClick={calc} disabled={loading} className="rounded-xl bg-[var(--accent-strong)] px-8 py-3 text-sm font-black text-white shadow-[var(--shadow-glow)] hover:opacity-90 disabled:opacity-50">
            {loading ? "공사비 산정 중…" : "개략 공사비 산정 실행"}
          </button>
          {err && <span className="text-xs font-semibold text-rose-400">{err}</span>}
        </div>

        {result && (
          <>
            {/* 할루시네이션·오류 검증(공사비) */}
            <VerificationBadge
              analysisType="cost"
              context={{ inputs: { bt, gfa, floorsAbove, floorsBelow, structure }, result } as unknown as Record<string, unknown>}
              // 응답 최상위 ledger_hash(원장 sha256) — 피드백 조인키(미노출이면 undefined·안전).
              ledgerHash={(result as unknown as { ledger_hash?: string })?.ledger_hash}
            />
            <ExpertPanelCard
              analysisType="cost"
              context={{ inputs: { bt, gfa, floorsAbove, floorsBelow, structure }, result } as unknown as Record<string, unknown>}
            />
            {/* 총공사비 + range */}
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="cc-panel cc-bracketed cc-interactive border-[var(--accent-strong)]/30">
                <i className="cc-bracket cc-bracket--tl" />
                <i className="cc-bracket cc-bracket--br" />
                <div className="cc-grid-bg opacity-30" />
                <div className="relative cc-panel__body p-5 bg-[var(--accent-soft)]">
                  <p className="cc-label">총 공사비(기대)</p>
                  <p className="cc-num mt-2 text-2xl font-[1000] text-[var(--accent-strong)]">{fmtKrw(result.total_won)}</p>
                  <p className="mt-1 text-[11px] text-[var(--text-secondary)]">평당 <span className="cc-num">{result.per_pyeong_won.toLocaleString()}</span>원</p>
                </div>
              </div>
              <div className="cc-panel cc-bracketed cc-interactive">
                <i className="cc-bracket cc-bracket--tr" />
                <i className="cc-bracket cc-bracket--bl" />
                <div className="cc-grid-bg opacity-25" />
                <div className="relative cc-panel__body p-5">
                  <p className="cc-label">최저~최대 예상</p>
                  <p className="cc-num mt-2 text-lg font-[1000] text-[var(--text-primary)]">{fmtKrw(result.range.min_won)} ~ {fmtKrw(result.range.max_won)}</p>
                  <p className="mt-1 text-[11px] text-[var(--text-secondary)]">건설물가 변동 ±(설계변경 반영)</p>
                </div>
              </div>
              <div className="cc-panel cc-bracketed cc-interactive">
                <i className="cc-bracket cc-bracket--tr" />
                <i className="cc-bracket cc-bracket--bl" />
                <div className="cc-grid-bg opacity-25" />
                <div className="relative cc-panel__body p-5">
                  <p className="cc-label">규모</p>
                  <p className="mt-2 text-sm font-bold text-[var(--text-primary)]">연면적 <span className="cc-num">{result.total_gfa_sqm.toLocaleString()}</span>㎡</p>
                  <p className="mt-1 text-[11px] text-[var(--text-secondary)]">지상 <span className="cc-num">{result.gfa_above_sqm.toLocaleString()}</span> / 지하 <span className="cc-num">{result.gfa_below_sqm.toLocaleString()}</span>㎡</p>
                </div>
              </div>
            </div>

            {/* 항목별 분해 */}
            <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-5">
              <h3 className="mb-3 text-sm font-black text-[var(--text-primary)]">공사비 항목별 구조</h3>
              <div className="space-y-2">
                {breakdown.map(([label, v]) => {
                  const pct = result.total_won > 0 ? (v / result.total_won) * 100 : 0;
                  return (
                    <div key={label} className="flex items-center gap-3">
                      <span className="w-28 shrink-0 text-xs font-semibold text-[var(--text-secondary)]">{label}</span>
                      <div className="h-3 flex-1 overflow-hidden rounded-full bg-[var(--surface-muted)]"><div className="h-full rounded-full bg-[var(--accent-strong)]" style={{ width: `${Math.min(100, pct)}%` }} /></div>
                      <span className="w-24 shrink-0 text-right text-xs font-bold text-[var(--text-primary)]">{fmtKrw(v)}</span>
                      <span className="w-10 shrink-0 text-right text-[11px] text-[var(--text-tertiary)]">{pct.toFixed(0)}%</span>
                    </div>
                  );
                })}
              </div>
              <p className="mt-4 inline-flex flex-wrap items-center gap-1.5 rounded-lg bg-[var(--surface-soft)] px-3 py-2 text-[11px] text-[var(--accent-strong)]"><Link2 className="size-3.5 shrink-0" aria-hidden />이 공사비가 <b>수지분석·투자수익성(ROI)</b>에 자동 반영됩니다(단일 데이터원).</p>
            </div>

            {/* 산출 근거(EvidencePanel) — 백엔드 evidence가 있으면 우선, 없으면 응답 수치로 산식 트레이스(가짜값/가짜URL 0).
                "왜 이 공사비인가?"(기준단가·지상/지하/조경/간접 산식)에 답해 ROI 하류까지 근거를 남긴다. */}
            {(() => {
              const backendEvidence = adaptEvidence(result.evidence, result.legal_refs);
              const items: EvidenceItem[] = backendEvidence.length > 0 ? backendEvidence : [
                { label: "㎡당 기준단가", value: `${result.unit_cost_per_sqm.toLocaleString()}원/㎡`, basis: `용도(${result.building_type})·구조(${result.structure_type}) 표준 평단가` },
                { label: "지상 직접공사비", value: fmtKrw(result.aboveground_won), basis: `지상 연면적 ${Math.round(result.gfa_above_sqm).toLocaleString()}㎡ × 기준단가` },
                { label: "지하 직접공사비", value: fmtKrw(result.underground_won), basis: `지하 연면적 ${Math.round(result.gfa_below_sqm).toLocaleString()}㎡ × 기준단가(지하 할증)` },
                { label: "조경", value: fmtKrw(result.landscape_won), basis: "직접공사비 대비 표준 요율" },
                { label: "간접비(설계·감리·예비·일반관리)", value: fmtKrw(result.indirect_won), basis: "직접공사비 대비 표준 요율 합계" },
                { label: "총 공사비", value: fmtKrw(result.total_won), basis: `직접 ${fmtKrw(result.direct_won)} + 간접 ${fmtKrw(result.indirect_won)} · 범위 ${fmtKrw(result.range.min_won)}~${fmtKrw(result.range.max_won)}` },
              ];
              return <EvidencePanel className="mt-1" title="개략 공사비 산출 근거" items={items} />;
            })()}

            {/* 항목별 적산(QTO) 요약 — 부위별 정밀 물량은 BIM·적산(Step4)에 위임 */}
            {result.items && result.items?.length > 0 && (
              <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-5">
                <h3 className="mb-1 flex items-center gap-1.5 text-sm font-black text-[var(--text-primary)]">
                  <Term label="개략 적산" hint="QTO(Quantity Take-Off, 물량 산출)의 개략 버전. 건축개요로 역산한 표준 물량입니다. 부위별 정밀 물량은 BIM·적산(Step4)에서 실치수로 산출합니다." />
                </h3>
                <p className="mb-3 flex items-center gap-1.5 text-[11px] text-[var(--text-hint)]">{hasDesign ? (<><Construction className="size-3.5 shrink-0" aria-hidden /> 설계 연동 — 도면/BIM 완성 시 실 매스로 정밀화됩니다.</>) : "건축개요 기반 표준 적산. 설계 완성 시 정밀화."}</p>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-[10px] font-bold uppercase tracking-widest text-[var(--text-tertiary)]">
                        <th className="pb-2 pr-4">공종</th><th className="pb-2 pr-4">규격</th><th className="pb-2 pr-4 text-right">물량</th><th className="pb-2 pr-4">단위</th><th className="pb-2 text-right">금액</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(result.items ?? []).map((it, i) => (
                        <tr key={i} className="border-t border-[var(--line)]">
                          <td className="py-2 pr-4 font-semibold text-[var(--text-primary)]">{it.name}</td>
                          <td className="py-2 pr-4 text-[var(--text-tertiary)]">{it.spec || "-"}</td>
                          <td className="py-2 pr-4 text-right text-[var(--text-secondary)]">{it.quantity?.toLocaleString()}</td>
                          <td className="py-2 pr-4 text-[var(--text-tertiary)]">{it.unit || "-"}</td>
                          <td className="py-2 text-right font-bold text-[var(--text-primary)]">{fmtKrw(it.cost_won)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* 기하(geometry) 기반 정밀 적산 — 매스 치수에서 체적·표면적 산출 */}
            {result.geometry && (
              <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-5">
                <div className="mb-2 flex items-center gap-2">
                  <h3 className="text-sm font-black text-[var(--text-primary)]">기하(Geometry) 정밀 적산</h3>
                  {result.geometry.source === "bim"
                    ? <span className="inline-flex items-center gap-1 rounded bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold text-emerald-400"><Construction className="size-3" aria-hidden /> BIM 매스 실치수</span>
                    : <span className="rounded bg-[var(--surface-muted)] px-2 py-0.5 text-[10px] font-bold text-[var(--text-tertiary)]">개요 역산</span>}
                </div>
                <p className="mb-3 text-[11px] text-[var(--text-hint)]">
                  매스 {result.geometry.width_m}×{result.geometry.depth_m}m · 기준층 {result.geometry.footprint_sqm.toLocaleString()}㎡ · 둘레 {result.geometry.perimeter_m}m · 지상 {result.geometry.floors_above}/지하 {result.geometry.floors_below}층
                </p>
                <div className="grid gap-3 sm:grid-cols-3">
                  {[
                    ["콘크리트(체적)", `${result.geometry.concrete_m3.toLocaleString()} m³`],
                    ["철근(중량)", `${result.geometry.rebar_ton.toLocaleString()} ton`],
                    ["거푸집(면적)", `${result.geometry.formwork_m2.toLocaleString()} m²`],
                  ].map(([k, v]) => (
                    <div key={k} className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                      <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-hint)]">{k}</p>
                      <p className="mt-1 text-base font-[1000] text-[var(--text-primary)]">{v}</p>
                    </div>
                  ))}
                </div>
                <div className="mt-3 space-y-1.5">
                  {(result.geometry.items ?? []).map((it, i) => (
                    <div key={i} className="flex items-center justify-between text-xs">
                      <span className="text-[var(--text-secondary)]">{it.name} <span className="text-[var(--text-tertiary)]">{it.quantity?.toLocaleString()}{it.unit}</span></span>
                      <span className="font-bold text-[var(--text-primary)]">{fmtKrw(it.cost_won)}</span>
                    </div>
                  ))}
                  <div className="flex items-center justify-between border-t border-[var(--line)] pt-1.5 text-xs">
                    <span className="font-bold text-[var(--text-secondary)]">구조 직접공사비(기하)</span>
                    <span className="font-[1000] text-[var(--accent-strong)]">{fmtKrw(result.geometry.structural_direct_won)}</span>
                  </div>
                </div>
                <p className="mt-3 text-[11px] text-[var(--text-hint)]">※ 슬래브 체적·기둥보 환산·둘레×층고 외벽·지하 매트기초를 분리 산출. 설계(BIM) 매스가 있으면 실치수로 자동 정밀화됩니다.</p>
              </div>
            )}
          </>
        )}
      </div>

      {/* ───────── Step 3: 리스크 시뮬레이션(몬테카를로) ───────── */}
      <div className={sectionCls}>
        <StepHeader n={3} title="리스크 시뮬레이션 (몬테카를로)" desc="개략 공사비의 최저~최대 범위를 근거로 수천~수만 회 무작위 시뮬레이션해 공사비 분포(P10·P50·P90)와 신뢰구간을 산출합니다." done={!!risk} />

        {!result ? (
          <p className="rounded-lg bg-[var(--surface-strong)] px-3 py-2 text-[11px] text-[var(--text-secondary)]">
            먼저 Step 2의 개략 공사비를 산정하면, 그 결과(기대값·최저~최대 범위)로 리스크 시뮬레이션을 실행할 수 있습니다.
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1">
                <span className="flex items-center gap-1.5 text-[11px] font-semibold text-[var(--text-secondary)]">
                  <Term label="시뮬레이션 횟수" hint="몬테카를로 반복 횟수. 횟수가 많을수록 분포가 안정적입니다(1,000~50,000회)." />
                </span>
                <div className="flex items-center gap-1.5"><NumberInput value={iterations} onChange={(n) => setIterations(n ?? 10000)} className={`${fcls} w-40`} /><span className="text-[11px] text-[var(--text-tertiary)]">회</span></div>
              </label>
              <button onClick={runRisk} disabled={riskLoading} className="rounded-xl bg-[var(--accent-strong)] px-6 py-2.5 text-sm font-black text-white shadow-[var(--shadow-glow)] hover:opacity-90 disabled:opacity-50">
                {riskLoading ? "시뮬레이션 중…" : "리스크 시뮬레이션 실행"}
              </button>
              <span className="text-[11px] text-[var(--text-tertiary)]">입력은 Step 1·2의 자동연동 값으로 구동됩니다(별도 입력 불필요).</span>
            </div>

            {risk && (
              <>
                <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
                  {[
                    ["평균", fmtKrw(risk.mean)],
                    ["표준편차", fmtKrw(risk.stdDev)],
                    ["P10 (하위 10%)", fmtKrw(risk.p10)],
                    ["P50 (중앙값)", fmtKrw(risk.p50)],
                    ["P90 (상위 10%)", fmtKrw(risk.p90)],
                    ["시뮬레이션", `${risk.iterations.toLocaleString()}회`],
                  ].map(([k, v]) => (
                    <div key={k} className="cc-panel cc-bracketed p-3">
                      <i className="cc-bracket cc-bracket--tl" />
                      <div className="relative">
                        <p className="cc-label text-[9px]">{k}</p>
                        <p className="cc-num mt-1 text-sm font-[1000] text-[var(--text-primary)]">{v}</p>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="cc-panel cc-bracketed border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] p-4">
                  <i className="cc-bracket cc-bracket--tl" />
                  <i className="cc-bracket cc-bracket--br" />
                  <div className="relative">
                    <p className="cc-label">90% 신뢰구간</p>
                    <p className="cc-num mt-1 text-base font-[1000] text-[var(--accent-strong)]">{fmtKrw(risk.ci90[0])} ~ {fmtKrw(risk.ci90[1])}</p>
                  </div>
                </div>

                {/* 히스토그램 */}
                <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-5">
                  <h3 className="mb-3 text-sm font-black text-[var(--text-primary)]">비용 분포 히스토그램</h3>
                  <div className="space-y-2">
                    {(() => {
                      const maxCount = Math.max(...(risk.histogram ?? []).map((h) => h.count));
                      return (risk.histogram ?? []).map((bin, i) => {
                        const pct = maxCount > 0 ? (bin.count / maxCount) * 100 : 0;
                        return (
                          <div key={i} className="flex items-center gap-3">
                            <span className="w-32 shrink-0 text-[10px] text-[var(--text-tertiary)]">{fmtKrw(bin.binStart)} ~ {fmtKrw(bin.binEnd)}</span>
                            <div className="h-3 flex-1 overflow-hidden rounded-full bg-[var(--surface-muted)]"><div className="h-full rounded-full bg-[var(--accent-strong)]" style={{ width: `${pct}%` }} /></div>
                            <span className="w-10 shrink-0 text-right text-[11px] font-semibold text-[var(--text-secondary)]">{bin.count}</span>
                          </div>
                        );
                      });
                    })()}
                  </div>
                </div>

                <div className="rounded-xl bg-[var(--surface-strong)] p-4">
                  <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">리스크 요약</p>
                  <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">{risk.summary}</p>
                </div>
              </>
            )}
          </>
        )}
      </div>

      {/* ───────── Step 4: 정밀 적산(BIM 연계) ───────── */}
      <div className={sectionCls}>
        <StepHeader n={4} title="정밀 적산 (BIM 연계)" desc="여기까지는 건축개요로 산정한 개략 공사비입니다. 설계·BIM이 완성되면 실치수 기반 부위별 정밀 물량(QTO)으로 정확도를 한 단계 높일 수 있습니다." />

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-4">
            <p className="flex items-center gap-1.5 text-sm font-black text-[var(--text-primary)]">
              <Term label="개략 공사비 (여기)" hint="설계 역산·표준 단가 기반의 빠른 추정. 사업 초기 의사결정·수지/ROI 연동에 사용." />
            </p>
            <p className="mt-1 text-[11px] text-[var(--text-secondary)]">설계 역산 + 표준 단가. 빠르고 사업성 판단에 충분합니다.</p>
          </div>
          <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-4">
            <p className="flex items-center gap-1.5 text-sm font-black text-[var(--text-primary)]">
              <Term label="정밀 적산 (BIM·적산)" hint="3D 모델의 실치수에서 부위별 물량(QTO)을 산출하고 상세 내역서(BOQ)로 연결하는 정밀 단계." />
            </p>
            <p className="mt-1 text-[11px] text-[var(--text-secondary)]">3D 모델 실치수 → 부위별 물량(QTO) → 상세 내역서(BOQ). 중복이 아닌 정확도 상승 단계입니다.</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Link
            href={`/${locale}/bim-studio`}
            className="rounded-xl bg-[var(--accent-strong)] px-6 py-3 text-sm font-black text-white shadow-[var(--shadow-glow)] hover:opacity-90"
          >
            3D 모델·공사물량(BIM·적산)으로 정밀 적산하기 →
          </Link>
          <span className="text-[11px] text-[var(--text-tertiary)]">{hasDesign ? "설계 연동됨 — BIM·적산에서 부위별 정밀 물량을 확인하세요." : "설계/BIM 완성 후 정밀 적산이 가능합니다."}</span>
        </div>

        {/* T2: 상세 공내역서(실적기반) 진입 — 프로젝트 선택 컨텍스트(projectId)로 /projects/{id}/boq 연결. */}
        <div className="flex flex-wrap items-center gap-3 border-t border-[var(--line)] pt-4">
          {projectId ? (
            <Link
              href={`/${locale}/projects/${projectId}/boq`}
              className="rounded-xl border border-[var(--accent-strong)]/50 bg-[var(--accent-soft)] px-6 py-3 text-sm font-black text-[var(--accent-strong)] hover:opacity-90"
            >
              상세 공내역서(실적기반) 자동작성으로 이동 →
            </Link>
          ) : (
            <span className="rounded-xl border border-[var(--line)] px-6 py-3 text-sm font-bold text-[var(--text-hint)]">
              상세 공내역서(실적기반) — 프로젝트 선택 후 이용 가능
            </span>
          )}
          <span className="text-[11px] text-[var(--text-tertiary)]">건축개요 항목을 실적(표준품셈) 물량·단가로 자동 산출해 공내역서를 작성합니다.</span>
        </div>
      </div>
    </section>
  );
}
