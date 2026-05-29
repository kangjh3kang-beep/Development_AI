"use client";

import { useCallback, useMemo, useState } from "react";

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

interface PipelineResultDetailProps {
  result: PipelineRunResponse;
  onRerun?: (stageName: string, overrides: Record<string, unknown>) => void;
}

/* ── Section definitions ── */

interface SectionDef {
  id: string;
  label: string;
  sourceStage: string;
  fields: FieldDef[];
}

interface FieldDef {
  key: string;
  label: string;
  unit: string;
  editable: boolean;
  format?: (v: unknown) => string;
}

function fmtNum(v: unknown): string {
  if (typeof v !== "number") return String(v ?? "-");
  if (Math.abs(v) >= 1e8) return `${(v / 1e8).toFixed(1)}억`;
  if (Math.abs(v) >= 1e4) return `${(v / 1e4).toFixed(0)}만`;
  return v.toLocaleString("ko-KR");
}

function fmtPct(v: unknown): string {
  return typeof v === "number" ? `${v.toFixed(1)}` : "-";
}

function fmtArea(v: unknown): string {
  return typeof v === "number" ? v.toLocaleString("ko-KR") : "-";
}

const SECTIONS: SectionDef[] = [
  {
    id: "overview",
    label: "1. 사업개요",
    sourceStage: "site_analysis",
    fields: [
      { key: "land_area_sqm", label: "대지면적", unit: "m\u00B2", editable: true, format: fmtArea },
      { key: "zone_code", label: "용도지역", unit: "", editable: false },
      { key: "pnu", label: "PNU 코드", unit: "", editable: false },
      { key: "estimated_value", label: "추정 지가", unit: "", editable: true, format: fmtNum },
    ],
  },
  {
    id: "location",
    label: "2. 입지분석",
    sourceStage: "site_analysis",
    fields: [
      { key: "distance_subway_m", label: "지하철 거리", unit: "m", editable: false, format: fmtNum },
      { key: "distance_school_m", label: "학교 거리", unit: "m", editable: false, format: fmtNum },
      { key: "nearby_amenities", label: "주변 편의시설", unit: "개", editable: false },
      { key: "road_width_m", label: "접도 너비", unit: "m", editable: false },
    ],
  },
  {
    id: "architecture",
    label: "3. 건축계획",
    sourceStage: "design",
    fields: [
      { key: "building_type", label: "건축유형", unit: "", editable: false },
      { key: "floor_count", label: "층수", unit: "층", editable: true },
      { key: "total_gfa_sqm", label: "연면적", unit: "m\u00B2", editable: true, format: fmtArea },
      { key: "bcr", label: "건폐율", unit: "%", editable: false, format: fmtPct },
      { key: "far", label: "용적률", unit: "%", editable: false, format: fmtPct },
    ],
  },
  {
    id: "unit_mix",
    label: "4. 유닛믹스",
    sourceStage: "design",
    fields: [
      { key: "unit_count", label: "세대수", unit: "세대", editable: true },
      { key: "avg_unit_sqm", label: "평균 전용면적", unit: "m\u00B2", editable: true, format: fmtArea },
      { key: "parking_ratio", label: "주차대수 비율", unit: "%", editable: false, format: fmtPct },
    ],
  },
  {
    id: "cost",
    label: "5. 공사비",
    sourceStage: "construction_cost",
    fields: [
      { key: "total_cost_won", label: "총공사비", unit: "", editable: true, format: fmtNum },
      { key: "cost_per_sqm", label: "m\u00B2당 공사비", unit: "원/m\u00B2", editable: false, format: fmtNum },
      { key: "structure_cost", label: "구조공사비", unit: "", editable: false, format: fmtNum },
      { key: "mep_cost", label: "기계전기공사비", unit: "", editable: false, format: fmtNum },
    ],
  },
  {
    id: "feasibility",
    label: "6. 수지분석",
    sourceStage: "feasibility",
    fields: [
      { key: "total_revenue_won", label: "총수입", unit: "", editable: true, format: fmtNum },
      { key: "total_cost_won", label: "총사업비", unit: "", editable: true, format: fmtNum },
      { key: "profit_rate_pct", label: "수익률", unit: "%", editable: false, format: fmtPct },
      { key: "grade", label: "등급", unit: "", editable: false },
      { key: "net_profit_won", label: "순이익", unit: "", editable: false, format: fmtNum },
    ],
  },
  {
    id: "tax",
    label: "7. 세금",
    sourceStage: "tax",
    fields: [
      { key: "acquisition_tax", label: "취득세", unit: "", editable: false, format: fmtNum },
      { key: "transfer_tax", label: "양도세", unit: "", editable: false, format: fmtNum },
      { key: "comprehensive_tax", label: "종부세", unit: "", editable: false, format: fmtNum },
      { key: "total_tax", label: "세금 합계", unit: "", editable: false, format: fmtNum },
    ],
  },
  {
    id: "esg",
    label: "8. ESG/탄소",
    sourceStage: "esg_carbon",
    fields: [
      { key: "embodied_carbon_kg", label: "내재탄소", unit: "kg", editable: false, format: fmtNum },
      { key: "operational_carbon_kg", label: "운영탄소", unit: "kg", editable: false, format: fmtNum },
      { key: "total_carbon_per_sqm", label: "탄소밀도", unit: "kgCO\u2082/m\u00B2", editable: false, format: fmtPct },
      { key: "gresb_score", label: "GRESB 점수", unit: "점", editable: false },
    ],
  },
  {
    id: "compliance",
    label: "9. 법규검토",
    sourceStage: "report",
    fields: [
      { key: "compliance_pass", label: "통과 항목", unit: "개", editable: false },
      { key: "compliance_fail", label: "위반 항목", unit: "개", editable: false },
      { key: "compliance_total", label: "전체 항목", unit: "개", editable: false },
    ],
  },
  {
    id: "summary",
    label: "10. 종합평가",
    sourceStage: "report",
    fields: [
      { key: "overall_grade", label: "종합등급", unit: "", editable: false },
      { key: "risk_level", label: "리스크 수준", unit: "", editable: false },
      { key: "recommendation", label: "투자 의견", unit: "", editable: false },
    ],
  },
];

