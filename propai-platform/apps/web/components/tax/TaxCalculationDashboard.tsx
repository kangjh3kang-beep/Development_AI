"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Button, Card, CardContent, CardTitle, Input } from "@propai/ui";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";

type TaxItem = {
  code: string;
  name: string;
  stage: string;
  amount_won: number;
  // 산출 근거(산식·적용세율·다주택중과·누진구간). kr-tax-calculator가 실제 계산한
  // 값으로만 채운다. 규칙추정(일정비율) 항목은 근거가 없으므로 undefined로 둔다.
  evidence?: EvidenceItem[];
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

// 백분율을 보기 좋게(소수점 자투리 제거) 표시. 예: 6 → "6%", 6.6 → "6.6%".
function pct(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  return `${rounded}%`;
}

// 세액 한 항목 = (항목행) + 근거가 있으면 (근거패널행). 표 레이아웃 유지를 위해
// 근거패널은 전체 폭(colSpan)으로 항목 바로 아래에 접이식으로 노출한다.
function FragmentRow({ item }: { item: TaxItem }) {
  const hasEvidence = Array.isArray(item.evidence) && item.evidence.length > 0;
  return (
    <>
      <tr className="hover:bg-[var(--surface-soft)]/50 transition-colors group">
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
      {hasEvidence && (
        <tr className="bg-[var(--surface-soft)]/30">
          <td colSpan={4} className="px-8 pb-4 pt-0">
            {/* 산식·적용세율·다주택중과·누진구간 근거(계산기 실값) */}
            <EvidencePanel title={`${item.name} 산출 근거`} items={item.evidence!} defaultOpen={false} />
          </td>
        </tr>
      )}
    </>
  );
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
      const { calculateAcquisitionTax, calculateCapitalGainsTax, calculateComprehensivePropertyTax } = await import("@/lib/kr-tax-calculator");
      const purchase = form.purchase_won;
      const saleTotal = form.total_sale_amount_won;
      const gfa = form.total_gfa_sqm;
      const households = form.total_households;

      // 취득 단계
      const acqRes = calculateAcquisitionTax(purchase, 1);
      const acqItems: TaxItem[] = [
        {
          code: "ACQ-01", name: "취득세", stage: "acquisition", amount_won: acqRes.acquisitionTax,
          // 근거: 취득세 = 취득가 × 적용세율(주택 1~3% 구간), 모두 계산기 실값
          evidence: [
            { label: "산식", value: "취득가 × 적용세율" },
            { label: "취득가", value: formatWon(acqRes.acquisitionPrice), basis: `${acqRes.acquisitionPrice.toLocaleString()}원` },
            { label: "적용세율", value: pct(acqRes.taxRate), basis: "주택 취득세 구간(6억↓ 1% · 9억↓ 2% · 9억↑ 3%)" },
            { label: "취득세", value: `${acqRes.acquisitionTax.toLocaleString()}원`, basis: `${acqRes.acquisitionPrice.toLocaleString()} × ${pct(acqRes.taxRate)}` },
          ],
        },
        { code: "ACQ-02", name: "농어촌특별세", stage: "acquisition", amount_won: acqRes.ruralTax,
          // 근거: 농특세 = 취득세 × 10%(계산기 실값)
          evidence: [{ label: "산식", value: "취득세 × 10%" }, { label: "취득세", value: `${acqRes.acquisitionTax.toLocaleString()}원` }] },
        { code: "ACQ-03", name: "지방교육세", stage: "acquisition", amount_won: acqRes.educationTax,
          // 근거: 지방교육세 = 취득세 × 10%(계산기 실값)
          evidence: [{ label: "산식", value: "취득세 × 10%" }, { label: "취득세", value: `${acqRes.acquisitionTax.toLocaleString()}원` }] },
        { code: "ACQ-04", name: "인지세", stage: "acquisition", amount_won: purchase > 1e9 ? 350000 : 150000 },
        { code: "ACQ-05", name: "등록면허세", stage: "acquisition", amount_won: Math.round(purchase * 0.002) },
        { code: "ACQ-06", name: "국민주택채권 매입", stage: "acquisition", amount_won: Math.round(purchase * 0.01) },
        { code: "ACQ-07", name: "법무사 보수", stage: "acquisition", amount_won: Math.round(purchase * 0.001) },
        { code: "ACQ-08", name: "중개수수료", stage: "acquisition", amount_won: Math.round(purchase * 0.004) },
      ];

      // 공사/보유 단계
      const propRes = calculateComprehensivePropertyTax(purchase, 1);
      const utilItems: TaxItem[] = [
        {
          code: "UTL-01", name: "재산세", stage: "utility", amount_won: propRes.propertyTax,
          // 근거: 과세표준 = 공시가격 × 공정시장가액비율, 재산세는 과표 누진세율 적용(계산기 실값)
          evidence: [
            { label: "산식", value: "과세표준 × 누진세율" },
            { label: "공정시장가액비율", value: pct(propRes.fairMarketRatio) },
            { label: "과세표준", value: `${propRes.taxBase.toLocaleString()}원`, basis: `공시가격 × ${pct(propRes.fairMarketRatio)}` },
            { label: "재산세", value: `${propRes.propertyTax.toLocaleString()}원`, basis: "과표 구간별 누진(6천만↓ 0.1% ~ 3억↑ 0.4%)" },
          ],
        },
        {
          code: "UTL-02", name: "종합부동산세", stage: "utility", amount_won: propRes.comprehensiveTax,
          // 근거: 공시가 11억 초과분에만 부과(계산기 실값). 미부과 시 0원 정직 표기.
          evidence: [
            { label: "산식", value: "공시가 기본공제 초과분 × 누진세율" },
            { label: "공정시장가액비율", value: pct(propRes.fairMarketRatio) },
            { label: "종합부동산세", value: `${propRes.comprehensiveTax.toLocaleString()}원`, basis: propRes.comprehensiveTax > 0 ? "1세대1주택 11억 초과분 과세" : "기본공제(11억) 이하 — 미부과" },
          ],
        },
        { code: "UTL-03", name: "도시계획세", stage: "utility", amount_won: Math.round(propRes.propertyTax * 0.14) },
        { code: "UTL-04", name: "지역자원시설세", stage: "utility", amount_won: Math.round(propRes.propertyTax * 0.1) },
        { code: "UTL-05", name: "건설부담금", stage: "utility", amount_won: Math.round(gfa * 15000) },
        { code: "UTL-06", name: "교통유발부담금", stage: "utility", amount_won: Math.round(gfa * 3500) },
        { code: "UTL-07", name: "학교용지부담금", stage: "utility", amount_won: Math.round(households * 500000) },
        { code: "UTL-08", name: "광역교통시설부담금", stage: "utility", amount_won: Math.round(households * 850000) },
        { code: "UTL-09", name: "상하수도 원인자부담금", stage: "utility", amount_won: Math.round(households * 300000) },
        { code: "UTL-10", name: "전기수전부담금", stage: "utility", amount_won: Math.round(households * 200000) },
      ];

      // 분양/운영 단계
      const saleItems: TaxItem[] = [
        { code: "SAL-01", name: "부가가치세", stage: "sale", amount_won: Math.round(saleTotal * 0.1) },
        { code: "SAL-02", name: "분양보증수수료", stage: "sale", amount_won: Math.round(saleTotal * 0.003) },
        { code: "SAL-03", name: "하자보수보증금", stage: "sale", amount_won: Math.round(saleTotal * 0.03) },
        { code: "SAL-04", name: "입주관리비", stage: "sale", amount_won: Math.round(households * 150000) },
        { code: "SAL-05", name: "취득세 감면 대상 환급", stage: "sale", amount_won: -Math.round(households * 200000) },
        { code: "SAL-06", name: "종합소득세(사업소득)", stage: "sale", amount_won: Math.round((saleTotal - purchase) * 0.15) },
        { code: "SAL-07", name: "주민세(종업원분)", stage: "sale", amount_won: Math.round(households * 10000) },
        { code: "SAL-08", name: "환경개선부담금", stage: "sale", amount_won: Math.round(gfa * 1200) },
        { code: "SAL-09", name: "농지전용부담금", stage: "sale", amount_won: form.land_category === "farmland" ? Math.round(purchase * 0.2) : 0 },
        { code: "SAL-10", name: "산지전용부담금", stage: "sale", amount_won: form.land_category === "forest" ? Math.round(purchase * 0.1) : 0 },
      ];

      // 양도/매각 단계
      const cgRes = calculateCapitalGainsTax({
        acquisitionPrice: purchase,
        salePrice: saleTotal,
        holdingYears: 3,
        houseCount: 1,
        isSingleHome: false,
        expenses: Math.round(purchase * 0.02),
      });
      // 양도세 근거(모두 계산기 실값): 다주택 중과는 houseCount=2일 때만 표기(현재 1주택→0).
      const cgEvidence: EvidenceItem[] = [
        { label: "산식", value: "과세표준 × 적용세율 − 누진공제" },
        { label: "양도차익", value: `${cgRes.capitalGain.toLocaleString()}원`, basis: "양도가 − 취득가 − 필요경비" },
      ];
      if (cgRes.ltcgRate > 0) {
        cgEvidence.push({ label: "장기보유특별공제율", value: pct(cgRes.ltcgRate), basis: `보유 ${3}년 기준` });
      }
      cgEvidence.push({ label: "과세표준", value: `${cgRes.taxBase.toLocaleString()}원`, basis: "양도소득금액 − 기본공제(250만)" });
      cgEvidence.push({ label: "적용세율", value: pct(cgRes.appliedRate), basis: "양도소득세 누진세율(6~45%)" });
      if (cgRes.multiHomeSurcharge > 0) {
        cgEvidence.push({ label: "다주택 중과", value: `+${pct(cgRes.multiHomeSurcharge)}`, basis: "2주택 +20%p · 3주택↑ +30%p" });
      }
      cgEvidence.push({ label: "산출세액", value: `${cgRes.calculatedTax.toLocaleString()}원` });

      const dispItems: TaxItem[] = [
        { code: "DSP-01", name: "양도소득세", stage: "disposal", amount_won: cgRes.calculatedTax, evidence: cgEvidence },
        {
          code: "DSP-02", name: "지방소득세(양도)", stage: "disposal", amount_won: cgRes.localTax,
          // 근거: 지방소득세 = 양도소득세 × 10%(계산기 실값)
          evidence: [{ label: "산식", value: "양도소득세 × 10%" }, { label: "양도소득세", value: `${cgRes.calculatedTax.toLocaleString()}원` }],
        },
        { code: "DSP-03", name: "법인세(법인매각시)", stage: "disposal", amount_won: Math.round((saleTotal - purchase) * 0.22) },
        { code: "DSP-04", name: "지방소득세(법인)", stage: "disposal", amount_won: Math.round((saleTotal - purchase) * 0.022) },
        { code: "DSP-05", name: "중개수수료(매도)", stage: "disposal", amount_won: Math.round(saleTotal * 0.003) },
        { code: "DSP-06", name: "말소등기비용", stage: "disposal", amount_won: 150000 },
        { code: "DSP-07", name: "양도 인지세", stage: "disposal", amount_won: saleTotal > 1e9 ? 350000 : 150000 },
        { code: "DSP-08", name: "부동산신탁 보수", stage: "disposal", amount_won: Math.round(saleTotal * 0.002) },
        { code: "DSP-09", name: "감정평가수수료", stage: "disposal", amount_won: Math.round(saleTotal * 0.001) },
        { code: "DSP-10", name: "세무사 보수", stage: "disposal", amount_won: Math.round(saleTotal * 0.0005) },
      ];

      const items = [...acqItems, ...utilItems, ...saleItems, ...dispItems];
      const stageTotals: Record<string, number> = {};
      for (const item of items) {
        stageTotals[item.stage] = (stageTotals[item.stage] || 0) + item.amount_won;
      }
      setResult({
        grand_total_won: items.reduce((s, i) => s + i.amount_won, 0),
        total_items_count: items.length,
        items,
        stage_totals: stageTotals,
      });
    } catch { /* 무시 */ } finally {
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
                      // Fragment로 항목행 + (근거 있으면) 근거패널행을 함께 렌더
                      <FragmentRow key={item.code} item={item} />
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
