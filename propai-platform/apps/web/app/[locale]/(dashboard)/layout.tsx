import Link from "next/link";
import { LocaleSwitcher } from "@/components/ui/LocaleSwitcher";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";
import { AIAssistant } from "@/components/common/AIAssistant";
import { ThemeToggle } from "@/components/ui/ThemeToggle";

type DashboardLayoutProps = Readonly<{
  children: React.ReactNode;
  params: Promise<{
    locale: string;
  }>;
}>;

export default async function DashboardLayout({
  children,
  params,
}: DashboardLayoutProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return children;
  }

  const dictionary = await getDictionary(locale as Locale);
  const approvalsLabel =
    (dictionary.nav as { approvals?: string }).approvals ?? "Approval Ops";
  const runtimeModeLabel =
    process.env.NEXT_PUBLIC_USE_MOCKS === "false"
      ? dictionary.workspace.modeLive
      : dictionary.workspace.modeMock;

  const nav = dictionary.nav as any;

  // I. Project Lifecycle (핵심 개발 전주기)
  const lifecycleNavigation = [
    { href: `/${locale}`, label: "대시보드" },
    { href: `/${locale}/projects`, label: "프로젝트 관리" },
    { href: `/${locale}/projects/sample-project/site-analysis`, label: "입지 및 사업성 분석" },
    { href: `/${locale}/market-insights`, label: "마켓 인텔리전스" },
    { href: `/${locale}/projects/sample-project/design`, label: "AI 설계 & BIM" },
    { href: `/${locale}/permits`, label: "인허가 자동화" },
    { href: `/${locale}/regulations`, label: "부동산 규제 연동" },
  ];

  // II. Strategic Analytics (수익성 및 ESG)
  const analyticsNavigation = [
    { href: `/${locale}/analytics/investment`, label: "투자 수익성 (ROI)" },
    { href: `/${locale}/analytics/esg`, label: "ESG / 탄소 경영" },
    { href: `/${locale}/analytics/cost`, label: "공사비 정밀 분석" },
  ];

  // III. Asset Operations (운영 및 물권)
  const operationsNavigation = [
    { href: `/${locale}/auction`, label: "경공매 AI 분석" },
    { href: `/${locale}/analytics/iot`, label: "데이터 허브 (IoT)" },
    { href: `/${locale}/digital-twin`, label: "디지털 트윈 (FM)" },
    { href: `/${locale}/maintenance`, label: "시설 관리 점검" },
    { href: `/${locale}/safety`, label: "현장 안전 관제" },
    { href: `/${locale}/dashboard/kdx`, label: "국가 데이터 거점 (KDX)" },
  ];

  // IV. Enterprise & Support (AI/협업/보안)
  const enterpriseNavigation = [
    { href: `/${locale}/agent`, label: "AI 오케스트레이터" },
    { href: `/${locale}/webrtc`, label: "실시간 협업" },
    { href: `/${locale}/approvals`, label: "전자 승인 시스템" },
    { href: `/${locale}/sre`, label: "시스템 신뢰성 (SRE)" },
    { href: `/${locale}/guide`, label: "이용 가이드 (Manual)" },
  ];

  return (
    <div className="mx-auto flex min-h-screen max-w-7xl flex-col gap-6 px-4 py-5 md:px-6">
      <AIAssistant />
      
      {/* Header */}
      <header className="sticky top-2 z-50 glass rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--glass-bg)] px-4 py-3 md:px-8 md:py-4 shadow-[var(--shadow-lg)] transition-all duration-500 mt-2">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 md:h-14 md:w-14 shrink-0 items-center justify-center rounded-[1.25rem] bg-gradient-to-br from-teal-600 to-teal-400 shadow-xl shadow-teal-500/20 ring-1 ring-white/10 transition-transform hover:scale-105 active:scale-95 cursor-pointer">
              <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M3 3h7v7H3z"/><path d="M14 3h7v7h-7z"/><path d="M14 14h7v7h-7z"/><path d="M3 14h7v7H3z"/></svg>
            </div>
            <div className="min-w-0">
               <p className="text-[9px] font-black uppercase tracking-[0.4em] text-[var(--accent-strong)] mb-0.5 truncate">
                  AI Real-Estate Intelligence
               </p>
               <h1 className="text-2xl md:text-3xl font-[900] tracking-tighter text-[var(--text-primary)] transition-colors">
                  <span className="bg-gradient-to-r from-[var(--text-primary)] to-[var(--accent-strong)] bg-clip-text text-transparent">사통</span>팔땅
                  <span className="text-[var(--accent-strong)] ml-px text-3xl md:text-4xl leading-none drop-shadow-sm">.</span>
               </h1>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <span className="hidden sm:inline-block rounded-full bg-[var(--accent-soft)] border border-[var(--line)] px-4 py-2 text-[10px] font-black tracking-widest uppercase text-[var(--accent-strong)] shadow-sm">
              {runtimeModeLabel}
            </span>
            <div className="flex items-center gap-2 rounded-2xl bg-[var(--surface-soft)] p-1 border border-[var(--line)] backdrop-blur-md shadow-inner">
              <ThemeToggle />
              <div className="h-6 w-px bg-[var(--line)]" />
              <LocaleSwitcher
                currentLocale={locale as Locale}
                label={dictionary.nav.locale}
              />
            </div>
          </div>
        </div>
      </header>

      {/* Main Grid */}
      <div className="grid gap-6 md:grid-cols-[240px_minmax(0,1fr)]">
        {/* Sidebar */}
        <aside className="glass space-y-4 rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-secondary)] p-4 shadow-[var(--shadow-md)]">
          
          {/* I. Lifecycle */}
          <div>
            <p className="px-3 pb-2 text-[10px] font-black uppercase tracking-[0.2em] text-[var(--text-tertiary)]">개발 전주기 매니지먼트</p>
            <nav className="grid gap-0.5">
              {lifecycleNavigation.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="group relative rounded-[var(--radius-md)] px-3 py-2 text-[13px] font-bold text-[var(--text-secondary)] transition-all duration-300 hover:bg-[var(--accent-soft)] hover:text-[var(--accent-strong)]"
                >
                  {item.label}
                  <span className="absolute left-0 top-1/2 h-3.5 w-1 -translate-y-1/2 rounded-r-full bg-[var(--accent)] opacity-0 transition-all group-hover:opacity-100" />
                </Link>
              ))}
            </nav>
          </div>

          <div className="h-px bg-[var(--line)] opacity-50" aria-hidden="true" />

          {/* II. Analytics */}
          <div>
            <p className="px-3 pb-2 text-[10px] font-black uppercase tracking-[0.2em] text-[var(--text-tertiary)]">수익성 및 ESG 분석</p>
            <nav className="grid gap-0.5">
              {analyticsNavigation.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="group relative rounded-[var(--radius-md)] px-3 py-1.5 text-[12px] font-medium text-[var(--text-secondary)] transition-all duration-300 hover:bg-[var(--accent-soft)] hover:text-[var(--accent-strong)]"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>

          <div className="h-px bg-[var(--line)] opacity-50" aria-hidden="true" />

          {/* III. Operations */}
          <div>
            <p className="px-3 pb-2 text-[10px] font-black uppercase tracking-[0.2em] text-[var(--text-tertiary)]">자산 운영 및 물권</p>
            <nav className="grid gap-0.5">
              {operationsNavigation.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="group relative rounded-[var(--radius-md)] px-3 py-1.5 text-[12px] font-medium text-[var(--text-secondary)] transition-all duration-300 hover:bg-[var(--accent-soft)] hover:text-[var(--accent-strong)]"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>

          <div className="h-px bg-[var(--line)] opacity-50" aria-hidden="true" />

          {/* IV. Enterprise */}
          <div>
            <p className="px-3 pb-2 text-[10px] font-black uppercase tracking-[0.2em] text-[var(--text-tertiary)]">엔터프라이즈 지원</p>
            <nav className="grid gap-0.5">
              {enterpriseNavigation.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="group relative rounded-[var(--radius-md)] px-3 py-1.5 text-[12px] font-medium text-[var(--text-secondary)] transition-all duration-300 hover:bg-[var(--accent-soft)] hover:text-[var(--accent-strong)]"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>

        </aside>

        {/* Content */}
        <main className="min-w-0">{children}</main>
      </div>
    </div>
  );
}
