import { UsageClient } from "@/components/mypage/UsageClient";
import { isValidLocale, type Locale } from "@/i18n/config";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export default async function MyPageUsage({ params }: PageProps) {
  const { locale } = await params;
  if (!isValidLocale(locale)) {
    return null;
  }
  return <UsageClient locale={locale as Locale} />;
}
