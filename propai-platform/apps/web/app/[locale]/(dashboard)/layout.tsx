import Link from "next/link";
import { LocaleSwitcher } from "@/components/ui/LocaleSwitcher";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";
import { AIAssistant } from "@/components/common/AIAssistant";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { SidebarNav } from "@/components/layout/SidebarNav";
import { MobileSidebarToggle } from "@/components/layout/MobileSidebarToggle";
import { AuthButton } from "@/components/auth/AuthButton";
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
function IconSiteAnalysis() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0"/><circle cx="12" cy="10" r="3"/></svg>
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
function IconESG() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M7 20h10"/><path d="M10 20c5.5-2.5.8-6.4 3-10"/><path d="M9.5 9.4c1.1.8 1.8 2.2 2.3 3.7-2 .4-3.5.4-4.8-.3-1.2-.6-2.3-1.9-3-4.2 2.8-.5 4.4 0 5.5.8z"/><path d="M14.1 6a7 7 0 0 0-1.1 4c1.9-.1 3.3-.6 4.3-1.4 1-1 1.6-2.3 1.7-4.6-2.7.1-4 1-4.9 2z"/></svg>
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
function IconIoT() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="16" height="10" x="2" y="7" rx="2" ry="2"/><line x1="22" x2="22" y1="11" y2="13"/><line x1="6" x2="6" y1="11" y2="13"/><line x1="10" x2="10" y1="11" y2="13"/><line x1="14" x2="14" y1="11" y2="13"/></svg>
  );
}
function IconDigitalTwin() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
  );
}
function IconMaintenance() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 0 0 4.486-6.336l-3.276 3.277a3.004 3.004 0 0 1-2.25-2.25l3.276-3.276a4.5 4.5 0 0 0-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085"/></svg>
  );
}
function IconSafety() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/></svg>
  );
}
function IconKDX() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5V19A9 3 0 0 0 21 19V5"/><path d="M3 12A9 3 0 0 0 21 12"/></svg>
  );
}
function IconAI() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg>
  );
}
function IconWebRTC() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
  );
}
function IconApprovals() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
  );
}
function IconSRE() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10.268 21a2 2 0 0 0 3.464 0"/><path d="M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.673C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326"/></svg>
  );
}
function IconTenant() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
  );
}
function IconGuide() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H19a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6.5a1 1 0 0 1 0-5H20"/></svg>
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

  // I. 프로젝트 전주기 (핵심 개발 매니지먼트)
  const lifecycleNavigation = [
    { href: `/${locale}`, label: "대시보드", icon: <IconDashboard /> },
    { href: `/${locale}/projects`, label: "프로젝트 관리", icon: <IconProject /> },
    { href: `/${locale}/projects`, label: "입지 및 사업성 분석", icon: <IconSiteAnalysis /> },
    { href: `/${locale}/market-insights`, label: "마켓 인텔리전스", icon: <IconMarket /> },
    { href: `/${locale}/projects`, label: "AI 설계 & BIM", icon: <IconDesign /> },
    { href: `/${locale}/permits`, label: "인허가 자동화", icon: <IconPermit /> },
    { href: `/${locale}/regulations`, label: "부동산 규제 연동", icon: <IconRegulation /> },
  ];

  // II. 전략 분석 (수익성 및 ESG)
  const analyticsNavigation = [
    { href: `/${locale}/analytics/investment`, label: "투자 수익성 (ROI)", icon: <IconROI /> },
    { href: `/${locale}/analytics/esg`, label: "ESG / 탄소 경영", icon: <IconESG /> },
    { href: `/${locale}/analytics/cost`, label: "공사비 정밀 분석", icon: <IconCost /> },
  ];

  // III. 자산 운영 (운영 및 물권)
  const operationsNavigation = [
    { href: `/${locale}/auction`, label: "경공매 AI 분석", icon: <IconAuction /> },
    { href: `/${locale}/analytics/iot`, label: "데이터 허브 (IoT)", icon: <IconIoT /> },
    { href: `/${locale}/digital-twin`, label: "디지털 트윈 (FM)", icon: <IconDigitalTwin /> },
    { href: `/${locale}/maintenance`, label: "시설 관리 점검", icon: <IconMaintenance /> },
    { href: `/${locale}/safety`, label: "현장 안전 관제", icon: <IconSafety /> },
    { href: `/${locale}/dashboard/kdx`, label: "국가 데이터 거점 (KDX)", icon: <IconKDX /> },
  ];

  // IV. 엔터프라이즈 지원 (AI/협업/보안)
  const enterpriseNavigation = [
    { href: `/${locale}/agent`, label: "AI 오케스트레이터", icon: <IconAI /> },
    { href: `/${locale}/webrtc`, label: "실시간 협업", icon: <IconWebRTC /> },
    { href: `/${locale}/approvals`, label: "전자 승인 시스템", icon: <IconApprovals /> },
    { href: `/${locale}/sre`, label: "시스템 신뢰성 (SRE)", icon: <IconSRE /> },
    { href: `/${locale}/tenant`, label: "테넌트 통합 관리", icon: <IconTenant /> },
    { href: `/${locale}/guide`, label: "이용 가이드", icon: <IconGuide /> },
  ];

  // V. 관리자
  const adminNavigation = [
    { href: `/${locale}/settings`, label: "⚙️ 관리자 설정", icon: <IconSRE /> },
  ];

  const sections = [
    { title: "개발 전주기 매니지먼트", items: lifecycleNavigation },
    { title: "수익성 및 ESG 분석", items: analyticsNavigation },
    { title: "자산 운영 및 물권", items: operationsNavigation },
    { title: "엔터프라이즈 지원", items: enterpriseNavigation },
    { title: "관리", items: adminNavigation },
  ];

  return (
    <div className="mx-auto flex min-h-screen max-w-7xl flex-col gap-6 px-4 py-5 md:px-6">
      <AIAssistant />
      
      {/* 헤더 */}
      <header className="sticky top-2 z-50 glass rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--glass-bg)] px-4 py-3 md:px-8 md:py-4 shadow-[var(--shadow-lg)] transition-all duration-500 mt-2">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <Link href={`/${locale}`} className="flex items-center gap-4 group">
             <img src="/logos/logo-horizontal.png" alt="사통팔땅 로고" className="h-10 md:h-12 w-auto object-contain transition-transform group-hover:scale-105 active:scale-95 drop-shadow-md" />
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
          <SidebarNav sections={sections} />
        </aside>

        {/* 콘텐츠 영역 */}
        <main className="min-w-0">{children}</main>
      </div>

      {/* 회사정보 푸터 */}
      <footer className="mt-16 border-t border-[var(--line)] bg-[var(--surface-soft)] py-8 px-6">
        <div className="mx-auto max-w-6xl flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div className="space-y-4">
            <img src="/logos/logo-horizontal.png" alt="사통팔땅" className="h-8 w-auto object-contain opacity-90" />
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
