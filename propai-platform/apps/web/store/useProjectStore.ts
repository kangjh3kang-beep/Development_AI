import { create } from 'zustand';
import { persist } from 'zustand/middleware';

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
};

type ProjectState = {
  projects: Project[];
  addProject: (project: Omit<Project, 'id' | 'createdAt' | 'status'>) => string;
  getProjectById: (id: string) => Project | undefined;
  removeProject: (id: string) => void;
  updateProject: (id: string, updates: Partial<Project>) => void;
};

export const useProjectStore = create<ProjectState>()(
  persist(
    (set, get) => ({
      projects: [],
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
      }
    }),
    {
      name: 'propai-project-storage',
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
