import { Suspense } from "react";

import { VerifyEmailClient } from "@/components/auth/PasswordRecoveryClient";
import { isValidLocale, type Locale } from "@/i18n/config";

type VerifyEmailPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function VerifyEmailPage({ params }: VerifyEmailPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  // useSearchParams(토큰 파싱)는 Suspense 경계가 필요하다(Next.js App Router 계약).
  return (
    <Suspense fallback={null}>
      <VerifyEmailClient locale={locale as Locale} />
    </Suspense>
  );
}
