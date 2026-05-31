import Link from "next/link";
import { DashboardKpiLoader } from "@/components/dashboard/DashboardKpiLoader";
import { DashboardProjectLoader } from "@/components/dashboard/DashboardProjectLoader";
import { MarketingPanels } from "@/components/dashboard/MarketingPanels";
import { PromoBanner } from "@/components/dashboard/PromoBanner";
import { OnboardingWizard } from "@/components/onboarding/OnboardingWizard";
import { ProjectPipelinePanel } from "@/components/pipeline/ProjectPipelinePanel";
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
    <div className="flex flex-col gap-8 pb-12">
      {/* ── 온보딩 위자드 (최초 방문 시에만 표시) ── */}
      <OnboardingWizard />

      {/* ── 페이지 헤딩 (Stitch Style) ── */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-slate-900 dark:text-white font-display">
            프로젝트 대시보드
          </h2>
          <p className="text-slate-500 dark:text-slate-400 text-sm">
            활성 개발 사업지 현황 및 AI 예측 개요
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href={`/${locale}/projects/new`}
            className="flex items-center justify-center gap-2 rounded-lg h-10 px-6 bg-primary hover:bg-primary/90 transition-colors text-white text-sm font-bold shadow-lg shadow-primary/25"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="M12 5v14"/></svg>
            <span>프로젝트 생성</span>
          </Link>
        </div>
      </div>

      {/* ── Stats Row (Stitch Style) ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Total Active Projects */}
        <div className="flex flex-col gap-2 rounded-xl p-6 bg-white dark:bg-card-dark border border-slate-200 dark:border-border-dark shadow-sm">
          <div className="flex items-center justify-between">
            <p className="text-slate-500 dark:text-slate-400 text-sm font-medium uppercase tracking-wider">활성 프로젝트</p>
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-primary"><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/></svg>
          </div>
          <div className="flex items-end gap-3 mt-1">
            <p className="text-3xl font-bold text-slate-900 dark:text-white">12</p>
            <div className="flex items-center gap-1 text-emerald-500 text-sm font-bold mb-1">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m22 7-7.5 7.5-5-5L2 17"/><path d="M16 7h6v6"/></svg>
              <span>+2 이번 달</span>
            </div>
          </div>
        </div>

        {/* Budget Deployed */}
        <div className="flex flex-col gap-2 rounded-xl p-6 bg-white dark:bg-card-dark border border-slate-200 dark:border-border-dark shadow-sm">
          <div className="flex items-center justify-between">
            <p className="text-slate-500 dark:text-slate-400 text-sm font-medium uppercase tracking-wider">투입 자본</p>
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-primary"><circle cx="12" cy="12" r="10"/><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"/><path d="M12 18V6"/></svg>
          </div>
          <div className="flex items-end gap-3 mt-1">
            <p className="text-3xl font-bold text-slate-900 dark:text-white">₩145억</p>
            <div className="flex items-center gap-1 text-emerald-500 text-sm font-bold mb-1">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m22 7-7.5 7.5-5-5L2 17"/><path d="M16 7h6v6"/></svg>
              <span>+12% 전년 대비</span>
            </div>
          </div>
        </div>

        {/* AI Risk Alerts */}
        <div className="flex flex-col gap-2 rounded-xl p-6 bg-white dark:bg-card-dark border border-primary/20 dark:border-primary/20 shadow-[0_0_15px_rgba(19,91,236,0.1)] relative overflow-hidden group">
          <div className="absolute -right-4 -top-4 w-24 h-24 bg-primary/10 rounded-full blur-2xl group-hover:bg-primary/20 transition-all" />
          <div className="flex items-center justify-between relative z-10">
            <p className="text-slate-500 dark:text-slate-400 text-sm font-medium uppercase tracking-wider">AI 리스크 알림</p>
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-primary"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
          </div>
          <div className="flex items-end gap-3 mt-1 relative z-10">
            <p className="text-3xl font-bold text-slate-900 dark:text-white">3</p>
            <div className="flex items-center gap-1 text-amber-500 text-sm font-bold mb-1">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/></svg>
              <span>주의 필요</span>
            </div>
          </div>
        </div>
      </div>

      {/* ── 검색 & 필터 (Stitch Style) ── */}
      <div className="flex flex-col md:flex-row gap-4 items-end bg-white dark:bg-card-dark p-4 rounded-xl border border-slate-200 dark:border-border-dark shadow-sm">
        <label className="flex flex-col w-full md:flex-1">
          <span className="text-sm font-medium pb-2 text-slate-500 dark:text-slate-400">프로젝트 검색</span>
          <div className="relative">
            <input
              className="w-full rounded-lg border border-slate-200 dark:border-border-dark bg-white dark:bg-[#111318] h-11 pl-10 pr-4 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all placeholder:text-slate-400 text-slate-900 dark:text-white"
              placeholder="프로젝트 이름 또는 위치로 검색..."
            />
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
          </div>
        </label>
        <label className="flex flex-col w-full md:w-64">
          <span className="text-sm font-medium pb-2 text-slate-500 dark:text-slate-400">상태</span>
          <select className="w-full appearance-none rounded-lg border border-slate-200 dark:border-border-dark bg-white dark:bg-[#111318] h-11 pl-4 pr-10 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all text-slate-700 dark:text-slate-200">
            <option>전체 상태</option>
            <option>진행 중</option>
            <option>보류</option>
            <option>완료</option>
          </select>
        </label>
      </div>

      {/* ── 사통팔땅 홍보 배너 ── */}
      <PromoBanner />

      {/* ── 자동 분석 파이프라인 ── */}
      <ProjectPipelinePanel />

      {/* ── 마케팅 홍보 벤토(Bento) 패널 ── */}
      <MarketingPanels />

      {/* ── KPI 그리드: 실시간 API 연동 (fallback 포함) ── */}
      <DashboardKpiLoader />

      {/* ── 대시보드 콘텐츠 레이아웃 (Stitch Style) ── */}
      <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
        
        {/* 메인 콘텐츠: 파이프라인 모니터링 */}
        <div className="space-y-6">
           <div className="flex items-center justify-between">
              <h2 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white">활성 파이프라인</h2>
              <Link href={`/${locale}/projects`} className="text-xs font-bold text-primary tracking-wider hover:underline underline-offset-8">전체 보기</Link>
           </div>

           <DashboardProjectLoader locale={locale} />

           {/* AI 포트폴리오 지능형 지도 */}
           <div className="relative h-[300px] w-full overflow-hidden rounded-xl border border-slate-200 dark:border-border-dark bg-slate-50 dark:bg-card-dark shadow-sm">
              <div className="absolute inset-0 bg-[linear-gradient(rgba(46,54,70,0.2)_1px,transparent_1px),linear-gradient(90deg,rgba(46,54,70,0.2)_1px,transparent_1px)] bg-[size:24px_24px] opacity-30" />
              <div className="absolute inset-0 flex items-center justify-center">
                 <div className="flex flex-col items-center gap-4 text-center">
                    <div className="h-14 w-14 rounded-xl bg-primary/10 flex items-center justify-center text-primary border border-primary/20">
                       <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 2v20"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                    </div>
                    <div>
                       <h3 className="text-base font-bold text-slate-900 dark:text-white tracking-tight">AI 포트폴리오 인텔리전스 맵</h3>
                       <p className="text-xs font-medium text-slate-500 dark:text-slate-400 tracking-wider mt-1">글로벌 자산 시각화 활성</p>
                    </div>
                 </div>
              </div>
           </div>
        </div>

        {/* 사이드바 위젯: 시스템 상태 & 규제 */}
        <div className="space-y-6">
           <div className="rounded-xl p-6 bg-white dark:bg-card-dark border border-slate-200 dark:border-border-dark shadow-sm space-y-6">
              <div>
                 <h4 className="text-sm font-bold text-slate-900 dark:text-white uppercase tracking-wider mb-4 flex items-center gap-2">
                   <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                   부동산 규제 동향
                 </h4>
                 <div className="space-y-4">
                    {[
                      { title: "건축법 제21조 (개정안)", desc: "친환경 건축물 가산 용적률 상향", date: "24.03.20", type: "업데이트" },
                      { title: "도시정비법 (시행령)", desc: "재건축 초과이익 환수제 완화 지침", date: "24.03.18", type: "중요" },
                    ].map((item, i) => (
                      <div key={i} className="group cursor-pointer">
                         <div className="flex justify-between items-center mb-1">
                            <span className="text-[10px] font-bold text-primary uppercase tracking-wider">{item.type}</span>
                            <span className="text-[10px] font-medium text-slate-400">{item.date}</span>
                         </div>
                         <h5 className="text-sm font-bold text-slate-900 dark:text-white group-hover:text-primary transition-colors">{item.title}</h5>
                         <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed mt-0.5">{item.desc}</p>
                      </div>
                    ))}
                 </div>
              </div>

              <div className="pt-6 border-t border-slate-200 dark:border-border-dark space-y-4">
                 <h4 className="text-sm font-bold text-slate-900 dark:text-white uppercase tracking-wider">ESG 통합 점수</h4>
                 <div className="relative h-36 w-full rounded-xl bg-gradient-to-br from-primary/20 to-blue-600/10 border border-primary/20 flex flex-col items-center justify-center gap-2 overflow-hidden group">
                    <div className="absolute inset-0 bg-primary/5 animate-pulse group-hover:scale-150 transition-transform duration-[3000ms]" />
                    <span className="text-5xl font-[900] text-slate-900 dark:text-white tracking-tighter z-10">84.2</span>
                    <span className="text-[10px] font-bold text-primary tracking-[0.3em] z-10 transition-all group-hover:tracking-[0.5em]">시스템 등급: A+</span>
                 </div>
              </div>
           </div>

           {/* 사용자 온보딩 카드 */}
           <div className="rounded-xl bg-white dark:bg-card-dark border border-slate-200 dark:border-border-dark shadow-sm p-8 space-y-4">
              <h4 className="text-lg font-bold text-slate-900 dark:text-white leading-tight tracking-tight">전문 가이드가<br/>필요하신가요?</h4>
              <p className="text-sm font-medium text-slate-500 dark:text-slate-400 leading-relaxed">
                 사통팔땅의 168종 데이터 맵과<br/>AI 엔진을 활용하는 방법을 확인하세요.
              </p>
              <Link href={`/${locale}/guide`} className="inline-flex h-10 items-center justify-center rounded-lg bg-primary px-6 text-xs font-bold text-white tracking-wider transition-all hover:bg-primary/90 shadow-lg shadow-primary/25">
                 온보딩 시작하기
              </Link>
           </div>
        </div>

      </div>
    </div>
  );
}

