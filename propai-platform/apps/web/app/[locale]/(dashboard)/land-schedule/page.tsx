import { LandScheduleClient } from "@/components/operations/LandScheduleClient";
import { isValidLocale, type Locale } from "@/i18n/config";

export default async function LandSchedulePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isValidLocale(locale)) return null;
  return (
    <div className="grid gap-6">
      <LandScheduleClient locale={locale as Locale} />
    </div>
  );
}
