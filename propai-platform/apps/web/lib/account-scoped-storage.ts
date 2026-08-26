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
 * **프로젝트 id 는 테넌트 스코프**다 → *"그 사용자가 볼 수 있는 프로젝트 id 에 속한 항목만
 * 그 사용자 것"* 이 안전한 규칙이다.
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
      const uid = currentUserId();
      if (scopeUid !== null && scopeUid !== uid) return; // ★교차계정 쓰기 차단
      scopeUid = uid;
      inner.setItem(accountScopedKey(name, uid), value);
    },
    removeItem: (name) => {
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
