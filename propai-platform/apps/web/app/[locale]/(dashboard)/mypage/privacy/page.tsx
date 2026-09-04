import { PrivacyClient } from "@/components/mypage/PrivacyClient";
import { isValidLocale, type Locale } from "@/i18n/config";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export default async function MyPagePrivacy({ params }: PageProps) {
  const { locale } = await params;
  if (!isValidLocale(locale)) {
    return null;
  }
  return <PrivacyClient locale={locale as Locale} />;
}
