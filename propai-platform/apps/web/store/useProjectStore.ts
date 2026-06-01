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
      // base64 siteImageUrl은 수 MB라 localStorage(약 5MB) 용량을 초과시켜
      // QuotaExceededError로 프로젝트 생성/이동이 실패하던 문제 → persist 시 제외.
      // (이미지는 세션 내 메모리에만 유지; 영속 필요 시 추후 서버 업로드로 전환)
      partialize: (state) => ({
        projects: state.projects.map(({ siteImageUrl: _omit, ...rest }) => rest),
      }),
    }
  )
);
