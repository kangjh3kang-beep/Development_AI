import { create } from "zustand";
import type {
  CadSnapshot,
  CadState,
  CadTool,
  DesignPayload,
} from "@/components/cad/types";

const POLYGON_FILLS = [
  "rgba(14,116,144,0.18)",
  "rgba(217,119,6,0.18)",
  "rgba(16,185,129,0.18)",
  "rgba(99,102,241,0.18)",
  "rgba(239,68,68,0.18)",
];

let nextPointIndex = 1;
let nextLineIndex = 1;
let nextPolygonIndex = 1;
let fillIndex = 0;

function genPointId() {
  return `pt-${nextPointIndex++}`;
}
function genLineId() {
  return `ln-${nextLineIndex++}`;
}
function genPolygonId() {
  return `pg-${nextPolygonIndex++}`;
}
function nextFill() {
  return POLYGON_FILLS[fillIndex++ % POLYGON_FILLS.length];
}

function takeSnapshot(state: CadState): CadSnapshot {
  return structuredClone({
    points: state.points,
    lines: state.lines,
    polygons: state.polygons,
    floorCount: state.floorCount,
    buildingHeightM: state.buildingHeightM,
    scale: state.scale,
  });
}

function snapValue(v: number, gridSize: number, enabled: boolean) {
  if (!enabled) return v;
  return Math.round(v / gridSize) * gridSize;
}

type CadStore = CadState & {
  selectedId: string | null;
  tool: CadTool;
  gridSize: number;
  gridSnap: boolean;
  pendingPointIds: string[];
  undoStack: CadSnapshot[];
  redoStack: CadSnapshot[];

  setTool: (tool: CadTool) => void;
  setGridSnap: (snap: boolean) => void;
  setGridSize: (size: number) => void;
  setSelected: (id: string | null) => void;
  setFloorCount: (count: number) => void;
  setBuildingHeight: (height: number) => void;

  addPoint: (x: number, y: number) => string;
  movePoint: (id: string, x: number, y: number) => void;
  addLine: (startId: string, endId: string) => void;
  addPolygon: (pointIds: string[]) => void;
  removeSelected: () => void;

  handleCanvasClick: (x: number, y: number) => void;
  completePending: () => void;
  cancelPending: () => void;

  undo: () => void;
  redo: () => void;

  toDesignPayload: () => DesignPayload;
  resetCanvas: () => void;
};

