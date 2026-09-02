/**
 * 결제 실패 리다이렉트.
 *
 * ★사용자가 결제창에서 취소하거나 카드사가 거절하면 **우리 서버를 거치지 않고** 여기로 온다.
 *   따라서 서버의 조치 문구가 닿지 않는다 — `lib/payments/payment-error.ts` 가 번역한다.
 */
import { PaymentFailClient } from "@/components/payments/PaymentFailClient";
import { isValidLocale, type Locale } from "@/i18n/config";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ code?: string; message?: string; orderId?: string }>;
};

export default async function PaymentFailPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  if (!isValidLocale(locale)) return null;
  const q = await searchParams;
  return (
    <PaymentFailClient
      locale={locale as Locale}
      code={typeof q.code === "string" ? q.code : null}
      message={typeof q.message === "string" ? q.message : null}
      orderId={typeof q.orderId === "string" ? q.orderId : null}
    />
  );
}
