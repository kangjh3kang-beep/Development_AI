import { Suspense } from "react";

import { ResetPasswordClient } from "@/components/auth/PasswordRecoveryClient";
import { isValidLocale, type Locale } from "@/i18n/config";

type ResetPasswordPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function ResetPasswordPage({ params }: ResetPasswordPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  // useSearchParams(토큰 파싱)는 Suspense 경계가 필요하다(Next.js App Router 계약).
  return (
    <Suspense fallback={null}>
      <ResetPasswordClient locale={locale as Locale} />
    </Suspense>
  );
}
