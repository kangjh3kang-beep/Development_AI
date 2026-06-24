import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { apiClient } from '@/lib/api-client';
import { createDebouncedStorage } from '@/lib/debounced-storage';

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
          const res = await apiClient.get<{ items?: BackendProject[] }>("/projects", {
            useMock: false,
            timeoutMs: 30000,
          });
          const backend = (res.items || []).map(_mapBackend);
          // 주소 기준 중복제거(백엔드 + 로컬 누적 중복) — 동일 주소 중복 마이그레이션 방지
          const seen = new Set(
            backend.map((p) => p.address.trim()).filter(Boolean),
          );
          const orphans: Project[] = [];
          for (const p of get().projects) {
            const a = p.address.trim();
            if (!_isUuid(p.id) && a && !seen.has(a)) {
              seen.add(a);
              orphans.push(p);
            }
          }
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
                useMock: false,
                timeoutMs: 30000,
              });
              migrated.push(_mapBackend(created));
            } catch {
              migrated.push(o); // 실패 시 로컬 유지(다음 동기화에 재시도)
            }
          }
          set({ projects: [...backend, ...migrated] });
        } catch {
          // 오프라인/실패 — 기존 로컬 목록 유지
        } finally {
          set({ syncing: false });
        }
      },
      deleteProject: async (id) => {
        set((state) => ({ projects: state.projects.filter((p) => p.id !== id) }));
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
