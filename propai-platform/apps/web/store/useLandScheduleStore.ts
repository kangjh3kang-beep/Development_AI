import { create } from "zustand";
import { persist } from "zustand/middleware";

/**
 * 토지조서(편입토지 관리) 스토어 — 프로젝트별 영속.
 *
 * 지번·소유자·소유지분·면적·소유구분(사유/국공유)·매입예정가·매입가·계약확정·
 * 동의(토지사용/지구단위)를 관리하고, 등기정보분석과 상호 연동한다.
 * 서버 동기화는 projectSync가 함께 처리(기기 무관).
 */

export type LandRow = {
  id: string;
  jibun: string; // 지번(주소)
  owner: string; // 소유자
  share: string; // 소유지분
  area_sqm: number | null; // 면적
  owner_type: "사유지" | "국공유지" | ""; // 소유구분
  expected_price: number | null; // 매입예정가(원)
  purchase_price: number | null; // 매입가(원)
  contracted: boolean; // 매입계약 확정여부
  land_use_consent: boolean; // 토지사용동의서
  district_consent: boolean; // 지구단위(정비) 동의서
  pdf_url?: string | null; // 발급 등기부등본 PDF(서버 저장, TTL)
  note?: string;
};

type State = {
  byProject: Record<string, LandRow[]>;
  getRows: (projectId: string | null) => LandRow[];
  setRows: (projectId: string | null, rows: LandRow[]) => void;
  addRow: (projectId: string | null, row: Partial<LandRow>) => void;
  updateRow: (projectId: string | null, id: string, patch: Partial<LandRow>) => void;
  removeRow: (projectId: string | null, id: string) => void;
};

const KEY = (id: string | null) => id || "_default";

export const useLandScheduleStore = create<State>()(
  persist(
    (set, get) => ({
      byProject: {},
      getRows: (pid) => get().byProject[KEY(pid)] || [],
      setRows: (pid, rows) =>
        set((s) => ({ byProject: { ...s.byProject, [KEY(pid)]: rows } })),
      addRow: (pid, row) =>
        set((s) => {
          const k = KEY(pid);
          const cur = s.byProject[k] || [];
          const newRow: LandRow = {
            id: Math.random().toString(36).slice(2, 9),
            jibun: "", owner: "", share: "", area_sqm: null, owner_type: "",
            expected_price: null, purchase_price: null, contracted: false,
            land_use_consent: false, district_consent: false,
            ...row,
          };
          return { byProject: { ...s.byProject, [k]: [...cur, newRow] } };
        }),
      updateRow: (pid, id, patch) =>
        set((s) => {
          const k = KEY(pid);
          return { byProject: { ...s.byProject, [k]: (s.byProject[k] || []).map((r) => (r.id === id ? { ...r, ...patch } : r)) } };
        }),
      removeRow: (pid, id) =>
        set((s) => {
          const k = KEY(pid);
          return { byProject: { ...s.byProject, [k]: (s.byProject[k] || []).filter((r) => r.id !== id) } };
        }),
    }),
    { name: "propai-land-schedule" },
  ),
);
