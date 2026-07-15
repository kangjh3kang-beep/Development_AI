"use client";

import React, { useState, useCallback, useRef, useEffect, useMemo } from "react";
import type Konva from "konva";
import { Check, Download, Eye, EyeOff, Lightbulb, Mic, Send, Terminal, Upload } from "lucide-react";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { executeCommand, getCommandHint } from "@/lib/cad-command-parser";
import { getZoningSpec } from "@/lib/kr-building-regulations";
import { useSpeechToText } from "@/lib/use-speech-to-text";
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

/**
 * 2차-A 시드 기하(미터 단위, 원점=좌상단). 외곽 footprint는 필수, 코어/벽체선은 선택.
 * 모든 좌표는 "건물 로컬 m"이며 폭 outerWidthM × 깊이 outerDepthM 안에 위치한다.
 * 편집기 진입 시 px 환산 + 캔버스 중앙배치된다(축소비 k는 외곽·자식 도형에 공통 적용 → 형상 보존).
 */
export interface SeedGeometry {
  /** 외곽 footprint 다각형(m). 비면(2점 이하) 시 outerWidthM×outerDepthM 사각형으로 폴백. */
  outline: Array<{ x: number; y: number }>;
  /** bbox 폭(m) — px 환산·중앙배치 기준(외곽 다각형 bbox와 일치해야 함). */
  outerWidthM: number;
  /** bbox 깊이(m). */
  outerDepthM: number;
  /** 코어(EV·계단실) 사각형(m) — 외곽 내부. 있으면 벽체 레이어 도형으로 시드. */
  core?: { x: number; y: number; w: number; h: number } | null;
  /** 세대 분할선 등 추가 벽체선(m, [x1,y1,x2,y2]). 있으면 벽체 레이어 선으로 시드. */
  walls?: Array<[number, number, number, number]> | null;
}

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
  /**
   * 2차-A: 실제 설계 기하(외곽 footprint + 벽체/코어 등)를 m 단위로 받는 시드.
   * 더미 30×20 박스 대신 부모가 spec/bimMass에서 파생한 실제 도형을 주입하면 2D 편집기가
   * 3D 매스·2D 평면과 동일한 기하로 시작한다. 좌표 단위는 "미터(원점=좌상단 기준 0,0)"이며
   * 편집기 진입 시 캔버스 중앙에 px 환산·중앙배치된다. 저장본(/drawings/load)이 있으면 그쪽 우선.
   */
  initialGeometryM?: SeedGeometry;
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

