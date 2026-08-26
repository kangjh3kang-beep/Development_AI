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
const HYDRATION_RE = /Hydration failed|error #418|errors\/418|Text content/;
const NOISE_RE = /PROBE_ALIVE|Failed to load resource|net::|CORS/;
export function countHydration(lines) {
  return lines.filter((e) => !NOISE_RE.test(e)).filter((e) => HYDRATION_RE.test(e)).length;
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
