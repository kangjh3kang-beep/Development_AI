"use client";

import { useState, useCallback } from "react";
import { motion } from "framer-motion";
import { apiClient } from "@/lib/api-client";

/* ── 타입 (백엔드 G2BBidAnalyzeResponse 1:1) ── */
type SpecEstimate = {
  building_type: string;
  total_gfa_sqm: number;
  floor_count_above: number;
  floor_count_below: number;
  structure_type: string;
  source: string;
  confidence: number;
};
type CostBreakdown = {
  direct_cost: number | null;
  total_project_cost: number | null;
  category_totals: Record<string, number>;
  cost_p10: number | null;
  cost_p50: number | null;
  cost_p80: number | null;
  cost_p90: number | null;
  cv: number | null;
  risk_contributions: Record<string, number>;
};
type Zoning = {
  zone_type: string | null;
  max_bcr_pct: number | null;
  max_far_pct: number | null;
  max_height_m: number | null;
  pnu: string | null;
  warnings: string[];
};
type PermitCheck = {
  is_permitted: boolean | null;
  permit_complexity: number | null;
  reason: string | null;
  rule_results: Array<Record<string, unknown>>;
};
type Esg = {
  total_score: number | null;
  grade: string | null;
  components: Record<string, unknown>;
  recommendations: string[];
};
type Cashflow = {
  irr_annual_pct: number | null;
  peak_negative_cashflow: number | null;
  net_profit: number | null;
  phases: Record<string, unknown>;
};
type Sensitivity = {
  tornado: Array<{ name?: string; variable?: string; spread?: number }>;
  scenarios: Array<Record<string, unknown>>;
};
type MarketFeed = {
  items: Array<{ stat_period: string; bid_type: string; avg_award_rate: number | null }>;
  region_avg: number | null;
  region_std: number | null;
};
type AiInterpretation = {
  bid_strategy: string;
  feasibility_view: string;
  risk_assessment: string;
  cost_competitiveness: string;
  recommendation: string;
  model_used: string | null;
  generated: boolean;
};
type AnalysisResult = {
  bid_notice_no: string;
  bid_notice_nm: string;
  estimated_price: number | null;
  recommended_bid_rate_low: number;
  recommended_bid_rate_mid: number;
  recommended_bid_rate_high: number;
  expected_npv: number | null;
  expected_roi: number | null;
  profit_probability: number | null;
  risk_score_cost: number;
  risk_score_trust: number;
  risk_score_competition: number;
  risk_score_total: number;
  region_avg_award_rate: number | null;
  ai_summary: string;
  g2b_url: string | null;
  spec: SpecEstimate | null;
  cost_breakdown: CostBreakdown | null;
  qto: Array<{ work_code: string; item_name: string; unit: string; quantity: number }> | null;
  zoning: Zoning | null;
  permit_check: PermitCheck | null;
  esg: Esg | null;
  cashflow: Cashflow | null;
  sensitivity: Sensitivity | null;
  market_feed: MarketFeed | null;
  break_even_bid_rate: number | null;
  recommended_bid_price: number | null;
  analysis_warnings: string[];
  ai_interpretation: AiInterpretation | null;
};

/* ── 유틸 ── */
function fmtKRW(v: number | null | undefined): string {
  if (v == null) return "-";
  if (Math.abs(v) >= 1_0000_0000) return `${(v / 1_0000_0000).toFixed(1)}억원`;
  if (Math.abs(v) >= 1_0000) return `${(v / 1_0000).toFixed(0)}만원`;
  return `${v.toLocaleString()}원`;
}
function fmtPct(v: number | null | undefined): string {
  return v == null ? "-" : `${v.toFixed(1)}%`;
}

type ManualForm = {
  total_gfa_sqm: string;
  floor_count_above: string;
  structure_type: string;
  building_type_override: string;
  target_margin_pct: string;
};

