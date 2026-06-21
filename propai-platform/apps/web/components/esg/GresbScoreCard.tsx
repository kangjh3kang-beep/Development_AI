"use client";

import { useState } from "react";
import { Button, Card, CardContent } from "@propai/ui";
import { ApiClientError, apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { NumberInput } from "@/components/common/NumberInput";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";
import {
  adaptEvidence,
  type BackendEvidence,
  type BackendLegalRef,
} from "@/lib/evidence/adaptEvidence";

/* ── Types ── */

interface ComponentScore {
  score: number;
  max: number;
}

interface Recommendation {
  area: string;
  action: string;
  potential_gain: number;
  cost_grade: string;
  priority: number;
}

interface GresbResult {
  total_score: number;
  max_score: number;
  grade: string;
  grade_label: string;
  components: {
    management: ComponentScore;
    performance: ComponentScore;
    development: ComponentScore;
    energy?: { value: number; benchmark: number; rating: string };
    ghg?: { value: number; benchmark: number; rating: string };
  };
  benchmark_type: string;
  benchmark_meta?: { version?: string; source?: string };
  recommendations: Recommendation[];
  potential_score: number;
  // 백엔드가 evidence/legal_refs를 반환하면 우선 사용(현재 미반환 → 응답 점수로 트레이스 구성).
  evidence?: BackendEvidence[];
  legal_refs?: BackendLegalRef[];
}

/**
 * GRESB 점수 산출 근거(EvidencePanel) — 백엔드 evidence가 있으면 우선,
 * 없으면 응답의 구성요소 점수·벤치마크로 산식 트레이스를 만든다(가짜값/가짜URL 0).
 */
function buildGresbEvidence(r: GresbResult): EvidenceItem[] {
  const backend = adaptEvidence(r.evidence, r.legal_refs);
  if (backend.length > 0) return backend;

  const c = r.components;
  const items: EvidenceItem[] = [
    {
      label: "총점",
      value: `${r.total_score}/${r.max_score}점 (${r.grade})`,
      basis: "경영 + 성과 + 개발 구성점수 합산",
    },
    {
      label: "Management(경영)",
      value: `${c.management.score}/${c.management.max}점`,
      basis: "ESG 정책·거버넌스 등 경영 구성 가중점수",
    },
    {
      label: "Performance(성과)",
      value: `${c.performance.score}/${c.performance.max}점`,
      basis: "에너지·온실가스·용수 등 실측 성과 벤치마크 대비 점수",
    },
    {
      label: "Development(개발)",
      value: `${c.development.score}/${c.development.max}점`,
      basis: "녹색건축 인증·재생에너지 등 개발단계 점수",
    },
  ];
  if (c.energy) {
    items.push({
      label: "에너지 강도",
      value: `${(c.energy.value ?? 0).toFixed(1)} (${c.energy.rating})`,
      basis: `벤치마크 ${c.energy.benchmark} 대비 (${r.benchmark_type})`,
    });
  }
  if (c.ghg) {
    items.push({
      label: "온실가스 강도",
      value: `${(c.ghg.value ?? 0).toFixed(1)} (${c.ghg.rating})`,
      basis: `벤치마크 ${c.ghg.benchmark} 대비 (${r.benchmark_type})`,
    });
  }
  items.push({
    label: "잠재 점수",
    value: `${r.potential_score}점`,
    basis: "개선 권고사항을 모두 반영했을 때 도달 가능 점수",
  });
  if (r.benchmark_meta?.source) {
    items.push({
      label: "기준 출처",
      value: r.benchmark_meta.source,
      basis: r.benchmark_meta.version ? `버전 v${r.benchmark_meta.version}` : "GRESB 벤치마크",
    });
  }
  return items;
}

interface FormData {
  building_type: string;
  energy_kwh_per_sqm: string;
  ghg_kg_per_sqm: string;
  water_l_per_sqm: string;
  has_esg_policy: boolean;
  green_cert_level: string;
  waste_recycling_pct: string;
  renewable_energy_pct: string;
  floor_area_sqm: string;
}

const INITIAL_FORM: FormData = {
  building_type: "apartment",
  energy_kwh_per_sqm: "",
  ghg_kg_per_sqm: "",
  water_l_per_sqm: "",
  has_esg_policy: false,
  green_cert_level: "none",
  waste_recycling_pct: "0",
  renewable_energy_pct: "0",
  floor_area_sqm: "1000",
};

const GRADE_COLORS: Record<string, string> = {
  A: "text-green-600",
  B: "text-blue-600",
  C: "text-yellow-600",
  D: "text-red-600",
};

const GRADE_BG: Record<string, string> = {
  A: "stroke-green-500",
  B: "stroke-blue-500",
  C: "stroke-yellow-500",
  D: "stroke-red-500",
};

const COST_LABELS: Record<string, { text: string; color: string }> = {
  low: { text: "저비용", color: "bg-green-100 text-green-700" },
  medium: { text: "중간", color: "bg-yellow-100 text-yellow-700" },
  high: { text: "고비용", color: "bg-red-100 text-red-700" },
};

/* ── Sub-Components ── */

function CircularGauge({ score, maxScore, grade }: { score: number; maxScore: number; grade: string }) {
  const pct = (score / maxScore) * 100;
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - pct / 100);

  return (
    <div className="relative flex items-center justify-center">
      <svg width="140" height="140" viewBox="0 0 140 140">
        <circle
          cx="70" cy="70" r={radius}
          fill="none" stroke="#e5e7eb" strokeWidth="10"
        />
        <circle
          cx="70" cy="70" r={radius}
          fill="none" strokeWidth="10" strokeLinecap="round"
          className={GRADE_BG[grade] || "stroke-gray-400"}
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          transform="rotate(-90 70 70)"
          style={{ transition: "stroke-dashoffset 0.8s ease" }}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className={`text-3xl font-bold ${GRADE_COLORS[grade] || "text-gray-600"}`}>
          {grade}
        </span>
        <span className="text-sm font-medium text-gray-600">{score}/{maxScore}</span>
      </div>
    </div>
  );
}

