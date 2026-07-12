"use client";

/**
 * 공사비(적산) 5단계 통합 허브 — 건축개요 기반(프로젝트 연동·지상/지하/조경/간접·최저~최대).
 *
 * 5-Step 구성(탭 구조는 page.tsx가 유지: overview/boq/alternatives/billing):
 *  ① 기준정보          — 프로젝트 자동연동(건축유형·연면적·구조·층수, 전부 수정 가능)
 *  ② 물량·개산         — /cost/estimate-overview(with_senior) 1회 호출(SSOT) → 범위·항목분해·QTO·기준선편차 → costData
 *  ③ 적산리스트        — 상세 내역서(BOQ) 탭 이동 + 저장된 적산 요약(GET /estimates) + BIM 정밀적산 CTA
 *  ④ AI 분석           — 시니어 적산(QS) 자문(SeniorVerdictCard) + 절감/설계변경 예측(alternatives 탭) 이동
 *  ⑤ 보고서·수지반영   — 적산 보고서 PDF/PPTX/DOCX 다운로드(POST /cost/{pid}/report) + 수지 반영 상태
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Construction, DraftingCompass, FileDown, Link2 } from "lucide-react";
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
import { SeniorVerdictCard, type SeniorConsultation } from "@/components/analysis/SeniorVerdictCard";
import { isValidLocale } from "@/i18n/config";

/** 페이지 탭 전환 콜백(page.tsx의 setTab) — 없으면 타 탭 링크는 비활성(방어적). */
type TabKey = "overview" | "boq" | "alternatives" | "billing";

/** 백엔드 base URL — LandScheduleClient.apiBase()와 동일 계약(프론트 호스트별 프록시/직결). */
function apiBase(): string {
  if (typeof window !== "undefined") {
    const h = window.location.hostname;
    if (h === "4t8t.net" || h === "www.4t8t.net" || h.endsWith(".pages.dev") || h === "propai.kr") {
      return "https://api.4t8t.net/api/v1";
    }
  }
  return "/api/proxy";
}

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
  items?: { name: string; spec?: string; unit?: string; quantity: number; unit_cost_won: number; cost_won: number; price_source?: string }[];
  qto_source?: string; // bim | derived
  // P1 T3: 기본형건축비 고시 대조(주택+평균전용면적 입력 시만, additive).
  baseline_check?: { baseline_won_per_sqm?: number; calc_won_per_sqm?: number; deviation_pct?: number | null; basis?: string; legal_link?: string; confidence?: string } | null;
  // P3: 시니어 적산(QS) 자문(with_senior opt-in 시만, additive).
  senior_consultation?: SeniorConsultation | null;
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

/** GET /cost/{pid}/estimates 목록 항목(저장된 적산 요약용). */
interface SavedEstimate {
  estimate_id: string;
  building_type?: string;
  structure_type?: string;
  total_gfa_sqm?: number;
  total_won?: number;
  confidence_grade?: string;
  created_at?: string;
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

// F-1: "59A"·"84B"·"114C" → 전용면적(㎡) 추정(앞 숫자). LiveProFormaStrip.tsx typeToArea와 동일 패턴
// (실패 시 0 — 평균 산출에서 스킵하기 위함, 발명 금지).
function typeToArea(t: string): number {
  const m = /(\d+(?:\.\d+)?)/.exec(t || "");
  return m ? Number(m[1]) : 0;
}

/** 항목 단가출처 요약("표준 N·DB M·fallback K") — 유의미하게 뽑을 수 있을 때만, 아니면 null(발명 금지). */
function summarizePriceTiers(items?: { price_source?: string }[]): string | null {
  if (!items || items.length === 0) return null;
  let std = 0, db = 0, fb = 0;
  for (const it of items) {
    const ps = (it.price_source ?? "").toString().toLowerCase();
    if (!ps || ps === "fallback") fb++;
    else if (ps === "standard" || ps.includes("표준") || ps.includes("품셈")) std++;
    else db++;
  }
  const parts: string[] = [];
  if (std) parts.push(`표준 ${std}`);
  if (db) parts.push(`DB ${db}`);
  if (fb) parts.push(`fallback ${fb}`);
  return parts.length ? parts.join("·") : null;
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
      <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-black ${done ? "bg-[var(--status-success)]/20 text-[var(--status-success)]" : "bg-[var(--accent-soft)] text-[var(--accent-strong)]"}`}>
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
  <span className="rounded bg-[var(--status-success)]/15 px-1.5 py-0.5 text-[9px] font-bold text-[var(--status-success)]">프로젝트에서 자동</span>
);

/** 상단 5단계 인디케이터 — "완료 여부"만 표시(현재 스크롤 위치 추적 아님), 클릭 시 해당 섹션으로 스크롤. */
function StepIndicator({ steps }: { steps: { n: number; label: string; done: boolean }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {steps.map((s) => (
        <button
          key={s.n}
          type="button"
          onClick={() => document.getElementById(`cost-step-${s.n}`)?.scrollIntoView({ behavior: "smooth", block: "start" })}
          className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-bold transition-colors ${
            s.done
              ? "border-[var(--status-success)]/40 bg-[var(--status-success)]/10 text-[var(--status-success)]"
              : "border-[var(--line-strong)] bg-[var(--surface-strong)] text-[var(--text-secondary)] hover:border-[var(--accent-strong)]"
          }`}
        >
          <span className={`flex h-4 w-4 items-center justify-center rounded-full text-[9px] font-black ${s.done ? "bg-[var(--status-success)]/25" : "bg-[var(--surface-muted)]"}`}>
            {s.done ? "✓" : s.n}
          </span>
          {s.label}
        </button>
      ))}
    </div>
  );
}

