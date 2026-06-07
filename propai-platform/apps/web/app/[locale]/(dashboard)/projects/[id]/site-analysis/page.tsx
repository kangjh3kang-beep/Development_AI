"use client";

import React, { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";
import { motion, AnimatePresence } from "framer-motion";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { NextStageCta } from "@/components/projects/NextStageCta";
import { LandIntelligencePanel } from "@/components/projects/LandIntelligencePanel";
import { SiteInitiator } from "@/components/projects/SiteInitiator";
import { ProjectSiteAnalysisWorkspaceClient } from "@/components/projects/ProjectSiteAnalysisWorkspaceClient";
import { TerrainAnalysisPanel } from "@/components/terrain/TerrainAnalysisPanel";
import { EnvironmentAnalysisPanel } from "@/components/environment/EnvironmentAnalysisPanel";
import { isValidLocale, type Locale } from "@/i18n/config";
import { useDictionary } from "@/hooks/use-dictionary";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore, type SiteAnalysisData } from "@/store/useProjectContextStore";

// 가상준공 3D 디지털트윈 씬 — @react-three/fiber. SSR/1102 회피 위해 ssr:false 동적 마운트.
const DigitalTwinScene = dynamic(() => import("@/components/digital-twin/DigitalTwinScene"), {
  ssr: false,
  loading: () => (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-8 text-center text-sm text-[var(--text-hint)]">
      가상준공 3D 트윈 불러오는 중…
    </div>
  ),
});

// 주변 실거래 지도(Leaflet) — window.L 동적 로드라 ssr:false 마운트.
const NearbyTransactionsMap = dynamic(
  () => import("@/components/map/NearbyTransactionsMap").then((m) => m.NearbyTransactionsMap),
  {
    ssr: false,
    loading: () => (
      <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-8 text-center text-sm text-[var(--text-hint)]">
        주변 실거래 지도 불러오는 중…
      </div>
    ),
  },
);

type IconProps = React.SVGAttributes<SVGElement>;

