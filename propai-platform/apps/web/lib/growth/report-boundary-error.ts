/**
 * ★**오류 경계 공용 보고기** — 경계가 잡은 오류를 **실제로 서버까지** 보낸다.
 *
 * 왜 공용 함수인가(2026-08-27 실측): 경계들이 저마다 `trackEvent` 를 부르거나(2곳) 아예
 * 안 부르거나(8곳) 갈렸고, 부르는 쪽조차 **배달되지 않았다.** 한 곳을 고쳐 전역이 따라오게 한다.
 *
 * ★결함(3모집단 실측 · `__tests__/global-error-delivery.test.ts`):
 * `trackEvent` 는 링버퍼에 넣기만 하고 `ring.length >= FLUSH_THRESHOLD`(20) 일 때만 보낸다.
 * 나머지 배달 구동자(5초 타이머·`pagehide`·`visibilitychange`)는 **전부 `initEventCollector()`
 * 안에서 등록**되고, `event-collector` 모듈에는 **모듈 스코프 부작용이 0건**이다.
 * 그런데 `app/global-error.tsx` 는 `<html>` 을 직접 렌더한다 — 즉 **루트 레이아웃을 대체**하므로
 * `AppProviders → AppStateBridge → useGrowthEvents → initEventCollector` 가 마운트되지 않는다.
 *
 *   ① 초기 로드 크래시 : 프로바이더가 커밋 못 함      → 구동자 0 → 1건이 임계 20 에 영원히 미달
 *   ② 마운트 후 크래시 : 언마운트 cleanup 이 teardown  → `flush()` 로 링을 **비우고** 타이머·리스너
 *                        제거 → 그 **뒤에** 경계가 1건 push → 결정적으로 고아
 *
 * 두 경우 모두 실측 배달 **0건**이었다(양성 대조군은 통과 — 프로브는 배달을 볼 수 있다).
 *
 * ★부수 효과가 본질이다: `initEventCollector()` 는 `drainEarlyErrors()` 로 **조기 포착 버퍼**를
 * 비운다. 조기 버퍼는 *"초기 렌더 오류"* 를 위해 만들어졌는데 그 오류가 트리를 죽이면
 * 배달자가 없어 버려졌다. 경계가 뜨는 순간이 바로 그 순간이므로, 여기서 초기화하면
 * **버퍼가 자기 목적대로 도착한다.**
 */
import {
  flush,
  initEventCollector,
  trackEvent,
} from "@/lib/growth/event-collector";

/** 경계 스코프 — `payload.scope` 로 실려 라우트별 실패를 가른다. */
export type BoundaryScope = string;

export function reportBoundaryError(
  scope: BoundaryScope,
  error: (Error & { digest?: string }) | null | undefined,
): void {
  try {
    // ① 배달 구동자를 확보한다(멱등 — 이미 초기화됐으면 즉시 반환).
    //    ★조기 포착 버퍼도 여기서 비워져 정식 경로로 실린다.
    initEventCollector();

    trackEvent("js_error", {
      severity: "error",
      payload: {
        scope,
        message: error?.message ?? "",
        digest: error?.digest ?? null,
        stack: error?.stack ? error.stack.slice(0, 2000) : null,
      },
    });

    // ② 즉시 보낸다 — 경계가 떴다는 것은 화면이 깨졌다는 뜻이고, 사용자는 타이머(5초)나
    //    `pagehide` 를 기다려 주지 않는다. `flush()` 는 논블로킹이다.
    flush();
  } catch {
    /* 계측 실패가 오류 화면을 다시 깨뜨리면 안 된다 */
  }
}
