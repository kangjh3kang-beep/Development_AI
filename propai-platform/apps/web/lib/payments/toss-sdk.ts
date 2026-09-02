/**
 * 토스페이먼츠 SDK 로더 + 결제창 실행.
 *
 * ★로더 형태는 `lib/kakao-map.ts:25-53` 을 따른다 — 이 저장소의 **정답 기준선**이다.
 *   (`next/script` 는 이 앱에서 **0회** 사용된다 — 실측. 표준은 수동 주입이다)
 *
 * ★핵심은 `onerror` 다. 그게 없으면 스크립트 로드 실패 시 **영원히 await 에 매달리고**
 *   싱글턴 플래그가 고착돼 재시도조차 불가능해진다 —
 *   `KakaoAddressSearch.tsx` 가 그 결함을 겪고 고친 이력을 주석으로 남겨 뒀다.
 *
 * ★CSP: 이 앱에는 CSP 가 **없다**(라이브 프로브 `curl -D - https://4t8t.net/...` 로
 *   `content-security-policy` 0건 · 대조군 `x-frame-options` 1건으로 프로브 생존 확인).
 *   따라서 `js.tosspayments.com` 로드를 막는 것이 없다. **단 이건 저장소 밖에서 바뀔 수
 *   있다**(Cloudflare Transform Rule) — 결제창이 안 뜨면 그 프로브부터 다시 돌려라.
 */

const SDK_SRC = "https://js.tosspayments.com/v2/standard";
const SDK_MARK = "data-toss-payments";

/** 결제창이 뜨지 않는 이유를 **구별**한다 — "안 뜬다"만으로는 고칠 수 없다. */
export class TossSdkError extends Error {
  readonly reason: "load_failed" | "not_configured" | "init_failed";
  constructor(reason: TossSdkError["reason"], message: string) {
    super(message);
    this.name = "TossSdkError";
    this.reason = reason;
  }
}

type TossPaymentsFactory = (clientKey: string) => {
  widgets: (opts: { customerKey: string }) => TossWidgets;
};

export type TossWidgets = {
  setAmount: (a: { value: number; currency: string }) => Promise<void>;
  renderPaymentWindow: (o: {
    variantKey: { paymentMethod: string; agreement: string };
  }) => Promise<{ on: (ev: string, cb: (p: unknown) => void) => void }>;
  requestPayment: (o: {
    orderId: string;
    orderName: string;
    successUrl: string;
    failUrl: string;
    customerEmail?: string;
    customerName?: string;
  }) => Promise<void>;
};

let loading: Promise<TossPaymentsFactory> | null = null;

/** SDK 를 한 번만 싣는다. 실패하면 싱글턴을 풀어 **재시도를 허용**한다. */
export function loadTossSdk(): Promise<TossPaymentsFactory> {
  if (typeof window === "undefined") {
    return Promise.reject(new TossSdkError("load_failed", "서버에서는 결제창을 열 수 없습니다."));
  }
  const w = window as unknown as { TossPayments?: TossPaymentsFactory };
  if (w.TossPayments) return Promise.resolve(w.TossPayments);
  if (loading) return loading;

  loading = new Promise<TossPaymentsFactory>((resolve, reject) => {
    const onReady = () => {
      const f = (window as unknown as { TossPayments?: TossPaymentsFactory }).TossPayments;
      if (f) resolve(f);
      else {
        loading = null; // ★재시도 허용
        reject(new TossSdkError("init_failed", "결제 모듈 초기화에 실패했습니다."));
      }
    };
    const existing = document.querySelector(`script[${SDK_MARK}]`) as HTMLScriptElement | null;
    if (existing) {
      if (w.TossPayments) onReady();
      else existing.addEventListener("load", onReady);
      return;
    }
    const el = document.createElement("script");
    el.src = SDK_SRC;
    el.async = true;
    el.setAttribute(SDK_MARK, "1");
    el.onload = onReady;
    el.onerror = () => {
      // ★싱글턴을 풀지 않으면 이후 모든 시도가 죽은 약속에 매달린다.
      loading = null;
      el.remove();
      reject(
        new TossSdkError(
          "load_failed",
          "결제 모듈을 불러오지 못했습니다. 네트워크를 확인하고 다시 시도해 주세요.",
        ),
      );
    };
    document.head.appendChild(el);
  });
  return loading;
}

export type TossConfig = {
  payment_mode: string;
  client_key: string | null;
  test_mode: boolean | null;
};

/** 결제창을 열고 결제를 요청한다. 성공하면 브라우저가 `successUrl` 로 이동한다. */
export async function openPaymentWindow(opts: {
  config: TossConfig;
  /** ★토스에 보내는 주문 식별자 = 우리 주문 **uuid**(엔트로피·텔레메트리 누출 대응) */
  orderId: string;
  /** ★사람이 읽는 주문번호 — 토스 대시보드에서 대사할 때 필요하다 */
  orderNo: string;
  amount: number;
  customerKey: string;
  /** 리다이렉트 기준 경로(로케일 포함). 예: `/ko/mypage/coins` */
  returnBase: string;
}): Promise<void> {
  const { config, orderId, orderNo, amount, customerKey, returnBase } = opts;
  if (config.payment_mode !== "toss" || !config.client_key) {
    throw new TossSdkError("not_configured", "현재 카드 결제를 사용할 수 없습니다.");
  }
  const factory = await loadTossSdk();
  const widgets = factory(config.client_key).widgets({ customerKey });

  await widgets.setAmount({ value: amount, currency: "KRW" });
  const paymentWindow = await widgets.renderPaymentWindow({
    variantKey: { paymentMethod: "DEFAULT", agreement: "AGREEMENT" },
  });

  paymentWindow.on("paymentRequest", () => {
    // ★`successUrl`/`failUrl` 은 **서버가 아니라 이 코드가** 만든다. 쿼리 파라미터에서
    //   가져오면 신뢰 도메인을 경유하는 오픈 리다이렉트가 된다 — 절대 그렇게 하지 않는다.
    const origin = window.location.origin;
    void widgets.requestPayment({
      orderId,
      // 사람이 읽는 번호를 실어 벤더 대시보드에서 대사할 수 있게 한다.
      orderName: `PropAI 코인 충전 ${orderNo}`,
      successUrl: `${origin}${returnBase}/success`,
      failUrl: `${origin}${returnBase}/fail`,
    });
  });
}
