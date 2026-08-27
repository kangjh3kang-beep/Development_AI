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
export const earlyErrorBootstrap = `(function(){try{var B=[];var S={buf:B,closed:false};window.__propaiEarly=S;` +
  `function P(o){if(S.closed)return;if(B.length<${EARLY_ERROR_CAP})B.push(o);}` +
  `window.addEventListener("error",function(e){P({k:"error",m:String(e.message||""),f:e.filename||null,` +
  `l:e.lineno||null,c:e.colno||null,s:(e.error&&e.error.stack)?String(e.error.stack).slice(0,2000):null,` +
  `t:Math.round(performance.now())});});` +
  `window.addEventListener("unhandledrejection",function(e){var r=e.reason;` +
  `P({k:"rejection",m:(r&&r.message)?String(r.message):String(r),f:null,l:null,c:null,` +
  `s:(r&&r.stack)?String(r.stack).slice(0,2000):null,t:Math.round(performance.now())});});` +
  `}catch(e){}})();`;

