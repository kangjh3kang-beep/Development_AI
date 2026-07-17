"use client";

import { useMemo } from "react";

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

interface ProjectCompareViewProps {
  results: PipelineRunResponse[];
}

/* ── Compare Field Definitions ── */

interface CompareField {
  key: string;
  label: string;
  source: string;
  unit: string;
  format: (v: unknown) => string;
  diffFormat?: (a: unknown, b: unknown) => { text: string; positive: boolean | null };
}

function fmtNum(v: unknown): string {
  if (typeof v !== "number") return String(v ?? "-");
  if (Math.abs(v) >= 1e8) return `${(v / 1e8).toFixed(1)}억`;
  if (Math.abs(v) >= 1e4) return `${(v / 1e4).toFixed(0)}만`;
  return v.toLocaleString("ko-KR");
}

function fmtPct(v: unknown): string {
  return typeof v === "number" ? `${v.toFixed(1)}%` : "-";
}

function fmtArea(v: unknown): string {
  return typeof v === "number" ? `${v.toLocaleString("ko-KR")} m\u00B2` : "-";
}

function numDiff(
  a: unknown,
  b: unknown,
  unit: string,
  higherIsBetter: boolean,
): { text: string; positive: boolean | null } {
  if (typeof a !== "number" || typeof b !== "number") return { text: "-", positive: null };
  const diff = b - a;
  const sign = diff > 0 ? "+" : "";
  let text: string;
  if (Math.abs(diff) >= 1e8) {
    text = `${sign}${(diff / 1e8).toFixed(1)}억`;
  } else if (Math.abs(diff) >= 1e4) {
    text = `${sign}${(diff / 1e4).toFixed(0)}만`;
  } else {
    text = `${sign}${diff.toLocaleString("ko-KR")}`;
  }
  if (unit) text += ` ${unit}`;
  const positive = diff === 0 ? null : higherIsBetter ? diff > 0 : diff < 0;
  return { text, positive };
}

function pctDiff(a: unknown, b: unknown, higherIsBetter: boolean) {
  if (typeof a !== "number" || typeof b !== "number") return { text: "-", positive: null };
  const diff = b - a;
  const sign = diff > 0 ? "+" : "";
  const text = `${sign}${diff.toFixed(1)}%p`;
  const positive = diff === 0 ? null : higherIsBetter ? diff > 0 : diff < 0;
  return { text, positive };
}

const COMPARE_FIELDS: CompareField[] = [
  {
    key: "land_area_sqm",
    label: "대지면적",
    source: "site_analysis",
    unit: "m\u00B2",
    format: fmtArea,
    diffFormat: (a, b) => numDiff(a, b, "m\u00B2", true),
  },
  {
    key: "zone_code",
    label: "용도지역",
    source: "site_analysis",
    unit: "",
    format: (v) => String(v ?? "-"),
  },
  {
    key: "far",
    label: "용적률",
    source: "design",
    unit: "%",
    format: fmtPct,
    diffFormat: (a, b) => pctDiff(a, b, true),
  },
  {
    key: "bcr",
    label: "건폐율",
    source: "design",
    unit: "%",
    format: fmtPct,
    diffFormat: (a, b) => pctDiff(a, b, false),
  },
  {
    key: "floor_count",
    label: "층수",
    source: "design",
    unit: "층",
    format: (v) => (typeof v === "number" ? `${v}층` : "-"),
    diffFormat: (a, b) => numDiff(a, b, "층", true),
  },
  {
    key: "total_gfa_sqm",
    label: "연면적",
    source: "design",
    unit: "m\u00B2",
    format: fmtArea,
    diffFormat: (a, b) => numDiff(a, b, "m\u00B2", true),
  },
  {
    key: "total_cost_won",
    label: "총공사비",
    source: "construction_cost",
    unit: "",
    format: fmtNum,
    diffFormat: (a, b) => numDiff(a, b, "", false),
  },
  {
    key: "profit_rate_pct",
    label: "수익률",
    source: "feasibility",
    unit: "%",
    format: fmtPct,
    diffFormat: (a, b) => pctDiff(a, b, true),
  },
  {
    key: "net_profit_won",
    label: "순이익",
    source: "feasibility",
    unit: "",
    format: fmtNum,
    diffFormat: (a, b) => numDiff(a, b, "", true),
  },
  {
    key: "grade",
    label: "수지등급",
    source: "feasibility",
    unit: "",
    format: (v) => String(v ?? "-"),
  },
  {
    key: "total_carbon_per_sqm",
    label: "탄소배출",
    source: "esg_carbon",
    unit: "kgCO\u2082/m\u00B2",
    format: (v) => (typeof v === "number" ? `${v.toFixed(1)} kg/m\u00B2` : "-"),
    diffFormat: (a, b) => {
      if (typeof a !== "number" || typeof b !== "number") return { text: "-", positive: null };
      const diff = b - a;
      const pct = a !== 0 ? ((diff / a) * 100).toFixed(0) : "0";
      const sign = diff > 0 ? "+" : "";
      return {
        text: `${sign}${diff.toFixed(1)} (${sign}${pct}%)`,
        positive: diff <= 0,
      };
    },
  },
  {
    key: "compliance_pass",
    label: "법규준수",
    source: "report",
    unit: "",
    format: (v) => String(v ?? "-"),
  },
];

/* ── Component ── */

