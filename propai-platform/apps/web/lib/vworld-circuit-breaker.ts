/**
 * VWorld 타일 상류 회로차단기 — 실패 요청 폭주 차단.
 *
 * ★왜 필요한가(실장애):
 *   웹서버의 VWorld 인증키가 무효인 상태로 방치되자, 지도를 팬/줌할 때마다 타일 수십 개가
 *   전부 실패했다. 그런데 오류 응답은 `Cache-Control: no-store`라 브라우저·CDN 어디에도
 *   캐시되지 않고, 서버에도 억제 장치가 없어 **실패 요청이 무한 반복**됐다.
 *   그 결과 VWorld가 우리 서버 IP를 차단해(도메인 전체 502/000) 키를 고쳐도 지도가
 *   복구되지 않는 상태가 됐다. 즉 "상류가 죽었을 때 더 세게 두드리는" 구조가 자해였다.
 *
 * 설계:
 *   · 연속 실패가 임계치를 넘으면 쿨다운 동안 **상류를 아예 호출하지 않는다**(open).
 *   · 쿨다운이 끝나면 1건만 흘려보내 회복을 탐색한다(half-open).
 *   · 성공하면 즉시 닫는다(closed).
 *   · 프로세스 로컬 인메모리 — 인스턴스가 여러 개여도 각자 자기 몫의 폭주를 줄인다.
 *     (분산 상태 저장소는 이 결함을 막는 데 불필요하다.)
 */

export type BreakerState = "closed" | "open" | "half-open";

type Entry = {
  failures: number;
  openedAt: number | null;
  probing: boolean;
};

// 연속 실패 임계치 — 일시적 단발 실패로 차단하지 않되, 폭주는 빠르게 끊는다.
const FAILURE_THRESHOLD = 5;
// 차단 유지 시간. 이 동안 상류 호출 0회.
const COOLDOWN_MS = 60_000;

const registry = new Map<string, Entry>();

function entryOf(key: string): Entry {
  let e = registry.get(key);
  if (!e) {
    e = { failures: 0, openedAt: null, probing: false };
    registry.set(key, e);
  }
  return e;
}

/** 지금 상류를 호출해도 되는가. false면 호출하지 말고 즉시 폴백을 반환한다. */
export function shouldAttempt(key: string, now: number = Date.now()): boolean {
  const e = entryOf(key);
  if (e.openedAt === null) return true;
  if (now - e.openedAt < COOLDOWN_MS) return false;
  // 쿨다운 종료 — 딱 1건만 탐색으로 흘린다(회복 확인). 나머지는 계속 막는다.
  if (e.probing) return false;
  e.probing = true;
  return true;
}

export function recordSuccess(key: string): void {
  const e = entryOf(key);
  e.failures = 0;
  e.openedAt = null;
  e.probing = false;
}

export function recordFailure(key: string, now: number = Date.now()): void {
  const e = entryOf(key);
  if (e.probing) {
    // 탐색 실패 — 쿨다운을 다시 시작한다(회복 안 됨).
    e.openedAt = now;
    e.probing = false;
    return;
  }
  e.failures += 1;
  if (e.failures >= FAILURE_THRESHOLD && e.openedAt === null) {
    e.openedAt = now;
  }
}

export function breakerState(key: string, now: number = Date.now()): BreakerState {
  const e = entryOf(key);
  if (e.openedAt === null) return "closed";
  return now - e.openedAt < COOLDOWN_MS ? "open" : "half-open";
}

/** 차단 중 남은 시간(초) — 사용자 안내·Retry-After 헤더용. */
export function cooldownRemainingSec(key: string, now: number = Date.now()): number {
  const e = entryOf(key);
  if (e.openedAt === null) return 0;
  return Math.max(0, Math.ceil((COOLDOWN_MS - (now - e.openedAt)) / 1000));
}

/** 테스트 전용 — 프로세스 로컬 상태 초기화. */
export function resetBreakers(): void {
  registry.clear();
}

export const BREAKER_TUNING = { FAILURE_THRESHOLD, COOLDOWN_MS } as const;
