"use client";

/**
 * 공사비 정밀 분석 — 건축개요 기반(프로젝트 연동·지상/지하/조경/간접·최저~최대).
 *
 * 수지·사업성과 단일 데이터원 연동:
 *  ① 프로젝트 선택 시 부지·설계(건축개요) 자동 로드(전부 수정 가능)
 *  ② 지상/지하 직접공사비 + 조경 + 간접비(설계·감리·예비·일반관리) 통상 산정
 *  ③ 건설물가 변동 반영 최저~최대 예상 공사비 레인지
 *  ④ 결과를 컨텍스트(costData)에 저장 → 수지분석·투자수익성(ROI)이 동일 공사비로 정합 분석
 *  ⑤ 도면/BIM 완성 프로젝트는 항목별 정밀 적산으로 정확도 향상(안내)
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";

interface Overview {
  building_type: string; structure_type: string;
  total_gfa_sqm: number; gfa_above_sqm: number; gfa_below_sqm: number;
  unit_cost_per_sqm: number;
  aboveground_won: number; underground_won: number; landscape_won: number; direct_won: number;
  design_fee_won: number; supervision_fee_won: number; contingency_won: number; general_expense_won: number;
  indirect_won: number; total_won: number; per_pyeong_won: number;
  range: { min_won: number; expected_won: number; max_won: number };
}

const BUILDING_TYPES = [
  ["apartment", "아파트/공동주택"], ["officetel", "오피스텔"], ["office", "업무시설"],
  ["townhouse", "연립·다세대"], ["single_house", "단독주택"], ["warehouse", "지식산업센터/창고"],
] as const;
const STRUCTURES = ["RC", "SRC", "SC", "PC", "목구조"];
const PYEONG = 3.305785;

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

export function CostEstimationClient() {
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const designData = useProjectContextStore((s) => s.designData);
  const projectId = useProjectContextStore((s) => s.projectId);
  const updateCostData = useProjectContextStore((s) => s.updateCostData);

  const [pickerAddr, setPickerAddr] = useState("");
  const [bt, setBt] = useState("apartment");
  const [gfa, setGfa] = useState(0);
  const [floorsAbove, setFloorsAbove] = useState(15);
  const [floorsBelow, setFloorsBelow] = useState(2);
  const [structure, setStructure] = useState("RC");
  const [autoGfa, setAutoGfa] = useState(false);
  const [autoBt, setAutoBt] = useState(false);
  const [result, setResult] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [editedGfa, setEditedGfa] = useState(false);

  const hasDesign = !!designData?.totalGfaSqm;

  // 건축개요 자동 로드(수정한 GFA는 보존)
  useEffect(() => {
    if (!projectId) return;
    if (designData?.totalGfaSqm && !editedGfa) { setGfa(Math.round(designData.totalGfaSqm)); setAutoGfa(true); }
    if (designData?.floorCount) setFloorsAbove(designData.floorCount);
    if (designData?.buildingType) { setBt(mapBuildingType(designData.buildingType)); setAutoBt(true); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, designData]);

  const calc = useCallback(async () => {
    if (!gfa || gfa <= 0) { setErr("연면적(GFA)을 입력하세요(프로젝트 선택 시 자동 반영)."); return; }
    setLoading(true); setErr("");
    try {
      const r = await apiClient.post<Overview>("/cost/estimate-overview", {
        body: { building_type: bt, total_gfa_sqm: gfa, floor_count_above: floorsAbove, floor_count_below: floorsBelow, structure_type: structure },
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
  }, [bt, gfa, floorsAbove, floorsBelow, structure, updateCostData]);

  const breakdown = useMemo(() => result ? [
    ["지상 직접공사비", result.aboveground_won],
    ["지하 직접공사비", result.underground_won],
    ["조경", result.landscape_won],
    ["설계비", result.design_fee_won],
    ["감리비", result.supervision_fee_won],
    ["예비비(설계변경)", result.contingency_won],
    ["일반관리비", result.general_expense_won],
  ] as [string, number][] : [], [result]);

  return (
    <section className="grid gap-6">
      <div>
        <h1 className="text-2xl font-black text-[var(--text-primary)]">공사비 정밀 분석 (건축개요 기반)</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          선택한 건축개요로 지상·지하 공사비 + 조경·간접비(설계·감리·예비·일반관리)를 산정하고 최저~최대 예상 공사비를 제시합니다. 결과는 <b className="text-[var(--text-primary)]">수지분석·투자수익성(ROI)과 자동 연동</b>됩니다. 자동 값도 모두 수정 가능합니다.
        </p>
      </div>

      <ProjectAddressInput value={pickerAddr} onChange={setPickerAddr} label="분석 대상 프로젝트" pickerLabel="프로젝트" placeholder="프로젝트를 선택하거나 주소를 검색하세요" />

      {hasDesign && (
        <p className="-mt-3 text-[11px] text-emerald-400">🏗 설계(건축개요) 연동됨 — 도면/BIM 완성 시 항목별 정밀 적산으로 정확도가 향상됩니다.</p>
      )}

      {/* 건축개요 입력 */}
      <div className="grid gap-4 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5 sm:grid-cols-2 lg:grid-cols-3">
        <label className="flex flex-col gap-1">
          <span className="flex items-center gap-1.5 text-[11px] font-semibold text-[var(--text-secondary)]">건축유형 {autoBt && <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[9px] font-bold text-emerald-400">자동</span>}</span>
          <select value={bt} onChange={(e) => { setBt(e.target.value); setAutoBt(false); }} className={fcls}>{BUILDING_TYPES.map(([c, n]) => <option key={c} value={c}>{n}</option>)}</select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="flex items-center gap-1.5 text-[11px] font-semibold text-[var(--text-secondary)]">연면적(GFA) {autoGfa && !editedGfa && <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[9px] font-bold text-emerald-400">자동</span>}{editedGfa && <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[9px] font-bold text-amber-400">수정됨</span>}</span>
          <div className="flex items-center gap-1.5"><input type="number" value={gfa} onChange={(e) => { setGfa(Number(e.target.value)); setEditedGfa(true); }} className={fcls} /><span className="text-[11px] text-[var(--text-tertiary)]">㎡</span></div>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold text-[var(--text-secondary)]">구조</span>
          <select value={structure} onChange={(e) => setStructure(e.target.value)} className={fcls}>{STRUCTURES.map((s) => <option key={s} value={s}>{s}조</option>)}</select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold text-[var(--text-secondary)]">지상 층수</span>
          <input type="number" value={floorsAbove} onChange={(e) => setFloorsAbove(Number(e.target.value))} className={fcls} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold text-[var(--text-secondary)]">지하 층수</span>
          <input type="number" value={floorsBelow} onChange={(e) => setFloorsBelow(Number(e.target.value))} className={fcls} />
        </label>
      </div>

      <div className="flex items-center gap-3">
        <button onClick={calc} disabled={loading} className="rounded-xl bg-[var(--accent-strong)] px-8 py-3 text-sm font-black text-white shadow-[var(--shadow-glow)] hover:opacity-90 disabled:opacity-50">
          {loading ? "공사비 산정 중…" : "공사비 정밀 분석 실행"}
        </button>
        {err && <span className="text-xs font-semibold text-rose-400">{err}</span>}
      </div>

      {result && (
        <>
          {/* 총공사비 + range */}
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] p-5">
              <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">총 공사비(기대)</p>
              <p className="mt-2 text-2xl font-[1000] text-[var(--accent-strong)]">{fmtKrw(result.total_won)}</p>
              <p className="mt-1 text-[11px] text-[var(--text-secondary)]">평당 {result.per_pyeong_won.toLocaleString()}원</p>
            </div>
            <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-5">
              <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">최저~최대 예상</p>
              <p className="mt-2 text-lg font-[1000] text-[var(--text-primary)]">{fmtKrw(result.range.min_won)} ~ {fmtKrw(result.range.max_won)}</p>
              <p className="mt-1 text-[11px] text-[var(--text-secondary)]">건설물가 변동 ±(설계변경 반영)</p>
            </div>
            <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-5">
              <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">규모</p>
              <p className="mt-2 text-sm font-bold text-[var(--text-primary)]">연면적 {result.total_gfa_sqm.toLocaleString()}㎡</p>
              <p className="mt-1 text-[11px] text-[var(--text-secondary)]">지상 {result.gfa_above_sqm.toLocaleString()} / 지하 {result.gfa_below_sqm.toLocaleString()}㎡</p>
            </div>
          </div>

          {/* 항목별 분해 */}
          <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5">
            <h3 className="mb-3 text-sm font-black text-[var(--text-primary)]">공사비 항목별 구조</h3>
            <div className="space-y-2">
              {breakdown.map(([label, v]) => {
                const pct = result.total_won > 0 ? (v / result.total_won) * 100 : 0;
                return (
                  <div key={label} className="flex items-center gap-3">
                    <span className="w-28 shrink-0 text-xs font-semibold text-[var(--text-secondary)]">{label}</span>
                    <div className="h-3 flex-1 overflow-hidden rounded-full bg-[var(--surface-strong)]"><div className="h-full rounded-full bg-[var(--accent-strong)]" style={{ width: `${Math.min(100, pct)}%` }} /></div>
                    <span className="w-24 shrink-0 text-right text-xs font-bold text-[var(--text-primary)]">{fmtKrw(v)}</span>
                    <span className="w-10 shrink-0 text-right text-[11px] text-[var(--text-tertiary)]">{pct.toFixed(0)}%</span>
                  </div>
                );
              })}
            </div>
            <p className="mt-4 rounded-lg bg-[var(--surface-strong)] px-3 py-2 text-[11px] text-[var(--accent-strong)]">🔗 이 공사비가 <b>수지분석·투자수익성(ROI)</b>에 자동 반영됩니다(단일 데이터원).</p>
          </div>
        </>
      )}
    </section>
  );
}
