import { Card, CardContent, Badge, Button } from "@propai/ui";
import { motion } from "framer-motion";
import { Gem, Landmark, Target, TrendingDown, TrendingUp, Wallet } from "lucide-react";
import { useParams } from "next/navigation";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useFeasibilityV2Store } from "@/store/use-feasibility-v2-store";
import { FeasibilitySimulationWidget } from "@/components/finance/FeasibilitySimulationWidget";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";

function formatWon(value: number): string {
  if (value == null || !Number.isFinite(value)) return "—";
  if (Math.abs(value) >= 1e12) return `${(value / 1e12).toFixed(1)}조`;
  if (Math.abs(value) >= 1e8) return `${(value / 1e8).toFixed(0)}억`;
  if (Math.abs(value) >= 1e4) return `${(value / 1e4).toFixed(0)}만`;
  return value.toLocaleString();
}

const GRADE_COLORS: Record<string, string> = {
  A: "bg-[var(--accent-strong)] text-white shadow-[var(--shadow-glow)]",
  B: "bg-blue-500 text-white shadow-[0_0_20px_rgba(59,130,246,0.3)]",
  C: "bg-cyan-500 text-white",
  D: "bg-amber-500 text-white",
  E: "bg-orange-500 text-white",
  F: "bg-red-500 text-white",
};

const PIE_COLORS = [
  "var(--accent-strong)", "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
  "#06b6d4", "#ec4899", "#84cc16",
];

/**
 * 전용 용어 해설 컴포넌트
 */
function Term({ children, definition }: { children: React.ReactNode; definition: string }) {
  return (
    <span 
      className="cursor-help border-b border-dotted border-[var(--text-hint)] transition-colors hover:text-[var(--accent-strong)] hover:border-[var(--accent-strong)]"
      title={definition}
    >
      {children}
    </span>
  );
}

const TERM_DEFINITIONS = {
  ROI: "투자자본수익률 (Return on Investment): 투자액 대비 순이익 비율을 나타내는 지표입니다.",
  NPV: "순현재가치 (Net Present Value): 미래에 발생할 현금흐름을 현재 가치로 환산하여 투자 타당성을 평가하는 지표입니다.",
};

/* ── WP-S 신뢰 블록(옵셔널·additive) — /calculate 응답의 evidence[]·legal_refs[] ── */

/** 법령 원문링크 근거(레지스트리 get_legal_refs 출력) — url은 백엔드 제공값만. */
type LegalRef = {
  key?: string | null;
  law_name?: string | null;
  article?: string | null;
  title?: string | null;
  url?: string | null;
  url_status?: string | null;
};

/** 수치 산출 트레이스 1건(EvidencePanel 항목 원천). */
type EvidenceTrace = {
  label?: string | null;
  value?: string | number | null;
  basis?: string | null;
  /** 이 항목과 연결할 법령 근거키(legal_refs[].key와 매칭해 url 주입). */
  legal_ref_key?: string | null;
};

/** evidence[] + legal_refs[]를 EvidencePanel 항목으로 결합(정본 패턴:
 *  ProjectSiteAnalysisWorkspaceClient.buildEvidenceItems와 동일 규약).
 *  legal_ref_key를 legal_refs[].key와 매칭해 url(백엔드 제공값)을 주입하고,
 *  매칭 실패/부재 시 legalRef 생략(텍스트만 — 가짜 링크 금지). 구버전 응답
 *  (두 블록 부재)이면 빈 배열 → EvidencePanel 자체가 렌더되지 않는다(하위호환). */