function resolveLimits(zone?: string): { bcr: number; far: number; height: number } | null {
  const spec = getZoningSpec(zone || "");
  return spec
    ? { bcr: spec.buildingCoverageMax, far: spec.floorAreaRatioMax, height: spec.heightLimit ?? 0 }
    : null;
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
  initialGeometryM,
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
  const [commandText, setCommandText] = useState("");
  const [commandResult, setCommandResult] = useState<{ ok: boolean; message: string } | null>(null);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stt = useSpeechToText((text) => setCommandText(text), "ko-KR");

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
        // 신규 shapes[](백엔드 px 좌표) 1차 → 레거시 polylines 폴백(cad-shapes 변환)
        const imported = dxfImportToShapes(res, { scalePxPerM });
        if (imported.length === 0) {
          showImportMsg("error", "가져올 수 있는 도형이 없습니다(빈 변환 결과).");
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
            : Array.isArray(ignoredRaw)
              ? ignoredRaw.reduce<number>((acc, item) => {
                  // 신규 백엔드 ignored:[{type,count}] → count 합산, 레거시 항목은 1개로 계수
                  const c = Number((item as Record<string, unknown> | null)?.count);
                  return acc + (Number.isFinite(c) && c > 0 ? c : 1);
                }, 0)
              : null;
        // unit은 신규 객체({detected,source}) 또는 레거시 문자열 — 둘 다 정직 표기
        const unitDetected =
          typeof res.unit === "string"
            ? res.unit.trim()
            : res.unit && typeof res.unit === "object" && typeof res.unit.detected === "string"
              ? res.unit.detected.trim()
              : "";
        const unitHeuristic =
          !!res.unit && typeof res.unit === "object" && res.unit.source === "heuristic";
        const unitTxt = unitDetected
          ? `단위 ${unitDetected}${unitHeuristic ? "(추정)" : ""}`
          : "단위 정보 없음(1단위=1m 가정)";
        // 변환 제외 개수 — 신규 shapes 기준 우선, 없으면 레거시 polylines 기준
        const sourceCount =
          Array.isArray(res.shapes) && res.shapes.length > 0
            ? res.shapes.length
            : Array.isArray(res.polylines)
              ? res.polylines.length
              : 0;
        const skippedLocal = sourceCount - imported.length;
        showImportMsg(
          "ok",
          `도형 ${imported.length}개 ${replace ? "교체" : "추가"} · ${unitTxt}` +
            (ignoredNum != null && ignoredNum > 0 ? ` · 미지원 엔티티 ${ignoredNum}개 무시` : "") +
            (skippedLocal > 0 ? ` · 변환 불가 도형 ${skippedLocal}개 제외` : "") +
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

  /* ── 기본 도형 시드: 크기 측정 완료 + 로드 완료 + 미시드일 때, 실제 설계 기하를 중앙배치 ──
     2차-A: initialGeometryM(부모가 spec/bimMass에서 파생한 실제 footprint+코어+벽체)이 있으면
     그것을 시드한다(더미 30×20 박스 → 실제 설계 기하). 없으면 폭×깊이 사각형(기존 동작) 폴백.
     모든 자식 도형(코어·벽체선)은 외곽과 동일한 center+scale 변환을 받아 형상이 보존된다. */
  useEffect(() => {
    if (seededRef.current) return;
    if (loadState !== "done") return;
    if (size.w < 50 || size.h < 50) return;
    if (shapes.length > 0) { seededRef.current = true; return; }

    // 1) 외곽(m) 결정: 주입 기하 우선 → 없으면 폭×깊이 사각형 폴백.
    const geo = initialGeometryM;
    const validOutline = geo && Array.isArray(geo.outline) && geo.outline.length >= 3;
    const wM = (validOutline ? geo!.outerWidthM : initialWidthM) || 0;
    const dM = (validOutline ? geo!.outerDepthM : initialDepthM) || 0;
    const outW = wM > 0 ? wM : 30;
    const outD = dM > 0 ? dM : 20;
    // 외곽 m 좌표(원점 보정): 주입 다각형은 자체 bbox 원점을 (0,0)으로 평행이동해 폭×깊이 안으로 정렬.
    let outlineM: Array<{ x: number; y: number }>;
    if (validOutline) {
      const xs = geo!.outline.map((p) => p.x);
      const ys = geo!.outline.map((p) => p.y);
      const minX = Math.min(...xs);
      const minY = Math.min(...ys);
      outlineM = geo!.outline.map((p) => ({ x: p.x - minX, y: p.y - minY }));
    } else {
      outlineM = [
        { x: 0, y: 0 }, { x: outW, y: 0 }, { x: outW, y: outD }, { x: 0, y: outD },
      ];
    }

    // 2) px 환산 + 캔버스 중앙배치(축소비 k는 외곽·자식에 공통 적용 → 형상 보존).
    const wPx0 = outW * scalePxPerM;
    const dPx0 = outD * scalePxPerM;
    const cx = size.w / 2;
    const cy = size.h / 2;
    const maxW = size.w * 0.7;
    const maxH = size.h * 0.7;
    const k = Math.min(1, maxW / wPx0, maxH / dPx0);
    // 건물 로컬 m(원점=좌상단) → 캔버스 px. 중앙배치: 외곽 bbox 중심을 캔버스 중심에 정렬.
    const sx = scalePxPerM * k;
    const sy = scalePxPerM * k;
    const offX = cx - (outW * sx) / 2;
    const offY = cy - (outD * sy) / 2;
    const toPx = (xm: number, ym: number): DesignPoint => ({
      id: nextId(), x: snap(offX + xm * sx), y: snap(offY + ym * sy),
    });

    const seed: DesignPoint[] = outlineM.map((p) => toPx(p.x, p.y));
    const seededShapes: CadShape[] = [
      { id: newShapeId("outline"), kind: "polygon", layer: "outline", points: seed },
    ];

    // 3) 코어(EV·계단실) — 벽체 레이어 사각형(외곽 내부, 동일 변환).
    if (validOutline && geo!.core && geo!.core.w > 0 && geo!.core.h > 0) {
      const c = geo!.core;
      // core 좌표도 outline과 동일 원점 보정(주입 좌표는 절대 m → bbox 원점 기준으로).
      const xs = geo!.outline.map((p) => p.x);
      const ys = geo!.outline.map((p) => p.y);
      const minX = Math.min(...xs);
      const minY = Math.min(...ys);
      const cx0 = c.x - minX;
      const cy0 = c.y - minY;
      seededShapes.push({
        id: newShapeId("core"), kind: "rect", layer: "wall",
        points: [toPx(cx0, cy0), toPx(cx0 + c.w, cy0 + c.h)],
      });
    }

    // 4) 세대 분할선 등 추가 벽체선(있으면).
    if (validOutline && Array.isArray(geo!.walls)) {
      const xs = geo!.outline.map((p) => p.x);
      const ys = geo!.outline.map((p) => p.y);
      const minX = Math.min(...xs);
      const minY = Math.min(...ys);
      for (const w of geo!.walls!) {
        if (!Array.isArray(w) || w.length < 4) continue;
        seededShapes.push({
          id: newShapeId("wl"), kind: "line", layer: "wall",
          points: [toPx(w[0] - minX, w[1] - minY), toPx(w[2] - minX, w[3] - minY)],
        });
      }
    }

    seededRef.current = true;
    setShapes(seededShapes);
    debouncedCheck(seed);
    // initialGeometryM은 시드 1회용(seededRef 가드) — deps에 넣어도 재시드는 가드로 막힌다.
  }, [loadState, size, shapes.length, initialWidthM, initialDepthM, initialGeometryM, scalePxPerM, snap, debouncedCheck]);

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

  /* ── CAD 명령/음성 실행: 기존 cad-command-parser를 CADEditor shapes 모델에 어댑트 ── */
  const runCanvasCommand = useCallback(
    (rawCommand?: string) => {
      const raw = (rawCommand ?? commandText).trim();
      if (!raw) return;
      const compact = raw.replace(/\s+/g, " ");
      const floorMatch =
        compact.match(/(?:층수|floors?)\s*(\d{1,2})/i) ??
        compact.match(/(\d{1,2})\s*층/);
      if (floorMatch) {
        const nextFloors = Math.max(1, Math.min(50, Number(floorMatch[1])));
        commitSnapshot();
        setFloorCount(nextFloors);
        setBuildingHeight(Math.round(nextFloors * floorHeightM));
        debouncedCheck(ring);
        setCommandResult({ ok: true, message: `층수 ${nextFloors}층 적용` });
        setCommandText("");
        return;
      }
      const heightMatch = compact.match(/(?:높이|height)\s*(\d{1,3}(?:\.\d+)?)/i);
      if (heightMatch) {
        const nextHeight = Math.max(3, Math.min(300, Number(heightMatch[1])));
        commitSnapshot();
        setBuildingHeight(nextHeight);
        debouncedCheck(ring);
        setCommandResult({ ok: true, message: `높이 ${nextHeight}m 적용` });
        setCommandText("");
        return;
      }

      const pendingPoints = new Map<string, CadShapePoint>();
      const consumedPointIds = new Set<string>();
      const pendingShapes: CadShape[] = [];
      let pendingOutline: CadShape | null = null;
      let directMutation = false;
      const commandLayer: LayerKey = activeLayer === "outline" ? "wall" : activeLayer;
      const allPoints = shapes.flatMap((s) => s.points.map((p) => ({ id: p.id, x: p.x, y: p.y })));
      const rects = shapes
        .filter((s) => s.kind === "rect" && s.points.length >= 2)
        .map((s) => {
          const [a, b] = s.points;
          return {
            id: s.id,
            x: Math.min(a.x, b.x),
            y: Math.min(a.y, b.y),
            width: Math.abs(b.x - a.x),
            height: Math.abs(b.y - a.y),
          };
        });
      const circles = shapes
        .filter((s) => s.kind === "circle" && s.points.length >= 1)
        .map((s) => ({ id: s.id, cx: s.points[0].x, cy: s.points[0].y, radius: s.radius ?? 10 }));
      const texts = shapes
        .filter((s) => s.kind === "label" && s.points.length >= 1)
        .map((s) => ({ id: s.id, x: s.points[0].x, y: s.points[0].y, text: s.text ?? "" }));
      const lines = shapes
        .filter((s) => s.kind === "line" && s.points.length >= 2)
        .map((s) => ({ id: s.id, startPointId: s.points[0].id, endPointId: s.points[1].id }));
      const polygons = shapes
        .filter((s) => s.kind === "polygon" && s.points.length >= 3)
        .map((s) => ({ id: s.id, pointIds: s.points.map((p) => p.id) }));

      const pointById = (id: string): CadShapePoint | null =>
        pendingPoints.get(id) ??
        allPoints.find((p) => p.id === id) ??
        null;

      const selectedPointId = selectedIdx != null ? ring[selectedIdx]?.id ?? null : null;
      const selectedId = selectedPointId ?? outlineShape?.id ?? null;
      const store = {
        addPoint: (x: number, y: number) => {
          const p = { id: nextId(), x: snap(x), y: snap(y) };
          pendingPoints.set(p.id, p);
          return p.id;
        },
        addLine: (startId: string, endId: string) => {
          const a = pointById(startId);
          const b = pointById(endId);
          if (!a || !b) return;
          consumedPointIds.add(startId);
          consumedPointIds.add(endId);
          pendingShapes.push({
            id: newShapeId("cmd-ln"),
            kind: "line",
            layer: commandLayer,
            points: [a, b],
          });
        },
        addRect: (x: number, y: number, w: number, h: number) => {
          pendingShapes.push({
            id: newShapeId("cmd-rc"),
            kind: "rect",
            layer: commandLayer,
            points: [
              { id: nextId(), x: snap(x), y: snap(y) },
              { id: nextId(), x: snap(x + w), y: snap(y + h) },
            ],
          });
        },
        addCircle: (cx: number, cy: number, r: number) => {
          pendingShapes.push({
            id: newShapeId("cmd-c"),
            kind: "circle",
            layer: commandLayer,
            points: [{ id: nextId(), x: snap(cx), y: snap(cy) }],
            radius: Math.max(1, r),
          });
        },
        addText: (x: number, y: number, text: string) => {
          pendingShapes.push({
            id: newShapeId("cmd-t"),
            kind: "label",
            layer: activeLayer === "outline" ? "note" : activeLayer,
            points: [{ id: nextId(), x: snap(x), y: snap(y) }],
            text,
          });
        },
        addPolygon: (pointIds: string[]) => {
          const pts = pointIds.map(pointById).filter(Boolean) as CadShapePoint[];
          if (pts.length < 3) return;
          pointIds.forEach((id) => consumedPointIds.add(id));
          const shape = { id: newShapeId("cmd-pg"), kind: "polygon" as const, layer: activeLayer, points: pts };
          if (activeLayer === "outline") pendingOutline = shape;
          else pendingShapes.push(shape);
        },
        removeSelected: () => {
          if (selectedIdx == null) return;
          deleteVertex(selectedIdx);
          directMutation = true;
        },
        undo: () => {
          undo();
          directMutation = true;
        },
        redo: () => {
          redo();
          directMutation = true;
        },
        setSelected: (id: string | null) => {
          if (id == null) setSelectedIdx(null);
        },
        points: allPoints,
        lines,
        polygons,
        rects,
        circles,
        texts,
        selectedId,
        selectedIds: selectedPointId ? [selectedPointId] : [],
        scale: scalePxPerM,
        movePoint: (id: string, x: number, y: number) => {
          commitSnapshot();
          const nextShapes = shapes.map((s) => ({
            ...s,
            points: s.points.map((p) => (p.id === id ? { ...p, x: snap(x), y: snap(y) } : p)),
          }));
          setShapes(nextShapes);
          debouncedCheck(outlineRing(findOutline(nextShapes)));
          directMutation = true;
        },
      };

      const result = executeCommand(compact, store);
      const loosePointShapes: CadShape[] = [...pendingPoints.values()]
        .filter((p) => !consumedPointIds.has(p.id))
        .map((p) => ({
          id: newShapeId("cmd-pt"),
          kind: "circle" as const,
          layer: activeLayer === "outline" ? "note" : activeLayer,
          points: [p],
          radius: 3,
        }));
      if (result.ok && (pendingOutline || pendingShapes.length > 0 || loosePointShapes.length > 0)) {
        commitSnapshot();
        const nextShapes = pendingOutline
          ? [pendingOutline, ...shapes.filter((s) => s.layer !== "outline"), ...pendingShapes, ...loosePointShapes]
          : [...shapes, ...pendingShapes, ...loosePointShapes];
        setShapes(nextShapes);
        const nextRing = outlineRing(findOutline(nextShapes));
        if (nextRing.length >= 3) debouncedCheck(nextRing);
      } else if (result.ok && !directMutation && /^AREA\b|^AA\b|^면적\b/i.test(compact)) {
        // 조회 명령은 상태 변경 없음.
      }
      setCommandResult(result);
      if (result.ok) setCommandText("");
    },
    [
      activeLayer,
      commandText,
      commitSnapshot,
      debouncedCheck,
      deleteVertex,
      floorHeightM,
      outlineShape,
      redo,
      ring,
      scalePxPerM,
      selectedIdx,
      shapes,
      snap,
      undo,
    ],
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
      <div className="flex h-full w-full items-center justify-center bg-[#0a0f14] px-6 text-center text-[var(--text-primary)]">
        <div className="flex flex-col items-center gap-3">
          <p className="text-sm font-bold text-[var(--status-error)]">{rkError}</p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded-[var(--r-input)] border border-[color-mix(in_srgb,var(--accent-strong)_40%,transparent)] bg-[color-mix(in_srgb,var(--accent-strong)_10%,transparent)] px-4 py-2 text-xs font-bold text-[var(--accent-strong)] hover:bg-[color-mix(in_srgb,var(--accent-strong)_20%,transparent)]"
          >
            새로고침
          </button>
        </div>
      </div>
    );
  }
  if (!isReady || !rk) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-[#0a0f14] text-[var(--text-primary)]">
        <div className="flex flex-col items-center gap-4">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-[var(--accent-strong)] border-t-transparent" />
          <p className="label-caps text-[var(--accent-strong)]">CAD 엔진 초기화...</p>
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
      <div className="absolute left-1/2 top-4 z-20 flex -translate-x-1/2 items-center gap-1.5 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--glass-bg)] p-1.5 backdrop-blur-[var(--glass-blur)] shadow-2xl">
        {TOOLS.map((t) => (
          <button
            key={t.key}
            onClick={() => { setTool(t.key); setSelectedIdx(null); if (t.key !== tool) setDraft([]); }}
            className={`rounded-[var(--r-input)] px-3 py-2 text-[10px] font-black uppercase tracking-widest transition-colors ${
              tool === t.key ? "bg-[var(--accent-strong)] text-white shadow-lg" : "text-[var(--text-tertiary)] hover:bg-[color-mix(in_srgb,var(--text-primary)_10%,transparent)] hover:text-[var(--text-primary)]"
            }`}
          >
            {t.label}
          </button>
        ))}
        <div className="mx-1 h-5 w-px bg-[var(--border-muted)]" />
        {/* ── undo/redo(↶↷) — Ctrl+Z / Ctrl+Shift+Z ── */}
        <button
          onClick={undo}
          disabled={!canUndo}
          title="실행 취소 (Ctrl+Z)"
          aria-label="실행 취소"
          className="rounded-[var(--r-input)] px-3 py-2 text-[13px] font-black text-[var(--text-secondary)] transition-colors hover:bg-[color-mix(in_srgb,var(--text-primary)_10%,transparent)] hover:text-[var(--text-primary)] disabled:opacity-30"
        >
          ↶
        </button>
        <button
          onClick={redo}
          disabled={!canRedo}
          title="다시 실행 (Ctrl+Shift+Z)"
          aria-label="다시 실행"
          className="rounded-[var(--r-input)] px-3 py-2 text-[13px] font-black text-[var(--text-secondary)] transition-colors hover:bg-[color-mix(in_srgb,var(--text-primary)_10%,transparent)] hover:text-[var(--text-primary)] disabled:opacity-30"
        >
          ↷
        </button>
        <div className="mx-1 h-5 w-px bg-[var(--border-muted)]" />
        <button
          onClick={handleSave}
          disabled={saveStatus === "saving" || ring.length < 3}
          title={ring.length < 3 ? "외곽 레이어 다각형이 있어야 저장됩니다" : undefined}
          className={`rounded-[var(--r-input)] px-4 py-2 text-[10px] font-black uppercase tracking-widest transition-colors disabled:opacity-50 ${
            saveStatus === "saved" ? "bg-[var(--status-success)] text-[var(--saas-ink)]"
              : saveStatus === "error" ? "bg-[color-mix(in_srgb,var(--status-error)_80%,transparent)] text-white"
              : "bg-[color-mix(in_srgb,var(--text-primary)_10%,transparent)] text-[var(--text-primary)] hover:bg-[color-mix(in_srgb,var(--text-primary)_20%,transparent)]"
          }`}
        >
          {saveStatus === "saving" ? "저장 중..."
            : saveStatus === "saved" ? (<span className="inline-flex items-center gap-1"><Check className="size-3" aria-hidden />저장{loadedVersion ? ` v${loadedVersion}` : ""}</span>)
            : saveStatus === "error" ? "재시도"
            : `저장${loadedVersion ? ` (v${loadedVersion})` : ""}`}
        </button>
        {/* ── 편집본 DXF 다운로드(저장본 → 정식 DXF). 404면 "먼저 저장하세요" 안내 ── */}
        <button
          onClick={downloadEditedDxf}
          disabled={dxfState === "loading"}
          title="저장된 편집본을 정식 DXF(LWPOLYLINE+치수)로 내려받습니다"
          className={`rounded-[var(--r-input)] px-3 py-2 text-[10px] font-black uppercase tracking-widest transition-colors disabled:opacity-50 ${
            dxfState === "need-save" ? "bg-[color-mix(in_srgb,var(--status-warning)_80%,transparent)] text-[var(--saas-ink)]"
              : dxfState === "error" ? "bg-[color-mix(in_srgb,var(--status-error)_80%,transparent)] text-white"
              : "bg-[color-mix(in_srgb,var(--text-primary)_10%,transparent)] text-[var(--text-secondary)] hover:bg-[color-mix(in_srgb,var(--text-primary)_20%,transparent)]"
          }`}
        >
          {dxfState === "loading" ? "DXF 생성…"
            : dxfState === "need-save" ? "먼저 저장하세요"
            : dxfState === "error" ? "DXF 실패"
            : (<span className="inline-flex items-center gap-1"><Download className="size-3" aria-hidden />편집본 DXF</span>)}
        </button>
        {/* ── DXF 가져오기(파일 → POST import-dxf → shapes 변환) ── */}
        <button
          onClick={triggerImport}
          disabled={importState === "loading"}
          title="DXF 파일을 업로드해 도형으로 가져옵니다(폴리라인 → 다각형/선)"
          className="rounded-[var(--r-input)] px-3 py-2 text-[10px] font-black uppercase tracking-widest text-[var(--text-secondary)] transition-colors hover:bg-[color-mix(in_srgb,var(--text-primary)_20%,transparent)] disabled:opacity-50 bg-[color-mix(in_srgb,var(--text-primary)_10%,transparent)]"
        >
          {importState === "loading" ? "가져오는 중…" : (<span className="inline-flex items-center gap-1"><Upload className="size-3" aria-hidden />가져오기</span>)}
        </button>
        <div className="mx-1 h-5 w-px bg-[var(--border-muted)]" />
        {/* ── 전체삭제(confirm — Ctrl+Z 복원 가능) ── */}
        <button
          onClick={clearAll}
          disabled={shapes.length === 0 && draft.length === 0}
          title="모든 도형을 삭제합니다(확인 후 실행, Ctrl+Z로 복원 가능)"
          className="rounded-[var(--r-input)] px-3 py-2 text-[10px] font-black uppercase tracking-widest text-[color-mix(in_srgb,var(--status-error)_80%,transparent)] transition-colors hover:bg-[color-mix(in_srgb,var(--status-error)_15%,transparent)] hover:text-[var(--status-error)] disabled:opacity-30"
        >
          전체삭제
        </button>
      </div>

      {/* ── 좌상단: 레이어 칩(활성 레이어 선택 + 표시 토글) ──
          top-16: 부모(CadBimIntegrationPanel)의 "← 편집 종료" 버튼(left-4 top-4 z-40)과 비충돌. */}
      <div className="absolute left-4 top-16 z-20 w-[148px] rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--glass-bg)] p-2.5 backdrop-blur-[var(--glass-blur)] shadow-2xl">
        <p className="mb-1.5 text-[8px] font-black uppercase tracking-[0.2em] text-[var(--text-tertiary)]">Layers</p>
        <div className="space-y-1">
          {LAYER_KEYS.map((k) => (
            <div key={k} className="flex items-center gap-1">
              <button
                onClick={() => setActiveLayer(k)}
                title={`${LAYER_LABELS[k]} 레이어에 그리기`}
                className={`flex flex-1 items-center gap-1.5 rounded-[var(--r-input)] px-2 py-1 text-left text-[10px] font-black transition-colors ${
                  activeLayer === k ? "bg-[color-mix(in_srgb,var(--text-primary)_15%,transparent)] text-[var(--text-primary)]" : "text-[var(--text-tertiary)] hover:bg-[color-mix(in_srgb,var(--text-primary)_10%,transparent)]"
                }`}
              >
                <span className="h-2 w-2 rounded-full" style={{ background: LAYER_COLORS[k] }} />
                {LAYER_LABELS[k]}
              </button>
              <button
                onClick={() => setVisibleLayers((v) => ({ ...v, [k]: !v[k] }))}
                title={visibleLayers[k] ? "레이어 숨기기" : "레이어 표시"}
                aria-label={`${LAYER_LABELS[k]} 레이어 표시 전환`}
                className={`rounded-[var(--r-input)] px-1.5 py-1 text-[11px] font-black transition-colors hover:bg-[color-mix(in_srgb,var(--text-primary)_10%,transparent)] ${
                  visibleLayers[k] ? "text-[var(--accent-strong)]" : "text-[var(--text-tertiary)]"
                }`}
              >
                {visibleLayers[k] ? <Eye className="size-3.5" aria-hidden /> : <EyeOff className="size-3.5" aria-hidden />}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* ── 최초 1회 도움말 칩(편집기 첫 진입 안내) ── */}
      {showHelp && !isDrawTool && (
        <div className="absolute left-1/2 top-[4.5rem] z-30 flex max-w-[440px] -translate-x-1/2 items-start gap-3 rounded-[var(--r-panel)] border border-[color-mix(in_srgb,var(--accent-strong)_30%,transparent)] bg-[var(--glass-bg-strong)] px-4 py-3 backdrop-blur-[var(--glass-blur)] shadow-2xl">
          <Lightbulb className="mt-0.5 size-3.5 shrink-0 text-[var(--accent-strong)]" aria-hidden />
          <div className="flex-1">
            <p className="text-[11px] font-black text-[var(--accent-strong)]">처음이신가요? 이렇게 다듬으세요</p>
            <p className="mt-1 text-[10px] leading-relaxed text-[var(--text-secondary)]">
              정점을 끌어 평면을 수정하면 면적·수지가 실시간 갱신됩니다.
              레이어 칩(외곽·벽체·치수·주석)을 고르고 선·사각형·주석을 그리거나 <b className="text-[var(--text-primary)]">가져오기</b>로 DXF를 불러올 수 있어요.
              <span className="text-[var(--text-tertiary)]"> 되돌리기 </span><b className="text-[var(--text-primary)]">Ctrl+Z</b>
              <span className="text-[var(--text-tertiary)]"> · 다시 </span><b className="text-[var(--text-primary)]">Ctrl+Shift+Z</b>.
              마치면 <b className="text-[var(--text-primary)]">저장</b> 후 <b className="text-[var(--text-primary)]">편집본 DXF</b>를 받을 수 있어요.
            </p>
          </div>
          <button
            onClick={dismissHelp}
            aria-label="도움말 닫기"
            className="rounded-[var(--r-input)] px-2 py-0.5 text-[13px] font-black text-[var(--text-tertiary)] hover:bg-[color-mix(in_srgb,var(--text-primary)_10%,transparent)] hover:text-[var(--text-primary)]"
          >
            ×
          </button>
        </div>
      )}

      {/* ── POLY 작도 안내(외곽 교체 / 레이어 다각형) ── */}
      {tool === "poly" && (
        <div className="absolute left-1/2 top-20 z-20 flex -translate-x-1/2 items-center gap-2 rounded-[var(--r-input)] border border-[color-mix(in_srgb,var(--status-info)_30%,transparent)] bg-[var(--glass-bg-strong)] px-4 py-2 backdrop-blur-[var(--glass-blur)]">
          <span className="text-[11px] font-bold text-[var(--status-info)]">
            캔버스를 클릭해 정점을 찍으세요 ({draft.length}개)
            {activeLayer === "outline" ? " — 완료 시 외곽 교체" : ` — ${LAYER_LABELS[activeLayer]} 레이어에 추가`}
          </span>
          <button onClick={finishPoly} disabled={draft.length < 3}
            className="rounded-[var(--r-input)] bg-[var(--accent-strong)] px-3 py-1 text-[10px] font-black text-white disabled:opacity-40">완료</button>
          <button onClick={cancelPoly}
            className="rounded-[var(--r-input)] bg-[color-mix(in_srgb,var(--text-primary)_10%,transparent)] px-3 py-1 text-[10px] font-black text-[var(--text-secondary)]">취소</button>
        </div>
      )}

      {/* ── LINE/RECT 작도 안내(2점 클릭) ── */}
      {(tool === "line" || tool === "rect") && draft.length === 1 && (
        <div className="absolute left-1/2 top-20 z-20 flex -translate-x-1/2 items-center gap-2 rounded-[var(--r-input)] border border-[color-mix(in_srgb,var(--status-info)_30%,transparent)] bg-[var(--glass-bg-strong)] px-4 py-2 backdrop-blur-[var(--glass-blur)]">
          <span className="text-[11px] font-bold text-[var(--status-info)]">
            {tool === "line" ? "끝점을 클릭하면 선이 완성됩니다" : "반대편 모서리를 클릭하면 사각형이 완성됩니다"}
          </span>
          <button onClick={cancelPoly}
            className="rounded-[var(--r-input)] bg-[color-mix(in_srgb,var(--text-primary)_10%,transparent)] px-3 py-1 text-[10px] font-black text-[var(--text-secondary)]">취소</button>
        </div>
      )}

      {/* ── DXF 가져오기 결과 토스트(정직 표기: 변환·무시·단위) ── */}
      {importMsg && (
        <div
          className={`absolute bottom-24 left-1/2 z-30 max-w-[560px] -translate-x-1/2 rounded-[var(--r-panel)] border px-4 py-2.5 backdrop-blur-[var(--glass-blur)] shadow-2xl ${
            importMsg.kind === "ok" ? "border-[color-mix(in_srgb,var(--status-success)_30%,transparent)] bg-[var(--glass-bg-strong)]" : "border-[color-mix(in_srgb,var(--status-error)_40%,transparent)] bg-[var(--glass-bg-strong)]"
          }`}
        >
          <p className={`text-[11px] font-bold leading-relaxed ${importMsg.kind === "ok" ? "text-[var(--status-success)]" : "text-[var(--status-error)]"}`}>
            {importMsg.text}
          </p>
        </div>
      )}

      {/* ── 하단 명령 바: 텍스트/음성 명령 → 동일 CAD shapes 모델에 즉시 반영 ── */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          runCanvasCommand();
        }}
        className="absolute bottom-4 left-4 right-4 z-30 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--glass-bg)] p-2.5 backdrop-blur-[var(--glass-blur)] shadow-2xl lg:left-[292px] lg:right-[252px]"
      >
        <div className="flex items-center gap-2">
          <Terminal className="size-4 shrink-0 text-[var(--accent-strong)]" aria-hidden />
          <input
            value={commandText}
            onChange={(e) => setCommandText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                setCommandText("");
                setCommandResult(null);
              }
            }}
            placeholder="층수 5 · 높이 18 · 선 10,10 30,10 · 사각형 10,10 20 12"
            aria-label="CAD 명령 입력"
            className="min-w-0 flex-1 bg-transparent text-[12px] font-bold text-[var(--text-primary)] outline-none placeholder:text-[var(--text-tertiary)]"
          />
          {stt.supported && (
            <button
              type="button"
              onClick={() => (stt.listening ? stt.stop() : stt.start())}
              title={stt.listening ? "음성 입력 중지" : "음성으로 명령 입력"}
              aria-label={stt.listening ? "음성 입력 중지" : "음성으로 명령 입력"}
              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--r-input)] border transition-colors ${
                stt.listening
                  ? "border-[color-mix(in_srgb,var(--status-error)_50%,transparent)] bg-[color-mix(in_srgb,var(--status-error)_20%,transparent)] text-[var(--status-error)]"
                  : "border-[var(--border-muted)] bg-[color-mix(in_srgb,var(--text-primary)_10%,transparent)] text-[var(--text-secondary)] hover:bg-[color-mix(in_srgb,var(--text-primary)_15%,transparent)] hover:text-[var(--text-primary)]"
              }`}
            >
              <Mic className="size-4" aria-hidden />
            </button>
          )}
          <button
            type="submit"
            disabled={!commandText.trim()}
            title="명령 실행"
            aria-label="명령 실행"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--r-input)] bg-[var(--accent-strong)] text-white transition-opacity hover:opacity-90 disabled:opacity-35"
          >
            <Send className="size-4" aria-hidden />
          </button>
        </div>
        {(commandText.trim() || commandResult || stt.error) && (
          <p
            className={`mt-1.5 truncate text-[10px] font-bold ${
              commandResult?.ok === false || stt.error ? "text-[var(--status-error)]" : "text-[var(--text-tertiary)]"
            }`}
            title={commandResult?.message || stt.error || getCommandHint(commandText.split(/\s+/)[0] || "")}
          >
            {commandResult?.message ||
              stt.error ||
              getCommandHint(commandText.split(/\s+/)[0] || "") ||
              "LINE · RECT · POLYGON · TEXT · AREA · LIST · UNDO"}
          </p>
        )}
      </form>

      {/* ── 좌하단: 지오메트리·법규 컴팩트 패널(좁게, 캔버스 비차폐) ── */}
      <div className="absolute bottom-4 left-4 z-20 w-[260px] rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--glass-bg)] p-4 backdrop-blur-[var(--glass-blur)] shadow-2xl">
        <div className="mb-3 flex items-center justify-between">
          <span className="label-caps text-[var(--text-tertiary)]">Building Geometry</span>
          <span className={`flex h-2 w-2 rounded-full ${isChecking ? "animate-pulse bg-[var(--status-warning)]" : hasViolationHint ? "bg-[var(--status-error)]" : "bg-[var(--status-success)]"}`} />
        </div>

        {/* 슬라이더 */}
        <div className="space-y-3">
          <div>
            <div className="flex justify-between px-0.5">
              <span className="text-[9px] font-black uppercase text-[var(--text-tertiary)]">층수</span>
              <span className="text-[11px] font-black text-[var(--accent-strong)]">{floorCount} F</span>
            </div>
            <input type="range" min={1} max={50} value={floorCount}
              onPointerDown={commitSnapshot}
              onChange={(e) => {
                const v = Number(e.target.value);
                setFloorCount(v);
                setBuildingHeight(Math.round(v * (initialFloorHeightM || 3)));
                debouncedCheck(ring);
              }}
              className="h-1 w-full cursor-pointer rounded-full bg-[color-mix(in_srgb,var(--text-primary)_10%,transparent)] accent-[var(--accent-strong)]" />
          </div>
          <div>
            <div className="flex justify-between px-0.5">
              <span className="text-[9px] font-black uppercase text-[var(--text-tertiary)]">전체높이</span>
              <span className={`text-[11px] font-black ${overHeight ? "text-[var(--status-error)]" : "text-[var(--status-info)]"}`}>{buildingHeight} m</span>
            </div>
            <input type="range" min={3} max={300} value={buildingHeight}
              onPointerDown={commitSnapshot}
              onChange={(e) => { setBuildingHeight(Number(e.target.value)); debouncedCheck(ring); }}
              className="h-1 w-full cursor-pointer rounded-full bg-[color-mix(in_srgb,var(--text-primary)_10%,transparent)] accent-[var(--status-info)]" />
          </div>
        </div>

        {/* 라이브 지표 */}
        <div className="mt-3 grid grid-cols-3 gap-2 border-t border-[var(--border-muted)] pt-3">
          <div>
            <p className="text-[8px] font-black uppercase tracking-wider text-[var(--text-tertiary)]">건축면적</p>
            <p className="text-[12px] font-black text-[var(--text-primary)]">{fmt(metrics.areaM2, "㎡")}</p>
          </div>
          <div>
            <p className="text-[8px] font-black uppercase tracking-wider text-[var(--text-tertiary)]">건폐율</p>
            <p className={`text-[12px] font-black ${overBcr ? "text-[var(--status-error)]" : "text-[var(--text-primary)]"}`}>
              {fmt(metrics.bcr, "%")}
              {limits.bcr != null && <span className="text-[8px] text-[var(--text-tertiary)]"> /{limits.bcr}</span>}
            </p>
          </div>
          <div>
            <p className="text-[8px] font-black uppercase tracking-wider text-[var(--text-tertiary)]">용적률</p>
            <p className={`text-[12px] font-black ${overFar ? "text-[var(--status-error)]" : "text-[var(--text-primary)]"}`}>
              {fmt(metrics.far, "%")}
              {limits.far != null && <span className="text-[8px] text-[var(--text-tertiary)]"> /{limits.far}</span>}
            </p>
          </div>
        </div>

        {/* 법규 위반(클라 힌트 + 백엔드 검증) */}
        {(hasViolationHint || violations.length > 0) ? (
          <div className="mt-3 rounded-[var(--r-input)] border border-[color-mix(in_srgb,var(--status-error)_25%,transparent)] bg-[color-mix(in_srgb,var(--status-error)_10%,transparent)] p-2.5">
            <p className="mb-1 text-[9px] font-black uppercase tracking-wider text-[var(--status-error)]">법규 초과 감지</p>
            {overBcr && <p className="text-[10px] leading-tight text-[var(--text-secondary)]">· 건폐율 {metrics.bcr?.toFixed(1)}% &gt; 상한 {limits.bcr}%</p>}
            {overFar && <p className="text-[10px] leading-tight text-[var(--text-secondary)]">· 용적률 {metrics.far?.toFixed(1)}% &gt; 상한 {limits.far}%</p>}
            {overHeight && <p className="text-[10px] leading-tight text-[var(--text-secondary)]">· 높이 {buildingHeight}m &gt; 상한 {limits.height}m</p>}
            {violations.slice(0, 2).map((v, i) => (
              <p key={i} className="text-[10px] leading-tight text-[var(--text-secondary)]">· {v.message}</p>
            ))}
          </div>
        ) : (
          <p className="mt-3 flex items-center gap-1.5 text-[10px] font-bold text-[var(--status-success)]">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
            법규 한도 충족 {limits.bcr == null && "(부지면적 연동 시 정밀)"}
          </p>
        )}
      </div>

      {/* ── 우하단: 선택/도움말 칩 ── */}
      <div className="absolute bottom-4 right-4 z-20 max-w-[220px] rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--glass-bg)] px-4 py-3 backdrop-blur-[var(--glass-blur)]">
        <p className="text-[9px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">
          현재 도구 · <span style={{ color: LAYER_COLORS[activeLayer] }}>{LAYER_LABELS[activeLayer]}</span>
        </p>
        <p className="text-[12px] font-black text-[var(--text-primary)]">{TOOLS.find((t) => t.key === tool)?.label}</p>
        <p className="mt-1.5 text-[10px] leading-tight text-[var(--text-secondary)]">
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
      <div className="absolute right-4 top-4 z-20 flex items-center gap-2 rounded-[var(--r-pill)] bg-[var(--glass-bg)] px-4 py-2 backdrop-blur-[var(--glass-blur)] border border-[var(--border-muted)]">
        <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--status-success)]" />
        <span className="text-[10px] font-black uppercase tracking-widest text-[var(--text-secondary)]">EPSG:5186 · 1px={(1 / scalePxPerM).toFixed(2)}m</span>
      </div>
    </div>
  );
}
