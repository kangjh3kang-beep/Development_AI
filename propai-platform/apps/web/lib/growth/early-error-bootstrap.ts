/**
 * ★**초기 렌더 오류 조기 포착** — 하이드레이션 전에 실행되어 오류를 버퍼에 담는다.
 *
 * 왜 필요한가(2026-08-27 라이브 실측): 전역 오류 수집기는 `initEventCollector()` 에서
 * `window.addEventListener("error", …)` 를 등록하는데, 그 호출이 `useGrowthEvents` 의
 * **`useEffect`** 안이라 **하이드레이션 커밋 이후**에 돈다. 같은 타임라인에서 재니
 *
 *     Minified React error #418   →  **237ms**
 *     addEventListener("error")   →  **307ms**
 *
 * **오류가 등록보다 70ms 먼저 났다.** 그래서 성장루프 analyzer 가 `js_error` 를 볼 준비를
 * 갖추고 있는데도(`WHERE event_type IN ('js_error','api_error')`) 라이브에서 #418 이 나는 동안
 * **`js_error` 는 0건**이었다(beacon 본문 가로채기로 확인 · 대조군 `api_call` 28건은 실림 —
 * `api-client` 가 `trackEvent` 를 직접 부르므로 **수집기의 일부만 살아 있었다**).
 * ★함의는 하이드레이션에 국한되지 않는다 — **초기 렌더 중 나는 모든 오류**가 같은 창에 빠진다.
 *
 * 이 스크립트는 위 `themeBootstrap` 과 **같은 자리·같은 방식**(문서 파싱 시점 인라인)이라
 * 등록 시점이 하이드레이션보다 앞선다는 것이 구조로 보장된다.
 * `initEventCollector()` 가 정식 핸들러를 붙인 뒤 이 버퍼를 비우고 **닫는다**(이중 전송 방지).
 */
export const EARLY_ERROR_CAP = 20;
/**
 * ★메시지 상한 — 건수(20)만 잠그면 **한 건이 메모리를 먹는다**(독립 리뷰 실측: 500,000자 메시지가
 *   그대로 남았다). 형제 `handleRejection` 의 1,000자보다 넉넉히 잡아 정보 손실을 줄이되
 *   상한 자체는 둔다. ★한계: 이 길이를 넘는 메시지는 조기/정식 경로에서 `normalize_stack` 의
 *   sha1 시그니처가 갈린다(analyzer 는 **메시지 전문**을 해싱한다).
 */
export const EARLY_MESSAGE_CAP = 8000;
export const EARLY_STACK_CAP = 2000;

export const earlyErrorBootstrap =
  // ★멱등 — 두 번 실행되면 store 가 갈려 첫 store 의 리스너가 담은 것을 drain 이 **못 본다**
  //   (이중 전송이 아니라 **조용한 손실**이다 — 독립 리뷰 실측).
  `(function(){try{if(window.__propaiEarly)return;var B=[];var S={buf:B,closed:false};window.__propaiEarly=S;` +
  `function P(o){if(S.closed)return;if(B.length<${EARLY_ERROR_CAP})B.push(o);}` +
  // ★사유→메시지 정규화는 형제 `handleRejection` 과 **같은 규칙**이어야 한다.
  //   달라지면 같은 사건이 다른 시그니처로 군집돼 `error_cluster` 가 갈린다.
  `function M(r){try{if(r instanceof Error)return String(r.message);if(typeof r==="string")return r;` +
  `try{return JSON.stringify(r);}catch(e){return String(r);}}catch(e){return "";}}` +
  `function C(x,n){return (x==null)?null:String(x).slice(0,n);}` +
  // ★리스너 **본문**도 try/catch 로 감싼다 — 바깥 try 는 등록만 감싼다(수집기 헤더가 선언한
  //   "모든 경로 격리"를 신규 코드가 어기고 있었다 · 독립 리뷰 지적).
  `window.addEventListener("error",function(e){try{P({k:"error",m:C(e.message,${EARLY_MESSAGE_CAP})||"",` +
  `f:e.filename||null,l:e.lineno||null,c:e.colno||null,` +
  `s:(e.error&&e.error.stack)?C(e.error.stack,${EARLY_STACK_CAP}):null,` +
  `t:Math.round(performance.now())});}catch(x){}});` +
  `window.addEventListener("unhandledrejection",function(e){try{var r=e.reason;` +
  `P({k:"rejection",m:C(M(r),${EARLY_MESSAGE_CAP})||"",f:null,l:null,c:null,` +
  `s:(r&&r.stack)?C(r.stack,${EARLY_STACK_CAP}):null,` +
  `t:Math.round(performance.now())});}catch(x){}});` +
  `}catch(e){}})();`;
