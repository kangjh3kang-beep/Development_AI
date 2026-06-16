"use client";

import { useState, useCallback, useEffect } from "react";
import { GlobalAddressSearch } from "@/components/common/GlobalAddressSearch";
import { DevelopmentScenarioCard } from "@/components/common/DevelopmentScenarioCard";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { apiClient } from "@/lib/api-client";

/* ── Helpers ── */

const SQM_PER_PYEONG = 3.3058;

function formatArea(sqm: number): string {
  if (!sqm || sqm <= 0) return "-";
  return `${sqm.toLocaleString("ko-KR")} m² (${(sqm / SQM_PER_PYEONG).toFixed(1)}평)`;
}

function formatWon(value: number): string {
  if (!value || value <= 0) return "-";
  if (value >= 1e8) return `${(value / 1e8).toFixed(1)}억원`;
  if (value >= 1e4) return `${(value / 1e4).toFixed(0)}만원`;
  return `${value.toLocaleString("ko-KR")}원`;
}

function formatManWon(value: number): string {
  if (!value || value <= 0) return "-";
  return `${value.toLocaleString("ko-KR")}만원`;
}

/* ── Sub-components ── */

function SectionCard({ title, icon, children, defaultOpen = false }: {
  title: string; icon: string; children: React.ReactNode; defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-strong)] overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-3 px-5 py-4 text-left hover:bg-[var(--surface-soft)] transition-colors"
      >
        <span className="text-lg">{icon}</span>
        <span className="flex-1 text-sm font-bold text-[var(--text-primary)]">{title}</span>
        <span className="text-[var(--text-hint)] text-xs">{open ? "▲" : "▼"}</span>
      </button>
      {open && <div className="px-5 pb-5 space-y-3">{children}</div>}
    </div>
  );
}

function MarketAiBlock({ label, text }: { label: string; text: string }) {
  return (
    <div>
      <p className="text-xs font-black text-emerald-400 mb-1">{label}</p>
      <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed whitespace-pre-line">
        {text}
      </p>
    </div>
  );
}

function AiInterpretation({ text }: { text: string }) {
  return (
    <div className="mt-3 rounded-lg bg-blue-500/5 border border-blue-500/20 p-4">
      <div className="flex items-start gap-2">
        <span className="text-blue-400 text-sm shrink-0">AI</span>
        <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed whitespace-pre-line">
          {text}
        </p>
      </div>
    </div>
  );
}

function AnnotationLine({ text }: { text: string }) {
  const tagMatch = text.match(/^\[(.+?)\]\s*(.*)/);
  if (!tagMatch) return <p className="text-[10px] text-[var(--text-secondary)]">{text}</p>;

  const [, tag, content] = tagMatch;
  const colors: Record<string, string> = {
    "법정 상한": "bg-blue-500/20 text-blue-400",
    "조례 제한": "bg-amber-500/20 text-amber-400",
    "조례 동일": "bg-gray-500/20 text-gray-400",
    "실효 용적률": "bg-emerald-500/20 text-emerald-400",
    "실효 건폐율": "bg-emerald-500/20 text-emerald-400",
    "적용 결과": "bg-[var(--accent-strong)]/20 text-[var(--accent-strong)]",
    "기부체납 여력": "bg-purple-500/20 text-purple-400",
  };
  const color = colors[tag] || "bg-gray-500/20 text-gray-400";

  return (
    <div className="flex items-start gap-2 text-[10px]">
      <span className={`shrink-0 px-1.5 py-0.5 rounded text-[9px] font-bold ${color}`}>{tag}</span>
      <span className="text-[var(--text-secondary)] leading-relaxed">{content}</span>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3">
      <p className="text-[10px] text-[var(--text-hint)] mb-0.5">{label}</p>
      <p className="text-sm font-bold text-[var(--text-primary)]">{String(value)}</p>
    </div>
  );
}

