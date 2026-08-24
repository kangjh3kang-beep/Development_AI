/**
 * 프로젝트 목록 조회 SSOT — **페이지를 끝까지 걷는다.**
 *
 * ## 무엇이 있었나(라이브 실측 2026-08-25)
 *
 * 백엔드 `GET /projects` 는 `page_size` 기본값이 **20** 이다(`routers/projects.py`).
 * 그런데 목록 화면의 실제 데이터원인 `store/useProjectStore.ts:syncFromBackend()` 는
 * 페이지 파라미터를 **하나도 주지 않고** 부른 뒤, 그 응답으로 로컬 목록을 **통째로 교체**했다:
 *
 *     set({ projects: [...backend, ...migrated] })   // backend = 최신 20건뿐
 *
 * 프로덕션 실측: `total=24 · page_size=20 · has_next=true` →
 * **가장 오래된 4건이 목록에서 사라진다**(2026-06 생성분 4건).
 *
 * ## 왜 단순한 표시 결함이 아닌가 — **중복 생성으로 번진다**
 *
 * 같은 함수의 고아 판정이 그 잘린 목록에 의존한다:
 *
 *     const seen = new Set(backend.map((p) => p.address.trim()))
 *     if (!_isUuid(p.id) && a && !seen.has(a) && …) orphans.push(p)   // → 다시 POST
 *
 * 잘려서 안 보이는 프로젝트의 주소를 가진 로컬 레코드는 `seen` 에 없다 →
 * **"백엔드에 없다"고 오판해 같은 프로젝트를 다시 만든다.**
 * ★`#815` 의 인플라이트 레지스트리로는 못 막는다 — 그것은 *생성이 진행 중인* 것만 보호하고,
 *   이쪽은 **이미 완료된** 프로젝트가 목록에서 안 보여서 생기는 오판이다. 경로가 다르다.
 *
 * ## 조용히 자르지 않는다
 *
 * 상한(`PROJECTS_MAX_PAGES`)에 걸려 끝까지 못 걸으면 `truncated: true` 로 **사실을 실어 보낸다**.
 * 형제 선례: `BulkParcelBatchPanel` 은 `has_next` 를 읽어 *"…상위 200건 표시(전체 N건)"* 라고
 * 화면에 고지한다 — 이 저장소가 이미 갖고 있던 옳은 패턴이다.
 */

/** 한 번에 받는 크기. 기본 20 은 너무 작아 24건 테넌트에서 이미 잘렸다. */
export const PROJECTS_PAGE_SIZE = 100;

/** 순회 상한 — 무한루프 방지. 넘으면 `truncated:true` 로 **신고**한다(조용한 절단 금지). */
export const PROJECTS_MAX_PAGES = 20;

export type ProjectsPageResponse<T> = {
  items?: T[] | null;
  /** 일부 소비자/픽스처는 `projects` 키를 쓴다(release-harness 가 두 키를 함께 담는 이유). */
  projects?: T[] | null;
  total?: number | null;
  page?: number | null;
  page_size?: number | null;
  has_next?: boolean | null;
};

export type AllProjectsResult<T> = {
  items: T[];
  /** 서버가 말한 전체 건수. 못 받았으면 null(0 으로 날조하지 않는다). */
  total: number | null;
  /**
   * ★상한에 걸려 **끝까지 못 걸었다**. 이 값이 참이면 `items` 는 전체가 아니다 —
   * 고아 판정처럼 "없으면 없는 것"으로 취급하는 로직은 이 값을 반드시 봐야 한다.
   */
  truncated: boolean;
  pagesFetched: number;
};

export function projectsPagePath(page: number, pageSize: number = PROJECTS_PAGE_SIZE): string {
  return `/projects?page=${page}&page_size=${pageSize}`;
}

