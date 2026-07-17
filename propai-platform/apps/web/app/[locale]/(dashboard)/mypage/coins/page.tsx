import { CoinsClient } from "@/components/mypage/CoinsClient";
import { isValidLocale, type Locale } from "@/i18n/config";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export default async function MyPageCoins({ params }: PageProps) {
  const { locale } = await params;
  if (!isValidLocale(locale)) {
    return null;
  }
  return <CoinsClient locale={locale as Locale} />;
}
