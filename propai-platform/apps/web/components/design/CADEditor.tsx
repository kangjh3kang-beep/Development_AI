"use client";

import React, { useState, useCallback, useRef, useEffect, useMemo } from "react";
import type Konva from "konva";
import { apiClient, ApiClientError } from "@/lib/api-client";
import {
  type CadShape,
  type CadShapePoint,
  type LayerKey,
  type DxfImportResult,
  LAYER_KEYS,
  LAYER_LABELS,
  findOutline,
  outlineRing,
  rectToRing,
  shapesToLegacy,
  legacyToShapes,
  sanitizeShapes,
  snapToVertex,
  ringAreaPx,
  ringBbox,
  newShapeId,
  dxfImportToShapes,
} from "@/lib/cad-shapes";

// React 19 Shim for React 18-era libraries (Proxy-based)
const applyShim = () => {
  if (typeof window !== "undefined" && React.version.startsWith("19")) {
    const anyReact = React as any;
    const client = anyReact.__CLIENT_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED;
    const secret = anyReact.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED;

    if (client && secret && !secret.ReactCurrentOwner) {
      try {
        const proxy = new Proxy(secret, {
          get: (target, prop) => {
            if (prop === "ReactCurrentOwner") return client.ReactCurrentOwner;
            if (prop === "ReactCurrentDispatcher") return client.ReactCurrentDispatcher;
            if (prop === "ReactCurrentBatchConfig") return client.ReactCurrentBatchConfig;
            return target[prop];
          },
        });
        Object.defineProperty(anyReact, "__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED", {
          get: () => proxy,
          configurable: true,
        });
      } catch {
        if (client.ReactCurrentOwner && !secret.ReactCurrentOwner) {
          secret.ReactCurrentOwner = client.ReactCurrentOwner;
        }
      }
    } else if (client && !secret) {
      Object.defineProperty(anyReact, "__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED", {
        get: () => client,
        configurable: true,
      });
    }
  }
};

/* ───────────── 타입 ───────────── */
type DesignPoint = CadShapePoint;
interface ComplianceViolation {
  type: string; message: string; severity: "error" | "warning";
  current_value: number; limit_value: number;
}
type Tool = "select" | "point" | "poly" | "line" | "rect" | "text" | "dim" | "delete";

/** 편집 중 면적·세대 변경을 부모(스튜디오)에 통지하는 메트릭 페이로드. */
export interface CADEditorMetrics {
  /** 건축면적(㎡) — 신발끈 면적. */
  footprintSqm: number;
  /** 연면적(㎡) = 건축면적 × 층수. */
  gfaSqm: number;
  floorCount: number;
  /** bbox 역산 건물 폭(m). */
  buildingWidthM: number;
  /** bbox 역산 건물 깊이(m). */
  buildingDepthM: number;
  floorHeightM: number;
  bcrPct: number | null;
  farPct: number | null;
}

interface CADEditorProps {
  projectId: string;
  apiBaseUrl?: string;
  gridSize?: number;
  snapGrid?: boolean;
  // 실제 기하·법규 연동(부모 spec에서 전달)
  siteAreaSqm?: number;
  initialWidthM?: number;
  initialDepthM?: number;
  initialFloors?: number;
  initialFloorHeightM?: number;
  zoneCode?: string;
  scalePxPerM?: number;     // 기본 10 (px per meter)
  maxBcrPct?: number;
  maxFarPct?: number;
  maxHeightM?: number;
  /** 면적·세대(건축면적·연면적·매스치수) 변경을 부모에 통지(라이브 수지 연동용). */
  onMetricsChange?: (m: CADEditorMetrics) => void;
}

/* ───────────── 상수 ───────────── */
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DEBOUNCE_MS = Number(process.env.NEXT_PUBLIC_COMPLIANCE_DEBOUNCE_MS ?? "500");
const GRID_STEP = 20; // px
const VERTEX_SNAP_PX = 10; // 정점 스냅 반경

// 레이어별 색(CAD2.0). outline은 법규 위반 시 rose로 덮어쓴다.
const LAYER_COLORS: Record<LayerKey, string> = {
  outline: "#2dd4bf",
  wall: "#60a5fa",
  dim: "#f59e0b",
  note: "#a78bfa",
};
const LAYER_FILLS: Record<LayerKey, string> = {
  outline: "rgba(45,212,191,0.10)",
  wall: "rgba(96,165,250,0.08)",
  dim: "rgba(245,158,11,0.08)",
  note: "rgba(167,139,250,0.08)",
};

// 용도지역 코드/명칭 → 법정 상한(개략). 클라이언트 힌트용일 뿐,
// 권위 검증은 백엔드 building-compliance API가 담당(할루시네이션 가드).
const ZONE_LIMITS: Record<string, { bcr: number; far: number; height: number }> = {
  "1R": { bcr: 50, far: 100, height: 0 },
  "2R": { bcr: 60, far: 200, height: 0 },
  "3R": { bcr: 50, far: 250, height: 0 },
  준주거: { bcr: 70, far: 400, height: 0 },
  일반상업: { bcr: 80, far: 800, height: 0 },
  근린상업: { bcr: 70, far: 600, height: 0 },
  제1종전용주거: { bcr: 50, far: 100, height: 0 },
  제2종전용주거: { bcr: 50, far: 150, height: 0 },
  제1종일반주거: { bcr: 60, far: 150, height: 0 },
  제2종일반주거: { bcr: 60, far: 200, height: 0 },
  제3종일반주거: { bcr: 50, far: 250, height: 0 },
};

function resolveLimits(zone?: string): { bcr: number; far: number; height: number } | null {
  if (!zone) return null;
  if (ZONE_LIMITS[zone]) return ZONE_LIMITS[zone];
  for (const key of Object.keys(ZONE_LIMITS)) {
    if (zone.includes(key)) return ZONE_LIMITS[key];
  }
  return null;
}

let _idSeq = 100;
const nextId = () => `p${++_idSeq}`;

