"use client";

import { useEffect, useState } from "react";
import { Button, Card, CardContent, CardTitle, Input } from "@propai/ui";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { NumberInput } from "@/components/common/NumberInput";
import { apiClient } from "@/lib/api-client";

/* ── Types ── */

type UnitTypeInfo = {
  code: string;
  name: string;
  area_sqm: number;
  area_pyeong: number;
  parking_per_unit: number;
};

type UnitDetail = {
  code: string;
  name: string;
  area_sqm: number;
  area_pyeong: number;
  count: number;
  ratio_pct: number;
  price_per_pyeong_10k: number;
  total_revenue_won: number;
  parking_required: number;
};

type OptimizeResponse = {
  method: string;
  total_units: number;
  total_gfa_used_sqm: number;
  gfa_efficiency_pct: number;
  total_revenue_won: number;
  total_revenue_100m: number;
  total_parking_required: number;
  units: UnitDetail[];
  error?: string;
};

type UnitTypesResponse = {
  types: UnitTypeInfo[];
  default_prices: Record<string, number>;
  default_demand: Record<string, number>;
};

/* ── Formatters ── */

function formatBillion(won: number): string {
  const billions = won / 100_000_000;
  if (billions >= 10000) {
    return `${(billions / 10000).toFixed(1)}조`;
  }
  return `${Math.round(billions).toLocaleString()}억`;
}

/* ── Color palette for stacked bar ── */

const UNIT_COLORS = [
  "rgb(14, 116, 144)",   // teal
  "rgb(59, 130, 246)",   // blue
  "rgb(168, 85, 247)",   // purple
  "rgb(236, 72, 153)",   // pink
  "rgb(245, 158, 11)",   // amber
  "rgb(34, 197, 94)",    // green
  "rgb(239, 68, 68)",    // red
];

/* ── Component ── */

