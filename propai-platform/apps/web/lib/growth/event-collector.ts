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
  | "heal_action"
  // ★선택 오염 관측(2026-08-24) — "고지는 하는데 빈도를 못 잰다"를 푼다.
  //   화면은 이미 "하나의 개발 부지가 아닙니다"를 고지하지만, 그 일이 **얼마나 자주**
  //   일어나는지는 아무도 몰랐다. 빈도를 모르면 데이터 정리의 우선순위를 정할 수 없다.
  //   ★이 항목은 백엔드 `growth.py:_ALLOWED_TYPES` 와 **같은 커밋에서** 추가해야 한다 —
  //     한쪽만 추가하면 서버가 조용히 `rejected` 로 버리고 화면·테스트는 초록이다.
  //     그 침묵을 `lib/growth/__tests__/event-type-whitelist.parity.test.ts` 가 잠근다.
  | "selection_contamination_observation";

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
/**
 * ★**1회 전송 본문의 바이트 상한.**
 *
 * `navigator.sendBeacon` 과 `fetch(keepalive:true)` 는 **같은 64KiB 예산**을 공유한다
 * (둘 다 Fetch 표준의 keepalive 요청 본문 한도를 쓴다). 그래서 본문이 그 한도를 넘으면
 * **1차와 2차가 같은 이유로 실패**하고, 종전 구현은 그것을 `.catch(() => {})` 로 삼킨 뒤
 * 이미 `splice()` 로 링에서 빼낸 배치를 되돌리지 않아 **조용한 전손**이 됐다.
 *
 * ★**이 값이 동시성을 보장하지는 않는다**(독립 리뷰 지적 — 종전 주석은 그렇게 읽혔다).
 * keepalive 예산은 **출처당·동시 in-flight 합산**이라, `visibilitychange` 와 `pagehide` 가
 * 각각 배치를 꺼내면 56,000 × 2 > 65,536 으로 **둘 다 실패할 수 있다.**
 * 그 경우의 안전은 이 숫자가 아니라 **실패 시 링으로 되돌리는 것**(`restoreUnsent`)이 준다 —
 * 브라우저가 `sendBeacon=false` 나 fetch 거부로 **알려 주고**, 우리는 다음 틱에 다시 보낸다.
 * 즉 이 상수는 **처리량 최적화**이고, **무손실은 복원 경로가 보장한다.**
 */
const MAX_BODY_BYTES = 56_000;
/** 이벤트 하나가 단독으로도 예산을 넘을 때 문자열 필드를 줄이는 상한(형제 `stack` 과 같은 축). */
export const MAX_FIELD_CHARS = 2_000;
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
/**
 * ★수량자에 **상한이 있어야 한다** — 없으면 2차 백트래킹으로 메인 스레드가 멈춘다.
 *
 * 종전 `[a-zA-Z0-9._%+-]+@` 는 `@` 가 없는 긴 문자열에서 각 시작위치마다 끝까지 삼켰다가
 * 되돌아온다. 실측(2026-08-28, node · 같은 입력 `"x".repeat(n)`):
 *
 *     n=4,000    무상한 15.1ms  →  상한 1.1ms
 *     n=10,000   무상한 90.9ms  →  상한 3.1ms
 *     n=50,000   무상한 **2,450.9ms**  →  상한 **14.6ms**   (168배)
 *
 * ★대조군: 같은 길이라도 `@` 가 있으면 무상한도 0.0ms 다 — 길이가 아니라 **백트래킹**이
 *   원인이라는 증거다.
 *
 * 상한값은 RFC 5321 의 한도를 쓴다(local-part 64 · domain 255). 따라서 **RFC 유효한
 * 이메일은 종전과 동일하게 전부 마스킹된다** — 탐지 동등성을 6개 입력으로 대조 확인했다.
 * ★한계(정직하게): local-part 가 64자를 **넘는** RFC 무효 문자열은 앞부분 일부가 남는다.
 */
