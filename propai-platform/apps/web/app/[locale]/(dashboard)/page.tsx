import Link from "next/link";
import { DashboardClientPanel } from "@/components/dashboard/DashboardClientPanel";
import { OverviewCard } from "@/components/layout/OverviewCard";
import { PwaStatusCard } from "@/components/pwa/PwaStatusCard";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type DashboardPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

/**
 * 전용 용어 해설 컴포넌트
 */
function Term({ children, definition }: { children: React.ReactNode; definition: string }) {
  return (
    <span 
      className="cursor-help border-b border-dotted border-[var(--text-tertiary)] transition-colors hover:text-[var(--accent)] hover:border-[var(--accent)]"
      title={definition}
    >
      {children}
    </span>
  );
}

const TERM_DEFINITIONS = {
  ROI: "투자자본수익률 (Return on Investment): 투자액 대비 순이익 비율",
  NPV: "순현재가치 (Net Present Value): 미래 현금흐름의 현재가치 합계",
  LCA: "전과정평가 (Life Cycle Assessment): 기획부터 폐기까지의 환경 영향 분석",
  LCC: "생애주기비용 (Life Cycle Cost): 건축물 수명 주기 동안의 총 비용",
  ESG: "환경(E), 사회(S), 지배구조(G): 기업의 지속가능성 평가지표",
  "G-SEED": "녹색건축인증제도: 건축물의 친환경성을 등급으로 인증하는 제도",
};

