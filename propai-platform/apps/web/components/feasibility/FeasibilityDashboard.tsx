import React from "react";
import { Building2 } from "lucide-react";
import { Card, CardContent } from "@propai/ui";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell
} from "recharts";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";

type FeasibilityData = {
  massing?: {
    land_area_sqm: number;
    gfa_sqm: number;
    gfa_pyeong: number;
    estimated_far: number;
    estimated_bca: number;
  };
  financials?: {
    total_revenue_10k: number;
    land_cost_10k: number;
    construction_cost_10k: number;
    soft_cost_10k: number;
    total_cost_10k: number;
    net_profit_10k: number;
    roi_percent: number;
    npv_10k?: number; // 순현재가치(개략·할인 반영)
  };
  assumptions?: {
    avg_pyeong_price_10k: number;
    construction_cost_per_pyeong_10k: number;
    npv_discount_rate?: number;
    npv_dev_period_years?: number;
  };
};

interface FeasibilityDashboardProps {
  data?: FeasibilityData;
  zoneType?: string;
}

const COLORS = ["#0e7490", "#0ea5e9", "#38bdf8", "#bae6fd"];

export const FeasibilityDashboard: React.FC<FeasibilityDashboardProps> = ({ data, zoneType }) => {
  if (!data || !data.financials || !data.massing) return null;

  const { financials, massing, assumptions } = data;

  const formatPrice = (val: number) => {
    if (val >= 10000) {
      const uk = Math.floor(val / 10000);
      const rest = val % 10000;
      return rest > 0 ? `${uk}억 ${rest.toLocaleString()}만원` : `${uk}억원`;
    }
    return `${val.toLocaleString()}만원`;
  };

  const costData = [
    { name: "토지 매입비", value: financials.land_cost_10k },
    { name: "예상 건축비", value: financials.construction_cost_10k },
    { name: "부대 비용", value: financials.soft_cost_10k },
  ];

  const profitData = [
    { name: "총 사업비 (지출)", amount: financials.total_cost_10k },
    { name: "분양 수익 (매출)", amount: financials.total_revenue_10k },
    { name: "세전 순수익", amount: financials.net_profit_10k },
  ];

  // ★근거 기본제공: ROI/NPV/순수익이 '왜 이 값인가'를 산식으로 보인다. 모두 data의 실제 값으로만 구성(가짜값 0).
  //   estimated_*·전용률75%·NPV 할인은 가설계 추정이므로 basis에 '추정'을 정직 표기한다.
  const evidenceItems: EvidenceItem[] = [
    { label: "예상 세전 순수익", value: formatPrice(financials.net_profit_10k), basis: "분양 수익 − 총 사업비" },
    { label: "예상 수익률(ROI)", value: `${financials.roi_percent}%`, basis: "세전 순수익 ÷ 총 사업비 × 100 — 투입자본 대비 수익률(추정)" },
    { label: "총 사업비", value: formatPrice(financials.total_cost_10k), basis: "토지 매입비 + 예상 건축비 + 부대 비용(아래 지출 구조 차트 참조)" },
    { label: "분양 수익", value: formatPrice(financials.total_revenue_10k), basis: `건축가능 연면적 ${massing.gfa_pyeong.toLocaleString()}평 × 평당 분양가 ${formatPrice(assumptions?.avg_pyeong_price_10k || 0)} × 전용률 75%(추정)` },
    { label: "건축비 단가", value: `평당 ${(assumptions?.construction_cost_per_pyeong_10k ?? 0).toLocaleString()}만원`, basis: "예상 건축비 산정 단가(추정)" },
  ];
  if (financials.npv_10k != null) {
    evidenceItems.push({
      label: "순현재가치(NPV)",
      value: formatPrice(financials.npv_10k),
      basis: `할인율 ${((assumptions?.npv_discount_rate ?? 0.08) * 100).toFixed(0)}%·${assumptions?.npv_dev_period_years ?? 3}년 가정의 개략 할인값(참고용·정밀 IRR/NPV는 정밀 수지엔진)`,
    });
  }

  return (
    <div className="flex flex-col gap-6 mt-8 mb-8">
      <div className="sa-di-block">
        <header className="sa-di-block__head" style={{ cursor: "default", borderBottom: "2px solid var(--accent-strong)" }}>
          <span className="sa-di-block__icon" aria-hidden><Building2 className="size-5" /></span>
          <span className="sa-di-block__title text-lg font-black text-[var(--accent-strong)]">AI 사업 타당성 분석 (Feasibility Report)</span>
          <span className="sa-di-eyebrow text-white bg-[var(--accent-strong)] px-2 py-0.5 rounded-full">BETA</span>
        </header>

        <div className="sa-di-block__body grid grid-cols-1 md:grid-cols-2 gap-6 p-6 bg-[var(--surface-soft)] rounded-b-2xl">
          {/* 가설계 / Massing */}
          <Card className="border-[var(--line-strong)] shadow-sm">
            <CardContent className="p-5 flex flex-col justify-between h-full">
              <div>
                <h4 className="text-sm font-bold text-[var(--text-secondary)] mb-4">건축 규모 가설계 (Massing)</h4>
                <div className="space-y-3">
                  <div className="flex justify-between border-b border-[var(--line-light)] pb-2">
                    <span className="text-[var(--text-secondary)] text-sm">적용 용도지역</span>
                    <span className="font-semibold text-sm">{zoneType || "정보 없음"}</span>
                  </div>
                  <div className="flex justify-between border-b border-[var(--line-light)] pb-2">
                    <span
                      className="text-[var(--text-secondary)] text-sm"
                      title="가설계 기준 추정값입니다. 실효 용적률(조례)·법정 상한과 다를 수 있으니 부지분석의 '건축 가능 범위'(정북일조·실효 한도)를 함께 확인하세요."
                    >
                      예상 건폐율 / 용적률 <span className="text-[10px] text-[var(--text-hint)]">(추정)</span>
                    </span>
                    <span className="font-semibold text-sm text-[var(--status-info)]">
                      {massing.estimated_bca}% / {massing.estimated_far}%
                    </span>
                  </div>
                  <div className="flex justify-between border-b border-[var(--line-light)] pb-2">
                    <span className="text-[var(--text-secondary)] text-sm">대지 면적</span>
                    <span className="font-semibold text-sm">{massing.land_area_sqm.toLocaleString()} ㎡</span>
                  </div>
                  <div className="flex justify-between border-b border-[var(--line-light)] pb-2">
                    <span className="text-[var(--text-secondary)] text-sm">건축 가능 연면적</span>
                    <span className="font-semibold text-sm text-[var(--accent-strong)]">
                      {massing.gfa_pyeong.toLocaleString()} 평 ({massing.gfa_sqm.toLocaleString()} ㎡)
                    </span>
                  </div>
                </div>
              </div>
              <div className="mt-4 p-3 bg-[var(--surface-main)] rounded-lg text-xs text-[var(--text-hint)] border border-[var(--line-light)]">
                건축비: 평당 {assumptions?.construction_cost_per_pyeong_10k.toLocaleString()}만원 적용<br/>
                적정 분양가: 평당 {formatPrice(assumptions?.avg_pyeong_price_10k || 0)} 적용 (전용률 75%)
              </div>
            </CardContent>
          </Card>

          {/* 재무 요약 / Financials */}
          <Card className="border-[var(--line-strong)] shadow-sm border-t-4 border-t-[var(--status-success)]">
            <CardContent className="p-5 flex flex-col justify-between h-full">
              <div>
                <h4 className="text-sm font-bold text-[var(--text-secondary)] mb-4">예상 수익률 (ROI) 요약</h4>
                
                <div className="flex flex-col items-center justify-center mb-6 py-4 bg-[var(--surface-main)] rounded-xl border border-[var(--status-success)]/30">
                  <span className="text-xs font-bold text-[var(--status-success)] mb-1">최종 예상 수익률 (ROI)</span>
                  <span className="text-4xl font-black text-[var(--status-success)]">
                    {financials.roi_percent}%
                  </span>
                </div>

                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-[var(--text-secondary)] text-sm">총 사업비</span>
                    <span className="font-semibold text-sm">{formatPrice(financials.total_cost_10k)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[var(--text-secondary)] text-sm">예상 분양 수익</span>
                    <span className="font-semibold text-sm text-[var(--status-info)]">{formatPrice(financials.total_revenue_10k)}</span>
                  </div>
                  <div className="flex justify-between pt-2 border-t border-[var(--line-strong)]">
                    <span className="font-bold text-sm">예상 세전 순수익</span>
                    <span className="font-black text-sm text-[var(--status-success)]">{formatPrice(financials.net_profit_10k)}</span>
                  </div>
                  {financials.npv_10k != null && (
                    <div className="flex justify-between">
                      <span className="text-[var(--text-secondary)] text-sm">
                        순현재가치 (NPV)
                        <span className="ml-1 text-[10px] text-[var(--text-hint)]">
                          할인율 {((assumptions?.npv_discount_rate ?? 0.08) * 100).toFixed(0)}%·{assumptions?.npv_dev_period_years ?? 3}년
                        </span>
                      </span>
                      <span className={`font-bold text-sm ${financials.npv_10k >= 0 ? "text-[var(--status-success)]" : "text-[var(--status-danger)]"}`}>
                        {formatPrice(financials.npv_10k)}
                      </span>
                    </div>
                  )}
                </div>
                <p className="mt-2 text-[10px] leading-snug text-[var(--text-hint)]">
                  ※ NPV는 토지비 선투입·건축비 분산·분양수입 완공시점 가정의 개략 할인값(참고용). 정밀 세후 IRR/NPV는 정밀 수지엔진 사용.
                </p>
              </div>
            </CardContent>
          </Card>

          {/* 차트 영역 */}
          <div className="md:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-6 mt-2">
            <Card className="border-[var(--line-strong)]">
              <CardContent className="p-4">
                <h5 className="text-xs font-bold text-[var(--text-secondary)] text-center mb-4">총 사업비 지출 구조</h5>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={costData}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={80}
                        paddingAngle={5}
                        dataKey="value"
                      >
                        {costData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                        ))}
                      </Pie>
                      <RechartsTooltip formatter={(val: any) => formatPrice(Number(val))} />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            <Card className="border-[var(--line-strong)]">
              <CardContent className="p-4">
                <h5 className="text-xs font-bold text-[var(--text-secondary)] text-center mb-4">수익성 (비용 vs 매출)</h5>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={profitData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                      <YAxis tickFormatter={(val) => `${Math.floor(val / 10000)}억`} />
                      <RechartsTooltip formatter={(val: any) => formatPrice(Number(val))} />
                      <Bar dataKey="amount" radius={[4, 4, 0, 0]}>
                        {profitData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.amount < 0 ? "#ef4444" : (index === 1 ? "#0ea5e9" : (index === 2 ? "#22c55e" : "#64748b"))} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* 산출 근거(EvidencePanel) — ROI/NPV/순수익 산식 트레이스. data의 실제 값만 사용(가짜값/가짜URL 0). */}
          <div className="md:col-span-2">
            <EvidencePanel items={evidenceItems} title="사업 타당성 산출 근거" />
          </div>
        </div>
      </div>
    </div>
  );
};
