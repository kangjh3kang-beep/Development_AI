/**
 * 계정별 zustand persist 저장소 + **유료 산출물 귀속 마이그레이션**.
 *
 * ## 두 가지를 한다
 *
 * ① `createAccountScopedStorage` — 읽기/쓰기 **시점에** `__<uid>` 를 붙이는 storage 어댑터.
 *    (zustand `persist` 의 `name` 은 모듈 로드 시점에 고정되므로 어댑터에서 붙여야 한다.)
 * ② `decideMigration` — 레거시 **공유키**에 쌓여 있던 항목 중 **이 계정 것만** 고르는 판단.
 *
 * ## ★귀속이 어려운 부분이다 — 키가 아니라
 *
 * 레거시 공유키의 항목은 **여러 계정이 같은 브라우저에서 만든 것이 섞여 있다.** 누구 것인지
 * 말해 주는 필드가 없다. 그런데 두 스토어 모두 `byProject: Record<projectId, T[]>` 이고
 * 프로젝트는 **테넌트 스코프**다 → *"그 사용자가 볼 수 있는 프로젝트 id 에 속한 항목만"* 이
 * 안전한 규칙이다.
 *
 * ★★**이 규칙이 주는 경계는 「계정」이 아니라 「테넌트」다 — 정직하게 적는다.**
 *   `apps/api/routers/projects.py:175-178` 의 목록 필터는 `tenant_id` **하나뿐**이고
 *   사용자 소유자 필드가 **아예 없다**(실측 2026-08-26 · 대조군 조회 0건).
 *   따라서 **같은 테넌트의 다른 사용자**는 `visibleProjectIds` 가 동일해 서로의 레거시
 *   저장분을 승계할 수 있다. 좁히려면 서버에 없는 필드가 필요하다.
 *   · **저장 키 격리**(`<base>__<uid>`)는 **사용자 단위**로 실제 작동한다 — 이건 그대로다.
 *   · **레거시 승계의 귀속**만 테넌트 단위다.
 *   프로젝트가 원래 테넌트 공유물이므로 이 경계가 **부당하다고 단정하지 않는다.** 다만
 *   *"계정 격리"* 라고만 말하면 **선언한 커버리지와 실제 커버리지가 갈린다** — 이 파일이
 *   막으려는 바로 그 형태다. 그래서 여기 적고, 락의 미트리아지 래칫에도 올린다.
 *
 * ## 안전장치 셋 — **틀려도 돈이 사라지지 않게**
 *
 * 1. **레거시 키를 지우지도 옮기지도 않는다.** 읽기만 한다. 잘못 귀속해도 원본이 남아 있어
 *    다음에 그 계정이 로그인하면 그때 가져간다. (그래서 레거시 키는 와이프 대상이 아니다.)
 * 2. **`_default` 버킷은 귀속 불가**다(프로젝트 없이 만든 렌더). **추측하지 않는다.**
 * 3. **목록이 비었거나 절단(`truncated`)이면 미룬다.** 불완전한 목록으로 귀속하면 **본인
 *    산출물이 안 보인다** — 오래된 프로젝트의 유료 렌더가 전부 남의 것으로 판정된다.
 *    ★`#822`(`fetchAllProjects` 페이지 순회)가 절단을 고쳤기 때문에 이 규칙이 비로소 성립한다.
 *
 * ★판단을 **순수 함수로 꺼낸** 이유: 배선 안에 두면 "현재 위반 0건"인 락이 무엇을 넣어도
 *   초록인 **공허한 참**이 된다. 합성 입력으로 직접 태울 수 있어야 갈린다.
 */
import type { PersistStorage, StorageValue } from "zustand/middleware";

import { accountScopedKey, currentUserId } from "@/lib/account-scope";
import { createDebouncedStorage } from "@/lib/debounced-storage";

/** 프로젝트가 없는 항목이 담기는 버킷 이름(두 스토어 공통 `KEY()` 규약). */
export const UNATTRIBUTED_BUCKET = "_default";

