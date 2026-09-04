/**
 * Leaflet 로더 — **번들에서** 불러온다(종전: unpkg.com CDN 런타임 로드).
 *
 * ## 왜 바꿨나
 *
 * 종전에는 세 파일이 `document.createElement("script")` 로 `unpkg.com` 에서 Leaflet 을
 * 받아왔다. 같은 함수가 **3벌 복붙**돼 있었고(SatongMultiMap · AuctionItemsMap ·
 * AuctionMonitorPanel), 셋 다 `integrity`(SRI) 도 `crossorigin` 도 없었다.
 * 프론트엔드에 CSP 도 없다(`next.config.mjs` 는 XFO·nosniff·Referrer-Policy·HSTS 만 설정).
 *
 * 그래서 **unpkg 에서 도착한 바이트가 그대로 실행**됐다. 그게 왜 큰가 하면 —
 * 이 플랫폼은 로그인 토큰을 `localStorage`(`propai_access_token`/`propai_refresh_token`)에
 * 두고, Leaflet 을 쓰는 지도는 **대부분의 로그인 분석 화면**에서 돈다. 구석 기능이 아니다.
 *
 * ★공정하게 적자면 `leaflet@1.9.4` 는 **버전이 고정**돼 있었으므로,
 *   *"공격자가 새 버전을 악성으로 올린다"* 는 시나리오는 **성립하지 않았다.**
 *   성립하는 것은 CDN·네트워크 경로가 침해되는 경우다.
 *
 * ## 그리고 더 흔한 위험 — 가용성
 *
 * `leaflet` 은 `package.json` 에도 `pnpm-lock.yaml` 에도 **없었다**(실측 각 0건).
 * 즉 **사본이 어디에도 없어서**, unpkg 가 죽으면 플랫폼 전역의 지도가 함께 죽는다.
 * 침해보다 이쪽이 훨씬 자주 일어난다.
 *
 * ## 계약 — 소비처는 하나도 안 바뀐다
 *
 * `window.L` 을 읽는 곳이 **36곳(9파일)** 이라, 이 로더는 종전과 똑같이
 * **`window.L` 을 채워 준다.** 호출부 시그니처도 `loadLeaflet(): Promise<void>` 그대로다.
 * 그래서 이 변경의 diff 는 로더 3벌을 지우고 import 한 줄로 바꾸는 것뿐이다.
 *
 * ★실패 처리는 저장소 안의 정답 기준선인 `lib/kakao-map.ts` 를 따른다 —
 *   실패하면 **캐시를 비워 다시 시도할 수 있게** 한다(한 번 실패했다고 영구히 막지 않는다).
 */

// ★CSS 는 정적 import 여야 한다(번들러가 스타일시트를 뽑아낸다). JS 본체만 동적으로
//   불러 초기 청크를 키우지 않는다 — 종전 CDN 방식도 지도를 열 때 받아왔다.
import "leaflet/dist/leaflet.css";

/** 진행 중인 로드 1건을 공유한다(동시에 여러 지도가 떠도 한 번만 받는다). */
let loading: Promise<void> | null = null;

/**
 * Leaflet 을 불러와 `window.L` 에 붙인다.
 *
 * · 이미 붙어 있으면 즉시 끝난다.
 * · 여러 번 불러도 실제 로드는 1회다.
 * · 실패하면 캐시를 비워 **다음 호출이 다시 시도**할 수 있게 한다.
 */
export function loadLeaflet(): Promise<void> {
  // ★SSR 방어 — 변이 검증에서 이 줄이 **생존**한다. 잠금이 없어서가 아니라,
   //   테스트(jsdom)와 실제 사용처(클라이언트 컴포넌트) **둘 다 window 가 있어** 도달하지
   //   않기 때문이다. 이중 가드로 남긴다(호출부가 서버에서 부르는 실수를 즉시 드러낸다).
  if (typeof window === "undefined") return Promise.reject(new Error("no window"));
  if (window.L) return Promise.resolve();
  if (loading) return loading;

  loading = import("leaflet")
    .then((mod) => {
      // UMD/ESM 양쪽 모양을 모두 받는다.
      window.L = (mod as unknown as { default?: unknown }).default ?? mod;
    })
    .catch((err) => {
      loading = null; // ★재시도 허용(lib/kakao-map.ts 와 같은 규약).
      throw err instanceof Error ? err : new Error("Leaflet 로드 실패");
    });

  return loading;
}

/** 테스트 전용 — 모듈 캐시를 비운다(로더가 1회성이라 케이스 간 격리가 필요하다). */
export function __resetLeafletLoaderForTest(): void {
  loading = null;
}
