import Link from "next/link";
import { headers } from "next/headers";
import { Logo } from "@/components/ui/Logo";
import { LocaleSwitcher } from "@/components/ui/LocaleSwitcher";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";
import { AIAssistant } from "@/components/common/AIAssistant";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { SidebarNav } from "@/components/layout/SidebarNav";
import { BillingMeter } from "@/components/billing/BillingMeter";
import { MobileSidebarToggle } from "@/components/layout/MobileSidebarToggle";
import { AuthButton } from "@/components/auth/AuthButton";
import { AuthGuard } from "@/components/auth/AuthGuard";
import { Disclaimer } from "@/components/common/Disclaimer";
import { ProjectSyncProvider } from "@/components/common/ProjectSyncProvider";
type DashboardLayoutProps = Readonly<{
  children: React.ReactNode;
  params: Promise<{
    locale: string;
  }>;
}>;

/* ── 사이드바 네비게이션 아이콘 ── */
function IconDashboard() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/></svg>
  );
}
function IconProject() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/></svg>
  );
}
function IconMarket() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="m19 9-5 5-4-4-3 3"/></svg>
  );
}
function IconDesign() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.287 1.288L3 12l5.8 1.9a2 2 0 0 1 1.288 1.287L12 21l1.9-5.8a2 2 0 0 1 1.287-1.288L21 12l-5.8-1.9a2 2 0 0 1-1.288-1.287Z"/></svg>
  );
}
function IconPermit() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="m9 15 2 2 4-4"/></svg>
  );
}
function IconRegulation() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m3 11 18-5v12L3 13v-2z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/></svg>
  );
}
function IconROI() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"/><path d="M12 18V6"/></svg>
  );
}
function IconCost() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 12h20"/><path d="M20 12v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-8"/><path d="m4 8 16-4"/><path d="m8.86 6.78-.45-1.81a2 2 0 0 1 1.45-2.43l1.94-.48a2 2 0 0 1 2.43 1.46l.45 1.8"/></svg>
  );
}
function IconAuction() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m14 12-8.5 8.5a2.12 2.12 0 1 1-3-3L11 9"/><path d="M15 13 9 7l4-4 6 6-4 4z"/><path d="m18 15 3 3"/><path d="M21 11V5a2 2 0 0 0-2-2H5"/></svg>
  );
}
function IconSRE() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10.268 21a2 2 0 0 0 3.464 0"/><path d="M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.673C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326"/></svg>
  );
}

