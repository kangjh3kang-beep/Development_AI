"use client";

import { useCallback, useRef, useState } from "react";
import { Button, Card, CardContent, Input } from "@propai/ui";
import { useFeasibilityV2Store } from "@/store/use-feasibility-v2-store";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useCadStore } from "@/store/use-cad-store";
import { motion } from "framer-motion";
import { NumberInput as CommaInput } from "@/components/common/NumberInput";

const LAND_CATEGORIES = [
  { value: "land", label: "대지" },
  { value: "farmland", label: "농지 (전/답)" },
  { value: "forest", label: "임야" },
];

const BUILDING_TYPES = [
  { value: "apartment", label: "아파트" },
  { value: "officetel", label: "오피스텔" },
  { value: "office", label: "오피스" },
  { value: "commercial", label: "상가" },
  { value: "mixed", label: "복합" },
];

function NumberInput({
  label,
  value,
  unit,
  onChange,
  comma = false,
  decimal = false,
}: {
  label: string;
  value: number | undefined;
  unit?: string;
  onChange: (v: number) => void;
  comma?: boolean;
  decimal?: boolean;
}) {
  return (
    <label className="grid gap-1.5 text-sm">
      <span className="font-medium text-slate-700 dark:text-slate-200">{label}</span>
      <div className="relative">
        {comma ? (
          <CommaInput
            allowDecimal={decimal}
            value={value ?? null}
            onChange={(n) => onChange(n ?? 0)}
            className="pr-12 flex h-11 w-full rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
          />
        ) : (
          <Input
            type="number"
            value={value ?? 0}
            onChange={(e) => onChange(Number(e.target.value))}
            className="pr-12"
          />
        )}
        {unit && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-400">
            {unit}
          </span>
        )}
      </div>
    </label>
  );
}

