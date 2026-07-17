import { MyPageOverviewClient } from "@/components/mypage/MyPageOverviewClient";
import { isValidLocale, type Locale } from "@/i18n/config";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export default async function MyPage({ params }: PageProps) {
  const { locale } = await params;
  if (!isValidLocale(locale)) {
    return null;
  }
  return <MyPageOverviewClient locale={locale as Locale} />;
}
