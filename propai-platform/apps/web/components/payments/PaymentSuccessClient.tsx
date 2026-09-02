"use client";

/**
 * 결제 승인 요청 → 결과 표시.
 *
 * ## ★이 화면이 지키는 것
 *
 * 1. **세 결과를 구별해 말한다** — 완료 / 보류(가상계좌) / **미확정**.
 *    미확정을 "실패"라고 말하면 사용자가 **다시 결제해서 이중 결제**가 된다.
 * 2. **한 번만 요청한다** — StrictMode 이중 실행·새로고침이 승인을 두 번 보내지 않게.
 *    (서버도 멱등이지만, 화면이 중복을 만들 이유가 없다)
 * 3. ★**쿼리 파라미터를 즉시 URL 에서 지운다** — `paymentKey` 는 결제 식별자다.
 *    브라우저 히스토리·스크린샷·성장루프 라우트에 남기지 않는다.
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

import { apiClient } from "@/lib/api-client";
import { fromApiError, type PaymentErrorView } from "@/lib/payments/payment-error";
import type { Locale } from "@/i18n/config";

type Props = {
  locale: Locale;
  orderId: string | null;
  paymentKey: string | null;
  amount: string | null;
};

type ConfirmResult = {
  order_no?: string;
  coin_krw?: number;
  already_applied?: boolean;
};

type Phase = "confirming" | "done" | "error";

/** 리다이렉트가 필요한 값을 안 실어 준 경우 — ★**props 에서 순수하게 유도**된다. */
const MISSING_PARAMS: PaymentErrorView = {
  code: "MISSING_PARAMS",
  message: "결제 정보가 전달되지 않았습니다.",
  remediation:
    "충전 내역에서 결제 상태를 확인해 주세요. 금액이 청구되었다면 고객센터로 문의해 주세요.",
  outcome: "unknown",
  retryable: false,
};

