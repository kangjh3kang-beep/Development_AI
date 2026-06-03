import SalesSiteWorkspace from "@/components/sales/SalesSiteWorkspace";
import { isValidLocale, type Locale } from "@/i18n/config";

export default async function SalesSitePage({ params }: { params: Promise<{ locale: string; siteId: string }> }) {
  const { locale, siteId } = await params;
  if (!isValidLocale(locale)) return null;
  return (
    <div className="grid gap-6">
      <SalesSiteWorkspace siteCode={siteId} locale={locale as Locale} />
    </div>
  );
}
