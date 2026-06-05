import { DeskAppraisalReportClient } from "@/components/operations/DeskAppraisalReportClient";
import { isValidLocale, type Locale } from "@/i18n/config";

export default async function DeskAppraisalPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isValidLocale(locale)) return null;
  return (
    <div className="grid gap-6">
      <DeskAppraisalReportClient locale={locale as Locale} />
    </div>
  );
}
