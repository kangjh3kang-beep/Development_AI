"use client";

import { useState, useMemo } from "react";
import { Card, CardContent, Button } from "@propai/ui";
import { apiClient } from "@/lib/api-client";
import { formatCurrencyCompact } from "@/lib/formatters";

interface MaterialBreakdown {
  material: string;
  quantity_kg: number;
  epd_kgco2e_per_kg: number;
  carbon_footprint_kgco2e: number;
  category: string;
}

interface CarbonResult {
  total_carbon_footprint_kgco2e: number;
  materials_assessed: number;
  breakdown: MaterialBreakdown[];
  standard: string;
  data_source: string;
}

interface Alternative {
  alternative_name: string;
  epd_kgco2e_per_kg: number;
  alt_carbon_footprint_kgco2e: number;
  carbon_reduction_pct: number;
}

interface AlternativesResult {
  original_material: string;
  original_carbon_kgco2e: number;
  alternatives: Alternative[];
}

const MATERIAL_PRESETS = [
  { name: "보통 포틀랜드 시멘트", quantity_kg: 50000 },
  { name: "철근_SD400", quantity_kg: 30000 },
  { name: "일반 콘크리트 (C25)", quantity_kg: 200000 },
  { name: "EPS단열재", quantity_kg: 5000 },
  { name: "삼중유리", quantity_kg: 8000 },
  { name: "구조용강재_H형강", quantity_kg: 15000 },
];

type Labels = {
  heroTitle: string;
  heroDesc: string;
  analysisTitle: string;
  materialLabel: string;
  quantityLabel: string;
  addBtn: string;
  calculateBtn: string;
  calculating: string;
  resultTitle: string;
  totalLabel: string;
  materialsLabel: string;
  standardLabel: string;
  breakdownTitle: string;
  alternativeTitle: string;
  alternativeBtn: string;
  reductionLabel: string;
  scopeTitle: string;
  scope1: string;
  scope2: string;
  scope3: string;
  presetBtn: string;
  removeBtn: string;
};

const DEFAULT_LABELS: Labels = {
  heroTitle: "건축자재 탄소발자국 분석",
  heroDesc: "ISO 21930 기반 EPD 한국 데이터베이스를 활용한 건축자재 탄소배출량 분석 및 저탄소 대안 추천",
  analysisTitle: "자재 입력",
  materialLabel: "자재명",
  quantityLabel: "수량 (kg)",
  addBtn: "자재 추가",
  calculateBtn: "탄소발자국 분석",
  calculating: "분석 중...",
  resultTitle: "분석 결과",
  totalLabel: "총 탄소발자국",
  materialsLabel: "분석 자재 수",
  standardLabel: "적용 기준",
  breakdownTitle: "자재별 탄소배출 내역",
  alternativeTitle: "저탄소 대안 추천",
  alternativeBtn: "대안 조회",
  reductionLabel: "절감률",
  scopeTitle: "Scope별 배출 구성",
  scope1: "Scope 1 (직접 배출)",
  scope2: "Scope 2 (에너지 간접)",
  scope3: "Scope 3 (기타 간접)",
  presetBtn: "샘플 데이터 불러오기",
  removeBtn: "삭제",
};

