/**
 * `e2e/support/hydration-probe.mjs` 의 **순수부** — 브라우저 없이 테스트할 수 있게 분리했다.
 *
 * ★왜 분리했나(2026-08-27 · 독립 리뷰 F7): 프로브가 커밋 본문에 종료코드 계약(0/1/2)을 표로
 *   선언했는데 **그것을 지키는 검사가 0건**이었다 — `vitest.config.ts` 가 `e2e/**` 를 수집에서
 *   제외하므로 어떤 러너도 그 파일을 태우지 않는다. 계약을 선언만 하고 잠그지 않으면
 *   그 표는 산문이다(§30: 동작 주장은 그 자체가 검증 대상).
 *   → 판정에 쓰이는 세 함수를 여기로 옮기고 `__tests__/probe-text.test.ts` 가 잠근다.
 */
/** 하이드레이션 불일치로 셀 오류 — **두 모드가 같은 계수 경로를 쓴다**(대조군의 존재 이유). */
export const HYDRATION_RE = /Hydration failed|error #418|errors\/418|Text content/;
const NOISE_RE = /PROBE_ALIVE|Failed to load resource|net::|CORS/;
/**
 * 노이즈를 걷어낸 줄 — **계수와 진단 표시가 같은 필터를 쓰게** 하는 단일 통로.
 * ★이것이 없어서 `run` 모드가 `NOISE_RE`(이 모듈의 **지역 상수**)를 참조한 채 남았고,
 *   그 한 줄 때문에 측정 모드가 `ReferenceError` 로 **즉시 죽었다**(2026-08-27 실측).
 *   `control` 모드는 이 줄을 지나지 않아 **통과했고**, 그래서 프로브가 살아 있는 것처럼 보였다.
 */
export function relevantErrors(lines) {
  return lines.filter((e) => !NOISE_RE.test(e));
}
export function countHydration(lines) {
  return relevantErrors(lines).filter((e) => HYDRATION_RE.test(e)).length;
}

/**
 * `run` 회차의 **진단 표본** — 잡음을 걷은 뒤 앞 3건을 400자로 자른다.
 * ★프로브 본문에 판정이 남으면 그 줄은 **무잠금**이다(브라우저 없이는 태울 수 없다).
 *   그래서 판정을 여기로 옮기고 프로브에는 **호출 한 줄**만 남긴다 — 표면을 줄이는 것이
 *   현실적 처방이다(독립 리뷰 MAJOR-2 지적).
 */
export function buildRunSample(lines, max = 3, width = 400) {
  return relevantErrors(lines).slice(0, max).map((x) => x.slice(0, width));
}

/**
 * 수집기 생존 — 일부러 던진 `PROBE_ALIVE` 가 잡혔는가.
 * ★이 판정이 거짓이면 그 회차의 "0건"은 근거가 아니다. 그래서 **판정 자체를 잠근다.**
 */
/**
 * **조기 포착 프로브의 판정** — `e2e/support/early-capture-probe.mjs` 가 이 함수를 쓴다.
 *
 * ★순수 함수로 꺼낸 이유: 초판은 판정이 스크립트 본문에 있어 **양성 방향을 태울 수 없었다**
 *   (고친 빌드가 배포되기 전에는 `verdict:true` 를 만들 수 없다). 독립 리뷰가 그 사이
 *   **신호 반전**을 실증했다 — `drainEarlyErrors()` 가 `closed=true` 로 닫으므로 카나리는 절대
 *   담기지 않고, 그래서 **고쳐진 배포본에서도 `exit 1`("죽음")** 이 나왔다.
 *   `verdict:true` 가 나오는 유일한 조건이 *"수집기가 안 돈 페이지"* 였다.
 *
 * ★`closed === true` 가 **가장 강한 증거**다: 그 플래그를 세우는 주체는 `drainEarlyErrors()` 뿐이고
 *   그것은 `initEventCollector()` 안에서만 불린다 → 부트스트랩이 실행됐고 수집기가 인계했다.
 */
export function decideEarlyCaptureVerdict({ runtime, caught }) {
  if (!runtime?.exists || !runtime?.hasBuf) return false;
  return runtime.closed === true || caught?.grew === true;
}

export function isCollectorAlive(lines) {
  return lines.some((e) => e.includes("PROBE_ALIVE"));
}

/**
 * 최종 URL 이 목표와 같은가 — **양쪽을 같은 정규화기로** 통과시킨다.
 * ★초판은 `new URL(finalUrl).pathname === path` 였는데, 한글 경로는 퍼센트 인코딩되고
 *   쿼리가 붙은 `path` 는 절대 안 맞아 **멀쩡한 측정을 무효로 버렸다**(가드의 위양성도 결함이다).
 */
export function samePath(finalUrl, path, base) {
  try {
    return new URL(finalUrl).pathname === new URL(path, base).pathname;
  } catch { return false; }
}