export function CostEstimationClient({ onNavigateTab }: { onNavigateTab?: (tab: TabKey) => void } = {}) {
  const params = useParams() as { locale?: string };
  const locale = isValidLocale(params?.locale ?? "") ? (params.locale as string) : "ko";

  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const designData = useProjectContextStore((s) => s.designData);
  const projectId = useProjectContextStore((s) => s.projectId);
  const projectName = useProjectContextStore((s) => s.projectName);
  const updateCostData = useProjectContextStore((s) => s.updateCostData);
  // F-4: 절감 시나리오·설계변경 예측 카드가 적재한 원응답 — 보고서(⑤) 조립 시 있으면 동봉.
  const costData = useProjectContextStore((s) => s.costData);

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
  // F-1: 평균 전용면적(㎡) — 주택(아파트) baseline_check(기본형건축비 대조) 입력. 미입력 시 대조 생략(정직).
  const [avgUnitSqm, setAvgUnitSqm] = useState<number>(0);
  const [autoAvgUnitSqm, setAutoAvgUnitSqm] = useState(false);
  const [editedAvgUnitSqm, setEditedAvgUnitSqm] = useState(false);

  // ② 리스크 시뮬레이션(몬테카를로) — 개산 결과의 최저~최대 범위 기반.
  const [iterations, setIterations] = useState(10000);
  const [risk, setRisk] = useState<RiskResult | null>(null);
  const [riskLoading, setRiskLoading] = useState(false);

  // ③ 저장된 적산 요약(GET /cost/{pid}/estimates 최근 목록).
  const [savedList, setSavedList] = useState<SavedEstimate[]>([]);

  // ⑤ 보고서 다운로드 상태.
  const [reportBusy, setReportBusy] = useState<string | null>(null);
  const [reportNotice, setReportNotice] = useState<{ kind: "info" | "warn"; text: string } | null>(null);

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

  // F-1: 평균 전용면적(㎡) 폴백 추정 — 설계 유닛믹스(designData.unitTypes, 예: ["59A","84A"])의
  // 평형 코드 앞 숫자를 평균(무날조 — 실존 필드만·부재 시 0으로 수동입력 유도).
  const estimatedAvgUnitSqmFromDesign = useMemo(() => {
    const types = designData?.unitTypes;
    if (!types || types.length === 0) return 0;
    const areas = types.map(typeToArea).filter((a) => a > 0);
    if (areas.length === 0) return 0;
    return Math.round((areas.reduce((s, a) => s + a, 0) / areas.length) * 10) / 10;
  }, [designData?.unitTypes]);

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
    // F-1: 주택(아파트)일 때만 평균 전용면적 자동프리필(BE baseline_check 판정조건과 동일).
    if (bt === "apartment" && estimatedAvgUnitSqmFromDesign > 0 && !editedAvgUnitSqm) {
      setAvgUnitSqm(estimatedAvgUnitSqmFromDesign); setAutoAvgUnitSqm(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, designData, estimatedGfaFromSite, bt, estimatedAvgUnitSqmFromDesign, editedAvgUnitSqm]);

  // ③ 저장된 적산 목록 조회(프로젝트 있을 때만·조용한 실패).
  useEffect(() => {
    if (!projectId) { setSavedList([]); return; }
    let cancelled = false;
    void apiClient
      .get<{ ok: boolean; items: SavedEstimate[] }>(`/cost/${projectId}/estimates`, { useMock: false, timeoutMs: 20000 })
      .then((r) => { if (!cancelled) setSavedList(r.items ?? []); })
      .catch(() => { /* 목록 조회 실패는 조용히 무시 — 개산 본 기능은 계속 이용 가능 */ });
    return () => { cancelled = true; };
  }, [projectId]);

  const calc = useCallback(async () => {
    if (!gfa || gfa <= 0) { setErr("연면적(GFA)을 입력하세요(프로젝트 선택 시 자동 반영)."); return; }
    setLoading(true); setErr(""); setRisk(null);
    try {
      const r = await apiClient.post<Overview>("/cost/estimate-overview", {
        body: {
          building_type: bt, total_gfa_sqm: gfa, floor_count_above: floorsAbove, floor_count_below: floorsBelow, structure_type: structure, project_id: projectId || undefined, with_senior: true,
          // F-1: 주택(아파트)+양수 입력일 때만 전송 — BE baseline_check가 이 조합에서만 대조를 산출.
          avg_unit_sqm: bt === "apartment" && avgUnitSqm > 0 ? avgUnitSqm : undefined,
        },
        useMock: false, timeoutMs: 30000,
      });
      setResult(r);
      // 수지·사업성 연동: 컨텍스트에 공사비 저장(P5 additive 필드 병기 — 무회귀).
      updateCostData({
        totalConstructionCostWon: r.total_won, perSqmWon: r.unit_cost_per_sqm, perPyeongWon: r.per_pyeong_won,
        abovegroundWon: r.aboveground_won, undergroundWon: r.underground_won, landscapeWon: r.landscape_won,
        directWon: r.direct_won, indirectWon: r.indirect_won,
        rangeMinWon: r.range.min_won, rangeMaxWon: r.range.max_won, source: "overview",
        qtoSource: r.qto_source ?? null,
        priceTierSummary: summarizePriceTiers(r.items),
        baselineDeviationPct: r.baseline_check?.deviation_pct ?? null,
      });
    } catch {
      setErr("공사비 산정에 실패했습니다. 입력값을 확인하세요.");
    } finally { setLoading(false); }
  }, [bt, gfa, floorsAbove, floorsBelow, structure, projectId, avgUnitSqm, updateCostData]);

  // 모세혈관: 부지·설계(업스트림)가 갱신되면 이미 산정된 공사비를 1회 자동 재계산.
  // 백엔드 호출이라 과도호출 금지 — 결과가 있고(hasResult) 로딩 중이 아닐 때만(enabled).
  useStageAutoRecalc("cost", calc, { enabled: !loading, hasResult: !!result });

  // ②: 개략 산정 결과의 기대공사비와 최저~최대 레인지를 근거로 몬테카를로 시뮬레이션.
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

  // ⑤: 적산 보고서 다운로드(POST /cost/{pid}/report?format=) — LandScheduleClient.downloadReport 패턴.
  // F-4: 부분조립 해소 — ①최신 영속 BOQ(저장된 적산 목록 ③의 최신 1건)를 조회해 동봉,
  //   ②절감 시나리오·설계변경 예측 카드가 store에 적재한 원응답이 있으면 함께 동봉(부재 시 생략 — 정직).
  const downloadReport = useCallback(async (format: "pdf" | "pptx" | "docx") => {
    if (!result) { setReportNotice({ kind: "warn", text: "먼저 ②에서 개략 공사비를 산정하세요." }); return; }
    setReportBusy(format); setReportNotice(null);
    try {
      // 최신 영속 BOQ — savedList는 GET /estimates(최신순) 결과라 상단 1건이 최신.
      let boq: Record<string, unknown> | undefined;
      const latestEstimateId = savedList[0]?.estimate_id;
      if (latestEstimateId) {
        try {
          boq = await apiClient.get<Record<string, unknown>>(
            `/cost/estimate/${latestEstimateId}`, { useMock: false, timeoutMs: 20000 },
          );
        } catch { /* BOQ 조회 실패는 무시 — overview만으로 보고서 생성 계속(정직 생략) */ }
      }
      const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
      const res = await fetch(`${apiBase()}/cost/${projectId || "default"}/report?format=${format}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({
          project_name: projectName || "적산 보고서",
          overview: result,
          senior_consultation: result.senior_consultation ?? undefined,
          boq: boq ?? undefined,
          saving_scenarios: costData?.costSavingScenarios ?? undefined,
          change_forecast: costData?.costChangeForecast ?? undefined,
        }),
      });
      const ct = res.headers.get("content-type") || "";
      if (!res.ok || ct.includes("json")) throw new Error();  // 성공=바이너리, 실패=JSON
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `적산보고서_${projectName || "프로젝트"}.${format}`; a.click();
      URL.revokeObjectURL(url);
      setReportNotice({ kind: "info", text: `적산 보고서를 생성했습니다 — ${format.toUpperCase()}(요약·항목분해·공종리스트·시니어 QS 자문 포함).` });
    } catch {
      setReportNotice({ kind: "warn", text: "적산 보고서 생성에 실패했습니다. 잠시 후 다시 시도하세요." });
    } finally { setReportBusy(null); }
  }, [result, projectId, projectName, savedList, costData]);

  const breakdown = useMemo(() => result ? [
    ["지상 직접공사비", result.aboveground_won],
    ["지하 직접공사비", result.underground_won],
    ["조경", result.landscape_won],
    ["설계비", result.design_fee_won],
    ["감리비", result.supervision_fee_won],
    ["예비비(설계변경)", result.contingency_won],
    ["일반관리비", result.general_expense_won],
  ] as [string, number][] : [], [result]);

  const sectionCls = "grid gap-5 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-6 scroll-mt-24";

  const steps = useMemo(() => [
    { n: 1, label: "기준정보", done: hasProject || gfa > 0 },
    { n: 2, label: "물량·개산", done: !!result },
    { n: 3, label: "적산리스트", done: savedList.length > 0 },
    { n: 4, label: "AI 분석", done: !!result?.senior_consultation },
    { n: 5, label: "보고서·수지반영", done: reportNotice?.kind === "info" },
  ], [hasProject, gfa, result, savedList.length, reportNotice]);

  return (
    <section className="grid grid-cols-1 gap-8 min-w-0">
      {/* 헤더 */}
      <div>
        <div className="flex items-center gap-3 mb-1.5">
          <span className="cc-meta">COST · WORKFLOW</span>
          {result && <span className="cc-live"><i />ESTIMATED</span>}
        </div>
        <h1 className="text-2xl font-black text-[var(--text-primary)]">적산·공사비 관리 (5단계 통합)</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          기준정보 자동연동 → 물량·개산 → 적산리스트 → AI 분석 → 보고서·수지반영까지 한 흐름으로 진행합니다.
          결과는 <b className="text-[var(--text-primary)]">수지분석·투자수익성(ROI)과 자동 연동</b>됩니다. 자동 값도 모두 수정 가능합니다.
        </p>
        <div className="mt-3">
          <StepIndicator steps={steps} />
        </div>
      </div>

      {/* ───────── ① 기준정보(자동연동) ───────── */}
      <div id="cost-step-1" className={sectionCls}>
        <StepHeader n={1} title="기준정보 (자동연동)" desc="설계·부지 분석에서 건축개요를 자동으로 불러옵니다. 모든 값은 수정할 수 있습니다." />

        {hasProject ? (
          <div className="rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-4 py-3">
            <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">분석 대상 프로젝트</p>
            <p className="mt-1 text-base font-black text-[var(--accent-strong)]">{projectName || "이름 없는 프로젝트"}</p>
          </div>
        ) : null}

        <ProjectAddressInput value={pickerAddr} onChange={setPickerAddr} label="분석 대상 프로젝트" pickerLabel="프로젝트" placeholder="프로젝트를 선택하거나 주소를 검색하세요" />

        {!hasProject && (
          <p className="rounded-lg bg-[var(--surface-strong)] px-3 py-2 text-[11px] text-[var(--status-warning)]">
            프로젝트 정보 없음 — 위에서 프로젝트를 선택하거나, 부지/설계 분석을 먼저 진행하면 건축개요가 자동으로 채워집니다.
          </p>
        )}
        {hasDesign && (
          <p className="flex items-center gap-1.5 text-[11px] text-[var(--status-success)]"><Construction className="size-3.5 shrink-0" aria-hidden /> 설계(건축개요) 연동됨 — 도면/BIM 완성 시 항목별 정밀 적산으로 정확도가 향상됩니다.</p>
        )}
        {!hasDesign && gfaFromSite && !editedGfa && (
          <p className="flex items-center gap-1.5 text-[11px] text-[var(--status-warning)]"><DraftingCompass className="size-3.5 shrink-0" aria-hidden /> 설계 미완 — 부지면적 × 용적률로 연면적(GFA)을 추정해 초기값으로 제안합니다. 설계 완료 시 정밀 적산으로 자동 정확화됩니다.</p>
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
              {autoGfa && !editedGfa && <AutoBadge />}{editedGfa && <span className="rounded bg-[var(--status-warning)]/15 px-1.5 py-0.5 text-[9px] font-bold text-[var(--status-warning)]">수정됨</span>}
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
          {/* F-1: 주택(아파트)일 때만 노출 — BE baseline_check(기본형건축비 대조) 판정조건과 동일. */}
          {bt === "apartment" && (
            <label className="flex flex-col gap-1">
              <span className="flex items-center gap-1.5 text-[11px] font-semibold text-[var(--text-secondary)]">
                <Term label="평균 전용면적" hint="세대별 전용면적의 평균값(㎡). 기본형건축비 고시 대조·시니어 QS 자문에 사용됩니다. 미입력 시 대조가 생략됩니다." />
                {autoAvgUnitSqm && !editedAvgUnitSqm && <AutoBadge />}
                {editedAvgUnitSqm && <span className="rounded bg-[var(--status-warning)]/15 px-1.5 py-0.5 text-[9px] font-bold text-[var(--status-warning)]">수정됨</span>}
              </span>
              <div className="flex items-center gap-1.5">
                <NumberInput allowDecimal value={avgUnitSqm} onChange={(n) => { setAvgUnitSqm(n ?? 0); setEditedAvgUnitSqm(true); }} className={fcls} />
                <span className="text-[11px] text-[var(--text-tertiary)]">㎡</span>
              </div>
            </label>
          )}
        </div>
      </div>

      {/* ───────── ② 물량·개산 ───────── */}
      <div id="cost-step-2" className={sectionCls}>
        <StepHeader n={2} title="물량·개산" desc="건축개요로 지상·지하 공사비 + 조경·간접비(설계·감리·예비·일반관리)를 산정하고 최저~최대 예상 범위·물량 산출(QTO)·기준선 대조를 제시합니다." done={!!result} />

        <div className="flex flex-wrap items-center gap-3">
          <button onClick={calc} disabled={loading} className="rounded-xl bg-[var(--accent-strong)] px-8 py-3 text-sm font-black text-white shadow-[var(--shadow-glow)] hover:opacity-90 disabled:opacity-50">
            {loading ? "공사비 산정 중…" : "개략 공사비 산정 실행"}
          </button>
          {err && <span className="text-xs font-semibold text-[var(--status-error)]">{err}</span>}
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

            {/* QTO 물량 산출 배지 + 기본형건축비 대조(baseline_check) — 있을 때만(정직). */}
            <div className="flex flex-wrap items-center gap-2">
              <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-bold ${result.qto_source === "bim" ? "bg-[var(--status-success)]/15 text-[var(--status-success)]" : "bg-[var(--surface-muted)] text-[var(--text-tertiary)]"}`}>
                <Construction className="size-3" aria-hidden />
                물량 산출(QTO): {result.qto_source === "bim" ? "BIM 실치수" : "개요 역산(derived)"}
              </span>
              {result.baseline_check && result.baseline_check.deviation_pct != null && (
                <span
                  title={result.baseline_check.basis || undefined}
                  className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-bold ${Math.abs(result.baseline_check.deviation_pct) > 15 ? "bg-[var(--status-warning)]/15 text-[var(--status-warning)]" : "bg-[var(--surface-muted)] text-[var(--text-secondary)]"}`}
                >
                  기본형건축비 대비 {result.baseline_check.deviation_pct >= 0 ? "+" : ""}{result.baseline_check.deviation_pct}%
                </span>
              )}
            </div>

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
                      <span className="w-24 shrink-0 text-right font-mono text-xs font-bold text-[var(--text-primary)]">{fmtKrw(v)}</span>
                      <span className="w-10 shrink-0 text-right font-mono text-[11px] text-[var(--text-tertiary)]">{pct.toFixed(0)}%</span>
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

            {/* 항목별 적산(QTO) 요약 — 부위별 정밀 물량은 상세 내역서(③)에 위임 */}
            {result.items && result.items?.length > 0 && (
              <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-5">
                <h3 className="mb-1 flex items-center gap-1.5 text-sm font-black text-[var(--text-primary)]">
                  <Term label="개략 적산" hint="QTO(Quantity Take-Off, 물량 산출)의 개략 버전. 건축개요로 역산한 표준 물량입니다. 부위별 정밀 물량은 상세 내역서(BOQ)에서 실치수로 산출합니다." />
                </h3>
                <p className="mb-3 flex items-center gap-1.5 text-[11px] text-[var(--text-hint)]">{hasDesign ? (<><Construction className="size-3.5 shrink-0" aria-hidden /> 설계 연동 — 도면/BIM 완성 시 실 매스로 정밀화됩니다.</>) : "건축개요 기반 표준 적산. 설계 완성 시 정밀화."}</p>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-tertiary)]">
                        <th className="pb-2 pr-4">공종</th><th className="pb-2 pr-4">규격</th><th className="pb-2 pr-4 text-right">물량</th><th className="pb-2 pr-4">단위</th><th className="pb-2 text-right">금액</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(result.items ?? []).map((it, i) => (
                        <tr key={i} className="border-t border-[var(--line)] transition-colors hover:bg-[var(--accent-strong)]/5">
                          <td className="py-2 pr-4 font-semibold text-[var(--text-primary)]">{it.name}</td>
                          <td className="py-2 pr-4 text-[var(--text-tertiary)]">{it.spec || "-"}</td>
                          <td className="py-2 pr-4 text-right font-mono text-[var(--text-secondary)]">{it.quantity?.toLocaleString()}</td>
                          <td className="py-2 pr-4 text-[var(--text-tertiary)]">{it.unit || "-"}</td>
                          <td className="py-2 text-right font-mono font-bold text-[var(--text-primary)]">{fmtKrw(it.cost_won)}</td>
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
                    ? <span className="inline-flex items-center gap-1 rounded bg-[var(--status-success)]/15 px-2 py-0.5 text-[10px] font-bold text-[var(--status-success)]"><Construction className="size-3" aria-hidden /> BIM 매스 실치수</span>
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

            {/* 리스크 시뮬레이션(몬테카를로) — 개산 범위를 근거로 분포(P10·P50·P90)·신뢰구간 산출(개산의 부속 분석). */}
            <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-5">
              <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
                <div>
                  <h3 className="flex items-center gap-1.5 text-sm font-black text-[var(--text-primary)]">
                    <Term label="리스크 시뮬레이션 (몬테카를로)" hint="개략 공사비의 최저~최대 범위를 근거로 수천~수만 회 무작위 시뮬레이션해 공사비 분포(P10·P50·P90)와 신뢰구간을 산출합니다." />
                  </h3>
                  <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">입력은 위 개산 결과(기대값·최저~최대 범위)로 구동됩니다(별도 입력 불필요).</p>
                </div>
                <div className="flex flex-wrap items-end gap-2">
                  <label className="flex flex-col gap-1">
                    <span className="text-[10px] font-semibold text-[var(--text-tertiary)]">시뮬레이션 횟수</span>
                    <div className="flex items-center gap-1.5"><NumberInput value={iterations} onChange={(n) => setIterations(n ?? 10000)} className={`${fcls} w-36`} /><span className="text-[11px] text-[var(--text-tertiary)]">회</span></div>
                  </label>
                  <button onClick={runRisk} disabled={riskLoading} className="rounded-xl bg-[var(--accent-strong)] px-5 py-2.5 text-xs font-black text-white shadow-[var(--shadow-glow)] hover:opacity-90 disabled:opacity-50">
                    {riskLoading ? "시뮬레이션 중…" : "리스크 시뮬레이션 실행"}
                  </button>
                </div>
              </div>

              {risk && (
                <div className="grid gap-3">
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
                  <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5">
                    <h4 className="mb-3 text-sm font-black text-[var(--text-primary)]">비용 분포 히스토그램</h4>
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

                  <p className="rounded-xl bg-[var(--surface-soft)] px-4 py-3 text-sm leading-7 text-[var(--text-secondary)]">{risk.summary}</p>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* ───────── ③ 적산리스트 ───────── */}
      <div id="cost-step-3" className={sectionCls}>
        <StepHeader n={3} title="적산리스트" desc="상세 내역서(BOQ)에서 공종별 물량·단가·금액을 산출하고, 설계·BIM이 완성되면 실치수 기반 정밀 물량(QTO)으로 정확도를 높입니다." done={savedList.length > 0} />

        <div className="flex flex-wrap items-center gap-3">
          {onNavigateTab ? (
            <button
              onClick={() => onNavigateTab("boq")}
              className="rounded-xl bg-[var(--accent-strong)] px-6 py-3 text-sm font-black text-white shadow-[var(--shadow-glow)] hover:opacity-90"
            >
              상세 내역서(BOQ) 탭으로 이동 →
            </button>
          ) : (
            <span className="rounded-xl border border-[var(--line)] px-6 py-3 text-sm font-bold text-[var(--text-hint)]">상세 내역서(BOQ) — 상단 탭에서 이용</span>
          )}
          <span className="text-[11px] text-[var(--text-tertiary)]">건축개요 항목을 실적(표준품셈) 물량·단가로 자동 산출해 공내역서를 작성합니다.</span>
        </div>

        {/* 저장된 적산 요약(최근 1~2건) — 영속화된 BOQ 목록. */}
        <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-5">
          <h3 className="mb-2 text-sm font-black text-[var(--text-primary)]">저장된 적산 요약</h3>
          {!hasProject ? (
            <p className="text-[11px] text-[var(--text-hint)]">프로젝트를 선택하면 저장된 적산 목록을 요약합니다.</p>
          ) : savedList.length === 0 ? (
            <p className="text-[11px] text-[var(--text-hint)]">저장된 적산이 없습니다. 상세 내역서(BOQ) 탭에서 적산을 실행하면 자동 저장됩니다.</p>
          ) : (
            <ul className="grid gap-2">
              {savedList.slice(0, 2).map((it) => (
                <li key={it.estimate_id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--line)]/60 bg-[var(--surface-soft)] px-4 py-2.5 text-[11px] text-[var(--text-secondary)]">
                  <span>
                    {it.building_type || "-"} · {it.structure_type || "-"} · {it.total_gfa_sqm ? `${Math.round(it.total_gfa_sqm).toLocaleString()}㎡` : "-"} ·{" "}
                    <b className="text-[var(--text-primary)]">{fmtKrw(it.total_won)}</b>
                    {it.confidence_grade ? ` · 신뢰등급 ${it.confidence_grade}` : ""}
                    {it.created_at ? ` · ${new Date(it.created_at).toLocaleDateString("ko-KR")}` : ""}
                  </span>
                </li>
              ))}
              {savedList.length > 2 && (
                <li className="text-[10px] text-[var(--text-hint)]">외 {savedList.length - 2}건 — 상세 내역서(BOQ) 탭에서 전체 확인</li>
              )}
            </ul>
          )}
        </div>

        {/* 정밀 적산(BIM) CTA — 3D 모델 실치수 → 부위별 물량(QTO) → 상세 내역서(BOQ). */}
        <div className="flex flex-wrap items-center gap-3 border-t border-[var(--line)] pt-4">
          <Link
            href={`/${locale}/bim-studio`}
            className="rounded-xl border border-[var(--accent-strong)]/50 bg-[var(--accent-soft)] px-6 py-3 text-sm font-black text-[var(--accent-strong)] hover:opacity-90"
          >
            3D 모델·공사물량(BIM·적산)으로 정밀 적산하기 →
          </Link>
          <span className="text-[11px] text-[var(--text-tertiary)]">{hasDesign ? "설계 연동됨 — BIM·적산에서 부위별 정밀 물량을 확인하세요." : "설계/BIM 완성 후 정밀 적산이 가능합니다."}</span>
        </div>
      </div>

      {/* ───────── ④ AI 분석 ───────── */}
      <div id="cost-step-4" className={sectionCls}>
        <StepHeader n={4} title="AI 분석" desc="시니어 적산(QS) 전문가 자문(법정요율 상한·기준선편차·예비비·단가 신뢰도)과 절감/설계변경 예측을 확인합니다." done={!!result?.senior_consultation} />

        {result?.senior_consultation ? (
          <SeniorVerdictCard consultation={result.senior_consultation} title="시니어 적산(QS) 자문" defaultOpen />
        ) : (
          <p className="rounded-lg bg-[var(--surface-strong)] px-3 py-2 text-[11px] text-[var(--text-secondary)]">
            {result
              ? "이 개산에서는 정량 자문을 산출할 입력(주택+평균전용면적 등)이 충분하지 않아 시니어 QS 자문이 첨부되지 않았습니다(정직 표기)."
              : "먼저 ②에서 개략 공사비를 산정하면 시니어 QS 자문이 함께 산출됩니다."}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-3">
          {onNavigateTab ? (
            <button
              onClick={() => onNavigateTab("alternatives")}
              className="rounded-xl border border-[var(--accent-strong)]/50 bg-[var(--accent-soft)] px-6 py-3 text-sm font-black text-[var(--accent-strong)] hover:opacity-90"
            >
              절감 시나리오 · 설계변경 예측 보기 →
            </button>
          ) : (
            <span className="rounded-xl border border-[var(--line)] px-6 py-3 text-sm font-bold text-[var(--text-hint)]">절감/설계변경 예측 — 상단 &ldquo;대안 설계 원가비교&rdquo; 탭에서 이용</span>
          )}
          <span className="text-[11px] text-[var(--text-tertiary)]">대안 설계 원가비교 탭에서 절감 Top-N·설계변경 예측공사비를 산출합니다.</span>
        </div>
      </div>

      {/* ───────── ⑤ 보고서·수지반영 ───────── */}
      <div id="cost-step-5" className={sectionCls}>
        <StepHeader n={5} title="보고서·수지반영" desc="가용 산출(개산·QTO·시니어 QS 자문)을 종합 보고서로 내보내고, 공사비를 수지분석에 반영합니다." done={reportNotice?.kind === "info"} />

        {!result ? (
          <p className="rounded-lg bg-[var(--surface-strong)] px-3 py-2 text-[11px] text-[var(--text-secondary)]">
            먼저 ②에서 개략 공사비를 산정하면 보고서를 생성할 수 있습니다.
          </p>
        ) : (
          <>
            <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-5">
              <h3 className="mb-1 flex items-center gap-1.5 text-sm font-black text-[var(--text-primary)]"><FileDown className="size-4 text-[var(--accent-strong)]" aria-hidden /> 적산 보고서 다운로드</h3>
              <p className="mb-3 text-[11px] text-[var(--text-hint)]">요약 KPI·항목별 원가 분해·공종 적산 리스트·시니어 QS 자문을 하나의 문서로 조립합니다(가용 산출만·부재 섹션 생략).</p>
              <div className="flex flex-wrap items-center gap-2">
                {(["pdf", "pptx", "docx"] as const).map((fmt) => (
                  <button
                    key={fmt}
                    onClick={() => void downloadReport(fmt)}
                    disabled={!!reportBusy}
                    className="rounded-xl border border-[var(--accent-strong)]/50 bg-[var(--accent-soft)] px-5 py-2.5 text-xs font-black uppercase text-[var(--accent-strong)] hover:opacity-90 disabled:opacity-50"
                  >
                    {reportBusy === fmt ? "생성 중…" : fmt}
                  </button>
                ))}
                {reportNotice && (
                  <span className={`text-[11px] font-semibold ${reportNotice.kind === "info" ? "text-[var(--status-success)]" : "text-[var(--status-error)]"}`}>{reportNotice.text}</span>
                )}
              </div>
            </div>

            {/* 수지 반영 상태 — ②의 calc()가 매 산정마다 costData를 자동 주입하므로 별도 버튼 없이 상태만 표기(과설계 금지). */}
            <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] px-5 py-4">
              <Link2 className="size-4 shrink-0 text-[var(--status-success)]" aria-hidden />
              <span className="text-[11px] font-bold text-[var(--status-success)]">이미 반영됨</span>
              <span className="text-[11px] text-[var(--text-secondary)]">②의 개략 공사비(총·직접·간접·범위·물량출처·기준선편차)가 수지분석·투자수익성(ROI) 공통 컨텍스트에 자동 주입되었습니다(단일 데이터원).</span>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
