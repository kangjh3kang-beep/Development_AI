"use client";

import { useState, useMemo } from "react";
import { Card, CardContent, Button } from "@propai/ui";
import { formatCurrencyCompact } from "@/lib/formatters";
import { NumberInput } from "@/components/common/NumberInput";
import { apiClient } from "@/lib/api-client";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";

// ★자재 선택 목록 — 백엔드 EPD Korea Database(EPD_KOREA_DATABASE) 등록 키와 동일하게 맞춘다.
//   (목록 외 자재는 백엔드가 산출에서 제외하므로, 등록된 자재명만 노출해 누락을 막는다.)
//   주의: 여기에는 GWP(탄소계수) 같은 "값"을 절대 두지 않는다 — 값은 모두 백엔드 응답에서만 온다.
const MATERIAL_NAMES = [
  "보통 포틀랜드 시멘트",
  "고강도 콘크리트 (C35)",
  "일반 콘크리트 (C25)",
  "레미콘_35MPa",
  "철근_SD400",
  "철근 (SD500)",
  "구조용강재_H형강",
  "구조용 강재 (H형강)",
  "저탄소 콘크리트 (슬래그 30%)",
  "재활용 철근 (EAF)",
  "단열재 (미네랄울)",
  "단열재 (EPS)",
  "EPS단열재",
  "삼중유리",
  "로이유리",
  "CLT 구조목",
  "OSB 합판",
];

interface MaterialBreakdown {
  material: string;
  quantity_kg: number;
  epd_kgco2e_per_kg: number;
  carbon_footprint_kgco2e: number;
  category: string;
}

// 백엔드 /esg/epd/carbon-footprint 응답 계약(받는 값만 사용).
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

