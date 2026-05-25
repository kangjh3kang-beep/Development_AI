import { SreDashboardClient } from "@/components/sre/SreDashboardClient";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type SrePageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function SrePage({ params }: SrePageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  const dictionary = await getDictionary(locale as Locale);

  return <SreDashboardClient dictionary={dictionary} />;
}
