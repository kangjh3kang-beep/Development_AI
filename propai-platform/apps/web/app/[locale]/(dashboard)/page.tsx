import Link from "next/link";
import { HeroGridBackground } from "@/components/dashboard/DashboardDynamicElements";
import { DashboardEsgScore } from "@/components/dashboard/DashboardEsgScore";
import { DashboardKpiLoader } from "@/components/dashboard/DashboardKpiLoader";
import { DashboardProjectLoader } from "@/components/dashboard/DashboardProjectLoader";
import { MarketingPanels } from "@/components/dashboard/MarketingPanels";
import { PalatriaBanner } from "@/components/dashboard/PalatriaBanner";
import { PromoBanner } from "@/components/dashboard/PromoBanner";
import { OnboardingWizard } from "@/components/onboarding/OnboardingWizard";
import { PipelinePanelClient } from "@/components/pipeline/PipelinePanelClient";
import { isValidLocale } from "@/i18n/config";

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

  return (
    <div className="flex flex-col gap-12 pb-16">
      {/* ── 시작 안내 위자드 (최초 방문 시에만 표시) ── */}
      <OnboardingWizard />

      {/* ── 히어로 섹션: 절제된 커맨드 센터(장식 제거·여백이 디자인) ── */}
      <section className="db-hero p-8 sm:p-12 lg:p-16">
        {/* 미묘한 깊이감을 위한 정밀 그리드만 유지(컬러 글로우는 제거) */}
        <HeroGridBackground />

        {/* 왼쪽 배경: '지도 위에서 AI가 분석하는' 느낌의 생동감 레이어.
            지도 좌표 그리드 + 분석 노드(펄스) + 가로로 천천히 지나가는 스캔 빔.
            텍스트 가독성을 위해 저투명도·단일 파랑이며, 오른쪽으로 갈수록 사라진다(mask).
            모션을 끄는 사용자 설정(prefers-reduced-motion)에선 애니메이션이 멈춘다. */}
        <div className="db-hero__viz" aria-hidden="true" />

        <div className="relative z-10 flex flex-col justify-between gap-12 lg:flex-row lg:items-end">
          <div className="max-w-3xl space-y-6">
            {/* eyebrow: 자사 슬로건 대신 차분한 분야 라벨로 축소(C2) */}
            <span className="db-eyebrow db-eyebrow--ko">
              <i />
              부동산 개발 분석
            </span>

            {/* C1: 히어로 중앙 대형 로고/태그라인 제거 → 가치제안 한 줄 헤드라인만.
                로고는 사이드바 1곳에만 남긴다. */}
            <h1 className="db-hero__headline text-[var(--text-primary)]">
              개발사업의 필수 플랫폼! 주소만 입력하면, 시장조사·사업성·수지 분석을 한 번에.
            </h1>

            <p className="max-w-xl text-lg leading-relaxed text-[var(--text-secondary)] sm:text-xl">
              전국 필지 데이터와 AI 분석 엔진으로 개발 전 과정을 한 흐름에서 검증합니다.
            </p>
          </div>

          <div className="flex shrink-0 flex-col gap-3 sm:flex-row">
            {/* 강조(accent)는 핵심 행동 단 1곳에만 — 프로젝트 생성 */}
            <Link
              href={`/${locale}/projects/new`}
              className="group/btn flex h-14 items-center justify-center gap-3 rounded-2xl bg-[var(--accent-strong)] px-8 text-base font-semibold text-white transition-all duration-200 hover:opacity-90 active:scale-[0.98]"
            >
              <span>프로젝트 생성</span>
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="transition-transform duration-200 group-hover/btn:translate-x-0.5"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
            </Link>
            <Link
              href={`/${locale}/guide`}
              className="flex h-14 items-center justify-center rounded-2xl border border-[var(--line)] bg-[var(--surface)] px-8 text-base font-semibold text-[var(--text-primary)] transition-colors duration-200 hover:border-[var(--line-strong)]"
            >
              이용 가이드
            </Link>
          </div>
        </div>
      </section>

      {/* ── 기능 요약: 떠다니는 카드 대신 헤어라인으로 칸을 나눈 한 줄(절제) ── */}
      <section className="relative z-10">
        <div className="db-feature-row">
          {[
            {
              title: "전국 데이터 연결",
              desc: "공간정보 통합",
              icon: <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="db-feature-icon"><circle cx="12" cy="5" r="3"/><circle cx="5" cy="19" r="3"/><circle cx="19" cy="19" r="3"/><path d="m7.5 16.5 4.5-9"/><path d="m16.5 16.5-4.5-9"/><path d="M5 19h14"/></svg>
            },
            {
              title: "AI 분석·예측",
              desc: "최적 개발안 도출",
              icon: <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="db-feature-icon"><rect width="16" height="16" x="4" y="4" rx="2"/><rect width="6" height="6" x="9" y="9" rx="1"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="M6 2v2"/><path d="M6 20v2"/><path d="M18 2v2"/><path d="M18 20v2"/><path d="M2 6h2"/><path d="M2 18h2"/><path d="M20 6h2"/><path d="M20 18h2"/></svg>
            },
            {
              title: "개발계획 자동수립",
              desc: "시간·비용 절감",
              icon: <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="db-feature-icon"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="m9 15 2 2 4-4"/></svg>
            },
            {
              title: "수익성 분석",
              desc: "사업성 극대화",
              icon: <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="db-feature-icon"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/><path d="M12 14v4"/><path d="M16 10v8"/></svg>
            },
            {
              title: "미래가치 창출",
              desc: "지속가능한 개발",
              icon: <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="db-feature-icon"><circle cx="12" cy="12" r="10"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/><path d="M2 12h20"/></svg>
            }
          ].map((item, idx) => (
            <div key={idx} className="db-feature-cell">
              {item.icon}
              <div className="min-w-0">
                <p className="db-feature-title truncate">{item.title}</p>
                <p className="db-feature-desc truncate">{item.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── 스카이게러지 팔라트리아 배너(분양광고 배너 위) ── */}
      <PalatriaBanner />

      {/* ── 사통팔땅 홍보 배너 ── */}
      <PromoBanner />

      {/* ── 자동 분석 진행 단계 ── */}
      <PipelinePanelClient />

      {/* ── 마케팅 홍보 벤토(Bento) 패널 ── */}
      <MarketingPanels />

      {/* ── KPI 그리드: 실시간 API 연동 (fallback 포함) ── */}
      <DashboardKpiLoader />

      {/* ── 대시보드 콘텐츠 레이아웃 ── */}
      <div className="grid gap-8 lg:grid-cols-[1fr_400px]">

        {/* 메인 콘텐츠: 진행 단계 모니터링 */}
        <div className="space-y-6">
           <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                 <h2 className="db-section-title">활성 진행 단계</h2>
                 {/* 실시간 표시 — 네온 시안 대신 파랑 펄스 도트(C2) */}
                 <span className="db-live"><i />실시간</span>
              </div>
              <Link href={`/${locale}/projects`} className="db-eyebrow db-eyebrow--ko text-[var(--accent-strong)] hover:opacity-80 transition-opacity">전체 보기</Link>
           </div>

           <DashboardProjectLoader locale={locale} />

           {/* ── 포트폴리오 커맨드 맵 — 그리드 + 레이더 모티프 ──
               실데이터(좌표/자산 시각화) 연동 전이므로 가짜 자산점을 찍지 않고
               "데이터 연결 대기" 정직 빈상태로 둔다(무목업 원칙). */}
            {/* 포트폴리오 공간 맵 — 게임 HUD 톤(네온 시안/레이더/모노 영문) 폐기.
                차분한 단일 파랑 + 한국어 라벨로 통일(C2). */}
            <div className="relative h-[300px] w-full overflow-hidden rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] shadow-[var(--shadow-inner)]">
               <div className="cc-grid-bg cc-grid-bg--radial opacity-50" />

               {/* 패널 헤더 — 한국어 라벨(좌)/상태(우) */}
               <div className="absolute left-5 top-4 z-10">
                  <span className="db-panel-label">포트폴리오 공간 맵</span>
               </div>
               <div className="absolute right-5 top-4 z-10">
                  <span className="db-status-chip">연결 대기</span>
               </div>

               <div className="absolute inset-0 flex items-center justify-center">
                  {/* 동심원(파랑 헤어라인) + 정직한 빈상태 */}
                  <div className="relative flex h-40 w-40 items-center justify-center">
                     <div className="absolute inset-0 rounded-full border border-[var(--line-strong)] opacity-50" />
                     <div className="absolute inset-6 rounded-full border border-[var(--line-strong)] opacity-35" />
                     <div className="absolute inset-12 rounded-full border border-[var(--line-strong)] opacity-25" />
                     <div className="relative z-10 flex flex-col items-center gap-2 text-center">
                        <span className="text-2xl text-[var(--accent-strong)]">⌖</span>
                        <div>
                           <p className="text-[13px] font-semibold text-[var(--text-secondary)]">포트폴리오 맵</p>
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
                    <h4 className="db-panel-label">규제 동향</h4>
                    <span className="db-panel-meta">실시간 모니터</span>
                 </div>
                 {/* 규제 동향 실데이터 소스 미연동 → 가짜 항목 대신 정직한 빈상태(무목업) */}
                 <div className="relative flex flex-col items-center gap-2 rounded-xl border border-dashed border-[var(--line-strong)] bg-[var(--surface)] px-5 py-8 text-center overflow-hidden">
                    <div className="cc-grid-bg opacity-30" />
                    <span className="relative z-10 text-xl text-[var(--text-tertiary)]">—</span>
                    <p className="relative z-10 text-[13px] font-bold text-[var(--text-primary)]">규제 동향 피드 연동 예정</p>
                    <p className="relative z-10 text-[11px] font-medium text-[var(--text-tertiary)] leading-relaxed">
                       실시간 법령·조례 변경 모니터링을 연결하면<br/>여기에 최신 개정 동향이 표시됩니다.
                    </p>
                    <Link href={`/${locale}/regulations`} className="relative z-10 mt-1 inline-flex items-center gap-1 text-[12px] font-semibold text-[var(--accent-strong)] hover:opacity-80 transition-opacity">규제 분석 열기 →</Link>
                 </div>
              </div>

              {/* ESG 통합 점수 — 실데이터(/analytics/esg) 로더 */}
              <DashboardEsgScore />
           </div>

           {/* 사용자 시작 안내 카드 */}
           <div className="db-card gap-5 p-7">
              <span className="db-eyebrow db-eyebrow--ko">시작 안내</span>
              <h4 className="db-card__title text-lg">전문 가이드가<br/>필요하신가요?</h4>
              <p className="db-card__desc">
                 사통팔땅의 168종 데이터 맵과<br/>AI 엔진을 활용하는 방법을 확인하세요.
              </p>
              <Link href={`/${locale}/guide`} className="inline-flex h-12 w-fit items-center justify-center rounded-2xl border border-[var(--line)] bg-[var(--surface)] px-7 text-[13px] font-semibold text-[var(--text-primary)] transition-colors duration-200 hover:border-[var(--line-strong)]">
                 시작 안내 보기
              </Link>
           </div>
        </div>

      </div>
    </div>
  );
}