export default async function DashboardLayout({
  children,
  params,
}: DashboardLayoutProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return children;
  }

  const dictionary = await getDictionary(locale as Locale);
  const runtimeModeLabel =
    process.env.NEXT_PUBLIC_USE_MOCKS === "false"
      ? dictionary.workspace.modeLive
      : dictionary.workspace.modeMock;

  // ── IA 재편(9→4섹션): 핵심 워크플로 순서로 군살빼기. 라벨 직관화 유지 ──
  // 프로젝트 상세 전용(수지/세금/계약/시공/운영 등)은 '프로젝트 관리'→선택 후 탭으로 진입.
  // 최상위에는 독립 진입점만 둔다. 운영/트윈/환경/블록체인은 페르소나(역할) 게이팅.

  // 1. 사업 검토 — 사업성·시장·인허가·규제 (핵심 깔때기 진입)
  const reviewNavigation = [
    { href: `/${locale}`, label: "대시보드", icon: <IconDashboard /> },
    { href: `/${locale}/precheck`, label: "90초 사업성 진단", icon: <IconPermit /> },
    { href: `/${locale}/projects`, label: "프로젝트 관리", icon: <IconProject /> },
    { href: `/${locale}/market-insights`, label: "시장·시세 분석", icon: <IconMarket /> },
    { href: `/${locale}/permits`, label: "인허가 가능성", icon: <IconPermit /> },
    { href: `/${locale}/regulations`, label: "개발 규제", icon: <IconRegulation /> },
  ];

  // 2. 토지·자금 — 토지조서·등기·AI시세 + 투자수익성·공사비
  //    ESG·탄소는 사업성/투자수익 결과 내로 흡수(메뉴 제외, 독립 라우트는 게이팅으로 보존)
  const landFinanceNavigation = [
    { href: `/${locale}/land-schedule`, label: "토지조서", icon: <IconProject /> },
    { href: `/${locale}/registry-analysis`, label: "└ 등기부등본 열람", icon: <IconPermit /> },
    { href: `/${locale}/desk-appraisal`, label: "└ AI 시세추정 보고서", icon: <IconPermit /> },
    { href: `/${locale}/analytics/investment`, label: "투자 수익성 (ROI)", icon: <IconROI /> },
    { href: `/${locale}/analytics/cost`, label: "공사비 분석", icon: <IconCost /> },
  ];

  // 3. 실행 — 분양·공공입찰·경공매
  const executionNavigation = [
    { href: `/${locale}/sales`, label: "분양 현장 관리", icon: <IconProject /> },
    { href: `/${locale}/sales/sites`, label: "└ 내 분양 현장(현장앱)", icon: <IconProject /> },
    { href: `/${locale}/sales/projection`, label: "└ 분양 요약(경영진용)", icon: <IconMarket /> },
    { href: `/${locale}/g2b`, label: "공공입찰 (나라장터)", icon: <IconAuction /> },
    { href: `/${locale}/auction`, label: "경매·공매", icon: <IconAuction /> },
  ];

  // 4. 설계 참고 — CAD 자동설계 / BIM·적산
  const designNavigation = [
    { href: `/${locale}/design-studio`, label: "AI 설계도면(CAD)", icon: <IconDesign /> },
    { href: `/${locale}/bim-studio`, label: "3D 모델·공사물량(BIM·적산)", icon: <IconCost /> },
  ];

  // 자산 운영 (준공 후 임대·임차인) — 페르소나 게이팅(운영/관리자 역할만)
  const assetOpsNavigation = [
    { href: `/${locale}/operations/lease`, label: "임대·임차인 관리", icon: <IconProject /> },
  ];

  // 관리자 — 기존 role 게이팅 유지
  const adminNavigation = [
    { href: `/${locale}/settings`, label: "⚙️ 관리자 설정", icon: <IconSRE /> },
    { href: `/${locale}/settings/users`, label: "👤 사용자 관리", icon: <IconSRE /> },
    { href: `/${locale}/settings/billing`, label: "💳 과금 금액 설정", icon: <IconSRE /> },
    { href: `/${locale}/settings/lists`, label: "📋 편집 목록 관리", icon: <IconSRE /> },
  ];

  const sections = [
    { title: "사업 검토", items: reviewNavigation },
    { title: "토지·자금", items: landFinanceNavigation },
    { title: "실행", items: executionNavigation },
    { title: "설계 참고", items: designNavigation },
    { title: "자산 운영", items: assetOpsNavigation, assetOpsOnly: true },
    { title: "관리", items: adminNavigation, adminOnly: true },
  ];

  return (
    <div className="mx-auto flex min-h-screen max-w-7xl flex-col gap-6 px-4 py-5 md:px-6">
      <ProjectSyncProvider />
      <AIAssistant />
      
      {/* 헤더 */}
      <header className="sticky top-2 z-50 glass rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--glass-bg)] px-4 py-3 md:px-8 md:py-4 shadow-[var(--shadow-lg)] transition-all duration-500 mt-2">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <Link href={`/${locale}`} className="flex items-center gap-4 group min-w-0">
             <Logo size="md" className="transition-transform group-hover:scale-105 active:scale-95 shrink-0" />
             <span className="sr-only">사통팔땅 AI Real-Estate Intelligence</span>
          </Link>

          <div className="flex flex-wrap items-center gap-3">
            <MobileSidebarToggle sections={sections} />
            <span className="hidden sm:inline-block rounded-full bg-[var(--accent-soft)] border border-[var(--line)] px-4 py-2 text-[11px] font-bold tracking-widest uppercase text-[var(--accent-strong)] shadow-sm">
              {runtimeModeLabel}
            </span>
            <div className="flex items-center gap-2 rounded-2xl bg-[var(--surface-soft)] p-1 border border-[var(--line)] backdrop-blur-md shadow-inner">
              <ThemeToggle />
              <div className="h-6 w-px bg-[var(--line)]" />
              <LocaleSwitcher
                currentLocale={locale as Locale}
                label={dictionary.nav.locale}
              />
              <div className="h-6 w-px bg-[var(--line)]" />
              <AuthButton locale={locale} />
            </div>
          </div>
        </div>
      </header>

      {/* 메인 그리드 */}
      <div className="grid gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
        {/* 사이드바 — 모바일에서 숨김, lg 이상에서 표시 */}
        <aside className="hidden lg:block glass space-y-5 rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-secondary)] p-5 shadow-[var(--shadow-md)] sticky top-[88px] h-[calc(100vh-100px)] overflow-y-auto custom-scrollbar">
          <BillingMeter compact />
          <SidebarNav sections={sections} />
        </aside>

        {/* 콘텐츠 영역 — 메인 페이지는 미인증 접근 허용 (기능 사용 시 로그인 요구) */}
        <main className="min-w-0 space-y-6">
          {children}
          {/* 면책 고지 — 모든 페이지·분석결과 하단 공통 노출 */}
          <Disclaimer />
        </main>
      </div>

      {/* 회사정보 푸터 */}
      <footer className="mt-16 border-t border-[var(--line)] bg-[var(--surface-soft)] py-8 px-6">
        <div className="mx-auto max-w-6xl flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div className="space-y-4">
            <Logo size="sm" className="opacity-80 grayscale" />
            <div className="space-y-1 text-xs text-[var(--text-tertiary)] leading-relaxed">
              <p>대표: 강재희 | 사업자등록번호: 682-38-01463</p>
              <p>업태: 도매 및 소매업</p>
              <p>소재지: 경기도 광주시 회안대로 637-36</p>
            </div>
          </div>
          <div className="space-y-1 text-xs text-[var(--text-tertiary)]">
            <p>대표번호: <a href="tel:1666-0916" className="text-[var(--text-secondary)] hover:text-[var(--accent-strong)]">1666-0916</a></p>
            <p>팩스: 02-6305-0044</p>
            <p className="mt-2 text-[var(--text-hint)]">&copy; 2026 사통팔땅. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
