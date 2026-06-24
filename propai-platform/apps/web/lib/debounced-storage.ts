/**
 * 디바운스 persist 저장소 — zustand persist 공용 storage(표준 계약).
 *
 * ★문제(전역): zustand persist의 기본 storage는 모든 상태변경(set)마다 스토어 '전체'를
 * 메인스레드에서 동기 JSON 직렬화→localStorage 기록한다. 누적 데이터(분석 스냅샷·캐시·
 * 오케스트레이션 결과·토지조서 등)가 큰 스토어는 set 1회가 큰 동기 직렬화를 유발해 화면
 * 전환·입력이 멈칫한다(예: 새 프로젝트 진입의 clearProject).
 *
 * ★해결(공용): 직렬화+쓰기를 트레일링 디바운스(기본 500ms)로 비동기화해 동기 메인스레드
 * 점유를 제거한다. 한 곳(이 헬퍼)을 고치면 이를 쓰는 전 스토어가 따라온다.
 *
 * 유실 방지: pagehide·탭 숨김 직전 즉시 flush(하드 내비게이션·세션만료 리다이렉트 포함).
 * createJSONStorage를 쓰지 않는 이유: 그쪽은 stringify를 동기로 수행해 '쓰기'만 미뤄도
 * 직렬화 비용이 남는다. 여기선 직렬화 자체를 flush 시점으로 미룬다.
 */
import type { PersistStorage, StorageValue } from "zustand/middleware";

export function createDebouncedStorage<S>(delay = 500): PersistStorage<S> {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let pending: { name: string; value: StorageValue<S> } | null = null;

  const flush = (): void => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    if (!pending || typeof window === "undefined") return;
    try {
      window.localStorage.setItem(pending.name, JSON.stringify(pending.value));
    } catch {
      /* quota 초과·직렬화 실패는 무시(다음 변경에서 재기록) */
    }
    pending = null;
  };

  if (typeof window !== "undefined") {
    // 페이지 이탈·탭 숨김 직전에 대기분을 반드시 기록(유실 0).
    window.addEventListener("pagehide", flush);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") flush();
    });
  }

  return {
    getItem: (name) => {
      if (typeof window === "undefined") return null;
      try {
        const raw = window.localStorage.getItem(name);
        return raw ? (JSON.parse(raw) as StorageValue<S>) : null;
      } catch {
        return null;
      }
    },
    setItem: (name, value) => {
      // 동기 직렬화 금지 — 최신 상태 참조만 잡아두고 트레일링 디바운스로 비동기 기록.
      pending = { name, value };
      if (timer) clearTimeout(timer);
      timer = setTimeout(flush, delay);
    },
    removeItem: (name) => {
      if (pending && pending.name === name) pending = null;
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
      if (typeof window === "undefined") return;
      try {
        window.localStorage.removeItem(name);
      } catch {
        /* noop */
      }
    },
  };
}
