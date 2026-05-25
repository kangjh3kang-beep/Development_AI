import { create } from "zustand";
import type {
  CadPoint,
  CadLine,
  CadPolygon,
  CadSnapshot,
  CadState,
  CadTool,
  CadPart,
  CadRect,
  CadCircle,
  CadText,
  DesignPayload,
  LayerConfig,
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
let nextRectIndex = 1;
let nextCircleIndex = 1;
let nextTextIndex = 1;
let fillIndex = 0;

const MAX_UNDO_STACK = 50;

/** 전역 인덱스 초기화 (loadDesignPayload, 테스트 등에서 사용). */
function resetIndices() {
  nextPointIndex = 1;
  nextLineIndex = 1;
  nextPolygonIndex = 1;
  nextRectIndex = 1;
  nextCircleIndex = 1;
  nextTextIndex = 1;
  fillIndex = 0;
}

function genPointId() {
  return `pt-${nextPointIndex++}`;
}
function genLineId() {
  return `ln-${nextLineIndex++}`;
}
function genPolygonId() {
  return `pg-${nextPolygonIndex++}`;
}
function genRectId() {
  return `rc-${nextRectIndex++}`;
}
function genCircleId() {
  return `ci-${nextCircleIndex++}`;
}
function genTextId() {
  return `tx-${nextTextIndex++}`;
}
function nextFill() {
  return POLYGON_FILLS[fillIndex++ % POLYGON_FILLS.length];
}

function takeSnapshot(state: CadState): CadSnapshot {
  return structuredClone({
    points: state.points,
    lines: state.lines,
    polygons: state.polygons,
    rects: state.rects,
    circles: state.circles,
    texts: state.texts,
    floorCount: state.floorCount,
    buildingHeightM: state.buildingHeightM,
    scale: state.scale,
    analysisMarkers: state.analysisMarkers,
    isAnalyzing: state.isAnalyzing,
  });
}

function snapValue(v: number, gridSize: number, enabled: boolean) {
  if (!enabled) return v;
  return Math.round(v / gridSize) * gridSize;
}

type CadStore = CadState & {
  selectedId: string | null;
  selectedIds: string[];
  tool: CadTool;
  gridSize: number;
  gridSnap: boolean;
  pendingPointIds: string[];
  pendingOrigin: { x: number; y: number } | null;
  undoStack: CadSnapshot[];
  redoStack: CadSnapshot[];
  layers: LayerConfig[];
  activePart: CadPart;
  analysisMarkers: Array<{ id: string; x: number; y: number; severity: string; desc: string }>;
  isAnalyzing: boolean;
  cursorPos: { x: number; y: number };
  viewScale: number;
  textInputPending: { x: number; y: number } | null;

  setTool: (tool: CadTool) => void;
  setPart: (part: CadPart) => void;
  toggleLayerVisibility: (name: string) => void;
  toggleLayerLock: (name: string) => void;
  setGridSnap: (snap: boolean) => void;
  setGridSize: (size: number) => void;
  setSelected: (id: string | null) => void;
  toggleSelected: (id: string) => void;
  clearSelection: () => void;
  setFloorCount: (count: number) => void;
  setBuildingHeight: (height: number) => void;

  addPoint: (x: number, y: number) => string;
  movePoint: (id: string, x: number, y: number) => void;
  addLine: (startId: string, endId: string) => void;
  addPolygon: (pointIds: string[]) => void;
  addRect: (x: number, y: number, width: number, height: number) => void;
  addCircle: (cx: number, cy: number, radius: number) => void;
  addText: (x: number, y: number, text: string) => void;
  removeSelected: () => void;

  handleCanvasClick: (x: number, y: number) => void;
  completePending: () => void;
  cancelPending: () => void;
  confirmTextInput: (text: string) => void;
  cancelTextInput: () => void;

  undo: () => void;
  redo: () => void;

  setCursorPos: (x: number, y: number) => void;
  setViewScale: (scale: number) => void;

  toDesignPayload: () => DesignPayload;
  loadDesignPayload: (payload: DesignPayload) => void;
  setAnalysis: (isAnalyzing: boolean, markers: Array<{ id: string; x: number; y: number; severity: "high" | "med" | "low"; desc: string }>) => void;
  resetCanvas: () => void;
};

export const useCadStore = create<CadStore>()((set, get) => ({
  points: [],
  lines: [],
  polygons: [],
  rects: [],
  circles: [],
  texts: [],
  floorCount: 1,
  buildingHeightM: 3.0,
  scale: 10.0,
  selectedId: null,
  selectedIds: [],
  tool: "select",
  gridSize: 20,
  gridSnap: true,
  pendingPointIds: [],
  pendingOrigin: null,
  undoStack: [],
  redoStack: [],
  cursorPos: { x: 0, y: 0 },
  viewScale: 1,
  textInputPending: null,
  layers: [
    { name: "A-WALL", color: "#000000", weight: 0.50, visible: true, locked: false },
    { name: "A-DOOR", color: "#0000FF", weight: 0.35, visible: true, locked: false },
    { name: "A-WIND", color: "#0984e3", weight: 0.35, visible: true, locked: false },
    { name: "A-DIMS", color: "#d63031", weight: 0.18, visible: true, locked: false },
    { name: "A-TEXT", color: "#2d3436", weight: 0.18, visible: true, locked: false },
    { name: "A-SITE", color: "#ffeaa7", weight: 0.25, visible: true, locked: false },
    { name: "A-HATC", color: "#dfe6e9", weight: 0.13, visible: true, locked: false },
  ],
  activePart: "ARCH",
  analysisMarkers: [],
  isAnalyzing: false,

  toggleLayerVisibility: (name: string) => {
    set((s: CadStore) => ({
      layers: s.layers.map((l: LayerConfig) =>
        l.name === name ? { ...l, visible: !l.visible } : l
      ),
    }));
  },
  toggleLayerLock: (name: string) => {
    set((s: CadStore) => ({
      layers: s.layers.map((l: LayerConfig) =>
        l.name === name ? { ...l, locked: !l.locked } : l
      ),
    }));
  },

  setTool: (tool: CadTool) => {
    set({ tool, pendingPointIds: [], pendingOrigin: null, selectedId: null, selectedIds: [] });
  },
  setPart: (activePart: CadPart) => {
    set({ activePart });
  },
  setGridSnap: (gridSnap: boolean) => {
    set({ gridSnap });
  },
  setGridSize: (gridSize: number) => {
    set({ gridSize });
  },
  setSelected: (selectedId: string | null) => {
    set({ selectedId, selectedIds: selectedId ? [selectedId] : [] });
  },
  toggleSelected: (id: string) => {
    const s = get();
    const ids = s.selectedIds.includes(id)
      ? s.selectedIds.filter((sid: string) => sid !== id)
      : [...s.selectedIds, id];
    set({ selectedIds: ids, selectedId: ids.length > 0 ? ids[ids.length - 1] : null });
  },
  clearSelection: () => {
    set({ selectedId: null, selectedIds: [] });
  },
  setFloorCount: (floorCount: number) => {
    set({ floorCount: Math.max(1, floorCount) });
  },
  setBuildingHeight: (buildingHeightM: number) => {
    set({ buildingHeightM: Math.max(0, buildingHeightM) });
  },

  addPoint: (rawX: number, rawY: number) => {
    const s = get();
    const x = snapValue(rawX, s.gridSize, s.gridSnap);
    const y = snapValue(rawY, s.gridSize, s.gridSnap);
    const id = genPointId();
    const snap = takeSnapshot(s);
    set({
      points: [...s.points, { id, x, y }],
      undoStack: [...s.undoStack, snap].slice(-MAX_UNDO_STACK),
      redoStack: [],
    });
    return id;
  },

  movePoint: (id: string, rawX: number, rawY: number) => {
    const s = get();
    const x = snapValue(rawX, s.gridSize, s.gridSnap);
    const y = snapValue(rawY, s.gridSize, s.gridSnap);
    set({
      points: s.points.map((p) => (p.id === id ? { ...p, x, y } : p)),
    });
  },

  addLine: (startId: string, endId: string) => {
    const s = get();
    const snap = takeSnapshot(s);
    set({
      lines: [...s.lines, { id: genLineId(), startPointId: startId, endPointId: endId }],
      undoStack: [...s.undoStack, snap].slice(-MAX_UNDO_STACK),
      redoStack: [],
    });
  },

  addPolygon: (pointIds: string[]) => {
    const s = get();
    const snap = takeSnapshot(s);
    set({
      polygons: [...s.polygons, { id: genPolygonId(), pointIds, fill: nextFill() }],
      undoStack: [...s.undoStack, snap].slice(-MAX_UNDO_STACK),
      redoStack: [],
    });
  },

  addRect: (x: number, y: number, width: number, height: number) => {
    const s = get();
    const snap = takeSnapshot(s);
    set({
      rects: [...s.rects, { id: genRectId(), x, y, width, height }],
      undoStack: [...s.undoStack, snap].slice(-MAX_UNDO_STACK),
      redoStack: [],
    });
  },

  addCircle: (cx: number, cy: number, radius: number) => {
    const s = get();
    const snap = takeSnapshot(s);
    set({
      circles: [...s.circles, { id: genCircleId(), cx, cy, radius }],
      undoStack: [...s.undoStack, snap].slice(-MAX_UNDO_STACK),
      redoStack: [],
    });
  },

  addText: (x: number, y: number, text: string) => {
    const s = get();
    const snap = takeSnapshot(s);
    set({
      texts: [...s.texts, { id: genTextId(), x, y, text, fontSize: 14 }],
      undoStack: [...s.undoStack, snap].slice(-MAX_UNDO_STACK),
      redoStack: [],
    });
  },

  removeSelected: () => {
    const s = get();
    const ids = s.selectedIds.length > 0 ? s.selectedIds : s.selectedId ? [s.selectedId] : [];
    if (ids.length === 0) return;
    const snap = takeSnapshot(s);
    const idSet = new Set(ids);
    set({
      points: s.points.filter((p) => !idSet.has(p.id)),
      lines: s.lines.filter(
        (l) => !idSet.has(l.id) && !idSet.has(l.startPointId) && !idSet.has(l.endPointId),
      ),
      polygons: s.polygons
        .filter((pg) => !idSet.has(pg.id))
        .map((pg) => ({
          ...pg,
          pointIds: pg.pointIds.filter((pid) => !idSet.has(pid)),
        }))
        .filter((pg) => pg.pointIds.length >= 3),
      rects: s.rects.filter((r) => !idSet.has(r.id)),
      circles: s.circles.filter((c) => !idSet.has(c.id)),
      texts: s.texts.filter((t) => !idSet.has(t.id)),
      selectedId: null,
      selectedIds: [],
      undoStack: [...s.undoStack, snap].slice(-MAX_UNDO_STACK),
      redoStack: [],
    });
  },

  handleCanvasClick: (rawX: number, rawY: number) => {
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
          undoStack: [...s.undoStack, snap].slice(-MAX_UNDO_STACK),
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
      return;
    }

    if (s.tool === "rect") {
      if (!s.pendingOrigin) {
        set({ pendingOrigin: { x, y } });
      } else {
        const ox = Math.min(s.pendingOrigin.x, x);
        const oy = Math.min(s.pendingOrigin.y, y);
        const w = Math.abs(x - s.pendingOrigin.x);
        const h = Math.abs(y - s.pendingOrigin.y);
        if (w > 0 && h > 0) {
          get().addRect(ox, oy, w, h);
        }
        set({ pendingOrigin: null });
      }
      return;
    }

    if (s.tool === "circle") {
      if (!s.pendingOrigin) {
        set({ pendingOrigin: { x, y } });
      } else {
        const dx = x - s.pendingOrigin.x;
        const dy = y - s.pendingOrigin.y;
        const r = Math.sqrt(dx * dx + dy * dy);
        if (r > 0) {
          get().addCircle(s.pendingOrigin.x, s.pendingOrigin.y, Math.round(r));
        }
        set({ pendingOrigin: null });
      }
      return;
    }

    if (s.tool === "text") {
      set({ textInputPending: { x, y } });
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
        undoStack: [...s.undoStack, snap].slice(-MAX_UNDO_STACK),
        redoStack: [],
      });
    }
  },

  cancelPending: () => {
    set({ pendingPointIds: [], pendingOrigin: null });
  },

  confirmTextInput: (text: string) => {
    const s = get();
    if (!s.textInputPending || !text.trim()) return;
    get().addText(s.textInputPending.x, s.textInputPending.y, text.trim());
    set({ textInputPending: null });
  },

  cancelTextInput: () => {
    set({ textInputPending: null });
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

  setCursorPos: (x: number, y: number) => {
    set({ cursorPos: { x, y } });
  },

  setViewScale: (viewScale: number) => {
    set({ viewScale });
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
      rects: s.rects.map((r) => ({ id: r.id, x: r.x, y: r.y, width: r.width, height: r.height })),
      circles: s.circles.map((c) => ({ id: c.id, cx: c.cx, cy: c.cy, radius: c.radius })),
      texts: s.texts.map((t) => ({ id: t.id, x: t.x, y: t.y, text: t.text })),
      floor_count: s.floorCount,
      building_height_m: s.buildingHeightM,
      scale: s.scale,
    };
  },

  loadDesignPayload: (payload: DesignPayload) => {
    const s = get();
    const snap = takeSnapshot(s);
    resetIndices();

    const points: CadPoint[] = payload.points.map((p) => ({
      id: p.id || genPointId(),
      x: p.x,
      y: p.y,
    }));
    const lines: CadLine[] = payload.lines.map((l) => ({
      id: l.id || genLineId(),
      startPointId: l.startPointId,
      endPointId: l.endPointId,
    }));
    const polygons: CadPolygon[] = payload.surfaces.map((sf) => ({
      id: sf.id || genPolygonId(),
      pointIds: sf.pointIds,
      fill: nextFill(),
    }));
    const rects: CadRect[] = (payload.rects ?? []).map((r) => ({
      id: r.id || genRectId(),
      x: r.x,
      y: r.y,
      width: r.width,
      height: r.height,
    }));
    const circles: CadCircle[] = (payload.circles ?? []).map((c) => ({
      id: c.id || genCircleId(),
      cx: c.cx,
      cy: c.cy,
      radius: c.radius,
    }));
    const texts: CadText[] = (payload.texts ?? []).map((t) => ({
      id: t.id || genTextId(),
      x: t.x,
      y: t.y,
      text: t.text,
      fontSize: 14,
    }));

    set({
      points,
      lines,
      polygons,
      rects,
      circles,
      texts,
      floorCount: payload.floor_count,
      buildingHeightM: payload.building_height_m,
      scale: payload.scale,
      selectedId: null,
      selectedIds: [],
      pendingPointIds: [],
      pendingOrigin: null,
      undoStack: [...s.undoStack, snap].slice(-MAX_UNDO_STACK),
      redoStack: [],
    });
  },

  setAnalysis: (isAnalyzing: boolean, analysisMarkers: Array<{ id: string; x: number; y: number; severity: "high" | "med" | "low"; desc: string }>) => {
    set({ isAnalyzing, analysisMarkers });
  },

  resetCanvas: () => {
    const s = get();
    const snap = takeSnapshot(s);
    set({
      points: [],
      lines: [],
      polygons: [],
      rects: [],
      circles: [],
      texts: [],
      selectedId: null,
      selectedIds: [],
      pendingPointIds: [],
      pendingOrigin: null,
      analysisMarkers: [],
      isAnalyzing: false,
      undoStack: [...s.undoStack, snap].slice(-MAX_UNDO_STACK),
      redoStack: [],
    });
  },
}));
