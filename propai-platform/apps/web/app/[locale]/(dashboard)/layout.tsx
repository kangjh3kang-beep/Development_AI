import Link from "next/link";
import { headers } from "next/headers";
import { Logo } from "@/components/ui/Logo";
import { LocaleSwitcher } from "@/components/ui/LocaleSwitcher";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";
import { AIAssistant } from "@/components/common/AIAssistant";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { SidebarNav } from "@/components/layout/SidebarNav";
import { buildPrimaryNav } from "@/components/layout/nav-config";
import { BillingMeter } from "@/components/billing/BillingMeter";
import { MobileSidebarToggle } from "@/components/layout/MobileSidebarToggle";
import { HomeLink } from "@/components/layout/HomeLink";
import { AuthButton } from "@/components/auth/AuthButton";
import { AuthGuard } from "@/components/auth/AuthGuard";
import { Disclaimer } from "@/components/common/Disclaimer";
import { ProjectSyncProvider } from "@/components/common/ProjectSyncProvider";
import { runtimeMode } from "@/lib/runtime-mode";
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
  const runtimeModeLabel =
    runtimeMode() === "live"
      ? dictionary.workspace.modeLive
      : dictionary.workspace.modeMock;

  // 좌측 네비게이션 단일 출처(SSOT) — IA 원칙은 components/layout/nav-config.tsx +
  // docs/design/navigation-ia-system.md. 접이식 그룹형(L1 섹션 → L2 항목/그룹 → L3 하위메뉴).
  const sections = buildPrimaryNav(locale);

  return (
    <div className="mx-auto flex min-h-screen max-w-7xl flex-col gap-6 px-4 py-5 md:px-6">
      <ProjectSyncProvider />
      <AIAssistant />
      
      {/* 헤더 */}
      <header className="sticky top-2 z-50 glass rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--glass-bg)] px-4 py-3 md:px-8 md:py-4 shadow-[var(--shadow-lg)] transition-all duration-500 mt-2">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <HomeLink href={`/${locale}`} className="flex items-center gap-4 group min-w-0">
             <Logo size="md" className="transition-transform group-hover:scale-105 active:scale-95 shrink-0" />
             <span className="sr-only">사통팔땅 AI Real-Estate Intelligence</span>
          </HomeLink>

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
        {/* 사이드바 — 모바일에서 숨김, lg 이상에서 표시.
            전체 메뉴가 스크롤 없이 보이도록 컴팩트 간격 + max-height 안전장치(초과 시에만 스크롤). */}
        <aside className="hidden lg:block glass space-y-3.5 rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-secondary)] p-4 shadow-[var(--shadow-md)] sticky top-[88px] max-h-[calc(100vh-100px)] overflow-y-auto custom-scrollbar">
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
