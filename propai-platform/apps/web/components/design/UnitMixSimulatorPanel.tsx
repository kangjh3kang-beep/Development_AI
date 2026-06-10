"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";

// 백엔드 API 베이스(스튜디오와 동일 규칙). 4t8t.net 등 운영 도메인 → api.4t8t.net.
function apiBase(): string {
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host === "4t8t.net" || host === "www.4t8t.net" || host.endsWith(".pages.dev") || host === "propai.kr") {
      return "https://api.4t8t.net/api/v1";
    }
  }
  return "http://localhost:8000/api/v1";
}

interface MixEntry { type: string; area_sqm: number; ratio_pct: number }

interface SimUnit {
  type: string; area_sqm: number; count_per_floor: number; total_count: number;
  area_pyeong: number; ratio_pct: number; revenue_won: number;
}
interface SimResult {
  units: SimUnit[]; total_units: number; gfa_sqm: number; sellable_area_sqm: number;
  revenue_won: number; land_cost_won: number; build_cost_won: number;
  indirect_cost_won: number; total_cost_won: number; profit_won: number; roi_pct: number;
  sale_price_per_pyeong_won: number; price_source: string; note: string;
}

interface Props {
  projectId: string;
  buildingWidthM?: number;
  buildingDepthM?: number;
  floorCount?: number;
  landAreaSqm?: number;
  buildingUse?: string;
  officialPricePerSqm?: number | null;
  defaultTypes?: string[] | null;
  // 평면 반영 콜백: mixParam("59A:59:20,84A:84:20") + 타입목록 → 부모가 도면 갱신
  onApplyMix?: (mixParam: string, types: string[]) => void;
}

// "59A"·"84B"·"114C"·"74" → 전용면적(㎡) 추정(앞 숫자). 실패 시 84.
function typeToArea(t: string): number {
  const m = /(\d+(?:\.\d+)?)/.exec(t || "");
  return m ? Number(m[1]) : 84;
}

const 억 = (won: number) => (won / 1e8).toLocaleString(undefined, { maximumFractionDigits: 1 });

