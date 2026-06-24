import { create } from "zustand";
import { persist } from "zustand/middleware";
import { createDebouncedStorage } from "@/lib/debounced-storage";

/**
 * 주변 개발계획(신설역·구역지정·도로 등) 스토어 — 프로젝트별 영속.
 *
 * 입지분석의 '현행 역세권 판정'은 운영 중인 최근접 역만 본다(SSOT=infra.nearest_subway).
 * 하지만 신상도역 같은 '신설 계획역'이 들어오면 역세권활성화 요건 시나리오가 달라진다.
 * 이 스토어는 자동수집(VWorld 도시계획시설)과 수동입력을 함께 담아,
 * '계획 반영 역세권 시나리오'(현행 판정과 분리·정직 고지)를 산출하는 근거로 쓴다.
 *
 * 무목업·정직: 거리(distance_m)가 미상이면 null로 두고 등급 산정에서 제외한다.
 *              계획역은 '운영' 상태가 아니면 단정 판정이 아닌 '시나리오/가능'으로만 쓴다.
 */

// 개발계획 종류
export type DevPlanKind = "station" | "district" | "road";
// 진행 상태(고시·개통될수록 확정도가 높아짐)
export type DevPlanStatus = "계획" | "추진" | "고시" | "운영";
// 출처 — 자동수집(VWorld)인지 사용자 수동입력인지
export type DevPlanSource = "manual" | "auto";

export type DevPlanItem = {
  id: string;
  kind: DevPlanKind;
  name: string;
  status: DevPlanStatus;
  distance_m: number | null; // 입지~시설 거리(미상이면 null → 역세권 등급 산정 제외)
  open_year: number | null; // 개통/완공 예정연도(미상이면 null)
  source: DevPlanSource;
  note?: string; // 자동수집 시설구분·원본 상태 등 정직 메모
};

const KIND_LABEL: Record<DevPlanKind, string> = {
  station: "역(철도)",
  district: "구역지정",
  road: "도로",
};
export function devPlanKindLabel(kind: DevPlanKind): string {
  return KIND_LABEL[kind] ?? "시설";
}

export const DEV_PLAN_KINDS: { value: DevPlanKind; label: string }[] = [
  { value: "station", label: "역(철도)" },
  { value: "district", label: "구역지정" },
  { value: "road", label: "도로" },
];
export const DEV_PLAN_STATUSES: DevPlanStatus[] = ["계획", "추진", "고시", "운영"];

type State = {
  byProject: Record<string, DevPlanItem[]>;
  getByProject: (projectId: string | null) => DevPlanItem[];
  add: (projectId: string | null, item: Partial<DevPlanItem>) => void;
  update: (projectId: string | null, id: string, patch: Partial<DevPlanItem>) => void;
  remove: (projectId: string | null, id: string) => void;
};

const KEY = (id: string | null) => id || "_default";

export const useDevelopmentPlanStore = create<State>()(
  persist(
    (set, get) => ({
      byProject: {},
      getByProject: (pid) => get().byProject[KEY(pid)] || [],
      add: (pid, item) =>
        set((s) => {
          const k = KEY(pid);
          const cur = s.byProject[k] || [];
          const newItem: DevPlanItem = {
            id: Math.random().toString(36).slice(2, 9),
            kind: "station",
            name: "",
            status: "계획",
            distance_m: null,
            open_year: null,
            source: "manual",
            ...item,
          };
          // 자동수집은 동일 출처·동일 명칭·동일 거리 중복 추가를 차단(연속 클릭 방지).
          if (
            newItem.source === "auto" &&
            cur.some(
              (c) =>
                c.source === "auto" &&
                c.name === newItem.name &&
                c.distance_m === newItem.distance_m,
            )
          ) {
            return {};
          }
          return { byProject: { ...s.byProject, [k]: [...cur, newItem] } };
        }),
      update: (pid, id, patch) =>
        set((s) => {
          const k = KEY(pid);
          return {
            byProject: {
              ...s.byProject,
              [k]: (s.byProject[k] || []).map((it) => (it.id === id ? { ...it, ...patch } : it)),
            },
          };
        }),
      remove: (pid, id) =>
        set((s) => {
          const k = KEY(pid);
          return {
            byProject: {
              ...s.byProject,
              [k]: (s.byProject[k] || []).filter((it) => it.id !== id),
            },
          };
        }),
    }),
    { name: "propai-development-plan", storage: createDebouncedStorage<State>() },
  ),
);
