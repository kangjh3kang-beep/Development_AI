/**
 * 결제 성공 리다이렉트 — 토스가 인증 후 여기로 보낸다.
 *
 * ★**여기서 승인이 끝난 것이 아니다.** 인증만 끝났고, 승인(돈이 실제로 움직이는 지점)은
 *   서버가 한다. 그래서 이 페이지의 일은 하나다 — 쿼리를 서버로 넘기고 결과를 보여 주는 것.
 *
 * 형태는 `app/[locale]/(auth)/kakao/callback/page.tsx` 를 따른다(같은 문제 구조).
 */
import { PaymentSuccessClient } from "@/components/payments/PaymentSuccessClient";
import { isValidLocale, type Locale } from "@/i18n/config";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{
    orderId?: string;
    paymentKey?: string;
    amount?: string;
    paymentType?: string;
  }>;
};

export default async function PaymentSuccessPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  if (!isValidLocale(locale)) return null;
  const q = await searchParams;
  return (
    <PaymentSuccessClient
      locale={locale as Locale}
      orderId={typeof q.orderId === "string" ? q.orderId : null}
      paymentKey={typeof q.paymentKey === "string" ? q.paymentKey : null}
      amount={typeof q.amount === "string" ? q.amount : null}
    />
  );
}