/**
 * 계정별 스코프를 씌운 persist 저장소.
 *
 * ★**교차계정 쓰기 차단**: 하이드레이션한 계정과 쓰기 시점의 계정이 다르면 **쓰지 않는다.**
 *   계정 전환은 페이지 새로고침 없이도 일어나는데(SPA), 그때 메모리에는 아직 **이전 계정의
 *   상태**가 남아 있다. 그대로 쓰면 A 의 유료 산출물이 **B 의 키에 복사**된다 — 이 함수가
 *   막으려는 바로 그 누출을 내가 만드는 셈이다. 재하이드레이션이 상태를 갈아 끼울 때까지
 *   조용히 건너뛴다(원본은 각자의 키에 그대로 있으므로 잃는 것이 없다).
 */
/**
 * ★쓰기 정지 창 — **리셋이 저장분을 지우지 못하게** 한다.
 *
 * 【무엇이 있었나 (2026-08-26 · `#839` 가 만든 CRITICAL 회귀 · 적대 리뷰가 실행 재현으로 적발)】
 * 계정 전환·로그아웃에서 메모리를 비우려고 `setState({byProject:{}})` 를 불렀는데,
 * persist 가 그 `setState` 에 쓰기를 붙여 **빈 값이 계정 키에 예약**됐다. 뒤이어 부른
 * `rehydrate()` 가 그것을 덮어 줄 거라고 적어 두었는데 **그 주장이 거짓이었다**:
 * `zustand/middleware.js` 의 `hydrate()` 는 `set(stateFromStorage, true)` 뒤
 * **`if (migrated) return setItem()`** — 즉 **버전 마이그레이션 때만** 쓴다.
 * 게다가 세 로그아웃 경로가 전부 `clearOnLogout()` 을 **토큰 제거보다 먼저** 부르므로
 * `currentUserId()` 가 아직 이전 계정이라 교차계정 가드도 통과했고, 하드 내비게이션의
 * `pagehide` 가 디바운스를 **즉시 flush** 했다.
 * → **첫 로그아웃에 유료 산출물이 영구 소실**된다(렌더 3,000원/건 · 등기 1,200원/필지).
 *
 * ★그래서 리셋은 **쓰기가 붙지 않는 창 안에서** 한다. zustand 내부 동작에 기대지 않는다 —
 *   `hydrate` 가 언제 쓰는지는 **라이브러리 구현 세부**이고, 그것에 돈을 걸었다가 틀렸다.
 */
let _writesSuspended = false;

/** `fn` 이 도는 동안 이 모듈의 모든 계정 스코프 쓰기를 **버린다**(동기 함수만 받는다). */
export function withWritesSuspended(fn: () => void): void {
  _writesSuspended = true;
  try {
    fn();
  } finally {
    _writesSuspended = false;
  }
}

/** 테스트·진단용 — 지금 쓰기가 정지 중인가. */
export function isWritesSuspended(): boolean {
  return _writesSuspended;
}

export function createAccountScopedStorage<S>(delay?: number): PersistStorage<S> {
  const inner = createDebouncedStorage<S>(delay);
  /** 마지막으로 읽거나 쓴 계정. null 이면 아직 한 번도 접촉하지 않은 것. */
  let scopeUid: string | null = null;

  return {
    getItem: (name) => {
      const uid = currentUserId();
      scopeUid = uid;
      return inner.getItem(accountScopedKey(name, uid));
    },
    setItem: (name, value) => {
      // ★리셋 창 — 메모리를 비우는 동안의 쓰기는 **저장분을 지운다.** 버린다.
      if (_writesSuspended) return;
      const uid = currentUserId();
      if (scopeUid !== null && scopeUid !== uid) return; // ★교차계정 쓰기 차단
      scopeUid = uid;
      inner.setItem(accountScopedKey(name, uid), value);
    },
    removeItem: (name) => {
      if (_writesSuspended) return;
      const uid = currentUserId();
      if (scopeUid !== null && scopeUid !== uid) return;
      inner.removeItem(accountScopedKey(name, uid));
    },
  };
}

