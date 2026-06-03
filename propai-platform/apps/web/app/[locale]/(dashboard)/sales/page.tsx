import SalesSiteList from "@/components/sales/SalesSiteList";
import { isValidLocale, type Locale } from "@/i18n/config";

export default async function SalesPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isValidLocale(locale)) return null;
  return (
    <div className="grid gap-6">
      <SalesSiteList locale={locale as Locale} />
    </div>
  );
}
