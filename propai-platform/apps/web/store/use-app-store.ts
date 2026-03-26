import { create } from "zustand";
import { defaultLocale, type Locale } from "@/i18n/config";

type ProjectViewMode = "grid" | "list";
type RuntimeMode = "mock" | "live" | "waiting";

type AppStore = {
  locale: Locale;
  sidebarOpen: boolean;
  online: boolean;
  projectViewMode: ProjectViewMode;
  restMode: RuntimeMode;
  graphqlEnabled: boolean;
  realtimeConnected: boolean;
  setLocale: (locale: Locale) => void;
  setSidebarOpen: (open: boolean) => void;
  setProjectViewMode: (mode: ProjectViewMode) => void;
  setOnline: (online: boolean) => void;
  setIntegrationState: (state: {
    restMode?: RuntimeMode;
    graphqlEnabled?: boolean;
    realtimeConnected?: boolean;
  }) => void;
};

export const useAppStore = create<AppStore>((set) => ({
  locale: defaultLocale,
  sidebarOpen: true,
  online: true,
  projectViewMode: "grid",
  restMode: "mock",
  graphqlEnabled: false,
  realtimeConnected: false,
  setLocale: (locale) => {
    set({ locale });
  },
  setSidebarOpen: (sidebarOpen) => {
    set({ sidebarOpen });
  },
  setProjectViewMode: (projectViewMode) => {
    set({ projectViewMode });
  },
  setOnline: (online) => {
    set({ online });
  },
  setIntegrationState: (state) => {
    set((current) => ({
      restMode: state.restMode ?? current.restMode,
      graphqlEnabled: state.graphqlEnabled ?? current.graphqlEnabled,
      realtimeConnected: state.realtimeConnected ?? current.realtimeConnected,
    }));
  },
}));