export function PaymentSuccessClient({ locale, orderId, paymentKey, amount }: Props) {
  // ★파라미터 누락 판정은 **props 의 순수 함수**다 — effect 안에서 setState 로 만들면
  //   동기 setState 가 되어 연쇄 렌더를 부른다(`react-hooks/set-state-in-effect`).
  //   렌더 시점에 정하면 그 자체가 없어진다.
  const missing = !orderId || !paymentKey || amount === null;
  const [phase, setPhase] = useState<Phase>(() => (missing ? "error" : "confirming"));
  const [result, setResult] = useState<ConfirmResult | null>(null);
  const [err, setErr] = useState<PaymentErrorView | null>(() => (missing ? MISSING_PARAMS : null));
  // ★StrictMode 는 effect 를 두 번 돌린다. ref 로 **한 번만** 보낸다.
  const sent = useRef(false);
  const coinsHref = `/${locale}/mypage/coins`;

  useEffect(() => {
    // ★결제 식별자를 URL 에서 즉시 제거(요청은 아래 클로저가 이미 값을 들고 있다).
    if (typeof window !== "undefined" && window.location.search) {
      window.history.replaceState(null, "", window.location.pathname);
    }
    if (missing || sent.current) return;
    sent.current = true;

    // ★비동기 작업을 effect 안에 두고 **언마운트 가드**를 건다.
    //   종전에는 `useCallback` 으로 뺀 뒤 `void confirm()` 으로 불렀는데,
    //   ①언마운트 후 setState 를 막을 길이 없었고
    //   ②`react-hooks/set-state-in-effect` 가 그 형태를 경고했다.
    //   여기 두면 둘 다 해소된다 — 린터를 피하려는 비틀기가 아니라 실제로 안전한 형태다.
    let alive = true;
    void (async () => {
      try {
        const r = await apiClient.post<ConfirmResult>("/billing/payments/toss/confirm", {
          body: { order_id: orderId, payment_key: paymentKey, amount: Number(amount) },
          useMock: false,
        });
        if (!alive) return;
        setResult(r);
        setPhase("done");
      } catch (error) {
        if (!alive) return;
        setErr(fromApiError(error, "결제 승인에 실패했습니다."));
        setPhase("error");
      }
    })();
    return () => {
      alive = false;
    };
  }, [orderId, paymentKey, amount, missing]);

  if (phase === "confirming") {
    return (
      <section className="mx-auto max-w-lg px-4 py-16 text-center" data-testid="payment-confirming">
        <div className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-2 border-[var(--border-subtle)] border-t-[var(--accent-primary)]" />
        <h1 className="text-lg font-semibold text-[var(--text-primary)]">결제를 승인하고 있습니다</h1>
        <p className="mt-2 text-sm text-[var(--text-tertiary)]">
          창을 닫지 마세요. 잠시만 기다려 주세요.
        </p>
      </section>
    );
  }

  if (phase === "done") {
    return (
      <section className="mx-auto max-w-lg px-4 py-16 text-center" data-testid="payment-done">
        <h1 className="text-xl font-semibold text-[var(--status-success)]">충전이 완료되었습니다</h1>
        <dl className="mt-6 space-y-2 rounded-lg bg-[var(--surface-strong)] p-4 text-sm">
          {result?.order_no ? (
            <div className="flex justify-between">
              <dt className="text-[var(--text-tertiary)]">주문번호</dt>
              <dd className="font-medium text-[var(--text-primary)]">{result.order_no}</dd>
            </div>
          ) : null}
          {typeof result?.coin_krw === "number" ? (
            <div className="flex justify-between">
              <dt className="text-[var(--text-tertiary)]">충전 금액</dt>
              <dd className="font-medium text-[var(--text-primary)]">
                {result.coin_krw.toLocaleString("ko-KR")}원
              </dd>
            </div>
          ) : null}
        </dl>
        {result?.already_applied ? (
          <p className="mt-3 text-xs text-[var(--text-tertiary)]">
            이미 처리된 결제입니다(중복 충전되지 않았습니다).
          </p>
        ) : null}
        <Link
          href={coinsHref}
          className="mt-6 inline-block rounded-md bg-[var(--accent-primary)] px-5 py-2 text-sm font-medium text-white"
        >
          충전 내역으로
        </Link>
      </section>
    );
  }

  // ★오류 — 세 결과를 **다르게** 말한다.
  const pending = err?.outcome === "pending";
  const unresolved = err?.outcome === "unresolved";
  return (
    <section className="mx-auto max-w-lg px-4 py-16" data-testid="payment-error">
      <h1
        className={`text-center text-xl font-semibold ${
          pending
            ? "text-[var(--status-warning)]"
            : unresolved
              ? "text-amber-400"
              : "text-[var(--status-error)]"
        }`}
      >
        {pending ? "입금을 기다리고 있습니다" : unresolved ? "결제 결과 확인 중" : "결제를 완료하지 못했습니다"}
      </h1>
      <div role="alert" className="mt-6 rounded-lg bg-[var(--surface-strong)] p-4">
        <p className="text-sm text-[var(--text-primary)]">{err?.message}</p>
        {/* ★조치 — 이게 없으면 사용자는 같은 실패를 반복한다. */}
        <p className="mt-3 text-sm text-[var(--text-secondary)]" data-testid="payment-remediation">
          {err?.remediation}
        </p>
        {err?.code && err.code !== "UNKNOWN" ? (
          <p className="mt-3 text-xs text-[var(--text-tertiary)]">오류 코드: {err.code}</p>
        ) : null}
      </div>
      {unresolved ? (
        // ★미확정일 때는 '다시 시도'를 **주지 않는다** — 이중 결제를 유도하게 된다.
        <p className="mt-4 text-center text-xs text-[var(--status-warning)]">
          중복 결제하지 마세요. 카드에서 결제되었을 수 있습니다.
        </p>
      ) : null}
      <div className="mt-6 flex justify-center gap-3">
        <Link
          href={coinsHref}
          className="rounded-md bg-[var(--accent-primary)] px-5 py-2 text-sm font-medium text-white"
        >
          충전 내역 확인
        </Link>
      </div>
    </section>
  );
}