export function CarbonEmissionsWorkspaceClient({
  dictionary,
  locale,
}: {
  dictionary: Record<string, string>;
  locale: string;
}) {
  const t: Labels = { ...DEFAULT_LABELS, ...dictionary };

  const [materials, setMaterials] = useState<{ name: string; quantity_kg: number }[]>([]);
  const [newName, setNewName] = useState("");
  const [newQty, setNewQty] = useState("");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [result, setResult] = useState<CarbonResult | null>(null);
  const [alternatives, setAlternatives] = useState<Record<string, AlternativesResult>>({});

  const addMaterial = () => {
    if (!newName || !newQty) return;
    setMaterials((prev) => [...prev, { name: newName, quantity_kg: Number(newQty) }]);
    setNewName("");
    setNewQty("");
  };

  const loadPresets = () => {
    setMaterials(MATERIAL_PRESETS);
  };

  const removeMaterial = (idx: number) => {
    setMaterials((prev) => prev.filter((_, i) => i !== idx));
  };

  const runAnalysis = async () => {
    if (materials.length === 0) return;
    setIsAnalyzing(true);
    try {
      const res = await apiClient.post<CarbonResult>("/esg/epd/carbon-footprint", {
        body: { material_list: materials },
      });
      if (res) setResult(res);
    } catch (err) {
      console.error("Carbon footprint analysis failed", err);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const fetchAlternative = async (materialName: string, quantityKg: number) => {
    try {
      const res = await apiClient.post<AlternativesResult>(
        `/esg/epd/low-carbon-alternatives?material_name=${encodeURIComponent(materialName)}&quantity_kg=${quantityKg}`,
        {},
      );
      if (res) {
        setAlternatives((prev) => ({ ...prev, [materialName]: res }));
      }
    } catch (err) {
      console.error("Failed to fetch alternatives", err);
    }
  };

  // Scope 배출 구성 (건축자재는 Scope 3가 대부분)
  const scopeData = useMemo(() => {
    if (!result) return null;
    const total = result.total_carbon_footprint_kgco2e;
    return {
      scope1: Math.round(total * 0.05),
      scope2: Math.round(total * 0.15),
      scope3: Math.round(total * 0.80),
    };
  }, [result]);

  const maxBreakdownCarbon = useMemo(() => {
    if (!result) return 1;
    return Math.max(...result.breakdown.map((b) => Math.abs(b.carbon_footprint_kgco2e)), 1);
  }, [result]);

  return (
    <div className="space-y-8">
      {/* Hero */}
      <div className="rounded-[2.5rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-10 shadow-[var(--shadow-xl)]">
        <div className="flex items-center gap-3 mb-4">
          <span className="flex h-3 w-3 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-[10px] font-black uppercase tracking-[0.2em] text-emerald-600">
            EPD Carbon · ISO 21930
          </span>
          <span className="rounded-lg bg-[var(--surface-soft)] px-3 py-1 text-[10px] font-bold text-[var(--text-hint)] uppercase">
            {locale}
          </span>
        </div>
        <h2 className="text-3xl font-[1000] tracking-tighter text-[var(--text-primary)] lg:text-4xl">
          {t.heroTitle}
        </h2>
        <p className="mt-2 max-w-3xl text-base font-medium text-[var(--text-secondary)] italic leading-relaxed">
          {t.heroDesc}
        </p>
      </div>

      {/* Input Section */}
      <Card className="rounded-[2rem] border-[var(--line)] shadow-sm">
        <CardContent className="p-8 space-y-6">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-black uppercase tracking-[0.3em] text-[var(--text-hint)]">
              {t.analysisTitle}
            </h3>
            <Button
              variant="secondary"
              size="sm"
              onClick={loadPresets}
              className="text-xs"
            >
              {t.presetBtn}
            </Button>
          </div>

          {/* Add Material */}
          <div className="flex gap-3 items-end">
            <div className="flex-1">
              <label className="text-xs font-bold text-[var(--text-secondary)] mb-1 block">{t.materialLabel}</label>
              <select
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2.5 text-sm font-medium"
              >
                <option value="">선택...</option>
                {[
                  "보통 포틀랜드 시멘트",
                  "철근_SD400",
                  "일반 콘크리트 (C25)",
                  "고강도 콘크리트 (C35)",
                  "EPS단열재",
                  "삼중유리",
                  "로이유리",
                  "구조용강재_H형강",
                  "CLT 구조목",
                  "OSB 합판",
                  "단열재 (미네랄울)",
                  "저탄소 콘크리트 (슬래그 30%)",
                  "재활용 철근 (EAF)",
                ].map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
            <div className="w-40">
              <label className="text-xs font-bold text-[var(--text-secondary)] mb-1 block">{t.quantityLabel}</label>
              <input
                type="number"
                value={newQty}
                onChange={(e) => setNewQty(e.target.value)}
                placeholder="10000"
                className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2.5 text-sm font-medium"
              />
            </div>
            <Button onClick={addMaterial} disabled={!newName || !newQty} size="sm">
              {t.addBtn}
            </Button>
          </div>

          {/* Material List */}
          {materials.length > 0 && (
            <div className="space-y-2">
              {materials.map((m, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-5 py-3"
                >
                  <div className="flex items-center gap-4">
                    <span className="h-2 w-2 rounded-full bg-emerald-500" />
                    <span className="text-sm font-bold text-[var(--text-primary)]">{m.name}</span>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className="text-sm font-medium text-[var(--text-secondary)]">
                      {m.quantity_kg.toLocaleString()} kg
                    </span>
                    <button
                      onClick={() => removeMaterial(i)}
                      className="text-[10px] font-bold text-rose-500 hover:text-rose-600 uppercase"
                    >
                      {t.removeBtn}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <Button
            onClick={runAnalysis}
            disabled={isAnalyzing || materials.length === 0}
            className="w-full"
          >
            {isAnalyzing ? t.calculating : t.calculateBtn}
          </Button>
        </CardContent>
      </Card>

      {/* Results */}
      {result && (
        <>
          {/* Summary Cards */}
          <div className="grid gap-4 md:grid-cols-3">
            <div className="rounded-[2rem] border border-emerald-500/20 bg-emerald-500/5 p-8">
              <p className="text-[10px] font-black uppercase tracking-[0.2em] text-emerald-600">{t.totalLabel}</p>
              <p className="mt-3 text-4xl font-[1000] tracking-tighter text-[var(--text-primary)]">
                {formatCurrencyCompact(result.total_carbon_footprint_kgco2e)}
              </p>
              <p className="mt-1 text-xs font-bold text-[var(--text-tertiary)]">kgCO₂eq</p>
            </div>
            <div className="rounded-[2rem] border border-[var(--line)] bg-[var(--surface)] p-8">
              <p className="text-[10px] font-black uppercase tracking-[0.2em] text-[var(--text-hint)]">{t.materialsLabel}</p>
              <p className="mt-3 text-4xl font-[1000] tracking-tighter text-[var(--text-primary)]">
                {result.materials_assessed}
              </p>
              <p className="mt-1 text-xs font-bold text-[var(--text-tertiary)]">items analyzed</p>
            </div>
            <div className="rounded-[2rem] border border-[var(--line)] bg-[var(--surface)] p-8">
              <p className="text-[10px] font-black uppercase tracking-[0.2em] text-[var(--text-hint)]">{t.standardLabel}</p>
              <p className="mt-3 text-xl font-[1000] tracking-tighter text-[var(--text-primary)]">
                {result.standard}
              </p>
              <p className="mt-1 text-xs font-bold text-[var(--text-tertiary)]">{result.data_source}</p>
            </div>
          </div>

          {/* Scope Breakdown */}
          {scopeData && (
            <Card className="rounded-[2rem] border-[var(--line)] shadow-sm">
              <CardContent className="p-8 space-y-6">
                <h3 className="text-xs font-black uppercase tracking-[0.3em] text-[var(--text-hint)]">{t.scopeTitle}</h3>
                <div className="space-y-4">
                  {[
                    { label: t.scope1, value: scopeData.scope1, pct: 5, color: "bg-amber-500" },
                    { label: t.scope2, value: scopeData.scope2, pct: 15, color: "bg-blue-500" },
                    { label: t.scope3, value: scopeData.scope3, pct: 80, color: "bg-emerald-500" },
                  ].map((s) => (
                    <div key={s.label} className="space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-[var(--text-secondary)]">{s.label}</span>
                        <span className="text-xs font-black text-[var(--text-primary)]">
                          {s.value.toLocaleString()} kgCO₂eq ({s.pct}%)
                        </span>
                      </div>
                      <div className="h-2 w-full overflow-hidden rounded-full bg-[var(--surface-soft)]">
                        <div
                          className={`h-full ${s.color} transition-all duration-700`}
                          style={{ width: `${s.pct}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Breakdown Table */}
          <Card className="rounded-[2rem] border-[var(--line)] shadow-sm">
            <CardContent className="p-8 space-y-6">
              <h3 className="text-xs font-black uppercase tracking-[0.3em] text-[var(--text-hint)]">{t.breakdownTitle}</h3>
              <div className="space-y-3">
                {result.breakdown.map((b) => {
                  const isNeg = b.carbon_footprint_kgco2e < 0;
                  const pct = Math.abs(b.carbon_footprint_kgco2e) / maxBreakdownCarbon * 100;
                  return (
                    <div key={b.material} className="space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <span className={`inline-block rounded-lg px-2 py-0.5 text-[9px] font-black uppercase ${
                            isNeg ? "bg-blue-100 text-blue-700" : "bg-rose-100 text-rose-700"
                          }`}>
                            {b.category}
                          </span>
                          <span className="text-sm font-bold text-[var(--text-primary)]">{b.material}</span>
                        </div>
                        <div className="flex items-center gap-4">
                          <span className="text-xs font-medium text-[var(--text-tertiary)]">
                            {b.quantity_kg.toLocaleString()} kg × {b.epd_kgco2e_per_kg} kgCO₂e/kg
                          </span>
                          <span className={`text-sm font-black ${isNeg ? "text-blue-600" : "text-rose-600"}`}>
                            {isNeg ? "" : "+"}{b.carbon_footprint_kgco2e.toLocaleString()} kgCO₂eq
                          </span>
                          <button
                            onClick={() => fetchAlternative(b.material, b.quantity_kg)}
                            className="text-[10px] font-bold text-indigo-600 hover:underline uppercase"
                          >
                            {t.alternativeBtn}
                          </button>
                        </div>
                      </div>
                      <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--surface-soft)]">
                        <div
                          className={`h-full transition-all duration-500 ${isNeg ? "bg-blue-500" : "bg-rose-400"}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      {/* Alternatives */}
                      {alternatives[b.material] && (
                        <div className="ml-8 mt-2 space-y-2">
                          <p className="text-[10px] font-black uppercase tracking-widest text-emerald-600">
                            {t.alternativeTitle}
                          </p>
                          {alternatives[b.material].alternatives.map((alt) => (
                            <div
                              key={alt.alternative_name}
                              className="flex items-center justify-between rounded-xl bg-emerald-50 dark:bg-emerald-500/5 px-4 py-2 border border-emerald-200 dark:border-emerald-500/10"
                            >
                              <span className="text-xs font-bold text-emerald-800 dark:text-emerald-300">
                                {alt.alternative_name}
                              </span>
                              <div className="flex items-center gap-4">
                                <span className="text-xs text-emerald-600">
                                  {alt.alt_carbon_footprint_kgco2e.toLocaleString()} kgCO₂eq
                                </span>
                                <span className="rounded-lg bg-emerald-600 px-2 py-0.5 text-[10px] font-black text-white">
                                  -{alt.carbon_reduction_pct}% {t.reductionLabel}
                                </span>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