export function UnitMixSimulatorPanel({
  projectId, buildingWidthM, buildingDepthM, floorCount, landAreaSqm,
  buildingUse = "공동주택", officialPricePerSqm, defaultTypes, onApplyMix,
}: Props) {
  const seedTypes = useMemo(
    () => (defaultTypes && defaultTypes.length > 0 ? defaultTypes : ["59A", "84A"]),
    [defaultTypes],
  );
  const [entries, setEntries] = useState<MixEntry[]>([]);
  const [salePrice10k, setSalePrice10k] = useState<string>(""); // 만원/평(선택, 비우면 기본값)
  const [result, setResult] = useState<SimResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [applied, setApplied] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 초기 시드: 타입별 균등 비율
  useEffect(() => {
    setEntries(seedTypes.map((t, i) => ({
      type: t, area_sqm: typeToArea(t),
      ratio_pct: Math.round((100 / seedTypes.length) * 10) / 10 + (i === 0 ? 100 - Math.round((100 / seedTypes.length) * 10) / 10 * seedTypes.length : 0),
    })));
  }, [seedTypes]);

  const canSim = !!(buildingWidthM && buildingDepthM && floorCount);

  const runSim = useCallback(async () => {
    if (!canSim || entries.length === 0) return;
    setLoading(true);
    try {
      const body: Record<string, unknown> = {
        building_width_m: buildingWidthM,
        building_depth_m: buildingDepthM,
        floor_count: floorCount,
        building_use: buildingUse,
        mix: entries.map((e) => ({ type: e.type, area_sqm: e.area_sqm, ratio_pct: e.ratio_pct })),
      };
      if (landAreaSqm) body.land_area_sqm = landAreaSqm;
      if (officialPricePerSqm) body.official_price_per_sqm = officialPricePerSqm;
      const p = Number(salePrice10k);
      if (salePrice10k && p > 0) body.sale_price_per_pyeong_won = p * 10000; // 만원→원
      const res = await fetch(`${apiBase()}/design/${encodeURIComponent(projectId)}/unit-mix/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(20000),
      });
      if (res.ok) setResult(await res.json());
    } catch {
      /* 실패 무시 — 다음 변경 시 재시도 */
    } finally {
      setLoading(false);
    }
  }, [canSim, entries, buildingWidthM, buildingDepthM, floorCount, buildingUse, landAreaSqm, officialPricePerSqm, salePrice10k, projectId]);

  // 입력 변경 → 디바운스 재계산
  useEffect(() => {
    if (!canSim || entries.length === 0) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(runSim, 400);
    setApplied(false);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [entries, salePrice10k, canSim, runSim]);

  const setRatio = (idx: number, v: number) => {
    setEntries((prev) => prev.map((e, i) => (i === idx ? { ...e, ratio_pct: v } : e)));
  };
  const ratioSum = entries.reduce((s, e) => s + e.ratio_pct, 0);

  const applyToFloorPlan = () => {
    if (!result || result.units.length === 0 || !onApplyMix) return;
    const mixParam = result.units.map((u) => `${u.type}:${u.area_sqm}:${u.total_count}`).join(",");
    onApplyMix(mixParam, result.units.map((u) => u.type));
    setApplied(true);
  };

  if (!canSim) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-5 text-center">
        <p className="text-[11px] text-white/40">세대믹스 시뮬레이션은 건축개요(폭·깊이·층수)가 준비되면 활성화됩니다.</p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h4 className="flex items-center gap-2 text-sm font-black text-white">
            <span className="text-[var(--accent-strong)]">◧</span> 세대믹스 시뮬레이터
          </h4>
          <p className="mt-0.5 text-[10px] text-white/40">비율을 조정하면 평형별 세대수·분양수입·약식 ROI가 실시간 갱신됩니다.</p>
        </div>
        {loading && <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-[var(--accent-strong)] border-t-transparent" />}
      </div>

      {/* 비율 슬라이더 */}
      <div className="space-y-3">
        {entries.map((e, i) => (
          <div key={e.type}>
            <div className="flex items-center justify-between px-0.5">
              <span className="text-[11px] font-bold text-white/80">{e.type} <span className="text-white/35">({e.area_sqm}㎡)</span></span>
              <span className="text-[11px] font-black text-[var(--accent-strong)]">{e.ratio_pct.toFixed(0)}%</span>
            </div>
            <input
              type="range" min={0} max={100} step={5} value={e.ratio_pct}
              onChange={(ev) => setRatio(i, Number(ev.target.value))}
              className="h-1 w-full cursor-pointer rounded-full bg-white/10 accent-[var(--accent-strong)]"
            />
          </div>
        ))}
        <p className="text-right text-[9px] font-bold text-white/30">비율 합계 {ratioSum.toFixed(0)}% (자동 정규화)</p>
      </div>

      {/* 분양가 입력(선택) */}
      <div className="mt-3 flex items-center gap-2 border-t border-white/5 pt-3">
        <span className="text-[10px] font-bold text-white/45">분양가(만원/평)</span>
        <input
          type="number" inputMode="numeric" placeholder="시세 미입력 시 기본값"
          value={salePrice10k} onChange={(e) => setSalePrice10k(e.target.value)}
          className="w-32 rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-[11px] font-bold text-white focus:border-[var(--accent-strong)] focus:outline-none"
        />
        {result && <span className="text-[9px] text-white/30">출처: {result.price_source}</span>}
      </div>

      {/* 결과 */}
      {result && (
        <div className="mt-4 space-y-3">
          {/* 평형별 세대수 */}
          <div className="overflow-hidden rounded-xl border border-white/5">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="bg-white/5 text-white/45">
                  <th className="px-2 py-1.5 text-left font-black">평형</th>
                  <th className="px-2 py-1.5 text-right font-black">세대수</th>
                  <th className="px-2 py-1.5 text-right font-black">층당</th>
                  <th className="px-2 py-1.5 text-right font-black">분양수입</th>
                </tr>
              </thead>
              <tbody>
                {result.units.map((u) => (
                  <tr key={u.type} className="border-t border-white/5 text-white/80">
                    <td className="px-2 py-1.5 font-bold">{u.type} <span className="text-white/35">{u.area_pyeong}평</span></td>
                    <td className="px-2 py-1.5 text-right font-black">{u.total_count}</td>
                    <td className="px-2 py-1.5 text-right text-white/50">{u.count_per_floor}</td>
                    <td className="px-2 py-1.5 text-right">{억(u.revenue_won)}억</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* 핵심 지표 */}
          <div className="grid grid-cols-4 gap-2">
            <Metric label="총 세대" value={`${result.total_units}`} />
            <Metric label="분양수입" value={`${억(result.revenue_won)}억`} />
            <Metric label="총사업비" value={`${억(result.total_cost_won)}억`} />
            <Metric label="약식 ROI" value={`${result.roi_pct}%`} accent={result.roi_pct >= 0} />
          </div>

          <div className="flex items-center justify-between gap-2">
            <p className="text-[9px] leading-tight text-white/30">{result.note}</p>
            <button
              onClick={applyToFloorPlan}
              className={`shrink-0 rounded-full px-4 py-2 text-[10px] font-black uppercase tracking-widest transition-colors ${
                applied ? "bg-emerald-500 text-white" : "bg-[var(--accent-strong)] text-white hover:opacity-90"
              }`}
            >
              {applied ? "✓ 평면 반영됨" : "이 믹스로 평면 반영"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="rounded-xl border border-white/5 bg-white/[0.03] p-2.5">
      <p className="text-[8px] font-black uppercase tracking-wider text-white/35">{label}</p>
      <p className={`mt-0.5 text-[13px] font-black ${accent === false ? "text-rose-400" : "text-white"}`}>{value}</p>
    </div>
  );
}
