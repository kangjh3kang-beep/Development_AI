"use client";

/**
 * P4 T1 — 절감 시나리오 Top-N 카드.
 * CostAlternativesPanel의 기준안 입력(base_params)을 그대로 받아, alternatives(D1) 엔진을
 * 재사용해 자동 생성한 절감 후보(구조/층수/GFA)를 일괄 재산정하고 절감액 상위 N개를 보여준다.
 * POST /api/v1/cost/{pid}/saving-scenarios. 무과금(LLM 없음)·결정론.
 */

import { useCallback, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { PYEONG_SQM } from "@/lib/formatters";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import type { SavingCandidate, SavingScenariosResponse } from "@/components/cost/cmTypes";

function fmtKrw(won?: number | null): string {
  if (won == null || Number.isNaN(won)) return "-";
  const abs = Math.abs(won);
  const sign = won < 0 ? "-" : "";
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)}억`;
  if (abs >= 1e4) return `${sign}${Math.round(abs / 1e4).toLocaleString()}만`;
  return `${sign}${Math.round(abs).toLocaleString()}원`;
}

interface BaseParams {
  building_type: string;
  total_gfa_sqm: number;
  floor_count_above: number;
  floor_count_below: number;
  structure_type: string;
}

export function SavingScenariosCard({
  projectId,
  baseParams,
}: {
  projectId: string;
  baseParams: BaseParams;
}) {
  const [topN, setTopN] = useState(5);
  const [result, setResult] = useState<SavingScenariosResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  // "이 대안을 수지에 반영" — 어느 후보를 반영했는지 로컬 피드백(BoqDetailTable.applied 패턴).
  const updateCostData = useProjectContextStore((s) => s.updateCostData);
  // F-4: 조회 성공 시 원응답을 costData에 additive 기록(적산 보고서 조립용 — updatedAt.cost 미변경).
  const setCostSavingScenarios = useProjectContextStore((s) => s.setCostSavingScenarios);
  const [appliedIdx, setAppliedIdx] = useState<number | null>(null);

  // 후보치를 수지 costData(SSOT)에 1방향 주입 — BoqDetailTable.applyToFeasibility와 동일 형태(meta 생략).
  // 후보 응답은 총액만 제공하므로 세부 분해(지상/지하/직접/간접·범위)는 가짜값 대신 null 유지.
  const applyCandidate = useCallback(
    (c: SavingCandidate, i: number) => {
      const gfa = baseParams.total_gfa_sqm;
      const perSqm = gfa && gfa > 0 ? c.total / gfa : null;
      updateCostData({
        totalConstructionCostWon: c.total,
        perSqmWon: perSqm,
        perPyeongWon: perSqm != null ? perSqm * PYEONG_SQM : null,
        abovegroundWon: null,
        undergroundWon: null,
        landscapeWon: null,
        directWon: null,
        indirectWon: null,
        rangeMinWon: null,
        rangeMaxWon: null,
        source: "saving_scenario",
      });
      setAppliedIdx(i);
    },
    [baseParams.total_gfa_sqm, updateCostData],
  );

  const run = useCallback(async () => {
    if (!baseParams.total_gfa_sqm || baseParams.total_gfa_sqm <= 0) {
      setErr("기준안의 연면적(GFA)을 먼저 입력하세요.");
      return;
    }
    setLoading(true);
    setErr("");
    try {
      const r = await apiClient.post<SavingScenariosResponse>(
        `/cost/${projectId}/saving-scenarios`,
        { body: { base_params: baseParams, top_n: topN }, useMock: false, timeoutMs: 45000 },
      );
      setResult(r);
      setAppliedIdx(null); // 새 조회 — 이전 "반영됨" 표시 해제
      // F-4: 적산 보고서(⑤)가 §6 절감 시나리오를 조립할 수 있도록 원응답을 store에 적재.
      setCostSavingScenarios(r);
    } catch {
      setErr("절감 시나리오 조회에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }, [projectId, baseParams, topN, setCostSavingScenarios]);

  return (
    <section className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-black text-[var(--text-primary)]">공사비 절감 시나리오 Top-N</h3>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            기준안에서 구조·층수·연면적을 결정론으로 변형한 후보를 자동 생성해, 실제로 절감되는 안만 상위 N개로 보여줍니다.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-[11px] font-semibold text-[var(--text-secondary)]">
            Top
            <input
              type="number"
              min={1}
              max={10}
              value={topN}
              onChange={(e) => setTopN(Math.min(10, Math.max(1, Number(e.target.value) || 5)))}
              className="w-14 rounded-lg border border-[var(--line-strong)] bg-[var(--surface-strong)] px-2 py-1 text-center text-xs text-[var(--text-primary)] outline-none"
            />
          </label>
          <button
            onClick={run}
            disabled={loading}
            className="rounded-xl bg-[var(--accent-strong)] px-5 py-2 text-xs font-black text-white shadow-[var(--shadow-glow)] hover:opacity-90 disabled:opacity-50"
          >
            {loading ? "조회 중…" : "절감 시나리오 조회"}
          </button>
        </div>
      </div>

      {err && <p className="mt-3 text-xs font-semibold text-rose-400">{err}</p>}

      {result && (
        <div className="mt-4 grid gap-3">
          <p className="text-[11px] text-[var(--text-tertiary)]">
            생성 후보 {result.evaluated_count}건 중 절감효과 있는 후보 {result.saving_count}건 — 상위 {result.candidates.length}건 표시
          </p>
          {result.candidates.length === 0 ? (
            <p className="rounded-lg bg-[var(--surface-strong)] px-3 py-3 text-xs text-[var(--text-tertiary)]">
              이 기준안에서는 절감효과가 있는 자동 후보를 찾지 못했습니다(구조/층수/GFA 축소만 시도).
            </p>
          ) : (
            <div className="grid gap-2">
              {result.candidates.map((c, i) => (
                <div key={i} className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-xs font-bold text-[var(--text-primary)]">
                      {i + 1}. {c.label}
                    </p>
                    <p className="text-sm font-[1000] text-emerald-400">
                      -{fmtKrw(c.savings)} ({c.delta_pct}%)
                    </p>
                  </div>
                  {c.affected_work_types.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {[...new Set(c.affected.map((a) => a.wb_name ?? a.name))].map((w, j) => (
                        <span
                          key={j}
                          className="rounded bg-[var(--surface-muted)] px-1.5 py-0.5 text-[9px] font-bold text-[var(--text-tertiary)]"
                        >
                          {w}
                        </span>
                      ))}
                    </div>
                  )}
                  <p className="mt-2 text-[11px] leading-5 text-[var(--text-tertiary)]">{c.tradeoff}</p>
                  {/* 후보치를 수지(costData)에 반영 — 확정 채택안이 아닌 "후보치" 정직 고지 병기. */}
                  <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-[var(--line)]/50 pt-2">
                    <button
                      onClick={() => applyCandidate(c, i)}
                      className="rounded-lg border border-[var(--accent-strong)]/50 bg-[var(--accent-soft)] px-3 py-1.5 text-[10px] font-black text-[var(--accent-strong)] hover:opacity-90"
                    >
                      이 대안을 수지에 반영
                    </button>
                    {appliedIdx === i ? (
                      <span className="text-[10px] font-bold text-emerald-400">
                        반영됨 — 공사비 컨텍스트(출처: 절감 시나리오)가 갱신되었습니다.
                      </span>
                    ) : (
                      <span className="text-[10px] text-[var(--text-hint)]">
                        이 값은 후보 시나리오이며, 다시 클릭하거나 다른 후보를 선택하면 덮어씁니다.
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
          {result.note && (
            <p className="rounded-lg bg-[var(--surface-strong)] px-3 py-2 text-[11px] text-[var(--text-hint)]">{result.note}</p>
          )}
        </div>
      )}
    </section>
  );
}
