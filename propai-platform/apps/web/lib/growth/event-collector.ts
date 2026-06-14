/**
 * 자가성장 엔진 — 프론트 텔레메트리 수집 코어 (설계서 §3.1, Phase 1).
 *
 * 역할
 * - 사용자 행동·오류·API·성능 이벤트를 모아 백엔드로 배치 전송한다.
 * - 백엔드 수신부: POST /api/v1/growth/events (apps/api/app/routers/growth.py).
 *   배치 래핑은 { events: [...] } 객체 형태이며 1회 최대 100건이다.
 *
 * 안전 원칙 (가장 중요)
 * - 이 코드는 절대로 본래 앱 동작을 막지 않는다. 모든 경로는 try/catch 로 격리하고,
 *   실패는 조용히 무시한다(논블로킹).
 * - SSR/빌드 환경 안전: 모든 브라우저 API 접근은 typeof window 가드를 통과해야 한다.
 *
 * 프라이버시
 * - 전송 직전 클라이언트 1차 마스킹(이메일/전화/주소 정규식 치환).
 * - user_id 원본은 서버가 HMAC 익명화하므로 클라는 보내지 않는다(여기서는 수집 안 함).
 */

// API base 오리진 단일 해석(api-client SSOT 공유 — 전송 대상이 백엔드와 일치하도록).
import { resolveApiOrigin } from "@/lib/api-client";

// ── 백엔드 화이트리스트와 1:1 일치하는 이벤트 타입(growth.py _ALLOWED_TYPES) ──
export type GrowthEventType =
  | "page_view"
  | "click"
  | "funnel_step"
  | "api_call"
  | "api_error"
  | "js_error"
  | "promise_rejection"
  | "web_vital"
  | "llm_call"
  | "verify_result"
  | "fallback"
  | "heal_action";

export type GrowthSeverity = "info" | "warn" | "error" | "critical";

/** 단일 이벤트(백엔드 GrowthEventIn 스키마와 필드명 1:1 일치). */
interface GrowthEvent {
  event_id: string;
  event_type: GrowthEventType;
  surface: "web";
  route: string | null;
  status_code: number | null;
  latency_ms: number | null;
  severity: GrowthSeverity | null;
  service: string | null;
  session_id: string | null;
  app_version: string | null;
  payload: Record<string, unknown> | null;
}

/** trackEvent 호출자가 넘기는 속성(나머지는 collector 가 채움). */
export interface TrackEventProps {
  route?: string | null;
  status_code?: number | null;
  latency_ms?: number | null;
  severity?: GrowthSeverity | null;
  service?: string | null;
  payload?: Record<string, unknown> | null;
}

// ── 설정 상수 ────────────────────────────────────────────────────────
const ENDPOINT_PATH = "/api/v1/growth/events";
const FLUSH_INTERVAL_MS = 5_000; // 5초마다 자동 flush
const FLUSH_THRESHOLD = 20; // 또는 20건 쌓이면 즉시 flush
const MAX_BATCH = 100; // 백엔드 _MAX_BATCH 와 동일(1회 전송 상한)
const RING_CAPACITY = 200; // 링버퍼 용량(폭주 시 오래된 것 폐기, 메모리 보호)
const SESSION_KEY = "propai_growth_session"; // sessionStorage 세션 UUID 키

// ── 샘플링 비율(설계서: page_view·web_vital 15%, js_error·api_error 100%) ──
const SAMPLE_RATES: Partial<Record<GrowthEventType, number>> = {
  page_view: 0.15,
  web_vital: 0.15,
  click: 0.15,
  funnel_step: 0.15,
  // 오류·API 오류는 전수(미지정 시 기본 1.0)
};

// ── PII 1차 마스킹 정규식 ────────────────────────────────────────────
const EMAIL_RE = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;
// 한국 휴대폰만 좁게 매칭(010/011/016/017/018/019 앵커, 총 10~11자리).
// ⚠️ 이전 정규식은 일반 7자리+ 숫자열(가격·면적·좌표·PNU)까지 [phone]으로
//    오마스킹했다. 휴대폰 앵커(01[016789])로 시작하는 번호만 마스킹한다.
//    구분자(-, ., 공백)는 허용하되 앵커 없는 일반 숫자열은 매칭하지 않는다.
const PHONE_RE = /\b01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}\b/g;
// 한국 주소 키워드(도로명/지번) — 번지·동·호 토큰 마스킹
const ADDRESS_RE = /[가-힣0-9]+(?:로|길)\s?\d+(?:-\d+)?(?:번길)?|\d+동\s?\d+호|\d+번지/g;