const EMAIL_RE = /[a-zA-Z0-9._%+-]{1,64}@[a-zA-Z0-9.-]{1,255}\.[a-zA-Z]{2,}/g;
// 한국 휴대폰만 좁게 매칭(010/011/016/017/018/019 앵커, 총 10~11자리).
// ⚠️ 이전 정규식은 일반 7자리+ 숫자열(가격·면적·좌표·PNU)까지 [phone]으로
//    오마스킹했다. 휴대폰 앵커(01[016789])로 시작하는 번호만 마스킹한다.
//    구분자(-, ., 공백)는 허용하되 앵커 없는 일반 숫자열은 매칭하지 않는다.
const PHONE_RE = /\b01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}\b/g;
// 한국 주소 키워드(도로명/지번) — 번지·동·호 토큰 마스킹
const ADDRESS_RE = /[가-힣0-9]+(?:로|길)\s?\d+(?:-\d+)?(?:번길)?|\d+동\s?\d+호|\d+번지/g;

// ── 모듈 상태 ────────────────────────────────────────────────────────
const ring: GrowthEvent[] = [];
/**
 * ★전송을 **포기해서 버린** 이벤트 수(누적). 전손은 정의상 DB 에 0행이라 사후 조회가
 * 원리적으로 불가능하다 — 침묵을 관측 가능하게 만들려면 **보내는 쪽이 세는 수밖에 없다**.
 */
let droppedEvents = 0;
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

/**
 * ★**자르고 나서 마스킹한다** — 순서가 성능 계약이다.
 *
 * `maskString` 의 `EMAIL_RE`(`[a-zA-Z0-9._%+-]+@…`)는 `@` 가 없는 긴 문자열에서
 * **2차 백트래킹**을 한다. 실측(2026-08-28, node):
 *
 *     1,000자 9.6ms · 2,000자 22.7ms · 4,000자 76.8ms · **10,000자 432ms**
 *     (대조군: 같은 길이라도 `@` 가 있으면 0.0ms — 백트래킹이 원인이라는 증거)
 *
 * 종전은 `maskString(전체).slice(0, N)` 이라 **자르기 전에 전체를 스캔**했다. 즉 상한을
 * 걸어도 비용은 안 줄었고, 무상한이던 `js_error.message` 는 **사용자 메인 스레드**를
 * 초 단위로 멈출 수 있었다(10만자면 산술적으로 ~40초 규모).
 *
 * 자르는 창을 `cap` 보다 조금 넓게 잡아 마스킹한 뒤 최종 절단한다 — 경계에 걸친 이메일이
 * **부분만 남아 노출되는 것**을 막기 위해서다(창 안에 온전히 들어오면 통째로 마스킹된다).
 */
const MASK_BOUNDARY_MARGIN = 256;

