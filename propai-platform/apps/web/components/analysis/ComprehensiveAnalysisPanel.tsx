"use client";

import { useState, useCallback, useEffect } from "react";
import { BarChart3, Construction, ExternalLink, Home, Map, MapPin, Tag, TrendingUp, Wallet, type LucideIcon } from "lucide-react";
import dynamic from "next/dynamic";
const SatongMapShellDynamic = dynamic(
  () => import("@/components/precheck/SatongMapShell").then((m) => m.SatongMapShell),
  { ssr: false },
);
import { DevelopmentScenarioCard } from "@/components/common/DevelopmentScenarioCard";
import { SiteInfraPoiCard } from "@/components/site/SiteInfraPoiCard";
import { SeniorVerdictCard, type SeniorConsultation } from "@/components/analysis/SeniorVerdictCard";
import { BuildableOptionsCard } from "@/components/analysis/BuildableOptionsCard";
import { AllowedBuildingsCard } from "@/components/analysis/AllowedBuildingsCard";
import { DecisionSpecialistCard } from "@/components/projects/DecisionSpecialistCard";
import type { DecisionSpecialist } from "@/components/projects/decision-brief-types";
import { EvidencePanel } from "@/components/common/EvidencePanel";
import { adaptEvidence } from "@/lib/evidence/adaptEvidence";
import type { ParcelRow } from "@/lib/parcel-rows";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { apiClient } from "@/lib/api-client";
import { PYEONG_SQM } from "@/lib/formatters";

/* ── Helpers ── */

function formatArea(sqm: number): string {
  if (!sqm || sqm <= 0) return "-";
  return `${sqm.toLocaleString("ko-KR")} m² (${(sqm / PYEONG_SQM).toFixed(1)}평)`;
}

function formatWon(value: number): string {
  if (!value || value <= 0) return "-";
  if (value >= 1e8) return `${(value / 1e8).toFixed(1)}억원`;
  if (value >= 1e4) return `${(value / 1e4).toFixed(0)}만원`;
  return `${value.toLocaleString("ko-KR")}원`;
}

function formatManWon(value: number): string {
  if (!value || value <= 0) return "-";
  return `${value.toLocaleString("ko-KR")}만원`;
}

/* ── Sub-components ── */

function SectionCard({ title, icon: Icon, children, defaultOpen = false }: {
  title: string; icon: LucideIcon; children: React.ReactNode; defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-strong)] overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-3 px-5 py-4 text-left hover:bg-[var(--surface-soft)] transition-colors"
      >
        <Icon className="size-5 text-[var(--text-secondary)]" aria-hidden />
        <span className="flex-1 text-sm font-bold text-[var(--text-primary)]">{title}</span>
        <span className="text-[var(--text-hint)] text-xs">{open ? "▲" : "▼"}</span>
      </button>
      {open && <div className="px-5 pb-5 space-y-3">{children}</div>}
    </div>
  );
}

function MarketAiBlock({ label, text }: { label: string; text: string }) {
  return (
    <div>
      <p className="text-xs font-black text-emerald-400 mb-1">{label}</p>
      <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed whitespace-pre-line">
        {text}
      </p>
    </div>
  );
}

function AiInterpretation({ text }: { text: string }) {
  return (
    <div className="mt-3 rounded-lg bg-blue-500/5 border border-blue-500/20 p-4">
      <div className="flex items-start gap-2">
        <span className="text-blue-400 text-sm shrink-0">AI</span>
        <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed whitespace-pre-line">
          {text}
        </p>
      </div>
    </div>
  );
}

function AnnotationLine({ text }: { text: string }) {
  const tagMatch = text.match(/^\[(.+?)\]\s*(.*)/);
  if (!tagMatch) return <p className="text-[10px] text-[var(--text-secondary)]">{text}</p>;

  const [, tag, content] = tagMatch;
  const colors: Record<string, string> = {
    "법정 상한": "bg-blue-500/20 text-blue-400",
    "조례 제한": "bg-amber-500/20 text-amber-400",
    "조례 동일": "bg-gray-500/20 text-gray-400",
    "실효 용적률": "bg-emerald-500/20 text-emerald-400",
    "실효 건폐율": "bg-emerald-500/20 text-emerald-400",
    "적용 결과": "bg-[var(--accent-strong)]/20 text-[var(--accent-strong)]",
    "기부체납 여력": "bg-purple-500/20 text-purple-400",
  };
  const color = colors[tag] || "bg-gray-500/20 text-gray-400";

  return (
    <div className="flex items-start gap-2 text-[10px]">
      <span className={`shrink-0 px-1.5 py-0.5 rounded text-[9px] font-bold ${color}`}>{tag}</span>
      <span className="text-[var(--text-secondary)] leading-relaxed">{content}</span>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3">
      <p className="text-[10px] text-[var(--text-hint)] mb-0.5">{label}</p>
      <p className="text-sm font-bold text-[var(--text-primary)]">{String(value)}</p>
    </div>
  );
}

// 개발계획 종합 리스크 등급 → 배지 색(comprehensive_analysis_service._research_dev_plans 산출).
const RISK_LEVEL_STYLE: Record<string, string> = {
  "낮음": "bg-emerald-500/20 text-emerald-400",
  "보통": "bg-amber-500/20 text-amber-400",
  "높음": "bg-orange-500/20 text-orange-400",
  "극히 높음": "bg-red-500/20 text-red-400",
};

// 결정론 모순탐지(contradictions.contradictions[]) 심각도 → 카드 색(status_flip·numeric_delta 공용).
const SEVERITY_CARD_STYLE: Record<string, string> = {
  high: "border-red-500/40 bg-red-500/10",
  medium: "border-amber-500/40 bg-amber-500/10",
  low: "border-[var(--line-strong)] bg-[var(--surface-strong)]",
};

