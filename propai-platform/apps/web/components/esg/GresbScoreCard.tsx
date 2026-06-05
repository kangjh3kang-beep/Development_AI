"use client";

import { useState } from "react";
import { Button, Card, CardContent } from "@propai/ui";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { NumberInput } from "@/components/common/NumberInput";

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
  recommendations: Recommendation[];
  potential_score: number;
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

  const esgData = useProjectContextStore((s) => s.esgData);
  const designData = useProjectContextStore((s) => s.designData);
  const addAnalysisResult = useProjectContextStore((s) => s.addAnalysisResult);

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

  const calculate = async () => {
    setLoading(true);
    try {
      const energy = form.energy_kwh_per_sqm ? parseFloat(form.energy_kwh_per_sqm) : 130;
      const ghg = form.ghg_kg_per_sqm ? parseFloat(form.ghg_kg_per_sqm) : 62;
      const water = form.water_l_per_sqm ? parseFloat(form.water_l_per_sqm) : 500;
      const waste = parseFloat(form.waste_recycling_pct) || 0;
      const renewable = parseFloat(form.renewable_energy_pct) || 0;
      const certLevel = form.green_cert_level;

      // 로컬 GRESB 스코어링 계산
      const mgmt = Math.min(30, (form.has_esg_policy ? 15 : 0) + (certLevel !== "none" ? 10 : 0) + 5);
      const energyBench = 130; // kWh/m² benchmark
      const ghgBench = 62;
      const energyScore = Math.max(0, Math.min(20, 20 * (1 - (energy - energyBench * 0.5) / energyBench)));
      const ghgScore = Math.max(0, Math.min(15, 15 * (1 - (ghg - ghgBench * 0.5) / ghgBench)));
      const wasteScore = Math.min(10, waste / 10);
      const renewableScore = Math.min(10, renewable / 10);
      const waterScore = Math.max(0, Math.min(5, 5 * (1 - (water - 250) / 500)));
      const perf = Math.round(energyScore + ghgScore + wasteScore + renewableScore + waterScore);
      const dev = Math.min(10, (certLevel === "excellent" ? 10 : certLevel === "good" ? 7 : certLevel === "basic" ? 4 : 0));
      const total = Math.min(100, mgmt + perf + dev);
      const grade = total >= 75 ? "A" : total >= 55 ? "B" : total >= 35 ? "C" : "D";
      const gradeLabel = grade === "A" ? "Green Star" : grade === "B" ? "우수" : grade === "C" ? "보통" : "개선필요";

      const energyRating = energy <= energyBench * 0.7 ? "우수" : energy <= energyBench ? "보통" : "개선필요";
      const ghgRating = ghg <= ghgBench * 0.7 ? "우수" : ghg <= ghgBench ? "보통" : "개선필요";

      const recommendations: Recommendation[] = [];
      if (renewable < 20) recommendations.push({ area: "에너지", action: "태양광 패널 설치로 재생에너지 비율 20% 달성", potential_gain: 5, cost_grade: "medium", priority: 1 });
      if (!form.has_esg_policy) recommendations.push({ area: "경영", action: "ESG 정책 수립 및 공시", potential_gain: 15, cost_grade: "low", priority: 2 });
      if (certLevel === "none") recommendations.push({ area: "개발", action: "녹색건축 인증(G-SEED) 취득", potential_gain: 10, cost_grade: "high", priority: 3 });
      if (waste < 50) recommendations.push({ area: "성과", action: "폐기물 재활용률 50% 이상 달성", potential_gain: 5, cost_grade: "low", priority: 4 });

      const res: GresbResult = {
        total_score: total, max_score: 100, grade, grade_label: gradeLabel,
        components: {
          management: { score: mgmt, max: 30 },
          performance: { score: perf, max: 60 },
          development: { score: dev, max: 10 },
          energy: { value: energy, benchmark: energyBench, rating: energyRating },
          ghg: { value: ghg, benchmark: ghgBench, rating: ghgRating },
        },
        benchmark_type: form.building_type === "apartment" ? "아시아-주거" : "아시아-상업",
        recommendations,
        potential_score: Math.min(100, total + recommendations.reduce((s, r) => s + r.potential_gain, 0)),
      };
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
    } catch {
      // Error handled silently; user sees no result
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
            <p className="text-xs text-gray-500">GRESB 2025 기준 ESG 점수 예측</p>
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

        <Button onClick={calculate} disabled={loading} className="w-full">
          {loading ? "계산 중..." : "GRESB 점수 계산"}
        </Button>

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
            {result.recommendations.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-semibold text-gray-700">개선 권고사항</p>
                {result.recommendations.map((rec, i) => {
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
          </div>
        )}
      </CardContent>
    </Card>
  );
}
