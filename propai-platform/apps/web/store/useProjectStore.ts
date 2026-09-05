import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { apiClient } from '@/lib/api-client';
import { fetchAllProjects, selectOrphans } from "@/lib/projects-fetch";
import { migratePaidArtifacts } from "@/lib/paid-artifact-migration";
import { projectCreateHeaders } from "@/lib/project-create-key";
import { createDebouncedStorage } from '@/lib/debounced-storage';
import { purgeProjectLocalData } from "@/lib/project-lifecycle";

type ProjectStatus = 'draft' | 'planning' | 'design' | 'permit' | 'construction' | 'completed' | 'archived';

export type Project = {
  id: string;
  name: string;
  type: string;
  pnu: string;
  address: string;
  area: string;
  status: ProjectStatus;
  createdAt: string;
  siteImageUrl?: string;
  /** 다필지 통합 프로젝트의 총 필지 수(대표지번 + 외 N필지 표기용). 단일필지면 1/미설정. */
  parcelCount?: number;
};

type BackendProject = {
  id: string; name: string; status?: string; address?: string | null;
  total_area_sqm?: number | null; building_type?: string | null;
  created_at?: string; updated_at?: string;
};

const _isUuid = (id: string) => /^[0-9a-f]{8}-[0-9a-f]{4}-/i.test(id);
const _parseArea = (a?: string) => {
  const n = Number(String(a ?? '').replace(/[^0-9.]/g, ''));
  return Number.isFinite(n) ? n : 0;
};
const _mapBackend = (p: BackendProject): Project => ({
  id: p.id,
  name: p.name,
  type: p.building_type || '',
  pnu: '',
  address: p.address || '',
  area: p.total_area_sqm ? `${Math.round(p.total_area_sqm)}㎡` : '',
  status: (p.status as ProjectStatus) || 'draft',
  createdAt: p.created_at || new Date().toISOString(),
});

type ProjectState = {
  projects: Project[];
  syncing: boolean;
  addProject: (project: Omit<Project, 'id' | 'createdAt' | 'status'>) => string;
  getProjectById: (id: string) => Project | undefined;
  removeProject: (id: string) => void;
  /** 백엔드 단일출처와 동기화 + 로컬 전용(미저장) 프로젝트 마이그레이션 */
  syncFromBackend: () => Promise<void>;
  /** 백엔드 소프트삭제까지 전파(테넌트 스코프) + 로컬 제거 */
  deleteProject: (id: string) => Promise<void>;
  updateProject: (id: string, updates: Partial<Project>) => void;
};

/**
 * **서버 생성이 진행 중인 로컬 프로젝트 id** — 중복 생성 경합 차단.
 *
 * ## 무엇이 있었나(실측)
 *
 * 두 생성 경로 모두 이 순서다:
 *
 *     addProject(...)            → **비UUID** 로컬 레코드가 생긴다(주소 포함)
 *     await POST /projects       → ★이 창 동안 레코드는 "고아"로 보인다
 *     updateProject(id → UUID)   → 비로소 UUID 가 된다
 *
 * 그런데 `syncFromBackend` 는 *"비UUID 이고 주소가 백엔드 목록에 없으면 고아"* 로 보고
 * **POST 로 다시 만든다.** 그 동기화는 마운트마다 여러 화면에서 발화한다 —
 * `await` 창에 겹치면 **같은 프로젝트가 두 번 생성된다.**
 * 실물: 이름·주소·필지수(77)가 완전히 같은 **중복 프로젝트 2건**이 프로덕션에 있다.
 *
 * ★주소 문자열 중복제거로는 못 막는다 — 그 창에서는 백엔드 목록에 **아직 없기 때문**이다.
 *
 * ## 범위(정직 표기)
 *
 * 이 레지스트리는 **같은 탭** 안에서만 유효하다. 다른 탭·기기에서 동시에 같은 프로젝트를
 * 만드는 경우는 **서버측 멱등키**가 있어야 막는다(별건).
 */
const _creatingLocalIds = new Set<string>();

/** 서버 생성 시작을 알린다 — 이 id 는 그동안 "고아"로 취급되지 않는다. */
export function markProjectCreating(localId: string): void {
  if (localId) _creatingLocalIds.add(localId);
}

/** 성공·실패 **양쪽 모두** 호출한다. 실패한 건은 다시 고아가 되어 다음 동기화가 재시도한다. */
export function unmarkProjectCreating(localId: string): void {
  if (localId) _creatingLocalIds.delete(localId);
}

