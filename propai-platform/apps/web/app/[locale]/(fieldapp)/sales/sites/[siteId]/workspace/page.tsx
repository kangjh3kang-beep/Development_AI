/**
 * 분양 현장앱 워크스페이스 페이지 — (fieldapp) 레이아웃 하위.
 *
 * URL은 그대로 /[locale]/sales/sites/[siteId]/workspace 이며,
 * (fieldapp) 그룹이 플랫폼 SidebarNav/푸터 없는 독립 셸을 제공한다.
 */
import SiteWorkspaceClient from "@/components/sales-app/SiteWorkspaceClient";
import { isValidLocale, type Locale } from "@/i18n/config";

export default async function SalesSiteWorkspacePage({
  params,
}: {
  params: Promise<{ locale: string; siteId: string }>;
}) {
  const { locale, siteId } = await params;
  if (!isValidLocale(locale)) return null;

  return (
    // 전폭 컨테이너 — 최대폭 제한 없이 현장앱이 공간을 모두 사용
    <div className="min-h-screen w-full">
      <SiteWorkspaceClient locale={locale as Locale} siteId={siteId} />
    </div>
  );
}