function ComponentBar({ label, score, max }: { label: string; score: number; max: number }) {
  const pct = max > 0 ? (score / max) * 100 : 0;
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="font-medium text-gray-700">{label}</span>
        <span className="text-gray-500">{score}/{max}</span>
      </div>
      <div className="h-2 w-full rounded-full bg-gray-200">
        <div
          className="h-2 rounded-full bg-blue-500 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function BenchmarkBadge({ label, value, benchmark, rating }: {
  label: string; value: number; benchmark: number; rating: string;
}) {
  const ratingColors: Record<string, string> = {
    "우수": "bg-green-100 text-green-700 border-green-200",
    "보통": "bg-yellow-100 text-yellow-700 border-yellow-200",
    "개선필요": "bg-red-100 text-red-700 border-red-200",
  };
  return (
    <div className={`rounded-lg border p-2 ${ratingColors[rating] || "border-gray-200 bg-gray-50"}`}>
      <p className="text-[10px] font-medium uppercase">{label}</p>
      <p className="text-sm font-semibold">{value.toFixed(1)}</p>
      <p className="text-[10px]">벤치마크: {benchmark} | {rating}</p>
    </div>
  );
}

/* ── Main Component ── */

export default function GresbScoreCard() {
  const [form, setForm] = useState<FormData>(INITIAL_FORM);
  const [result, setResult] = useState<GresbResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const esgData = useProjectContextStore((s) => s.esgData);
  const designData = useProjectContextStore((s) => s.designData);
  const addAnalysisResult = useProjectContextStore((s) => s.addAnalysisResult);

  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  const updateField = <K extends keyof FormData>(key: K, value: FormData[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const loadFromEsg = () => {
    if (esgData) {
      if (esgData.totalCarbonPerSqm) {
        updateField("ghg_kg_per_sqm", String(esgData.totalCarbonPerSqm));
      }
    }
    if (designData) {
      if (designData.totalGfaSqm) {
        updateField("floor_area_sqm", String(designData.totalGfaSqm));
      }
      if (designData.buildingType) {
        updateField("building_type", designData.buildingType);
      }
    }
  };

  // 백엔드 GRESB 산식 단일화: /api/v1/gresb/score 호출(프론트 자체 산식 제거).
  const calculate = async () => {
    setLoading(true);
    setError("");
    try {
      const toNum = (v: string): number | null =>
        v.trim() === "" ? null : Number(v);

      const res = await apiClient.post<GresbResult>("/gresb/score", {
        useMock: false,
        body: {
          building_type: form.building_type,
          energy_kwh_per_sqm: toNum(form.energy_kwh_per_sqm),
          ghg_kg_per_sqm: toNum(form.ghg_kg_per_sqm),
          water_l_per_sqm: toNum(form.water_l_per_sqm),
          has_esg_policy: form.has_esg_policy,
          has_green_cert: form.green_cert_level !== "none",
          green_cert_level: form.green_cert_level,
          waste_recycling_pct: Number(form.waste_recycling_pct) || 0,
          renewable_energy_pct: Number(form.renewable_energy_pct) || 0,
          lca_total_carbon_kg: esgData?.embodiedCarbonKg ?? null,
          floor_area_sqm: Number(form.floor_area_sqm) || 1000,
        },
      });
      setResult(res);

      addAnalysisResult({
        module: "gresb",
        completedAt: new Date().toISOString(),
        summary: {
          total_score: res.total_score,
          grade: res.grade,
          grade_label: res.grade_label,
          potential_score: res.potential_score,
        },
      });
    } catch (e) {
      if (e instanceof ApiClientError && (e.status === 401 || e.status === 403)) {
        setError("GRESB 점수 산출에는 로그인이 필요합니다.");
      } else if (e instanceof Error) {
        setError(e.message);
      } else {
        setError("GRESB 점수 산출 요청에 실패했습니다.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="w-full">
      <CardContent className="space-y-6 p-5">
        {/* Title */}
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold text-gray-900">GRESB ESG 스코어링</h3>
            <p className="text-xs text-gray-500">GRESB 2025 기준 ESG 점수 예측 · 백엔드 산식</p>
          </div>
          <Button variant="secondary" size="sm" onClick={loadFromEsg} className="text-xs">
            ESG 분석에서 자동 입력
          </Button>
        </div>

        {/* Input Form */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {/* Building Type */}
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">건물 유형</label>
            <select
              value={form.building_type}
              onChange={(e) => updateField("building_type", e.target.value)}
              className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
            >
              <option value="apartment">아파트</option>
              <option value="office">오피스</option>
              <option value="commercial">상업시설</option>
            </select>
          </div>

          {/* Energy */}
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">에너지 강도 (kWh/m&sup2;)</label>
            <input
              type="number"
              value={form.energy_kwh_per_sqm}
              onChange={(e) => updateField("energy_kwh_per_sqm", e.target.value)}
              placeholder="예: 130"
              className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
            />
          </div>

          {/* GHG */}
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">온실가스 (kgCO2/m&sup2;)</label>
            <input
              type="number"
              value={form.ghg_kg_per_sqm}
              onChange={(e) => updateField("ghg_kg_per_sqm", e.target.value)}
              placeholder="예: 62"
              className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
            />
          </div>

          {/* Water */}
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">용수 사용 (L/m&sup2;)</label>
            <input
              type="number"
              value={form.water_l_per_sqm}
              onChange={(e) => updateField("water_l_per_sqm", e.target.value)}
              placeholder="예: 500"
              className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
            />
          </div>

          {/* Waste Recycling */}
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">폐기물 재활용률 (%)</label>
            <input
              type="number"
              value={form.waste_recycling_pct}
              onChange={(e) => updateField("waste_recycling_pct", e.target.value)}
              className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
            />
          </div>

          {/* Renewable Energy */}
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">재생에너지 비율 (%)</label>
            <input
              type="number"
              value={form.renewable_energy_pct}
              onChange={(e) => updateField("renewable_energy_pct", e.target.value)}
              className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
            />
          </div>

          {/* Green Cert Level */}
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">녹색건축 인증</label>
            <select
              value={form.green_cert_level}
              onChange={(e) => updateField("green_cert_level", e.target.value)}
              className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
            >
              <option value="none">미취득</option>
              <option value="basic">일반</option>
              <option value="good">우수</option>
              <option value="excellent">최우수</option>
            </select>
          </div>

          {/* ESG Policy */}
          <div className="flex items-end gap-2 pb-1">
            <label className="flex items-center gap-2 text-xs font-medium text-gray-600">
              <input
                type="checkbox"
                checked={form.has_esg_policy}
                onChange={(e) => updateField("has_esg_policy", e.target.checked)}
                className="rounded"
              />
              ESG 정책 수립 여부
            </label>
          </div>

          {/* Floor Area */}
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">연면적 (m&sup2;)</label>
            <NumberInput
              allowDecimal
              value={form.floor_area_sqm === "" ? null : Number(form.floor_area_sqm)}
              onChange={(n) => updateField("floor_area_sqm", n != null ? String(n) : "")}
              className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
            />
          </div>
        </div>

        <Button onClick={calculate} disabled={loading || !canUseLiveApi} className="w-full">
          {loading ? "계산 중..." : "GRESB 점수 계산"}
        </Button>

        {!canUseLiveApi && (
          <p className="text-center text-xs text-gray-500">
            GRESB 점수 산출에는 로그인이 필요합니다.
          </p>
        )}
        {error && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-700">
            {error}
          </div>
        )}

        {/* ── Result Display ── */}
        {result && (
          <div className="space-y-5 border-t pt-5">
            {/* Gauge + Grade */}
            <div className="flex items-center gap-6">
              <CircularGauge
                score={result.total_score}
                maxScore={result.max_score}
                grade={result.grade}
              />
              <div>
                <p className="text-lg font-bold text-gray-900">
                  {result.grade_label}
                </p>
                <p className="text-xs text-gray-500">
                  벤치마크: {result.benchmark_type} | 잠재 점수: {result.potential_score}점
                </p>
                {result.benchmark_meta?.source && (
                  <p className="text-[10px] text-gray-400">
                    기준 출처: {result.benchmark_meta.source}
                    {result.benchmark_meta.version
                      ? ` (v${result.benchmark_meta.version})`
                      : ""}
                  </p>
                )}
              </div>
            </div>

            {/* Component Bars */}
            <div className="space-y-3">
              <ComponentBar
                label="Management (경영)"
                score={result.components.management.score}
                max={result.components.management.max}
              />
              <ComponentBar
                label="Performance (성과)"
                score={result.components.performance.score}
                max={result.components.performance.max}
              />
              <ComponentBar
                label="Development (개발)"
                score={result.components.development.score}
                max={result.components.development.max}
              />
            </div>

            {/* Benchmark Comparison */}
            {(result.components.energy || result.components.ghg) && (
              <div className="grid grid-cols-2 gap-2">
                {result.components.energy && (
                  <BenchmarkBadge
                    label="에너지"
                    value={result.components.energy.value}
                    benchmark={result.components.energy.benchmark}
                    rating={result.components.energy.rating}
                  />
                )}
                {result.components.ghg && (
                  <BenchmarkBadge
                    label="온실가스"
                    value={result.components.ghg.value}
                    benchmark={result.components.ghg.benchmark}
                    rating={result.components.ghg.rating}
                  />
                )}
              </div>
            )}

            {/* Recommendations */}
            {(result.recommendations?.length ?? 0) > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-semibold text-gray-700">개선 권고사항</p>
                {(result.recommendations ?? []).map((rec, i) => {
                  const cost = COST_LABELS[rec.cost_grade] || COST_LABELS.medium;
                  return (
                    <div
                      key={i}
                      className="flex items-start gap-3 rounded-lg border border-gray-100 bg-gray-50 p-3"
                    >
                      <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-blue-100 text-[10px] font-bold text-blue-700">
                        {rec.priority}
                      </span>
                      <div className="flex-1">
                        <p className="text-xs font-medium text-gray-800">{rec.action}</p>
                        <div className="mt-1 flex items-center gap-2">
                          <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-medium text-blue-700">
                            +{rec.potential_gain}점
                          </span>
                          <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${cost.color}`}>
                            {cost.text}
                          </span>
                          <span className="text-[10px] text-gray-400">{rec.area}</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* 산출 근거(EvidencePanel) — 구성점수·가중치·벤치마크로 트레이스 구성.
                ★법령 URL은 백엔드 get_legal_refs 출력만(프론트 URL 조립 금지) — 미반환 시 basis 텍스트만. */}
            <EvidencePanel items={buildGresbEvidence(result)} title="GRESB 점수 산출 근거" />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
