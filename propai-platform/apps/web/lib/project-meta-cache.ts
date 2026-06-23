// 프로젝트 메타(GET /projects/{id}) 공용 dedup 캐시.
//
// 왜 필요한가: 프로젝트 작업공간 진입 시 page.tsx·ProjectContextBinder·LifecycleStageViews 등
// 여러 컴포넌트가 같은 /projects/{id} 를 각자 마운트에서 호출해 동일 요청이 3회 중복됐다
// (실측 1747+1272+921ms). 짧은 TTL 의 in-flight promise 캐시로 동시 호출을 단일 네트워크로
// 합쳐 진입 로딩을 단축한다(auth/me role 세션캐시와 동일 패턴).
import { apiClient } from "@/lib/api-client";

type Entry = { promise: Promise<unknown>; ts: number };

const cache = new Map<string, Entry>();
// 10초: 마운트 시 동시 호출(수십 ms 간격) dedup + 짧은 재사용. 변경(수정/저장) 시 invalidate.
const TTL_MS = 10_000;

/** GET /projects/{id} — 공용 dedup 캐시 경유. 동시/근접 호출은 단일 요청을 공유한다. */
export function fetchProjectMeta<T = unknown>(
  id: string,
  opts?: { force?: boolean },
): Promise<T> {
  const now = Date.now();
  const hit = cache.get(id);
  if (!opts?.force && hit && now - hit.ts < TTL_MS) {
    return hit.promise as Promise<T>;
  }
  const promise = apiClient
    .get<T>(`/projects/${id}`, { useMock: false })
    .catch((e) => {
      // 실패는 캐시하지 않는다(다음 호출이 재시도).
      const cur = cache.get(id);
      if (cur && cur.promise === (promise as Promise<unknown>)) cache.delete(id);
      throw e;
    });
  cache.set(id, { promise: promise as Promise<unknown>, ts: now });
  return promise;
}

/** 프로젝트 수정/저장 후 메타 캐시 무효화(다음 호출이 최신값 재조회). id 미지정 시 전체. */
export function invalidateProjectMeta(id?: string): void {
  if (id) cache.delete(id);
  else cache.clear();
}