// ── 모듈 상태 ────────────────────────────────────────────────────────
const ring: GrowthEvent[] = [];
let flushTimer: ReturnType<typeof setInterval> | null = null;
let initialized = false;
let cachedSessionId: string | null = null;
let cachedAppVersion: string | null = null;

/** 안전한 UUID 생성(crypto.randomUUID 우선, 폴백 포함). */
function safeUuid(): string {
  try {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
  } catch {
    /* noop */
  }
  // 폴백: 충분히 고유한 비암호 UUID v4 유사값
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/** sessionStorage 기반 세션 UUID(브라우저 세션 유지). 실패 시 메모리 폴백. */
function getSessionId(): string | null {
  if (cachedSessionId) return cachedSessionId;
  if (typeof window === "undefined") return null;
  try {
    const existing = window.sessionStorage.getItem(SESSION_KEY);
    if (existing) {
      cachedSessionId = existing;
      return existing;
    }
    const fresh = safeUuid();
    window.sessionStorage.setItem(SESSION_KEY, fresh);
    cachedSessionId = fresh;
    return fresh;
  } catch {
    // sessionStorage 차단 환경: 메모리 세션으로 폴백
    if (!cachedSessionId) cachedSessionId = safeUuid();
    return cachedSessionId;
  }
}

/**
 * 앱 버전(sw CACHE_NAME, 예: "propai-v169-payroll-deduct") 베스트에포트 조회.
 * Service Worker 캐시 키에서 propai-v* 항목을 찾아 사용한다. 실패 시 null.
 * 비동기지만 결과는 캐싱하고, 첫 이벤트들은 버전 없이 전송될 수 있다(허용).
 */
function primeAppVersion(): void {
  if (cachedAppVersion || typeof window === "undefined") return;
  try {
    // 1차 소스: 빌드타임 주입 버전(NEXT_PUBLIC_APP_VERSION). 주입돼 있으면 즉시 사용.
    //   (빌드에 미주입이면 undefined → 아래 sw 캐시키 폴백으로 진행, 무해.)
    const buildVersion = process.env.NEXT_PUBLIC_APP_VERSION?.trim();
    if (buildVersion) {
      cachedAppVersion = buildVersion;
      return;
    }
    // 2차(폴백): Service Worker 캐시 키(propai-v*)에서 비동기 조회.
    if (typeof caches === "undefined" || !caches.keys) return;
    void caches
      .keys()
      .then((keys) => {
        const hit = keys.find((k) => k.startsWith("propai-"));
        if (hit) cachedAppVersion = hit;
      })
      .catch(() => {
        /* noop */
      });
  } catch {
    /* noop */
  }
}

/** 현재 라우트(쿼리스트링 제거). SSR 안전. */
function currentRoute(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.location.pathname || null;
  } catch {
    return null;
  }
}

/** 문자열 내 PII 1차 마스킹. */
function maskString(value: string): string {
  try {
    return value
      .replace(EMAIL_RE, "[email]")
      .replace(ADDRESS_RE, "[addr]")
      .replace(PHONE_RE, "[phone]");
  } catch {
    return value;
  }
}

/** payload(object) 의 문자열 값을 재귀 마스킹(얕은 깊이 제한으로 폭주 방지). */
function maskPayload(input: unknown, depth = 0): unknown {
  if (input == null || depth > 4) return input;
  if (typeof input === "string") return maskString(input);
  if (typeof input === "number" || typeof input === "boolean") return input;
  if (Array.isArray(input)) {
    return input.slice(0, 50).map((v) => maskPayload(v, depth + 1));
  }
  if (typeof input === "object") {
    const out: Record<string, unknown> = {};
    try {
      for (const [k, v] of Object.entries(input as Record<string, unknown>)) {
        out[k] = maskPayload(v, depth + 1);
      }
    } catch {
      return undefined;
    }
    return out;
  }
  return undefined;
}

/** 샘플링 통과 여부(전수 타입은 항상 통과). */
function passesSampling(type: GrowthEventType): boolean {
  const rate = SAMPLE_RATES[type];
  if (rate == null || rate >= 1) return true;
  return Math.random() < rate;
}

/**
 * 공개 API — 이벤트 1건 수집(논블로킹·전부 try/catch).
 * 샘플링·PII 마스킹·링버퍼 적재까지 수행한다.
 */
