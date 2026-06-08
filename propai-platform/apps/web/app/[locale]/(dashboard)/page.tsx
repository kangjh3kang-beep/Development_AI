import Link from "next/link";
import { HeroGridBackground } from "@/components/dashboard/DashboardDynamicElements";
import { DashboardEsgScore } from "@/components/dashboard/DashboardEsgScore";
import { DashboardKpiLoader } from "@/components/dashboard/DashboardKpiLoader";
import { DashboardProjectLoader } from "@/components/dashboard/DashboardProjectLoader";
import { MarketingPanels } from "@/components/dashboard/MarketingPanels";
import { PromoBanner } from "@/components/dashboard/PromoBanner";
import { OnboardingWizard } from "@/components/onboarding/OnboardingWizard";
import { PipelinePanelClient } from "@/components/pipeline/PipelinePanelClient";
import { Logo } from "@/components/ui/Logo";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type DashboardPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

/**
 * 전용 용어 해설 컴포넌트
 * 용어 위에 마우스를 올리면 정의가 표시됩니다.
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
    <div className="flex flex-col gap-3 pb-12">
      {/* ── 시작 안내 위자드 (최초 방문 시에만 표시) ── */}
      <OnboardingWizard />

      {/* ── 프리미엄 히어로 섹션: AI 커맨드 센터 ── */}
      <section className="relative min-h-[200px] sm:min-h-[260px] lg:min-h-[320px] overflow-hidden rounded-2xl sm:rounded-[2rem] lg:rounded-[3rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5 sm:p-8 lg:p-12 shadow-[var(--shadow-2xl)] transition-all group backdrop-blur-2xl">
        {/* 애니메이션 배경 요소 (Cyber Glows) */}
        <div className="absolute -right-20 -top-20 h-[500px] w-[500px] rounded-full bg-[var(--accent-strong)]/10 blur-[120px] transition-all duration-[3000ms] group-hover:scale-150 group-hover:bg-[var(--accent-strong)]/20" />
        <div className="absolute -bottom-40 left-1/4 h-[400px] w-[400px] rounded-full bg-[var(--data-accent)]/10 blur-[100px] animate-float opacity-60" />
        {/* 그리드 배경 패턴 (사이버틱한 공간감) */}
        <HeroGridBackground />

        <div className="relative z-10 flex flex-col justify-between h-full gap-12 lg:flex-row lg:items-end">
          <div className="max-w-4xl space-y-10">
            <div className="flex items-center gap-3">
              <span className="inline-flex items-center gap-2 rounded-full border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-5 py-2 text-[11px] font-bold uppercase tracking-[0.2em] text-[var(--accent-strong)] backdrop-blur-md">
                <span className="h-2 w-2 rounded-full bg-[var(--accent-strong)] animate-pulse" />
                {dictionary.dashboard.title}
              </span>
            </div>

            <h1 className="text-3xl font-[900] font-display tracking-tighter text-[var(--text-primary)] sm:text-5xl md:text-6xl lg:text-7xl leading-[0.9]">
               <span className="sr-only">{dictionary.meta.siteName}</span>
               <div className="flex justify-start items-center">
                 <Logo size="xl" />
               </div>
            </h1>

            <p className="max-w-xl text-base font-medium leading-relaxed text-[var(--text-secondary)] sm:text-lg lg:text-xl tracking-tight">
              &quot;{(dictionary.dashboard as any).welcome}&quot;
            </p>
          </div>

          <div className="flex flex-col gap-4 sm:flex-row lg:mb-4 shrink-0">
            <Link
              href={`/${locale}/projects/new`}
              className="group/btn flex h-16 items-center justify-center gap-5 rounded-[2rem] bg-gradient-to-br from-[var(--accent-strong)] to-[var(--accent)] px-10 text-lg font-bold text-white shadow-[var(--shadow-glow)] transition-all hover:scale-[1.05] active:scale-[0.95] shrink-0 whitespace-nowrap"
            >
              <span>프로젝트 생성</span>
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-hover/btn:translate-x-1"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
            </Link>
            <Link
              href={`/${locale}/guide`}
              className="flex h-16 items-center justify-center gap-4 rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] px-8 text-base font-bold text-[var(--text-primary)] backdrop-blur-xl transition-all hover:bg-[var(--surface-strong)] shrink-0 whitespace-nowrap"
            >
              이용 가이드
            </Link>
          </div>
        </div>
      </section>

      {/* ── 기능 요약 배너 (유기적 플로팅 카드) ── */}
      <section className="w-full mb-3 mt-1 relative z-10">
        <div className="flex flex-wrap justify-center gap-4 lg:gap-6">
          {[
            {
              title: "전국 데이터 연결",
              desc: "공간정보 통합",
              icon: <svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--accent-strong)] opacity-90"><circle cx="12" cy="5" r="3"/><circle cx="5" cy="19" r="3"/><circle cx="19" cy="19" r="3"/><path d="m7.5 16.5 4.5-9"/><path d="m16.5 16.5-4.5-9"/><path d="M5 19h14"/></svg>
            },
            {
              title: "AI 분석/예측",
              desc: "최적 개발안 도출",
              icon: <svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--accent-strong)] opacity-90"><rect width="16" height="16" x="4" y="4" rx="2"/><rect width="6" height="6" x="9" y="9" rx="1"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="M6 2v2"/><path d="M6 20v2"/><path d="M18 2v2"/><path d="M18 20v2"/><path d="M2 6h2"/><path d="M2 18h2"/><path d="M20 6h2"/><path d="M20 18h2"/></svg>
            },
            {
              title: "개발계획 자동수립",
              desc: "시간과 비용 절감",
              icon: <svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--accent-strong)] opacity-90"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="m9 15 2 2 4-4"/></svg>
            },
            {
              title: "수익성 분석",
              desc: "사업성 극대화",
              icon: <svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--accent-strong)] opacity-90"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/><path d="M12 14v4"/><path d="M16 10v8"/></svg>
            },
            {
              title: "미래가치 창출",
              desc: "지속가능한 개발",
              icon: <svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--accent-strong)] opacity-90"><circle cx="12" cy="12" r="10"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/><path d="M2 12h20"/></svg>
            }
          ].map((item, idx) => (
            <div key={idx} className="flex items-center gap-3 px-4 py-3 lg:px-6 lg:py-4 rounded-2xl bg-[var(--surface-soft)] border border-[var(--line-strong)] shadow-sm hover:shadow-[var(--shadow-glow)] hover:border-[var(--accent)] hover:-translate-y-1 transition-all duration-300 group flex-1 min-w-[200px] w-full sm:w-auto backdrop-blur-md">
              <div className="flex items-center justify-center shrink-0 h-10 w-10 lg:h-12 lg:w-12 rounded-xl bg-gradient-to-br from-[var(--surface-muted)] to-[var(--surface)] border border-[var(--line)] group-hover:border-[var(--accent-strong)]/50 group-hover:scale-110 group-hover:bg-[var(--accent-soft)] transition-all duration-300">
                {item.icon}
              </div>
              <div className="flex flex-col gap-1 min-w-0">
                <p className="text-[14px] lg:text-[15px] font-[800] text-[var(--text-primary)] leading-tight tracking-tight group-hover:text-[var(--accent-strong)] transition-colors truncate">{item.title}</p>
                <p className="text-[12px] lg:text-[13px] font-medium text-[var(--text-secondary)] tracking-tight truncate">{item.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── 사통팔땅 홍보 배너 ── */}
      <PromoBanner />

      {/* ── 자동 분석 진행 단계 ── */}
      <PipelinePanelClient />

      {/* ── 마케팅 홍보 벤토(Bento) 패널 ── */}
      <MarketingPanels />

      {/* ── KPI 그리드: 실시간 API 연동 (fallback 포함) ── */}
      <DashboardKpiLoader />

      {/* ── 대시보드 콘텐츠 레이아웃 ── */}
      <div className="grid gap-4 lg:grid-cols-[1fr_420px]">
        
        {/* 메인 콘텐츠: 진행 단계 모니터링 */}
        <div className="space-y-6">
           <div className="flex items-center justify-between px-1">
              <div className="flex items-center gap-3">
                 <h2 className="text-2xl font-bold tracking-tight text-[var(--text-primary)]">활성 진행 단계</h2>
                 <span className="cc-live"><i />LIVE</span>
              </div>
              <Link href={`/${locale}/projects`} className="cc-label text-[var(--accent-strong)] hover:underline underline-offset-8">전체 보기</Link>
           </div>

           <DashboardProjectLoader locale={locale} />

           {/* ── 포트폴리오 커맨드 맵 — 그리드 + 레이더 모티프 ──
               실데이터(좌표/자산 시각화) 연동 전이므로 가짜 자산점을 찍지 않고
               "데이터 연결 대기" 정직 빈상태로 둔다(무목업 원칙). */}
            <div className="cc-bracketed relative h-[300px] w-full overflow-hidden rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] shadow-[var(--shadow-inner)]">
               <div className="cc-grid-bg cc-grid-bg--radial" />
               <div className="cc-scanline" />
               <i className="cc-bracket cc-bracket--tl" />
               <i className="cc-bracket cc-bracket--tr" />
               <i className="cc-bracket cc-bracket--bl" />
               <i className="cc-bracket cc-bracket--br" />

               {/* 패널 메타 헤더(HUD) */}
               <div className="absolute left-4 top-3 z-10 flex items-center gap-3">
                  <span className="cc-meta">PORTFOLIO · SPATIAL MAP</span>
               </div>
               <div className="absolute right-4 top-3 z-10">
                  <span className="cc-chip-data">STANDBY</span>
               </div>

               <div className="absolute inset-0 flex items-center justify-center">
                  {/* 레이더 링 + 절제된 단일 스윕 */}
                  <div className="relative flex h-40 w-40 items-center justify-center">
                     <div className="absolute inset-0 rounded-full border border-[var(--data-accent-line)] opacity-40" />
                     <div className="absolute inset-6 rounded-full border border-[var(--data-accent-line)] opacity-30" />
                     <div className="absolute inset-12 rounded-full border border-[var(--data-accent-line)] opacity-20" />
                     <div className="cc-radar-sweep" />
                     <div className="relative z-10 flex flex-col items-center gap-2 text-center">
                        <span className="cc-num cc-num--data text-base">⌖</span>
                        <div>
                           <p className="cc-label text-[var(--text-secondary)]">포트폴리오 맵</p>
                           <p className="mt-1 text-[11px] font-medium text-[var(--text-tertiary)]">데이터 연결 대기</p>
                        </div>
                     </div>
                  </div>
               </div>
            </div>
        </div>

        {/* 사이드바 위젯: 시스템 상태 & 규제 */}
        <div className="space-y-6">
           <div className="cc-panel space-y-6 p-6">
              <div>
                 <div className="flex items-center justify-between mb-5">
                    <h4 className="cc-label text-[var(--text-secondary)]">REGULATION FEED</h4>
                    <span className="cc-meta">규제 모니터</span>
                 </div>
                 {/* 규제 동향 실데이터 소스 미연동 → 가짜 항목 대신 정직한 빈상태(무목업) */}
                 <div className="cc-bracketed relative flex flex-col items-center gap-2 rounded-xl border border-dashed border-[var(--line-strong)] bg-[var(--surface)] px-5 py-8 text-center overflow-hidden">
                    <div className="cc-grid-bg opacity-40" />
                    <span className="relative z-10 cc-num text-xl text-[var(--text-tertiary)]">—</span>
                    <p className="relative z-10 text-[13px] font-bold text-[var(--text-primary)]">규제 동향 피드 연동 예정</p>
                    <p className="relative z-10 text-[11px] font-medium text-[var(--text-tertiary)] leading-relaxed">
                       실시간 법령·조례 변경 모니터링을 연결하면<br/>여기에 최신 개정 동향이 표시됩니다.
                    </p>
                    <Link href={`/${locale}/regulations`} className="relative z-10 mt-1 cc-label text-[var(--accent-strong)] hover:underline underline-offset-4">규제 분석 열기 →</Link>
                 </div>
              </div>

              {/* ESG 통합 점수 — 실데이터(/analytics/esg) 로더 */}
              <DashboardEsgScore />
           </div>

           {/* 사용자 시작 안내 카드 */}
           <div className="cc-panel cc-interactive group p-7 space-y-5">
              <div className="cc-grid-bg opacity-40" />
              <div className="relative z-10 space-y-5">
                 <span className="cc-meta">GUIDE · ONBOARDING</span>
                 <h4 className="text-lg font-bold text-[var(--text-primary)] leading-tight tracking-tight">전문 가이드가<br/>필요하신가요?</h4>
                 <p className="text-sm font-medium text-[var(--text-secondary)] leading-relaxed">
                    사통팔땅의 168종 데이터 맵과<br/>AI 엔진을 활용하는 방법을 확인하세요.
                 </p>
                 <Link href={`/${locale}/guide`} className="inline-flex h-12 items-center justify-center rounded-2xl bg-[var(--accent-strong)] px-8 text-[12px] font-bold text-white tracking-wider transition-all hover:scale-105 active:scale-95">
                    시작 안내 시작하기
                 </Link>
              </div>
           </div>
        </div>

      </div>
    </div>
  );
}
