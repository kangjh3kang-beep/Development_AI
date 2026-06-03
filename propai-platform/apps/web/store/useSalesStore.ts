/**
 * v62 분양관리 동호 상태 스토어 (zustand v5).
 * ★셀렉터 안정성: 빈 배열은 모듈 상수(EMPTY_UNITS)로 반환해 무한 렌더(React #185) 방지.
 */
import { create } from "zustand";
import type { UnitStatus } from "@/lib/salesApi";

export interface Unit {
  id: string;
  dong: string;
  ho: string;
  floor: number;
  line: string;
  aspect?: string;
  status: UnitStatus;
  total_price?: number;
  type_id?: string;
}

export const EMPTY_UNITS: Unit[] = [];

interface SalesState {
  units: Unit[];
  selectedUnit?: Unit;
  setUnits: (u: Unit[]) => void;
  select: (u?: Unit) => void;
  applyStatus: (unitId: string, to: UnitStatus) => void; // WebSocket 실시간 반영
}

export const useSalesStore = create<SalesState>((set) => ({
  units: EMPTY_UNITS,
  setUnits: (u) => set({ units: u }),
  select: (u) => set({ selectedUnit: u }),
  applyStatus: (id, to) =>
    set((st) => ({ units: st.units.map((u) => (u.id === id ? { ...u, status: to } : u)) })),
}));