export const useCadStore = create<CadStore>((set, get) => ({
  points: [],
  lines: [],
  polygons: [],
  floorCount: 1,
  buildingHeightM: 3.0,
  scale: 10.0,
  selectedId: null,
  tool: "select",
  gridSize: 20,
  gridSnap: true,
  pendingPointIds: [],
  undoStack: [],
  redoStack: [],

  setTool: (tool) => {
    set({ tool, pendingPointIds: [], selectedId: null });
  },
  setGridSnap: (gridSnap) => {
    set({ gridSnap });
  },
  setGridSize: (gridSize) => {
    set({ gridSize });
  },
  setSelected: (selectedId) => {
    set({ selectedId });
  },
  setFloorCount: (floorCount) => {
    set({ floorCount: Math.max(1, floorCount) });
  },
  setBuildingHeight: (buildingHeightM) => {
    set({ buildingHeightM: Math.max(0, buildingHeightM) });
  },

  addPoint: (rawX, rawY) => {
    const s = get();
    const x = snapValue(rawX, s.gridSize, s.gridSnap);
    const y = snapValue(rawY, s.gridSize, s.gridSnap);
    const id = genPointId();
    const snap = takeSnapshot(s);
    set({
      points: [...s.points, { id, x, y }],
      undoStack: [...s.undoStack, snap],
      redoStack: [],
    });
    return id;
  },

  movePoint: (id, rawX, rawY) => {
    const s = get();
    const x = snapValue(rawX, s.gridSize, s.gridSnap);
    const y = snapValue(rawY, s.gridSize, s.gridSnap);
    set({
      points: s.points.map((p) => (p.id === id ? { ...p, x, y } : p)),
    });
  },

  addLine: (startId, endId) => {
    const s = get();
    const snap = takeSnapshot(s);
    set({
      lines: [...s.lines, { id: genLineId(), startPointId: startId, endPointId: endId }],
      undoStack: [...s.undoStack, snap],
      redoStack: [],
    });
  },

  addPolygon: (pointIds) => {
    const s = get();
    const snap = takeSnapshot(s);
    set({
      polygons: [...s.polygons, { id: genPolygonId(), pointIds, fill: nextFill() }],
      undoStack: [...s.undoStack, snap],
      redoStack: [],
    });
  },

  removeSelected: () => {
    const s = get();
    if (!s.selectedId) return;
    const snap = takeSnapshot(s);
    const id = s.selectedId;
    set({
      points: s.points.filter((p) => p.id !== id),
      lines: s.lines.filter(
        (l) => l.id !== id && l.startPointId !== id && l.endPointId !== id,
      ),
      polygons: s.polygons
        .filter((pg) => pg.id !== id)
        .map((pg) => ({
          ...pg,
          pointIds: pg.pointIds.filter((pid) => pid !== id),
        }))
        .filter((pg) => pg.pointIds.length >= 3),
      selectedId: null,
      undoStack: [...s.undoStack, snap],
      redoStack: [],
    });
  },

  handleCanvasClick: (rawX, rawY) => {
    const s = get();
    const x = snapValue(rawX, s.gridSize, s.gridSnap);
    const y = snapValue(rawY, s.gridSize, s.gridSnap);

    if (s.tool === "point") {
      get().addPoint(x, y);
      return;
    }

    if (s.tool === "line") {
      const ptId = genPointId();
      const snap = takeSnapshot(s);
      const newPoints = [...s.points, { id: ptId, x, y }];
      const pending = [...s.pendingPointIds, ptId];

      if (pending.length === 2) {
        set({
          points: newPoints,
          lines: [
            ...s.lines,
            { id: genLineId(), startPointId: pending[0], endPointId: pending[1] },
          ],
          pendingPointIds: [],
          undoStack: [...s.undoStack, snap],
          redoStack: [],
        });
      } else {
        set({ points: newPoints, pendingPointIds: pending });
      }
      return;
    }

    if (s.tool === "polygon") {
      const ptId = genPointId();
      const newPoints = [...s.points, { id: ptId, x, y }];
      set({ points: newPoints, pendingPointIds: [...s.pendingPointIds, ptId] });
    }
  },

  completePending: () => {
    const s = get();
    if (s.tool === "polygon" && s.pendingPointIds.length >= 3) {
      const snap = takeSnapshot(s);
      set({
        polygons: [
          ...s.polygons,
          { id: genPolygonId(), pointIds: [...s.pendingPointIds], fill: nextFill() },
        ],
        pendingPointIds: [],
        undoStack: [...s.undoStack, snap],
        redoStack: [],
      });
    }
  },

  cancelPending: () => {
    set({ pendingPointIds: [] });
  },

  undo: () => {
    const s = get();
    if (s.undoStack.length === 0) return;
    const current = takeSnapshot(s);
    const prev = s.undoStack[s.undoStack.length - 1];
    set({
      ...prev,
      undoStack: s.undoStack.slice(0, -1),
      redoStack: [...s.redoStack, current],
    });
  },

  redo: () => {
    const s = get();
    if (s.redoStack.length === 0) return;
    const current = takeSnapshot(s);
    const next = s.redoStack[s.redoStack.length - 1];
    set({
      ...next,
      redoStack: s.redoStack.slice(0, -1),
      undoStack: [...s.undoStack, current],
    });
  },

  toDesignPayload: () => {
    const s = get();
    return {
      points: s.points.map((p) => ({ id: p.id, x: p.x, y: p.y })),
      lines: s.lines.map((l) => ({
        id: l.id,
        startPointId: l.startPointId,
        endPointId: l.endPointId,
      })),
      surfaces: s.polygons.map((pg) => ({ id: pg.id, pointIds: pg.pointIds })),
      floor_count: s.floorCount,
      building_height_m: s.buildingHeightM,
      scale: s.scale,
    };
  },

  resetCanvas: () => {
    const s = get();
    const snap = takeSnapshot(s);
    set({
      points: [],
      lines: [],
      polygons: [],
      selectedId: null,
      pendingPointIds: [],
      undoStack: [...s.undoStack, snap],
      redoStack: [],
    });
  },
}));
