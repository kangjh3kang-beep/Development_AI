/**
 * 결제 오류 → **사용자 문구 + 조치**.
 *
 * ## 왜 별도 모듈인가
 *
 * 이 앱에는 코드→조치 매핑이 **한 곳도 없다**(실측: `extractErrorMessage` 계열 함수가
 * **31개 중복**인데 **어느 것도 코드로 분기하지 않고, 어느 것도 조치를 붙이지 않는다**).
 * 가장 가까운 것이 `lib/field-audit.ts:127` 의 `FINDING_COPY` 구조라 그 형태를 따랐다.
 *
 * ## 두 출처를 구별한다 — 이게 핵심이다
 *
 * | 출처 | 형태 | 처리 |
 * |---|---|---|
 * | **우리 서버** | `ApiClientError.payload.detail = {code,message,remediation,outcome}` | **그대로 쓴다** — 서버가 이미 판정했다 |
 * | **토스 failUrl** | `?code=&message=` (우리 서버를 안 거친다) | 이 파일의 표로 번역 |
 *
 * ★두 번째가 이 파일이 존재하는 이유다. 사용자가 결제창에서 취소하면 브라우저는
 *   **우리 서버를 거치지 않고** `failUrl` 로 온다 — 서버의 조치 문구가 닿지 않는다.
 *
 * ★`ApiClientError.message` 를 읽으면 안 된다 — HTTP 오류의 `message` 는 **항상 상수**
 *   `"API 요청 처리에 실패했습니다."` 다(`lib/api-client.ts:432-436` 실측). 사유는 `payload.detail`.
 */

export type PaymentOutcome = "rejected" | "pending" | "unresolved" | "unknown";

export type PaymentErrorView = {
  code: string;
  /** 무슨 일이 있었는지 */
  message: string;
  /** ★다음에 무엇을 하면 되는지 — 이게 비면 사용자는 같은 실패를 반복한다 */
  remediation: string;
  outcome: PaymentOutcome;
  /** 다시 시도할 가치가 있는가 → 화면이 '다시 시도' 버튼을 낼지 결정 */
  retryable: boolean;
};

/**
 * 토스 결제창이 `failUrl` 로 직접 넘겨주는 코드.
 * 출처: https://docs.tosspayments.com/reference/error-codes
 */
const TOSS_FAIL_COPY: Record<string, { message: string; remediation: string; retryable: boolean }> = {
  PAY_PROCESS_CANCELED: {
    message: "결제를 취소하셨습니다.",
    remediation: "결제 금액은 청구되지 않았습니다. 다시 충전하시려면 결제하기를 눌러 주세요.",
    retryable: true,
  },
  PAY_PROCESS_ABORTED: {
    message: "결제 진행 중 오류가 발생했습니다.",
    remediation: "잠시 후 다시 시도해 주세요. 반복되면 다른 결제수단을 이용해 주세요.",
    retryable: true,
  },
  REJECT_CARD_COMPANY: {
    message: "카드사에서 결제를 거절했습니다.",
    remediation: "한도·잔액·비밀번호를 확인하시거나 다른 카드로 결제해 주세요.",
    retryable: true,
  },
  INVALID_CARD_EXPIRATION: {
    message: "카드 유효기간이 올바르지 않습니다.",
    remediation: "유효기간을 다시 확인해 주세요.",
    retryable: true,
  },
  INVALID_STOPPED_CARD: {
    message: "정지된 카드입니다.",
    remediation: "다른 카드로 결제해 주세요.",
    retryable: true,
  },
  EXCEED_MAX_AMOUNT: {
    message: "카드 한도를 초과했습니다.",
    remediation: "충전 금액을 낮추거나 다른 카드로 결제해 주세요.",
    retryable: true,
  },
  EXCEED_MAX_ONE_DAY_AMOUNT: {
    message: "1일 결제 한도를 초과했습니다.",
    remediation: "내일 다시 시도하시거나 다른 결제수단을 이용해 주세요.",
    retryable: false,
  },
  BELOW_MINIMUM_AMOUNT: {
    message: "최소 결제 금액 미만입니다.",
    remediation: "충전 금액을 높여 주세요.",
    retryable: true,
  },
  NOT_SUPPORTED_INSTALLMENT_PLAN_CARD_OR_MERCHANT: {
    message: "이 카드는 할부를 지원하지 않습니다.",
    remediation: "일시불로 결제하시거나 다른 카드를 이용해 주세요.",
    retryable: true,
  },
  // ★아래는 **사용자 잘못이 아니다** — 우리 설정 문제다. 그렇게 말해야 한다.
  UNAUTHORIZED_KEY: {
    message: "결제 시스템 설정에 문제가 있습니다.",
    remediation: "고객센터로 문의해 주세요. 결제 금액은 청구되지 않았습니다.",
    retryable: false,
  },
  FORBIDDEN_REQUEST: {
    message: "결제 시스템 설정에 문제가 있습니다.",
    remediation: "고객센터로 문의해 주세요. 결제 금액은 청구되지 않았습니다.",
    retryable: false,
  },
};

