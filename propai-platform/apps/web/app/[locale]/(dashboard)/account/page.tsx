import { AccountSecurityClient } from "@/components/auth/AccountSecurityClient";
import { isValidLocale, type Locale } from "@/i18n/config";

type AccountPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function AccountPage({ params }: AccountPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  return <AccountSecurityClient locale={locale as Locale} />;
}
