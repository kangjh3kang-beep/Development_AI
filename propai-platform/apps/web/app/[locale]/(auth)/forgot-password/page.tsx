import { ForgotPasswordClient } from "@/components/auth/PasswordRecoveryClient";
import { isValidLocale, type Locale } from "@/i18n/config";

type ForgotPasswordPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function ForgotPasswordPage({ params }: ForgotPasswordPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  return <ForgotPasswordClient locale={locale as Locale} />;
}