function PermitBadge({ complexity }: { complexity: number }) {
  const colors = ["", "bg-emerald-500/20 text-emerald-400", "bg-blue-500/20 text-blue-400", "bg-amber-500/20 text-amber-400", "bg-orange-500/20 text-orange-400", "bg-red-500/20 text-red-400"];
  const labels = ["", "매우쉽움", "쉽움", "보통", "어려움", "매우어려움"];
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${colors[complexity] || colors[3]}`}>
      {labels[complexity] || "보통"}
    </span>
  );
}

/* ── Types ── */

interface ModelInfo {
  id: string;
  name: string;
  tier: "standard" | "premium" | "economy";
}

interface ProviderInfo {
  provider: string;
  name: string;
  models: ModelInfo[];
  default_model: string;
}

/* ── Main Component ── */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnalysisResult = Record<string, any>;

export function ComprehensiveAnalysisPanel() {
  const ctxStore = useProjectContextStore();
  const [address, setAddress] = useState(ctxStore.siteAnalysis?.address ?? "");
  // 다필지: 검색·엑셀로 등록된 전 필지 주소(2필지↑ 시 통합 개발방식 분석 노출)
  const [parcels, setParcels] = useState<string[]>([]);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>("anthropic");
  const [selectedModel, setSelectedModel] = useState<string>("");

  useEffect(() => {
    apiClient.get<{ providers: ProviderInfo[] }>("/analysis/llm-providers")
      .then(data => {
        setProviders(data.providers ?? []);
        if ((data.providers?.length ?? 0) > 0) {
          setSelectedProvider(data.providers[0].provider);
          setSelectedModel(data.providers[0].default_model);
        }
      })
      .catch(() => {}); // 실패 시 기본값 유지
  }, []);

  const handleAnalyze = useCallback(async () => {
    if (!address.trim()) { setError("주소를 입력해주세요."); return; }
    setLoading(true); setError(null); setResult(null);
    try {
      const data = await apiClient.post<AnalysisResult>("/analysis/comprehensive", {
        body: {
          address,
          llm_provider: selectedProvider || undefined,
          llm_model: selectedModel || undefined,
        },
        useMock: false,
      });
      setResult(data);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [address, selectedProvider, selectedModel]);

  const ef = result?.effective_far || {};
  const supplyAreas: AnalysisResult[] = result?.supply_areas || [];
  const landPrices = result?.land_prices || {};
  const transactions = result?.transaction_prices || {};
  const salePrices: AnalysisResult[] = result?.sale_prices || [];
  const location = result?.location || {};
  const devPlans = result?.development_plans || {};

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--surface-strong)] p-6">
        <h2 className="text-xl font-black text-[var(--text-primary)] mb-1">종합 부지분석 보고서</h2>
        <p className="text-xs text-[var(--text-secondary)] mb-4">주소를 입력하면 7개 카테고리 자동 분석 보고서를 생성합니다</p>
        <div className="flex gap-3 items-end">
          <div className="flex-1">
            <GlobalAddressSearch
              writeToContext={false}
              onChange={(entries) => {
                if (entries.length > 0) setAddress(entries[0].jibunAddress || entries[0].fullAddress);
                setParcels(entries.map((e) => e.jibunAddress || e.fullAddress || e.roadAddress).filter(Boolean));
              }}
              placeholder="분석할 주소 검색 · 다필지는 엑셀로 일괄 등록"
            />
          </div>
          <button
            onClick={handleAnalyze}
            disabled={loading || !address.trim()}
            className="shrink-0 rounded-xl bg-[var(--accent-strong)] px-6 py-3 text-sm font-bold text-white shadow-[var(--shadow-glow)] transition-all hover:brightness-110 disabled:opacity-50"
          >
            {loading ? "분석 중..." : "종합 분석 시작"}
          </button>
        </div>
        {providers.length > 0 ? (
          <div className="flex gap-3 items-center mt-3">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold text-[var(--text-hint)]">AI 모델</span>
              <select
                value={selectedProvider}
                onChange={(e) => {
                  setSelectedProvider(e.target.value);
                  const p = providers.find(pr => pr.provider === e.target.value);
                  if (p) setSelectedModel(p.default_model);
                }}
                className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-1.5 text-xs text-[var(--text-primary)]"
              >
                {providers.map(p => (
                  <option key={p.provider} value={p.provider}>{p.name}</option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold text-[var(--text-hint)]">모델</span>
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-1.5 text-xs text-[var(--text-primary)]"
              >
                {providers.find(p => p.provider === selectedProvider)?.models.map(m => (
                  <option key={m.id} value={m.id}>
                    {m.name} {m.tier === "premium" ? "★" : m.tier === "economy" ? "⚡" : ""}
                  </option>
                ))}
              </select>
            </div>
          </div>
        ) : (
          <p className="text-[10px] text-[var(--text-hint)] mt-2">AI 해석: API 키 미설정 (규칙 기반 분석만 제공)</p>
        )}
      </div>

      {/* 다필지(2필지↑) 통합 개발방식 분석 — 검색·엑셀로 등록 시 자동 노출 */}
      {parcels.length > 1 && (
        <DevelopmentScenarioCard address={address} parcels={parcels} />
      )}

      {error && (
        <div className="rounded-xl bg-red-500/10 border border-red-500/30 p-4 text-sm text-red-400">{error}</div>
      )}

      {loading && (
        <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-strong)] p-8 text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-3 border-[var(--accent-strong)] border-t-transparent mb-3" />
          <p className="text-sm text-[var(--text-secondary)]">7개 카테고리 분석 중... (약 5~10초)</p>
          <div className="mt-3 flex items-center justify-center gap-2">
            <span className="inline-block h-2 w-2 rounded-full bg-blue-400 animate-pulse" />
            <p className="text-[11px] text-blue-400">AI 해석 생성 중...</p>
          </div>
        </div>
      )}

      {result && (
        <div className="space-y-3">
          {/* 기본 정보 요약 */}
          <div className="rounded-2xl border border-[var(--accent-strong)]/20 bg-[var(--surface-strong)] p-5">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <Field label="주소" value={result.address || ""} />
              <Field label="PNU" value={result.pnu || "-"} />
              <Field label="용도지역" value={result.zone_type || "-"} />
              <Field label="대지면적" value={formatArea(result.land_area_sqm)} />
            </div>
          </div>

          {/* AI 종합 요약 */}
          {result.ai_interpretation?.overall_summary && (
            <div className="rounded-2xl border border-[var(--accent-strong)]/30 bg-gradient-to-r from-[var(--accent-strong)]/5 to-transparent p-6">
              <h3 className="text-sm font-bold text-[var(--accent-strong)] mb-2">AI 종합 분석</h3>
              <p className="text-xs text-[var(--text-secondary)] leading-relaxed whitespace-pre-line">
                {result.ai_interpretation.overall_summary}
              </p>
              {result.ai_interpretation.risk_factors && (
                <div className="mt-3 flex gap-4">
                  <div className="flex-1 rounded-lg bg-red-500/5 border border-red-500/20 p-3">
                    <p className="text-[10px] font-bold text-red-400 mb-1">리스크 요인</p>
                    <p className="text-[10px] text-[var(--text-secondary)] whitespace-pre-line">{result.ai_interpretation.risk_factors}</p>
                  </div>
                  <div className="flex-1 rounded-lg bg-emerald-500/5 border border-emerald-500/20 p-3">
                    <p className="text-[10px] font-bold text-emerald-400 mb-1">기회 요인</p>
                    <p className="text-[10px] text-[var(--text-secondary)] whitespace-pre-line">{result.ai_interpretation.opportunity_factors}</p>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* AI 시장분석 종합 해석 (market_interpretation) */}
          {result.market_interpretation && (
            <div className="rounded-2xl border border-emerald-500/25 bg-emerald-500/5 p-6">
              <h3 className="text-sm font-bold text-emerald-400 mb-3">📊 AI 시장분석</h3>
              <div className="space-y-3">
                {result.market_interpretation.market_overview && (
                  <MarketAiBlock label="시장 종합 현황" text={result.market_interpretation.market_overview} />
                )}
                {result.market_interpretation.price_trend_analysis && (
                  <MarketAiBlock label="가격 추이·전망" text={result.market_interpretation.price_trend_analysis} />
                )}
                {result.market_interpretation.comparable_analysis && (
                  <MarketAiBlock label="유사물건 비교" text={result.market_interpretation.comparable_analysis} />
                )}
                {result.market_interpretation.investment_insight && (
                  <MarketAiBlock label="투자 시사점" text={result.market_interpretation.investment_insight} />
                )}
                {result.market_interpretation.risk_factors && (
                  <MarketAiBlock label="시장 리스크" text={result.market_interpretation.risk_factors} />
                )}
                {result.market_interpretation.timing_recommendation && (
                  <MarketAiBlock label="매수·개발 타이밍" text={result.market_interpretation.timing_recommendation} />
                )}
              </div>
            </div>
          )}

          {/* Section 1: 실효용적률 */}
          <SectionCard title="1. 실효용적률 산정" icon="📊" defaultOpen>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              <Field label="법정 건폐율 (국토계획법)" value={`${ef.national_bcr_pct ?? "-"}%`} />
              <Field label="법정 용적률 (국토계획법)" value={`${ef.national_far_pct ?? "-"}%`} />
              <Field label="조례 건폐율 (지자체)" value={`${ef.ordinance_bcr_pct ?? "-"}%`} />
              <Field label="조례 용적률 (지자체)" value={`${ef.ordinance_far_pct ?? "-"}%`} />
              <Field label="실효 건폐율" value={`${ef.effective_bcr_pct ?? "-"}%`} />
              <Field label="실효 용적률" value={`${ef.effective_far_pct ?? "-"}%`} />
            </div>
            {ef.source && <p className="text-[10px] text-[var(--text-hint)] mt-1">출처: {ef.source}</p>}
            {Array.isArray(ef.annotations) && ef.annotations?.length > 0 && (
              <div className="mt-3 rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3 space-y-1.5">
                <p className="text-[10px] font-bold text-[var(--text-hint)] mb-1">분석 근거</p>
                {(ef.annotations ?? []).map((note: string, i: number) => (
                  <AnnotationLine key={i} text={note} />
                ))}
              </div>
            )}
            {result.ai_interpretation?.effective_far_interpretation && (
              <AiInterpretation text={result.ai_interpretation.effective_far_interpretation} />
            )}
          </SectionCard>

          {/* Section 1-B: 용적률 최적화 시뮬레이션 */}
          {ef.far_optimization?.scenarios && (
            <SectionCard title="1-B. 용적률 최적화 시뮬레이션" icon="📈" defaultOpen>
              <div className="grid grid-cols-3 gap-2 mb-3">
                <Field label="현재 기본 용적률" value={`${ef.far_optimization.base_far}%`} />
                <Field label="최대 달성 가능" value={`${ef.far_optimization.max_achievable_far}%`} />
                <Field label="법정 상한" value={`${ef.far_optimization.cap_far}%`} />
              </div>
              {ef.far_optimization.recommended_scenario && (
                <div className="rounded-lg bg-[var(--accent-strong)]/10 border border-[var(--accent-strong)]/30 p-3 mb-3">
                  <p className="text-[10px] font-bold text-[var(--accent-strong)]">추천: {ef.far_optimization.recommended_scenario}</p>
                  <p className="text-[10px] text-[var(--text-secondary)]">{ef.far_optimization.recommended_reason}</p>
                </div>
              )}
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-[var(--line)] text-[var(--text-hint)]">
                      <th className="py-2 px-2 text-left">시나리오</th>
                      <th className="py-2 px-1 text-right">달성 용적률</th>
                      <th className="py-2 px-1 text-right">인센티브</th>
                      <th className="py-2 px-1 text-right">기부체납</th>
                      <th className="py-2 px-1 text-right">연면적 증가</th>
                      <th className="py-2 px-1 text-center">상한</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(ef.far_optimization.scenarios as AnalysisResult[]).map((sc: AnalysisResult, i: number) => (
                      <tr key={i} className={`border-b border-[var(--line)]/50 ${sc.scenario_name === ef.far_optimization.recommended_scenario ? "bg-[var(--accent-strong)]/5" : ""}`}>
                        <td className="py-2 px-2 font-bold text-[var(--text-primary)]">
                          {sc.scenario_name === ef.far_optimization.recommended_scenario && <span className="text-[var(--accent-strong)] mr-1">★</span>}
                          {sc.scenario_name}
                        </td>
                        <td className="py-2 px-1 text-right font-bold text-[var(--accent-strong)]">{sc.achieved_far}%</td>
                        <td className="py-2 px-1 text-right text-[var(--text-secondary)]">+{sc.total_incentive}%</td>
                        <td className="py-2 px-1 text-right text-[var(--text-secondary)]">{sc.donation_pct > 0 ? `${sc.donation_pct}%` : "-"}</td>
                        <td className="py-2 px-1 text-right text-[var(--text-secondary)]">{sc.gfa_increase_sqm > 0 ? `+${sc.gfa_increase_sqm}m²` : "-"}</td>
                        <td className="py-2 px-1 text-center">{sc.is_capped ? <span className="text-amber-400 text-[10px] font-bold">상한</span> : ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </SectionCard>
          )}

          {/* Section 2: 개발방식별 적정공급면적 */}
          <SectionCard title="2. 개발방식별 적정공급면적 산정" icon="🏗️" defaultOpen>
            {supplyAreas.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-[var(--line)] text-[var(--text-hint)]">
                      <th className="py-2 px-2 text-left">개발유형</th>
                      <th className="py-2 px-1 text-right">전용율</th>
                      <th className="py-2 px-1 text-right">공급면적/세대</th>
                      <th className="py-2 px-1 text-right">연면적</th>
                      <th className="py-2 px-1 text-right">세대수</th>
                      <th className="py-2 px-1 text-right">층수</th>
                      <th className="py-2 px-1 text-right">주차</th>
                      <th className="py-2 px-1 text-right">공사비(추정)</th>
                      <th className="py-2 px-1 text-center">인허가</th>
                      <th className="py-2 px-1 text-center">적합성</th>
                    </tr>
                  </thead>
                  <tbody>
                    {supplyAreas.map((sa: AnalysisResult) => (
                      <tr key={sa.dev_type} className={`border-b border-[var(--line)]/50 hover:bg-[var(--surface-soft)] transition-colors ${sa.feasibility_status === "부적합" ? "opacity-50" : ""}`}>
                        <td className="py-2.5 px-2 font-bold text-[var(--text-primary)]">{sa.type_name}</td>
                        <td className="py-2.5 px-1 text-right text-[var(--text-secondary)]">{sa.exclusive_ratio_pct}%</td>
                        <td className="py-2.5 px-1 text-right text-[var(--text-secondary)]">{sa.supply_area_per_unit_pyeong}평</td>
                        <td className="py-2.5 px-1 text-right text-[var(--accent-strong)] font-bold">{sa.total_gfa_pyeong}평</td>
                        <td className="py-2.5 px-1 text-right text-[var(--text-primary)] font-bold">{sa.unit_count}</td>
                        <td className="py-2.5 px-1 text-right text-[var(--text-secondary)]">{sa.floor_count}층</td>
                        <td className="py-2.5 px-1 text-right text-[var(--text-secondary)]">{sa.parking_count}대</td>
                        <td className="py-2.5 px-1 text-right text-[var(--text-secondary)]">{formatWon(sa.estimated_construction_cost_won)}</td>
                        <td className="py-2.5 px-1 text-center"><PermitBadge complexity={sa.permit_complexity} /></td>
                        <td className="py-2.5 px-1 text-center">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${
                            sa.feasibility_status === "적합" ? "bg-emerald-500/20 text-emerald-400" :
                            sa.feasibility_status === "조건부" ? "bg-amber-500/20 text-amber-400" :
                            sa.feasibility_status === "부적합" ? "bg-red-500/20 text-red-400" :
                            "bg-gray-500/20 text-gray-400"
                          }`}>{sa.feasibility_status || "-"}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {/* 유형별 검증 상세 */}
                {supplyAreas.filter((sa: AnalysisResult) => sa.conditions_met?.length > 0).length > 0 && (
                  <div className="mt-3 space-y-2">
                    <p className="text-[10px] font-bold text-[var(--text-hint)]">유형별 법적 조건 검증 상세</p>
                    {supplyAreas.map((sa: AnalysisResult) => {
                      const conditions = sa.conditions_met as AnalysisResult[] | undefined;
                      if (!conditions || conditions.length === 0) return null;
                      return (
                        <div key={sa.dev_type} className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3">
                          <p className="text-[11px] font-bold text-[var(--text-primary)] mb-1">
                            {sa.type_name}
                            <span className={`ml-2 text-[10px] px-1.5 py-0.5 rounded ${
                              sa.feasibility_status === "적합" ? "bg-emerald-500/20 text-emerald-400" :
                              sa.feasibility_status === "부적합" ? "bg-red-500/20 text-red-400" :
                              "bg-amber-500/20 text-amber-400"
                            }`}>{sa.feasibility_status}</span>
                          </p>
                          <div className="space-y-0.5">
                            {conditions.map((c: AnalysisResult, i: number) => (
                              <p key={i} className="text-[10px] text-[var(--text-secondary)]">
                                <span className={`inline-block w-3 h-3 mr-1 rounded-full text-center text-[8px] leading-3 font-bold ${
                                  c.status === "pass" ? "bg-emerald-500/20 text-emerald-400" :
                                  c.status === "fail" ? "bg-red-500/20 text-red-400" :
                                  c.status === "unknown" ? "bg-gray-500/20 text-gray-400" :
                                  "bg-amber-500/20 text-amber-400"
                                }`}>{c.status === "pass" ? "O" : c.status === "fail" ? "X" : "?"}</span>
                                <span className="font-medium">{c.rule}:</span> {c.detail}
                              </p>
                            ))}
                          </div>
                          {sa.recommendations?.length > 0 && (
                            <div className="mt-1 pt-1 border-t border-[var(--line)]">
                              {(sa.recommendations as string[]).map((r: string, i: number) => (
                                <p key={i} className="text-[10px] text-[var(--accent-strong)]">→ {r}</p>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            ) : (
              <p className="text-xs text-[var(--text-hint)] italic">해당 용도지역에서 허용된 개발유형이 없습니다</p>
            )}
            {result.ai_interpretation?.supply_area_interpretation && (
              <AiInterpretation text={result.ai_interpretation.supply_area_interpretation} />
            )}
          </SectionCard>

          {/* Section 3: 토지 주변시세 */}
          <SectionCard title="3. 토지 주변시세" icon="💰">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              <Field label="공시지가 (원/m²)" value={formatManWon(landPrices.official_price_per_sqm / 10000)} />
              <Field label="공시지가 총액" value={formatWon(landPrices.total_official_value_won)} />
              <Field label="추정 시세 (원/m²)" value={formatManWon(landPrices.estimated_market_per_sqm / 10000)} />
              <Field label="추정 시세 총액" value={formatWon(landPrices.total_estimated_value_won)} />
              <Field label="시세 보정계수" value={`×${landPrices.market_multiplier ?? "-"}`} />
            </div>
            {result.ai_interpretation?.land_price_interpretation && (
              <AiInterpretation text={result.ai_interpretation.land_price_interpretation} />
            )}
          </SectionCard>

          {/* Section 4: 물건별 주변 실거래가 */}
          <SectionCard title="4. 물건별 주변 실거래가" icon="🏠">
            {Object.keys(transactions).length > 0 && !transactions.error ? (
              <div className="space-y-2">
                {Object.entries(transactions).map(([type, data]) => {
                  const d = data as AnalysisResult;
                  if (!d || !d.count) return null;
                  return (
                    <div key={type} className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3">
                      <p className="text-xs font-bold text-[var(--text-primary)] mb-1">{type} ({d.count}건)</p>
                      <div className="grid grid-cols-3 gap-2 text-[11px]">
                        <div><span className="text-[var(--text-hint)]">평균: </span><span className="font-bold">{formatManWon(d.avg_price_10k)}</span></div>
                        <div><span className="text-[var(--text-hint)]">최고: </span><span className="font-bold">{formatManWon(d.max_price_10k)}</span></div>
                        <div><span className="text-[var(--text-hint)]">최저: </span><span className="font-bold">{formatManWon(d.min_price_10k)}</span></div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-xs text-[var(--text-hint)] italic">{transactions.error || transactions.message || "실거래 데이터 없음"}</p>
            )}
            {result.ai_interpretation?.transaction_interpretation && (
              <AiInterpretation text={result.ai_interpretation.transaction_interpretation} />
            )}
          </SectionCard>

          {/* Section 5: 물건별 분양가 */}
          <SectionCard title="5. 개발유형별 예상 분양가" icon="🏷️">
            {salePrices.length > 0 ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {salePrices.map((sp: AnalysisResult) => (
                  <div key={sp.dev_type} className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3">
                    <p className="text-[10px] text-[var(--text-hint)]">{sp.type_name}</p>
                    <p className="text-sm font-bold text-[var(--accent-strong)]">{formatManWon(sp.sale_price_per_pyeong_man)}/평</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-[var(--text-hint)] italic">분양가 데이터 없음</p>
            )}
            {result.ai_interpretation?.sale_price_interpretation && (
              <AiInterpretation text={result.ai_interpretation.sale_price_interpretation} />
            )}
          </SectionCard>

          {/* Section 6: 입지분석 */}
          <SectionCard title="6. 입지분석" icon="📍">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              <Field label="입지 점수" value={`${location.location_score ?? "-"}점 (${location.grade ?? "-"})`} />
              {location.transportation?.nearest_subway && (
                <>
                  <Field label="최근접 지하철" value={location.transportation.nearest_subway.name || "-"} />
                  <Field label="지하철 거리" value={`${location.transportation.nearest_subway.distance_m ?? "-"}m`} />
                </>
              )}
              <Field label="인근 학교" value={`${location.education?.school_count ?? 0}개교`} />
            </div>
            {result.ai_interpretation?.location_interpretation && (
              <AiInterpretation text={result.ai_interpretation.location_interpretation} />
            )}
          </SectionCard>

          {/* Section 7: 주변 개발계획 */}
          <SectionCard title="7. 주변 개발계획 및 규제" icon="🗺️">
            {(devPlans.land_use_regulations?.length > 0 || devPlans.special_districts?.length > 0) ? (
              <div className="space-y-2">
                {devPlans.land_use_regulations?.length > 0 && (
                  <div className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3">
                    <p className="text-[10px] font-bold text-[var(--text-hint)] mb-2">토지이용계획 규제</p>
                    <div className="space-y-1">
                      {(devPlans.land_use_regulations ?? []).map((reg: string, i: number) => (
                        <div key={i} className="flex items-center gap-2 text-[11px]">
                          <span className="h-1.5 w-1.5 rounded-full bg-amber-400 shrink-0" />
                          <span className="text-[var(--text-primary)]">{reg}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-xs text-[var(--text-hint)] italic">개발계획/규제 정보 없음</p>
            )}
            {result.ai_interpretation?.development_plan_interpretation && (
              <AiInterpretation text={result.ai_interpretation.development_plan_interpretation} />
            )}
          </SectionCard>

          {/* 분석 시간 */}
          <p className="text-[10px] text-[var(--text-hint)] text-right">분석 시간: {result.analyzed_at}</p>
        </div>
      )}
    </div>
  );
}