/** 표에 없는 코드의 조치 — ★**침묵하지 않는다.** 벤더 문구를 그대로 보여 준다. */
function fallbackCopy(code: string, message: string): PaymentErrorView {
  return {
    code: code || "UNKNOWN",
    message: message || "결제에 실패했습니다.",
    remediation:
      "잠시 후 다시 시도해 주세요. 반복되면 오류 코드와 함께 고객센터로 문의해 주세요.",
    outcome: "rejected",
    retryable: true,
  };
}

/** 토스 `failUrl` 의 쿼리 파라미터를 사용자 화면으로 번역한다. */
export function fromTossFailUrl(code: string | null, message: string | null): PaymentErrorView {
  const c = (code ?? "").trim();
  const hit = TOSS_FAIL_COPY[c];
  if (!hit) return fallbackCopy(c, (message ?? "").trim());
  return { code: c, ...hit, outcome: "rejected" };
}

type StructuredDetail = {
  code?: unknown;
  message?: unknown;
  remediation?: unknown;
  outcome?: unknown;
  retryable?: unknown;
};

/**
 * 우리 서버가 돌려준 오류를 화면용으로 바꾼다.
 *
 * ★서버는 이미 `{code, message, remediation, outcome}` 로 판정해 보낸다 —
 *   여기서 **다시 판정하지 않는다**(두 곳이 판정하면 반드시 갈라진다).
 */
export function fromApiError(error: unknown, fallback: string): PaymentErrorView {
  const payload = (error as { payload?: { detail?: unknown } } | null)?.payload;
  const detail = payload?.detail;
  if (detail && typeof detail === "object") {
    const d = detail as StructuredDetail;
    if (typeof d.message === "string" && typeof d.remediation === "string") {
      const outcome =
        d.outcome === "pending" || d.outcome === "unresolved" || d.outcome === "rejected"
          ? (d.outcome as PaymentOutcome)
          : "unknown";
      return {
        code: typeof d.code === "string" ? d.code : "UNKNOWN",
        message: d.message,
        remediation: d.remediation,
        outcome,
        retryable: d.retryable === true,
      };
    }
  }
  // 구조화되지 않은 오류(네트워크·타임아웃 등). `detail` 이 문자열이면 그것을 쓴다.
  const text = typeof detail === "string" ? detail : fallback;
  return {
    code: "UNKNOWN",
    message: text,
    remediation: "네트워크 상태를 확인하고 다시 시도해 주세요.",
    outcome: "unknown",
    retryable: true,
  };
}

/** ★모든 코드가 문구와 **조치**를 갖는지 테스트가 전수로 확인한다(파생형). */
export const TOSS_FAIL_CODES = Object.keys(TOSS_FAIL_COPY);
export { TOSS_FAIL_COPY };