export function ProjectCompareView({ results }: ProjectCompareViewProps) {
  // Build data maps for each result
  const dataMaps = useMemo(() => {
    return results.map((r) => {
      const map: Record<string, Record<string, unknown>> = {};
      for (const stage of r.stages) {
        map[stage.stage] = { ...stage.data };
      }
      if (r.summary) {
        for (const [key, val] of Object.entries(r.summary)) {
          map[key] = { ...map[key], ...val };
        }
      }
      return map;
    });
  }, [results]);

  const getValue = (resultIdx: number, source: string, key: string) => {
    return dataMaps[resultIdx]?.[source]?.[key];
  };

  const projectLabels = results.map((r, i) => {
    const addr =
      (dataMaps[i]?.site_analysis?.address as string) ??
      (dataMaps[i]?.site_analysis?.juso as string) ??
      "";
    return addr || `프로젝트 ${String.fromCharCode(65 + i)}`;
  });

  if (results.length < 2) {
    return (
      <section className="rounded-2xl sm:rounded-[var(--radius-lg)] border border-[var(--line-strong)] bg-[var(--surface-soft)] shadow-[var(--shadow-xl)] p-8 text-center">
        <p className="text-sm font-medium text-[var(--text-secondary)]">
          비교하려면 2개 이상의 분석 결과가 필요합니다.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-2xl sm:rounded-[var(--radius-lg)] border border-[var(--line-strong)] bg-[var(--surface-soft)] shadow-[var(--shadow-xl)] overflow-hidden transition-all">
      {/* ── Header ── */}
      <div className="px-6 py-5 sm:px-8 sm:py-6 border-b border-[var(--line)] bg-gradient-to-r from-[var(--accent-strong)]/5 to-transparent">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-[var(--accent-soft)] border border-[var(--accent-strong)]/20">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent-strong)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M16 3h5v5" />
              <path d="M8 3H3v5" />
              <path d="M12 22v-8.3a4 4 0 0 0-1.172-2.872L3 3" />
              <path d="m15 9 6-6" />
            </svg>
          </div>
          <div>
            <h2 className="text-lg sm:text-xl font-[800] tracking-tight text-[var(--text-primary)]">
              프로젝트 비교 분석
            </h2>
            <p className="text-sm font-medium text-[var(--text-secondary)] tracking-tight">
              {results.length}개 프로젝트 비교
            </p>
          </div>
        </div>
      </div>

      {/* ── Compare Table ── */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--line)]">
              <th className="px-6 py-3 text-left text-[10px] font-bold text-[var(--text-hint)] tracking-[0.15em] uppercase w-[180px]">
                항목
              </th>
              {projectLabels.map((label, i) => (
                <th
                  key={i}
                  className="px-4 py-3 text-left text-[10px] font-bold text-[var(--text-hint)] tracking-[0.12em] uppercase"
                >
                  <div className="flex items-center gap-2">
                    <span className="flex h-5 w-5 items-center justify-center rounded-md bg-[var(--accent-strong)]/10 text-[var(--accent-strong)] text-[10px] font-[900]">
                      {String.fromCharCode(65 + i)}
                    </span>
                    <span className="truncate max-w-[120px]">{label}</span>
                  </div>
                </th>
              ))}
              {results.length === 2 && (
                <th className="px-4 py-3 text-left text-[10px] font-bold text-[var(--text-hint)] tracking-[0.15em] uppercase">
                  차이 (B-A)
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {COMPARE_FIELDS.map((field, rowIdx) => {
              const values = results.map((_, i) => getValue(i, field.source, field.key));
              const diff =
                results.length === 2 && field.diffFormat
                  ? field.diffFormat(values[0], values[1])
                  : null;

              return (
                <tr
                  key={field.key}
                  className={`border-b border-[var(--line)] transition-colors hover:bg-[var(--surface-strong)]/50 ${
                    rowIdx % 2 === 0 ? "" : "bg-[var(--surface-strong)]/20"
                  }`}
                >
                  <td className="px-6 py-3 font-bold text-[var(--text-secondary)] whitespace-nowrap">
                    {field.label}
                    {field.unit && (
                      <span className="text-[var(--text-hint)] text-[10px] ml-1">({field.unit})</span>
                    )}
                  </td>
                  {values.map((val, i) => (
                    <td key={i} className="px-4 py-3 font-bold text-[var(--text-primary)]">
                      {field.format(val)}
                    </td>
                  ))}
                  {diff && (
                    <td className="px-4 py-3 font-bold whitespace-nowrap">
                      <span
                        className={
                          diff.positive === true
                            ? "text-emerald-400"
                            : diff.positive === false
                              ? "text-red-400"
                              : "text-[var(--text-tertiary)]"
                        }
                      >
                        {diff.text}
                        {diff.positive === true && " \u2705"}
                        {diff.positive === false && " \u26A0\uFE0F"}
                      </span>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* ── Summary Footer ── */}
      <div className="px-6 py-4 sm:px-8 border-t border-[var(--line)] bg-[var(--surface-strong)]/30">
        <div className="flex flex-wrap gap-4">
          {results.map((r, i) => {
            const profitRate = getValue(i, "feasibility", "profit_rate_pct");
            const grade = getValue(i, "feasibility", "grade");
            return (
              <div
                key={r.pipeline_id}
                className="flex items-center gap-2 rounded-xl border border-[var(--line-strong)] bg-[var(--surface)] px-4 py-2"
              >
                <span className="flex h-5 w-5 items-center justify-center rounded-md bg-[var(--accent-strong)]/10 text-[var(--accent-strong)] text-[10px] font-[900]">
                  {String.fromCharCode(65 + i)}
                </span>
                <span className="text-xs font-bold text-[var(--text-primary)]">
                  수익률 {typeof profitRate === "number" ? `${profitRate.toFixed(1)}%` : "-"}
                </span>
                {typeof grade === "string" && (
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    {grade}등급
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