function maskCapped(value: string, cap: number): string {
  return maskString(value.slice(0, cap + MASK_BOUNDARY_MARGIN)).slice(0, cap);
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
    // ★이 축출도 **센다**. 종전에는 여기서 버린 것이 계수기에 안 잡혀, 계수기가
    //   *"침묵을 관측 가능하게 한다"* 고 주장하면서 **가장 큰 침묵 채널**을 비워 뒀다
    //   (독립 리뷰 실측: 1,000건 투입 시 수백 건 축출 · 폐기계수 0).
    //   ★게다가 바이트 예산은 flush 당 배출량을 줄이므로 **이 채널의 압력을 올린다.**
    while (ring.length > RING_CAPACITY) {
      ring.shift();
      droppedEvents += 1;
    }

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
/** 문자열의 UTF-8 바이트 길이. `TextEncoder` 가 없는 환경은 보수적으로 과대 추정한다. */
function byteLength(text: string): number {
  try {
    if (typeof TextEncoder !== "undefined") return new TextEncoder().encode(text).length;
  } catch {
    /* noop */
  }
  // 폴백: 최악치(UTF-8 최대 4바이트/코드유닛)로 **과대** 추정한다.
  // ★과소 추정은 절벽으로 되돌아가므로, 모르면 크게 잡는 쪽이 안전측이다.
  return text.length * 4;
}

/**
 * 이벤트 하나가 **단독으로도** 예산을 넘을 때 문자열 필드를 줄인다.
 * 줄여도 못 담으면 `null` — 호출부가 **버린 것으로 세고**, 배치 전체를 잃지 않는다.
 */
function shrinkOversized(event: GrowthEvent): GrowthEvent | null {
  try {
    // ★**최상위만 훑으면 안 된다** — 형제 `maskPayload` 는 depth 4 까지 재귀하므로
    //   중첩 페이로드는 이 저장소가 정상으로 취급하는 모양이다. 최상위만 줄이면
    //   `{ detail: { blob: 60,000자 } }` 가 **줄이는 단계를 건너뛰고 곧장 폐기**된다
    //   (독립 리뷰 실측: 전송 0건 · 폐기 1건).
    const shrinkDeep = (v: unknown, depth: number): unknown => {
      if (typeof v === "string") return v.length > MAX_FIELD_CHARS ? v.slice(0, MAX_FIELD_CHARS) : v;
      if (depth >= 4 || v === null || typeof v !== "object") return v;
      if (Array.isArray(v)) return v.map((x) => shrinkDeep(x, depth + 1));
      const out: Record<string, unknown> = {};
      for (const [k, x] of Object.entries(v as Record<string, unknown>)) out[k] = shrinkDeep(x, depth + 1);
      return out;
    };
    const payload = event.payload;
    // ★`payload` 가 없어도 **무조건 폐기하지 않는다** — 최상위 필드(`route` 등)만으로
    //   예산을 넘는 경우가 있고, 그때도 폐기 전에 한 번은 재 봐야 한다.
    const shrunk = payload ? (shrinkDeep(payload, 0) as Record<string, unknown>) : null;
    const candidate: GrowthEvent = { ...event, payload: shrunk };
    return byteLength(JSON.stringify({ events: [candidate] })) <= MAX_BODY_BYTES ? candidate : null;
  } catch {
    return null;
  }
}

/**
 * 이벤트 하나의 전송 비용(바이트)을 **한 번만** 재고 기억한다.
 *
 * ★왜 캐시가 필요한가(2026-08-28 실측): 캐시가 없으면 `flush()` 가 돌 때마다 링에 남은
 *   **모든** 이벤트를 다시 `JSON.stringify` + 인코딩한다. 링은 최대 200건이고 flush 는
 *   5초마다 도는데, 대용량 오류(메시지 10,000자)가 쌓이면 그 재직렬화가 **사용자 메인
 *   스레드**에서 반복된다. 전수 테스트에서 이 O(n²) 가 30초 타임아웃으로 드러났다
 *   (단독 실행 417ms → 전수 실행 timeout). 이벤트는 만들어진 뒤 변경되지 않으므로
 *   객체 동일성으로 캐시해도 안전하다.
 */
const costCache = new WeakMap<GrowthEvent, number>();

function eventCost(event: GrowthEvent): number {
  const cached = costCache.get(event);
  if (cached !== undefined) return cached;
  // 항목 하나의 증분(직렬화 + 구분자 1바이트).
  let cost: number;
  try {
    cost = byteLength(JSON.stringify(event)) + 1;
  } catch {
    // 직렬화 불가는 배치 전체를 위협한다 — 예산을 넘는 값으로 쳐서 격리한다.
    cost = MAX_BODY_BYTES + 1;
  }
  costCache.set(event, cost);
  return cost;
}

/**
 * 링 **앞쪽**에서 예산 안에 담기는 만큼만 꺼낸다(건수 상한 `MAX_BATCH` 도 함께 지킨다).
 *
 * ★종전은 건수만 보고 `splice(0, MAX_BATCH)` 했다 — 바이트를 아무도 안 봤다.
 */
function takeBatchWithinBudget(): GrowthEvent[] {
  const batch: GrowthEvent[] = [];
  // `{"events":[]}` 자체의 고정 비용.
  let bytes = byteLength('{"events":[]}');

  while (ring.length > 0 && batch.length < MAX_BATCH) {
    const next = ring[0];
    const cost = eventCost(next);

    if (bytes + cost > MAX_BODY_BYTES) {
      if (batch.length > 0) break; // 다음 배치로 넘긴다(전손 아님).
      // 단독으로도 안 들어간다 — 줄여 보고, 그래도 안 되면 **그 한 건만** 버린다.
      ring.shift();
      const shrunk = shrinkOversized(next);
      if (!shrunk) {
        droppedEvents += 1;
        continue;
      }
      batch.push(shrunk);
      break;
    }

    ring.shift();
    batch.push(next);
    bytes += cost;
  }
  return batch;
}

/** 전송하지 못한 배치를 링 **앞**으로 되돌린다(순서 보존). 용량 초과분은 종전 정책대로 축출. */
function restoreUnsent(batch: GrowthEvent[]): void {
  try {
    if (batch.length === 0) return;
    ring.unshift(...batch);
    while (ring.length > RING_CAPACITY) {
      ring.shift();
      droppedEvents += 1;
    }
  } catch {
    /* noop */
  }
}

/** 테스트·진단용: 전송을 포기해 버린 누적 건수. */
export function getDroppedEventCount(): number {
  return droppedEvents;
}

export function flush(): void {
  try {
    if (typeof window === "undefined") return;
    if (ring.length === 0) return;

    // ★건수가 아니라 **바이트 예산** 안에서 꺼낸다.
    const batch = takeBatchWithinBudget();
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
          // ★삼키지 않는다 — 링으로 되돌려 다음 틱에 재시도한다.
          //   종전에는 여기서 사라졌고, 배치는 이미 링에서 빠진 뒤라 되돌릴 대상조차 없었다.
          restoreUnsent(batch);
        });
      } catch {
        restoreUnsent(batch);
      }
    }
  } catch {
    /* noop */
  }
}