export default async function DashboardPage({ params }: DashboardPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  const dictionary = await getDictionary(locale as Locale);

  return (
    <div className="flex flex-col gap-10 pb-20">
      {/* ── Premium Hero Section: Command Center ── */}
      <section className="relative min-h-[480px] overflow-hidden rounded-[3.5rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-12 lg:p-20 shadow-[var(--shadow-2xl)] transition-all group">
        {/* Animated Background Elements */}
        <div className="absolute -right-20 -top-20 h-[500px] w-[500px] rounded-full bg-[var(--accent-strong)]/10 blur-[120px] transition-all duration-[2000ms] group-hover:scale-150" />
        <div className="absolute -bottom-40 left-1/4 h-[400px] w-[400px] rounded-full bg-blue-600/10 blur-[100px] animate-float opacity-50" />
        <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')] opacity-[0.03] dark:invert" />
        <div className="absolute inset-0 bg-[linear-gradient(var(--line-subtle)_1px,transparent_1px),linear-gradient(90deg,var(--line-subtle)_1px,transparent_1px)] bg-[size:40px_40px] opacity-20" />

        <div className="relative z-10 flex flex-col justify-between h-full gap-12 lg:flex-row lg:items-end">
          <div className="max-w-4xl space-y-10">
            <div className="flex items-center gap-3">
              <span className="inline-flex items-center gap-2 rounded-full border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-5 py-2 text-[10px] font-black uppercase tracking-[0.3em] text-[var(--accent-strong)] backdrop-blur-md">
                <span className="h-2 w-2 rounded-full bg-[var(--accent-strong)] animate-pulse" />
                {dictionary.dashboard.title}
              </span>
            </div>
            
            <h1 className="text-6xl font-[1000] tracking-tighter text-[var(--text-primary)] sm:text-7xl lg:text-8xl leading-[0.9]">
               <span className="bg-gradient-to-r from-[var(--text-primary)] to-[var(--accent-strong)] bg-clip-text text-transparent">{dictionary.meta.siteName}</span>
               <span className="text-[var(--accent-strong)]">.</span>
            </h1>

            <p className="max-w-xl text-xl font-medium leading-relaxed text-[var(--text-secondary)] sm:text-2xl tracking-tight underline decoration-[var(--line-strong)] decoration-2 underline-offset-8">
              &quot;{(dictionary.dashboard as any).welcome}&quot;
            </p>
          </div>

          <div className="flex flex-col gap-4 sm:flex-row lg:mb-4 shrink-0">
            <Link
              href={`/${locale}/projects/new`}
              className="group flex h-20 items-center justify-center gap-6 rounded-[2.5rem] bg-gradient-to-br from-[var(--accent-strong)] to-teal-700 px-12 text-xl font-black text-white shadow-[var(--shadow-glow)] transition-all hover:scale-[1.05] active:scale-[0.95] shrink-0 whitespace-nowrap"
            >
              <span>{dictionary.nav.projects} 생성</span>
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-hover:translate-x-2"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
            </Link>
            <Link
              href={`/${locale}/guide`}
              className="flex h-20 items-center justify-center gap-4 rounded-[2.5rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] px-10 text-lg font-black text-[var(--text-primary)] backdrop-blur-xl transition-all hover:bg-[var(--surface-strong)] shrink-0 whitespace-nowrap"
            >
              {dictionary.nav.report}
            </Link>
          </div>
        </div>
      </section>

      {/* ── KPI Grid: Real-time Intelligence ── */}
      <div className="grid gap-8 md:grid-cols-3">
        {[
          { label: "전체 포트폴리오 자산", value: "3,500.2", unit: "B", trend: "+12.5%", sub: "Total Assets Under Management", color: "text-teal-600 dark:text-teal-400", bg: "bg-teal-500/5 dark:bg-teal-500/10", border: "border-teal-500/20" },
          { label: "평균 프로젝트 ROI", value: "18.4", unit: "%", trend: "+2.1%", sub: "Across 12 Major Projects", color: "text-blue-600 dark:text-blue-400", bg: "bg-blue-500/5 dark:bg-blue-500/10", border: "border-blue-500/20" },
          { label: "탄소 배출 절감률", value: "24.9", unit: "%", trend: "-1.5%", sub: "Life Cycle Assessment (LCA)", color: "text-emerald-600 dark:text-emerald-400", bg: "bg-emerald-500/5 dark:bg-emerald-500/10", border: "border-emerald-500/20" },
        ].map((item, i) => (
          <div key={i} className={`group relative overflow-hidden rounded-[2.5rem] border ${item.border} ${item.bg} p-8 transition-all hover:border-[var(--accent)] hover:scale-[1.02] shadow-[var(--shadow-sm)]`}>
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-black uppercase tracking-[0.2em] text-[var(--text-tertiary)]">{item.label}</span>
              <span className={`text-[10px] font-black ${item.color} px-2 py-1 rounded-full bg-white/10 dark:bg-black/20`}>{item.trend}</span>
            </div>
            <div className="mt-6 flex items-baseline gap-2">
              <h3 className="text-6xl font-black tracking-tighter text-[var(--text-primary)]">{item.value}</h3>
              <span className="text-xl font-bold text-[var(--text-tertiary)]">{item.unit}</span>
            </div>
            <p className="mt-4 text-[10px] font-bold text-[var(--text-hint)] uppercase tracking-widest">{item.sub}</p>
          </div>
        ))}
      </div>

      {/* ── Dashboard Content Layout ── */}
      <div className="grid gap-12 lg:grid-cols-[1fr_420px]">
        
        {/* Main Content: Pipeline Monitoring */}
        <div className="space-y-8">
           <div className="flex items-center justify-between px-4">
              <h2 className="text-2xl font-black tracking-tight text-white uppercase">Pipeline Active <span className="text-teal-500">_</span></h2>
              <Link href={`/${locale}/projects`} className="text-xs font-black text-teal-400 uppercase tracking-widest hover:underline underline-offset-8">Browse All</Link>
           </div>

           <div className="grid gap-6 sm:grid-cols-2">
               {([
                 { id: "demo-gangnam", name: "강남 게이트웨이 복합시설", status: "AI DESIGN STAGE", value: "12,940", tag: "ULTRA", progress: 68 },
                 { id: "demo-songdo", name: "송도 이노베이션 루프", status: "FEASIBILITY AUDIT", value: "8,210", tag: "CORE", progress: 42 },
               ] as const).map((proj) => (
                 <Link href={`/${locale}/projects/${proj.id}`} key={proj.id} className="group relative rounded-[2.5rem] border border-[var(--line)] bg-[var(--surface)] p-8 transition-all hover:border-[var(--accent)] hover:bg-[var(--accent-soft)] shadow-[var(--shadow-sm)]">
                    <div className="flex items-center justify-between mb-6">
                       <span className="rounded-lg bg-[var(--surface-muted)] px-3 py-1 text-[9px] font-black text-[var(--text-tertiary)]">{proj.tag}</span>
                       <div className="h-8 w-8 rounded-full border border-[var(--line)] flex items-center justify-center transition-all group-hover:bg-[var(--accent)] group-hover:border-[var(--accent)]">
                         <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--text-primary)] group-hover:text-white transition-colors"><path d="m9 18 6-6-6-6"/></svg>
                       </div>
                    </div>
                    <h4 className="text-xl font-black text-[var(--text-primary)] leading-tight mb-2">{proj.name}</h4>
                    <p className="text-[10px] font-black text-[var(--accent-strong)] uppercase tracking-widest mb-8">{proj.status}</p>
                    
                    <div className="space-y-2">
                       <div className="flex justify-between text-[10px] font-black uppercase text-[var(--text-hint)]">
                         <span>Overall Progress</span>
                         <span>{proj.progress}%</span>
                       </div>
                       <div className="h-1.5 w-full rounded-full bg-[var(--line)]">
                         <div className="h-full rounded-full bg-gradient-to-r from-[var(--accent)] to-blue-500 transition-all duration-1000 group-hover:w-full" style={{ width: `${proj.progress}%` }} />
                       </div>
                    </div>
                 </Link>
               ))}
           </div>

           {/* Quick Action Map Container Placeholder */}
            <div className="relative h-[300px] w-full overflow-hidden rounded-[2.5rem] border border-[var(--line)] bg-[var(--surface-soft)] shadow-[var(--shadow-inner)]">
               <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/diagmonds-light.png')] opacity-5" />
               <div className="absolute inset-0 flex items-center justify-center">
                  <div className="flex flex-col items-center gap-4 text-center">
                     <div className="h-16 w-16 rounded-3xl bg-[var(--accent-soft)] flex items-center justify-center text-[var(--accent-strong)] border border-[var(--accent-strong)]/20 shadow-[var(--shadow-md)]">
                        <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 2v20"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                     </div>
                     <div>
                        <h3 className="text-lg font-[900] text-[var(--text-primary)] uppercase tracking-tight">AI Portfolio Intelligence Map</h3>
                        <p className="text-xs font-bold text-[var(--text-tertiary)] uppercase tracking-widest">Global Asset Visualization Active</p>
                     </div>
                  </div>
               </div>
            </div>
        </div>

        {/* Sidebar Widgets: System Health & Compliance */}
        <div className="space-y-8">
           <div className="glass rounded-[2.5rem] p-8 border border-[var(--line)] shadow-2xl space-y-8">
              <div>
                 <h4 className="text-sm font-black text-[var(--text-primary)] uppercase tracking-[0.2em] mb-6 flex items-center gap-2">
                   <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                   Market Regulations
                 </h4>
                 <div className="space-y-6">
                    {[
                      { title: "건축법 제21조 (개정안)", desc: "친환경 건축물 가산 용적률 상향", date: "24.03.20", type: "UPDATE" },
                      { title: "도시정비법 (시행령)", desc: "재건축 초과이익 환수제 완화 지침", date: "24.03.18", type: "CRITICAL" },
                    ].map((item, i) => (
                      <div key={i} className="group cursor-pointer">
                         <div className="flex justify-between items-center mb-1">
                            <span className="text-[9px] font-black text-teal-400 uppercase tracking-widest">{item.type}</span>
                            <span className="text-[9px] font-black text-[var(--text-hint)]">{item.date}</span>
                         </div>
                         <h5 className="text-[13px] font-black text-[var(--text-primary)] group-hover:text-teal-400 transition-colors uppercase">{item.title}</h5>
                         <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed italic">{item.desc}</p>
                      </div>
                    ))}
                 </div>
              </div>

              <div className="pt-8 border-t border-[var(--line)] space-y-6">
                 <h4 className="text-sm font-black text-[var(--text-primary)] uppercase tracking-[0.2em] mb-4">ESG Integrated Score</h4>
                 <div className="relative h-40 w-full rounded-2xl bg-gradient-to-br from-indigo-500/20 to-purple-600/20 border border-indigo-500/20 flex flex-col items-center justify-center gap-2 overflow-hidden group">
                    <div className="absolute inset-0 bg-indigo-500/5 animate-pulse group-hover:scale-150 transition-transform duration-[3000ms]" />
                    <span className="text-5xl font-black text-[var(--text-primary)] tracking-tighter z-10">84.2</span>
                    <span className="text-[10px] font-black text-indigo-400 uppercase tracking-[0.4em] z-10 transition-all group-hover:tracking-[0.6em]">System Rating: A+</span>
                 </div>
              </div>
           </div>

           {/* User Onboarding Card */}
           <div className="rounded-[2.5rem] bg-gradient-to-br from-teal-500/10 to-blue-500/10 p-1 border border-white/10 group overflow-hidden">
              <div className="rounded-[2.5rem] bg-[#0a0f14] p-10 space-y-6 transition-all group-hover:bg-transparent">
                 <h4 className="text-lg font-black text-white leading-tight uppercase tracking-tight">Need a professional<br/>Guide?</h4>
                 <p className="text-xs font-medium text-white/40 leading-relaxed italic">
                    사통팔땅의 168종 데이터 맵과<br/>AI 엔진을 활용하는 방법을 확인하세요.
                 </p>
                 <Link href={`/${locale}/guide`} className="inline-flex h-12 items-center justify-center rounded-2xl bg-white px-8 text-[11px] font-black text-black uppercase tracking-widest transition-all hover:scale-105 active:scale-95">
                    Start Onboarding
                 </Link>
              </div>
           </div>
        </div>

      </div>
    </div>
  );
}
