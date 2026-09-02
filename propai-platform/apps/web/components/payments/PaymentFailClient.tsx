"use client";

/**
 * 결제 실패 안내 — ★**우리 서버를 거치지 않고** 도착하는 경로.
 *
 * 사용자가 결제창에서 취소하거나 카드사가 거절하면 토스가 직접 이리로 보낸다.
 * 그래서 서버가 만든 조치 문구가 없고, `lib/payments/payment-error.ts` 가 번역한다.
 *
 * ★여기서 **돈은 청구되지 않았다.** 승인 전 단계이므로 그렇게 명확히 말해야
 *   사용자가 불필요하게 카드사에 문의하지 않는다.
 */

import { useEffect, useState } from "react";
import Link from "next/link";

import { fromTossFailUrl, type PaymentErrorView } from "@/lib/payments/payment-error";
import type { Locale } from "@/i18n/config";

type Props = {
  locale: Locale;
  code: string | null;
  message: string | null;
  orderId: string | null;
};

export function PaymentFailClient({ locale, code, message, orderId }: Props) {
  const [view] = useState<PaymentErrorView>(() => fromTossFailUrl(code, message));
  const coinsHref = `/${locale}/mypage/coins`;

  useEffect(() => {
    // ★`orderId` 가 URL 에 남지 않게 한다(성장루프가 라우트를 그대로 수집한다).
    if (typeof window !== "undefined" && window.location.search) {
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, []);

  return (
    <section className="mx-auto max-w-lg px-4 py-16" data-testid="payment-fail">
      <h1 className="text-center text-xl font-semibold text-[var(--status-error)]">
        결제를 완료하지 못했습니다
      </h1>
      <div role="alert" className="mt-6 rounded-lg bg-[var(--surface-strong)] p-4">
        <p className="text-sm text-[var(--text-primary)]">{view.message}</p>
        <p className="mt-3 text-sm text-[var(--text-secondary)]" data-testid="payment-remediation">
          {view.remediation}
        </p>
        {/* ★결제 전 단계라 청구가 없다는 사실을 명시 — 불필요한 카드사 문의를 막는다. */}
        <p className="mt-3 text-xs text-[var(--status-success)]">
          결제 금액은 청구되지 않았습니다.
        </p>
        {view.code && view.code !== "UNKNOWN" ? (
          <p className="mt-2 text-xs text-[var(--text-tertiary)]">
            오류 코드: {view.code}
            {orderId ? " · 주문 확인은 충전 내역에서 하실 수 있습니다." : ""}
          </p>
        ) : null}
      </div>
      <div className="mt-6 flex justify-center gap-3">
        <Link
          href={coinsHref}
          className="rounded-md bg-[var(--accent-primary)] px-5 py-2 text-sm font-medium text-white"
        >
          {view.retryable ? "다시 충전하기" : "충전 내역으로"}
        </Link>
      </div>
    </section>
  );
}