/**
 * 개변할 텍스트를 **HTML 에서 파생**한다(손으로 나열하지 않는다 — 목록은 곧 상한이 된다).
 * `<script>`·`<style>` 을 걷어낸 뒤 4~40자 텍스트 노드를 모아 **문서에서 유일한 것**만 고른다
 * (여러 번 나오면 `replace` 가 어디를 바꿨는지 알 수 없다).
 * ★어느 자리를 집었는지 **오프셋과 앞뒤 문맥**을 함께 돌려준다 — `picked` 문자열만으로는
 *   그것이 공용 셸의 스킵링크인지 그 라우트의 서브트리인지 구별되지 않는다(리뷰 지적).
 */
export function pickMutableText(html) {
  // ★`<body>` 안만 본다 — `<head>` 의 `<title>`·메타는 React 가 하이드레이트하는 자리가 아니라
  //   개변해도 불일치가 나지 않는다(실측 2026-08-27: `<title>` 을 골라 exit 1 로 "프로브 사망" 오판).
  const bodyAt = html.indexOf("<body");
  if (bodyAt < 0) return null;
  const body = html.slice(bodyAt)
    .replace(/<script\b[\s\S]*?<\/script>/g, "")
    .replace(/<style\b[\s\S]*?<\/style>/g, "");
  const seen = new Map();
  for (const m of body.matchAll(/>([^<>]{4,40})</g)) {
    const t = m[1];
    if (!/[가-힣A-Za-z]/.test(t)) continue;
    if (/^\s|\s$/.test(t)) continue;
    seen.set(t, (seen.get(t) ?? 0) + 1);
  }
  // ★문서에서 **유일한** 것만(여러 번 나오면 `replace` 가 어디를 바꿨는지 알 수 없다).
  //   그리고 **뒤쪽**을 먼저 고른다 — 앞쪽은 공용 셸(스킵링크·네비)이라 라우트별 증명이 못 된다.
  const uniq = [...seen].filter(([, n]) => n === 1).map(([t]) => t);
  for (const t of uniq.reverse()) {
    const tag = ">" + t + "<";
    const at = html.indexOf(tag, bodyAt);
    if (at < 0) continue;
    return { text: t, at, context: html.slice(Math.max(0, at - 60), at + tag.length + 60) };
  }
  return null;
}

/**
 * **종료코드 판정** — 프로브가 커밋 본문에 표로 선언한 계약을 **여기 하나로** 모은다.
 *
 * ★왜 꺼냈나(2026-08-27 · 동료 세션 지적): 순수부(문자열·계수)만 잠그면
 *   **그것을 부르는 판정 층이 빈다.** 계약표가 산문으로 남는다.
 *   브라우저 I/O 는 여전히 무잠금이지만, **무엇을 보고 어떤 코드를 내는가**는 여기서 잠긴다.
 *
 * @returns {{code: 0|1|2, kind: string, message: string|null}}
 */
export function decideControlVerdict({ handlerRan, urlOk, picked, hydration, noMutate }) {
  // 무효(2)가 먼저다 — 무효를 음성으로 읽는 것이 이 프로브가 막으려는 첫 번째 오류다.
  if (!handlerRan) return { code: 2, kind: "invalid-handler", message: "★라우트 핸들러가 발화하지 않았다 — 이 회차는 **무효**다" };
  if (!urlOk) return { code: 2, kind: "invalid-url", message: "★목표와 다른 페이지를 쟀다 — **무효**" };
  if (!picked) return { code: 2, kind: "invalid-nopick", message: "★서버 HTML 에서 개변할 유일 텍스트를 못 찾았다 — **무효**" };
  if (noMutate) {
    return hydration > 0
      ? { code: 1, kind: "false-positive", message: "★개변하지 않았는데 #418 이 났다 — **가로채기 자체가 원인**이다. 양성 대조군이 위양성이다" }
      : { code: 0, kind: "negative-ok", message: "음성 대조군 통과 — 가로채기만으로는 #418 이 나지 않는다(양성의 원인은 개변이다)" };
  }
  return hydration >= 1
    ? { code: 0, kind: "positive-ok", message: "양성 대조군 통과 — 이 프로브는 프로덕션 번들에서 #418 을 잡는다" }
    : { code: 1, kind: "probe-dead", message: "★대조군이 #418 을 못 만들었다 — **프로브가 죽었다.** 이 프로브로 잰 '0건'은 근거가 아니다" };
}

/** `run` 모드 판정 — 무효(2)가 발견(1)보다 **먼저**다("0건"이라 말하지 못하게). */
export function decideRunVerdict({ invalid, found }) {
  if (invalid) return { code: 2, kind: "invalid", message: null };
  if (found > 0) return { code: 1, kind: "found", message: null };
  return { code: 0, kind: "clean", message: null };
}
