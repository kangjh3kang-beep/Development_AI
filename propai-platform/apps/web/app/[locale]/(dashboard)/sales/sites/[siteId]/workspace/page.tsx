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
    <div className="grid gap-6">
      <SiteWorkspaceClient locale={locale as Locale} siteId={siteId} />
    </div>
  );
}
