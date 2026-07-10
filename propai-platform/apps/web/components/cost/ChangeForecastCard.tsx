"use client";

/**
 * P4 T2 — 설계변경 예측공사비 카드.
 * 몬테카를로 추가공사비 밴드(p10/50/90)는 항상 산출하고, 설계변경 사전예측(D3,
 * /design-risk/predict)의 리스크를 opt-in으로 불러와 공종(WB) 단위 delta 시나리오를 얹는다.
 * design-risk 서비스와 서버간 결합 없이 프론트가 결과를 그대로 전달하는 입력 주입 방식.
 * POST /api/v1/cost/{pid}/change-forecast. 무과금(LLM 없음)·개산 정직 배지.
 */

import { useCallback, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import type { ChangeForecastResponse, ChangeForecastRiskInput } from "@/components/cost/cmTypes";
import type { DesignRiskPredictResponse } from "@/components/design-risk/types";

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

export function ChangeForecastCard({
  projectId,
  baseParams,
}: {
  projectId: string;
  baseParams: BaseParams;
}) {
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  // F-4: 조회 성공 시 원응답을 costData에 additive 기록(적산 보고서 조립용 — updatedAt.cost 미변경).
  const setCostChangeForecast = useProjectContextStore((s) => s.setCostChangeForecast);

  const [risks, setRisks] = useState<ChangeForecastRiskInput[]>([]);
  const [riskLoading, setRiskLoading] = useState(false);
  const [riskMsg, setRiskMsg] = useState("");

  const [result, setResult] = useState<ChangeForecastResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  // 리스크 가져오기(선택) — D3 사전예측(/design-risk/predict)을 그대로 호출해 risks[]를
  // 입력으로 주입한다(서버간 강결합 없음 — 프론트가 두 API를 순차 호출할 뿐).
  const loadRisks = useCallback(async () => {
    const addr = siteAnalysis?.address;
    if (!addr) {
      setRiskMsg("부지분석 주소가 없어 리스크를 불러올 수 없습니다. MC 밴드만 조회됩니다.");
      return;
    }
    setRiskLoading(true);
    setRiskMsg("");
    try {
      const r = await apiClient.post<DesignRiskPredictResponse>("/design-risk/predict", {
        useMock: false,
        body: { address: addr, pnu: siteAnalysis?.pnu ?? undefined, project_id: projectId },
      });
      if (r.ok && r.risks) {
        setRisks(r.risks as ChangeForecastRiskInput[]);
        setRiskMsg(`설계변경 리스크 ${r.risks.length}건 반영됨`);
      } else {
        setRiskMsg("리스크 예측 결과가 없습니다(MC 밴드만 조회됩니다).");
      }
    } catch {
      setRiskMsg("리스크 조회에 실패했습니다(MC 밴드만 조회됩니다).");
    } finally {
      setRiskLoading(false);
    }
  }, [siteAnalysis, projectId]);

  const run = useCallback(async () => {
    if (!baseParams.total_gfa_sqm || baseParams.total_gfa_sqm <= 0) {
      setErr("기준안의 연면적(GFA)을 먼저 입력하세요.");
      return;
    }
    setLoading(true);
    setErr("");
    try {
      const r = await apiClient.post<ChangeForecastResponse>(
        `/cost/${projectId}/change-forecast`,
        { body: { base_params: baseParams, risks }, useMock: false, timeoutMs: 45000 },
      );
      setResult(r);
      // F-4: 적산 보고서(⑤)가 §7 설계변경 예측공사비를 조립할 수 있도록 원응답을 store에 적재.
      setCostChangeForecast(r);
    } catch {
      setErr("설계변경 예측공사비 조회에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }, [projectId, baseParams, risks, setCostChangeForecast]);

  return (
    <section className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-black text-[var(--text-primary)]">설계변경 예측공사비</h3>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            착공 전 설계변경 리스크가 실제로 얼마짜리 공사비 변동인지, 몬테카를로 밴드와 공종별 시나리오로 보여줍니다.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={loadRisks}
            disabled={riskLoading}
            className="rounded-xl border border-[var(--line-strong)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] disabled:opacity-50"
          >
            {riskLoading ? "리스크 조회 중…" : `설계변경 리스크 불러오기(선택)${risks.length ? ` · ${risks.length}건` : ""}`}
          </button>
          <button
            onClick={run}
            disabled={loading}
            className="rounded-xl bg-[var(--accent-strong)] px-5 py-2 text-xs font-black text-white shadow-[var(--shadow-glow)] hover:opacity-90 disabled:opacity-50"
          >
            {loading ? "예측 중…" : "설계변경 예측 실행"}
          </button>
        </div>
      </div>

      {riskMsg && <p className="mt-2 text-[11px] text-[var(--text-tertiary)]">{riskMsg}</p>}
      {err && <p className="mt-3 text-xs font-semibold text-rose-400">{err}</p>}

      {result && (
        <div className="mt-4 grid gap-4">
          <span className="w-fit rounded bg-amber-500/15 px-2 py-0.5 text-[10px] font-bold text-amber-400">
            개산(추정) — 확정 아님
          </span>

          {/* MC 밴드 타일 */}
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-3">
            {(
              [
                ["P10", result.mc_band.p10],
                ["P50(중앙)", result.mc_band.p50],
                ["P90", result.mc_band.p90],
              ] as const
            ).map(([label, v]) => (
              <div key={label} className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-3 text-center">
                <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-hint)]">{label}</p>
                <p className="mt-1 text-sm font-[1000] text-[var(--text-primary)]">{fmtKrw(v)}</p>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-[var(--text-tertiary)]">
            기준 총공사비 {fmtKrw(result.mc_band.base_total)} 대비 몬테카를로 추가공사비 분포(설계변경 리스크 계수 포함).
          </p>

          {/* 리스크 → 공종 delta 시나리오 */}
          {result.scenarios.length > 0 && (
            <div className="overflow-x-auto rounded-xl border border-[var(--line)]">
              <table className="w-full min-w-[520px] text-left text-xs">
                <thead className="bg-[var(--surface-strong)] text-[var(--text-tertiary)]">
                  <tr>
                    <th className="px-3 py-2 font-bold">리스크</th>
                    <th className="px-3 py-2 font-bold">영향 공종</th>
                    <th className="px-3 py-2 font-bold">델타(%)</th>
                    <th className="px-3 py-2 font-bold text-right">추가공사비</th>
                  </tr>
                </thead>
                <tbody>
                  {result.scenarios.map((s, i) => (
                    <tr key={i} className="border-t border-[var(--line)]">
                      <td className="px-3 py-2 text-[var(--text-primary)]">{s.risk_item}</td>
                      <td className="px-3 py-2 text-[var(--text-secondary)]">{s.wb_names.filter(Boolean).join(", ")}</td>
                      <td className="px-3 py-2 text-[var(--text-secondary)]">
                        {s.delta_pct_low === s.delta_pct_high ? `+${s.delta_pct_low}%` : `+${s.delta_pct_low}~${s.delta_pct_high}%`}
                      </td>
                      <td className="px-3 py-2 text-right font-bold text-rose-400">
                        {s.delta_low === s.delta_high ? `+${fmtKrw(s.delta_low)}` : `+${fmtKrw(s.delta_low)}~${fmtKrw(s.delta_high)}`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {result.data_gaps.length > 0 && (
            <div className="rounded-lg bg-[var(--surface-strong)] px-3 py-2">
              <p className="text-[10px] font-bold text-[var(--text-secondary)]">부족·스킵 데이터</p>
              <ul className="mt-1 list-disc pl-4 text-[11px] text-[var(--text-tertiary)]">
                {result.data_gaps.map((g, i) => (
                  <li key={i}>{g}</li>
                ))}
              </ul>
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