function buildEvidenceItems(
  evidence?: EvidenceTrace[] | null,
  legalRefs?: LegalRef[] | null,
): EvidenceItem[] {
  const traces = Array.isArray(evidence) ? evidence : [];
  if (traces.length === 0) return [];
  const refIndex: Record<string, LegalRef> = {};
  for (const ref of Array.isArray(legalRefs) ? legalRefs : []) {
    if (ref && typeof ref.key === "string" && ref.key.trim()) {
      refIndex[ref.key.trim()] = ref;
    }
  }
  const items: EvidenceItem[] = [];
  for (const trace of traces) {
    if (!trace || typeof trace !== "object") continue;
    const label = (trace.label ?? "").toString().trim();
    if (!label) continue;
    const value = trace.value ?? "—";
    const key = trace.legal_ref_key?.trim();
    const ref = key ? refIndex[key] : undefined;
    items.push({
      label,
      value: typeof value === "number" ? value : String(value),
      basis: trace.basis ?? null,
      legalRef:
        ref && typeof ref.law_name === "string" && ref.law_name.trim()
          ? {
              lawName: ref.law_name,
              article: ref.article,
              title: ref.title,
              url: ref.url,
            }
          : null,
    });
  }
  return items;
}

export function FeasibilityResultView() {
  const params = useParams();
  const projectId = typeof params.id === 'string' ? params.id : "default-project";
  const { result } = useFeasibilityV2Store();

  // Dictionary for simulation widget (In production, this should come from getDictionary)
  const simulationDict = {
    title: "경제적 민감도 시뮬레이션",
    description: "다양한 경제 변수를 조정하여 수익성의 확률적 변동성을 예측합니다.",
    runBtn: "시뮬레이션 실행",
    runningBtn: "연산 중...",
    inputTitle: "변수 조정 패널",
    outputTitle: "시뮬레이션 결과분포",
    costVol: "사업비 변동성 (±%)",
    interestRate: "목표 이자율",
    salesDelay: "분양/임대 지연율",
    meanNpv: "기대 NPV (평균)",
    var5: "Value-at-Risk (하위 5%)",
    profitIndex: "수익성 지수 (PI)",
  };

  if (!result) {
    return (
      <Card className="rounded-[3rem] border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] shadow-none">
        <CardContent className="p-16 text-center flex flex-col items-center gap-6">
          <div className="h-20 w-20 rounded-3xl bg-[var(--surface-strong)] flex items-center justify-center text-[var(--text-hint)] shadow-[var(--shadow-lg)] border border-[var(--line)]">
             <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21.21 15.89A10 10 0 1 1 8 2.83"/><path d="M22 12A10 10 0 0 0 12 2v10z"/></svg>
          </div>
          <div className="space-y-2">
            <h3 className="text-xl font-[1000] text-[var(--text-primary)]">분석 데이터 준비됨</h3>
            <p className="text-sm font-bold text-[var(--text-secondary)] italic underline decoration-[var(--line)] underline-offset-4">
              입력 탭에서 데이터를 구성한 후 분석을 실행하여 실시간 결과를 확인하세요.
            </p>
          </div>
          <Button variant={"outline" as any} className="mt-4 rounded-full px-10 h-14 border-[var(--line-strong)] hover:bg-[var(--accent-strong)] hover:text-white transition-all font-black text-xs uppercase tracking-widest">분석 가이드 라인 보기</Button>
        </CardContent>
      </Card>
    );
  }

  const kpis = [
    { id: "revenue", label: "총 수입", value: formatWon(result.total_revenue_won), color: "text-[var(--accent-strong)]", icon: Wallet },
    { id: "cost", label: "총 비용", value: formatWon(result.total_cost_won), color: "text-rose-500", icon: TrendingDown },
    { id: "profit", label: "세전 이익", value: formatWon(result.net_profit_won), color: "text-blue-500", icon: TrendingUp },
    { id: "rate", label: "사업 수익률", value: `${result.profit_rate_pct.toFixed(1)}%`, color: "text-cyan-500", icon: Target },
    { id: "roi", label: <Term definition={TERM_DEFINITIONS.ROI}>ROI</Term>, value: `${result.roi_pct.toFixed(1)}%`, color: "text-indigo-500", icon: Landmark },
    { id: "npv", label: <Term definition={TERM_DEFINITIONS.NPV}>NPV</Term>, value: formatWon(result.npv_won), color: "text-[var(--text-primary)]", icon: Gem },
    // ★W3(additive): 월별 DCF 지표 — 백엔드 미산출(null)이면 정직하게 "—" 표기.
    ...(result.cashflow_summary
      ? [
          { id: "irr", label: "IRR(연)", value: result.cashflow_summary.irr_pct != null ? `${result.cashflow_summary.irr_pct.toFixed(1)}%` : "—", color: "text-emerald-500", icon: TrendingUp },
          { id: "payback", label: "회수기간", value: result.cashflow_summary.payback_month != null ? `${result.cashflow_summary.payback_month}개월` : "—", color: "text-amber-500", icon: Target },
          ...(result.cashflow_summary.dscr != null
            ? [{ id: "dscr", label: "DSCR", value: `${result.cashflow_summary.dscr.toFixed(2)}x`, color: "text-sky-500", icon: Landmark }]
            : []),
        ]
      : []),
  ];

  const costData = Object.entries(result.cost_breakdown_won)
    .filter(([, v]) => v > 0)
    .map(([name, value]) => ({ name, value }));

  // ── ★W4(감사 프론트 고아): tax_detail·special_detail 렌더 준비 ──
  // 백엔드가 채워 반환하는데 어떤 화면도 렌더하지 않던 필드 — 세금 4단계 요약과
  // 모듈 특화 상세를 정직 표기(값 부재 시 섹션 자체 미렌더·하위호환).
  const TAX_STAGE_LABELS: Record<string, string> = {
    acquisition: "취득단계", construction: "공사단계", sale: "분양단계", disposal: "양도단계",
  };
  const taxDetail = (result.tax_detail ?? {}) as {
    grand_total_won?: number;
    summary_by_stage?: Record<string, number>;
  } & Record<string, { items?: { code?: string; name?: string; amount_won?: number }[] } | unknown>;
  const taxStages = Object.entries(taxDetail.summary_by_stage ?? {})
    .filter(([k]) => TAX_STAGE_LABELS[k])
    .map(([k, total]) => {
      const stage = taxDetail[k] as { items?: { code?: string; name?: string; amount_won?: number }[] } | undefined;
      const items = (Array.isArray(stage?.items) ? stage.items : [])
        .filter((it) => (it.amount_won ?? 0) > 0)
        .sort((a, b) => (b.amount_won ?? 0) - (a.amount_won ?? 0));
      return { key: k, label: TAX_STAGE_LABELS[k], total: Number(total ?? 0), items };
    });
  const specialEntries = Object.entries(result.special_detail ?? {}).flatMap(([k, v]) => {
    if (typeof v === "number") {
      return [{ key: k, value: k.endsWith("_won") ? formatWon(v) : v.toLocaleString() }];
    }
    if (typeof v === "string" && v) return [{ key: k, value: v }];
    if (v && typeof v === "object") {
      // 1단계 평탄화 — 숫자/문자만(객체는 정직하게 생략).
      return Object.entries(v as Record<string, unknown>)
        .filter(([, sv]) => typeof sv === "number" || (typeof sv === "string" && sv))
        .map(([sk, sv]) => ({
          key: `${k}.${sk}`,
          value: typeof sv === "number" ? (sk.endsWith("_won") ? formatWon(sv) : sv.toLocaleString()) : String(sv),
        }));
    }
    return [];
  });

  // WP-S 산출 근거(옵셔널 가드) — 스토어 타입에 없는 가산 필드는 안전하게 좁혀 읽는다.
  // 구버전 응답(evidence/legal_refs 부재)이면 빈 배열 → 패널 미렌더(기존 화면 무손상).
  const trust = result as typeof result & {
    evidence?: EvidenceTrace[] | null;
    legal_refs?: LegalRef[] | null;
  };
  const backendEvidence = buildEvidenceItems(trust.evidence, trust.legal_refs);
  // ★근거 기본제공(전역원칙): 백엔드가 구조화 evidence를 안 줘도 결과 수치로 산식 트레이스를 구성해
  //   "왜 이 ROI/NPV인가"에 답한다. 백엔드 evidence가 있으면 그것을 우선(가짜 법령URL 0·산식 basis만).
  //   기존엔 evidence 부재 시 빈 배열 → 근거 패널이 통째로 사라져 큰 숫자만 떠 있었다(오도 위험).
  const evidenceItems: EvidenceItem[] = backendEvidence.length > 0 ? backendEvidence : [
    { label: "총 수입", value: formatWon(result.total_revenue_won), basis: "분양·임대 매출 합계" },
    { label: "총 비용", value: formatWon(result.total_cost_won), basis: "토지·공사·금융·기타·세금 등 사업비 전 항목 합계(아래 비용 구성 차트 참조)" },
    { label: "세전 이익", value: formatWon(result.net_profit_won), basis: "총 수입 − 총 비용" },
    { label: "사업 수익률", value: `${result.profit_rate_pct.toFixed(1)}%`, basis: "세전 이익 ÷ 총 수입 × 100" },
    { label: "ROI", value: `${result.roi_pct.toFixed(1)}%`, basis: "세전 이익 ÷ 총 사업비 × 100 — 투입자본 대비 수익률" },
    { label: "NPV", value: formatWon(result.npv_won), basis: result.cashflow_summary?.npv_basis ?? "기간별 현금흐름을 할인율로 현재가치 환산한 순현재가치(할인율·기간은 입력 가정)" },
    ...(result.cashflow_summary?.dscr != null
      ? [{ label: "DSCR", value: `${result.cashflow_summary.dscr.toFixed(2)}x`, basis: result.cashflow_summary.dscr_basis ?? "" }]
      : []),
  ];

  return (
    <div className="space-y-12 animate-premium-fade">
      {/* ── Summary Hero Scorecard ── */}
      <div className="relative overflow-hidden rounded-[3.5rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-10 shadow-[var(--shadow-2xl)]">
         <div className="absolute top-0 right-0 -mr-20 -mt-20 h-64 w-64 rounded-full bg-[var(--accent-strong)] opacity-[0.05] blur-[100px]" />
         <div className="absolute bottom-0 left-0 -ml-20 -mb-20 h-64 w-64 rounded-full bg-blue-500/5 blur-[100px]" />
         
         <div className="relative z-10 grid items-center gap-10 lg:grid-cols-[1fr_auto_1.2fr]">
            {/* Left: Grade Indicator */}
            <div className="flex items-center gap-10">
               <div className={`relative flex h-32 w-32 items-center justify-center rounded-[2.5rem] text-5xl font-[1000] ${GRADE_COLORS[result.grade] ?? "bg-slate-700"} ring-8 ring-[var(--line-strong)]/50`}>
                  {result.grade}
                  <div className="absolute -bottom-2 -right-2 flex h-10 w-10 items-center justify-center rounded-2xl bg-[var(--surface)] text-[10px] font-black text-[var(--accent-strong)] shadow-lg border border-[var(--line-strong)]">
                    AI
                  </div>
               </div>
               <div className="space-y-2">
                  <div className="inline-flex items-center gap-2 rounded-full border border-[var(--accent-strong)]/20 bg-[var(--accent-soft)] px-3 py-1 label-caps text-[var(--accent-strong)]">
                    Real-time Analysis
                  </div>
                  <h3 className="text-3xl font-[1000] tracking-tight text-[var(--text-primary)] leading-tight">{result.module_name}</h3>
                  <div className="flex items-center gap-3">
                     <span className="text-xs font-black text-[var(--text-primary)] tracking-widest decoration-[var(--accent-strong)]/30 underline decoration-2 underline-offset-4">
                        {result.development_type}
                     </span>
                     <span className="text-[10px] font-[1000] text-[var(--text-hint)] uppercase tracking-[0.2em]">v58.5-ADVANCED</span>
                  </div>
               </div>
            </div>

            {/* Middle: Divider */}
            <div className="hidden h-24 w-px bg-[var(--line-strong)] lg:block opacity-50" />

            {/* Right: Primary ROI Gauge Result */}
            <div className="flex flex-wrap items-center gap-12 lg:justify-end">
               <div className="flex flex-col">
                  <span className="label-caps text-[var(--text-hint)] mb-2">Expected ROI</span>
                  <div className="flex items-baseline gap-2">
                     <span className="text-6xl font-[1000] text-[var(--accent-strong)] tracking-tighter">{result.roi_pct.toFixed(2)}</span>
                     <span className="text-xl font-black text-[var(--accent-strong)] opacity-60">%</span>
                  </div>
               </div>
               <div className="flex flex-col">
                  <span className="label-caps text-[var(--text-hint)] mb-2">Net Value (NPV)</span>
                  <div className="flex items-baseline gap-2">
                     <span className="text-3xl font-[1000] text-[var(--text-primary)] tracking-tight">{formatWon(result.npv_won)}</span>
                  </div>
               </div>
            </div>
         </div>
      </div>

      {/* ── KPI Grid ── */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {kpis.map((kpi, i) => (
          <motion.div
            key={kpi.id}
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: i * 0.05 }}
            className="flex"
          >
            <Card className="group flex-1 rounded-[2.5rem] border-[var(--line-strong)] bg-[var(--surface-strong)] transition-all duration-500 hover:scale-[1.05] hover:shadow-[var(--shadow-2xl)] hover:border-[var(--accent-strong)]/30 overflow-hidden">
              <CardContent className="p-8">
                <div className="mb-6 flex items-center justify-between">
                   <div className={`h-10 w-10 rounded-2xl bg-[var(--surface-soft)] flex items-center justify-center shadow-[var(--shadow-sm)] border border-[var(--line)] ${kpi.color}`}>
                      <kpi.icon className="size-5" aria-hidden />
                   </div>
                   <span className="text-[9px] font-[1000] uppercase tracking-[0.3em] text-[var(--text-hint)] group-hover:text-[var(--accent-strong)] transition-colors">{kpi.label}</span>
                </div>
                <div className="space-y-1">
                  <p className={`text-2xl font-[1000] tracking-tighter ${kpi.color}`}>{kpi.value}</p>
                  <div className="h-1 w-10 rounded-full bg-[var(--line)] group-hover:w-full group-hover:bg-[var(--accent-strong)]/50 transition-all duration-1000" />
                </div>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>

      {/* ── Real-time Financial Sensitivity Simulation ── */}
      <section className="space-y-6">
        <div className="flex items-center gap-3">
          <div className="h-2 w-10 rounded-full bg-[var(--accent-strong)]" />
          <h4 className="text-xl font-[1000] tracking-tighter text-[var(--text-primary)] uppercase">Financial Sensitivity Matrix</h4>
        </div>
        <Card className="rounded-[3.5rem] border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)] overflow-hidden">
          <CardContent className="p-10">
            <FeasibilitySimulationWidget projectId={projectId} dictionary={simulationDict} />
          </CardContent>
        </Card>
      </section>

      {/* ── Charts Section ── */}
      <div className="grid gap-8">
        {/* Cost Breakdown Chart */}
        <Card className="rounded-[3.5rem] border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)] overflow-hidden">
          <CardContent className="p-12">
            <div className="mb-10 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h4 className="text-2xl font-[1000] text-[var(--text-primary)] tracking-tighter">상세 비용 구조 분석</h4>
                <div className="flex items-center gap-2 mt-1">
                  <div className="h-1.5 w-1.5 rounded-full bg-[var(--accent-strong)]" />
                  <p className="text-[10px] font-black text-[var(--text-hint)] uppercase tracking-[0.4em]">Granular Cost Allocation Matrix</p>
                </div>
              </div>
              <Badge variant={"outline" as any} className="rounded-xl px-5 py-2 font-black text-[10px] border-[var(--line-strong)] text-[var(--text-secondary)] uppercase tracking-widest bg-[var(--surface-soft)]">
                Total Basis: {formatWon(result.total_cost_won)}
              </Badge>
            </div>
            
            <div className="h-[400px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <defs>
                    {PIE_COLORS.map((color, i) => (
                      <linearGradient key={`grad-${i}`} id={`grad-${i}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={color} stopOpacity={1} />
                        <stop offset="100%" stopColor={color} stopOpacity={0.4} />
                      </linearGradient>
                    ))}
                  </defs>
                  <Pie
                    data={costData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={100}
                    outerRadius={140}
                    paddingAngle={8}
                    stroke="none"
                  >
                    {costData.map((_, i) => (
                      <Cell key={`cell-${i}`} fill={`url(#grad-${i % PIE_COLORS.length})`} className="outline-none focus:outline-none transition-all duration-300 hover:opacity-80" />
                    ))}
                  </Pie>
                  <Tooltip 
                    contentStyle={{ borderRadius: '2rem', border: '1px solid var(--line-strong)', backgroundColor: 'var(--surface)', boxShadow: 'var(--shadow-2xl)', padding: '1.5rem', fontWeight: 'bold' }}
                    itemStyle={{ color: 'var(--text-primary)' }}
                    formatter={(v) => [formatWon(Number(v ?? 0)), '비용 규모']}
                  />
                  <Legend 
                    verticalAlign="bottom" 
                    height={36} 
                    iconType="circle"
                    formatter={(value) => <span className="text-[10px] font-black text-[var(--text-secondary)] uppercase tracking-widest">{value}</span>}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>

            {/* 산출 근거(WP-S evidence[]+legal_refs[]) — 항목이 없으면(구버전 응답) 자동 미표시. */}
            <EvidencePanel title="산출 근거" items={evidenceItems} className="mt-8" />

            {/* ── ★W4: 세금 상세(4단계) — 종전 미렌더 고아 필드의 정직 표기 ── */}
            {taxStages.length > 0 && (
              <div className="mt-8 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-6">
                <div className="mb-4 flex items-center justify-between">
                  <h5 className="text-sm font-black text-[var(--text-primary)]">제세공과금 상세 (4단계)</h5>
                  {typeof taxDetail.grand_total_won === "number" && (
                    <span className="text-xs font-black text-[var(--text-secondary)]">합계 {formatWon(taxDetail.grand_total_won)}</span>
                  )}
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  {taxStages.map((st) => (
                    <div key={st.key} className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-4">
                      <div className="mb-2 flex items-center justify-between">
                        <span className="text-[11px] font-black text-[var(--text-secondary)]">{st.label}</span>
                        <span className="text-[11px] font-black text-[var(--text-primary)]">{formatWon(st.total)}</span>
                      </div>
                      {st.items.length > 0 ? (
                        <ul className="space-y-1">
                          {st.items.slice(0, 6).map((it) => (
                            <li key={`${st.key}-${it.code}`} className="flex items-center justify-between text-[11px] text-[var(--text-secondary)]">
                              <span>{it.name ?? it.code}</span>
                              <span className="cc-num">{formatWon(it.amount_won ?? 0)}</span>
                            </li>
                          ))}
                          {st.items.length > 6 && (
                            <li className="text-[10px] text-[var(--text-hint)]">외 {st.items.length - 6}건</li>
                          )}
                        </ul>
                      ) : (
                        <p className="text-[10px] text-[var(--text-hint)]">부과 항목 없음</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ── ★W4: 모듈 특화 상세(special_detail) — 종전 미렌더 고아 필드 ── */}
            {specialEntries.length > 0 && (
              <div className="mt-6 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-6">
                <h5 className="mb-3 text-sm font-black text-[var(--text-primary)]">모듈 특화 상세</h5>
                <div className="grid gap-2 sm:grid-cols-2">
                  {specialEntries.map((e) => (
                    <div key={e.key} className="flex items-center justify-between rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-[11px]">
                      <span className="text-[var(--text-secondary)]">{e.key}</span>
                      <span className="cc-num font-semibold text-[var(--text-primary)]">{e.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
        {/* AI 총평 카드 제거(무목업) — 데이터 출처 없이 "성수역 12%·92PT"를 상수로 렌더하던 블록.
           FeasibilityResult 에 총평/점수 필드가 없고, 실제 AI 산출물은 같은 탭의
           AIRecommendationPanel(/feasibility/recommendations 응답)이 담당한다. */}
      </div>
    </div>
  );
}