/* ── Executive Summary Card Specs ── */

interface ExecKPI {
  label: string;
  key: string;
  source: string;
  unit: string;
  format: (v: unknown) => string;
  color: string;
}

const EXEC_KPIS: ExecKPI[] = [
  { label: "수익률", key: "profit_rate_pct", source: "feasibility", unit: "%", format: fmtPct, color: "text-emerald-400" },
  { label: "총사업비", key: "total_cost_won", source: "feasibility", unit: "", format: fmtNum, color: "text-[var(--accent-strong)]" },
  { label: "순이익", key: "net_profit_won", source: "feasibility", unit: "", format: fmtNum, color: "text-emerald-400" },
  { label: "탄소밀도", key: "total_carbon_per_sqm", source: "esg_carbon", unit: "kgCO\u2082/m\u00B2", format: fmtPct, color: "text-yellow-400" },
  { label: "법규준수", key: "compliance_pass", source: "report", unit: "", format: (v) => String(v ?? "-"), color: "text-blue-400" },
];

/* ── Inline Edit Cell ── */

function EditableCell({
  value,
  fieldDef,
  onChange,
}: {
  value: unknown;
  fieldDef: FieldDef;
  onChange: (newVal: unknown) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  const display = fieldDef.format ? fieldDef.format(value) : String(value ?? "-");

  const startEdit = () => {
    setDraft(String(value ?? ""));
    setEditing(true);
  };

  const commitEdit = () => {
    setEditing(false);
    const parsed = Number(draft);
    if (!isNaN(parsed)) {
      onChange(parsed);
    } else {
      onChange(draft);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") commitEdit();
    if (e.key === "Escape") setEditing(false);
  };

  if (!fieldDef.editable) {
    return (
      <p className="text-sm font-bold text-[var(--text-primary)] truncate">
        {display}
      </p>
    );
  }

  if (editing) {
    return (
      <input
        autoFocus
        type="text"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commitEdit}
        onKeyDown={handleKeyDown}
        className="w-full h-7 rounded-md border border-[var(--accent-strong)] bg-[var(--surface)] px-2 text-sm font-bold text-[var(--text-primary)] outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/30"
      />
    );
  }

  return (
    <button
      type="button"
      onClick={startEdit}
      className="group flex items-center gap-1 text-left w-full"
    >
      <span className="text-sm font-bold text-[var(--text-primary)] truncate">
        {display}
      </span>
      <svg
        width="12"
        height="12"
        viewBox="0 0 24 24"
        fill="none"
        stroke="var(--text-hint)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
      >
        <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
      </svg>
    </button>
  );
}

/* ── Component ── */

export function PipelineResultDetail({ result, onRerun }: PipelineResultDetailProps) {
  const [activeTab, setActiveTab] = useState("overview");
  const [overrides, setOverrides] = useState<Record<string, Record<string, unknown>>>({});
  const [downloading, setDownloading] = useState(false);

  // Merge stage data + summary data for lookup
  const stageDataMap = useMemo(() => {
    const map: Record<string, Record<string, unknown>> = {};
    for (const stage of result.stages) {
      map[stage.stage] = { ...stage.data };
    }
    // Also merge summary
    if (result.summary) {
      for (const [key, val] of Object.entries(result.summary)) {
        map[key] = { ...map[key], ...val };
      }
    }
    return map;
  }, [result]);

  // Apply overrides on top
  const getFieldValue = useCallback(
    (sourceStage: string, fieldKey: string) => {
      const ov = overrides[sourceStage]?.[fieldKey];
      if (ov !== undefined) return ov;
      return stageDataMap[sourceStage]?.[fieldKey];
    },
    [stageDataMap, overrides],
  );

  const setFieldOverride = useCallback((sourceStage: string, fieldKey: string, value: unknown) => {
    setOverrides((prev) => ({
      ...prev,
      [sourceStage]: { ...prev[sourceStage], [fieldKey]: value },
    }));
  }, []);

  const hasOverrides = Object.keys(overrides).length > 0;

  // Collect all overrides into flat map for rerun
  const collectOverrides = useCallback(() => {
    const flat: Record<string, unknown> = {};
    for (const [stage, fields] of Object.entries(overrides)) {
      for (const [k, v] of Object.entries(fields)) {
        flat[`${stage}.${k}`] = v;
      }
    }
    return flat;
  }, [overrides]);

  const handleRerun = useCallback(() => {
    if (!onRerun) return;
    const activeSection = SECTIONS.find((s) => s.id === activeTab);
    onRerun(activeSection?.sourceStage ?? "site_analysis", collectOverrides());
  }, [onRerun, activeTab, collectOverrides]);

  const handleDownload = useCallback(async () => {
    setDownloading(true);
    try {
      const res = await fetch("/api/v2/pipeline/report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pipeline_id: result.pipeline_id,
          project_id: result.project_id,
        }),
      });
      if (!res.ok) throw new Error("보고서 생성 실패");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `PropAI_Report_${result.project_id}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert("보고서 다운로드에 실패했습니다.");
    } finally {
      setDownloading(false);
    }
  }, [result.pipeline_id, result.project_id]);

  const activeSection = SECTIONS.find((s) => s.id === activeTab)!;
  const address =
    (stageDataMap.site_analysis?.address as string) ??
    (stageDataMap.site_analysis?.juso as string) ??
    "";
  const profitRate = getFieldValue("feasibility", "profit_rate_pct");
  const grade = getFieldValue("feasibility", "grade");

  return (
    <section className="rounded-2xl sm:rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] shadow-[var(--shadow-xl)] overflow-hidden transition-all">
      {/* ── Header ── */}
      <div className="px-6 py-5 sm:px-8 sm:py-6 border-b border-[var(--line)] bg-gradient-to-r from-[var(--accent-strong)]/5 to-transparent">
        <div className="flex items-center gap-3 mb-1">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-[var(--accent-soft)] border border-[var(--accent-strong)]/20">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent-strong)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
              <path d="M14 2v6h6" />
              <path d="M16 13H8" />
              <path d="M16 17H8" />
              <path d="M10 9H8" />
            </svg>
          </div>
          <div>
            <h2 className="text-lg sm:text-xl font-[800] tracking-tight text-[var(--text-primary)]">
              프로젝트 통합 분석 보고서
            </h2>
            {address && (
              <p className="text-sm font-medium text-[var(--text-secondary)] tracking-tight">
                {address}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* ── Executive Summary ── */}
      <div className="px-6 py-4 sm:px-8 border-b border-[var(--line)]">
        <div className="rounded-xl border border-[var(--accent-strong)]/20 bg-gradient-to-br from-[var(--accent-soft)]/30 to-transparent p-4 sm:p-5">
          <div className="flex items-center gap-2 mb-4">
            <span className="h-2 w-2 rounded-full bg-[var(--accent-strong)] animate-pulse" />
            <h3 className="text-sm font-bold text-[var(--text-primary)] tracking-[0.1em]">
              Executive Summary
            </h3>
            {typeof profitRate === "number" && typeof grade === "string" && (
              <span className="ml-auto text-xs font-bold px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                수익률 {fmtPct(profitRate)}% ({String(grade)}등급)
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            {EXEC_KPIS.map((kpi) => {
              const val = getFieldValue(kpi.source, kpi.key);
              return (
                <div
                  key={kpi.key}
                  className="rounded-xl bg-[var(--surface)] border border-[var(--line-strong)] p-3 text-center shadow-sm hover:shadow-[var(--shadow-glow)] hover:-translate-y-0.5 transition-all duration-300"
                >
                  <p className="text-[10px] font-bold text-[var(--text-hint)] tracking-[0.12em] uppercase mb-1">
                    {kpi.label}
                  </p>
                  <p className={`text-lg sm:text-xl font-[900] tracking-tight leading-none ${kpi.color}`}>
                    {kpi.format(val)}
                  </p>
                  {kpi.unit && (
                    <p className="text-[10px] font-medium text-[var(--text-tertiary)] mt-0.5">{kpi.unit}</p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* ── Tab Navigation ── */}
      <div className="px-6 sm:px-8 border-b border-[var(--line)] overflow-x-auto">
        <div className="flex gap-1 py-2 min-w-max">
          {SECTIONS.map((sec) => (
            <button
              key={sec.id}
              type="button"
              onClick={() => setActiveTab(sec.id)}
              className={`px-3 py-2 rounded-lg text-xs font-bold tracking-tight whitespace-nowrap transition-all ${
                activeTab === sec.id
                  ? "bg-[var(--accent-strong)] text-white shadow-[var(--shadow-glow)]"
                  : "text-[var(--text-secondary)] hover:bg-[var(--surface-strong)] hover:text-[var(--text-primary)]"
              }`}
            >
              {sec.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Section Content ── */}
      <div className="px-6 py-5 sm:px-8 sm:py-6">
        <h3 className="text-sm font-bold text-[var(--text-primary)] tracking-[0.08em] mb-4">
          {activeSection.label}
        </h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {activeSection.fields.map((field) => {
            const val = getFieldValue(activeSection.sourceStage, field.key);
            const isOverridden = overrides[activeSection.sourceStage]?.[field.key] !== undefined;

            return (
              <div
                key={field.key}
                className={`rounded-xl bg-[var(--surface)] border px-4 py-3 transition-all ${
                  isOverridden
                    ? "border-[var(--accent-strong)]/50 ring-1 ring-[var(--accent-strong)]/20"
                    : "border-[var(--line-strong)]"
                }`}
              >
                <p className="text-[10px] font-bold text-[var(--text-hint)] tracking-[0.12em] uppercase mb-1 flex items-center gap-1">
                  {field.label}
                  {field.unit && (
                    <span className="text-[var(--text-hint)]/60">({field.unit})</span>
                  )}
                  {isOverridden && (
                    <span className="ml-auto text-[8px] px-1.5 py-0.5 rounded bg-[var(--accent-strong)]/10 text-[var(--accent-strong)] font-bold">
                      수정됨
                    </span>
                  )}
                </p>
                <EditableCell
                  value={val}
                  fieldDef={field}
                  onChange={(newVal) => setFieldOverride(activeSection.sourceStage, field.key, newVal)}
                />
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Action Bar ── */}
      <div className="px-6 py-4 sm:px-8 border-t border-[var(--line)] flex flex-wrap items-center gap-3">
        {/* Download */}
        <button
          type="button"
          onClick={handleDownload}
          disabled={downloading}
          className="h-10 px-5 rounded-xl border border-[var(--line-strong)] bg-[var(--surface)] text-sm font-bold text-[var(--text-primary)] hover:bg-[var(--surface-strong)] transition-all disabled:opacity-50 flex items-center gap-2"
        >
          {downloading ? (
            <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" x2="12" y1="15" y2="3" />
            </svg>
          )}
          보고서 다운로드
        </button>

        {/* Rerun */}
        {onRerun && (
          <button
            type="button"
            onClick={handleRerun}
            disabled={!hasOverrides}
            className="h-10 px-5 rounded-xl bg-gradient-to-br from-[var(--accent-strong)] to-[var(--accent)] text-white text-sm font-bold shadow-[var(--shadow-glow)] hover:scale-[1.03] active:scale-[0.97] transition-all disabled:opacity-40 disabled:hover:scale-100 flex items-center gap-2"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
              <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
              <path d="M16 16h5v5" />
            </svg>
            {hasOverrides ? "수정값으로 재분석" : "재분석"}
          </button>
        )}

        {hasOverrides && (
          <button
            type="button"
            onClick={() => setOverrides({})}
            className="h-10 px-4 rounded-xl text-xs font-bold text-[var(--text-secondary)] hover:text-red-400 transition-colors"
          >
            수정 초기화
          </button>
        )}
      </div>
    </section>
  );
}
