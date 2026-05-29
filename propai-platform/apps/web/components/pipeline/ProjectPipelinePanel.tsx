"use client";

import { useCallback, useEffect, useState } from "react";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { PipelineResultDetail } from "./PipelineResultDetail";
import { ProjectCompareView } from "./ProjectCompareView";

/* ── Types ── */

interface PipelineStageStatus {
  stage: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  duration_ms: number | null;
  data: Record<string, unknown>;
  error: string | null;
}

interface PipelineRunResponse {
  pipeline_id: string;
  project_id: string;
  status: string;
  stages: PipelineStageStatus[];
  summary: Record<string, Record<string, unknown>>;
}

/* ── History entry stored in localStorage ── */

interface HistoryEntry {
  id: string;
  address: string;
  completedAt: string;
  result: PipelineRunResponse;
}

const HISTORY_KEY = "propai_pipeline_history";
const MAX_HISTORY = 5;

function loadHistory(): HistoryEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    return raw ? (JSON.parse(raw) as HistoryEntry[]) : [];
  } catch {
    return [];
  }
}

function saveHistory(entries: HistoryEntry[]) {
  if (typeof window === "undefined") return;
  localStorage.setItem(HISTORY_KEY, JSON.stringify(entries.slice(0, MAX_HISTORY)));
}

/* ── Constants ── */

const STAGE_LABELS: Record<string, string> = {
  site_analysis: "부지분석",
  design: "건축설계",
  construction_cost: "공사비",
  feasibility: "수지분석",
  tax: "세금계산",
  esg_carbon: "ESG/탄소",
  report: "통합보고서",
};

const STAGE_NUMBERS: Record<string, string> = {
  site_analysis: "\u2460",
  design: "\u2461",
  construction_cost: "\u2462",
  feasibility: "\u2463",
  tax: "\u2464",
  esg_carbon: "\u2465",
  report: "\u2466",
};

const DEFAULT_STAGES: PipelineStageStatus[] = [
  "site_analysis",
  "design",
  "construction_cost",
  "feasibility",
  "tax",
  "esg_carbon",
  "report",
].map((s) => ({
  stage: s,
  status: "pending",
  duration_ms: null,
  data: {},
  error: null,
}));

/* ── Helpers ── */

function statusIcon(status: PipelineStageStatus["status"]) {
  switch (status) {
    case "completed":
      return (
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-400 text-xs font-bold">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
        </span>
      );
    case "running":
      return (
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[var(--accent-strong)]/20 text-[var(--accent-strong)]">
          <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
        </span>
      );
    case "failed":
      return (
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-red-500/20 text-red-400 text-xs font-bold">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
        </span>
      );
    case "skipped":
      return (
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-yellow-500/20 text-yellow-400 text-[10px] font-bold">
          -
        </span>
      );
    default:
      return (
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[var(--surface-strong)] text-[var(--text-tertiary)] text-[10px]">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="10" /><path d="M12 6v6l4 2" /></svg>
        </span>
      );
  }
}

function statusLabel(status: PipelineStageStatus["status"]) {
  switch (status) {
    case "completed":
      return "완료";
    case "running":
      return "진행 중...";
    case "failed":
      return "실패";
    case "skipped":
      return "건너뜀";
    default:
      return "대기";
  }
}

function formatDuration(ms: number | null) {
  if (ms == null) return "";
  return `(${(ms / 1000).toFixed(1)}s)`;
}

function formatNumber(value: unknown): string {
  if (typeof value === "number") {
    if (Math.abs(value) >= 1e8) {
      return `${(value / 1e8).toFixed(1)}억`;
    }
    if (Math.abs(value) >= 1e4) {
      return `${(value / 1e4).toFixed(0)}만`;
    }
    return value.toLocaleString("ko-KR");
  }
  return String(value ?? "-");
}

/* ── Summary card specs ── */

interface SummaryCard {
  label: string;
  key: string;
  unit: string;
  source: string;
  format?: (v: unknown) => string;
}

