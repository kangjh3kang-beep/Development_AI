"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";
import { Logo } from "@/components/ui/Logo";
import { LocaleSwitcher } from "@/components/ui/LocaleSwitcher";
import { AIAssistant } from "@/components/common/AIAssistant";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { MobileSidebarToggle } from "@/components/layout/MobileSidebarToggle";
import { WorkspaceNavBar } from "@/components/layout/WorkspaceNavBar";
import { HomeLink } from "@/components/layout/HomeLink";
import { AuthButton } from "@/components/auth/AuthButton";
import { Disclaimer } from "@/components/common/Disclaimer";
import { ProjectSyncProvider } from "@/components/common/ProjectSyncProvider";
import { useIsAuthenticated } from "@/hooks/useIsAuthenticated";
import type { Locale } from "@/i18n/config";
import type { NavSection } from "@/components/layout/nav-config";

type DashboardChromeGateProps = {
  locale: Locale;
  localeLabel: string;
  runtimeModeLabel: string;
  sections: NavSection[];
  children: ReactNode;
};

/**
 * 앱 크롬(헤더·워크스페이스 내비·푸터·면책고지) 표시 여부 게이트.
 *
 * "미인증 + 홈 라우트(/{locale})"일 때만 크롬을 숨기고 children(랜딩,
 * `components/marketing/LandingPage`)을 풀블리드로 렌더한다 — 랜딩은 자체
 * 내비(MarketingNav)·배경(.mkt-root)을 완결하게 갖추고 있어 앱 크롬과
 * 시각적으로 이중 노출되지 않게 하기 위함이다.
 * 그 외 모든 경우(인증된 홈 포함 · 모든 하위 라우트)는 기존 크롬을 그대로 유지한다.
 *
 * 인증 판정은 `useIsAuthenticated`(단일 소스) — 홈 콘텐츠 분기(`HomeGate`)와
 * 동일한 훅을 공유해 판정 로직이 두 곳에서 중복되지 않는다.
 * 서버는 인증 상태를 모르므로(토큰=localStorage 전용) 이 컴포넌트는 클라이언트
 * 경계이고, layout.tsx는 서버 컴포넌트로 유지한 채 데이터(dictionary·sections)만
 * props로 내려받아 크롬 래퍼만 클라이언트로 감싼다.
 */
export function DashboardChromeGate({
  locale,
  localeLabel,
  runtimeModeLabel,
  sections,
  children,
}: DashboardChromeGateProps) {
  const pathname = usePathname();
  const authed = useIsAuthenticated();

  const isHomeRoute = pathname === `/${locale}` || pathname === `/${locale}/`;

  if (isHomeRoute && !authed) {
    return <>{children}</>;
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-[1500px] flex-col gap-4 px-4 py-4 md:px-6">
      <ProjectSyncProvider />
      <AIAssistant />

      {/* 헤더 — ★sticky top-2(0.5rem) + 실측 높이 80px(5rem)="고정 시 하단 경계" 5.5rem.
          이 값은 tokens.css의 --app-header-offset(6.25rem=5.5rem+여백 0.75rem) 파생 기준이다
          (하위 sticky 자식이 헤더 뒤로 가려지지 않도록 top 오프셋으로 참조). 이 헤더의
          padding(py-3)·내부 높이가 바뀌면 --app-header-offset도 함께 갱신할 것(불변식). */}
      <header className="sticky top-2 z-[1000] rounded-2xl border border-[var(--line)] bg-[var(--surface-secondary)] px-4 py-3 shadow-[var(--shadow-md)]">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <HomeLink href={`/${locale}`} className="flex items-center gap-4 group min-w-0">
             <Logo size="md" className="transition-transform group-hover:scale-105 active:scale-95 shrink-0" />
             <span className="sr-only">사통팔땅 AI Real-Estate Intelligence</span>
          </HomeLink>

          <div className="flex flex-wrap items-center gap-3">
            <MobileSidebarToggle sections={sections} />
            <span className="hidden sm:inline-block rounded-[var(--r-pill)] bg-[var(--status-success)]/10 border border-[var(--status-success)]/30 px-3 py-2 text-[11px] font-bold tracking-widest uppercase text-[var(--status-success)]">
              {runtimeModeLabel}
            </span>
            <div className="flex items-center gap-2 rounded-xl bg-[var(--surface-soft)] p-1 border border-[var(--line)]">
              <ThemeToggle />
              <div className="h-6 w-px bg-[var(--line)]" />
              <LocaleSwitcher
                currentLocale={locale}
                label={localeLabel}
              />
              <div className="h-6 w-px bg-[var(--line)]" />
              <AuthButton locale={locale} />
            </div>
          </div>
        </div>
      </header>

      <WorkspaceNavBar sections={sections} />

      {/* 콘텐츠 영역 — 메인 페이지는 미인증 접근 허용 (기능 사용 시 로그인 요구) */}
      <main className="min-w-0 space-y-6">
        {children}
        {/* 면책 고지 — 모든 페이지·분석결과 하단 공통 노출 */}
        <Disclaimer />
      </main>

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
