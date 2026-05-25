"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Button, Card, CardContent, CardTitle, Input } from "@propai/ui";
import { apiClient } from "@/lib/api-client";

type TaxItem = {
  code: string;
  name: string;
  stage: string;
  amount_won: number;
};

type TaxResult = {
  grand_total_won: number;
  total_items_count: number;
  items: TaxItem[];
  stage_totals: Record<string, number>;
};

const STAGES = [
  { key: "all", label: "전체 항목" },
  { key: "acquisition", label: "취득 세무" },
  { key: "utility", label: "공사/보유" },
  { key: "sale", label: "분양/운영" },
  { key: "disposal", label: "양도/매각" },
];

function formatWon(value: number): string {
  if (Math.abs(value) >= 1e8) return `${(value / 1e8).toFixed(1)}억`;
  if (Math.abs(value) >= 1e4) return `${(value / 1e4).toFixed(0)}만`;
  return value.toLocaleString();
}

export function TaxCalculationDashboard() {
  const [activeStage, setActiveStage] = useState("all");
  const [result, setResult] = useState<TaxResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const [form, setForm] = useState({
    purchase_won: 50_000_000_000,
    land_category: "land",
    sido_name: "서울",
    sigungu_name: "강남구",
    total_households: 1000,
    total_sale_amount_won: 500_000_000_000,
    total_gfa_sqm: 100_000,
  });

  const handleCalculate = async () => {
    setIsLoading(true);
    try {
      const data = await apiClient.postV2<TaxResult>("/tax/calculate-all", {
        body: form as unknown as Record<string, unknown>,
      });
      setResult(data);
    } catch {
      /* 무시 */
    } finally {
      setIsLoading(false);
    }
  };

  const filteredItems = result?.items.filter(
    (item) => activeStage === "all" || item.stage === activeStage
  ) ?? [];

  return (
    <div className="grid gap-8">
      {/* Simulation Inputs */}
      <Card className="border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-xl)] overflow-hidden">
        <div className="bg-[var(--surface-soft)] p-6 border-b border-[var(--line)]">
           <CardTitle className="text-[12px] font-black uppercase tracking-[0.3em] text-[var(--text-primary)]">
             38종 부동산 개발 세무 시뮬레이션
           </CardTitle>
        </div>
        <CardContent className="p-8">
          <div className="grid gap-6 md:grid-cols-3 lg:grid-cols-4">
            {[
              { label: "총 매입 금액", type: "number", key: "purchase_won", unit: "원" },
              { label: "시도", type: "text", key: "sido_name" },
              { label: "시군구", type: "text", key: "sigungu_name" },
              { label: "총 세대수", type: "number", key: "total_households", unit: "세대" },
              { label: "예상 분양 총액", type: "number", key: "total_sale_amount_won", unit: "원" },
              { label: "전체 연면적", type: "number", key: "total_gfa_sqm", unit: "㎡" },
            ].map((input) => (
              <div key={input.key} className="space-y-2">
                <p className="text-[10px] font-black uppercase tracking-wider text-[var(--text-tertiary)]">{input.label}</p>
                <div className="relative">
                  <Input
                    type={input.type}
                    value={(form as any)[input.key]}
                    onChange={(e) => setForm((p) => ({ ...p, [input.key]: input.type === "number" ? Number(e.target.value) : e.target.value }))}
                    className="bg-[var(--surface-soft)] border-[var(--line)] rounded-xl font-bold text-[var(--text-primary)]"
                  />
                  {input.unit && <span className="absolute right-4 top-1/2 -translate-y-1/2 text-[10px] font-bold text-[var(--text-hint)]">{input.unit}</span>}
                </div>
              </div>
            ))}
            <div className="space-y-2">
              <p className="text-[10px] font-black uppercase tracking-wider text-[var(--text-tertiary)]">지목 구분</p>
              <select
                value={form.land_category}
                onChange={(e) => setForm((p) => ({ ...p, land_category: e.target.value }))}
                className="w-full h-11 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 text-sm font-bold text-[var(--text-primary)] outline-none focus:ring-2 focus:ring-[var(--accent)] transition-all appearance-none"
              >
                <option value="land">대지 (Land)</option>
                <option value="farmland">농지 (Farmland)</option>
                <option value="forest">임야 (Forest)</option>
              </select>
            </div>
            <div className="flex items-end">
              <Button 
                onClick={handleCalculate} 
                disabled={isLoading} 
                className="w-full h-11 bg-[var(--accent)] hover:bg-[var(--accent-strong)] text-white font-black uppercase tracking-widest rounded-xl transition-all shadow-[var(--shadow-glow)]"
              >
                {isLoading ? "CALCULATING..." : "시뮬레이션 실행"}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <AnimatePresence>
        {result && (
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="grid gap-8"
          >
            {/* Summary Highlights */}
            <div className="grid gap-4 md:grid-cols-5">
              <Card className="border-[var(--accent)] bg-[var(--accent-soft)]/20 shadow-[var(--shadow-lg)]">
                <CardContent className="p-6">
                  <p className="text-[10px] font-black text-[var(--accent)] uppercase tracking-[0.2em]">전체 세액 합계</p>
                  <p className="mt-2 text-3xl font-[1000] tracking-tighter text-[var(--accent)]">
                    {formatWon(result.grand_total_won)}
                  </p>
                  <p className="mt-1 text-[9px] font-bold text-[var(--accent)] opacity-60 uppercase">{result.total_items_count} ITEMS IDENTIFIED</p>
                </CardContent>
              </Card>
              {Object.entries(result.stage_totals).map(([stage, total]) => (
                <Card key={stage} className="border-[var(--line-strong)] bg-[var(--surface-strong)]">
                  <CardContent className="p-6">
                    <p className="text-[10px] font-black text-[var(--text-tertiary)] uppercase tracking-[0.2em]">{stage}</p>
                    <p className="mt-2 text-2xl font-[1000] tracking-tighter text-[var(--text-primary)]">
                      {formatWon(total)}
                    </p>
                  </CardContent>
                </Card>
              ))}
            </div>

            {/* Stage Navigation Tabs */}
            <div className="flex p-1 bg-[var(--surface-strong)] rounded-2xl border border-[var(--line-strong)] w-fit">
              {STAGES.map((s) => (
                <button
                  key={s.key}
                  onClick={() => setActiveStage(s.key)}
                  className={`px-6 py-2.5 text-[11px] font-black uppercase tracking-widest rounded-xl transition-all ${
                    activeStage === s.key
                      ? "bg-[var(--accent)] text-white shadow-[var(--shadow-md)]"
                      : "text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>

            {/* Detailed Tax Itemization */}
            <Card className="border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)] overflow-hidden">
              <CardContent className="p-0">
                <table className="w-full text-left">
                  <thead>
                    <tr className="bg-[var(--surface-soft)] border-b border-[var(--line)]">
                      <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">TAX CODE</th>
                      <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">항목명 (DESC)</th>
                      <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">구분 (STAGE)</th>
                      <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-[var(--text-tertiary)] text-right">산출 세액 (AMOUNT)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--line)]">
                    {filteredItems.map((item) => (
                      <tr key={item.code} className="hover:bg-[var(--surface-soft)]/50 transition-colors group">
                        <td className="px-8 py-4 font-mono text-[10px] font-bold text-[var(--text-hint)]">{item.code}</td>
                        <td className="px-8 py-4 text-[13px] font-bold text-[var(--text-primary)]">{item.name}</td>
                        <td className="px-8 py-4">
                           <span className="px-3 py-1 rounded-full bg-[var(--surface-soft)] text-[9px] font-black uppercase text-[var(--text-tertiary)] border border-[var(--line)]">
                             {item.stage}
                           </span>
                        </td>
                        <td className="px-8 py-4 text-right">
                          <p className="text-[14px] font-[1000] text-[var(--text-primary)] tracking-tight">
                            {formatWon(item.amount_won)}
                          </p>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