/* ───────────── 컴포넌트 ───────────── */
export default function CADEditor({
  projectId,
  apiBaseUrl = API_BASE,
  gridSize = GRID_STEP,
  snapGrid = true,
  siteAreaSqm,
  initialWidthM,
  initialDepthM,
  initialFloors = 5,
  initialFloorHeightM = 3,
  zoneCode,
  scalePxPerM = 10,
  maxBcrPct,
  maxFarPct,
  maxHeightM,
  onMetricsChange,
}: CADEditorProps) {
  /* ── CAD2.0 다중 도형 — 레이어 기반 shapes[]. 외곽 ring은 findOutline에서 파생 ── */
  const [shapes, setShapes] = useState<CadShape[]>([]);
  const [activeLayer, setActiveLayer] = useState<LayerKey>("outline");
  const [visibleLayers, setVisibleLayers] = useState<Record<LayerKey, boolean>>({
    outline: true, wall: true, dim: true, note: true,
  });
  const [violations, setViolations] = useState<ComplianceViolation[]>([]);
  const [isChecking, setIsChecking] = useState(false);
  const [floorCount, setFloorCount] = useState(initialFloors);
  const [buildingHeight, setBuildingHeight] = useState(
    Math.round((initialFloors || 5) * (initialFloorHeightM || 3)),
  );
  const [isReady, setIsReady] = useState(false);
  const [rk, setRK] = useState<any>(null);
  const [rkError, setRkError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [loadedVersion, setLoadedVersion] = useState<number | null>(null);
  const [loadState, setLoadState] = useState<"loading" | "done">("loading");
  const [tool, setTool] = useState<Tool>("select");
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [draft, setDraft] = useState<DesignPoint[]>([]); // POLY/LINE/RECT 임시 정점
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 0, h: 0 });
  const seededRef = useRef(false);

  // ── DXF 가져오기(POST import-dxf) 상태 + 정직 토스트 ──
  const [importState, setImportState] = useState<"idle" | "loading">("idle");
  const [importMsg, setImportMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const importMsgTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── undo/redo 스냅샷 스택(use-cad-store MAX 50 패턴 이식) ──
  // 편집 상태(다중 도형 shapes + 층수/높이)를 스냅샷으로 쌓아 Ctrl+Z/Ctrl+Shift+Z로 복원.
  type EditSnapshot = { shapes: CadShape[]; floorCount: number; buildingHeight: number };
  const MAX_HISTORY = 50;
  const undoStackRef = useRef<EditSnapshot[]>([]);
  const redoStackRef = useRef<EditSnapshot[]>([]);
  const skipHistoryRef = useRef(false); // undo/redo 적용 중에는 새 스냅샷 push 금지
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);

  // 편집본 DXF 다운로드 상태(저장본 없으면 404 → 안내)
  const [dxfState, setDxfState] = useState<"idle" | "loading" | "need-save" | "error">("idle");

  // 최초 1회 도움말 칩(편집기 진입 시 1회만 노출)
  const [showHelp, setShowHelp] = useState(false);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const limits = useMemo(() => {
    const zl = resolveLimits(zoneCode);
    const zlHeight = zl?.height && zl.height > 0 ? zl.height : null;
    return {
      bcr: maxBcrPct ?? zl?.bcr ?? null,
      far: maxFarPct ?? zl?.far ?? null,
      height: maxHeightM ?? zlHeight,
    };
  }, [zoneCode, maxBcrPct, maxFarPct, maxHeightM]);

  /* ── 외곽 ring 파생(metrics/매스치수/법규체크의 단일 기준 — 기존 호출부 무수정) ── */
  const outlineShape = useMemo(() => findOutline(shapes), [shapes]);
  const ring = useMemo(() => outlineRing(outlineShape), [outlineShape]);

  /* ── 스냅 ── */
  const snap = useCallback(
    (v: number) => (snapGrid ? Math.round(v / gridSize) * gridSize : v),
    [snapGrid, gridSize],
  );

  /* ── undo/redo: 변경 직전 현재 상태를 undo 스택에 push(use-cad-store MAX 50 이식) ── */
  const commitSnapshot = useCallback(() => {
    if (skipHistoryRef.current) return;
    undoStackRef.current.push({ shapes, floorCount, buildingHeight });
    if (undoStackRef.current.length > MAX_HISTORY) undoStackRef.current.shift();
    redoStackRef.current = []; // 새 편집 → redo 무효화
    setCanUndo(true);
    setCanRedo(false);
  }, [shapes, floorCount, buildingHeight]);

  /* ── 면적·BCR·FAR 라이브 계산(신발끈 공식 — cad-shapes 유틸) ── */
  const metrics = useMemo(() => {
    if (ring.length < 3) return { areaM2: 0, bcr: null as number | null, far: null as number | null, gfa: 0 };
    const areaPx = ringAreaPx(ring);
    const areaM2 = areaPx / (scalePxPerM * scalePxPerM);
    const gfa = areaM2 * floorCount;
    const bcr = siteAreaSqm && siteAreaSqm > 0 ? (areaM2 / siteAreaSqm) * 100 : null;
    const far = siteAreaSqm && siteAreaSqm > 0 ? (gfa / siteAreaSqm) * 100 : null;
    return { areaM2, bcr, far, gfa };
  }, [ring, scalePxPerM, floorCount, siteAreaSqm]);

  /* ── 매스치수 bbox 역산(C2): 외곽 ring의 경계상자를 px→m로 환산 ── */
  const massDims = useMemo(() => {
    if (ring.length < 3) return { widthM: 0, depthM: 0 };
    const bb = ringBbox(ring);
    if (!bb) return { widthM: 0, depthM: 0 };
    return {
      widthM: bb.widthPx / scalePxPerM,
      depthM: bb.heightPx / scalePxPerM,
    };
  }, [ring, scalePxPerM]);

  const floorHeightM = initialFloorHeightM || 3;

  /* ── 면적·세대 변경을 부모에 통지(라이브 수지 연동). 읽기 전용 — 부모 결정. ── */
  useEffect(() => {
    if (!onMetricsChange) return;
    if (ring.length < 3) return;
    onMetricsChange({
      footprintSqm: metrics.areaM2,
      gfaSqm: metrics.gfa,
      floorCount,
      buildingWidthM: Math.round(massDims.widthM * 100) / 100,
      buildingDepthM: Math.round(massDims.depthM * 100) / 100,
      floorHeightM,
      bcrPct: metrics.bcr,
      farPct: metrics.far,
    });
  }, [metrics, floorCount, massDims, floorHeightM, onMetricsChange, ring.length]);

  // 법규 초과 여부(클라 힌트)
  const overBcr = limits.bcr != null && metrics.bcr != null && metrics.bcr > limits.bcr + 0.5;
  const overFar = limits.far != null && metrics.far != null && metrics.far > limits.far + 0.5;
  const overHeight = limits.height != null && buildingHeight > limits.height;
  const hasViolationHint = overBcr || overFar || overHeight;

  /* ── 법규 검증 API(권위 검증, 디바운스) ── */
  const checkCompliance = useCallback(
    async (pts: DesignPoint[]) => {
      if (pts.length < 3) return;
      setIsChecking(true);
      try {
        const lines = pts.map((p, i) => ({
          id: `l${i}`, start_point_id: p.id, end_point_id: pts[(i + 1) % pts.length].id,
        }));
        const body = {
          project_id: projectId,
          design: {
            points: pts.map((p) => ({ id: p.id, x: p.x, y: p.y })),
            lines,
            surfaces: [{ id: "s1", point_ids: pts.map((p) => p.id) }],
            floor_count: floorCount,
            building_height_m: buildingHeight,
            scale: scalePxPerM,
          },
        };
        const res = await fetch(`${apiBaseUrl}/api/v1/building-compliance/check`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          signal: AbortSignal.timeout(20000),
        });
        const data = await res.json();
        setViolations(data.violations ?? []);
      } catch {
        /* 검증 실패는 무시(클라 힌트로 대체) */
      } finally {
        setIsChecking(false);
      }
    },
    [projectId, apiBaseUrl, floorCount, buildingHeight, scalePxPerM],
  );

  const debouncedCheck = useCallback(
    (pts: DesignPoint[]) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => checkCompliance(pts), DEBOUNCE_MS);
    },
    [checkCompliance],
  );

  /* ── 외곽 ring 변경을 shapes에 반영(외곽 없으면 생성, rect 외곽은 polygon 승격) ── */
  const setOutlineRing = useCallback(
    (updater: (prev: DesignPoint[]) => DesignPoint[]) => {
      setShapes((prev) => {
        const o = findOutline(prev);
        const cur = outlineRing(o);
        const nextRing = updater(cur);
        if (nextRing === cur) return prev;
        if (o) {
          return prev.map((s) =>
            s.id === o.id ? { ...s, kind: "polygon" as const, points: nextRing } : s,
          );
        }
        return [
          { id: newShapeId("outline"), kind: "polygon" as const, layer: "outline" as const, points: nextRing },
          ...prev,
        ];
      });
    },
    [],
  );

  /* ── undo: undo 스택에서 직전 상태 복원, 현재 상태는 redo로 ── */
  const undo = useCallback(() => {
    const prev = undoStackRef.current.pop();
    if (!prev) return;
    redoStackRef.current.push({ shapes, floorCount, buildingHeight });
    skipHistoryRef.current = true;
    setShapes(prev.shapes);
    setFloorCount(prev.floorCount);
    setBuildingHeight(prev.buildingHeight);
    setTimeout(() => { skipHistoryRef.current = false; }, 0);
    setCanUndo(undoStackRef.current.length > 0);
    setCanRedo(true);
    debouncedCheck(outlineRing(findOutline(prev.shapes)));
  }, [shapes, floorCount, buildingHeight, debouncedCheck]);

  /* ── redo: redo 스택에서 상태 재적용, 현재 상태는 undo로 ── */
  const redo = useCallback(() => {
    const next = redoStackRef.current.pop();
    if (!next) return;
    undoStackRef.current.push({ shapes, floorCount, buildingHeight });
    if (undoStackRef.current.length > MAX_HISTORY) undoStackRef.current.shift();
    skipHistoryRef.current = true;
    setShapes(next.shapes);
    setFloorCount(next.floorCount);
    setBuildingHeight(next.buildingHeight);
    setTimeout(() => { skipHistoryRef.current = false; }, 0);
    setCanUndo(true);
    setCanRedo(redoStackRef.current.length > 0);
    debouncedCheck(outlineRing(findOutline(next.shapes)));
  }, [shapes, floorCount, buildingHeight, debouncedCheck]);

  /* ── 키보드 단축키: Ctrl+Z(undo) / Ctrl+Shift+Z(redo) ── */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      const key = e.key.toLowerCase();
      if (key !== "z") return;
      e.preventDefault();
      if (e.shiftKey) redo();
      else undo();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo, redo]);

  /* ── 저장(design_versions 영속) ── */
  const handleSave = useCallback(async () => {
    if (ring.length < 3) return;
    setSaveStatus("saving");
    try {
      // CAD2.0: 외곽 ring을 기존 계약(points/lines/surfaces)으로 파생해 동봉
      // — 기존 소비자(export-edited-dxf·building-compliance·GLB 매스)는 무수정.
      const legacy = shapesToLegacy(shapes);
      // apiClient 사용 — Authorization 헤더·401 자동 갱신을 일관 처리(직접 localStorage 토큰 read 금지).
      // C2: ring bbox 역산 매스치수(building_width/depth_m) + floor_height_m 동봉(GLB 12×9 폴백 해소).
      // export-edited-dxf가 vector_data.scale을 소비하므로 scale(px/m)도 함께 영속.
      const d = await apiClient.post<{ status?: string }>(
        `/design/${encodeURIComponent(projectId)}/drawings/save`,
        {
          body: {
            drawing_code: "CAD-EDIT",
            drawing_type: "평면도",
            points: legacy.points,
            lines: legacy.lines,
            surfaces: legacy.surfaces,
            floor_count: floorCount,
            building_height_m: buildingHeight,
            // C2 신규 필드(WP-16 CADSaveRequest) — 편집본 매스치수
            building_width_m: Math.round(massDims.widthM * 100) / 100 || undefined,
            building_depth_m: Math.round(massDims.depthM * 100) / 100 || undefined,
            floor_height_m: floorHeightM,
            // CAD2.0 다중 도형(additive 신규 키) — 구버전 백엔드는 무시해도 안전.
            shapes,
            // vector_data는 백엔드가 그대로 영속하므로 shapes 복원 경로를 보장(scale 키는 기존 계약 유지).
            vector_data: { scale: scalePxPerM, shapes },
          },
          timeoutMs: 30000,
        },
      );
      setSaveStatus("saved");
      const m = /v(\d+)/.exec(d?.status || "");
      if (m) setLoadedVersion(Number(m[1]));
      setTimeout(() => setSaveStatus("idle"), 2500);
    } catch {
      setSaveStatus("error");
      setTimeout(() => setSaveStatus("idle"), 3000);
    }
  }, [projectId, shapes, ring.length, floorCount, buildingHeight, massDims, floorHeightM, scalePxPerM]);

  /* ── 편집본 DXF 다운로드(GET export-edited-dxf) ──
     저장본을 ParametricCADService.create_dxf_from_edited_points로 변환한 정식 DXF(LWPOLYLINE+DIMENSION).
     DXF는 UTF-8 텍스트라 apiClient.get이 { message } 로 회신(바이너리 손상 없음). 404면 "먼저 저장하세요". */
  const downloadEditedDxf = useCallback(async () => {
    setDxfState("loading");
    try {
      const payload = await apiClient.get<{ message?: string }>(
        `/design/${encodeURIComponent(projectId)}/drawings/export-edited-dxf`,
        { timeoutMs: 30000 },
      );
      const dxfText = typeof payload?.message === "string" ? payload.message : "";
      if (!dxfText) {
        setDxfState("error");
        setTimeout(() => setDxfState("idle"), 3000);
        return;
      }
      const url = URL.createObjectURL(new Blob([dxfText], { type: "application/dxf" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `propai_${projectId}_편집본.dxf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setDxfState("idle");
    } catch (err) {
      // 404 = 저장본 없음 → "먼저 저장하세요" 안내. 그 외는 일반 오류.
      if (err instanceof ApiClientError && err.status === 404) {
        setDxfState("need-save");
        setTimeout(() => setDxfState("idle"), 3500);
      } else {
        setDxfState("error");
        setTimeout(() => setDxfState("idle"), 3000);
      }
    }
  }, [projectId]);

  /* ── DXF 가져오기 토스트(정직 표기 — 무시 엔티티·단위는 응답에 있을 때만 수치, 없으면 '정보 없음') ── */
  const showImportMsg = useCallback((kind: "ok" | "error", text: string) => {
    if (importMsgTimerRef.current) clearTimeout(importMsgTimerRef.current);
    setImportMsg({ kind, text });
    importMsgTimerRef.current = setTimeout(() => setImportMsg(null), 7000);
  }, []);
  useEffect(() => () => {
    if (importMsgTimerRef.current) clearTimeout(importMsgTimerRef.current);
  }, []);

  /* ── DXF 가져오기(POST import-dxf → shapes 변환 → 교체/추가 confirm → 스냅샷 push) ── */
  const triggerImport = useCallback(() => { fileInputRef.current?.click(); }, []);
  const handleImportFile = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      e.target.value = ""; // 같은 파일 재선택 허용
      if (!file) return;
      setImportState("loading");
      try {
        const fd = new FormData();
        fd.append("file", file, file.name);
        const res = await apiClient.post<DxfImportResult>(
          `/design/${encodeURIComponent(projectId)}/drawings/import-dxf`,
          { body: fd, timeoutMs: 60000 },
        );
        // polyline→polygon/line 매핑, main_outline_index→outline 레이어(cad-shapes 변환)
        const imported = dxfImportToShapes(res, { scalePxPerM });
        if (imported.length === 0) {
          showImportMsg("error", "가져올 수 있는 폴리라인이 없습니다(빈 변환 결과).");
          return;
        }
        const replace =
          shapes.length === 0
            ? true
            : window.confirm("가져온 도형으로 기존 도형을 교체할까요?\n[확인] 교체 · [취소] 기존 도형에 추가");
        commitSnapshot(); // 교체/추가 전 상태를 undo 스택에 push
        let appendedNote = "";
        let nextShapes: CadShape[];
        if (replace) {
          nextShapes = imported;
        } else {
          // 추가 모드: 기존 외곽이 있으면 가져온 외곽은 벽체로 강등(외곽 이중화 방지 — 정직 고지)
          const hasOutline = findOutline(shapes) != null;
          const adjusted = hasOutline
            ? imported.map((s) =>
                s.layer === "outline" ? { ...s, layer: "wall" as LayerKey } : s,
              )
            : imported;
          if (hasOutline && imported.some((s) => s.layer === "outline")) {
            appendedNote = " · 기존 외곽 유지(가져온 외곽은 벽체 레이어로 추가)";
          }
          nextShapes = [...shapes, ...adjusted];
        }
        setShapes(nextShapes);
        seededRef.current = true;
        setSelectedIdx(null);
        const newRing = outlineRing(findOutline(nextShapes));
        if (newRing.length >= 3) debouncedCheck(newRing);
        // 정직 표기: ignored/unit은 백엔드 응답에 있을 때만 수치로 표기
        const rec = res as Record<string, unknown>;
        const ignoredRaw = rec.ignored_count ?? rec.ignored ?? rec.ignored_entities;
        const ignoredNum =
          typeof ignoredRaw === "number" ? ignoredRaw
            : Array.isArray(ignoredRaw) ? ignoredRaw.length : null;
        const unitTxt =
          typeof res.unit === "string" && res.unit.trim()
            ? `단위 ${res.unit.trim()}`
            : "단위 정보 없음(1단위=1m 가정)";
        const skippedLocal =
          (Array.isArray(res.polylines) ? res.polylines.length : 0) - imported.length;
        showImportMsg(
          "ok",
          `도형 ${imported.length}개 ${replace ? "교체" : "추가"} · ${unitTxt}` +
            (ignoredNum != null && ignoredNum > 0 ? ` · 미지원 엔티티 ${ignoredNum}개 무시` : "") +
            (skippedLocal > 0 ? ` · 변환 불가 폴리라인 ${skippedLocal}개 제외` : "") +
            appendedNote,
        );
      } catch (err) {
        if (err instanceof ApiClientError && err.status === 404) {
          showImportMsg("error", "DXF 가져오기 API를 사용할 수 없습니다(404). 백엔드 배포를 확인하세요.");
        } else {
          showImportMsg("error", "DXF 가져오기에 실패했습니다. 파일 형식(DXF)을 확인해 주세요.");
        }
      } finally {
        setImportState("idle");
      }
    },
    [projectId, scalePxPerM, shapes, commitSnapshot, debouncedCheck, showImportMsg],
  );

  /* ── 저장본 로드(shapes 우선 복원, 없으면 v1 → outline 승격) — apiClient(인증 첨부)로 호출 ── */
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const d = await apiClient.get<{
          saved?: boolean; version?: number | null;
          data?: {
            points?: any[]; surfaces?: any[]; floor_count?: number; building_height_m?: number;
            shapes?: any[]; vector_data?: { shapes?: any[] };
          };
        }>(`/design/${encodeURIComponent(projectId)}/drawings/load`, { timeoutMs: 20000 });
        if (!cancelled && d?.saved && d.data) {
          // CAD2.0 shapes 우선(top-level 또는 vector_data 경유), 없으면 v1 points+surfaces 마이그레이션
          const vd = d.data.vector_data;
          const rawShapes = Array.isArray(d.data.shapes)
            ? d.data.shapes
            : vd && Array.isArray(vd.shapes)
              ? vd.shapes
              : null;
          let restored: CadShape[] = rawShapes ? sanitizeShapes(rawShapes) : [];
          if (restored.length === 0) restored = legacyToShapes(d.data);
          if (restored.length > 0) {
            setShapes(restored);
            seededRef.current = true;
          }
          if (typeof d.data.floor_count === "number") setFloorCount(d.data.floor_count);
          if (typeof d.data.building_height_m === "number") setBuildingHeight(d.data.building_height_m);
          setLoadedVersion(d.version ?? null);
        }
      } catch {
        /* 로드 실패(401·미저장 등) 무시 — 기본 도형으로 시드 */
      } finally {
        if (!cancelled) setLoadState("done");
      }
    })();
    return () => { cancelled = true; };
  }, [projectId]);

  /* ── 최초 1회 도움말 칩(편집기 진입 시 1회만, localStorage 플래그) ── */
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      if (!window.localStorage.getItem("propai_cad_help_seen")) {
        setShowHelp(true);
      }
    } catch {
      /* localStorage 차단 환경 — 칩 생략 */
    }
  }, []);
  const dismissHelp = useCallback(() => {
    setShowHelp(false);
    try { window.localStorage.setItem("propai_cad_help_seen", "1"); } catch { /* noop */ }
  }, []);

  /* ── react-konva 로드 ── */
  useEffect(() => {
    applyShim();
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const mod = require("react-konva");
      // 일부 번들러 경로에서 named export가 default 아래로 들어갈 수 있어 정규화.
      const resolved = mod?.Stage ? mod : (mod?.default?.Stage ? mod.default : mod);
      if (!resolved?.Stage) {
        // require는 성공했으나 Stage/Layer 등이 누락된 경우(예: optimizePackageImports
        // 배럴 재작성으로 깨진 모듈) — 무증상 빈 캔버스가 되지 않도록 명시 실패 처리.
        console.error(
          "[CADEditor] react-konva exports 누락 — keys:",
          Object.keys(mod || {}),
        );
        setRkError("CAD 엔진(Konva) 모듈을 불러오지 못했습니다. 페이지를 새로고침해 주세요.");
      } else {
        setRK(resolved);
      }
    } catch (e) {
      console.error("[CADEditor] react-konva 로드 실패:", e);
      setRkError("CAD 엔진을 초기화하지 못했습니다. 페이지를 새로고침해 주세요.");
    }
    setIsReady(true);
  }, []);

  /* ── 컨테이너 크기 측정(반응형 캔버스) ──
     deps에 rk 포함: 캔버스 div는 react-konva 로드(rk) 후에야 마운트되므로 그때 재측정해야 한다.
     초기 레이아웃이 0으로 잡혀 Stage가 안 뜨던 문제: rAF로 size>0 될 때까지 재시도(+ResizeObserver). */
  useEffect(() => {
    if (!isReady || !rk) return;
    const el = containerRef.current;
    if (!el) return;
    let raf = 0;
    let tries = 0;
    const measure = () => {
      const w = el.clientWidth;
      const h = el.clientHeight;
      if (w > 0 && h > 0) {
        setSize({ w, h });
        return;
      }
      if (tries++ < 90) raf = requestAnimationFrame(measure); // 레이아웃 확정까지 ~1.5s 재시도
    };
    measure();
    const ro = new ResizeObserver((entries) => {
      const cr = entries[0]?.contentRect;
      if (cr && cr.width > 0 && cr.height > 0) {
        setSize({ w: Math.round(cr.width), h: Math.round(cr.height) });
      }
    });
    ro.observe(el);
    const onResize = () => {
      if (el.clientWidth > 0 && el.clientHeight > 0) {
        setSize({ w: el.clientWidth, h: el.clientHeight });
      }
    };
    window.addEventListener("resize", onResize);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      window.removeEventListener("resize", onResize);
    };
  }, [isReady, rk]);

  /* ── 기본 도형 시드: 크기 측정 완료 + 로드 완료 + 미시드일 때, 실제 건물치수 외곽을 중앙배치 ── */
  useEffect(() => {
    if (seededRef.current) return;
    if (loadState !== "done") return;
    if (size.w < 50 || size.h < 50) return;
    if (shapes.length > 0) { seededRef.current = true; return; }
    const wM = initialWidthM && initialWidthM > 0 ? initialWidthM : 30;
    const dM = initialDepthM && initialDepthM > 0 ? initialDepthM : 20;
    let wPx = wM * scalePxPerM;
    let dPx = dM * scalePxPerM;
    // 캔버스보다 크면 80% 안에 맞춰 축소(보기용 — 비율 유지). 단 면적계산은 px→m 역산이라 영향 없도록 scale은 유지.
    const cx = size.w / 2;
    const cy = size.h / 2;
    const maxW = size.w * 0.7;
    const maxH = size.h * 0.7;
    const k = Math.min(1, maxW / wPx, maxH / dPx);
    wPx *= k; dPx *= k;
    const seed: DesignPoint[] = [
      { id: nextId(), x: snap(cx - wPx / 2), y: snap(cy - dPx / 2) },
      { id: nextId(), x: snap(cx + wPx / 2), y: snap(cy - dPx / 2) },
      { id: nextId(), x: snap(cx + wPx / 2), y: snap(cy + dPx / 2) },
      { id: nextId(), x: snap(cx - wPx / 2), y: snap(cy + dPx / 2) },
    ];
    seededRef.current = true;
    setShapes([{ id: newShapeId("outline"), kind: "polygon", layer: "outline", points: seed }]);
    debouncedCheck(seed);
  }, [loadState, size, shapes.length, initialWidthM, initialDepthM, scalePxPerM, snap, debouncedCheck]);

  /* ── 외곽 정점 드래그(라이브) ── */
  // 드래그 시작 시 1회 스냅샷(이동 전 상태) → undo로 정확 복원.
  const handleDragStart = useCallback(() => { commitSnapshot(); }, [commitSnapshot]);
  const handleDragMove = useCallback(
    (idx: number, e: Konva.KonvaEventObject<DragEvent>) => {
      const nx = snap(e.target.x());
      const ny = snap(e.target.y());
      e.target.position({ x: nx, y: ny });
      setOutlineRing((prev) => {
        if (!prev[idx]) return prev;
        const next = [...prev];
        next[idx] = { ...next[idx], x: nx, y: ny };
        return next;
      });
    },
    [snap, setOutlineRing],
  );
  const handleDragEnd = useCallback(
    () => {
      setShapes((prev) => {
        debouncedCheck(outlineRing(findOutline(prev)));
        return prev;
      });
    },
    [debouncedCheck],
  );

  /* ── 도형 전체 이동(SELECT 도구, 비외곽 도형 — Group 드래그 후 위치 커밋) ── */
  const moveShapeBy = useCallback(
    (shapeId: string, dx: number, dy: number) => {
      const sx = snap(dx);
      const sy = snap(dy);
      if (sx === 0 && sy === 0) return;
      setShapes((prev) =>
        prev.map((s) =>
          s.id === shapeId
            ? { ...s, points: s.points.map((p) => ({ ...p, x: p.x + sx, y: p.y + sy })) }
            : s,
        ),
      );
    },
    [snap],
  );

  /* ── 도형 삭제(DELETE 도구, 비외곽 도형) ── */
  const deleteShape = useCallback(
    (shapeId: string) => {
      commitSnapshot();
      setShapes((prev) => prev.filter((s) => s.id !== shapeId));
    },
    [commitSnapshot],
  );

  /* ── 전체삭제(confirm) ── */
  const clearAll = useCallback(() => {
    if (shapes.length === 0 && draft.length === 0) return;
    if (!window.confirm("모든 도형을 삭제할까요? (Ctrl+Z로 되돌릴 수 있습니다)")) return;
    commitSnapshot();
    setShapes([]);
    setDraft([]);
    setSelectedIdx(null);
    setViolations([]);
  }, [shapes.length, draft.length, commitSnapshot]);

  /* ── 엣지 중점에 정점 삽입(POINT 도구 — 외곽 전용) ── */
  const insertVertexAt = useCallback(
    (edgeIdx: number) => {
      commitSnapshot(); // 삽입 전 스냅샷(undo 대상)
      setOutlineRing((prev) => {
        const a = prev[edgeIdx];
        const b = prev[(edgeIdx + 1) % prev.length];
        if (!a || !b) return prev;
        const mid: DesignPoint = { id: nextId(), x: snap((a.x + b.x) / 2), y: snap((a.y + b.y) / 2) };
        const next = [...prev];
        next.splice(edgeIdx + 1, 0, mid);
        debouncedCheck(next);
        return next;
      });
    },
    [snap, debouncedCheck, commitSnapshot, setOutlineRing],
  );

  /* ── 외곽 정점 삭제(DELETE 도구) ── */
  const deleteVertex = useCallback(
    (idx: number) => {
      commitSnapshot(); // 삭제 전 스냅샷(undo 대상)
      setOutlineRing((prev) => {
        if (prev.length <= 3) return prev; // 최소 삼각형 유지
        const next = prev.filter((_, i) => i !== idx);
        debouncedCheck(next);
        return next;
      });
      setSelectedIdx(null);
    },
    [debouncedCheck, commitSnapshot, setOutlineRing],
  );

  /* ── 스테이지 클릭(POLY/LINE/RECT/TEXT 작도 — 기존 정점에 스냅) ── */
  const handleStageClick = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      if (tool !== "poly" && tool !== "line" && tool !== "rect" && tool !== "text") return;
      const stage = e.target.getStage();
      const pos = stage?.getPointerPosition();
      if (!pos) return;
      const hit = snapToVertex(pos.x, pos.y, shapes, VERTEX_SNAP_PX);
      const x = hit ? hit.x : snap(pos.x);
      const y = hit ? hit.y : snap(pos.y);
      if (tool === "text") {
        const t = window.prompt("주석 텍스트를 입력하세요", "");
        if (!t || !t.trim()) return;
        commitSnapshot();
        setShapes((prev) => [
          ...prev,
          {
            id: newShapeId("txt"),
            kind: "label",
            // 외곽 레이어에 텍스트는 의미 없음 → note로 보정
            layer: activeLayer === "outline" ? "note" : activeLayer,
            points: [{ id: nextId(), x, y }],
            text: t.trim(),
          },
        ]);
        return;
      }
      if (tool === "poly") {
        setDraft((prev) => [...prev, { id: nextId(), x, y }]);
        return;
      }
      // LINE·RECT: 2점 클릭으로 완성(첫 클릭 = 시작점, 둘째 클릭 = 완성)
      if (draft.length === 0) {
        setDraft([{ id: nextId(), x, y }]);
        return;
      }
      const a = draft[0];
      const b: DesignPoint = { id: nextId(), x, y };
      commitSnapshot();
      if (tool === "line") {
        setShapes((prev) => [
          ...prev,
          {
            id: newShapeId("ln"),
            kind: "line",
            layer: activeLayer === "outline" ? "wall" : activeLayer, // 외곽은 polygon 전용
            points: [a, b],
          },
        ]);
      } else {
        setShapes((prev) => [
          ...prev,
          {
            id: newShapeId("rc"),
            kind: "rect",
            layer: activeLayer === "outline" ? "wall" : activeLayer,
            points: [a, b],
          },
        ]);
      }
      setDraft([]);
    },
    [tool, snap, shapes, draft, activeLayer, commitSnapshot],
  );
  const finishPoly = useCallback(() => {
    if (draft.length >= 3) {
      commitSnapshot(); // 외곽 교체/다각형 추가 전 스냅샷(undo 대상)
      if (activeLayer === "outline") {
        // 외곽 레이어 활성 시: 기존 외곽 교체(기존 재작도 동작 유지)
        const next = draft;
        setOutlineRing(() => next);
        debouncedCheck(next);
      } else {
        setShapes((prev) => [
          ...prev,
          { id: newShapeId("pg"), kind: "polygon", layer: activeLayer, points: draft },
        ]);
      }
    }
    setDraft([]);
    setTool("select");
  }, [draft, activeLayer, debouncedCheck, commitSnapshot, setOutlineRing]);
  const cancelPoly = useCallback(() => { setDraft([]); setTool("select"); }, []);

  /* ── 렌더 게이트 ── */
  if (rkError) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-[#0a0f14] px-6 text-center text-white">
        <div className="flex flex-col items-center gap-3">
          <p className="text-sm font-bold text-rose-400">{rkError}</p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded-lg border border-teal-500/40 bg-teal-500/10 px-4 py-2 text-xs font-bold text-teal-300 hover:bg-teal-500/20"
          >
            새로고침
          </button>
        </div>
      </div>
    );
  }
  if (!isReady || !rk) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-[#0a0f14] text-white">
        <div className="flex flex-col items-center gap-4">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-teal-500 border-t-transparent" />
          <p className="text-xs font-black uppercase tracking-[0.2em] text-teal-400">CAD 엔진 초기화...</p>
        </div>
      </div>
    );
  }

  const { Stage, Layer, Group, Line, Circle, Text } = rk;

  const surfaceCoords = ring.flatMap((p) => [p.x, p.y]);
  const draftCoords = draft.flatMap((p) => [p.x, p.y]);
  const strokeColor = hasViolationHint ? "#f43f5e" : LAYER_COLORS.outline;
  const fillColor = hasViolationHint ? "rgba(244,63,94,0.10)" : LAYER_FILLS.outline;

  const edgeMidpoints = tool === "point" && visibleLayers.outline
    ? ring.map((p, i) => {
        const q = ring[(i + 1) % ring.length];
        return { i, x: (p.x + q.x) / 2, y: (p.y + q.y) / 2 };
      })
    : [];

  const fmt = (v: number | null, suffix = "") =>
    v == null ? "—" : `${v.toLocaleString(undefined, { maximumFractionDigits: 1 })}${suffix}`;

  const TOOLS: { key: Tool; label: string }[] = [
    { key: "select", label: "이동" },
    { key: "point", label: "정점추가" },
    { key: "poly", label: "다각형" },
    { key: "line", label: "선" },
    { key: "rect", label: "사각형" },
    { key: "text", label: "주석" },
    { key: "dim", label: "치수" },
    { key: "delete", label: "삭제" },
  ];

  const isDrawTool = tool === "poly" || tool === "line" || tool === "rect" || tool === "text";

  /* ── 비외곽 도형 렌더(레이어 색·표시 토글·SELECT 이동·DELETE 삭제) ── */
  const renderShape = (s: CadShape) => {
    if (s.layer === "outline" || !visibleLayers[s.layer]) return null;
    const color = LAYER_COLORS[s.layer];
    const fill = LAYER_FILLS[s.layer];
    let body: React.ReactNode = null;
    if (s.kind === "polygon" && s.points.length >= 3) {
      body = (
        <Line
          points={s.points.flatMap((p) => [p.x, p.y])}
          closed fill={fill} stroke={color} strokeWidth={2}
        />
      );
    } else if (s.kind === "rect" && s.points.length >= 2) {
      const corners = rectToRing(s);
      body = (
        <Line
          points={corners.flatMap((p) => [p.x, p.y])}
          closed fill={fill} stroke={color} strokeWidth={2}
        />
      );
    } else if (s.kind === "line" && s.points.length >= 2) {
      body = (
        <Line points={s.points.flatMap((p) => [p.x, p.y])} stroke={color} strokeWidth={2} />
      );
    } else if (s.kind === "circle" && s.points.length >= 1) {
      body = (
        <Circle x={s.points[0].x} y={s.points[0].y} radius={s.radius ?? 10} stroke={color} strokeWidth={2} />
      );
    } else if (s.kind === "label" && s.points.length >= 1) {
      body = (
        <Text
          x={s.points[0].x} y={s.points[0].y} text={s.text ?? ""}
          fontSize={12} fontStyle="700" fill={color} fontFamily="Inter, sans-serif"
        />
      );
    }
    if (!body) return null;
    return (
      <Group
        key={s.id}
        draggable={tool === "select"}
        onDragStart={handleDragStart}
        onDragEnd={(e: Konva.KonvaEventObject<DragEvent>) => {
          const pos = e.target.position();
          e.target.position({ x: 0, y: 0 });
          moveShapeBy(s.id, pos.x, pos.y);
        }}
        onClick={() => { if (tool === "delete") deleteShape(s.id); }}
        onTap={() => { if (tool === "delete") deleteShape(s.id); }}
        onMouseEnter={(e: Konva.KonvaEventObject<MouseEvent>) => {
          const c = e.target.getStage()?.container();
          if (c) c.style.cursor = tool === "delete" ? "not-allowed" : tool === "select" ? "move" : "default";
        }}
        onMouseLeave={(e: Konva.KonvaEventObject<MouseEvent>) => {
          const c = e.target.getStage()?.container();
          if (c) c.style.cursor = "default";
        }}
      >
        {body}
      </Group>
    );
  };

  return (
    <div className="relative h-full w-full overflow-hidden bg-[#0a0f14]">
      {/* ── Grid Layer (배경) ── */}
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.03)_1px,transparent_1px)] bg-[size:20px_20px]" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,#0a0f14_92%)]" />

      {/* ── Canvas (전체 영역 채움, ResizeObserver로 측정) ── */}
      <div
        ref={containerRef}
        className={`absolute inset-0 ${isDrawTool ? "cursor-crosshair" : tool === "delete" ? "cursor-not-allowed" : "cursor-default"}`}
      >
        {size.w > 0 && size.h > 0 && (
          <Stage width={size.w} height={size.h} onMouseDown={handleStageClick}>
            <Layer>
              {/* 비외곽 도형(벽체·치수·주석 레이어) */}
              {shapes.map(renderShape)}

              {/* 외곽 폴리곤 면(표시 토글) */}
              {visibleLayers.outline && surfaceCoords.length >= 6 && (
                <Line points={surfaceCoords} closed fill={fillColor} stroke={strokeColor} strokeWidth={2} />
              )}

              {/* 외곽 엣지 + 치수 라벨(DIM) */}
              {visibleLayers.outline && ring.map((p, i) => {
                const q = ring[(i + 1) % ring.length];
                const lenM = Math.hypot(q.x - p.x, q.y - p.y) / scalePxPerM;
                return (
                  <Group key={`e${i}`}>
                    <Line points={[p.x, p.y, q.x, q.y]} stroke={strokeColor} strokeWidth={3}
                      shadowBlur={8} shadowColor={strokeColor} />
                    {tool === "dim" && (
                      <Text
                        x={(p.x + q.x) / 2 - 18} y={(p.y + q.y) / 2 - 8}
                        text={`${lenM.toFixed(1)}m`} fontSize={11} fontStyle="700"
                        fill="#e2e8f0" fontFamily="Inter, sans-serif"
                      />
                    )}
                  </Group>
                );
              })}

              {/* 외곽 엣지 중점 삽입 핸들(POINT 도구) */}
              {edgeMidpoints.map((m) => (
                <Group key={`mid${m.i}`} onClick={() => insertVertexAt(m.i)} onTap={() => insertVertexAt(m.i)}>
                  <Circle x={m.x} y={m.y} radius={9} fill="rgba(96,165,250,0.25)" />
                  <Circle x={m.x} y={m.y} radius={5} fill="#60a5fa" />
                  <Text x={m.x - 3} y={m.y - 5} text="+" fontSize={11} fontStyle="900" fill="#fff" />
                </Group>
              ))}

              {/* 외곽 정점(드래그/선택/삭제) */}
              {visibleLayers.outline && ring.map((p, idx) => {
                const isSel = selectedIdx === idx;
                return (
                  <Group key={p.id}>
                    <Circle x={p.x} y={p.y} radius={13} fill={isSel ? "rgba(96,165,250,0.18)" : "rgba(45,212,191,0.10)"} />
                    <Circle
                      x={p.x} y={p.y} radius={7}
                      fill={isSel ? "#60a5fa" : "#ffffff"}
                      stroke={hasViolationHint ? "#f43f5e" : "#2dd4bf"} strokeWidth={3}
                      draggable={tool === "select"}
                      onDragStart={handleDragStart}
                      onDragMove={(e: Konva.KonvaEventObject<DragEvent>) => handleDragMove(idx, e)}
                      onDragEnd={handleDragEnd}
                      onClick={() => {
                        if (tool === "delete") deleteVertex(idx);
                        else setSelectedIdx(idx);
                      }}
                      onTap={() => { if (tool === "delete") deleteVertex(idx); else setSelectedIdx(idx); }}
                      onMouseEnter={(e: Konva.KonvaEventObject<MouseEvent>) => {
                        const c = e.target.getStage()?.container();
                        if (c) c.style.cursor = tool === "delete" ? "not-allowed" : tool === "select" ? "move" : "pointer";
                        (e.target as Konva.Circle).radius(9);
                      }}
                      onMouseLeave={(e: Konva.KonvaEventObject<MouseEvent>) => {
                        const c = e.target.getStage()?.container();
                        if (c) c.style.cursor = "default";
                        (e.target as Konva.Circle).radius(7);
                      }}
                    />
                  </Group>
                );
              })}

              {/* POLY/LINE/RECT 작도 임시 정점 */}
              {draft.length > 0 && (
                <>
                  <Line points={draftCoords} stroke="#60a5fa" strokeWidth={2} dash={[6, 4]} />
                  {draft.map((p) => (
                    <Circle key={p.id} x={p.x} y={p.y} radius={5} fill="#60a5fa" />
                  ))}
                </>
              )}
            </Layer>
          </Stage>
        )}
      </div>

      {/* ── DXF 가져오기 파일 입력(숨김) ── */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".dxf,application/dxf"
        className="hidden"
        onChange={handleImportFile}
      />

      {/* ── 상단 도구 바(슬림, 캔버스 비차폐) ── */}
      <div className="absolute left-1/2 top-4 z-20 flex -translate-x-1/2 items-center gap-1.5 rounded-2xl border border-white/10 bg-black/55 p-1.5 backdrop-blur-xl shadow-2xl">
        {TOOLS.map((t) => (
          <button
            key={t.key}
            onClick={() => { setTool(t.key); setSelectedIdx(null); if (t.key !== tool) setDraft([]); }}
            className={`rounded-xl px-3 py-2 text-[10px] font-black uppercase tracking-widest transition-colors ${
              tool === t.key ? "bg-teal-500 text-white shadow-lg" : "text-white/55 hover:bg-white/10 hover:text-white"
            }`}
          >
            {t.label}
          </button>
        ))}
        <div className="mx-1 h-5 w-px bg-white/10" />
        {/* ── undo/redo(↶↷) — Ctrl+Z / Ctrl+Shift+Z ── */}
        <button
          onClick={undo}
          disabled={!canUndo}
          title="실행 취소 (Ctrl+Z)"
          aria-label="실행 취소"
          className="rounded-xl px-3 py-2 text-[13px] font-black text-white/70 transition-colors hover:bg-white/10 hover:text-white disabled:opacity-30"
        >
          ↶
        </button>
        <button
          onClick={redo}
          disabled={!canRedo}
          title="다시 실행 (Ctrl+Shift+Z)"
          aria-label="다시 실행"
          className="rounded-xl px-3 py-2 text-[13px] font-black text-white/70 transition-colors hover:bg-white/10 hover:text-white disabled:opacity-30"
        >
          ↷
        </button>
        <div className="mx-1 h-5 w-px bg-white/10" />
        <button
          onClick={handleSave}
          disabled={saveStatus === "saving" || ring.length < 3}
          title={ring.length < 3 ? "외곽 레이어 다각형이 있어야 저장됩니다" : undefined}
          className={`rounded-xl px-4 py-2 text-[10px] font-black uppercase tracking-widest transition-colors disabled:opacity-50 ${
            saveStatus === "saved" ? "bg-emerald-500 text-white"
              : saveStatus === "error" ? "bg-red-500/80 text-white"
              : "bg-white/10 text-white hover:bg-white/20"
          }`}
        >
          {saveStatus === "saving" ? "저장 중..."
            : saveStatus === "saved" ? `✓ 저장${loadedVersion ? ` v${loadedVersion}` : ""}`
            : saveStatus === "error" ? "재시도"
            : `저장${loadedVersion ? ` (v${loadedVersion})` : ""}`}
        </button>
        {/* ── 편집본 DXF 다운로드(저장본 → 정식 DXF). 404면 "먼저 저장하세요" 안내 ── */}
        <button
          onClick={downloadEditedDxf}
          disabled={dxfState === "loading"}
          title="저장된 편집본을 정식 DXF(LWPOLYLINE+치수)로 내려받습니다"
          className={`rounded-xl px-3 py-2 text-[10px] font-black uppercase tracking-widest transition-colors disabled:opacity-50 ${
            dxfState === "need-save" ? "bg-amber-500/80 text-white"
              : dxfState === "error" ? "bg-red-500/80 text-white"
              : "bg-white/10 text-white/80 hover:bg-white/20"
          }`}
        >
          {dxfState === "loading" ? "DXF 생성…"
            : dxfState === "need-save" ? "먼저 저장하세요"
            : dxfState === "error" ? "DXF 실패"
            : "⬇ 편집본 DXF"}
        </button>
        {/* ── DXF 가져오기(파일 → POST import-dxf → shapes 변환) ── */}
        <button
          onClick={triggerImport}
          disabled={importState === "loading"}
          title="DXF 파일을 업로드해 도형으로 가져옵니다(폴리라인 → 다각형/선)"
          className="rounded-xl px-3 py-2 text-[10px] font-black uppercase tracking-widest text-white/80 transition-colors hover:bg-white/20 disabled:opacity-50 bg-white/10"
        >
          {importState === "loading" ? "가져오는 중…" : "⬆ 가져오기"}
        </button>
        <div className="mx-1 h-5 w-px bg-white/10" />
        {/* ── 전체삭제(confirm — Ctrl+Z 복원 가능) ── */}
        <button
          onClick={clearAll}
          disabled={shapes.length === 0 && draft.length === 0}
          title="모든 도형을 삭제합니다(확인 후 실행, Ctrl+Z로 복원 가능)"
          className="rounded-xl px-3 py-2 text-[10px] font-black uppercase tracking-widest text-rose-300/80 transition-colors hover:bg-rose-500/15 hover:text-rose-200 disabled:opacity-30"
        >
          전체삭제
        </button>
      </div>

      {/* ── 좌상단: 레이어 칩(활성 레이어 선택 + 표시 토글) ──
          top-16: 부모(CadBimIntegrationPanel)의 "← 편집 종료" 버튼(left-4 top-4 z-40)과 비충돌. */}
      <div className="absolute left-4 top-16 z-20 w-[148px] rounded-2xl border border-white/10 bg-black/55 p-2.5 backdrop-blur-xl shadow-2xl">
        <p className="mb-1.5 text-[8px] font-black uppercase tracking-[0.2em] text-white/40">Layers</p>
        <div className="space-y-1">
          {LAYER_KEYS.map((k) => (
            <div key={k} className="flex items-center gap-1">
              <button
                onClick={() => setActiveLayer(k)}
                title={`${LAYER_LABELS[k]} 레이어에 그리기`}
                className={`flex flex-1 items-center gap-1.5 rounded-lg px-2 py-1 text-left text-[10px] font-black transition-colors ${
                  activeLayer === k ? "bg-white/15 text-white" : "text-white/55 hover:bg-white/10"
                }`}
              >
                <span className="h-2 w-2 rounded-full" style={{ background: LAYER_COLORS[k] }} />
                {LAYER_LABELS[k]}
              </button>
              <button
                onClick={() => setVisibleLayers((v) => ({ ...v, [k]: !v[k] }))}
                title={visibleLayers[k] ? "레이어 숨기기" : "레이어 표시"}
                aria-label={`${LAYER_LABELS[k]} 레이어 표시 전환`}
                className={`rounded-lg px-1.5 py-1 text-[11px] font-black transition-colors hover:bg-white/10 ${
                  visibleLayers[k] ? "text-teal-300" : "text-white/25"
                }`}
              >
                {visibleLayers[k] ? "◉" : "○"}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* ── 최초 1회 도움말 칩(편집기 첫 진입 안내) ── */}
      {showHelp && !isDrawTool && (
        <div className="absolute left-1/2 top-[4.5rem] z-30 flex max-w-[440px] -translate-x-1/2 items-start gap-3 rounded-2xl border border-teal-400/30 bg-black/80 px-4 py-3 backdrop-blur-xl shadow-2xl">
          <span className="mt-0.5 text-[14px] leading-none">💡</span>
          <div className="flex-1">
            <p className="text-[11px] font-black text-teal-200">처음이신가요? 이렇게 다듬으세요</p>
            <p className="mt-1 text-[10px] leading-relaxed text-white/65">
              정점을 끌어 평면을 수정하면 면적·수지가 실시간 갱신됩니다.
              레이어 칩(외곽·벽체·치수·주석)을 고르고 선·사각형·주석을 그리거나 <b className="text-white/80">가져오기</b>로 DXF를 불러올 수 있어요.
              <span className="text-white/40"> 되돌리기 </span><b className="text-white/80">Ctrl+Z</b>
              <span className="text-white/40"> · 다시 </span><b className="text-white/80">Ctrl+Shift+Z</b>.
              마치면 <b className="text-white/80">저장</b> 후 <b className="text-white/80">편집본 DXF</b>를 받을 수 있어요.
            </p>
          </div>
          <button
            onClick={dismissHelp}
            aria-label="도움말 닫기"
            className="rounded-lg px-2 py-0.5 text-[13px] font-black text-white/50 hover:bg-white/10 hover:text-white"
          >
            ×
          </button>
        </div>
      )}

      {/* ── POLY 작도 안내(외곽 교체 / 레이어 다각형) ── */}
      {tool === "poly" && (
        <div className="absolute left-1/2 top-20 z-20 flex -translate-x-1/2 items-center gap-2 rounded-xl border border-blue-400/30 bg-black/70 px-4 py-2 backdrop-blur-xl">
          <span className="text-[11px] font-bold text-blue-200">
            캔버스를 클릭해 정점을 찍으세요 ({draft.length}개)
            {activeLayer === "outline" ? " — 완료 시 외곽 교체" : ` — ${LAYER_LABELS[activeLayer]} 레이어에 추가`}
          </span>
          <button onClick={finishPoly} disabled={draft.length < 3}
            className="rounded-lg bg-teal-500 px-3 py-1 text-[10px] font-black text-white disabled:opacity-40">완료</button>
          <button onClick={cancelPoly}
            className="rounded-lg bg-white/10 px-3 py-1 text-[10px] font-black text-white/70">취소</button>
        </div>
      )}

      {/* ── LINE/RECT 작도 안내(2점 클릭) ── */}
      {(tool === "line" || tool === "rect") && draft.length === 1 && (
        <div className="absolute left-1/2 top-20 z-20 flex -translate-x-1/2 items-center gap-2 rounded-xl border border-blue-400/30 bg-black/70 px-4 py-2 backdrop-blur-xl">
          <span className="text-[11px] font-bold text-blue-200">
            {tool === "line" ? "끝점을 클릭하면 선이 완성됩니다" : "반대편 모서리를 클릭하면 사각형이 완성됩니다"}
          </span>
          <button onClick={cancelPoly}
            className="rounded-lg bg-white/10 px-3 py-1 text-[10px] font-black text-white/70">취소</button>
        </div>
      )}

      {/* ── DXF 가져오기 결과 토스트(정직 표기: 변환·무시·단위) ── */}
      {importMsg && (
        <div
          className={`absolute bottom-4 left-1/2 z-30 max-w-[560px] -translate-x-1/2 rounded-2xl border px-4 py-2.5 backdrop-blur-xl shadow-2xl ${
            importMsg.kind === "ok" ? "border-teal-400/30 bg-black/80" : "border-rose-400/40 bg-black/80"
          }`}
        >
          <p className={`text-[11px] font-bold leading-relaxed ${importMsg.kind === "ok" ? "text-teal-200" : "text-rose-300"}`}>
            {importMsg.text}
          </p>
        </div>
      )}

      {/* ── 좌하단: 지오메트리·법규 컴팩트 패널(좁게, 캔버스 비차폐) ── */}
      <div className="absolute bottom-4 left-4 z-20 w-[260px] rounded-2xl border border-white/10 bg-black/60 p-4 backdrop-blur-xl shadow-2xl">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-[10px] font-black uppercase tracking-[0.2em] text-white/45">Building Geometry</span>
          <span className={`flex h-2 w-2 rounded-full ${isChecking ? "animate-pulse bg-amber-500" : hasViolationHint ? "bg-rose-500" : "bg-teal-500"}`} />
        </div>

        {/* 슬라이더 */}
        <div className="space-y-3">
          <div>
            <div className="flex justify-between px-0.5">
              <span className="text-[9px] font-black uppercase text-white/40">층수</span>
              <span className="text-[11px] font-black text-teal-400">{floorCount} F</span>
            </div>
            <input type="range" min={1} max={50} value={floorCount}
              onPointerDown={commitSnapshot}
              onChange={(e) => {
                const v = Number(e.target.value);
                setFloorCount(v);
                setBuildingHeight(Math.round(v * (initialFloorHeightM || 3)));
                debouncedCheck(ring);
              }}
              className="h-1 w-full cursor-pointer rounded-full bg-white/10 accent-teal-400" />
          </div>
          <div>
            <div className="flex justify-between px-0.5">
              <span className="text-[9px] font-black uppercase text-white/40">전체높이</span>
              <span className={`text-[11px] font-black ${overHeight ? "text-rose-400" : "text-blue-400"}`}>{buildingHeight} m</span>
            </div>
            <input type="range" min={3} max={300} value={buildingHeight}
              onPointerDown={commitSnapshot}
              onChange={(e) => { setBuildingHeight(Number(e.target.value)); debouncedCheck(ring); }}
              className="h-1 w-full cursor-pointer rounded-full bg-white/10 accent-blue-400" />
          </div>
        </div>

        {/* 라이브 지표 */}
        <div className="mt-3 grid grid-cols-3 gap-2 border-t border-white/5 pt-3">
          <div>
            <p className="text-[8px] font-black uppercase tracking-wider text-white/35">건축면적</p>
            <p className="text-[12px] font-black text-white">{fmt(metrics.areaM2, "㎡")}</p>
          </div>
          <div>
            <p className="text-[8px] font-black uppercase tracking-wider text-white/35">건폐율</p>
            <p className={`text-[12px] font-black ${overBcr ? "text-rose-400" : "text-white"}`}>
              {fmt(metrics.bcr, "%")}
              {limits.bcr != null && <span className="text-[8px] text-white/35"> /{limits.bcr}</span>}
            </p>
          </div>
          <div>
            <p className="text-[8px] font-black uppercase tracking-wider text-white/35">용적률</p>
            <p className={`text-[12px] font-black ${overFar ? "text-rose-400" : "text-white"}`}>
              {fmt(metrics.far, "%")}
              {limits.far != null && <span className="text-[8px] text-white/35"> /{limits.far}</span>}
            </p>
          </div>
        </div>

        {/* 법규 위반(클라 힌트 + 백엔드 검증) */}
        {(hasViolationHint || violations.length > 0) ? (
          <div className="mt-3 rounded-xl border border-rose-500/25 bg-rose-500/10 p-2.5">
            <p className="mb-1 text-[9px] font-black uppercase tracking-wider text-rose-400">법규 초과 감지</p>
            {overBcr && <p className="text-[10px] leading-tight text-white/80">· 건폐율 {metrics.bcr?.toFixed(1)}% &gt; 상한 {limits.bcr}%</p>}
            {overFar && <p className="text-[10px] leading-tight text-white/80">· 용적률 {metrics.far?.toFixed(1)}% &gt; 상한 {limits.far}%</p>}
            {overHeight && <p className="text-[10px] leading-tight text-white/80">· 높이 {buildingHeight}m &gt; 상한 {limits.height}m</p>}
            {violations.slice(0, 2).map((v, i) => (
              <p key={i} className="text-[10px] leading-tight text-white/70">· {v.message}</p>
            ))}
          </div>
        ) : (
          <p className="mt-3 flex items-center gap-1.5 text-[10px] font-bold text-teal-400">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
            법규 한도 충족 {limits.bcr == null && "(부지면적 연동 시 정밀)"}
          </p>
        )}
      </div>

      {/* ── 우하단: 선택/도움말 칩 ── */}
      <div className="absolute bottom-4 right-4 z-20 max-w-[220px] rounded-2xl border border-white/10 bg-black/55 px-4 py-3 backdrop-blur-xl">
        <p className="text-[9px] font-black uppercase tracking-widest text-white/35">
          현재 도구 · <span style={{ color: LAYER_COLORS[activeLayer] }}>{LAYER_LABELS[activeLayer]}</span>
        </p>
        <p className="text-[12px] font-black text-white">{TOOLS.find((t) => t.key === tool)?.label}</p>
        <p className="mt-1.5 text-[10px] leading-tight text-white/45">
          {tool === "select" && "외곽 정점을 끌어 수정하고, 벽체·주석 도형은 통째로 이동합니다."}
          {tool === "point" && "파란 + 핸들을 클릭하면 외곽 엣지 중간에 정점이 추가됩니다."}
          {tool === "poly" && (activeLayer === "outline"
            ? "빈 캔버스를 클릭해 새 외곽선을 그리세요(완료 시 교체)."
            : `클릭으로 정점을 찍어 ${LAYER_LABELS[activeLayer]} 다각형을 그립니다.`)}
          {tool === "line" && "두 점을 클릭해 선을 그립니다(활성 레이어, 정점 자동 스냅)."}
          {tool === "rect" && "대각 두 모서리를 클릭해 사각형을 그립니다(활성 레이어)."}
          {tool === "text" && "클릭한 위치에 주석 텍스트를 답니다."}
          {tool === "dim" && "외곽 각 변의 실제 길이(m)가 표시됩니다."}
          {tool === "delete" && "외곽 정점(최소 3개 유지) 또는 도형을 클릭해 삭제합니다."}
        </p>
      </div>

      {/* ── 좌표계 칩(상단 우측) ── */}
      <div className="absolute right-4 top-4 z-20 flex items-center gap-2 rounded-full bg-black/55 px-4 py-2 backdrop-blur-xl border border-white/10">
        <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
        <span className="text-[10px] font-black uppercase tracking-widest text-white/70">EPSG:5186 · 1px={(1 / scalePxPerM).toFixed(2)}m</span>
      </div>
    </div>
  );
}