export function UnitMixOptimizerPanel() {
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const designData = useProjectContextStore((s) => s.designData);
  const updateFeasibilityData = useProjectContextStore(
    (s) => s.updateFeasibilityData,
  );
  const addAnalysisResult = useProjectContextStore(
    (s) => s.addAnalysisResult,
  );

  // Form state
  const [totalGfa, setTotalGfa] = useState("");
  const [region, setRegion] = useState("서울");
  const [maxFloors, setMaxFloors] = useState("25");
  const [maxFar, setMaxFar] = useState("250");
  const [maxBcr, setMaxBcr] = useState("60");
  const [landArea, setLandArea] = useState("1000");

  // Demand sliders
  const [unitTypes, setUnitTypes] = useState<UnitTypeInfo[]>([]);
  const [demandRatio, setDemandRatio] = useState<Record<string, number>>({});
  const [defaultDemand, setDefaultDemand] = useState<Record<string, number>>(
    {},
  );

  // Results
  const [result, setResult] = useState<OptimizeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Pre-fill from project context
  useEffect(() => {
    if (designData?.totalGfaSqm) {
      setTotalGfa(String(designData.totalGfaSqm));
    }
    if (designData?.far) {
      setMaxFar(String(designData.far));
    }
    if (designData?.bcr) {
      setMaxBcr(String(designData.bcr));
    }
    if (designData?.floorCount) {
      setMaxFloors(String(designData.floorCount));
    }
    const eff = effectiveLandAreaSqm(siteAnalysis); // 다필지=통합 면적 우선
    if (eff) {
      setLandArea(String(eff));
    }
  }, [designData, siteAnalysis]);

  // 표준 평형 타입·기본 수요비율을 백엔드에서 로드(/unit-mix/types). 실패 시 폴백(무중단).
  useEffect(() => {
    let cancelled = false;
    const fallback: Record<string, number> = {
      S39: 0.05, S49: 0.1, S59: 0.25, S74: 0.15, S84: 0.3, S102: 0.1, S135: 0.05,
    };
    (async () => {
      try {
        const res = await apiClient.get<UnitTypesResponse>("/unit-mix/types", { useMock: false });
        if (cancelled) return;
        setUnitTypes(res.types ?? []);
        const demand = res.default_demand && Object.keys(res.default_demand).length ? res.default_demand : fallback;
        setDefaultDemand(demand);
        setDemandRatio(demand);
      } catch {
        if (cancelled) return;
        setDefaultDemand(fallback);
        setDemandRatio(fallback);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  function handleDemandChange(code: string, value: number) {
    setDemandRatio((prev) => ({ ...prev, [code]: value }));
  }

  async function handleOptimize() {
    const gfa = Number(totalGfa);
    if (!Number.isFinite(gfa) || gfa <= 0) {
      setError("총 연면적을 입력해주세요.");
      return;
    }

    setLoading(true);
    setError("");
    setResult(null);

    try {
      // ★실백엔드 배선: 서버 SLSQP 최적화기(/unit-mix/optimize)가 실제 시세(default_prices)·용적률
      //   제약으로 수익 극대화 유닛믹스를 계산한다(과거 하드코딩 상수+setTimeout 목업 제거·무목업).
      const res = await apiClient.post<OptimizeResponse>("/unit-mix/optimize", {
        useMock: false,
        body: {
          total_gfa_sqm: gfa,
          land_area_sqm: Number(landArea) || 1000,
          max_far_pct: Number(maxFar) || 250,
          max_bcr_pct: Number(maxBcr) || 60,
          max_floors: Number(maxFloors) || 25,
          region,
          demand_ratio: demandRatio,
        },
      });
      if (res.error) {
        setError(res.error);
        return;
      }
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "평형 구성 최적화 실패");
    } finally {
      setLoading(false);
    }
  }

  function handleApplyToFeasibility() {
    if (!result) return;

    // merge 패치 — 기존 totalCostWon(수지/공사비 산출분)을 보존(null로 덮지 않음).
    updateFeasibilityData({
      totalRevenueWon: result.total_revenue_won,
    });
    addAnalysisResult({
      module: "unit-mix",
      completedAt: new Date().toISOString(),
      summary: {
        totalUnits: result.total_units,
        totalRevenue100m: result.total_revenue_100m,
        method: result.method,
        gfaEfficiency: result.gfa_efficiency_pct,
      },
    });
  }

  return (
    <Card>
      <CardContent className="p-6">
        <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
          평형 구성 최적화
        </p>
        <CardTitle className="mt-2 text-xl">
          수익 극대화 평형 배분 계산
        </CardTitle>

        {/* Inputs */}
        <div className="mt-5 grid gap-3 md:grid-cols-3">
          <NumberInput
            allowDecimal
            value={totalGfa === "" ? null : Number(totalGfa)}
            onChange={(n) => setTotalGfa(n != null ? String(n) : "")}
            placeholder="총 연면적 (m2)"
            className="flex h-11 w-full rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
          />
          <NumberInput
            allowDecimal
            value={landArea === "" ? null : Number(landArea)}
            onChange={(n) => setLandArea(n != null ? String(n) : "")}
            placeholder="대지면적 (m2)"
            className="flex h-11 w-full rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
          />
          <Input
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            placeholder="지역 (예: 서울)"
          />
        </div>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <Input
            type="number"
            value={maxFloors}
            onChange={(e) => setMaxFloors(e.target.value)}
            placeholder="최대 층수"
          />
          <Input
            type="number"
            value={maxFar}
            onChange={(e) => setMaxFar(e.target.value)}
            placeholder="용적률 상한 (%)"
          />
          <Input
            type="number"
            value={maxBcr}
            onChange={(e) => setMaxBcr(e.target.value)}
            placeholder="건폐율 상한 (%)"
          />
        </div>

        {/* Demand ratio sliders */}
        {Object.keys(demandRatio).length > 0 && (
          <div className="mt-5">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              수요 비율 조정
            </p>
            <div className="mt-3 grid gap-2">
              {Object.entries(demandRatio).map(([code, ratio]) => {
                const typeInfo = unitTypes.find((t) => t.code === code);
                const label = typeInfo
                  ? typeInfo.name
                  : code;
                return (
                  <div
                    key={code}
                    className="flex items-center gap-3"
                  >
                    <span className="w-28 text-xs text-[var(--text-secondary)]">
                      {label}
                    </span>
                    <input
                      type="range"
                      min={0}
                      max={50}
                      step={1}
                      value={Math.round(ratio * 100)}
                      onChange={(e) =>
                        handleDemandChange(
                          code,
                          Number(e.target.value) / 100,
                        )
                      }
                      className="flex-1"
                    />
                    <span className="w-12 text-right text-xs font-semibold text-[var(--text-primary)]">
                      {Math.round(ratio * 100)}%
                    </span>
                  </div>
                );
              })}
            </div>
            <button
              type="button"
              onClick={() => setDemandRatio({ ...defaultDemand })}
              className="mt-2 text-[10px] text-[var(--accent-strong)] underline"
            >
              기본값 초기화
            </button>
          </div>
        )}

        {/* Action */}
        <div className="mt-5">
          <Button onClick={handleOptimize} disabled={loading}>
            {loading ? "최적화 계산 중..." : "최적 평형 구성 계산"}
          </Button>
        </div>

        {/* Error */}
        {error && (
          <div className="mt-4 rounded-[var(--radius-xl)] border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] p-4 text-sm text-[var(--spot)]">
            {error}
          </div>
        )}

        {/* Results */}
        {result && !result.error && (
          <div className="mt-6 space-y-5">
            {/* Summary metrics */}
            <div className="grid gap-3 md:grid-cols-4">
              <MetricTile
                label="총 세대수"
                value={`${result.total_units.toLocaleString()}세대`}
              />
              <MetricTile
                label="총 분양수입"
                value={formatBillion(result.total_revenue_won)}
              />
              <MetricTile
                label="연면적 효율"
                value={`${result.gfa_efficiency_pct}%`}
              />
              <MetricTile
                label="총 주차대수"
                value={`${result.total_parking_required.toLocaleString()}대`}
              />
            </div>

            {/* Stacked bar chart */}
            <div>
              <p className="mb-2 text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                평형 배분 비율
              </p>
              <div className="flex h-8 w-full overflow-hidden rounded-[var(--radius-lg)]">
                {(result.units ?? []).map((u, i) => (
                  <div
                    key={u.code}
                    style={{
                      width: `${u.ratio_pct}%`,
                      backgroundColor:
                        UNIT_COLORS[i % UNIT_COLORS.length],
                    }}
                    className="relative flex items-center justify-center transition-all"
                    title={`${u.name}: ${u.count}세대 (${u.ratio_pct}%)`}
                  >
                    {u.ratio_pct >= 8 && (
                      <span className="text-[10px] font-semibold text-white">
                        {u.ratio_pct}%
                      </span>
                    )}
                  </div>
                ))}
              </div>
              {/* Legend */}
              <div className="mt-2 flex flex-wrap gap-3">
                {(result.units ?? []).map((u, i) => (
                  <div key={u.code} className="flex items-center gap-1.5">
                    <span
                      className="inline-block h-2.5 w-2.5 rounded-sm"
                      style={{
                        backgroundColor:
                          UNIT_COLORS[i % UNIT_COLORS.length],
                      }}
                    />
                    <span className="text-[10px] text-[var(--text-secondary)]">
                      {u.name} ({u.count}세대)
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Detailed table */}
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--line)]">
                    <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                      평형
                    </th>
                    <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                      세대수
                    </th>
                    <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                      비율
                    </th>
                    <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                      분양가 (만원/평)
                    </th>
                    <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                      수입
                    </th>
                    <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                      주차
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {(result.units ?? []).map((u) => (
                    <tr
                      key={u.code}
                      className="border-b border-[var(--line)] last:border-0"
                    >
                      <td className="px-3 py-2 text-[var(--text-primary)]">
                        {u.name}
                      </td>
                      <td className="px-3 py-2 text-right font-semibold text-[var(--text-primary)]">
                        {u.count.toLocaleString()}
                      </td>
                      <td className="px-3 py-2 text-right text-[var(--text-secondary)]">
                        {u.ratio_pct}%
                      </td>
                      <td className="px-3 py-2 text-right text-[var(--text-secondary)]">
                        {u.price_per_pyeong_10k.toLocaleString()}
                      </td>
                      <td className="px-3 py-2 text-right font-semibold text-[var(--text-primary)]">
                        {formatBillion(u.total_revenue_won)}
                      </td>
                      <td className="px-3 py-2 text-right text-[var(--text-secondary)]">
                        {u.parking_required}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Method badge + apply button */}
            <div className="flex items-center justify-between">
              <span className="rounded-full border border-[var(--line)] px-3 py-1 text-[10px] font-medium text-[var(--text-tertiary)]">
                {result.method}
              </span>
              <Button onClick={handleApplyToFeasibility}>
                수지분석에 적용
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ── MetricTile ── */

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-4">
      <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-2 text-sm font-semibold text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}