/** 마이그레이션 판단 결과 — **왜 안 했는지**까지 값으로 말한다(부재의 사유를 코드로). */
export type MigrationDecision<T> =
  | { action: "defer"; reason: "no-projects" | "truncated"; }
  | { action: "noop"; reason: "no-legacy" | "nothing-owned"; }
  | {
      action: "migrate";
      /** 현재 계정 키에 기록할 병합 결과. */
      merged: Record<string, T[]>;
      /** 이번에 가져온 프로젝트 id. */
      adopted: string[];
      /** 귀속하지 않고 레거시에 남겨 둔 버킷과 사유. */
      left: Array<{ bucket: string; reason: "unattributable" | "not-visible" | "already-owned" }>;
    };

/**
 * 레거시 공유 버킷에서 **이 계정 것만** 골라 현재 계정 데이터에 합친다.
 *
 * @param legacy   레거시 공유키에서 읽은 `byProject`(읽기 전용 — 호출자는 원본을 지우지 않는다)
 * @param owned    현재 계정 키에 이미 있는 `byProject`
 * @param visibleProjectIds 이 사용자가 볼 수 있는 프로젝트 id 전체
 * @param truncated 프로젝트 목록이 상한에 걸려 **끝까지 못 걸었다**
 */
export function decideMigration<T>(args: {
  legacy: Record<string, T[]> | null | undefined;
  owned: Record<string, T[]>;
  visibleProjectIds: ReadonlySet<string>;
  truncated: boolean;
}): MigrationDecision<T> {
  const { legacy, owned, visibleProjectIds, truncated } = args;

  const legacyBuckets = Object.entries(legacy ?? {}).filter(([, v]) => Array.isArray(v) && v.length > 0);
  if (legacyBuckets.length === 0) return { action: "noop", reason: "no-legacy" };

  // ★안전장치 3 — 불완전한 목록으로 귀속하지 않는다. 미루면 다음 기회에 온전한 목록으로 한다.
  if (truncated) return { action: "defer", reason: "truncated" };
  if (visibleProjectIds.size === 0) return { action: "defer", reason: "no-projects" };

  const merged: Record<string, T[]> = { ...owned };
  const adopted: string[] = [];
  const left: Array<{ bucket: string; reason: "unattributable" | "not-visible" | "already-owned" }> = [];

  for (const [bucket, items] of legacyBuckets) {
    // ★안전장치 2 — 프로젝트가 없던 항목은 누구 것인지 말할 재료가 없다. 추측하지 않는다.
    if (bucket === UNATTRIBUTED_BUCKET) {
      left.push({ bucket, reason: "unattributable" });
      continue;
    }
    if (!visibleProjectIds.has(bucket)) {
      left.push({ bucket, reason: "not-visible" });
      continue;
    }
    // 이미 이 계정 키에 그 프로젝트 데이터가 있으면 **덮지 않는다** — 현행이 더 최신이고,
    // 레거시로 덮으면 방금 산 것이 옛것으로 되돌아간다.
    if (Array.isArray(owned[bucket]) && owned[bucket].length > 0) {
      left.push({ bucket, reason: "already-owned" });
      continue;
    }
    merged[bucket] = items;
    adopted.push(bucket);
  }

  if (adopted.length === 0) return { action: "noop", reason: "nothing-owned" };
  return { action: "migrate", merged, adopted, left };
}

/** 레거시 **공유키**를 원본 그대로 읽는다(스코프를 붙이지 않는다 · 지우지 않는다). */
export function readLegacyByProject<T>(legacyKey: string): Record<string, T[]> | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(legacyKey);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StorageValue<{ byProject?: Record<string, T[]> }>;
    const bp = parsed?.state?.byProject;
    return bp && typeof bp === "object" ? bp : null;
  } catch {
    return null;
  }
}
