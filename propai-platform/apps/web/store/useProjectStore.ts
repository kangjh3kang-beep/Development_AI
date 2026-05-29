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
};

type ProjectState = {
  projects: Project[];
  addProject: (project: Omit<Project, 'id' | 'createdAt' | 'status'>) => string;
  getProjectById: (id: string) => Project | undefined;
  removeProject: (id: string) => void;
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
      removeProject: (id) => {
        set((state) => ({
          projects: state.projects.filter(p => p.id !== id),
        }));
      }
    }),
    {
      name: 'propai-project-storage',
    }
  )
);