export function G2BBidAnalysisModal({
  bidId,
  bidName,
  initialResult,
  initialForm,
  onClose,
}: {
  bidId: string;
  bidName?: string;
  /** 히스토리에서 저장된 결과를 바로 표시(재조회) */
  initialResult?: AnalysisResult | null;
  /** 편집 재분석 시 입력 폼 프리필 */
  initialForm?: Partial<ManualForm>;
  onClose: () => void;
}) {
  const [result, setResult] = useState<AnalysisResult | null>(initialResult ?? null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<ManualForm>({
    total_gfa_sqm: initialForm?.total_gfa_sqm ?? "",
    floor_count_above: initialForm?.floor_count_above ?? "",
    structure_type: initialForm?.structure_type ?? "",
    building_type_override: initialForm?.building_type_override ?? "",
    target_margin_pct: initialForm?.target_margin_pct ?? "5",
  });

  const runAnalysis = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        simulation_iterations: 5000,
        cost_volatility_pct: 10,
        target_margin_pct: Number(form.target_margin_pct) || 5,
      };
      if (form.total_gfa_sqm) body.total_gfa_sqm = Number(form.total_gfa_sqm);
      if (form.floor_count_above) body.floor_count_above = Number(form.floor_count_above);
      if (form.structure_type) body.structure_type = form.structure_type;
      if (form.building_type_override) body.building_type_override = form.building_type_override;
      const data = await apiClient.post<AnalysisResult>(
        `/g2b/bids/${bidId}/feasibility`,
        { body },
      );
      setResult(data);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [bidId, form]);

  const riskColor = (s: number) =>
    s < 30 ? "text-emerald-400" : s < 60 ? "text-yellow-400" : "text-red-400";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-3xl max-h-[90vh] overflow-y-auto rounded-2xl bg-[var(--surface-strong)] border-2 border-[var(--line-strong)] p-6 shadow-2xl ring-1 ring-black/40"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 헤더 */}
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-xl font-black text-[var(--text-primary)]">AI 정밀 입찰 분석</h2>
            <p className="text-sm text-[var(--text-secondary)] mt-1">
              {bidName || result?.bid_notice_nm || ""}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-[var(--text-hint)] hover:text-[var(--text-primary)] text-2xl leading-none"
          >
            ×
          </button>
        </div>

        {/* 수동 보정 폼 */}
        <div className="rounded-xl border border-[var(--line)] p-4 mb-4 bg-[var(--surface-soft)]/30">
          <p className="text-xs font-bold text-[var(--text-secondary)] mb-3">
            건축 개요 보정 (비워두면 추정가격으로 자동 역산)
          </p>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            <input
              placeholder="연면적(㎡)"
              value={form.total_gfa_sqm}
              onChange={(e) => setForm({ ...form, total_gfa_sqm: e.target.value })}
              className="h-9 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2 text-sm text-[var(--text-primary)]"
            />
            <input
              placeholder="지상 층수"
              value={form.floor_count_above}
              onChange={(e) => setForm({ ...form, floor_count_above: e.target.value })}
              className="h-9 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2 text-sm text-[var(--text-primary)]"
            />
            <select
              value={form.structure_type}
              onChange={(e) => setForm({ ...form, structure_type: e.target.value })}
              className="h-9 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2 text-sm text-[var(--text-primary)]"
            >
              <option value="">구조 자동</option>
              <option value="RC">RC</option>
              <option value="SRC">SRC</option>
              <option value="SC">철골(SC)</option>
              <option value="PC">PC</option>
            </select>
            <select
              value={form.building_type_override}
              onChange={(e) => setForm({ ...form, building_type_override: e.target.value })}
              className="h-9 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2 text-sm text-[var(--text-primary)]"
            >
              <option value="">유형 자동</option>
              <option value="아파트">아파트</option>
              <option value="공동주택">공동주택</option>
              <option value="오피스텔">오피스텔</option>
              <option value="다세대주택">다세대주택</option>
              <option value="근린생활시설">근린생활시설</option>
            </select>
            <input
              placeholder="목표마진(%)"
              value={form.target_margin_pct}
              onChange={(e) => setForm({ ...form, target_margin_pct: e.target.value })}
              className="h-9 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2 text-sm text-[var(--text-primary)]"
            />
            <button
              onClick={runAnalysis}
              disabled={loading}
              className="h-9 rounded-lg bg-[var(--accent-strong)] text-white text-sm font-bold hover:opacity-90 disabled:opacity-50"
            >
              {loading ? "분석 중…" : result ? "다시 분석" : "분석 시작"}
            </button>
          </div>
        </div>

        {error && (
          <div className="rounded-lg bg-red-500/10 border border-red-500/30 p-3 text-sm text-red-400 mb-4">
            분석 실패: {error}
          </div>
        )}

        {!result && !loading && !error && (
          <p className="text-center text-sm text-[var(--text-hint)] py-8">
            [분석 시작]을 누르면 물량산출·수지·법규·ESG를 통합 분석합니다.
          </p>
        )}

        {result && (
          <div className="space-y-4">
            {result.analysis_warnings?.length > 0 && (
              <div className="rounded-lg bg-yellow-500/10 border border-yellow-500/30 p-2 text-xs text-yellow-400">
                {result.analysis_warnings.map((w, i) => (
                  <div key={i}>⚠ {w}</div>
                ))}
              </div>
            )}

            {/* 적정 투찰가 */}
            <section className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
              <h3 className="text-sm font-black text-[var(--text-primary)] mb-2">적정 투찰가</h3>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-black text-[var(--accent-strong)]">
                  {fmtPct(result.recommended_bid_rate_mid)}
                </span>
                <span className="text-sm text-[var(--text-secondary)]">
                  ({fmtPct(result.recommended_bid_rate_low)} ~ {fmtPct(result.recommended_bid_rate_high)})
                </span>
              </div>
              <div className="text-sm text-[var(--text-secondary)] mt-1">
                추천 투찰가: <b className="text-[var(--text-primary)]">{fmtKRW(result.recommended_bid_price)}</b>
                {result.break_even_bid_rate != null && (
                  <span className="ml-2 text-[var(--text-hint)]">손익분기 {fmtPct(result.break_even_bid_rate)}</span>
                )}
              </div>
            </section>

            {/* 사업성 */}
            <section className="grid grid-cols-3 gap-2">
              <Stat label="예상 NPV" value={fmtKRW(result.expected_npv)} />
              <Stat label="ROI" value={fmtPct(result.expected_roi)} />
              <Stat label="수익 확률" value={fmtPct(result.profit_probability)} />
            </section>

            {/* 리스크 3축 */}
            <section className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
              <h3 className="text-sm font-black text-[var(--text-primary)] mb-2">
                리스크 <span className={riskColor(result.risk_score_total)}>{result.risk_score_total.toFixed(0)}점</span>
              </h3>
              <RiskBar label="공사비" v={result.risk_score_cost} />
              <RiskBar label="발주처 신뢰도" v={result.risk_score_trust} />
              <RiskBar label="경쟁 강도" v={result.risk_score_competition} />
            </section>

            {/* QTO 원가 */}
            {result.cost_breakdown && (
              <section className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
                <h3 className="text-sm font-black text-[var(--text-primary)] mb-2">
                  추정 공사원가 (물량산출 기반)
                </h3>
                <div className="text-sm text-[var(--text-secondary)]">
                  총 원가 <b className="text-[var(--text-primary)]">{fmtKRW(result.cost_breakdown.total_project_cost)}</b>
                  {result.cost_breakdown.cv != null && (
                    <span className="ml-2 text-[var(--text-hint)]">변동계수 {(result.cost_breakdown.cv * 100).toFixed(1)}%</span>
                  )}
                </div>
                <div className="text-xs text-[var(--text-hint)] mt-1">
                  P10 {fmtKRW(result.cost_breakdown.cost_p10)} · P90 {fmtKRW(result.cost_breakdown.cost_p90)}
                </div>
                {result.spec && (
                  <div className="text-xs text-[var(--text-hint)] mt-2">
                    추정 개요: {result.spec.building_type} / 연면적 {result.spec.total_gfa_sqm.toLocaleString()}㎡ /
                    {result.spec.floor_count_above}층 / {result.spec.structure_type}
                    <span className="ml-1">(신뢰도 {(result.spec.confidence * 100).toFixed(0)}%, {result.spec.source})</span>
                  </div>
                )}
              </section>
            )}

            {/* 용도지역 + 법규 + ESG */}
            <section className="grid md:grid-cols-3 gap-2">
              {result.zoning && (
                <MiniCard title="용도지역">
                  {result.zoning.zone_type || "미상"}
                  <div className="text-xs text-[var(--text-hint)] mt-1">
                    건폐 {fmtPct(result.zoning.max_bcr_pct)} / 용적 {fmtPct(result.zoning.max_far_pct)}
                  </div>
                </MiniCard>
              )}
              {result.permit_check && (
                <MiniCard title="인허가">
                  {result.permit_check.is_permitted ? "가능" : "검토 필요"}
                  <div className="text-xs text-[var(--text-hint)] mt-1">
                    난이도 {result.permit_check.permit_complexity ?? "-"}/5
                  </div>
                </MiniCard>
              )}
              {result.esg && (
                <MiniCard title="ESG (GRESB)">
                  {result.esg.grade || "-"} 등급
                  <div className="text-xs text-[var(--text-hint)] mt-1">{result.esg.total_score ?? "-"}점</div>
                </MiniCard>
              )}
            </section>

            {/* 현금흐름 + 민감도 */}
            <section className="grid md:grid-cols-2 gap-2">
              {result.cashflow && (
                <MiniCard title="현금흐름">
                  IRR {fmtPct(result.cashflow.irr_annual_pct)}
                  <div className="text-xs text-[var(--text-hint)] mt-1">
                    순이익 {fmtKRW(result.cashflow.net_profit)}
                  </div>
                </MiniCard>
              )}
              {result.sensitivity && result.sensitivity.tornado.length > 0 && (
                <MiniCard title="민감도 (영향 큰 변수)">
                  {result.sensitivity.tornado.slice(0, 3).map((t, i) => (
                    <div key={i} className="text-xs text-[var(--text-secondary)]">
                      {t.name || t.variable} {t.spread != null ? `(${t.spread.toFixed(1)})` : ""}
                    </div>
                  ))}
                </MiniCard>
              )}
            </section>

            {/* AI 요약 (규칙기반 한줄 요약) */}
            {result.ai_summary && (
              <section className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
                <h3 className="text-sm font-black text-[var(--text-primary)] mb-2">AI 종합 의견</h3>
                <pre className="whitespace-pre-wrap text-sm text-[var(--text-secondary)] font-sans">
                  {result.ai_summary}
                </pre>
              </section>
            )}

            {/* LLM(Claude) 입찰 전략 해석 — 5섹션 전용 카드 */}
            {result.ai_interpretation?.generated && (
              <section className="rounded-xl border border-blue-500/30 bg-blue-500/5 p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-black text-[var(--text-primary)] flex items-center gap-2">
                    <span className="text-blue-400">🧠</span> AI 입찰 전략 분석
                  </h3>
                  {result.ai_interpretation.model_used && (
                    <span className="text-[10px] text-[var(--text-hint)]">
                      {result.ai_interpretation.model_used}
                    </span>
                  )}
                </div>
                <div className="space-y-3">
                  <AiSection icon="📊" title="투찰 전략" text={result.ai_interpretation.bid_strategy} />
                  <AiSection icon="💰" title="사업성 진단" text={result.ai_interpretation.feasibility_view} />
                  <AiSection icon="⚠️" title="리스크 평가" text={result.ai_interpretation.risk_assessment} />
                  <AiSection icon="🏗️" title="원가 경쟁력" text={result.ai_interpretation.cost_competitiveness} />
                  <AiSection
                    icon="✅"
                    title="종합 권고"
                    text={result.ai_interpretation.recommendation}
                    emphasis
                  />
                </div>
              </section>
            )}

            {result.g2b_url && (
              <button
                onClick={() => window.open(result.g2b_url || "#", "_blank")}
                className="w-full h-11 rounded-xl bg-[var(--accent-strong)] text-white font-bold hover:opacity-90 transition"
              >
                나라장터에서 입찰하기 →
              </button>
            )}
          </div>
        )}
      </motion.div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3 text-center">
      <p className="text-[10px] text-[var(--text-hint)]">{label}</p>
      <p className="text-base font-black text-[var(--text-primary)] mt-1">{value}</p>
    </div>
  );
}

function MiniCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
      <p className="text-[10px] text-[var(--text-hint)] mb-1">{title}</p>
      <div className="text-sm font-bold text-[var(--text-primary)]">{children}</div>
    </div>
  );
}

function RiskBar({ label, v }: { label: string; v: number }) {
  const color = v < 30 ? "bg-emerald-400" : v < 60 ? "bg-yellow-400" : "bg-red-400";
  return (
    <div className="flex items-center gap-2 mt-1">
      <span className="text-xs text-[var(--text-secondary)] w-24 shrink-0">{label}</span>
      <div className="flex-1 h-2 rounded-full bg-[var(--surface-soft)]">
        <div className={`h-2 rounded-full ${color}`} style={{ width: `${Math.min(100, v)}%` }} />
      </div>
      <span className="text-xs text-[var(--text-hint)] w-8 text-right">{v.toFixed(0)}</span>
    </div>
  );
}

/* LLM 입찰 전략 해석 섹션 카드 (종합권고는 emphasis로 강조) */
function AiSection({
  icon,
  title,
  text,
  emphasis = false,
}: {
  icon: string;
  title: string;
  text: string;
  emphasis?: boolean;
}) {
  if (!text) return null;
  return (
    <div
      className={`rounded-lg p-3 ${
        emphasis
          ? "bg-blue-500/10 border border-blue-500/30"
          : "bg-[var(--surface-soft)]/40"
      }`}
    >
      <div className="flex items-center gap-1.5 mb-1">
        <span className="text-sm shrink-0">{icon}</span>
        <span
          className={`text-xs font-bold ${
            emphasis ? "text-blue-300" : "text-[var(--text-primary)]"
          }`}
        >
          {title}
        </span>
      </div>
      <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed whitespace-pre-line">
        {text}
      </p>
    </div>
  );
}

export default G2BBidAnalysisModal;