/**
 * `has_next` 를 따라 전 페이지를 모은다.
 *
 * `getPage` 를 주입받는 이유: 소비처마다 `apiClient` 옵션(`useMock`·`timeoutMs`)이 달라서다.
 * 테스트가 apiClient 모듈을 몽키패치하지 않고 **이 함수의 판단만** 직접 태울 수 있다는 부수효과도 있다.
 */
export async function fetchAllProjects<T>(
  getPage: (path: string) => Promise<unknown>,
  opts: { pageSize?: number; maxPages?: number } = {},
): Promise<AllProjectsResult<T>> {
  const pageSize = opts.pageSize ?? PROJECTS_PAGE_SIZE;
  const maxPages = opts.maxPages ?? PROJECTS_MAX_PAGES;
  const items: T[] = [];
  let total: number | null = null;
  let page = 1;
  let hasNext = true;
  let pagesFetched = 0;

  while (hasNext && pagesFetched < maxPages) {
    const raw = await getPage(projectsPagePath(page, pageSize));
    pagesFetched += 1;

    // 레거시/목 응답이 배열 그대로인 경우 — 페이지 정보가 없으므로 그것이 전부다.
    if (Array.isArray(raw)) {
      items.push(...(raw as T[]));
      hasNext = false;
      break;
    }

    const res = (raw ?? {}) as ProjectsPageResponse<T>;
    const batch = Array.isArray(res.items)
      ? res.items
      : Array.isArray(res.projects)
        ? res.projects
        : [];
    items.push(...batch);
    if (typeof res.total === "number") total = res.total;

    // ★이중 종료 조건: `has_next` 가 참이어도 **빈 페이지면 멈춘다**.
    //   서버가 has_next 를 잘못 계산하면 상한까지 헛도는데, 그 낭비가 곧 사용자 대기시간이다.
    hasNext = res.has_next === true && batch.length > 0;
    page += 1;
  }

  return { items, total, truncated: hasNext, pagesFetched };
}

/** 고아 판정에 필요한 최소 형태 — store 의 `Project` 전체 타입을 요구하지 않는다. */
export type OrphanCandidate = { id: string; address: string };

export type SelectOrphansOptions = {
  /**
   * ★백엔드 목록이 **전부**인가. 거짓이면 고아 판정을 **하지 않는다**.
   *
   * 왜: 불완전한 목록으로 "백엔드에 없다"고 판정하면, 잘려서 안 보일 뿐인 프로젝트를
   * 고아로 오판해 **같은 프로젝트를 다시 만든다**. 모르면 아무것도 안 하는 쪽이 안전하다
   * (중복 생성은 되돌리기 어렵고, 마이그레이션 지연은 다음 동기화가 만회한다).
   */
  listComplete: boolean;
  isUuid: (id: string) => boolean;
  /** 서버 생성이 진행 중인 로컬 id — `#815` 의 인플라이트 레지스트리. */
  inFlight: ReadonlySet<string>;
};

/**
 * ★고아 **판단** — 어느 로컬 레코드를 백엔드에 다시 만들 것인가.
 *
 * 순수 함수로 꺼내 두는 이유: 종전엔 이 판정이 `syncFromBackend` 안의 `for` 루프에 박혀 있어
 * **어떤 테스트도 직접 태우지 못했다**. 재료(주소 집합)만 잠그면 판단 분기를 통째로 지워도
 * 초록이 된다 — 이 저장소가 실제로 겪은 형태다.
 */
export function selectOrphans<P extends OrphanCandidate>(
  local: readonly P[],
  backendAddresses: ReadonlySet<string>,
  opts: SelectOrphansOptions,
): P[] {
  if (!opts.listComplete) return [];
  const seen = new Set(backendAddresses);
  const orphans: P[] = [];
  for (const p of local) {
    const a = p.address.trim();
    if (!a) continue;
    if (opts.isUuid(p.id)) continue;
    if (seen.has(a)) continue;
    if (opts.inFlight.has(p.id)) continue;
    seen.add(a); // 같은 주소의 로컬 중복이 여러 번 POST 되지 않게 한다.
    orphans.push(p);
  }
  return orphans;
}