function PermitBadge({ complexity }: { complexity: number }) {
  const colors = ["", "bg-emerald-500/20 text-emerald-400", "bg-blue-500/20 text-blue-400", "bg-amber-500/20 text-amber-400", "bg-orange-500/20 text-orange-400", "bg-red-500/20 text-red-400"];
  const labels = ["", "매우 쉬움", "쉬움", "보통", "어려움", "매우 어려움"];
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${colors[complexity] || colors[3]}`}>
      {labels[complexity] || "보통"}
    </span>
  );
}

/**
 * ContradictionsCard — "이전 분석과 모순 감지" 렌더.
 *
 * ★신규(additive) contradictions.groups[] 있으면 패턴별 그룹 카드(파생 필드 N개 + 펼치면
 * sample_keys)로 요약, 없으면 기존 원시 나열을 최대 5행 + 접기로 강등(무제한 나열 방지).
 * 둘 다 없으면 렌더하지 않는다(무목업 — 모순 0건이면 빈 카드도 안 남긴다).
 */
function ContradictionsCard({ contradictions }: { contradictions?: AnalysisResult }) {
  const [expanded, setExpanded] = useState(false);
  if (!contradictions) return null;
  const groups: AnalysisResult[] = Array.isArray(contradictions.groups) ? contradictions.groups : [];
  const raw: AnalysisResult[] = Array.isArray(contradictions.contradictions) ? contradictions.contradictions : [];
  if (groups.length === 0 && raw.length === 0) return null;

  const maxSeverity = contradictions.max_severity as string | undefined;
  const visibleRaw = expanded ? raw : raw.slice(0, 5);

  return (
    <div className={`rounded-2xl border p-4 ${SEVERITY_CARD_STYLE[maxSeverity ?? ""] || SEVERITY_CARD_STYLE.low}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-bold text-[var(--text-primary)]">이전 분석과 모순 감지</span>
        {maxSeverity && (
          <span className="rounded-full bg-black/10 px-2 py-0.5 text-[10px] font-bold uppercase text-[var(--text-primary)]">
            최고 심각도 {maxSeverity}
          </span>
        )}
      </div>

      {groups.length > 0 ? (
        // ★그룹 카드(패턴키 단위 요약) — leaf_count는 같은 패턴에서 몇 개 세부필드가 함께 변했는지.
        <div className="mt-2 space-y-2">
          {groups.map((g, i) => (
            <div key={i} className={`rounded-xl border p-3 ${SEVERITY_CARD_STYLE[g.severity as string] || SEVERITY_CARD_STYLE.low}`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-bold text-[var(--text-primary)]">{g.key_pattern}</span>
                {g.severity ? (
                  <span className="rounded-full bg-black/10 px-1.5 py-0.5 text-[9px] font-bold uppercase text-[var(--text-primary)]">{g.severity}</span>
                ) : null}
                {typeof g.leaf_count === "number" && g.leaf_count > 1 ? (
                  <span className="text-[10px] text-[var(--text-hint)]">파생 필드 {g.leaf_count}개</span>
                ) : null}
              </div>
              <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
                {String(g.prev)} → {String(g.now)}
                {g.rel_change != null ? ` (변화율 ${Math.round((g.rel_change as number) * 100)}%)` : ""}
              </p>
              {Array.isArray(g.sample_keys) && g.sample_keys.length > 0 ? (
                <details className="mt-1.5">
                  <summary className="cursor-pointer text-[10px] font-semibold text-[var(--accent-strong)]">
                    세부 키 {g.sample_keys.length}개 보기
                  </summary>
                  <ul className="mt-1 space-y-0.5 pl-3">
                    {(g.sample_keys as string[]).map((k, ki) => (
                      <li key={ki} className="text-[10px] text-[var(--text-hint)]">· {k}</li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        // ★그룹 미제공(구버전 응답) — 원시 나열은 최대 5행 + 접기로 강등(무제한 나열 방지).
        <>
          <ul className="mt-2 space-y-1">
            {visibleRaw.map((c, i) => (
              <li key={i} className="text-[11px] text-[var(--text-secondary)]">
                · {c.key}: {String(c.prev)} → {String(c.now)}
                {c.kind === "numeric_delta" && c.rel_change != null ? ` (변화율 ${Math.round(c.rel_change * 100)}%)` : ""}
                {c.severity ? ` · 심각도 ${c.severity}` : ""}
              </li>
            ))}
          </ul>
          {raw.length > 5 ? (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="mt-2 text-[11px] font-semibold text-[var(--accent-strong)]"
            >
              {expanded ? "접기 ▲" : `${raw.length - 5}건 더보기 ▼`}
            </button>
          ) : null}
        </>
      )}
    </div>
  );
}

/** 용적률 시나리오 표(1-B 최적화 시뮬레이션) — 전체 표 원형(요약 축약 시에도 재사용). */
function ScenarioTable({ scenarios, recommended }: { scenarios: AnalysisResult[]; recommended?: string }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-[var(--line)] text-[var(--text-hint)]">
            <th className="py-2 px-2 text-left">시나리오</th>
            <th className="py-2 px-1 text-right">달성 용적률</th>
            <th className="py-2 px-1 text-right">인센티브</th>
            <th className="py-2 px-1 text-right">기부체납</th>
            <th className="py-2 px-1 text-right">연면적 증가</th>
            <th className="py-2 px-1 text-center">상한</th>
          </tr>
        </thead>
        <tbody>
          {scenarios.map((sc, i) => (
            <tr key={i} className={`border-b border-[var(--line)]/50 ${sc.scenario_name === recommended ? "bg-[var(--accent-strong)]/5" : ""}`}>
              <td className="py-2 px-2 font-bold text-[var(--text-primary)]">
                {sc.scenario_name === recommended && <span className="text-[var(--accent-strong)] mr-1">★</span>}
                {sc.scenario_name}
              </td>
              <td className="py-2 px-1 text-right font-bold text-[var(--accent-strong)]">{sc.achieved_far}%</td>
              <td className="py-2 px-1 text-right text-[var(--text-secondary)]">+{sc.total_incentive}%</td>
              <td className="py-2 px-1 text-right text-[var(--text-secondary)]">{sc.donation_pct > 0 ? `${sc.donation_pct}%` : "-"}</td>
              <td className="py-2 px-1 text-right text-[var(--text-secondary)]">{sc.gfa_increase_sqm > 0 ? `+${sc.gfa_increase_sqm}m²` : "-"}</td>
              <td className="py-2 px-1 text-center">{sc.is_capped ? <span className="text-amber-400 text-[10px] font-bold">상한</span> : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * FarOptimizationPanel — "1-B. 용적률 최적화 시뮬레이션" 섹션.
 *
 * 전 시나리오의 achieved_far가 상한(cap_far)과 동일하면(인센티브를 더 써도 무의미) 표 대신
 * 요약 1행 + '자세히' 접기로 원 표를 강등한다. structural_cap_pct(구조상한 — 층수 제한이
 * 지배하는 경우)가 있으면 그 사실도 함께 부기해 "인센티브를 더 계산해봐야 소용없는 이유"를 밝힌다.
 */
function FarOptimizationPanel({ farOpt, structuralCapPct }: { farOpt?: AnalysisResult; structuralCapPct?: number | null }) {
  const [showDetail, setShowDetail] = useState(false);
  if (!farOpt?.scenarios) return null;
  const scenarios: AnalysisResult[] = farOpt.scenarios;
  const capFar = farOpt.cap_far;
  // achieved_far(1자리)·cap_far(2자리 가능) 반올림 자릿수가 달라 엄격 등가 대신 0.5%p
  // 허용오차로 "상한 도달"을 판정한다(소수 상한에서 요약 강등 누락 방지 — 안전 방향 유지).
  const allCapped =
    scenarios.length > 0 &&
    Number.isFinite(capFar) &&
    scenarios.every(
      (sc) => Number.isFinite(sc.achieved_far) && Math.abs((sc.achieved_far as number) - (capFar as number)) < 0.5,
    );

  return (
    <SectionCard title="1-B. 용적률 최적화 시뮬레이션" icon={TrendingUp} defaultOpen>
      <div className="grid grid-cols-3 gap-2 mb-3">
        <Field label="현재 기본 용적률" value={`${farOpt.base_far}%`} />
        <Field label="최대 달성 가능" value={`${farOpt.max_achievable_far}%`} />
        {/* 통합모드의 상한은 §84 면적가중 통합값(단일필지 시행령 정값과 의미가 달라 라벨 분리) */}
        <Field label={farOpt.integrated ? "통합 상한 (면적가중)" : "법정 상한"} value={`${capFar}%`} />
      </div>
      {farOpt.recommended_scenario && (
        <div className="rounded-lg bg-[var(--accent-strong)]/10 border border-[var(--accent-strong)]/30 p-3 mb-3">
          <p className="text-[10px] font-bold text-[var(--accent-strong)]">추천: {farOpt.recommended_scenario}</p>
          <p className="text-[10px] text-[var(--text-secondary)]">{farOpt.recommended_reason}</p>
        </div>
      )}
      {allCapped ? (
        <div className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3">
          <p className="text-xs font-bold text-[var(--text-primary)]">
            모든 시나리오가 상한 {capFar}%에서 cap — 인센티브 추가 완화 불가
          </p>
          {structuralCapPct != null && (
            <p className="mt-1 text-[11px] text-amber-400">
              층수 제한이 지배 — 구조상한 {structuralCapPct}% 기준으론 인센티브 무의미
            </p>
          )}
          <button
            type="button"
            onClick={() => setShowDetail((v) => !v)}
            className="mt-2 text-[11px] font-semibold text-[var(--accent-strong)]"
          >
            {showDetail ? "표 접기 ▲" : "자세히(원 표) ▼"}
          </button>
          {showDetail && (
            <div className="mt-2">
              <ScenarioTable scenarios={scenarios} recommended={farOpt.recommended_scenario} />
            </div>
          )}
        </div>
      ) : (
        <ScenarioTable scenarios={scenarios} recommended={farOpt.recommended_scenario} />
      )}
    </SectionCard>
  );
}

/* ── Types ── */

interface ModelInfo {
  id: string;
  name: string;
  tier: "standard" | "premium" | "economy";
}

interface ProviderInfo {
  provider: string;
  name: string;
  models: ModelInfo[];
  default_model: string;
}

/* ── Main Component ── */

type AnalysisResult = Record<string, any>;

// ★F3(QA REQUEST CHANGES) supply_areas 항목 타입 — additive(blocked_reason?/note? 신설).
//   백엔드가 개발불가 게이트(GB·비연접 등)로 공급규모 산정을 억제할 때 dev_type/지표 필드는
//   전부 비우고(undefined) blocked_reason(또는 note)만 채워 반환한다("판정불가" 스텁 — P0-2/F1).
//   나머지 필드는 AnalysisResult(Record<string, any>) 계약을 그대로 잇는다(느슨한 기존 패턴 유지).
type SupplyAreaItem = AnalysisResult & {
  dev_type?: string | null;
  total_gfa_pyeong?: number | null;
  blocked_reason?: string | null;
  note?: string | null;
};

export function ComprehensiveAnalysisPanel() {
  const siteAnalysis = useProjectContextStore((state) => state.siteAnalysis);
  const [address, setAddress] = useState("");
  // 다필지: 검색·엑셀로 등록된 전 필지 주소(2필지↑ 시 통합 개발방식 분석 노출)
  const [parcels, setParcels] = useState<string[]>([]);
  // ★다필지 통합분석용 필지 상세(면적·용도지역·실효한도) — 백엔드 통합집계 전송 페이로드.
  const [parcelRows, setParcelRows] = useState<ParcelRow[]>([]);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>("anthropic");
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [selectionNotice, setSelectionNotice] = useState("");

  useEffect(() => {
    apiClient.get<{ providers: ProviderInfo[] }>("/analysis/llm-providers")
      .then(data => {
        setProviders(data.providers ?? []);
        if ((data.providers?.length ?? 0) > 0) {
          setSelectedProvider(data.providers[0].provider);
          setSelectedModel(data.providers[0].default_model);
        }
      })
      .catch(() => {}); // 실패 시 기본값 유지
  }, []);

  useEffect(() => {
    if (!siteAnalysis) {
      setAddress("");
      setParcels([]);
      setParcelRows([]);
      return;
    }
    const mainAddr = siteAnalysis.address ?? "";
    setAddress(mainAddr);
    
    // 이전 분석결과 무효화 (주소 불일치 시 stale 표시 차단)
    if (mainAddr && result && mainAddr !== (result as any).address) {
      setResult(null);
      setError(null);
    }
    
    const parcelList = siteAnalysis.parcels ?? [];
    if (parcelList.length > 0) {
      setParcels(parcelList.map((p) => p.address).filter(Boolean));
      setParcelRows(
        parcelList
          .filter((p) => (p.areaSqm ?? 0) > 0)
          .map((p) => ({
            address: p.address,
            area_sqm: p.areaSqm ?? null,
            zone_type: p.zoneCode ?? null,
            farPct: null,
            bcrPct: null,
            farLegalPct: null,
            bcrLegalPct: null,
            // ★P1(감사): 경계 전송 — 서버 통합집계의 인접성(contiguous) 판정 재료.
            geometry: p.geometry ?? null,
          }))
      );
    } else if (mainAddr) {
      setParcels([mainAddr]);
      setParcelRows([
        {
          address: mainAddr,
          // ★P1(감사): raw landAreaSqm 직독 금지 — 다필지 통합면적 우선 공용헬퍼로
          //   (단일 PNU 재조회가 대표면적으로 덮어써도 통합면적이 이긴다: 면적 SSOT 패리티).
          area_sqm: effectiveLandAreaSqm(siteAnalysis) ?? null,
          zone_type: siteAnalysis.zoneCode ?? null,
          farPct: null,
          bcrPct: null,
          farLegalPct: null,
          bcrLegalPct: null,
        }
      ]);
    }
  }, [siteAnalysis, result]);

  const handleAnalyze = useCallback(async () => {
    if (!address.trim()) { setError("주소를 입력해주세요."); return; }
    setLoading(true); setError(null); setResult(null);
    try {
      const data = await apiClient.post<AnalysisResult>("/analysis/comprehensive", {
        body: {
          address,
          llm_provider: selectedProvider || undefined,
          llm_model: selectedModel || undefined,
          // ★다필지(2필지↑)면 통합집계용 필지목록 전송 → 종합분석이 '통합면적' 기준 산출(543㎡ 단일 버그 제거).
          //   단일/미등록은 미전송(백엔드 단일경로 = N=1 항등). 면적 보유 필지만.
          ...(parcelRows.length > 1 ? { parcels: parcelRows } : {}),
        },
        useMock: false,
      });
      setResult(data);
    } catch (e) {
      // 원시 개발자 문자열(Error:…·[object Object]) 노출 금지 — 통상어 안내(정직 표기).
      setError(e instanceof Error ? e.message : "종합분석 중 오류가 발생했습니다. 입력을 확인하고 다시 시도해 주세요.");
    } finally {
      setLoading(false);
    }
  }, [address, selectedProvider, selectedModel, parcelRows]);

  const ef = result?.effective_far || {};
  const supplyAreas: SupplyAreaItem[] = result?.supply_areas || [];
  const landPrices = result?.land_prices || {};
  const transactions = result?.transaction_prices || {};
  const salePrices: AnalysisResult[] = result?.sale_prices || [];
  const location = result?.location || {};
  const devPlans = result?.development_plans || {};

  return (
    <div className="space-y-4">
      {/* 사통팔땅 전역 싱글 통합지도 워크스페이스 (대시보드와 100% 동일한 필지 입력 + 멀티지도 엔진) */}
      <SatongMapShellDynamic locale="ko" />
      {/* Header */}
      <div className="rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--surface-strong)] p-6">
        <h2 className="text-xl font-black text-[var(--text-primary)] mb-1">종합 부지분석 보고서</h2>
        <p className="text-xs text-[var(--text-secondary)] mb-4">주소를 입력하면 7개 카테고리 자동 분석 보고서를 생성합니다</p>
        {selectionNotice && (
          <p className="mb-3 rounded-xl border border-lime-400/40 bg-lime-400/10 px-3 py-2 text-xs font-bold text-lime-700">
            {selectionNotice}
          </p>
        )}
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)]/50 p-4">
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">분석 대상 정보</span>
            <h3 className="text-sm font-black text-[var(--text-primary)] mt-0.5">
              {address ? (
                <span className="inline-flex items-center gap-1.5">
                  <MapPin className="size-4 text-[var(--accent-strong)]" />
                  {address}
                  {parcels.length > 1 ? (
                    <span className="text-xs font-bold text-[var(--accent-strong)]">(외 {parcels.length - 1}필지 선택됨)</span>
                  ) : null}
                </span>
              ) : (
                <span className="text-[var(--text-hint)]">상단 통합 지도를 클릭하거나 검색하여 필지를 선택해 주세요.</span>
              )}
            </h3>
          </div>
          <div className="flex items-center gap-3">
            {effectiveLandAreaSqm(siteAnalysis) ? (
              <div className="text-right text-xs font-bold text-[var(--text-secondary)] mr-2">
                <p>총 대지면적: <span className="text-[var(--text-primary)]">{(effectiveLandAreaSqm(siteAnalysis) as number).toLocaleString()}㎡</span></p>
                <p className="text-[10px] text-[var(--text-hint)] mt-0.5">용도: {siteAnalysis?.dominantZoneCode || siteAnalysis?.zoneCode || "미확인"}</p>
              </div>
            ) : null}
            <button
              onClick={handleAnalyze}
              disabled={loading || !address.trim()}
              className="shrink-0 rounded-xl bg-[var(--accent-strong)] px-6 py-3 text-sm font-bold text-white shadow-[var(--shadow-glow)] transition-all hover:brightness-110 disabled:opacity-50"
            >
              {loading ? "분석 중..." : "종합 분석 시작"}
            </button>
          </div>
        </div>
        {providers.length > 0 ? (
          <div className="flex gap-3 items-center mt-3">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold text-[var(--text-hint)]">AI 모델</span>
              <select
                value={selectedProvider}
                onChange={(e) => {
                  setSelectedProvider(e.target.value);
                  const p = providers.find(pr => pr.provider === e.target.value);
                  if (p) setSelectedModel(p.default_model);
                }}
                className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-1.5 text-xs text-[var(--text-primary)]"
              >
                {providers.map(p => (
                  <option key={p.provider} value={p.provider}>{p.name}</option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold text-[var(--text-hint)]">모델</span>
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-1.5 text-xs text-[var(--text-primary)]"
              >
                {providers.find(p => p.provider === selectedProvider)?.models.map(m => (
                  <option key={m.id} value={m.id}>
                    {m.name} {m.tier === "premium" ? "★" : m.tier === "economy" ? "⚡" : ""}
                  </option>
                ))}
              </select>
            </div>
          </div>
        ) : (
          <p className="text-[10px] text-[var(--text-hint)] mt-2">AI 해석: API 키 미설정 (규칙 기반 분석만 제공)</p>
        )}
      </div>

      {/* 입지 인프라(POI) 분석 — 주소 선택 시. 분석결과 있으면 context로 통합 입지점수 산출 */}
      {address.trim() && (
        <SiteInfraPoiCard
          address={address}
          context={result ? (result as unknown as Record<string, unknown>) : undefined}
        />
      )}

      {/* 다필지(2필지↑) 통합 개발방식 분석 — 검색·엑셀로 등록 시 자동 노출 */}
      {parcels.length > 1 && (
        <DevelopmentScenarioCard address={address} parcels={parcels} />
      )}

      {error && (
        <div className="rounded-xl bg-red-500/10 border border-red-500/30 p-4 text-sm text-red-400">{error}</div>
      )}

      {loading && (
        <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-strong)] p-8 text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-3 border-[var(--accent-strong)] border-t-transparent mb-3" />
          <p className="text-sm text-[var(--text-secondary)]">7개 카테고리 분석 중... (약 5~10초)</p>
          <div className="mt-3 flex items-center justify-center gap-2">
            <span className="inline-block h-2 w-2 rounded-full bg-blue-400 animate-pulse" />
            <p className="text-[11px] text-blue-400">AI 해석 생성 중...</p>
          </div>
        </div>
      )}

      {result && (
        <div className="space-y-3">
          {/* ★결정론 모순탐지(contradictions) — prior(원장) 대비 status 플립·수치 델타(상단 경고).
              백엔드 detect_contradictions 산출을 그간 미렌더(핸드오프 손실). 모순 0건이면 렌더 안 함.
              groups[] 있으면 패턴별 그룹 카드, 없으면 원시 나열(최대 5행+접기)로 강등(ContradictionsCard). */}
          <ContradictionsCard contradictions={result.contradictions} />

          {/* 기본 정보 요약 */}
          <div className="rounded-2xl border border-[var(--accent-strong)]/20 bg-[var(--surface-strong)] p-5">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <Field label="주소" value={result.address || ""} />
              <Field label="PNU" value={result.pnu || "-"} />
              <Field label="용도지역" value={result.zone_type || "-"} />
              <Field label="대지면적" value={formatArea(result.land_area_sqm)} />
            </div>
          </div>

          {/* ★정합성 안내 배너 — 비연접 파편 필지(다필지 통합 불가) 경고 + 백엔드 warnings[](이미
              라이브였으나 미렌더였던 핸드오프 손실 해소). §2 "판정불가" 스텁과 동일 논조로
              페이지 전체 정직 표기 일관성을 맞춘다(가짜 통합수치를 그대로 믿지 않도록 상단에 배치). */}
          {(result.integrated_zoning?.adjacency_contiguous === false ||
            (Array.isArray(result.warnings) && result.warnings.length > 0)) && (
            <div className="rounded-2xl border border-[var(--status-warning)]/40 bg-[color-mix(in_srgb,var(--status-warning)_8%,transparent)] p-4 space-y-2">
              {result.integrated_zoning?.adjacency_contiguous === false && (
                <p className="text-xs font-bold leading-relaxed text-[var(--status-warning)]">
                  비연접 파편 필지
                  {typeof result.integrated_zoning?.cluster_count === "number"
                    ? ` ${result.integrated_zoning.cluster_count}개 클러스터`
                    : ""}
                  {" "}— 단일 대지 통합개발 불가. 아래 통합 수치는 참고용이며 클러스터별 분석이 필요합니다.
                </p>
              )}
              {Array.isArray(result.warnings) && result.warnings.length > 0 && (
                <ul className="space-y-1">
                  {(result.warnings as string[]).map((w, i) => (
                    <li key={i} className="text-[11px] text-[var(--text-secondary)]">· {w}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* 시니어 전문가 자문 verdict(심의·도시계획·법무) — 백엔드 senior_consultation 소비 */}
          <SeniorVerdictCard
            consultation={(result as { senior_consultation?: SeniorConsultation }).senior_consultation}
            title="시니어 종합 자문(심의·도시계획·법무)"
          />

          {/* ★SpecialistAgent 결정론 교차검증(전수감사 #2) — 백엔드 result.specialists 소비.
              zoning 허용용도·far 실효검증·심의/설계(엔진 가용 시)를 동기 수집해 화면 반영.
              그간 .delay fire-and-forget로 결과 미반영이던 갭 해소. specialists 비면 미렌더(graceful). */}
          <DecisionSpecialistCard
            specialists={(result as { specialists?: DecisionSpecialist[] }).specialists}
          />

          {/* ★특이부지 게이트(학교·GB·맹지·농지 등) — 백엔드 special_parcel/developability 소비.
              표시 누락 시 '최대 연면적 가능' 오해 위험이므로 경고를 명시 렌더(orphan handoff 해소). */}
          {result.special_parcel?.is_special && (
            <div className="rounded-2xl border border-[var(--status-warning)]/40 bg-[color-mix(in_srgb,var(--status-warning)_8%,transparent)] p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-bold text-[var(--status-warning)]">특이부지 제약 감지</span>
                {result.developability ? (
                  <span className="rounded-full border border-[var(--status-warning)]/40 px-2 py-0.5 text-[10px] font-semibold text-[var(--status-warning)]">
                    {result.developability}
                  </span>
                ) : null}
              </div>
              {(result.special_parcel.honest_disclosure || result.special_parcel.development_caveat) && (
                <p className="mt-1.5 text-xs leading-relaxed text-[var(--text-secondary)]">
                  {result.special_parcel.honest_disclosure || result.special_parcel.development_caveat}
                </p>
              )}
            </div>
          )}

          {/* ★현행 허용건축물(별표2~20) — 백엔드 allowed_buildings 소비(orphan handoff 해소).
              스토리: "지금 지을 수 있는 것"을 먼저 보여준 다음, 그 아래 랭킹으로 사업성을 비교한다. */}
          <AllowedBuildingsCard data={result.allowed_buildings} floorCap={ef.floor_cap} />

          {/* ★건축가능항목 랭킹(Stage 1) — 백엔드 buildable_options 소비(orphan handoff 해소) */}
          <BuildableOptionsCard data={result.buildable_options} />
          {/* ★ai_interpretation.buildable_options_interpretation — 12해석키 중 미소비였던 마지막 1건(핸드오프 손실 해소) */}
          {result.ai_interpretation?.buildable_options_interpretation && (
            <AiInterpretation text={result.ai_interpretation.buildable_options_interpretation} />
          )}

          {/* ★종상향/종변경 잠재(예상치 — 현행과 분리) — 백엔드 upzoning 소비 */}
          {Array.isArray(result.upzoning_scenarios) && result.upzoning_scenarios.length > 0 && (
            <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-bold text-[var(--text-primary)]">종상향 잠재 시나리오</span>
                <span className="text-[10px] text-[var(--text-secondary)]">★예상치 — 현행 실효 용적률과 분리</span>
                {result.potential_far_range ? (
                  <span className="text-xs font-semibold text-[var(--accent-strong)]">
                    예상 상한 {result.potential_far_range.min_pct}~{result.potential_far_range.max_pct}%
                  </span>
                ) : null}
              </div>
              <ul className="mt-2 space-y-1">
                {result.upzoning_scenarios.slice(0, 4).map((s: Record<string, any>, i: number) => (
                  <li key={i} className="text-[11px] text-[var(--text-secondary)]">
                    · {s.path} → {s.target_zone}
                    {s.expected_far_pct_high != null ? ` (예상 ${s.expected_far_pct_high}%)` : ""}
                    {s.feasibility ? ` · 가능성 ${s.feasibility}` : ""}
                    {/* ★신규(additive) blocked_reasons — 비연접 등으로 구역 성립이 불확실한 사유(정직 표기). */}
                    {Array.isArray(s.blocked_reasons) && s.blocked_reasons.length > 0
                      ? ` · ${(s.blocked_reasons as string[]).join(" · ")}`
                      : ""}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* ★산출 근거·법령링크(EvidencePanel) — 백엔드 evidence/legal_refs 소비.
              '용적률 200% 왜 나왔나'의 법령 원문까지 표면화(근거 기본제공·할루시네이션 가드 전역원칙). */}
          <EvidencePanel
            items={adaptEvidence(result.evidence, result.legal_refs)}
            title="산출 근거·법령"
            defaultOpen={false}
          />

          {/* AI 종합 요약 */}
          {result.ai_interpretation?.overall_summary && (
            <div className="rounded-2xl border border-[var(--accent-strong)]/30 bg-gradient-to-r from-[var(--accent-strong)]/5 to-transparent p-6">
              <h3 className="text-sm font-bold text-[var(--accent-strong)] mb-2">AI 종합 분석</h3>
              <p className="text-xs text-[var(--text-secondary)] leading-relaxed whitespace-pre-line">
                {result.ai_interpretation.overall_summary}
              </p>
              {result.ai_interpretation.risk_factors && (
                <div className="mt-3 flex gap-4">
                  <div className="flex-1 rounded-lg bg-red-500/5 border border-red-500/20 p-3">
                    <p className="text-[10px] font-bold text-red-400 mb-1">리스크 요인</p>
                    <p className="text-[10px] text-[var(--text-secondary)] whitespace-pre-line">{result.ai_interpretation.risk_factors}</p>
                  </div>
                  <div className="flex-1 rounded-lg bg-emerald-500/5 border border-emerald-500/20 p-3">
                    <p className="text-[10px] font-bold text-emerald-400 mb-1">기회 요인</p>
                    <p className="text-[10px] text-[var(--text-secondary)] whitespace-pre-line">{result.ai_interpretation.opportunity_factors}</p>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* AI 시장분석 종합 해석 (market_interpretation) — market_interpretation이 빈 객체({})로만
              와도 헤더 셸이 남지 않도록 실제 내용(6개 하위텍스트 중 1개 이상) 보유 여부로 게이트한다.
              내용이 없고 market_interpretation_status.reason이 있으면 정직 미생성 사유 한 줄만 표기(무목업). */}
          {(() => {
            const mi = result.market_interpretation as AnalysisResult | undefined;
            const miFields = mi
              ? [mi.market_overview, mi.price_trend_analysis, mi.comparable_analysis, mi.investment_insight, mi.risk_factors, mi.timing_recommendation]
              : [];
            const hasMarketInterp = miFields.some((v) => typeof v === "string" && v.trim().length > 0);
            if (hasMarketInterp && mi) {
              return (
                <div className="rounded-2xl border border-emerald-500/25 bg-emerald-500/5 p-6">
                  <h3 className="mb-3 inline-flex items-center gap-1.5 text-sm font-bold text-emerald-400"><BarChart3 className="size-4" aria-hidden /> AI 시장분석</h3>
                  <div className="space-y-3">
                    {mi.market_overview && <MarketAiBlock label="시장 종합 현황" text={mi.market_overview} />}
                    {mi.price_trend_analysis && <MarketAiBlock label="가격 추이·전망" text={mi.price_trend_analysis} />}
                    {mi.comparable_analysis && <MarketAiBlock label="유사물건 비교" text={mi.comparable_analysis} />}
                    {mi.investment_insight && <MarketAiBlock label="투자 시사점" text={mi.investment_insight} />}
                    {mi.risk_factors && <MarketAiBlock label="시장 리스크" text={mi.risk_factors} />}
                    {mi.timing_recommendation && <MarketAiBlock label="매수·개발 타이밍" text={mi.timing_recommendation} />}
                  </div>
                </div>
              );
            }
            if (result.market_interpretation_status?.reason) {
              return (
                <p className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2.5 text-xs text-[var(--text-hint)]">
                  시장분석 미생성 — 사유: {result.market_interpretation_status.reason}
                </p>
              );
            }
            return null;
          })()}

          {/* Section 1: 실효용적률 */}
          <SectionCard title="1. 실효용적률 산정" icon={BarChart3} defaultOpen>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              <Field label="법정 건폐율 (국토계획법)" value={`${ef.national_bcr_pct ?? "-"}%`} />
              <Field label="법정 용적률 (국토계획법)" value={`${ef.national_far_pct ?? "-"}%`} />
              <Field label="조례 건폐율 (지자체)" value={`${ef.ordinance_bcr_pct ?? "-"}%`} />
              <Field label="조례 용적률 (지자체)" value={`${ef.ordinance_far_pct ?? "-"}%`} />
              <Field label="실효 건폐율" value={`${ef.effective_bcr_pct ?? "-"}%`} />
              <Field label="실효 용적률" value={`${ef.effective_far_pct ?? "-"}%`} />
            </div>
            {ef.source && <p className="text-[10px] text-[var(--text-hint)] mt-1">출처: {ef.source}</p>}
            {/* ★신규(additive) structural_cap_pct — 구조상한(층수 제한 등)이 조례 용적률보다
                더 타이트하게 걸리는 경우를 명시(예: 4층 이하 제한 부지). 없으면 미표시(무목업). */}
            {ef.structural_cap_pct != null && (
              <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
                <p className="text-[11px] font-bold text-amber-400">
                  구조상한 {ef.structural_cap_pct}%{ef.floor_cap != null ? ` · ${ef.floor_cap}층 이하` : ""}
                </p>
                {ef.floor_cap_basis && (
                  <p className="mt-0.5 text-[10px] text-[var(--text-secondary)]">근거: {ef.floor_cap_basis}</p>
                )}
              </div>
            )}
            {Array.isArray(ef.annotations) && ef.annotations?.length > 0 && (
              <div className="mt-3 rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3 space-y-1.5">
                <p className="text-[10px] font-bold text-[var(--text-hint)] mb-1">분석 근거</p>
                {(ef.annotations ?? []).map((note: string, i: number) => (
                  <AnnotationLine key={i} text={note} />
                ))}
              </div>
            )}
            {result.ai_interpretation?.effective_far_interpretation && (
              <AiInterpretation text={result.ai_interpretation.effective_far_interpretation} />
            )}
          </SectionCard>

          {/* Section 1-B: 용적률 최적화 시뮬레이션 — 전 시나리오 cap 동일 시 요약+접기(FarOptimizationPanel) */}
          <FarOptimizationPanel farOpt={ef.far_optimization} structuralCapPct={ef.structural_cap_pct} />

          {/* Section 2: 개발방식별 적정공급면적 */}
          <SectionCard title="2. 개발방식별 적정공급면적 산정" icon={Construction} defaultOpen>
            {supplyAreas.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-[var(--line)] text-[var(--text-hint)]">
                      <th className="py-2 px-2 text-left">개발유형</th>
                      <th className="py-2 px-1 text-right">전용율</th>
                      <th className="py-2 px-1 text-right">공급면적/세대</th>
                      <th className="py-2 px-1 text-right">연면적</th>
                      <th className="py-2 px-1 text-right">세대수</th>
                      <th className="py-2 px-1 text-right">층수</th>
                      <th className="py-2 px-1 text-right">주차</th>
                      <th className="py-2 px-1 text-right">공사비(추정)</th>
                      <th className="py-2 px-1 text-center">인허가</th>
                      <th className="py-2 px-1 text-center">적합성</th>
                    </tr>
                  </thead>
                  <tbody>
                    {supplyAreas.map((sa: SupplyAreaItem, i: number) => {
                      // ★F3(QA REQUEST CHANGES) 개발불가 게이트 정직 표기 — 백엔드가 공급규모를
                      //   산정하지 않은 항목(total_gfa_pyeong 미확보 + blocked_reason/note 보유,
                      //   P0-2/F1의 "판정불가" 스텁)은 undefined평·₩NaN 지표 행 대신 colSpan
                      //   전체 설명 행으로 사유를 표시한다(가짜 지표 은폐 금지).
                      const blockedText = sa.blocked_reason || sa.note;
                      const rowKey = sa.dev_type ?? `blocked-${i}`;
                      if (sa.total_gfa_pyeong == null && blockedText) {
                        return (
                          <tr key={rowKey} className="border-b border-[var(--line)]/50">
                            <td
                              colSpan={10}
                              className="py-3 px-3 text-xs leading-relaxed text-[var(--status-warning)] bg-[color-mix(in_srgb,var(--status-warning)_8%,transparent)] rounded"
                            >
                              {sa.type_name ? `${sa.type_name} — ` : ""}{blockedText}
                            </td>
                          </tr>
                        );
                      }
                      return (
                      <tr key={rowKey} className={`border-b border-[var(--line)]/50 hover:bg-[var(--surface-soft)] transition-colors ${sa.feasibility_status === "부적합" ? "opacity-50" : ""}`}>
                        <td className="py-2.5 px-2 font-bold text-[var(--text-primary)]">{sa.type_name}</td>
                        <td className="py-2.5 px-1 text-right text-[var(--text-secondary)]">{sa.exclusive_ratio_pct}%</td>
                        <td className="py-2.5 px-1 text-right text-[var(--text-secondary)]">{sa.supply_area_per_unit_pyeong}평</td>
                        <td className="py-2.5 px-1 text-right text-[var(--accent-strong)] font-bold">{sa.total_gfa_pyeong}평</td>
                        <td className="py-2.5 px-1 text-right text-[var(--text-primary)] font-bold">{sa.unit_count}</td>
                        <td className="py-2.5 px-1 text-right text-[var(--text-secondary)]">{sa.floor_count}층</td>
                        <td className="py-2.5 px-1 text-right text-[var(--text-secondary)]">{sa.parking_count}대</td>
                        <td className="py-2.5 px-1 text-right text-[var(--text-secondary)]">{formatWon(sa.estimated_construction_cost_won)}</td>
                        <td className="py-2.5 px-1 text-center"><PermitBadge complexity={sa.permit_complexity} /></td>
                        <td className="py-2.5 px-1 text-center">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${
                            sa.feasibility_status === "적합" ? "bg-emerald-500/20 text-emerald-400" :
                            sa.feasibility_status === "조건부" ? "bg-amber-500/20 text-amber-400" :
                            sa.feasibility_status === "부적합" ? "bg-red-500/20 text-red-400" :
                            "bg-gray-500/20 text-gray-400"
                          }`}>{sa.feasibility_status || "-"}</span>
                        </td>
                      </tr>
                      );
                    })}
                  </tbody>
                </table>
                {/* 유형별 검증 상세 */}
                {supplyAreas.filter((sa: AnalysisResult) => sa.conditions_met?.length > 0).length > 0 && (
                  <div className="mt-3 space-y-2">
                    <p className="text-[10px] font-bold text-[var(--text-hint)]">유형별 법적 조건 검증 상세</p>
                    {supplyAreas.map((sa: AnalysisResult) => {
                      const conditions = sa.conditions_met as AnalysisResult[] | undefined;
                      if (!conditions || conditions.length === 0) return null;
                      return (
                        <div key={sa.dev_type} className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3">
                          <p className="text-[11px] font-bold text-[var(--text-primary)] mb-1">
                            {sa.type_name}
                            <span className={`ml-2 text-[10px] px-1.5 py-0.5 rounded ${
                              sa.feasibility_status === "적합" ? "bg-emerald-500/20 text-emerald-400" :
                              sa.feasibility_status === "부적합" ? "bg-red-500/20 text-red-400" :
                              "bg-amber-500/20 text-amber-400"
                            }`}>{sa.feasibility_status}</span>
                          </p>
                          <div className="space-y-0.5">
                            {conditions.map((c: AnalysisResult, i: number) => (
                              <p key={i} className="text-[10px] text-[var(--text-secondary)]">
                                <span className={`inline-block w-3 h-3 mr-1 rounded-full text-center text-[8px] leading-3 font-bold ${
                                  c.status === "pass" ? "bg-emerald-500/20 text-emerald-400" :
                                  c.status === "fail" ? "bg-red-500/20 text-red-400" :
                                  c.status === "unknown" ? "bg-gray-500/20 text-gray-400" :
                                  "bg-amber-500/20 text-amber-400"
                                }`}>{c.status === "pass" ? "O" : c.status === "fail" ? "X" : "?"}</span>
                                <span className="font-medium">{c.rule}:</span> {c.detail}
                              </p>
                            ))}
                          </div>
                          {sa.recommendations?.length > 0 && (
                            <div className="mt-1 pt-1 border-t border-[var(--line)]">
                              {(sa.recommendations as string[]).map((r: string, i: number) => (
                                <p key={i} className="text-[10px] text-[var(--accent-strong)]">→ {r}</p>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            ) : (
              <p className="text-xs text-[var(--text-hint)] italic">해당 용도지역에서 허용된 개발유형이 없습니다</p>
            )}
            {result.ai_interpretation?.supply_area_interpretation && (
              <AiInterpretation text={result.ai_interpretation.supply_area_interpretation} />
            )}
          </SectionCard>

          {/* Section 3: 토지 주변시세 */}
          <SectionCard title="3. 토지 주변시세" icon={Wallet}>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              <Field label="공시지가 (원/m²)" value={formatManWon(landPrices.official_price_per_sqm / 10000)} />
              <Field label="공시지가 총액" value={formatWon(landPrices.total_official_value_won)} />
              <Field label="추정 시세 (원/m²)" value={formatManWon(landPrices.estimated_market_per_sqm / 10000)} />
              <Field label="추정 시세 총액" value={formatWon(landPrices.total_estimated_value_won)} />
              <Field label="시세 보정계수" value={`×${landPrices.market_multiplier ?? "-"}`} />
            </div>
            {result.ai_interpretation?.land_price_interpretation && (
              <AiInterpretation text={result.ai_interpretation.land_price_interpretation} />
            )}
          </SectionCard>

          {/* Section 4: 물건별 주변 실거래가 */}
          <SectionCard title="4. 물건별 주변 실거래가" icon={Home}>
            {Object.keys(transactions).length > 0 && !transactions.error ? (
              <div className="space-y-2">
                {Object.entries(transactions).map(([type, data]) => {
                  const d = data as AnalysisResult;
                  if (!d || !d.count) return null;
                  return (
                    <div key={type} className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3">
                      <p className="text-xs font-bold text-[var(--text-primary)] mb-1">
                        {type} ({d.count}건)
                        {d.excluded_outliers > 0 && (
                          <span className="ml-1 text-[10px] font-normal text-[var(--text-hint)]">· 이상치 {d.excluded_outliers}건 제외(지분·정정 등)</span>
                        )}
                      </p>
                      <div className="grid grid-cols-3 gap-2 text-[11px]">
                        <div><span className="text-[var(--text-hint)]">평균: </span><span className="font-bold">{formatManWon(d.avg_price_10k)}</span></div>
                        <div><span className="text-[var(--text-hint)]">최고: </span><span className="font-bold">{formatManWon(d.max_price_10k)}</span></div>
                        <div><span className="text-[var(--text-hint)]">최저: </span><span className="font-bold">{formatManWon(d.min_price_10k)}</span></div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-xs text-[var(--text-hint)] italic">{transactions.error || transactions.message || "실거래 데이터 없음"}</p>
            )}
            {result.ai_interpretation?.transaction_interpretation && (
              <AiInterpretation text={result.ai_interpretation.transaction_interpretation} />
            )}
          </SectionCard>

          {/* Section 5: 물건별 분양가 */}
          <SectionCard title="5. 개발유형별 예상 분양가" icon={Tag}>
            {salePrices.length > 0 ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {salePrices.map((sp: AnalysisResult) => (
                  <div key={sp.dev_type} className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3">
                    <p className="text-[10px] text-[var(--text-hint)]">{sp.type_name}</p>
                    <p className="text-sm font-bold text-[var(--accent-strong)]">{formatManWon(sp.sale_price_per_pyeong_man)}/평</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-[var(--text-hint)] italic">분양가 데이터 없음</p>
            )}
            {result.ai_interpretation?.sale_price_interpretation && (
              <AiInterpretation text={result.ai_interpretation.sale_price_interpretation} />
            )}
          </SectionCard>

          {/* Section 6: 입지분석 */}
          <SectionCard title="6. 입지분석" icon={MapPin}>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              <Field label="입지 점수" value={`${location.location_score ?? "-"}점 (${location.grade ?? "-"})`} />
              {location.transportation?.nearest_subway && (
                <>
                  <Field label="최근접 지하철" value={location.transportation.nearest_subway.name || "-"} />
                  <Field label="지하철 거리" value={`${location.transportation.nearest_subway.distance_m ?? "-"}m`} />
                </>
              )}
              <Field label="인근 학교" value={`${location.education?.school_count ?? 0}개교`} />
            </div>
            {/* ★입지 점수 산정 근거(score_breakdown) — 핸드오프 손실 해소(그간 location_score만 표시). */}
            {Array.isArray(location.score_breakdown) && location.score_breakdown.length > 0 && (
              <div className="mt-3 rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3 space-y-1">
                <p className="text-[10px] font-bold text-[var(--text-hint)] mb-1">입지 점수 산정 근거</p>
                {(location.score_breakdown as string[]).map((s: string, i: number) => (
                  <p key={i} className="text-[10px] text-[var(--text-secondary)]">· {s}</p>
                ))}
              </div>
            )}
            {result.ai_interpretation?.location_interpretation && (
              <AiInterpretation text={result.ai_interpretation.location_interpretation} />
            )}
          </SectionCard>

          {/* Section 7: 주변 개발계획 */}
          {(() => {
            // ★신규(additive) land_use_regulations_detail — {name, link|null}. 있으면 이름+링크로
            //   렌더(이름 중복 제거·순서 보존), 없으면 기존 land_use_regulations(문자열 배열)로 폴백.
            const rawDetail: AnalysisResult[] = Array.isArray(devPlans.land_use_regulations_detail)
              ? devPlans.land_use_regulations_detail
              : [];
            const seenNames = new Set<string>();
            const regDetail = rawDetail.filter((r) => {
              const n = (r?.name ?? "").trim();
              if (!n || seenNames.has(n)) return false;
              seenNames.add(n);
              return true;
            });
            const regItems: { name: string; link?: string | null }[] =
              regDetail.length > 0
                ? regDetail.map((r) => ({ name: r.name, link: r.link ?? null }))
                : (devPlans.land_use_regulations ?? []).map((name: string) => ({ name, link: null }));
            const specialDistricts: string[] = Array.isArray(devPlans.special_districts)
              ? devPlans.special_districts
              : [];
            const hasAnyRegInfo = regItems.length > 0 || specialDistricts.length > 0;

            return (
              <SectionCard title="7. 주변 개발계획 및 규제" icon={Map}>
                {hasAnyRegInfo ? (
                  <div className="space-y-2">
                    {regItems.length > 0 && (
                      <div className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3">
                        <div className="mb-2 flex flex-wrap items-center gap-2">
                          <p className="text-[10px] font-bold text-[var(--text-hint)]">토지이용계획 규제</p>
                          {/* ★risk_level(종합 리스크) — 핸드오프 손실 해소(그간 규제명 나열만 표시). */}
                          {devPlans.risk_level && (
                            <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[9px] font-bold ${RISK_LEVEL_STYLE[devPlans.risk_level as string] || RISK_LEVEL_STYLE["낮음"]}`}>
                              종합 리스크 {devPlans.risk_level}
                            </span>
                          )}
                        </div>
                        <div className="space-y-1">
                          {regItems.map((reg, i) => {
                            // ★regulation_notes(이름별 해석 주석) — 매칭되면 회색 보조텍스트로 병기(핸드오프 손실 해소).
                            const note = (devPlans.regulation_notes as AnalysisResult[] | undefined)?.find(
                              (n: AnalysisResult) => n?.name === reg.name,
                            );
                            return (
                              <div key={i} className="flex flex-col gap-0.5">
                                <div className="flex items-center gap-2 text-[11px]">
                                  <span className="h-1.5 w-1.5 rounded-full bg-amber-400 shrink-0" />
                                  <span className="text-[var(--text-primary)]">{reg.name}</span>
                                  {/* 근거 링크 — url 있을 때만(가짜 링크 날조 금지), 새 탭으로 열기. */}
                                  {reg.link ? (
                                    <a
                                      href={reg.link}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      title={`${reg.name} 근거 새 탭에서 열기`}
                                      aria-label={`${reg.name} 근거 새 탭에서 열기`}
                                      className="inline-flex items-center text-[var(--accent-strong)] hover:opacity-80"
                                    >
                                      <ExternalLink className="size-3" aria-hidden />
                                    </a>
                                  ) : null}
                                </div>
                                {note?.interpretation && (
                                  <p className="ml-3.5 text-[10px] text-[var(--text-hint)]">{note.interpretation}</p>
                                )}
                              </div>
                            );
                          })}
                        </div>
                        {/* ★risk_factors(리스크 유발 규제 목록) — 핸드오프 손실 해소. */}
                        {Array.isArray(devPlans.risk_factors) && devPlans.risk_factors.length > 0 && (
                          <div className="mt-3 space-y-1 border-t border-[var(--line)] pt-2">
                            <p className="text-[10px] font-bold text-[var(--text-hint)] mb-1">리스크 요인</p>
                            {(devPlans.risk_factors as string[]).map((f: string, i: number) => (
                              <div key={i} className="flex items-center gap-2 text-[11px]">
                                <span className="h-1.5 w-1.5 rounded-full bg-amber-400 shrink-0" />
                                <span className="text-[var(--text-secondary)]">{f}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                    {/* 특별·지구 지정 — devPlans.special_districts(그간 게이트 조건에만 쓰이고 미렌더였던 항목). */}
                    {specialDistricts.length > 0 && (
                      <div className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3">
                        <p className="mb-1 text-[10px] font-bold text-[var(--text-hint)]">특별·지구 지정</p>
                        <div className="space-y-1">
                          {specialDistricts.map((d, i) => (
                            <div key={i} className="flex items-center gap-2 text-[11px]">
                              <span className="h-1.5 w-1.5 rounded-full bg-purple-400 shrink-0" />
                              <span className="text-[var(--text-secondary)]">{d}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-xs text-[var(--text-hint)] italic">개발계획/규제 정보 없음</p>
                )}
                {result.ai_interpretation?.development_plan_interpretation && (
                  <AiInterpretation text={result.ai_interpretation.development_plan_interpretation} />
                )}
              </SectionCard>
            );
          })()}

          {/* 분석 시간 */}
          <p className="text-[10px] text-[var(--text-hint)] text-right">분석 시간: {result.analyzed_at}</p>
        </div>
      )}
    </div>
  );
}