const Icons = {
  Cpu: (props: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><rect width="16" height="16" x="4" y="4" rx="2"/><rect width="6" height="6" x="9" y="9" rx="1"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/></svg>,
  Brain: (props: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 4.44-2.54Z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-4.44-2.54Z"/></svg>,
  Database: (props: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5V19A9 3 0 0 0 21 19V5"/><path d="M3 12A9 3 0 0 0 21 12"/></svg>,
  Map: (props: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"/><line x1="9" x2="9" y1="3" y2="18"/><line x1="15" x2="15" y1="6" y2="21"/></svg>,
  Search: (props: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>,
  Sparkles: (props: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><path d="m12 3 1.912 5.813a2 2 0 0 0 1.275 1.275L21 12l-5.813 1.912a2 2 0 0 0-1.275 1.275L12 21l-1.912-5.813a2 2 0 0 0-1.275-1.275L3 12l5.813-1.912a2 2 0 0 0 1.275-1.275L12 3Z"/><path d="M5 3v4"/><path d="M19 17v4"/><path d="M3 5h4"/><path d="M17 19h4"/></svg>,
};

// ── L3 Enhanced Types ──
type NearbyTransactionSummary = {
  avg_price_10k: number;
  max_price_10k: number;
  min_price_10k: number;
  count: number;
  items: Array<{ price_10k: string; area_sqm: string; deal_date: string; name: string; floor: string }>;
};

type InfrastructureData = {
  nearest_subway: { name: string; distance_m: number } | null;
  schools: Array<{ name: string; type: string; distance_m: number }>;
};

type BuildingDetail = {
  main_purpose: string;
  structure: string;
  total_area_sqm: number;
  ground_floors: number;
  underground_floors: number;
  use_approval_date: string;
  building_name: string;
  // 표제부 대장 데이터(표시 전용, 백엔드 building_detail에 동봉되면 자동 노출)
  household_count?: number;
  household_count_display?: string;
  family_count?: number;
  ho_count?: number;
  ho_count_display?: string;
  dong_count?: number;
  dong_count_display?: string;
  title_status?: string;
  is_demolished?: boolean;
  demolition_date?: string;
  demolition_basis?: string;
  is_uncompleted?: boolean;
  uncompleted_basis?: string;
  data_source?: string;
};

// 실효용적률 계층(법정범위→조례→계획상한→인센티브) 상세 메타
type FarBasisDetail = {
  법정범위?: { min_far_pct?: number | null; max_far_pct?: number | null; max_bcr_pct?: number | null } | null;
  조례값?: { far_pct?: number | null; bcr_pct?: number | null; confirmed?: boolean } | null;
  계획상한?: { far_pct?: number | null; bcr_pct?: number | null } | null;
  인센티브?: { relaxation_ratio_pct?: number | null } | null;
  최종근거?: string | null;
  데이터출처?: string[] | null;
  조례확인필요?: boolean;
};

type EffectiveFarData = {
  effective_far_pct?: number | null;
  effective_bcr_pct?: number | null;
  far_basis?: string | null;
  far_basis_detail?: FarBasisDetail | null;
  ordinance_confirmed?: boolean;
  legal_min_far_pct?: number | null;
  legal_max_far_pct?: number | null;
};

// 종상향/종변경 잠재 시나리오(예상치 — 현행과 분리)
type UpzoningScenario = {
  path?: string;
  target_zone?: string;
  expected_far_pct_low?: number | null;
  expected_far_pct_high?: number | null;
  expected_far_source?: string;
  conditions?: string[];
  feasibility?: string;
  feasibility_reason?: string;
  legal_basis?: string;
  timeline_est?: string;
  caveats?: string[];
  is_estimate?: boolean;
};

type PotentialFarRange = { min_pct?: number | null; max_pct?: number | null; note?: string } | null;

type UpzoningData = {
  current_zone?: string;
  scenarios?: UpzoningScenario[];
  potential_far_range?: PotentialFarRange;
  summary?: string;
  disclaimer?: string;
} | null;

type L3SiteData = {
  nearby_transactions?: { apt?: NearbyTransactionSummary; land?: NearbyTransactionSummary } | null;
  infrastructure?: InfrastructureData | null;
  building_detail?: BuildingDetail | null;
  // 실효용적률 계층 / 종상향 / 분묘 (백엔드 종합응답에 포함 시 자동 노출, 없으면 정직 미표시)
  effective_far?: EffectiveFarData | null;
  zone_limits?: Record<string, unknown> | null;
  upzoning?: UpzoningData;
  upzoning_scenarios?: UpzoningScenario[] | null;
  potential_far_range?: PotentialFarRange;
  upzoning_interpretation?: string | null;
  grave_registry?: { available?: boolean; reason?: string; suggestion?: string; data_source?: string } | null;
};

function formatPriceKr(amount10k: number): string {
  if (amount10k >= 10000) {
    const eok = Math.floor(amount10k / 10000);
    const remain = amount10k % 10000;
    return remain > 0 ? `${eok}억 ${remain.toLocaleString()}만` : `${eok}억`;
  }
  return `${amount10k.toLocaleString()}만`;
}

// ── L3 Enhanced Cards Component ──
function L3EnhancedCards({
  l3Data,
  siteAnalysis,
}: {
  l3Data: L3SiteData | null;
  siteAnalysis: SiteAnalysisData | null;
}) {
  // l3Data를 우선 사용, siteAnalysis는 향후 진행 단계 데이터 연동 시 활용
  const _storeRef = siteAnalysis; // 향후 진행 단계 스토어 데이터 연동용
  void _storeRef;
  const tx = l3Data?.nearby_transactions;
  const infra = l3Data?.infrastructure;
  const bldg = l3Data?.building_detail;
  const effFar = l3Data?.effective_far;
  const zoneLimits = l3Data?.zone_limits;
  const upzoning = l3Data?.upzoning;
  const upScenarios = upzoning?.scenarios ?? l3Data?.upzoning_scenarios ?? [];
  const potentialRange = upzoning?.potential_far_range ?? l3Data?.potential_far_range ?? null;
  const upInterp = l3Data?.upzoning_interpretation;
  const grave = l3Data?.grave_registry;

  // 실효용적률 계층 카드 노출 조건: 실효용적률 메타 또는 zone_limits 보유
  const hasFarTier = Boolean(effFar?.far_basis_detail || effFar?.effective_far_pct != null || zoneLimits);
  const hasUpzoning = upScenarios.length > 0 || Boolean(upInterp) || Boolean(potentialRange);
  const hasGraveInfo = grave != null && grave.available === false;

  const hasAnyData = tx || infra || bldg || hasFarTier || hasUpzoning || hasGraveInfo;
  if (!hasAnyData) return null;

  // 헬퍼: 용적률 퍼센트 안전 포맷
  const pct = (v: number | null | undefined): string => (v == null ? "—" : `${Math.round(v)}%`);
  // far_basis_detail에서 zone_limits로 폴백한 법정/조례 추출(데이터·호출 무변경, 표시만)
  const fbd = effFar?.far_basis_detail;
  const legalMin = fbd?.법정범위?.min_far_pct ?? effFar?.legal_min_far_pct ?? null;
  const legalMax =
    fbd?.법정범위?.max_far_pct ??
    effFar?.legal_max_far_pct ??
    (typeof zoneLimits?.["max_far_pct"] === "number" ? (zoneLimits["max_far_pct"] as number) : null);
  const ordinanceFarVal =
    fbd?.조례값?.far_pct ??
    (typeof zoneLimits?.["ordinance_far_pct"] === "number" ? (zoneLimits["ordinance_far_pct"] as number) : null);
  const planCeil = fbd?.계획상한?.far_pct ?? null;
  const incentiveRatio = fbd?.인센티브?.relaxation_ratio_pct ?? null;
  const ordinanceConfirmed =
    effFar?.ordinance_confirmed ?? fbd?.조례값?.confirmed ?? (ordinanceFarVal != null);
  const farFinalBasis =
    fbd?.최종근거 ??
    effFar?.far_basis ??
    (typeof zoneLimits?.["ordinance_source"] === "string" ? (zoneLimits["ordinance_source"] as string) : null);
  const farSources =
    fbd?.데이터출처 ??
    (typeof zoneLimits?.["ordinance_legal_basis"] === "string" && zoneLimits["ordinance_legal_basis"]
      ? [zoneLimits["ordinance_legal_basis"] as string]
      : null);
  const ordinanceNeedCheck = fbd?.조례확인필요 ?? !ordinanceConfirmed;
  // 가능성 등급 → 의미색(상=success/중=warning/하=muted)
  const feasibilityStyle = (f?: string): string => {
    if (f === "상") return "bg-emerald-500/10 text-emerald-400 border-emerald-500/30";
    if (f === "중") return "bg-amber-500/10 text-amber-400 border-amber-500/30";
    return "bg-[var(--surface-muted)] text-[var(--text-hint)] border-[var(--line)]";
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 30 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.4 }}
      className="flex flex-col gap-6"
    >
      {/* ① 실효용적률 계층 카드 (법정범위 → 조례 적용 → 계획상한 → 인센티브) */}
      {hasFarTier && (
        <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-6 shadow-[var(--shadow-xl)]">
          <div className="flex items-center gap-3 mb-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500/10 text-indigo-400">
              <Icons.Search width={20} height={20} />
            </div>
            <div className="flex-1">
              <h4 className="text-sm font-black text-[var(--text-primary)]">실효 용적률 산정 계층</h4>
              <p className="text-[9px] font-bold text-indigo-400 uppercase tracking-widest">법정범위 → 조례 → 계획상한 → 인센티브</p>
            </div>
            {ordinanceNeedCheck && (
              <span className="shrink-0 rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-[8px] font-black uppercase tracking-wider text-amber-400">
                조례 확인 필요
              </span>
            )}
          </div>

          {/* 계층 흐름 */}
          <div className="flex flex-col sm:flex-row sm:items-stretch gap-2">
            {/* 법정범위 */}
            <div className="flex-1 rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] p-4">
              <p className="text-[8px] font-black text-[var(--text-hint)] uppercase tracking-wider mb-1">① 법정범위 (국토계획법)</p>
              <p className="text-base font-black text-[var(--text-primary)]">
                {legalMin != null && legalMax != null ? `${pct(legalMin)} ~ ${pct(legalMax)}` : pct(legalMax)}
              </p>
            </div>
            <div className="hidden sm:flex items-center text-[var(--text-hint)] font-black">→</div>
            {/* 조례 적용값 */}
            <div className={`flex-1 rounded-xl border p-4 ${ordinanceConfirmed ? "border-emerald-500/30 bg-emerald-500/5" : "border-dashed border-[var(--line)] bg-[var(--surface-muted)]"}`}>
              <p className="text-[8px] font-black text-[var(--text-hint)] uppercase tracking-wider mb-1">② 조례 적용 (지자체)</p>
              <p className={`text-base font-black ${ordinanceConfirmed ? "text-emerald-400" : "text-[var(--text-hint)] italic"}`}>
                {ordinanceConfirmed && ordinanceFarVal != null ? pct(ordinanceFarVal) : "확인 필요"}
              </p>
            </div>
            {/* 계획상한(있을 때만) */}
            {planCeil != null && (
              <>
                <div className="hidden sm:flex items-center text-[var(--text-hint)] font-black">→</div>
                <div className="flex-1 rounded-xl border border-blue-500/30 bg-blue-500/5 p-4">
                  <p className="text-[8px] font-black text-[var(--text-hint)] uppercase tracking-wider mb-1">③ 계획상한 (지구단위/도시군관리)</p>
                  <p className="text-base font-black text-blue-400">{pct(planCeil)}</p>
                </div>
              </>
            )}
            {/* 인센티브(있을 때만) */}
            {incentiveRatio != null && (
              <>
                <div className="hidden sm:flex items-center text-[var(--text-hint)] font-black">→</div>
                <div className="flex-1 rounded-xl border border-purple-500/30 bg-purple-500/5 p-4">
                  <p className="text-[8px] font-black text-[var(--text-hint)] uppercase tracking-wider mb-1">④ 인센티브 완화율</p>
                  <p className="text-base font-black text-purple-400">+{Math.round(incentiveRatio)}%</p>
                </div>
              </>
            )}
          </div>

          {/* 최종 실효용적률 + 근거/출처 */}
          <div className="mt-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 rounded-xl border border-[var(--accent-strong)]/20 bg-[var(--accent-soft)] p-4">
            <div>
              <p className="text-[8px] font-black text-[var(--text-hint)] uppercase tracking-wider mb-0.5">최종 실효 용적률</p>
              <p className="text-xl font-black text-[var(--accent-strong)]">
                {effFar?.effective_far_pct != null ? pct(effFar.effective_far_pct) : (ordinanceConfirmed && ordinanceFarVal != null ? pct(ordinanceFarVal) : pct(legalMax))}
              </p>
            </div>
            {farFinalBasis && (
              <p className="text-[10px] font-bold text-[var(--text-secondary)] sm:text-right max-w-md">근거: {farFinalBasis}</p>
            )}
          </div>
          {farSources && farSources.length > 0 && (
            <p className="mt-2 text-[9px] text-[var(--text-hint)]">데이터 출처: {farSources.join(" · ")}</p>
          )}
        </div>
      )}

      {/* ② 종상향/종변경 잠재 시나리오 카드 (현행 vs 잠재 — 예상치 명확 분리) */}
      {hasUpzoning && (
        <div className="rounded-2xl border border-purple-500/20 bg-[var(--surface-strong)] p-6 shadow-[var(--shadow-xl)]">
          <div className="flex items-center gap-3 mb-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-500/10 text-purple-400">
              <Icons.Sparkles width={20} height={20} />
            </div>
            <div>
              <h4 className="text-sm font-black text-[var(--text-primary)]">종상향 · 종변경 잠재 시나리오</h4>
              <p className="text-[9px] font-bold text-purple-400 uppercase tracking-widest">현행과 분리된 예상치</p>
            </div>
          </div>

          {/* ★예상치 고지 */}
          <div className="mb-4 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3">
            <p className="text-[11px] font-black text-amber-400 leading-relaxed">
              예상치 — 도시·군관리계획 결정 및 인허가를 전제로 한 잠재 시나리오이며, 실현을 보장하지 않습니다.
            </p>
          </div>

          {/* 현행 vs 잠재 2계층 시각분리 */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
            <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] p-4">
              <p className="text-[8px] font-black text-[var(--text-hint)] uppercase tracking-wider mb-1">현행 (확정)</p>
              <p className="text-sm font-black text-[var(--text-primary)]">{upzoning?.current_zone || "현행 용도지역"}</p>
              <p className="text-xs font-bold text-[var(--text-secondary)] mt-0.5">
                실효 용적률 {effFar?.effective_far_pct != null ? pct(effFar.effective_far_pct) : (legalMax != null ? `~${pct(legalMax)}` : "—")}
              </p>
            </div>
            <div className="rounded-xl border border-dashed border-purple-500/40 bg-purple-500/5 p-4">
              <p className="text-[8px] font-black text-purple-400/70 uppercase tracking-wider mb-1">잠재 (예상치 · 미확정)</p>
              <p className="text-sm font-black text-purple-400">
                {potentialRange?.min_pct != null && potentialRange?.max_pct != null
                  ? `예상 용적률 ${pct(potentialRange.min_pct)} ~ ${pct(potentialRange.max_pct)}`
                  : "잠재 시나리오 검토"}
              </p>
              {potentialRange?.note && (
                <p className="text-[10px] font-bold text-[var(--text-secondary)] mt-0.5">{potentialRange.note}</p>
              )}
            </div>
          </div>

          {/* 시나리오 리스트 */}
          {upScenarios.length > 0 && (
            <div className="space-y-2">
              {upScenarios.map((sc, i) => (
                <div key={i} className="rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] p-4">
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <div className="flex-1">
                      <p className="text-xs font-black text-[var(--text-primary)]">{sc.path || "잠재 경로"}</p>
                      {sc.target_zone && (
                        <p className="text-[10px] font-bold text-purple-400 mt-0.5">→ {sc.target_zone}</p>
                      )}
                    </div>
                    <span className={`shrink-0 rounded-full border px-2.5 py-1 text-[9px] font-black ${feasibilityStyle(sc.feasibility)}`}>
                      가능성 {sc.feasibility || "—"}
                    </span>
                  </div>
                  {(sc.expected_far_pct_low != null || sc.expected_far_pct_high != null) && (
                    <p className="text-[11px] font-bold text-[var(--text-secondary)] mb-1">
                      예상 용적률 {sc.expected_far_pct_low != null ? pct(sc.expected_far_pct_low) : ""}{sc.expected_far_pct_high != null ? ` ~ ${pct(sc.expected_far_pct_high)}` : ""}
                      {sc.expected_far_source ? ` (${sc.expected_far_source})` : ""}
                    </p>
                  )}
                  {sc.feasibility_reason && (
                    <p className="text-[10px] text-[var(--text-hint)] mb-1">사유: {sc.feasibility_reason}</p>
                  )}
                  {sc.conditions && sc.conditions.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1.5">
                      {sc.conditions.map((c, ci) => (
                        <span key={ci} className="rounded-md bg-[var(--surface-strong)] border border-[var(--line)] px-2 py-0.5 text-[9px] font-bold text-[var(--text-secondary)]">{c}</span>
                      ))}
                    </div>
                  )}
                  <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-[9px] text-[var(--text-hint)]">
                    {sc.legal_basis && <span>근거법령: {sc.legal_basis}</span>}
                    {sc.timeline_est && <span>예상 기간: {sc.timeline_est}</span>}
                  </div>
                  {sc.caveats && sc.caveats.length > 0 && (
                    <p className="mt-1.5 text-[9px] text-amber-400/80 italic">전제: {sc.caveats.join(" / ")}</p>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* LLM 해석 */}
          {upInterp && (
            <div className="mt-4 rounded-xl border border-[var(--accent-strong)]/20 bg-[var(--accent-soft)] p-4">
              <div className="flex items-center gap-2 mb-1.5">
                <Icons.Brain width={14} height={14} className="text-[var(--accent-strong)]" />
                <p className="text-[10px] font-black text-[var(--accent-strong)] uppercase tracking-wider">AI 종상향 해석 (예상치)</p>
              </div>
              <p className="text-xs leading-relaxed text-[var(--text-secondary)] whitespace-pre-line">{upInterp}</p>
            </div>
          )}
          {upScenarios.length === 0 && upzoning?.summary && (
            <p className="text-xs text-[var(--text-hint)] italic mt-2">{upzoning.summary}</p>
          )}
        </div>
      )}

      {/* ③ 분묘 정보 — 무자료 정직 안내 (가짜 표시 금지) */}
      {hasGraveInfo && (
        <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-5">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[var(--surface-muted)] text-[var(--text-hint)]">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22V8"/><path d="M5 12H2a10 10 0 0 0 20 0h-3"/><path d="M12 8a4 4 0 0 0-4-4V2h8v2a4 4 0 0 0-4 4Z"/></svg>
            </div>
            <div className="flex-1">
              <p className="text-xs font-black text-[var(--text-primary)] mb-1">분묘 정보: 데이터 없음</p>
              <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed">
                {grave?.reason || "전국 단위 무료 공공API 미제공"} — {grave?.suggestion || "현장조사·항공/위성 판독(디지털트윈 항공레이어) 또는 지자체 개별 확인 권장"}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 하단 3종 카드 그리드 (실거래가 · 건축물대장 · 인프라) */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {/* 실거래가 요약 카드 */}
      {tx?.apt && tx.apt.count > 0 && (
        <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-6 shadow-[var(--shadow-xl)]">
          <div className="flex items-center gap-3 mb-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-400">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" x2="12" y1="2" y2="22"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
            </div>
            <div>
              <h4 className="text-sm font-black text-[var(--text-primary)]">인근 아파트 실거래가</h4>
              <p className="text-[9px] font-bold text-emerald-400 uppercase tracking-widest">최근 3개월 · {tx.apt.count}건</p>
            </div>
          </div>
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-2">
              <div className="rounded-lg bg-[var(--surface-muted)] p-3 text-center border border-[var(--line)]">
                <p className="text-[8px] font-black text-[var(--text-hint)] uppercase mb-1">평균</p>
                <p className="text-sm font-black text-[var(--text-primary)]">{formatPriceKr(tx.apt.avg_price_10k)}</p>
              </div>
              <div className="rounded-lg bg-[var(--surface-muted)] p-3 text-center border border-[var(--line)]">
                <p className="text-[8px] font-black text-[var(--text-hint)] uppercase mb-1">최고</p>
                <p className="text-sm font-black text-red-400">{formatPriceKr(tx.apt.max_price_10k)}</p>
              </div>
              <div className="rounded-lg bg-[var(--surface-muted)] p-3 text-center border border-[var(--line)]">
                <p className="text-[8px] font-black text-[var(--text-hint)] uppercase mb-1">최저</p>
                <p className="text-sm font-black text-blue-400">{formatPriceKr(tx.apt.min_price_10k)}</p>
              </div>
            </div>
            {tx.apt.items.length > 0 && (
              <div className="space-y-1 mt-2">
                {tx.apt.items.slice(0, 3).map((item, i) => (
                  <div key={i} className="flex items-center justify-between text-[10px] text-[var(--text-secondary)] bg-[var(--surface-muted)] rounded-lg px-3 py-1.5">
                    <span className="font-medium">{item.deal_date}</span>
                    <span className="text-[var(--text-hint)] truncate max-w-[120px]">{item.name}</span>
                    <span className="font-bold text-[var(--text-primary)]">{formatPriceKr(parseInt(item.price_10k) || 0)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 건축물대장 카드 — 표제부(세대·동·호·가구) + 멸실/미준공 정직표기 */}
      {bldg && (bldg.main_purpose || bldg.title_status) && (
        <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-6 shadow-[var(--shadow-xl)]">
          <div className="flex items-center gap-3 mb-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500/10 text-blue-400">
              <Icons.Database width={20} height={20} />
            </div>
            <div className="flex-1">
              <h4 className="text-sm font-black text-[var(--text-primary)]">기존 건축물 현황</h4>
              <p className="text-[9px] font-bold text-blue-400 uppercase tracking-widest">건축물대장 표제부</p>
            </div>
            {/* 출처 배지 */}
            {bldg.data_source && (
              <span className={`shrink-0 rounded-full px-2.5 py-1 text-[8px] font-black uppercase tracking-wider border ${
                bldg.data_source === "molit_live"
                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                  : "bg-[var(--surface-muted)] text-[var(--text-hint)] border-[var(--line)]"
              }`}>
                {bldg.data_source === "molit_live" ? "실시간 조회" : "조회 불가"}
              </span>
            )}
          </div>

          {/* 멸실/미준공 경고 배지 */}
          {(bldg.is_demolished || bldg.is_uncompleted) && (
            <div className="mb-3 flex flex-wrap gap-2">
              {bldg.is_demolished && (
                <span className="inline-flex items-center gap-1.5 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-[10px] font-black text-red-400">
                  <span className="h-1.5 w-1.5 rounded-full bg-red-400" />
                  멸실 건축물(확인 필요){bldg.demolition_date ? ` · ${bldg.demolition_date}` : ""}
                </span>
              )}
              {bldg.is_uncompleted && (
                <span className="inline-flex items-center gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-[10px] font-black text-amber-400">
                  <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                  미준공/공사중 추정
                </span>
              )}
            </div>
          )}

          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-lg bg-[var(--surface-muted)] p-3 border border-[var(--line)]">
              <p className="text-[8px] font-black text-[var(--text-hint)] uppercase mb-1">용도</p>
              <p className="text-xs font-bold text-[var(--text-primary)]">{bldg.main_purpose || "—"}</p>
            </div>
            <div className="rounded-lg bg-[var(--surface-muted)] p-3 border border-[var(--line)]">
              <p className="text-[8px] font-black text-[var(--text-hint)] uppercase mb-1">구조</p>
              <p className="text-xs font-bold text-[var(--text-primary)]">{bldg.structure || "—"}</p>
            </div>
            <div className="rounded-lg bg-[var(--surface-muted)] p-3 border border-[var(--line)]">
              <p className="text-[8px] font-black text-[var(--text-hint)] uppercase mb-1">연면적</p>
              <p className="text-xs font-bold text-[var(--text-primary)]">{bldg.total_area_sqm ? `${bldg.total_area_sqm.toLocaleString()}m²` : "—"}</p>
            </div>
            <div className="rounded-lg bg-[var(--surface-muted)] p-3 border border-[var(--line)]">
              <p className="text-[8px] font-black text-[var(--text-hint)] uppercase mb-1">층수</p>
              <p className="text-xs font-bold text-[var(--text-primary)]">
                지상 {bldg.ground_floors}층{bldg.underground_floors ? ` / 지하 ${bldg.underground_floors}층` : ""}
              </p>
            </div>
            {/* 표제부 세대·동·호·가구 (_display 우선) */}
            {(bldg.dong_count_display || (bldg.dong_count ?? 0) > 0) && (
              <div className="rounded-lg bg-[var(--surface-muted)] p-3 border border-[var(--line)]">
                <p className="text-[8px] font-black text-[var(--text-hint)] uppercase mb-1">동수</p>
                <p className="text-xs font-bold text-[var(--text-primary)]">{bldg.dong_count_display || `${bldg.dong_count}개동`}</p>
              </div>
            )}
            {(bldg.household_count_display || (bldg.household_count ?? 0) > 0) && (
              <div className="rounded-lg bg-[var(--surface-muted)] p-3 border border-[var(--line)]">
                <p className="text-[8px] font-black text-[var(--text-hint)] uppercase mb-1">세대수</p>
                <p className="text-xs font-bold text-[var(--text-primary)]">{bldg.household_count_display || `${bldg.household_count?.toLocaleString()}세대`}</p>
              </div>
            )}
            {(bldg.ho_count_display || (bldg.ho_count ?? 0) > 0) && (
              <div className="rounded-lg bg-[var(--surface-muted)] p-3 border border-[var(--line)]">
                <p className="text-[8px] font-black text-[var(--text-hint)] uppercase mb-1">호수</p>
                <p className="text-xs font-bold text-[var(--text-primary)]">{bldg.ho_count_display || `${bldg.ho_count?.toLocaleString()}호`}</p>
              </div>
            )}
            {(bldg.family_count ?? 0) > 0 && (
              <div className="rounded-lg bg-[var(--surface-muted)] p-3 border border-[var(--line)]">
                <p className="text-[8px] font-black text-[var(--text-hint)] uppercase mb-1">가구수</p>
                <p className="text-xs font-bold text-[var(--text-primary)]">{bldg.family_count?.toLocaleString()}가구</p>
              </div>
            )}
            {bldg.use_approval_date && (
              <div className="rounded-lg bg-[var(--surface-muted)] p-3 border border-[var(--line)] col-span-2">
                <p className="text-[8px] font-black text-[var(--text-hint)] uppercase mb-1">사용승인일</p>
                <p className="text-xs font-bold text-[var(--text-primary)]">{bldg.use_approval_date}</p>
              </div>
            )}
            {bldg.title_status && bldg.title_status !== "정상" && (
              <div className="rounded-lg bg-[var(--surface-muted)] p-3 border border-[var(--line)] col-span-2">
                <p className="text-[8px] font-black text-[var(--text-hint)] uppercase mb-1">표제부 상태</p>
                <p className="text-xs font-bold text-[var(--text-hint)] italic">{bldg.title_status}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 주변 인프라 카드 */}
      {infra && (infra.nearest_subway || infra.schools.length > 0) && (
        <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-6 shadow-[var(--shadow-xl)]">
          <div className="flex items-center gap-3 mb-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-500/10 text-purple-400">
              <Icons.Map width={20} height={20} />
            </div>
            <div>
              <h4 className="text-sm font-black text-[var(--text-primary)]">주변 인프라</h4>
              <p className="text-[9px] font-bold text-purple-400 uppercase tracking-widest">교통 · 학군</p>
            </div>
          </div>
          <div className="space-y-3">
            {infra.nearest_subway && (
              <div className="rounded-lg bg-[var(--surface-muted)] p-3 border border-[var(--line)] flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="h-6 w-6 rounded-full bg-blue-500/20 flex items-center justify-center">
                    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-blue-400"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>
                  </div>
                  <div>
                    <p className="text-[8px] font-black text-[var(--text-hint)] uppercase">최근접 지하철</p>
                    <p className="text-xs font-bold text-[var(--text-primary)]">{infra.nearest_subway.name}</p>
                  </div>
                </div>
                <span className={`text-sm font-black ${infra.nearest_subway.distance_m <= 500 ? "text-emerald-400" : infra.nearest_subway.distance_m <= 1000 ? "text-amber-400" : "text-red-400"}`}>
                  {infra.nearest_subway.distance_m.toLocaleString()}m
                </span>
              </div>
            )}
            {infra.schools.length > 0 && (
              <div className="space-y-1.5">
                <p className="text-[8px] font-black text-[var(--text-hint)] uppercase tracking-widest px-1">학군 (반경 500m)</p>
                {infra.schools.slice(0, 4).map((school, i) => (
                  <div key={i} className="flex items-center justify-between text-[10px] bg-[var(--surface-muted)] rounded-lg px-3 py-2 border border-[var(--line)]">
                    <div className="flex items-center gap-2">
                      <span className={`inline-block h-1.5 w-1.5 rounded-full ${
                        school.type === "초등학교" ? "bg-green-400" :
                        school.type === "중학교" ? "bg-blue-400" :
                        school.type === "고등학교" ? "bg-purple-400" : "bg-gray-400"
                      }`} />
                      <span className="font-bold text-[var(--text-primary)]">{school.name}</span>
                      <span className="text-[var(--text-hint)]">{school.type}</span>
                    </div>
                    <span className="font-bold text-[var(--text-secondary)]">{school.distance_m}m</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
      </div>
    </motion.div>
  );
}

export default function SiteAnalysisPage() {
  const { locale, id } = useParams() as { locale: string; id: string };
  const { dictionary, isLoading } = useDictionary(locale as Locale);
  const [stage, setStage] = useState<"init" | "analyzing" | "result">("init");
  const [siteData, setSiteData] = useState<Record<string, string | undefined> | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [l3Data, setL3Data] = useState<L3SiteData | null>(null);
  // 디지털트윈 건물 자동연결: 프로젝트에 저장된 설계(design_versions)가 있으면 design_version_id를 확보.
  // 없으면 null → DigitalTwinScene이 안내 블록만 표시(가짜 건물 금지).
  const [designVersionId, setDesignVersionId] = useState<string | null>(null);
  // 사용자 명시 액션(새 분석/분석 시작) 추적 — 컨텍스트 자동진입이 사용자 의도를 덮어쓰지 않게 한다.
  const [userInitiated, setUserInitiated] = useState(false);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const ctxProjectId = useProjectContextStore((s) => s.projectId);
  // ProjectContextBinder가 이 프로젝트를 바인딩 완료했는지(레이아웃에서 동기 바인딩).
  const isBound = ctxProjectId === id;

  // 주소 단일화: 바인딩 완료 후 컨텍스트에 주소가 있으면 재입력 없이 결과로 자동진입하고
  // 컨텍스트 데이터를 siteData로 시드한다. 사용자가 직접 '새 분석'을 누른 경우(userInitiated)는 예외.
  useEffect(() => {
    if (!isBound || userInitiated) return;
    const addr = siteAnalysis?.address?.trim();
    if (!addr) return;
    setSiteData((prev) => {
      // 이미 결과 데이터가 있으면(분석 진행 중/완료) 덮어쓰지 않는다.
      if (prev?.address) return prev;
      return {
        address: addr,
        pnu: siteAnalysis?.pnu ?? undefined,
        zoneType: siteAnalysis?.zoneCode ?? undefined,
        landAreaSqm: siteAnalysis?.landAreaSqm != null ? String(siteAnalysis.landAreaSqm) : undefined,
      };
    });
    setStage((prev) => (prev === "init" ? "result" : prev));
  }, [isBound, userInitiated, siteAnalysis?.address, siteAnalysis?.pnu, siteAnalysis?.zoneCode, siteAnalysis?.landAreaSqm]);

  // 결과 단계 진입 시 프로젝트의 최신 설계(design_versions) 존재 여부를 조회.
  // 백엔드 /digital-twin/scene은 design_version_id 경로로 glb URL(/design/{id}/bim/model.glb)을
  // 구성하며, 해당 glb POST 라우트는 path를 project_id로 사용하므로 프로젝트 id를 전달한다.
  // 설계가 없으면 designVersionId=null → 건물 미합성 + 안내 블록 표시(무목업).
  useEffect(() => {
    if (stage !== "result" || !id) return;
    let alive = true;
    (async () => {
      try {
        const res = await apiClient.get<{ saved?: boolean }>(
          `/design/${encodeURIComponent(id)}/drawings/load`,
          { useMock: false },
        );
        if (alive) setDesignVersionId(res?.saved ? id : null);
      } catch {
        if (alive) setDesignVersionId(null);
      }
    })();
    return () => {
      alive = false;
    };
  }, [stage, id]);

  if (isLoading || !dictionary) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <div className="h-12 w-12 animate-spin rounded-full border-4 border-[var(--accent-strong)] border-t-transparent shadow-[var(--shadow-glow)]" />
      </div>
    );
  }

  const handleInitiate = async (data: { address?: string; file?: File | null; fileName?: string }) => {
    const address = data.address?.trim();
    if (!address) return;

    setUserInitiated(true);
    setStage("analyzing");
    setAnalysisError(null);
    setSiteData({ address });

    try {
      // 실제 용도지역 분석 API 호출
      const zoningResult = await apiClient.post<{
        address: string;
        pnu: string | null;
        zone_type: string | null;
        zone_limits: { max_bcr_pct: number; max_far_pct: number; max_height_m: number | null; zone_key: string; legal_basis: string } | null;
        land_area_sqm: number | null;
        land_category: string | null;
        official_price_per_sqm: number | null;
      }>("/zoning/analyze", {
        useMock: false,
        body: { address },
      });

      setSiteData({
        address: zoningResult.address || address,
        pnu: zoningResult.pnu ?? undefined,
        zoneType: zoningResult.zone_type ?? undefined,
        landAreaSqm: zoningResult.land_area_sqm?.toString(),
        landCategory: zoningResult.land_category ?? undefined,
      });

      // L3: 종합 토지정보 비동기 수집 (실거래가, 건축물대장, 인프라)
      try {
        const landResult = await apiClient.post<{
          nearby_transactions?: L3SiteData["nearby_transactions"];
          infrastructure?: L3SiteData["infrastructure"];
          building_detail?: L3SiteData["building_detail"];
          effective_far?: L3SiteData["effective_far"];
          zone_limits?: L3SiteData["zone_limits"];
          upzoning?: L3SiteData["upzoning"];
          upzoning_scenarios?: L3SiteData["upzoning_scenarios"];
          potential_far_range?: L3SiteData["potential_far_range"];
          upzoning_interpretation?: L3SiteData["upzoning_interpretation"];
          grave_registry?: L3SiteData["grave_registry"];
        }>("/zoning/comprehensive", {
          useMock: false,
          body: { address, pnu: zoningResult.pnu },
        });
        setL3Data({
          nearby_transactions: landResult.nearby_transactions ?? null,
          infrastructure: landResult.infrastructure ?? null,
          building_detail: landResult.building_detail ?? null,
          effective_far: landResult.effective_far ?? null,
          zone_limits: landResult.zone_limits ?? null,
          upzoning: landResult.upzoning ?? null,
          upzoning_scenarios: landResult.upzoning_scenarios ?? null,
          potential_far_range: landResult.potential_far_range ?? null,
          upzoning_interpretation: landResult.upzoning_interpretation ?? null,
          grave_registry: landResult.grave_registry ?? null,
        });
      } catch {
        // L3 데이터 실패는 무시 — 기본 분석만 표시
      }
    } catch {
      // API 실패 시에도 주소 기반으로 결과 화면 진행 (LandIntelligencePanel이 자체 폴백 보유)
      setAnalysisError("용도지역 API 연결 실패 — 로컬 추정값으로 표시합니다.");
    } finally {
      setStage("result");
    }
  };

  const safeLocale = (isValidLocale(locale) ? locale : "ko") as Locale;
  const runtimeMode =
    process.env.NEXT_PUBLIC_USE_MOCKS === "false"
      ? dictionary.workspace.modeLive
      : dictionary.workspace.modeMock;
  const t = dictionary.modulePlaceholders["site-analysis"];

  return (
    <div className="flex flex-col gap-12 min-h-screen pb-20 font-sans">
      {/* ① 컨텍스트 헤더 — 3구역 표준(ModulePlaceholder) */}
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <ModulePlaceholder
          eyebrow={t.eyebrow}
          title={t.title}
          description={t.description}
          statusLabel={runtimeMode}
          localeLabel={locale}
          items={t.items}
        />
      </motion.div>

      {/* ── Dynamic Content Stages ── */}
      <AnimatePresence mode="wait">
        {stage === "init" && !isBound && (
          // 컨텍스트 바인딩(ProjectContextBinder) 완료 전 — 주소 프롬프트를 섣불리 띄우지 않는다.
          <motion.div
            key="init-binding"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex items-center justify-center py-32"
          >
            <div className="h-12 w-12 animate-spin rounded-full border-4 border-[var(--accent-strong)] border-t-transparent shadow-[var(--shadow-glow)]" />
          </motion.div>
        )}
        {stage === "init" && isBound && (
          <motion.div
            key="init"
            initial={{ opacity: 0, scale: 0.95, y: 40 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, y: -40, filter: "blur(20px)" }}
            className="mx-auto w-full max-w-5xl"
          >
            <div className="rounded-2xl sm:rounded-[2.5rem] lg:rounded-[4.5rem] p-1.5 border border-[var(--line)] bg-[var(--surface-soft)] overflow-hidden group shadow-[var(--shadow-2xl)]">
               <div className="rounded-xl sm:rounded-[2.2rem] lg:rounded-[4.2rem] p-6 sm:p-10 lg:p-20 bg-[var(--surface-strong)]/80 backdrop-blur-3xl transition-all group-hover:bg-[var(--surface-strong)]/60 border border-[var(--line-strong)]">
                  <SiteInitiator onInitiate={handleInitiate} loading={false} />
               </div>
            </div>
          </motion.div>
        )}

        {stage === "analyzing" && (
          <motion.div
            key="analyzing"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, filter: "blur(20px)" }}
            className="flex flex-col items-center justify-center gap-20 py-48"
          >
            <div className="relative group">
              <div className="absolute -inset-24 animate-spin-slow bg-gradient-to-r from-[var(--accent-strong)] via-blue-500 to-teal-500 rounded-full blur-[80px] opacity-10" />
              <motion.div
                animate={{ scale: [1, 1.05, 1] }}
                transition={{ duration: 2, repeat: Infinity }}
                className="relative flex h-64 w-64 items-center justify-center rounded-[4rem] bg-[var(--surface-strong)] border border-[var(--line-strong)] shadow-[var(--shadow-2xl)] backdrop-blur-3xl overflow-hidden"
              >
                 <div className="absolute inset-0 bg-[var(--accent-strong)]/5 animate-pulse" />
                 <Icons.Brain width={112} height={112} strokeWidth={1} />
              </motion.div>
            </div>

            <div className="flex flex-col items-center gap-10 text-center max-w-2xl px-6">
               <div className="space-y-4">
                  <h3 className="text-2xl sm:text-3xl lg:text-5xl font-[1000] text-[var(--text-primary)] italic tracking-tighter leading-tight">AI <span className="text-[var(--accent-strong)]">GIS 엔진</span> 분석 중...</h3>
                  <p className="text-[11px] font-black text-[var(--accent-strong)]/50 uppercase tracking-[0.6em]">사통팔땅 멀티레이어 지능형 엔진 가동 중</p>
               </div>

               <div className="flex flex-wrap justify-center gap-6">
                  {[
                    { label: "지적도 오버레이 데이터 연동", delay: 0 },
                    { label: "용도지역 지자체 조례 전수 분석", delay: 0.6 },
                    { label: "주변 개발 압력 및 시세 매핑", delay: 1.2 },
                    { label: "AI 최적 공간 모델링 추론", delay: 1.8 },
                  ].map((step, i) => (
                    <motion.div
                      key={step.label}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: step.delay }}
                      className="rounded-3xl border border-[var(--line-strong)] bg-[var(--surface-strong)] px-8 py-5 text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)] flex items-center gap-4 backdrop-blur-md hover:bg-[var(--surface-soft)] hover:text-[var(--text-primary)] transition-all cursor-default shadow-[var(--shadow-sm)]"
                    >
                       <div className="h-2 w-2 rounded-full bg-[var(--accent-strong)] shadow-[var(--shadow-glow)] animate-pulse" />
                       {step.label}
                    </motion.div>
                  ))}
               </div>
            </div>
          </motion.div>
        )}

        {stage === "result" && siteData && (
          <motion.div
            key="result"
            initial={{ opacity: 0, y: 40 }}
            animate={{ opacity: 1, y: 0 }}
            className="w-full flex flex-col gap-16"
          >
            {/* Context Summary Bar */}
            <div className="flex flex-col lg:flex-row lg:items-center justify-between rounded-2xl sm:rounded-[2rem] lg:rounded-[4rem] bg-[var(--surface-strong)] p-6 sm:p-8 lg:p-10 lg:px-14 border border-[var(--line-strong)] backdrop-blur-3xl shadow-[var(--shadow-2xl)] gap-6 sm:gap-8">
               <div className="flex items-center gap-8">
                  <div className="flex h-20 w-20 items-center justify-center rounded-[2rem] bg-[var(--accent-strong)]/10 text-[var(--accent-strong)] border border-[var(--accent-strong)]/20 shadow-[var(--shadow-glow)]">
                    <Icons.Map width={40} height={40} strokeWidth={1.5} />
                  </div>
                  <div className="space-y-1">
                    <p className="text-[10px] font-black uppercase tracking-[0.4em] text-[var(--text-hint)]">분석 대상 부지</p>
                    <p className="text-xl sm:text-2xl lg:text-3xl font-[1000] text-[var(--text-primary)] tracking-tighter italic">
                      {siteData.address || "분석 대상 주소를 입력하세요"}
                    </p>
                    {siteData.zoneType && (
                      <p className="text-sm font-bold text-[var(--accent-strong)]">
                        {siteData.zoneType}
                        {siteData.landAreaSqm && ` · ${Number(siteData.landAreaSqm).toLocaleString()}m²`}
                        {siteData.landCategory && ` · ${siteData.landCategory}`}
                      </p>
                    )}
                  </div>
               </div>
               <button
                onClick={() => { setUserInitiated(true); setStage("init"); setSiteData(null); setAnalysisError(null); }}
                className="group flex h-16 items-center justify-center gap-4 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] px-10 text-[11px] font-black text-[var(--text-primary)] hover:text-white uppercase tracking-[0.3em] transition-all hover:bg-[var(--accent-strong)] hover:border-[var(--accent-strong)] active:scale-95 shadow-[var(--shadow-lg)]"
               >
                 <span>새 분석</span>
                 <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-hover:rotate-180"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 16h5v5"/></svg>
               </button>
            </div>

            {/* API 연결 실패 안내 */}
            {analysisError && (
              <div className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-5 text-sm text-amber-600 dark:text-amber-400 font-medium">
                {analysisError}
              </div>
            )}

            <motion.div
              initial={{ opacity: 0, y: 40 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="rounded-2xl sm:rounded-[2.5rem] lg:rounded-[4.5rem] border border-[var(--line-strong)] bg-[var(--surface-strong)]/50 p-4 sm:p-8 lg:p-14 shadow-[var(--shadow-2xl)] backdrop-blur-xl"
            >
              <LandIntelligencePanel projectId={id} data={siteData} />
            </motion.div>

            {/* ── L3 Enhanced Cards: 실거래가, 건축물대장, 인프라 ── */}
            <L3EnhancedCards l3Data={l3Data} siteAnalysis={siteAnalysis} />

            {/* ── 주변 실거래가(지도) — 반경원·매매/전월세·유형필터·마커 상세 ── */}
            {siteData.address && (
              <div id="nearby-transactions-map" className="scroll-mt-24">
                <NearbyTransactionsMap address={siteData.address} pnu={siteData.pnu} />
              </div>
            )}

            {/* ── Flagship C-1: 지형분석(경사도·토공량·지형단면) ── */}
            <TerrainAnalysisPanel address={siteData.address} pnu={siteData.pnu} />

            {/* ── Flagship C-2: 환경분석(일조·조망·스카이라인) ── */}
            <EnvironmentAnalysisPanel address={siteData.address} pnu={siteData.pnu} />

            {/* ── 가상준공 3D 디지털트윈(지형·필지·건물·주변 합성 뷰) ── */}
            <DigitalTwinScene
              address={siteData.address}
              pnu={siteData.pnu}
              designVersionId={designVersionId}
              designHref={`/${locale}/projects/${id}/design`}
              zoneType={siteData.zoneType ?? siteAnalysis?.zoneCode ?? undefined}
            />

            {/* ── AVM ML 자동감정(상단이 확정한 주소/PNU/면적으로 자동실행, 입력폼 없음) ── */}
            <ProjectSiteAnalysisWorkspaceClient
              locale={safeLocale}
              projectId={id}
              address={siteData.address}
              pnu={siteData.pnu}
              areaSqm={siteData.landAreaSqm ? Number(siteData.landAreaSqm) : undefined}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* ③ 다음 단계 CTA */}
      <NextStageCta locale={locale} currentStage="site-analysis" />
    </div>
  );
}