// 백엔드 /esg/epd/low-carbon-alternatives 응답 계약(받는 값만 사용).
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
  const [newQty, setNewQty] = useState<number | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [result, setResult] = useState<CarbonResult | null>(null);
  const [alternatives, setAlternatives] = useState<Record<string, AlternativesResult>>({});
  // 호출 실패/무자료 시 정직 표기용 메시지(가짜 데이터 생성 금지).
  const [error, setError] = useState<string | null>(null);
  // 대안 조회 중인 자재명(중복 클릭 방지·로딩 표시).
  const [altLoading, setAltLoading] = useState<string | null>(null);

  const addMaterial = () => {
    if (!newName || !newQty) return;
    setMaterials((prev) => [...prev, { name: newName, quantity_kg: newQty }]);
    setNewName("");
    setNewQty(null);
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
    setError(null);
    try {
      // ★실제 백엔드 호출 — EPD Korea Database 기반 탄소발자국 산출(클라이언트 하드코딩 GWP 제거).
      //   body = { material_list: [{ name, quantity_kg }] } (EPDRequest 계약).
      const payload = await apiClient.post<CarbonResult>("/esg/epd/carbon-footprint", {
        body: { material_list: materials.map((m) => ({ name: m.name, quantity_kg: m.quantity_kg })) },
        useMock: false,
        timeoutMs: 60000,
      });

      // 받는 값만 사용 + null 가드(가짜 기본값 주입 금지).
      const breakdown = Array.isArray(payload?.breakdown) ? payload.breakdown : [];
      if (breakdown.length === 0) {
        // 백엔드 EPD DB에 없는 자재만 입력된 경우 → 정직 표기(빈 결과).
        setResult(null);
        setError("입력하신 자재가 EPD 데이터베이스에 등록되어 있지 않아 탄소발자국을 산출할 수 없습니다. 등록된 자재명을 선택해 주세요.");
        return;
      }
      setResult({
        total_carbon_footprint_kgco2e: Number(payload.total_carbon_footprint_kgco2e ?? 0),
        materials_assessed: Number(payload.materials_assessed ?? breakdown.length),
        breakdown,
        standard: payload.standard ?? "ISO 21930:2017",
        data_source: payload.data_source ?? "EPD Korea Database",
      });
      // 새 분석 시작 시 이전 대안 결과 초기화(자재 변경과 불일치 방지).
      setAlternatives({});
    } catch (e) {
      // 호출 실패 → 정직 표기(가짜 데이터 생성 안 함).
      const msg = e instanceof Error ? e.message : "탄소발자국 분석 실패";
      setResult(null);
      setError(`탄소발자국 분석 중 오류가 발생했습니다(${msg}). 잠시 후 다시 시도해 주세요.`);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const fetchAlternative = async (materialName: string, quantityKg: number) => {
    if (altLoading) return;
    setAltLoading(materialName);
    try {
      // ★실제 백엔드 호출 — 동일 카테고리 저탄소 대안 추천(클라이언트 하드코딩 대안맵 제거).
      //   엔드포인트는 쿼리 파라미터(material_name, quantity_kg)로 받음.
      const qs = new URLSearchParams({
        material_name: materialName,
        quantity_kg: String(quantityKg),
      }).toString();
      const payload = await apiClient.post<AlternativesResult>(
        `/esg/epd/low-carbon-alternatives?${qs}`,
        { useMock: false, timeoutMs: 60000 },
      );
      const alts = Array.isArray(payload?.alternatives) ? payload.alternatives : [];
      setAlternatives((prev) => ({
        ...prev,
        [materialName]: {
          original_material: payload?.original_material ?? materialName,
          original_carbon_kgco2e: Number(payload?.original_carbon_kgco2e ?? 0),
          alternatives: alts,
        },
      }));
    } catch (e) {
      // 대안 조회 실패 → 빈 대안(가짜 추천 생성 안 함) + 메시지.
      const msg = e instanceof Error ? e.message : "대안 조회 실패";
      setAlternatives((prev) => ({
        ...prev,
        [materialName]: {
          original_material: materialName,
          original_carbon_kgco2e: 0,
          alternatives: [],
        },
      }));
      setError(`저탄소 대안 조회 중 오류가 발생했습니다(${msg}).`);
    } finally {
      setAltLoading(null);
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
    return Math.max(...(result.breakdown ?? []).map((b) => Math.abs(b.carbon_footprint_kgco2e)), 1);
  }, [result]);

  // 산출 근거(EvidencePanel) — 모든 항목이 실응답 실값에서 옴(가짜 0 금지).
  const evidence: EvidenceItem[] = useMemo(() => {
    if (!result) return [];
    return [
      {
        label: "총 탄소발자국",
        value: `${result.total_carbon_footprint_kgco2e.toLocaleString()} kgCO₂eq`,
        basis: "Σ(자재별 수량 × EPD 탄소계수)",
      },
      {
        label: "적용 기준",
        value: result.standard,
        basis: "건축자재 환경성적표지(EPD) 산정 표준",
      },
      {
        label: "데이터 출처",
        value: result.data_source,
        basis: `분석 자재 ${result.materials_assessed}종 · 백엔드 EPD DB 실값`,
      },
    ];
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
                {MATERIAL_NAMES.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
            <div className="w-40">
              <label className="text-xs font-bold text-[var(--text-secondary)] mb-1 block">{t.quantityLabel}</label>
              <NumberInput
                allowDecimal
                value={newQty}
                onChange={(n) => setNewQty(n)}
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

          {/* 오류·무자료 정직 표기 (가짜 데이터 대체 금지) */}
          {error && (
            <div className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
              {error}
            </div>
          )}
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

          {/* 산출 근거(공용 EvidencePanel) — 산식·출처 트레이스(실값만) */}
          <EvidencePanel title="산출 근거" items={evidence} defaultOpen={false} />

          {/* Scope Breakdown */}
          {scopeData && (
            <Card className="rounded-[2rem] border-[var(--line)] shadow-sm">
              <CardContent className="p-8 space-y-6">
                <h3 className="text-xs font-black uppercase tracking-[0.3em] text-[var(--text-hint)]">{t.scopeTitle}</h3>
                {/* ★정직 고지: EPD는 자재 내재탄소(A1~A3=대부분 Scope 3)를 측정한다. 아래 Scope 1/2/3 분해는
                    실측이 아니라 업계 통상 가정비율(5/15/80)로 나눈 '추정 구성'이다. 가짜 측정값으로 오인 방지. */}
                <p className="text-[11px] leading-snug text-amber-600">
                  ⚠ 추정 구성 — 업계 통상 가정비율(5/15/80)로 분해한 참고값입니다. EPD는 자재 내재탄소(대부분 Scope 3)를 측정하며, 정밀 Scope 분해는 운영단계 실측이 필요합니다.
                </p>
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
                {(result.breakdown ?? []).map((b) => {
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
                            disabled={altLoading === b.material}
                            className="text-[10px] font-bold text-indigo-600 hover:underline uppercase disabled:opacity-50"
                          >
                            {altLoading === b.material ? t.calculating : t.alternativeBtn}
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
                          {alternatives[b.material].alternatives.length === 0 ? (
                            // 대안 없음/조회 실패 → 정직 표기(가짜 추천 금지).
                            <p className="text-xs font-medium text-[var(--text-tertiary)]">
                              조회된 저탄소 대안이 없습니다.
                            </p>
                          ) : (
                            alternatives[b.material].alternatives.map((alt) => (
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
                            ))
                          )}
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
