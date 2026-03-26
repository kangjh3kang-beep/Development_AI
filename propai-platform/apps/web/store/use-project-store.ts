import { create } from "zustand";

type ProjectStore = {
  currentProjectId: string | null;
  recentProjectIds: string[];
  activeModule: string | null;
  setCurrentProject: (projectId: string) => void;
  setActiveModule: (moduleId: string | null) => void;
};

export const useProjectStore = create<ProjectStore>((set) => ({
  currentProjectId: null,
  recentProjectIds: [],
  activeModule: null,
  setCurrentProject: (projectId) => {
    set((state) => ({
      currentProjectId: projectId,
      recentProjectIds: [
        projectId,
        ...state.recentProjectIds.filter((value) => value !== projectId),
      ].slice(0, 5),
    }));
  },
  setActiveModule: (activeModule) => {
    set({ activeModule });
  },
}));