const SUMMARY_CARDS: SummaryCard[] = [
  { label: "토지면적", key: "land_area_sqm", unit: "m\u00B2", source: "site_analysis", format: (v) => (typeof v === "number" ? `${v.toLocaleString("ko-KR")}` : "-") },
  { label: "총공사비", key: "total_cost_won", unit: "", source: "construction_cost", format: (v) => formatNumber(v) },
  { label: "수익률", key: "profit_rate_pct", unit: "%", source: "feasibility", format: (v) => (typeof v === "number" ? v.toFixed(1) : "-") },
  { label: "탄소배출", key: "total_carbon_per_sqm", unit: "kgCO\u2082/m\u00B2", source: "esg_carbon", format: (v) => (typeof v === "number" ? v.toFixed(1) : "-") },
];

/* ── View Mode ── */

type ViewMode = "pipeline" | "detail" | "compare";

/* ── Component ── */

export function ProjectPipelinePanel() {
  const [address, setAddress] = useState("");
  const [stages, setStages] = useState<PipelineStageStatus[]>(DEFAULT_STAGES);
  const [summary, setSummary] = useState<Record<string, Record<string, unknown>>>({});
  const [isRunning, setIsRunning] = useState(false);
  const [expandedStage, setExpandedStage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Phase 3: view mode, history, compare
  const [viewMode, setViewMode] = useState<ViewMode>("pipeline");
  const [lastResult, setLastResult] = useState<PipelineRunResponse | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [compareSelection, setCompareSelection] = useState<Set<string>>(new Set());

  // Load history on mount
  useEffect(() => {
    setHistory(loadHistory());
  }, []);

  const projectId = useProjectContextStore((s) => s.projectId);
  const updateSiteAnalysis = useProjectContextStore((s) => s.updateSiteAnalysis);
  const updateDesignData = useProjectContextStore((s) => s.updateDesignData);
  const updateFeasibilityData = useProjectContextStore((s) => s.updateFeasibilityData);
  const updateEsgData = useProjectContextStore((s) => s.updateEsgData);
  const addAnalysisResult = useProjectContextStore((s) => s.addAnalysisResult);
  const markStageComplete = useProjectContextStore((s) => s.markStageComplete);

  const saveToStore = useCallback(
    (result: PipelineRunResponse) => {
      // site_analysis
      const site = result.summary?.site_analysis;
      if (site) {
        updateSiteAnalysis({
          estimatedValue: (site.estimated_value as number) ?? null,
          landAreaSqm: (site.land_area_sqm as number) ?? null,
          zoneCode: (site.zone_code as string) ?? null,
          address: address || null,
          pnu: (site.pnu as string) ?? null,
        });
        markStageComplete("site-analysis");
      }

      // design
      const design = result.summary?.design;
      if (design) {
        updateDesignData({
          totalGfaSqm: (design.total_gfa_sqm as number) ?? null,
          floorCount: (design.floor_count as number) ?? null,
          buildingType: (design.building_type as string) ?? null,
          bcr: (design.bcr as number) ?? null,
          far: (design.far as number) ?? null,
        });
        markStageComplete("design");
      }

      // feasibility
      const feas = result.summary?.feasibility;
      if (feas) {
        updateFeasibilityData({
          totalCostWon: (feas.total_cost_won as number) ?? null,
          totalRevenueWon: (feas.total_revenue_won as number) ?? null,
          profitRatePct: (feas.profit_rate_pct as number) ?? null,
          grade: (feas.grade as string) ?? null,
        });
        markStageComplete("feasibility");
      }

      // esg
      const esg = result.summary?.esg_carbon;
      if (esg) {
        updateEsgData({
          embodiedCarbonKg: (esg.embodied_carbon_kg as number) ?? null,
          operationalCarbonKg: (esg.operational_carbon_kg as number) ?? null,
          totalCarbonPerSqm: (esg.total_carbon_per_sqm as number) ?? null,
        });
        markStageComplete("esg");
      }

      // analysis results for each completed stage
      for (const stage of result.stages) {
        if (stage.status === "completed") {
          addAnalysisResult({
            module: stage.stage,
            completedAt: new Date().toISOString(),
            summary: stage.data,
          });
        }
      }
    },
    [address, updateSiteAnalysis, updateDesignData, updateFeasibilityData, updateEsgData, addAnalysisResult, markStageComplete],
  );

  const addToHistory = useCallback(
    (result: PipelineRunResponse, addr: string) => {
      const entry: HistoryEntry = {
        id: result.pipeline_id,
        address: addr,
        completedAt: new Date().toISOString(),
        result,
      };
      const updated = [entry, ...history.filter((h) => h.id !== entry.id)].slice(0, MAX_HISTORY);
      setHistory(updated);
      saveHistory(updated);
    },
    [history],
  );

  const runPipeline = useCallback(async () => {
    if (!address.trim()) return;

    setIsRunning(true);
    setError(null);
    setStages(DEFAULT_STAGES.map((s) => ({ ...s })));
    setSummary({});
    setExpandedStage(null);
    setViewMode("pipeline");
    setLastResult(null);

    const updatedStages = DEFAULT_STAGES.map((s) => ({ ...s }));

    try {
      updatedStages[0]!.status = "running";
      setStages([...updatedStages]);

      const response = await fetch("/api/v2/pipeline/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address: address.trim(), project_id: projectId }),
      });

      if (!response.ok) {
        const errBody = await response.text();
        throw new Error(`파이프라인 실행 실패 (${response.status}): ${errBody}`);
      }

      const result: PipelineRunResponse = await response.json();

      setStages(result.stages);
      setSummary(result.summary ?? {});
      setLastResult(result);

      // Save to Zustand store
      saveToStore(result);

      // Save to history
      addToHistory(result, address.trim());
    } catch (err) {
      const msg = err instanceof Error ? err.message : "알 수 없는 오류가 발생했습니다.";
      setError(msg);

      const failedStages = updatedStages.map((s) =>
        s.status === "completed" ? s : { ...s, status: "failed" as const, error: msg },
      );
      setStages(failedStages);
    } finally {
      setIsRunning(false);
    }
  }, [address, projectId, saveToStore, addToHistory]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    runPipeline();
  };

  const toggleStage = (stageKey: string) => {
    setExpandedStage((prev) => (prev === stageKey ? null : stageKey));
  };

  const handleRerun = useCallback(
    async (stageName: string, overrides: Record<string, unknown>) => {
      if (!lastResult) return;
      setIsRunning(true);
      setError(null);
      setViewMode("pipeline");

      try {
        const response = await fetch("/api/v2/pipeline/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            address: address.trim(),
            project_id: projectId,
            options: { from_stage: stageName, overrides },
          }),
        });

        if (!response.ok) {
          const errBody = await response.text();
          throw new Error(`재분석 실패 (${response.status}): ${errBody}`);
        }

        const result: PipelineRunResponse = await response.json();
        setStages(result.stages);
        setSummary(result.summary ?? {});
        setLastResult(result);
        saveToStore(result);
        addToHistory(result, address.trim());
      } catch (err) {
        const msg = err instanceof Error ? err.message : "알 수 없는 오류가 발생했습니다.";
        setError(msg);
      } finally {
        setIsRunning(false);
      }
    },
    [lastResult, address, projectId, saveToStore, addToHistory],
  );

  const toggleCompareSelect = (id: string) => {
    setCompareSelection((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else if (next.size < 3) {
        next.add(id);
      }
      return next;
    });
  };

  const startCompare = () => {
    if (compareSelection.size >= 2) {
      setViewMode("compare");
    }
  };

  const compareResults = history
    .filter((h) => compareSelection.has(h.id))
    .map((h) => h.result);

  const pipelineCompleted = stages.every((s) => s.status === "completed" || s.status === "skipped");
  const hasSummary = Object.keys(summary).length > 0;

  /* ── Detail View ── */
  if (viewMode === "detail" && lastResult) {
    return (
      <div className="space-y-4">
        <button
          type="button"
          onClick={() => setViewMode("pipeline")}
          className="flex items-center gap-2 text-sm font-bold text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="m15 18-6-6 6-6" />
          </svg>
          파이프라인으로 돌아가기
        </button>
        <PipelineResultDetail result={lastResult} onRerun={handleRerun} />
      </div>
    );
  }

  /* ── Compare View ── */
  if (viewMode === "compare" && compareResults.length >= 2) {
    return (
      <div className="space-y-4">
        <button
          type="button"
          onClick={() => {
            setViewMode("pipeline");
            setCompareSelection(new Set());
          }}
          className="flex items-center gap-2 text-sm font-bold text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="m15 18-6-6 6-6" />
          </svg>
          파이프라인으로 돌아가기
        </button>
        <ProjectCompareView results={compareResults} />
      </div>
    );
  }

  /* ── Pipeline View (default) ── */
  return (
    <section className="rounded-2xl sm:rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] shadow-[var(--shadow-xl)] overflow-hidden transition-all">
      {/* ── Header ── */}
      <div className="px-6 py-5 sm:px-8 sm:py-6 border-b border-[var(--line)] bg-gradient-to-r from-[var(--accent-strong)]/5 to-transparent">
        <div className="flex items-center gap-3 mb-1">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-[var(--accent-soft)] border border-[var(--accent-strong)]/20">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent-strong)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 3v18h18" /><path d="m19 9-5 5-4-4-3 3" /></svg>
          </div>
          <h2 className="text-lg sm:text-xl font-[800] tracking-tight text-[var(--text-primary)]">
            프로젝트 자동 분석 파이프라인
          </h2>
        </div>
        <p className="text-sm font-medium text-[var(--text-secondary)] tracking-tight ml-11">
          주소를 입력하면 7단계 분석을 자동 수행합니다
        </p>
      </div>

      {/* ── Address Input ── */}
      <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-3 px-6 py-4 sm:px-8 border-b border-[var(--line)]">
        <input
          type="text"
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          placeholder="분석할 주소를 입력하세요 (예: 서울특별시 강남구 테헤란로 123)"
          disabled={isRunning}
          className="flex-1 h-12 rounded-xl border border-[var(--line-strong)] bg-[var(--surface)] px-4 text-sm font-medium text-[var(--text-primary)] placeholder:text-[var(--text-hint)] focus:outline-none focus:border-[var(--accent-strong)] focus:ring-2 focus:ring-[var(--accent-strong)]/20 transition-all disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={isRunning || !address.trim()}
          className="h-12 px-6 sm:px-8 rounded-xl bg-gradient-to-br from-[var(--accent-strong)] to-[var(--accent)] text-white text-sm font-bold tracking-wide shadow-[var(--shadow-glow)] transition-all hover:scale-[1.03] active:scale-[0.97] disabled:opacity-50 disabled:hover:scale-100 disabled:cursor-not-allowed whitespace-nowrap flex items-center justify-center gap-2"
        >
          {isRunning ? (
            <>
              <svg className="animate-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
              분석 중...
            </>
          ) : (
            <>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polygon points="6 3 20 12 6 21 6 3" /></svg>
              분석 시작
            </>
          )}
        </button>
      </form>

      {/* ── Error Banner ── */}
      {error && (
        <div className="mx-6 sm:mx-8 mt-4 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm font-medium text-red-400">
          {error}
        </div>
      )}

      {/* ── Stage List ── */}
      <div className="px-6 py-4 sm:px-8 space-y-1">
        {stages.map((stage) => {
          const isExpanded = expandedStage === stage.stage;
          const hasData = Object.keys(stage.data).length > 0;

          return (
            <div key={stage.stage} className="rounded-xl border border-[var(--line)] overflow-hidden transition-all">
              {/* Stage Row */}
              <button
                type="button"
                onClick={() => hasData && toggleStage(stage.stage)}
                className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-colors ${
                  hasData ? "cursor-pointer hover:bg-[var(--surface-strong)]" : "cursor-default"
                } ${stage.status === "running" ? "bg-[var(--accent-strong)]/5" : "bg-transparent"}`}
              >
                {/* Number */}
                <span className="text-sm font-bold text-[var(--text-tertiary)] w-5 shrink-0">
                  {STAGE_NUMBERS[stage.stage] ?? ""}
                </span>

                {/* Icon */}
                {statusIcon(stage.status)}

                {/* Label */}
                <span className={`flex-1 text-sm font-bold tracking-tight ${
                  stage.status === "completed" ? "text-[var(--text-primary)]" :
                  stage.status === "running" ? "text-[var(--accent-strong)]" :
                  stage.status === "failed" ? "text-red-400" :
                  "text-[var(--text-tertiary)]"
                }`}>
                  {STAGE_LABELS[stage.stage] ?? stage.stage}
                </span>

                {/* Status */}
                <span className={`text-xs font-medium ${
                  stage.status === "completed" ? "text-emerald-400" :
                  stage.status === "running" ? "text-[var(--accent-strong)]" :
                  stage.status === "failed" ? "text-red-400" :
                  "text-[var(--text-hint)]"
                }`}>
                  {statusLabel(stage.status)} {formatDuration(stage.duration_ms)}
                </span>

                {/* Expand arrow */}
                {hasData && (
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="var(--text-tertiary)"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className={`shrink-0 transition-transform duration-200 ${isExpanded ? "rotate-180" : ""}`}
                  >
                    <path d="m6 9 6 6 6-6" />
                  </svg>
                )}
              </button>

              {/* Expanded Detail */}
              {isExpanded && hasData && (
                <div className="px-4 pb-4 pt-1 border-t border-[var(--line)] bg-[var(--surface-strong)]/50">
                  {stage.error && (
                    <p className="text-xs text-red-400 mb-2">{stage.error}</p>
                  )}
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    {Object.entries(stage.data).map(([key, value]) => (
                      <div key={key} className="rounded-lg bg-[var(--surface)] border border-[var(--line)] px-3 py-2">
                        <p className="text-[10px] font-bold text-[var(--text-hint)] tracking-wider uppercase mb-0.5">
                          {key.replace(/_/g, " ")}
                        </p>
                        <p className="text-xs font-bold text-[var(--text-primary)] truncate">
                          {typeof value === "object" ? JSON.stringify(value) : formatNumber(value)}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* ── Summary Cards + Detail Button ── */}
      {pipelineCompleted && hasSummary && (
        <div className="px-6 pb-6 sm:px-8 sm:pb-8">
          <div className="rounded-xl border border-[var(--accent-strong)]/20 bg-gradient-to-br from-[var(--accent-soft)]/30 to-transparent p-4 sm:p-6">
            <h3 className="text-sm font-bold text-[var(--text-primary)] tracking-[0.1em] mb-4 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-[var(--accent-strong)] animate-pulse" />
              핵심 지표 요약
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {SUMMARY_CARDS.map((card) => {
                const stageData = summary[card.source];
                const rawValue = stageData?.[card.key];
                const displayValue = card.format ? card.format(rawValue) : formatNumber(rawValue);

                return (
                  <div
                    key={card.key}
                    className="rounded-xl bg-[var(--surface)] border border-[var(--line-strong)] p-4 text-center shadow-sm hover:shadow-[var(--shadow-glow)] hover:border-[var(--accent)] hover:-translate-y-0.5 transition-all duration-300"
                  >
                    <p className="text-[10px] font-bold text-[var(--text-hint)] tracking-[0.15em] uppercase mb-2">
                      {card.label}
                    </p>
                    <p className="text-xl sm:text-2xl font-[900] text-[var(--text-primary)] tracking-tight leading-none">
                      {displayValue}
                    </p>
                    {card.unit && (
                      <p className="text-[10px] font-medium text-[var(--text-tertiary)] mt-1">{card.unit}</p>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Detail Report Button */}
            {lastResult && (
              <div className="mt-4 flex justify-center">
                <button
                  type="button"
                  onClick={() => setViewMode("detail")}
                  className="h-10 px-6 rounded-xl bg-gradient-to-br from-[var(--accent-strong)] to-[var(--accent)] text-white text-sm font-bold shadow-[var(--shadow-glow)] hover:scale-[1.03] active:scale-[0.97] transition-all flex items-center gap-2"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
                    <path d="M14 2v6h6" />
                    <path d="M16 13H8" />
                    <path d="M16 17H8" />
                    <path d="M10 9H8" />
                  </svg>
                  상세 보고서 보기
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Analysis History ── */}
      {history.length > 0 && (
        <div className="px-6 pb-6 sm:px-8 sm:pb-8">
          <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)]/30 p-4 sm:p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold text-[var(--text-primary)] tracking-[0.08em] flex items-center gap-2">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <polyline points="12 6 12 12 16 14" />
                </svg>
                분석 이력
              </h3>
              {compareSelection.size >= 2 && (
                <button
                  type="button"
                  onClick={startCompare}
                  className="h-8 px-4 rounded-lg bg-gradient-to-br from-[var(--accent-strong)] to-[var(--accent)] text-white text-xs font-bold shadow-[var(--shadow-glow)] hover:scale-[1.03] active:scale-[0.97] transition-all flex items-center gap-1.5"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M16 3h5v5" />
                    <path d="M8 3H3v5" />
                    <path d="M12 22v-8.3a4 4 0 0 0-1.172-2.872L3 3" />
                    <path d="m15 9 6-6" />
                  </svg>
                  비교 분석 ({compareSelection.size}개)
                </button>
              )}
            </div>
            <div className="space-y-1.5">
              {history.map((entry) => {
                const isSelected = compareSelection.has(entry.id);
                const profitRate = entry.result.summary?.feasibility?.profit_rate_pct;
                const date = new Date(entry.completedAt);
                const dateStr = `${date.getMonth() + 1}/${date.getDate()} ${date.getHours().toString().padStart(2, "0")}:${date.getMinutes().toString().padStart(2, "0")}`;

                return (
                  <div
                    key={entry.id}
                    className={`flex items-center gap-3 rounded-xl border px-4 py-2.5 transition-all ${
                      isSelected
                        ? "border-[var(--accent-strong)]/50 bg-[var(--accent-strong)]/5 ring-1 ring-[var(--accent-strong)]/20"
                        : "border-[var(--line)] bg-[var(--surface)] hover:bg-[var(--surface-strong)]"
                    }`}
                  >
                    {/* Compare checkbox */}
                    <button
                      type="button"
                      onClick={() => toggleCompareSelect(entry.id)}
                      className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border-2 transition-all ${
                        isSelected
                          ? "border-[var(--accent-strong)] bg-[var(--accent-strong)] text-white"
                          : "border-[var(--line-strong)] bg-transparent hover:border-[var(--accent-strong)]/50"
                      }`}
                      title="비교 대상 선택"
                    >
                      {isSelected && (
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M20 6 9 17l-5-5" />
                        </svg>
                      )}
                    </button>

                    {/* Address */}
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-bold text-[var(--text-primary)] truncate">
                        {entry.address}
                      </p>
                      <p className="text-[10px] text-[var(--text-hint)]">{dateStr}</p>
                    </div>

                    {/* Profit rate badge */}
                    {typeof profitRate === "number" && (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 shrink-0">
                        {profitRate.toFixed(1)}%
                      </span>
                    )}

                    {/* View detail button */}
                    <button
                      type="button"
                      onClick={() => {
                        setLastResult(entry.result);
                        setAddress(entry.address);
                        setStages(entry.result.stages);
                        setSummary(entry.result.summary ?? {});
                        setViewMode("detail");
                      }}
                      className="text-[10px] font-bold text-[var(--text-secondary)] hover:text-[var(--accent-strong)] transition-colors shrink-0"
                    >
                      상세
                    </button>
                  </div>
                );
              })}
            </div>
            {compareSelection.size > 0 && compareSelection.size < 2 && (
              <p className="text-[10px] text-[var(--text-hint)] mt-2 text-center">
                비교하려면 2개 이상 선택하세요 (최대 3개)
              </p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
