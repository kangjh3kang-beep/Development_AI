// v377: ★링크 클릭 이동 불가(플랫폼 전역) 근본수정 — RSC(Next App Router 클라 네비게이션
//        데이터)를 stale-while-revalidate 로 캐시해, 옛 빌드의 RSC(죽은 청크해시 참조)를
//        Link 클릭 시 반환 → 클라 네비게이션 침묵 실패하던 근본원인. RSC 는 콘텐츠해시가
//        없어(같은 라우트 URL·빌드마다 다른 내용) 절대 캐시하면 안 되므로 network-only 분기.
//        버전 범프로 v376 캐시(오염된 stale RSC 포함) 일괄 삭제.
const CACHE_NAME = "propai-v383-market-layer";
const OFFLINE_URL = "/offline";

// ★API 캐시 정합(보안·정확성): 인증/실시간/머니패스/현장세션 응답은 절대 캐시하지 않는다.
//   네트워크 실패 시에도 옛 데이터를 '살아있는 값'처럼 돌려주면 오결제·권한혼동·옛 잔액
//   표시 등 위험이 있어, 이런 경로는 stale 캐시 폴백 없이 정직한 오프라인(503)만 반환한다.
//   (셸/정적 자산만 캐시 — API 는 기본 network-first, 민감경로는 no-store.)
const API_NO_STORE_PATTERNS = [
  /\/auth\b/,        // 로그인/토큰/세션
  /\/login\b/,
  /\/logout\b/,
  /\/token\b/,
  /\/secrets?\b/,    // 관리자 시크릿
  /\/sales(\b|-|\/)/, // 현장앱 전체(역할·세대선점·수납·수수료 등 실시간/머니패스)
                      //  ★하이픈 변형도 포함: /sales/ 뿐 아니라 /api/v1/sales-summary 같은 머니패스 롤업도 no-store.
  /\/billing\b/,     // 과금
  /\/payments?\b/,   // 수납·결제
  /\/commission\b/,  // 수수료
  /\/balance\b/,     // 잔액
  /\/me\b/,          // 내 계정/권한
];

// 요청 URL 이 민감(no-store) API 경로인지 판정.
function isNoStoreApi(pathname) {
  return API_NO_STORE_PATTERNS.some((re) => re.test(pathname));
}
const APP_SHELL_ASSETS = [
  "/",
  "/ko",
  "/en",
  "/zh-CN",
  OFFLINE_URL,
  "/manifest.webmanifest",
  "/icon.svg",
  "/icon-maskable.svg",
  "/apple-touch-icon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL_ASSETS)),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)),
      ),
    ),
  );
  self.clients.claim();
});

self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") {
    self.skipWaiting();
    return;
  }

  if (event.data?.type === "SHOW_NOTIFICATION") {
    const payload = event.data.payload ?? {};

    event.waitUntil(
      self.registration.showNotification(payload.title ?? "PropAI", {
        body: payload.body ?? "Offline workspace is ready.",
        tag: payload.tag ?? "propai-pwa-runtime",
        data: {
          url: payload.url ?? "/ko/inspection",
        },
      }),
    );
  }
});

self.addEventListener("push", (event) => {
  const payload = event.data ? event.data.json() : {};
  const title = payload.title ?? "PropAI";

  event.waitUntil(
    self.registration.showNotification(title, {
      body: payload.body ?? "New field operation update is available.",
      tag: payload.tag ?? "propai-web-push",
      data: {
        url: payload.url ?? "/ko",
      },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  event.waitUntil(clients.openWindow(event.notification.data?.url ?? "/ko"));
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  if (request.method !== "GET") {
    return;
  }

  const url = new URL(request.url);

  // http(s)만 처리 — chrome-extension://, ws:// 등은 SW 캐시 대상 아님(put 에러 방지)
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(navigationNetworkFirst(request));
    return;
  }

  // ★RSC(React Server Component) — Next.js App Router 의 클라이언트 네비게이션(Link 클릭·
  //   prefetch)이 라우트 URL 로 보내는 데이터 요청. mode 가 'navigate' 가 아니라 아래 자산
  //   catch-all(staleWhileRevalidate)로 빠져 '옛 빌드의 RSC'가 캐시에서 반환되면, 그 RSC 가
  //   참조하는 청크 해시가 새 배포로 사라져 클라 네비게이션이 침묵 실패(=링크 클릭해도 이동
  //   안 함)한다. RSC 는 콘텐츠해시가 없는 '빌드별' 페이로드이므로 절대 캐시/stale 금지 →
  //   항상 네트워크(network-only). 헤더(RSC/Next-Router-*)·?_rsc·Accept 로 판별.
  if (isRscRequest(request, url)) {
    event.respondWith(networkOnlyNoStore(request));
    return;
  }

  if (url.pathname.startsWith("/api/")) {
    // 민감 API(인증/현장/머니패스)는 캐시 금지 + stale 폴백 금지(정직한 오프라인 503).
    if (isNoStoreApi(url.pathname)) {
      event.respondWith(apiNoStore(request));
      return;
    }
    event.respondWith(apiNetworkFirst(request));
    return;
  }

  if (request.destination === "image") {
    event.respondWith(staleWhileRevalidate(request));
    return;
  }

  // JS/CSS/폰트/RSC 등 자산: stale-while-revalidate(즉시 표시 + 백그라운드 갱신).
  // ★cacheFirst(영구캐시)였던 것을 SWR로 변경 — 새 배포가 다음 로드에 자동 반영(자가치유).
  // 콘텐츠해시 청크는 캐시미스=항상 최신, 비해시 자산도 한 번 더 로드 시 갱신됨.
  event.respondWith(staleWhileRevalidate(request));
});

// 응답을 안전하게 캐시 — 클론을 즉시 떠서 본문 중복사용/스킴미지원 에러를 흡수.
function safePut(request, response) {
  try {
    if (!response || !response.ok || response.type === "opaque") return;
    const copy = response.clone();
    caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)).catch(() => {});
  } catch {
    /* clone/put 실패는 무해하게 무시 */
  }
}