export function ModuleInputForm() {
  const { input, setInput, calculate, isCalculating, selectedModule, commitVersion } =
    useFeasibilityV2Store();
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);

  // 자동 산정값 (API에서 추천된 초기값) — 사용자가 수정하면 배지 표시
  const [autoValues] = useState<Partial<Record<string, number>>>({});
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 사용자 수정 시 자동 히스토리 저장 (디바운스 3초)
  const handleInputChange = useCallback((patch: Partial<typeof input>) => {
    setInput(patch);
    // 3초 후 자동 커밋
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      const changedKeys = Object.keys(patch).join(", ");
      commitVersion(`사용자 수정: ${changedKeys}`).catch(() => {});
    }, 3000);
  }, [setInput, commitVersion]);

  // 부지분석 데이터에서 자동 반영
  const loadFromSiteAnalysis = useCallback(() => {
    if (!siteAnalysis) return;
    const patch: Partial<typeof input> = {};
    if (siteAnalysis.landAreaSqm) patch.total_land_area_sqm = siteAnalysis.landAreaSqm;
    if (siteAnalysis.address) patch.sido_name = siteAnalysis.address.split(" ")[0] || "";
    if (siteAnalysis.officialPrices?.[0]?.pricePerSqm) {
      patch.official_price_per_sqm = siteAnalysis.officialPrices[0].pricePerSqm;
    }
    setInput(patch);
  }, [siteAnalysis, setInput]);

  const syncWithCAD = () => {
    const cadState = useCadStore.getState();
    // Simulate area calculation from polygons
    const floorArea = cadState.polygons.length * 450 * cadState.floorCount; // Rough estimate for demo
    if (floorArea > 0) {
      setInput({ 
        total_gfa_sqm: floorArea,
        total_households: Math.floor(floorArea / 85) // 85sqm per household
      });
      alert("CAD 설계 데이터가 동기화되었습니다: 연면적 " + floorArea.toLocaleString() + "m²");
    } else {
      alert("동기화할 CAD 설계 데이터(면적)가 존재하지 않습니다. Stage 4에서 도면을 작성해 주세요.");
    }
  };

  return (
    <Card className="rounded-[var(--radius-xl)] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900 overflow-hidden">
      <CardContent className="p-6">
         {/* Synergy Alert */}
         <motion.div 
           initial={{ opacity: 0, y: -10 }}
           animate={{ opacity: 1, y: 0 }}
           className="mb-6 rounded-2xl bg-blue-50 border border-blue-100 p-4 flex items-center justify-between"
         >
            <div className="flex items-center gap-3">
               <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-blue-600 text-white shadow-lg">
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="m12 3-1.912 5.813a2 2 0 0 0-1.275 1.275L3 12l5.813 1.912a2 2 0 0 0 1.275 1.275L12 21l-1.912-5.813a2 2 0 0 0-1.275-1.275L21 12l-5.813-1.912a2 2 0 0 0-1.275-1.275L12 3Z"/></svg>
               </div>
               <div>
                  <p className="text-xs font-black text-blue-600 uppercase tracking-widest">Cross-Stage Synergy</p>
                  <p className="text-[11px] font-bold text-blue-800">Stage 4(설계)의 CAD 데이터와 Stage 5(수지분석)가 논리적으로 연결되어 있습니다.</p>
               </div>
            </div>
            <Button variant={"outline" as any} size="sm" onClick={syncWithCAD} className="bg-white border-blue-200 text-blue-700 hover:bg-blue-50 font-black">
               CAD 설계 데이터 가져오기 (Sync)
            </Button>
         </motion.div>

        <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 dark:border-slate-800 pb-4">
          <h3 className="text-lg font-semibold text-[var(--text-primary)]">
            {selectedModule} 입력 항목
          </h3>
          <div className="flex gap-2">
            {siteAnalysis?.address && (
              <Button variant={"outline" as any} size="sm" onClick={loadFromSiteAnalysis} className="text-xs">
                부지분석 데이터 반영
              </Button>
            )}
            <Button onClick={() => calculate()}
              disabled={isCalculating || !((input.total_land_area_sqm ?? 0) > 0) || !((input.total_gfa_sqm ?? 0) > 0)}
              title={((input.total_land_area_sqm ?? 0) > 0) && ((input.total_gfa_sqm ?? 0) > 0) ? undefined : "대지면적·연면적을 입력하세요(부지분석 데이터 반영 가능)"}
              className="bg-[var(--accent-strong)] text-white px-6">
              {isCalculating ? "계산 중..." : "수지분석 실행"}
            </Button>
          </div>
        </div>
        {siteAnalysis?.address && (
          <p className="mb-3 text-xs text-emerald-500 flex items-center gap-1.5">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
            부지분석 연동: {siteAnalysis.address} ({siteAnalysis.zoneCode || ""})
          </p>
        )}

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {/* 기본 정보 */}
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium text-slate-700 dark:text-slate-200">프로젝트명</span>
            <Input
              value={input.project_name ?? ""}
              onChange={(e) => setInput({ project_name: e.target.value })}
              placeholder="예: 오산 내삼미동 프로젝트"
            />
          </label>

          <label className="grid gap-1.5 text-sm">
            <span className="font-medium text-slate-700 dark:text-slate-200">지목</span>
            <select
              value={input.land_category ?? "land"}
              onChange={(e) => setInput({ land_category: e.target.value })}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm outline-none transition focus:border-blue-400 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            >
              {LAND_CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
          </label>

          <label className="grid gap-1.5 text-sm">
            <span className="font-medium text-slate-700 dark:text-slate-200">건물유형</span>
            <select
              value={input.building_type ?? "apartment"}
              onChange={(e) => setInput({ building_type: e.target.value })}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm outline-none transition focus:border-blue-400 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            >
              {BUILDING_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </label>

          {/* 면적/규모 */}
          <NumberInput label="대지면적" value={input.total_land_area_sqm} unit="m²" comma decimal
            onChange={(v) => setInput({ total_land_area_sqm: v })} />
          <NumberInput label="연면적" value={input.total_gfa_sqm} unit="m²" comma decimal
            onChange={(v) => setInput({ total_gfa_sqm: v })} />
          <NumberInput label="총 세대수" value={input.total_households} unit="세대" comma
            onChange={(v) => setInput({ total_households: v })} />

          {/* 분양 (핵심 수정 항목 — 변경 시 자동 히스토리) */}
          <NumberInput label="평당 분양가" value={input.avg_sale_price_per_pyeong} unit="원/평" comma
            onChange={(v) => handleInputChange({ avg_sale_price_per_pyeong: v })} />
          <NumberInput label="평균 전용면적" value={input.avg_area_pyeong} unit="평"
            onChange={(v) => handleInputChange({ avg_area_pyeong: v })} />
          <NumberInput label="분양률" value={input.sale_ratio} unit="%"
            onChange={(v) => handleInputChange({ sale_ratio: v })} />

          {/* 토지비 (핵심 수정 항목) */}
          <NumberInput label="공시지가" value={input.official_price_per_sqm} unit="원/m²" comma
            onChange={(v) => handleInputChange({ official_price_per_sqm: v })} />
          <NumberInput label="시가반영배율" value={input.price_multiplier}
            onChange={(v) => handleInputChange({ price_multiplier: v })} />

          {/* 금융 (핵심 수정 항목) */}
          <NumberInput label="브릿지론" value={input.bridge_amount_won} unit="원" comma
            onChange={(v) => handleInputChange({ bridge_amount_won: v })} />
          <NumberInput label="본PF" value={input.pf_amount_won} unit="원" comma
            onChange={(v) => handleInputChange({ pf_amount_won: v })} />
          <NumberInput label="중도금대출" value={input.midpay_amount_won} unit="원" comma
            onChange={(v) => handleInputChange({ midpay_amount_won: v })} />

          {/* 지역 */}
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium text-slate-700 dark:text-slate-200">시/도</span>
            <Input
              value={input.sido_name ?? ""}
              onChange={(e) => setInput({ sido_name: e.target.value })}
              placeholder="예: 경기"
            />
          </label>
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium text-slate-700 dark:text-slate-200">시/군/구</span>
            <Input
              value={input.sigungu_name ?? ""}
              onChange={(e) => setInput({ sigungu_name: e.target.value })}
              placeholder="예: 오산시"
            />
          </label>

          {/* 기타 */}
          <NumberInput label="사업기간" value={input.project_months} unit="개월"
            onChange={(v) => setInput({ project_months: v })} />
          <NumberInput label="할인율" value={input.discount_rate}
            onChange={(v) => setInput({ discount_rate: v })} />
          <NumberInput label="자기자본" value={input.equity_won} unit="원" comma
            onChange={(v) => setInput({ equity_won: v })} />
        </div>
      </CardContent>
    </Card>
  );
}