/**
 * ★**조기 포착 버퍼** — `app/layout.tsx` 의 인라인 부트스트랩이 하이드레이션 **전에** 담아 둔 오류.
 *
 * 왜 필요한가(2026-08-27 라이브 실측): 아래 `handleWindowError` 는 `initEventCollector()` 에서
 * 등록되는데 그 호출이 `useGrowthEvents` 의 **`useEffect`** 안이라 하이드레이션 커밋 **이후**에 돈다.
 * 같은 타임라인에서 재니 `#418` = **237ms**, `addEventListener("error")` = **307ms** —
 * **오류가 등록보다 70ms 먼저 났다.** 그래서 초기 렌더 오류는 구조적으로 수집되지 않았다.
 */
export type EarlyCapturedError = {
  k: "error" | "rejection";
  m: string;
  f: string | null;
  l: number | null;
  c: number | null;
  s: string | null;
  t: number;
};
type EarlyStore = { buf: EarlyCapturedError[]; closed: boolean };

/**
 * 버퍼를 **비우고 닫는다**. 닫는 이유: 이 뒤에는 정식 핸들러가 붙으므로, 닫지 않으면 같은 오류가
 * **두 경로로 두 번** 전송된다(부트스트랩 리스너는 페이지 수명 내내 살아 있다).
 * ★순수 함수로 둔 이유는 이 계약을 **브라우저 없이 태우기** 위해서다.
 */
export function drainEarlyErrors(w: { __propaiEarly?: EarlyStore }): EarlyCapturedError[] {
  const s = w.__propaiEarly;
  if (!s || !Array.isArray(s.buf)) return [];
  const out = s.buf.slice();
  s.buf.length = 0;
  s.closed = true;
  return out;
}

