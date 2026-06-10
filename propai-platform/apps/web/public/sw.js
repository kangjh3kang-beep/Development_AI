const CACHE_NAME = "propai-v132-modal-portal-swr";
const OFFLINE_URL = "/offline";
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

  if (url.pathname.startsWith("/api/")) {
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

async function navigationNetworkFirst(request) {
  try {
    const response = await fetch(request);
    safePut(request, response);
    return response;
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

async function apiNetworkFirst(request) {
  try {
    const response = await fetch(request);
    safePut(request, response);
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) {
      return cached;
    }

    return new Response(JSON.stringify({ error: "오프라인 상태입니다" }), {
      status: 503,
      headers: { "Content-Type": "application/json; charset=utf-8" },
    });
  }
}

async function staleWhileRevalidate(request) {
  const cached = await caches.match(request);

  const fetchPromise = fetch(request)
    .then((response) => {
      safePut(request, response);
      return response;
    })
    .catch(() => cached);

  return cached || fetchPromise;
}
