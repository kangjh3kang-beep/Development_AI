import Link from "next/link";
import { isValidLocale, defaultLocale } from "@/i18n/config";

/**
 * 법적 고지 페이지(개인정보처리방침·서비스이용약관) 공통 레이아웃.
 * 대시보드 사이드바·인증 게이트 없이 누구나(비로그인 포함) 열람 가능한 standalone 문서 레이아웃.
 * 디자인 토큰 기반(하드코딩 색 없음) — 가독성 위주 prose 컨테이너.
 */
type LegalLayoutProps = Readonly<{
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}>;

export default async function LegalLayout({ children, params }: LegalLayoutProps) {
  const { locale: raw } = await params;
  const locale = isValidLocale(raw) ? raw : defaultLocale;
  const base = `/${locale}`;

  return (
    <div className="min-h-screen bg-[var(--surface)] text-[var(--text-primary)]">
      {/* 상단 바 — 브랜드 + 문서 간 이동 */}
      <header className="sticky top-0 z-10 border-b border-[var(--line)] bg-[var(--surface)]/90 backdrop-blur">
        <div className="mx-auto flex max-w-3xl flex-wrap items-center justify-between gap-2 px-5 py-3">
          <Link href={base} className="font-black tracking-tight text-[var(--text-primary)]">
            Prop<span className="text-[var(--accent-strong)]">AI</span>
          </Link>
          <nav className="flex items-center gap-1 text-xs font-semibold">
            <Link href={`${base}/legal/privacy`} className="rounded-lg px-2.5 py-1.5 text-[var(--text-secondary)] hover:bg-[var(--surface-soft)] hover:text-[var(--text-primary)]">
              개인정보처리방침
            </Link>
            <Link href={`${base}/legal/terms`} className="rounded-lg px-2.5 py-1.5 text-[var(--text-secondary)] hover:bg-[var(--surface-soft)] hover:text-[var(--text-primary)]">
              서비스이용약관
            </Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-5 py-8 sm:py-12">{children}</main>

      <footer className="mx-auto max-w-3xl px-5 pb-12 pt-4 text-xs text-[var(--text-tertiary)]">
        <div className="border-t border-[var(--line)] pt-4">
          <p>PropAI — 부동산개발 전주기 AI 자동화 플랫폼</p>
          <p className="mt-1">
            본 문서에 관한 문의는 개인정보 보호책임자 연락처(아래 본문 참조) 또는 고객센터로 접수해 주세요.
          </p>
        </div>
      </footer>
    </div>
  );
}