export function trackEvent(type: GrowthEventType, props: TrackEventProps = {}): void {
  try {
    if (typeof window === "undefined") return;
    if (!passesSampling(type)) return;

    const event: GrowthEvent = {
      event_id: safeUuid(),
      event_type: type,
      surface: "web",
      route: props.route ?? currentRoute(),
      status_code: props.status_code ?? null,
      latency_ms: props.latency_ms ?? null,
      severity: props.severity ?? null,
      service: props.service ?? null,
      session_id: getSessionId(),
      app_version: cachedAppVersion,
      payload: (props.payload ? (maskPayload(props.payload) as Record<string, unknown>) : null) ?? null,
    };

    ring.push(event);
    // 링버퍼 용량 초과 시 가장 오래된 항목 폐기(메모리 보호).
    while (ring.length > RING_CAPACITY) ring.shift();

    if (ring.length >= FLUSH_THRESHOLD) {
      flush();
    }
  } catch {
    /* 수집 실패는 앱 동작에 영향 주지 않는다 */
  }
}

/**
 * growth 엔드포인트 절대 URL.
 * ⚠️ 상대경로(/api/v1/growth/events)는 프론트 오리진(A1 www.4t8t.net)으로 가서
 *    404 가 된다. growth 수신부는 API 백엔드(api.4t8t.net, Micro)에 있으므로
 *    api-client 와 동일한 절대 API base 로 보낸다.
 *    resolveApiOrigin() 은 버전 prefix(/api/v1)를 포함하지 않는 순수 오리진을
 *    반환하므로(api-client.ts getRequestUrl 규칙과 동일) 여기서 /api/v1 을 1회만
 *    붙인다(이중 prefix 함정 회피). ENDPOINT_PATH 는 이미 /api/v1/... 형태이므로
 *    오리진에 그대로 결합한다.
 */
function endpointUrl(): string {
  try {
    const origin = resolveApiOrigin();
    if (origin) return `${origin}${ENDPOINT_PATH}`;
  } catch {
    /* noop */
  }
  // 폴백: 오리진 해석 실패 시 상대경로(동일 오리진 가정).
  return ENDPOINT_PATH;
}

/**
 * 링버퍼를 비우고 백엔드로 배치 전송.
 * sendBeacon 우선(언로드 안전), 실패 시 fetch keepalive 폴백. 전부 논블로킹.
 */
export function flush(): void {
  try {
    if (typeof window === "undefined") return;
    if (ring.length === 0) return;

    // 1회 전송 상한(MAX_BATCH)만큼 꺼낸다.
    const batch = ring.splice(0, MAX_BATCH);
    if (batch.length === 0) return;

    const body = JSON.stringify({ events: batch });
    const url = endpointUrl();

    // 1) sendBeacon(언로드 시에도 전송 보장). Blob 으로 content-type 명시.
    let sent = false;
    try {
      if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
        const blob = new Blob([body], { type: "application/json" });
        sent = navigator.sendBeacon(url, blob);
      }
    } catch {
      sent = false;
    }

    // 2) 폴백: fetch keepalive(인증 헤더 불필요 — 익명 허용 엔드포인트).
    if (!sent) {
      try {
        void fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body,
          keepalive: true,
        }).catch(() => {
          /* 전송 실패는 무시(수집은 베스트에포트) */
        });
      } catch {
        /* noop */
      }
    }
  } catch {
    /* noop */
  }
}

/** window.onerror — 런타임 JS 오류(전수 수집). */
function handleWindowError(event: ErrorEvent): void {
  try {
    trackEvent("js_error", {
      severity: "error",
      payload: {
        message: maskString(String(event.message ?? "")),
        filename: event.filename ?? null,
        lineno: event.lineno ?? null,
        colno: event.colno ?? null,
        stack: event.error?.stack ? maskString(String(event.error.stack)).slice(0, 2000) : null,
      },
    });
  } catch {
    /* noop */
  }
}

/** unhandledrejection — 처리되지 않은 Promise 거부(전수 수집). */
function handleRejection(event: PromiseRejectionEvent): void {
  try {
    const reason = event.reason;
    const message =
      reason instanceof Error
        ? reason.message
        : typeof reason === "string"
          ? reason
          : (() => {
              try {
                return JSON.stringify(reason);
              } catch {
                return String(reason);
              }
            })();
    trackEvent("promise_rejection", {
      severity: "error",
      payload: {
        message: maskString(String(message ?? "")).slice(0, 1000),
        stack: reason instanceof Error && reason.stack ? maskString(reason.stack).slice(0, 2000) : null,
      },
    });
  } catch {
    /* noop */
  }
}

