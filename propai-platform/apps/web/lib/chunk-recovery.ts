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

import { reportBoundaryError } from "@/lib/growth/report-boundary-error";

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
  // ★**리로드 전에 보고한다** — 안 그러면 이 사건은 **어디에도 안 남는다**(라이브 실측 2026-08-27:
  //   네트워크 층에서 `POST /growth/events` 를 가로채 문서 리로드를 넘겨 관측 —
  //   `_cr` 리로드 25,682ms · **리로드 前 `js_error` 0건** / 리로드 後 1건).
  //   경계 10곳은 전부 `if (tryRecoverFromChunkError(error)) return;` 이 보고기 **앞**이라,
  //   자동복구가 도는 **첫 발생** — 즉 **배포 직후 열린 탭이 깨지는, 가장 정보가 많은 경우** —
  //   가 통째로 유실됐다. 두 번째부터는 복구를 포기하므로 경계가 정상 보고한다.
  //
  // ★**왜 경계 10곳의 순서를 바꾸지 않고 여기서 부르나**(적대 리뷰가 원안을 밀어냈다):
  //   ①10파일 대신 **1파일** ②불변식이 *문장 순서*가 아니라 **함수 계약**이 된다 —
  //     소스 순서 검사는 死코드·별칭 임포트에 뚫린다(이 저장소가 `#903` 에서 실증했다)
  //   ③**새 경계가 생겨도 자동으로 따라온다**(저자가 순서를 틀릴 여지가 없다)
  //   ④전용 `scope` 로 **리로드 後 이벤트와 구별**된다 — 순서만 바꾸면 두 행이 완전히 같아진다
  //     (`analyzer` 군집 키는 `normalize_stack(message, route, status)` 이고 `message` 의 hex 는
  //      정규화되며 `route`·`session_id` 는 리로드를 넘어 동일 — 실측: `analyzer.py` 에 `scope` **0건**).
  //
  // ★`sendBeacon` 이 `location.replace()` 를 넘는다는 것은 **잰 값**이다 — 서버측 그라운드 트루스로
  //   **10/10 DB 도달**(렌더러 뷰의 `ERR_ABORTED` 는 **위음성**이다: keepalive 로더는 브라우저
  //   프로세스에 있어 렌더러 해체와 무관하다. 그것만 믿었으면 이 처방을 죽였을 것이다).
  //
  // ★`reportBoundaryError` 라는 이름과 달리 **여기는 오류 경계가 아니다.** 그래도 그 함수를 쓰는
  //   이유는 그것이 *"수집기를 확보하고(멱등) 싣고 즉시 flush 한다"* 는 계약이기 때문이다 —
  //   경계 전용 로직은 들어 있지 않다. 배선 오류로 읽고 되돌리지 말 것.
  reportBoundaryError("chunk-auto-recovery", error as Error & { digest?: string });

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