/** 테스트·진단용 — 현재 인플라이트 개수. */
export function _creatingCount(): number {
  return _creatingLocalIds.size;
}

/** 테스트 전용 초기화. ★개별 해제를 루프로 흉내 내지 마라 — 빈 id 는 no-op 이라
 *  `while(count>0) unmark("")` 같은 정리는 **테스트가 실패했을 때만 무한루프**가 된다
 *  (변이 검증이 필요한 바로 그 순간에 하네스가 멈춘다 — 실제로 겪었다). */
export function __resetProjectCreating(): void {
  _creatingLocalIds.clear();
}

export const useProjectStore = create<ProjectState>()(
  persist(
    (set, get) => ({
      projects: [],
      syncing: false,
      addProject: (projectData) => {
        const id = Math.random().toString(36).substring(2, 9);
        const newProject: Project = {
          ...projectData,
          id,
          status: 'draft',
          createdAt: new Date().toISOString(),
        };
        set((state) => ({
          projects: [...state.projects, newProject],
        }));
        return id;
      },
      getProjectById: (id) => {
        return get().projects.find(p => p.id === id);
      },
      updateProject: (id, updates) => {
        set((state) => ({
          projects: state.projects.map((p) =>
            p.id === id ? { ...p, ...updates } : p
          )
        }));
      },
      removeProject: (id) => {
        set((state) => ({
          projects: state.projects.filter(p => p.id !== id),
        }));
      },
      syncFromBackend: async () => {
        if (get().syncing) return;
        set({ syncing: true });
        try {
          // ★페이지를 끝까지 걷는다. 종전엔 파라미터 없이 한 번만 불러 **최신 20건**만 받고
          //   그것으로 로컬 목록을 통째로 교체했다(서버 기본 page_size=20).
          //   프로덕션 실측(2026-08-25): total=24 · has_next=true → 오래된 4건이 사라졌다.
          const fetched = await fetchAllProjects<BackendProject>((path) =>
            apiClient.get<unknown>(path, { useMock: false, timeoutMs: 30000 }),
          );
          const backend = fetched.items.map(_mapBackend);
          const listComplete = !fetched.truncated;
          // 주소 기준 중복제거(백엔드 + 로컬 누적 중복) — 동일 주소 중복 마이그레이션 방지
          const seen = new Set(
            backend.map((p) => p.address.trim()).filter(Boolean),
          );
          // ★고아 판정은 순수 함수로 꺼냈다 — 루프 안에 두면 어떤 테스트도 그 **판단**을
          //   직접 태우지 못한다(재료만 잠그면 분기를 통째로 지워도 초록이 된다).
          //   목록이 불완전하면 판정 자체를 하지 않는다: 잘려서 안 보일 뿐인 프로젝트를
          //   "백엔드에 없다"고 오판하면 같은 프로젝트를 **다시 만든다**.
          const orphans = selectOrphans(get().projects, seen, {
            listComplete,
            isUuid: _isUuid,
            inFlight: _creatingLocalIds,
          });
          const migrated: Project[] = [];
          for (const o of orphans) {
            try {
              const areaNum = _parseArea(o.area);
              const created = await apiClient.post<BackendProject>("/projects", {
                body: {
                  name: o.name || o.address,
                  address: o.address || undefined,
                  ...(areaNum > 0 ? { total_area_sqm: areaNum } : {}),
                },
                // ★최초 생성과 **같은 키**(로컬 id)다 — 이 재전송이 서버에서 재생으로 처리돼
                //   같은 프로젝트가 두 번 만들어지지 않는다. 클라이언트 가드가 못 닿는
                //   다른 탭·기기까지 이 한 줄이 덮는다.
                headers: projectCreateHeaders(o.id),
                useMock: false,
                timeoutMs: 30000,
              });
              migrated.push(_mapBackend(created));
            } catch {
              migrated.push(o); // 실패 시 로컬 유지(다음 동기화에 재시도)
            }
          }
          // ★유료 산출물 승계 — 목록을 **끝까지 받은 이 자리**가 유일하게 옳은 시점이다.
          //   귀속 규칙이 "이 사용자가 볼 수 있는 프로젝트 id" 를 재료로 쓰는데, 그 목록은
          //   여기서야 확정된다. 절단이면 판단이 **미룸**으로 떨어져 다음 동기화에 다시 온다
          //   (불완전한 목록으로 귀속하면 오래된 프로젝트의 유료 렌더가 전부 남의 것이 된다).
          try {
            migratePaidArtifacts({
              visibleProjectIds: new Set(backend.map((p) => p.id)),
              truncated: !listComplete,
            });
          } catch { /* 승계 실패는 조용히 넘긴다 — 레거시 원본은 그대로라 다음에 다시 시도된다 */ }
          if (listComplete) {
            set({ projects: [...backend, ...migrated] });
            // ★고아 스냅샷 정리 — **목록을 끝까지 받은 이 자리**가 유일하게 옳은 시점이다
            //   (바로 위 유료 산출물 승계와 같은 근거: 판단 재료가 여기서야 확정된다).
            //   절단(`!listComplete`)이면 **하지 않는다** — 「모르는 것을 지우지 않는다」.
            //
            //   왜 필요한가(2026-09-05 실측 · 성장루프가 신고한 `/store/projects` 지연 추적):
            //   그 응답 **3.17MB** 중 `snapshots` 가 **2.37MB**, 그중 **60%(1.42MB)** 가
            //   **이미 없는 프로젝트**의 것이었다. `snapshots` 는 `CTX_KEYS` 라 매 동기화마다
            //   왕복하는데 **쌓는 곳만 있고 지우는 곳이 없었다.**
            //   ★삭제 경로마다 붙이지 않는다 — 경로가 여럿이면 하나를 빠뜨린다.
            //   ★**정적 임포트를 쓰지 않는다** — 반대편(`useProjectContextStore`)이
            //     *"`useProjectStore` import 대신 raw 접근 — persist hydrate 순서 의존·순환
            //     import 제거"* 라고 적어 뒀다. 같은 관례로 **동적 임포트**를 쓴다.
            void import("@/store/useProjectContextStore")
              .then((m) =>
                m.useProjectContextStore
                  .getState()
                  .pruneOrphanSnapshots([...backend, ...migrated].map((p) => p.id)),
              )
              .catch(() => { /* 정리 실패는 조용히 넘긴다 — 다음 동기화에 다시 온다(기능 영향 0) */ });
          } else {
            // ★상한에 걸려 전체를 못 받았다 — **모르는 것을 지우지 않는다.**
            //   백엔드가 준 것으로 덮되, 그 목록에 없는 로컬 레코드는 "삭제됐다"고 단정할 수
            //   없으므로 남긴다(이 결함의 증상이 정확히 "있는 것이 사라진다"였다).
            const backendIds = new Set(backend.map((p) => p.id));
            const keptLocal = get().projects.filter((p) => !backendIds.has(p.id));
            set({ projects: [...backend, ...keptLocal] });
          }
        } catch {
          // 오프라인/실패 — 기존 로컬 목록 유지
        } finally {
          set({ syncing: false });
        }
      },
      deleteProject: async (id) => {
        set((state) => ({ projects: state.projects.filter((p) => p.id !== id) }));
        // ★생명주기 트리거 — 목록에서 지우는 것만으로는 프로젝트가 사라지지 않는다.
        //   분석 스냅샷(snapshots[id])·토지조서(byProject[id])·활성 컨텍스트가 남고,
        //   그중 snapshots 는 CTX_KEYS 라 **매 syncUp 마다 서버로 재업로드**된다 →
        //   다음 syncDown 이 다시 내려 준다(삭제가 동기화로 되돌려진다).
        purgeProjectLocalData(id);
        if (_isUuid(id)) {
          try {
            await apiClient.delete(`/projects/${id}`, { useMock: false, timeoutMs: 30000 });
          } catch {
            // 백엔드 삭제 실패는 무시(로컬은 이미 제거) — 다음 동기화에 재노출될 수 있음
          }
        }
      },
    }),
    {
      name: 'propai-project-storage',
      storage: createDebouncedStorage(),
      // 서버 업로드 URL(짧음)은 영속화하고, base64(data:) 폴백만 제외한다.
      // base64는 수 MB라 localStorage(약 5MB) 용량초과(QuotaExceededError)를 유발하므로
      // 세션 메모리에만 유지한다. (서버 업로드 = Supabase Storage public URL)
      partialize: (state) => ({
        projects: state.projects.map((p) => ({
          ...p,
          siteImageUrl:
            p.siteImageUrl && !p.siteImageUrl.startsWith("data:")
              ? p.siteImageUrl
              : undefined,
        })),
      }),
    }
  )
);