// RSC 요청 판별 — Next.js App Router 는 클라 네비게이션/prefetch 시 라우트 URL 로 RSC
// 페이로드를 요청한다. 버전별로 시그니처가 조금씩 다르므로 여러 신호를 OR 로 넓게 잡는다:
//  - 헤더 RSC:1, Next-Router-Prefetch:1, Next-Router-State-Tree(존재)
//  - 쿼리 ?_rsc=...
//  - Accept 에 text/x-component
// (false-negative 는 stale 위험 잔존, false-positive 는 단지 네트워크 강제라 안전측 = 넓게)
function isRscRequest(request, url) {
  try {
    const h = request.headers;
    if (h.get("RSC") === "1") return true;
    if (h.get("Next-Router-Prefetch") === "1") return true;
    if (h.get("Next-Router-State-Tree")) return true;
    if (url.searchParams.has("_rsc")) return true;
    const accept = h.get("Accept") || "";
    if (accept.includes("text/x-component")) return true;
  } catch {
    /* 헤더 접근 실패는 무해 — 캐시 안 하는 방향이 안전 */
  }
  return false;
}

// network-only(무캐시) — RSC 등 '빌드별' 동적 페이로드용. 캐시에 넣지도, 캐시에서
// 꺼내지도 않는다. 실패 시 정직한 네트워크 오류(라우터가 하드네비 폴백/재시도).
async function networkOnlyNoStore(request) {
  try {
    return await fetch(request);
  } catch {
    return Response.error();
  }
}

async function navigationNetworkFirst(request) {
  try {
    // ★HTML 은 캐시에 저장하지 않는다 — 오프라인 폴백은 OFFLINE_URL 만 쓰므로 페이지 HTML
    //   put 은 사용처 없는 스테일 셸 축적이었다(배포 후 죽은 청크를 참조하는 구 HTML 이
    //   Cache Storage 에 남아, 향후 매칭 로직 변화 시 백지 사고의 원료가 됨). 항상 네트워크.
    return await fetch(request);
  } catch {
    return (await caches.match(OFFLINE_URL)) || Response.error();
  }
}

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) {
    return cached;
  }

  try {
    const response = await fetch(request);
    safePut(request, response);
    return response;
  } catch {
    return (await caches.match(OFFLINE_URL)) || Response.error();
  }
}

// 민감 API(인증/현장/머니패스): 항상 네트워크. 응답을 캐시하지 않고(no-store),
// 네트워크 실패 시 옛 데이터를 돌려주지 않고 정직한 오프라인(503)만 반환한다.
// → 옛 잔액/권한/세대상태를 '살아있는 값'으로 오인하게 하는 위험을 원천 차단.
async function apiNoStore(request) {
  try {
    return await fetch(request);
  } catch {
    return new Response(
      JSON.stringify({ error: "오프라인 상태입니다", offline: true, stale: false }),
      {
        status: 503,
        headers: { "Content-Type": "application/json; charset=utf-8" },
      },
    );
  }
}

async function apiNetworkFirst(request) {
  try {
    const response = await fetch(request);
    safePut(request, response);
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) {
      // 오프라인 캐시 폴백 — '옛 데이터'임을 헤더로 정직하게 표기한다(silent 위장 금지).
      // 응답 본문은 보존하되 X-PropAI-Stale 헤더로 신선도를 알린다.
      // ★향후 network-first 화면 stale 배지용 hook(현재 소비처 없음=backlog). 무해한 응답헤더라
      //   부착은 유지한다(나중에 그런 화면이 생기면 api-client 에서 이 헤더만 다시 감지하면 됨).
      const headers = new Headers(cached.headers);
      headers.set("X-PropAI-Stale", "1");
      return new Response(cached.body, {
        status: cached.status,
        statusText: cached.statusText,
        headers,
      });
    }

    return new Response(
      JSON.stringify({ error: "오프라인 상태입니다", offline: true, stale: false }),
      {
        status: 503,
        headers: { "Content-Type": "application/json; charset=utf-8" },
      },
    );
  }
}

async function staleWhileRevalidate(request) {
  const cached = await caches.match(request);

  const fetchPromise = fetch(request)
    .then((response) => {
      safePut(request, response);
      return response;
    })
    // ★버그픽스: 캐시가 없는 상태에서 네트워크까지 실패하면 이전 코드는 undefined 를
    //   반환해 respondWith(undefined) 로 요청이 '침묵사'했다(CSS/JS 로드 실패가 원인
    //   불명 백지로 위장). 캐시가 있으면 그것을, 없으면 정직한 네트워크 오류를 반환해
    //   브라우저가 실패를 정상 보고(재시도/개발자도구 관측 가능)하게 한다.
    .catch(() => cached || Response.error());

  return cached || fetchPromise;
}
