/**
 * 배포 직후 **열려 있던 탭**이 맞는 청크 로드 실패를 한 번만 자동 복구한다.
 *
 * 【실증 2026-08-18 · 사용자 스크린샷】
 *   화면: "페이지 오류 — Failed to load chunk /_next/static/chunks/3b1cf6ac98c74f4b.js"
 *   실측: 그 청크 **404**(사라짐) · 현재 배포본이 참조하는 청크 **200** · 라이브 캐시명이 갱신됨
 *   → 브라우저가 **이전 빌드의 문서**를 들고 있는데 서버의 청크는 교체됐다.
 *     Next 의 코드분할은 라우팅·상호작용 시점에 청크를 받아오므로, 배포가 끼면 그 순간 깨진다.
 *
 * 【왜 자동 복구가 맞나】이 실패는 **사용자가 고칠 것이 없다** — 새로고침하면 끝난다.
 * 그런데 화면은 "다시 시도"를 주고, 그 버튼(`reset()`)은 **같은 깨진 문서 안에서 다시 렌더**하므로
 * 청크는 여전히 404 다. 즉 사용자가 눌러도 낫지 않는 버튼을 누르게 된다.
 *
 * 【무한루프를 막는 것이 이 파일의 핵심】
 * 새로고침해도 안 낫는 경우(예: 그 청크가 CDN 에서 영구 소실)에 무한 새로고침이 되면
 * **사용자가 페이지를 아예 못 벗어난다** — 원래 결함보다 나쁘다.
 * 그래서 `sessionStorage` 에 **한 번 표시**를 남기고, 두 번째부터는 복구를 포기하고
 * 오류 화면을 그대로 보여준다. 탭을 닫으면 표시도 사라진다(다음 배포 때 다시 1회 기회).
 */

/** 세션당 1회만 자동 새로고침한다는 표시. 탭 생명주기와 함께 사라진다. */
const RELOAD_FLAG = "propai:chunk-reload-attempted";

/**
 * 청크 로드 실패인가.
 *
 * ★메시지 문자열로 판정한다 — 브라우저·번들러마다 오류 타입이 달라 `instanceof` 로는 못 가른다.
 *   Next/webpack 은 `ChunkLoadError` 이름 또는 "Loading chunk … failed" / "Failed to load chunk"
 *   형태를 낸다(사용자 실측 문구는 후자다). 동적 import 실패의 표현도 함께 본다.
 * ★넓게 잡지 않는다 — 아무 오류나 새로고침하면 진짜 버그가 **무한 새로고침으로 은폐**된다.
 */
export function isChunkLoadError(error: unknown): boolean {
  const e = error as { name?: unknown; message?: unknown } | null | undefined;
  const name = typeof e?.name === "string" ? e.name : "";
  const msg = typeof e?.message === "string" ? e.message : "";
  if (name === "ChunkLoadError") return true;
  return (
    /Loading chunk\s+\S+\s+failed/i.test(msg) ||
    /Failed to load chunk/i.test(msg) ||
    /Loading CSS chunk/i.test(msg) ||
    /error loading dynamically imported module/i.test(msg)
  );
}

/**
 * 청크 오류면 **세션당 한 번** 하드 리로드한다.
 * @returns 복구를 시도했으면 true(호출부는 그대로 두면 곧 페이지가 갈린다).
 *          false 면 복구하지 않았다는 뜻이므로 **오류 화면을 정직하게 보여야 한다**.
 */
export function tryRecoverFromChunkError(error: unknown): boolean {
  if (typeof window === "undefined") return false;
  if (!isChunkLoadError(error)) return false;
  try {
    if (window.sessionStorage.getItem(RELOAD_FLAG)) return false; // 이미 한 번 시도했다 — 포기한다
    window.sessionStorage.setItem(RELOAD_FLAG, "1");
  } catch {
    // sessionStorage 가 막힌 환경(프라이빗 모드 등)에서는 **복구를 포기한다**.
    // 표시를 남길 수 없으면 루프를 막을 방법이 없으므로, 자동 새로고침을 하지 않는 쪽이 안전하다.
    return false;
  }
  // `location.reload()` 는 캐시된 문서를 다시 쓸 수 있어 같은 청크를 또 참조할 수 있다.
  // 쿼리에 표식을 붙여 **문서 자체를 새로 받게** 한다(SW 캐시 키도 미스시킨다).
  const url = new URL(window.location.href);
  url.searchParams.set("_cr", String(Date.now()));
  window.location.replace(url.toString());
  return true;
}

/** 테스트 전용 — 세션 표시 초기화. */
export function __resetChunkRecoveryForTest(): void {
  try {
    window.sessionStorage.removeItem(RELOAD_FLAG);
  } catch {
    /* noop */
  }
}