/** Web Vitals(LCP/CLS/INP) — PerformanceObserver 기반(web-vitals 의존성 없이). */
function registerWebVitals(): void {
  try {
    if (typeof PerformanceObserver === "undefined") return;

    // LCP — 가장 큰 콘텐츠풀 페인트(마지막 값 사용)
    try {
      let lcpValue = 0;
      const lcpObserver = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        const last = entries[entries.length - 1] as PerformanceEntry & { renderTime?: number; startTime: number };
        if (last) lcpValue = last.renderTime || last.startTime || lcpValue;
      });
      lcpObserver.observe({ type: "largest-contentful-paint", buffered: true } as PerformanceObserverInit);
      // 페이지 숨김 시점에 최종 LCP 기록(샘플링은 trackEvent 가 적용).
      const reportLcp = () => {
        if (lcpValue > 0) {
          trackEvent("web_vital", { payload: { metric: "LCP", value: Math.round(lcpValue) } });
          lcpValue = 0;
        }
      };
      window.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "hidden") reportLcp();
      });
    } catch {
      /* noop */
    }

    // CLS — 누적 레이아웃 이동(세션 합산 근사)
    try {
      let clsValue = 0;
      const clsObserver = new PerformanceObserver((list) => {
        for (const entry of list.getEntries() as Array<PerformanceEntry & { value?: number; hadRecentInput?: boolean }>) {
          if (!entry.hadRecentInput && typeof entry.value === "number") {
            clsValue += entry.value;
          }
        }
      });
      clsObserver.observe({ type: "layout-shift", buffered: true } as PerformanceObserverInit);
      window.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "hidden" && clsValue > 0) {
          trackEvent("web_vital", { payload: { metric: "CLS", value: Math.round(clsValue * 1000) / 1000 } });
          clsValue = 0;
        }
      });
    } catch {
      /* noop */
    }

    // INP 근사 — event timing 중 최대 지연(첫 입력 포함)
    try {
      let maxInp = 0;
      const inpObserver = new PerformanceObserver((list) => {
        for (const entry of list.getEntries() as Array<PerformanceEntry & { duration: number }>) {
          if (entry.duration > maxInp) maxInp = entry.duration;
        }
      });
      inpObserver.observe({ type: "event", buffered: true, durationThreshold: 40 } as PerformanceObserverInit);
      window.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "hidden" && maxInp > 0) {
          trackEvent("web_vital", { payload: { metric: "INP", value: Math.round(maxInp) } });
          maxInp = 0;
        }
      });
    } catch {
      /* noop */
    }
  } catch {
    /* noop */
  }
}

/** 언로드/숨김 시 잔여 이벤트 flush. */
function handleVisibility(): void {
  try {
    if (document.visibilityState === "hidden") flush();
  } catch {
    /* noop */
  }
}

/**
 * 수집기 초기화(1회). 전역 핸들러 등록·flush 타이머 시작·web vitals 관측.
 * useGrowthEvents 훅이 마운트 시 호출한다. 중복 호출은 무시.
 */
export function initEventCollector(): void {
  try {
    if (initialized || typeof window === "undefined") return;
    initialized = true;

    primeAppVersion();
    getSessionId();

    window.addEventListener("error", handleWindowError);
    window.addEventListener("unhandledrejection", handleRejection);
    window.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("pagehide", flush);

    registerWebVitals();

    flushTimer = setInterval(flush, FLUSH_INTERVAL_MS);
  } catch {
    /* noop */
  }
}

/** 수집기 정리(언마운트). 잔여 flush 후 핸들러 해제. */
export function teardownEventCollector(): void {
  try {
    if (!initialized || typeof window === "undefined") return;
    initialized = false;

    flush();

    window.removeEventListener("error", handleWindowError);
    window.removeEventListener("unhandledrejection", handleRejection);
    window.removeEventListener("visibilitychange", handleVisibility);
    window.removeEventListener("pagehide", flush);

    if (flushTimer != null) {
      clearInterval(flushTimer);
      flushTimer = null;
    }
  } catch {
    /* noop */
  }
}

/** growth 엔드포인트 경로 판정(자기수집 무한루프 방지용 — api-client 에서 사용). */
export function isGrowthEndpoint(path: string): boolean {
  try {
    return path.includes("/growth/events");
  } catch {
    return false;
  }
}
