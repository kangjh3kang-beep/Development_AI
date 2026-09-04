import { ProfileClient } from "@/components/mypage/ProfileClient";
import { isValidLocale, type Locale } from "@/i18n/config";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export default async function MyPageProfile({ params }: PageProps) {
  const { locale } = await params;
  if (!isValidLocale(locale)) {
    return null;
  }
  return <ProfileClient locale={locale as Locale} />;
}