/** window.onerror — 런타임 JS 오류(전수 수집). */
function handleWindowError(event: ErrorEvent): void {
  try {
    trackEvent("js_error", {
      severity: "error",
      payload: {
        // ★상한이 **형제와 어긋나 있었다**: 같은 함수의 `stack` 은 2,000자, 형제 함수
        //   `handleRejection` 의 `message` 는 1,000자인데 **이 줄만 무상한**이었다.
        //   무상한 필드는 이벤트 하나로 전송 예산(`MAX_BODY_BYTES`)을 넘길 수 있고,
        //   그때 종전 구현은 배치 전체를 조용히 잃었다.
        message: maskCapped(String(event.message ?? ""), MAX_FIELD_CHARS),
        // ★`filename` 은 **인라인 스크립트 오류에서 문서 URL 전체**가 된다(쿼리 포함).
        //   이 앱은 지번을 쿼리에 싣는다(`registry-analysis?addr=${encodeURIComponent(jibun)}`)
        //   — 형제 `message`·`stack` 은 전부 `maskString` 을 거치는데 **이 줄만 생것**이었다.
        filename: event.filename ? maskCapped(String(event.filename), MAX_FIELD_CHARS) : null,
        lineno: event.lineno ?? null,
        colno: event.colno ?? null,
        stack: event.error?.stack ? maskCapped(String(event.error.stack), MAX_FIELD_CHARS) : null,
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
        message: maskCapped(String(message ?? ""), 1000),
        stack: reason instanceof Error && reason.stack ? maskCapped(reason.stack, MAX_FIELD_CHARS) : null,
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

    // ★정식 핸들러를 **먼저** 붙인 뒤 조기 버퍼를 비운다 — 그 사이(등록~flush)에 난 오류도
    //   정식 경로로 잡히고, 버퍼를 닫는 순간 이중 전송이 끊긴다.
    for (const e of drainEarlyErrors(window as unknown as { __propaiEarly?: EarlyStore })) {
      // ★형제와 **같은 이벤트 타입**을 쓴다 — 조기 포착이라고 다른 타입으로 보내면 같은 사건이
      //   두 이름으로 쌓여 analyzer 의 군집이 갈린다(`handleWindowError`=js_error /
      //   `handleRejection`=promise_rejection · 둘 다 백엔드 화이트리스트에 있다).
      const isRejection = e.k === "rejection";
      trackEvent(isRejection ? "promise_rejection" : "js_error", {
        severity: "error",
        payload: {
          // ★절단 길이도 형제와 **같아야** 한다 — `analyzer.normalize_stack` 이 **메시지 전문**을
          //   sha1 해싱하므로, 조기/정식 경로의 자르는 길이가 다르면 같은 오류가 **다른 시그니처**로
          //   군집된다(독립 리뷰 지적). `handleRejection`=1,000자 / `handleWindowError`=`MAX_FIELD_CHARS`.
          // ★2026-08-28: `handleWindowError` 가 **무절단**이던 것을 `MAX_FIELD_CHARS` 로 막으면서
          //   **이 줄도 같이** 바꾼다. 한쪽만 고치면 바로 위 주석이 경고하는 시그니처 분열이 난다.
          message: isRejection ? maskCapped(e.m, 1000) : maskCapped(e.m, MAX_FIELD_CHARS),
          stack: e.s ? maskCapped(e.s, MAX_FIELD_CHARS) : null,
          // 위치 정보는 `error` 경로에만 있다(형제 `handleRejection` 도 안 싣는다).
          ...(isRejection ? {} : { filename: e.f ? maskCapped(String(e.f), MAX_FIELD_CHARS) : null, lineno: e.l, colno: e.c }),
          // ★진단용 — 이 오류가 **수집기 등록 전**에 났다는 사실 자체가 정보다.
          //   `tMs` 로 얼마나 앞섰는지까지 남는다(실측 기준 #418 237ms vs 등록 307ms).
          early: true,
          tMs: e.t,
        },
      });
    }
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
