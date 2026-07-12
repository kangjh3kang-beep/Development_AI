"use client";

/**
 * D1 — 대안설계 원가비교(A/B).
 * 기준안(건축개요) + 변형(구조형식·층수·연면적)을 입력하면 변형별 총공사비·델타(±)·델타%·
 * 영향공종·rationale을 비교한다. "이 설계를 바꾸면 −N억" 직관 표현.
 * POST /api/v1/cost/{pid}/alternatives. 추정치 — 전문 적산사 검토 배지.
 */

import { useCallback, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { ChangeForecastCard } from "@/components/cost/ChangeForecastCard";
import { SavingScenariosCard } from "@/components/cost/SavingScenariosCard";
import type {
  AlternativesResponse,
  AlternativeVariantInput,
} from "@/components/cost/cmTypes";

const STRUCTURES = ["RC", "SRC", "SC", "PC"];
const fcls =
  "w-full rounded-lg border border-[var(--line-strong)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]";

function fmtKrw(won?: number | null): string {
  if (won == null || isNaN(won)) return "-";
  const abs = Math.abs(won);
  const sign = won < 0 ? "-" : "";
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)}억`;
  if (abs >= 1e4) return `${sign}${Math.round(abs / 1e4).toLocaleString()}만`;
  return `${sign}${Math.round(abs).toLocaleString()}원`;
}
function fmtDelta(won: number): string {
  return `${won >= 0 ? "+" : "−"}${fmtKrw(Math.abs(won))}`;
}

interface VariantForm {
  label: string;
  structure_type: string;
  floor_count_above: string;
  total_gfa_sqm: string;
}

const EMPTY_VARIANT = (label: string): VariantForm => ({
  label,
  structure_type: "",
  floor_count_above: "",
  total_gfa_sqm: "",
});

export function CostAlternativesPanel({ projectId: projectIdProp }: { projectId?: string }) {
  const ctxProjectId = useProjectContextStore((s) => s.projectId);
  const designData = useProjectContextStore((s) => s.designData);
  const projectId = projectIdProp || ctxProjectId || "default";

  const [bt, setBt] = useState("apartment");
  const [gfa, setGfa] = useState<string>(
    designData?.totalGfaSqm ? String(Math.round(designData.totalGfaSqm)) : "",
  );
  const [floorsAbove, setFloorsAbove] = useState<string>(
    designData?.floorCount ? String(designData.floorCount) : "15",
  );
  const [floorsBelow, setFloorsBelow] = useState<string>("2");
  const [structure, setStructure] = useState("RC");
  const [variants, setVariants] = useState<VariantForm[]>([
    { label: "대안 A · 구조 SRC", structure_type: "SRC", floor_count_above: "", total_gfa_sqm: "" },
    { label: "대안 B · 층수 +5", structure_type: "", floor_count_above: "20", total_gfa_sqm: "" },
  ]);
  const [result, setResult] = useState<AlternativesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const updateVariant = useCallback((i: number, patch: Partial<VariantForm>) => {
    setVariants((prev) => prev.map((v, idx) => (idx === i ? { ...v, ...patch } : v)));
  }, []);

  const run = useCallback(async () => {
    const gfaNum = Number(gfa);
    if (!gfaNum || gfaNum <= 0) {
      setErr("기준 연면적(GFA)을 입력하세요.");
      return;
    }
    const payloadVariants: AlternativeVariantInput[] = variants
      .filter((v) => v.label.trim())
      .map((v) => {
        const overrides: AlternativeVariantInput["overrides"] = {};
        if (v.structure_type) overrides.structure_type = v.structure_type;
        if (v.floor_count_above) overrides.floor_count_above = Number(v.floor_count_above);
        if (v.total_gfa_sqm) overrides.total_gfa_sqm = Number(v.total_gfa_sqm);
        return { label: v.label.trim(), overrides };
      });
    if (payloadVariants.length === 0) {
      setErr("비교할 변형(대안)을 1개 이상 입력하세요.");
      return;
    }
    setLoading(true);
    setErr("");
    try {
      const r = await apiClient.post<AlternativesResponse>(`/cost/${projectId}/alternatives`, {
        body: {
          base_params: {
            building_type: bt,
            total_gfa_sqm: gfaNum,
            floor_count_above: Number(floorsAbove) || 1,
            floor_count_below: Number(floorsBelow) || 0,
            structure_type: structure,
          },
          variants: payloadVariants,
        },
        useMock: false,
        timeoutMs: 45000,
      });
      setResult(r);
    } catch {
      setErr("대안설계 원가비교에 실패했습니다. 입력값을 확인하세요.");
    } finally {
      setLoading(false);
    }
  }, [bt, gfa, floorsAbove, floorsBelow, structure, variants, projectId]);

  const chartData = useMemo(() => {
    if (!result) return [];
    return [
      { name: "기준안", total: result.base.total, delta: 0, isBase: true },
      ...(result.variants ?? []).map((v) => ({
        name: v.label,
        total: v.total,
        delta: v.delta,
        isBase: false,
      })),
    ];
  }, [result]);

  // P4 T3: 절감 Top-N·설계변경 예측 카드가 공유하는 기준안 params(입력 폼 재사용 — 중복 폼 금지).
  const baseParams = useMemo(
    () => ({
      building_type: bt,
      total_gfa_sqm: Number(gfa) || 0,
      floor_count_above: Number(floorsAbove) || 1,
      floor_count_below: Number(floorsBelow) || 0,
      structure_type: structure,
    }),
    [bt, gfa, floorsAbove, floorsBelow, structure],
  );

  return (
    <section className="grid gap-5">
      <div>
        <h2 className="text-xl font-black text-[var(--text-primary)]">대안설계 원가비교 (A/B)</h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          기준안 대비 구조형식·층수·연면적을 바꾼 변형의 총공사비를 비교합니다.
          <b className="text-[var(--text-primary)]"> &ldquo;이 설계를 바꾸면 ±N억&rdquo;</b>을 한눈에 확인하세요.
        </p>
      </div>

      {/* 기준안 입력 */}
      <div className="grid gap-4 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5 sm:grid-cols-2 lg:grid-cols-5">
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold text-[var(--text-secondary)]">건축유형</span>
          <select value={bt} onChange={(e) => setBt(e.target.value)} className={fcls}>
            <option value="apartment">아파트/공동주택</option>
            <option value="officetel">오피스텔</option>
            <option value="office">업무시설</option>
            <option value="townhouse">연립·다세대</option>
            <option value="warehouse">지식산업센터/창고</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold text-[var(--text-secondary)]">기준 연면적(㎡)</span>
          <input value={gfa} onChange={(e) => setGfa(e.target.value)} inputMode="decimal" className={fcls} placeholder="예: 30000" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold text-[var(--text-secondary)]">구조</span>
          <select value={structure} onChange={(e) => setStructure(e.target.value)} className={fcls}>
            {STRUCTURES.map((s) => (
              <option key={s} value={s}>{s}조</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold text-[var(--text-secondary)]">지상 층수</span>
          <input value={floorsAbove} onChange={(e) => setFloorsAbove(e.target.value)} inputMode="numeric" className={fcls} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold text-[var(--text-secondary)]">지하 층수</span>
          <input value={floorsBelow} onChange={(e) => setFloorsBelow(e.target.value)} inputMode="numeric" className={fcls} />
        </label>
      </div>

      {/* 변형 입력 */}
      <div className="grid gap-3 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-black text-[var(--text-primary)]">변형(대안) 설계</h3>
          <div className="flex gap-2">
            <button
              onClick={() => setVariants((p) => [...p, EMPTY_VARIANT(`대안 ${String.fromCharCode(65 + p.length)}`)])}
              className="rounded-lg border border-[var(--line-strong)] px-3 py-1.5 text-[11px] font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)]"
            >
              + 변형 추가
            </button>
          </div>
        </div>
        {variants.map((v, i) => (
          <div key={i} className="grid items-end gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-3 sm:grid-cols-5">
            <label className="flex flex-col gap-1">
              <span className="text-[10px] font-semibold text-[var(--text-tertiary)]">이름</span>
              <input value={v.label} onChange={(e) => updateVariant(i, { label: e.target.value })} className={fcls} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[10px] font-semibold text-[var(--text-tertiary)]">구조형식</span>
              <select value={v.structure_type} onChange={(e) => updateVariant(i, { structure_type: e.target.value })} className={fcls}>
                <option value="">(기준 유지)</option>
                {STRUCTURES.map((s) => (
                  <option key={s} value={s}>{s}조</option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[10px] font-semibold text-[var(--text-tertiary)]">지상 층수</span>
              <input value={v.floor_count_above} onChange={(e) => updateVariant(i, { floor_count_above: e.target.value })} inputMode="numeric" className={fcls} placeholder="(유지)" />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[10px] font-semibold text-[var(--text-tertiary)]">연면적(㎡)</span>
              <input value={v.total_gfa_sqm} onChange={(e) => updateVariant(i, { total_gfa_sqm: e.target.value })} inputMode="decimal" className={fcls} placeholder="(유지)" />
            </label>
            <button
              onClick={() => setVariants((p) => p.filter((_, idx) => idx !== i))}
              disabled={variants.length <= 1}
              className="rounded-lg border border-[var(--line-strong)] px-3 py-2 text-[11px] font-bold text-[var(--status-error)] hover:border-[var(--status-error)]/60 disabled:opacity-40"
            >
              삭제
            </button>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={run}
          disabled={loading}
          className="rounded-xl bg-[var(--accent-strong)] px-8 py-3 text-sm font-black text-white shadow-[var(--shadow-glow)] hover:opacity-90 disabled:opacity-50"
        >
          {loading ? "원가비교 중…" : "대안설계 원가비교 실행"}
        </button>
        {err && <span className="text-xs font-semibold text-[var(--status-error)]">{err}</span>}
      </div>

      {result && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded bg-[var(--status-warning)]/15 px-2 py-0.5 text-[10px] font-bold text-[var(--status-warning)]">추정 (±12%)</span>
            <span className="rounded bg-[var(--surface-muted)] px-2 py-0.5 text-[10px] font-bold text-[var(--text-tertiary)]">전문 적산사 검토 권장</span>
          </div>

          {/* 비교 차트 */}
          <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5">
            <h3 className="mb-4 text-sm font-black text-[var(--text-primary)]">총공사비 비교</h3>
            <div style={{ width: "100%", height: 260 }}>
              <ResponsiveContainer>
                <BarChart data={chartData} margin={{ top: 24, right: 16, left: 8, bottom: 8 }}>
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: "var(--text-tertiary)" }} interval={0} />
                  <YAxis
                    tickFormatter={(v: number) => `${(v / 1e8).toFixed(0)}억`}
                    tick={{ fontSize: 11, fill: "var(--text-tertiary)" }}
                    width={48}
                  />
                  <Tooltip
                    cursor={{ fill: "var(--surface-strong)" }}
                    contentStyle={{
                      background: "var(--surface-strong)",
                      border: "1px solid var(--line-strong)",
                      borderRadius: 12,
                      fontSize: 12,
                    }}
                    formatter={(v) => [fmtKrw(Number(v)), "총공사비"]}
                  />
                  <Bar dataKey="total" radius={[6, 6, 0, 0]}>
                    {chartData.map((d, i) => (
                      <Cell
                        key={i}
                        fill={d.isBase ? "var(--accent-strong)" : d.delta < 0 ? "var(--status-success)" : "var(--status-error)"}
                      />
                    ))}
                    <LabelList
                      dataKey="total"
                      position="top"
                      formatter={(v) => fmtKrw(Number(v))}
                      style={{ fontSize: 10, fontWeight: 800, fill: "var(--text-secondary)" }}
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* 변형별 카드 */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div className="rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] p-4">
              <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">기준안</p>
              <p className="mt-1.5 text-xl font-[1000] text-[var(--accent-strong)]">{fmtKrw(result.base.total)}</p>
              <p className="mt-1 text-[11px] text-[var(--text-secondary)]">{bt} · {structure}조 · {floorsAbove}F · {gfa}㎡</p>
            </div>
            {(result.variants ?? []).map((v, i) => {
              const better = v.delta < 0;
              return (
                <div key={i} className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-4">
                  <p className="text-[11px] font-bold text-[var(--text-secondary)]">{v.label}</p>
                  <p className="mt-1.5 text-xl font-[1000] text-[var(--text-primary)]">{fmtKrw(v.total)}</p>
                  <p className={`mt-1 text-sm font-[1000] ${better ? "text-[var(--status-success)]" : "text-[var(--status-error)]"}`}>
                    {better ? "이 설계로 바꾸면 " : "이 설계로 바꾸면 "}
                    {fmtDelta(v.delta)} ({v.delta_pct >= 0 ? "+" : ""}{v.delta_pct}%)
                  </p>
                  <p className="mt-1.5 text-[11px] text-[var(--text-tertiary)]">변경: {v.rationale}</p>
                  {v.affected_work_types?.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {(v.affected_work_types ?? []).map((w, j) => (
                        <span key={j} className="rounded bg-[var(--surface-muted)] px-1.5 py-0.5 text-[9px] font-bold text-[var(--text-tertiary)]">
                          {w}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {result.note && (
            <p className="rounded-lg bg-[var(--surface-strong)] px-3 py-2 text-[11px] text-[var(--text-hint)]">{result.note}</p>
          )}
        </>
      )}

      {/* P4 T3: 절감 Top-N·설계변경 예측 — 위 기준안 입력을 그대로 재사용(무과금·결정론). */}
      <SavingScenariosCard projectId={projectId} baseParams={baseParams} />
      <ChangeForecastCard projectId={projectId} baseParams={baseParams} />
    </section>
  );
}
