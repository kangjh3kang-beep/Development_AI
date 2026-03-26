import { AuthWorkspaceClient } from "@/components/auth/AuthWorkspaceClient";
import { isValidLocale, type Locale } from "@/i18n/config";

type RegisterPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function RegisterPage({ params }: RegisterPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  return <AuthWorkspaceClient locale={locale as Locale} defaultMode="register" />;
}
