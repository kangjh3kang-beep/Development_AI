/**
 * (fieldapp) 레이아웃 — 현장앱 전용 독립(standalone) 레이아웃.
 *
 * (dashboard) 레이아웃과 비교:
 *   - 제거: SidebarNav, BillingMeter, HomeLink, MobileSidebarToggle, Disclaimer, 회사 푸터, 사이드바 그리드
 *   - 유지: AuthGuard(인증 필수), ProjectSyncProvider(컨텍스트 공유), locale/theme 무결성
 *
 * 현장앱 자체가 상단바(분양현장·역할·액션)를 포함하고 있으므로 레이아웃은
 * 인증된 사용자에게 전폭(full-width)·전고(min-h-screen) 셸만 제공한다.
 */
import { isValidLocale } from "@/i18n/config";
import { AuthGuard } from "@/components/auth/AuthGuard";
import { ProjectSyncProvider } from "@/components/common/ProjectSyncProvider";

type FieldAppLayoutProps = Readonly<{
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}>;

export default async function FieldAppLayout({
  children,
  params,
}: FieldAppLayoutProps) {
  const { locale } = await params;

  // 유효하지 않은 locale은 children을 그대로 반환 (상위 LocaleLayout이 처리)
  if (!isValidLocale(locale)) {
    return <>{children}</>;
  }

  return (
    <div className="flex min-h-screen flex-col bg-[var(--background)]">
      {/* 전역 프로젝트 컨텍스트 동기화 (플랫폼과 동일한 스토어 공유) */}
      <ProjectSyncProvider />

      {/* 인증 게이트 — 미인증 시 /login으로 리다이렉트 */}
      <AuthGuard>
        {/* 현장앱 콘텐츠 — 전폭 전고, 자체 스크롤 */}
        <main className="flex-1 overflow-auto">
          {children}
        </main>
      </AuthGuard>
    </div>
  );
}
