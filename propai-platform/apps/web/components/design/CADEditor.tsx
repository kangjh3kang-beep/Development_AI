"use client";

import React, { useState, useCallback, useRef, useEffect } from "react";
import type Konva from "konva";

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
            if (prop === "ReactCurrentOwner") return client.ReactCurrentOwner;
            return target[prop];
          },
        });
        Object.defineProperty(anyReact, "__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED", {
          get: () => proxy,
          configurable: true,
        });
      } catch (e) {
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

/* ───────────── 타입 정의 ───────────── */
interface DesignPoint {
  id: string;
  x: number;
  y: number;
}

interface DesignLine {
  id: string;
  start_point_id: string;
  end_point_id: string;
}

interface DesignSurface {
  id: string;
  point_ids: string[];
}

interface ComplianceViolation {
  type: string;
  message: string;
  severity: "error" | "warning";
  current_value: number;
  limit_value: number;
}

interface CorrectionAlternative {
  alternative_id: string;
  description: string;
  corrected_design: Record<string, unknown>;
  estimated_cost_change_krw: number;
  far_after: number;
  bcr_after: number;
}

interface CADEditorProps {
  projectId: string;
  apiBaseUrl?: string;
  width?: number;
  height?: number;
  gridSize?: number;
  snapGrid?: boolean;
}

/* ───────────── 상수 ───────────── */
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DEBOUNCE_MS = Number(
  process.env.NEXT_PUBLIC_COMPLIANCE_DEBOUNCE_MS ?? "500"
);
const GRID_STEP = 20; // px

/* ───────────── 컴포넌트 ───────────── */
export default function CADEditor({
  projectId,
  apiBaseUrl = API_BASE,
  width = 800,
  height = 600,
  gridSize = GRID_STEP,
  snapGrid = true,
}: CADEditorProps) {
  /* ── 상태 ── */
  const [points, setPoints] = useState<DesignPoint[]>([
    { id: "p1", x: 100, y: 100 },
    { id: "p2", x: 400, y: 100 },
    { id: "p3", x: 400, y: 350 },
    { id: "p4", x: 100, y: 350 },
  ]);
  const [lines] = useState<DesignLine[]>([
    { id: "l1", start_point_id: "p1", end_point_id: "p2" },
    { id: "l2", start_point_id: "p2", end_point_id: "p3" },
    { id: "l3", start_point_id: "p3", end_point_id: "p4" },
    { id: "l4", start_point_id: "p4", end_point_id: "p1" },
  ]);
  const [surfaces] = useState<DesignSurface[]>([
    { id: "s1", point_ids: ["p1", "p2", "p3", "p4"] },
  ]);
  const [violations, setViolations] = useState<ComplianceViolation[]>([]);
  const [alternatives, setAlternatives] = useState<CorrectionAlternative[]>([]);
  const [isChecking, setIsChecking] = useState(false);
  const [floorCount, setFloorCount] = useState(5);
  const [buildingHeight, setBuildingHeight] = useState(15);
  const [isReady, setIsReady] = useState(false);
  const [rk, setRK] = useState<any>(null);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [loadedVersion, setLoadedVersion] = useState<number | null>(null);

  // 편집 도면 저장(design_versions 영속화)
  const handleSave = useCallback(async () => {
    setSaveStatus("saving");
    try {
      const res = await fetch(
        `${apiBaseUrl}/api/v1/design/${encodeURIComponent(projectId)}/drawings/save`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            drawing_code: "CAD-EDIT",
            drawing_type: "평면도",
            points: points.map((p) => ({ id: p.id, x: p.x, y: p.y })),
            lines,
            surfaces,
            floor_count: floorCount,
            building_height_m: buildingHeight,
          }),
          signal: AbortSignal.timeout(30000),
        }
      );
      if (!res.ok) throw new Error(`저장 실패 ${res.status}`);
      const d = await res.json();
      setSaveStatus("saved");
      const m = /v(\d+)/.exec(d?.status || "");
      if (m) setLoadedVersion(Number(m[1]));
      setTimeout(() => setSaveStatus("idle"), 2500);
    } catch {
      setSaveStatus("error");
      setTimeout(() => setSaveStatus("idle"), 3000);
    }
  }, [apiBaseUrl, projectId, points, lines, surfaces, floorCount, buildingHeight]);

  // 마운트 시 저장된 편집본 로드(있으면 좌표 복원)
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(
          `${apiBaseUrl}/api/v1/design/${encodeURIComponent(projectId)}/drawings/load`,
          { signal: AbortSignal.timeout(20000) }
        );
        if (!res.ok) return;
        const d = await res.json();
        if (!cancelled && d?.saved && Array.isArray(d.data?.points) && d.data.points.length >= 3) {
          setPoints(d.data.points.map((p: any) => ({ id: String(p.id), x: Number(p.x), y: Number(p.y) })));
          setLoadedVersion(d.version ?? null);
        }
      } catch {
        /* 로드 실패 무시 — 기본 도형 사용 */
      }
    })();
    return () => { cancelled = true; };
  }, [apiBaseUrl, projectId]);

  useEffect(() => {
    applyShim();
    try {
      const modules = require("react-konva");
      setRK(modules);
    } catch (e) {
      console.error("[CADEditor] Failed to load react-konva:", e);
    }
    setIsReady(true);
  }, []);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /* ── 스냅 ── */
  const snap = useCallback(
    (v: number) => (snapGrid ? Math.round(v / gridSize) * gridSize : v),
    [snapGrid, gridSize]
  );

  /* ── 법규 검증 API 호출 ── */
  const checkCompliance = useCallback(
    async (pts: DesignPoint[]) => {
      setIsChecking(true);
      try {
        const body = {
          project_id: projectId,
          design: {
            points: pts.map((p) => ({ id: p.id, x: p.x, y: p.y })),
            lines,
            surfaces,
            floor_count: floorCount,
            building_height_m: buildingHeight,
            scale: 10.0,
          },
        };
        const res = await fetch(
          `${apiBaseUrl}/api/v1/building-compliance/check`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }
        );
        const data = await res.json();
        setViolations(data.violations ?? []);
      } catch (err) {
        console.error("[CADEditor] 법규 검증 API 오류:", err);
      } finally {
        setIsChecking(false);
      }
    },
    [projectId, apiBaseUrl, lines, surfaces, floorCount, buildingHeight]
  );

  /* ── 자동 보정 API 호출 ── */
  const requestAutoCorrect = useCallback(
    async (violationType: string) => {
      try {
        const body = {
          project_id: projectId,
          design: {
            points: points.map((p) => ({ id: p.id, x: p.x, y: p.y })),
            lines,
            surfaces,
            floor_count: floorCount,
            building_height_m: buildingHeight,
            scale: 10.0,
          },
          violation_type: violationType,
        };
        const res = await fetch(
          `${apiBaseUrl}/api/v1/building-compliance/auto-correct`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }
        );
        const data = await res.json();
        setAlternatives(data.alternatives ?? []);
      } catch (err) {
        console.error("[CADEditor] 자동 보정 API 오류:", err);
      }
    },
    [projectId, apiBaseUrl, points, lines, surfaces, floorCount, buildingHeight]
  );

  /* ── 디바운스 검증 ── */
  const debouncedCheck = useCallback(
    (pts: DesignPoint[]) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => checkCompliance(pts), DEBOUNCE_MS);
    },
    [checkCompliance]
  );

  /* ── 초기 검증 ── */
  useEffect(() => {
    if (isReady) {
      checkCompliance(points);
    }
  }, [isReady, points, checkCompliance]);

  /* ── 포인트 드래그 핸들러 ── */
  const handleDragEnd = useCallback(
    (idx: number, e: Konva.KonvaEventObject<DragEvent>) => {
      const newX = snap(e.target.x());
      const newY = snap(e.target.y());
      setPoints((prev) => {
        const next = [...prev];
        next[idx] = { ...next[idx], x: newX, y: newY };
        debouncedCheck(next);
        return next;
      });
    },
    [snap, debouncedCheck]
  );

  /* ── 렌더링 ── */
  if (!isReady || !rk) return (
    <div className="flex h-[600px] w-full items-center justify-center rounded-[2.5rem] bg-[#0a0f14] text-white">
      <div className="flex flex-col items-center gap-4">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-teal-500 border-t-transparent" />
        <p className="text-xs font-black uppercase tracking-[0.2em] text-teal-400">Initializing AI Engine...</p>
      </div>
    </div>
  );

  const { Stage, Layer, Group, Line, Circle, Text, Rect } = rk;

  /* ── 포인트 맵 ── */
  const pointMap: Record<string, DesignPoint> = Object.fromEntries(
    points.map((p) => [p.id, p])
  );

  const surfaceCoords = surfaces.flatMap((s) =>
    s.point_ids
      .filter((pid) => pointMap[pid])
      .flatMap((pid) => [pointMap[pid].x, pointMap[pid].y])
  );

  const lineElems = lines.map((l) => {
    const sp = pointMap[l.start_point_id];
    const ep = pointMap[l.end_point_id];
    if (!sp || !ep) return null;
    return (
      <Line
        key={l.id}
        points={[sp.x, sp.y, ep.x, ep.y]}
        stroke="#2dd4bf"
        strokeWidth={3}
        shadowBlur={10}
        shadowColor="#2dd4bf"
      />
    );
  });

  return (
    <div className="relative h-[800px] w-full overflow-hidden rounded-[3rem] border border-white/10 bg-[#0a0f14] shadow-2xl">
      {/* ── Grid/Scanline Layer ── */}
      <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.03)_1px,transparent_1px)] bg-[size:20px_20px]" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,#0a0f14_80%)]" />

      {/* ── Canvas Layer (Konva) ── */}
      <div className="absolute inset-0 flex items-center justify-center cursor-crosshair">
        <Stage width={width} height={height}>
          <Layer>
            {/* 면 (반투명 채움) */}
            {surfaceCoords.length >= 6 && (
              <Line
                points={surfaceCoords}
                closed
                fill="rgba(45,212,191,0.08)"
                stroke="#2dd4bf"
                strokeWidth={1}
                dash={[5, 5]}
              />
            )}

            {/* 선 */}
            {lineElems}

            {/* 점 (드래그 가능) */}
            {points.map((p, idx) => (
              <Group key={p.id}>
                {/* Outer Glow */}
                <Circle x={p.x} y={p.y} radius={12} fill="rgba(45,212,191,0.1)" />
                <Circle
                  x={p.x}
                  y={p.y}
                  radius={6}
                  fill="#ffffff"
                  stroke="#2dd4bf"
                  strokeWidth={3}
                  draggable
                  onDragEnd={(e: Konva.KonvaEventObject<DragEvent>) => handleDragEnd(idx, e)}
                  onMouseEnter={(e: Konva.KonvaEventObject<MouseEvent>) => {
                    const container = e.target.getStage()?.container();
                    if (container) container.style.cursor = "move";
                    (e.target as Konva.Circle).radius(8);
                  }}
                  onMouseLeave={(e: Konva.KonvaEventObject<MouseEvent>) => {
                    const container = e.target.getStage()?.container();
                    if (container) container.style.cursor = "crosshair";
                    (e.target as Konva.Circle).radius(6);
                  }}
                />
                <Text
                  x={p.x + 12}
                  y={p.y - 12}
                  text={p.id.toUpperCase()}
                  fontSize={10}
                  fontStyle="900"
                  fill="#2dd4bf"
                  fontFamily="Inter, sans-serif"
                />
              </Group>
            ))}
          </Layer>
        </Stage>
      </div>

      {/* ── HUD Left: Build Stats ── */}
      <div className="absolute left-8 top-8 w-[320px] space-y-4">
        <div className="glass rounded-[2rem] p-6 border border-white/10">
           <div className="flex items-center gap-3 mb-6">
              <div className="h-10 w-10 rounded-full bg-teal-500/20 flex items-center justify-center text-teal-400">
                 <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2v20"/><path d="m5 15 7-7 7 7"/></svg>
              </div>
              <div>
                <h4 className="text-sm font-black text-white uppercase tracking-widest">Building Geometry</h4>
                <p className="text-[10px] text-white/40 font-bold italic tracking-tighter">Real-time Constraints Active</p>
              </div>
           </div>

           <div className="space-y-4">
              <div className="flex flex-col gap-2">
                 <div className="flex justify-between px-1">
                   <span className="text-[10px] font-black text-white/40 uppercase">Floor Count</span>
                   <span className="text-xs font-black text-teal-400">{floorCount} F</span>
                 </div>
                 <input 
                   type="range" min="1" max="30" value={floorCount} 
                   onChange={(e) => { setFloorCount(Number(e.target.value)); debouncedCheck(points); }}
                   className="h-1 w-full bg-white/10 rounded-full accent-teal-400 cursor-pointer"
                 />
              </div>
              <div className="flex flex-col gap-2">
                 <div className="flex justify-between px-1">
                   <span className="text-[10px] font-black text-white/40 uppercase">Total Height</span>
                   <span className="text-xs font-black text-blue-400">{buildingHeight} m</span>
                 </div>
                 <input 
                   type="range" min="3" max="150" value={buildingHeight} 
                   onChange={(e) => { setBuildingHeight(Number(e.target.value)); debouncedCheck(points); }}
                   className="h-1 w-full bg-white/10 rounded-full accent-blue-400 cursor-pointer"
                 />
              </div>
           </div>
        </div>

        {/* AI Compliance Ticker */}
        <div className="glass rounded-[2rem] p-6 border border-white/5 bg-black/40">
           <div className="flex items-center justify-between mb-4">
              <span className="text-[10px] font-black text-white/40 uppercase tracking-[0.2em]">Compliance Monitor</span>
              {isChecking ? (
                 <span className="flex h-2 w-2 rounded-full bg-amber-500 animate-pulse" />
              ) : (
                 <span className="flex h-2 w-2 rounded-full bg-teal-500" />
              )}
           </div>
           
           {violations.length === 0 ? (
              <p className="text-xs font-bold text-teal-400 flex items-center gap-2">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                모든 법규 조건을 충족합니다
              </p>
           ) : (
              <div className="space-y-3">
                 {violations.slice(0, 2).map((v, i) => (
                    <div key={i} className="rounded-xl border border-rose-500/20 bg-rose-500/5 p-3">
                       <p className="text-[10px] font-black text-rose-400 uppercase mb-1">{v.type}</p>
                       <p className="text-[11px] leading-tight text-white/70">{v.message}</p>
                    </div>
                 ))}
                 {violations.length > 2 && <p className="text-[9px] text-center text-white/30 font-black italic">외 {violations.length - 2}건의 위반 사항 검출</p>}
              </div>
           )}
        </div>
      </div>

      {/* ── HUD Right: AI Recommendations ── */}
      <div className="absolute right-8 top-8 w-[360px] space-y-4">
         <div className="glass rounded-[2.5rem] p-8 border border-white/10 shadow-2xl">
            <h4 className="text-lg font-black text-white tracking-tight mb-6 flex items-center gap-3">
               <span className="h-8 w-8 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-xs">AI</span>
               최적화 제안
            </h4>

            {alternatives.length === 0 ? (
               <div className="py-8 flex flex-col items-center text-center gap-3">
                  <div className="h-12 w-12 rounded-2xl bg-white/5 flex items-center justify-center text-white/20">
                     <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m12 3-1.912 5.813a2 2 0 0 0 1.275 1.275L21 12l-5.813 1.912a2 2 0 0 0-1.275 1.275L12 21l-1.912-5.813a2 2 0 0 0-1.275-1.275L3 12l5.813-1.912a2 2 0 0 0 1.275-1.275L12 3Z"/></svg>
                  </div>
                  <p className="text-xs font-medium text-white/40 leading-relaxed italic">
                    포인트를 드래그하여 설계를 수정하면<br/>AI가 법규 준수 대안을 생성합니다.
                  </p>
               </div>
            ) : (
               <div className="space-y-4">
                  {alternatives.map((alt) => (
                    <div key={alt.alternative_id} className="group relative rounded-2xl border border-white/5 bg-white/5 p-5 transition-all hover:border-teal-500/50 hover:bg-teal-500/5 cursor-pointer"
                      onClick={() => {
                        const cd = alt.corrected_design as any;
                        if (cd.points) setPoints(cd.points);
                        if (cd.building_height_m) setBuildingHeight(cd.building_height_m);
                        setAlternatives([]);
                      }}
                    >
                       <div className="flex items-center justify-between mb-3">
                          <span className="text-[10px] font-black text-teal-400 uppercase tracking-widest">Alternative #{alt.alternative_id}</span>
                          <span className="rounded-full bg-teal-500/20 px-2 py-0.5 text-[9px] font-black text-teal-400">Score 98+</span>
                       </div>
                       <p className="text-xs font-bold text-white/90 mb-2">{alt.description}</p>
                       <div className="flex gap-4 text-[9px] font-black text-white/40 uppercase">
                          <span>BCR: {(alt.bcr_after * 100).toFixed(1)}%</span>
                          <span>FAR: {(alt.far_after * 100).toFixed(1)}%</span>
                       </div>
                    </div>
                  ))}
               </div>
            )}
         </div>

         {/* Design Tools Bar */}
         <div className="flex gap-2 justify-center">
            {['SELECT', 'POINT', 'POLY', 'DIM'].map((tool) => (
              <button key={tool} className="h-12 flex-1 rounded-2xl border border-white/10 bg-[#0a0f14] text-[9px] font-black text-white/40 hover:text-white hover:border-teal-500 transition-all uppercase tracking-widest">
                {tool}
              </button>
            ))}
         </div>

         {/* 저장 버튼 — 편집한 도면을 design_versions에 영속화 */}
         <button
           onClick={handleSave}
           disabled={saveStatus === "saving"}
           className={`h-12 w-full rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all disabled:opacity-60 ${
             saveStatus === "saved"
               ? "bg-emerald-500 text-white"
               : saveStatus === "error"
                 ? "bg-red-500/80 text-white"
                 : "bg-teal-500 text-white hover:bg-teal-400"
           }`}
         >
           {saveStatus === "saving" ? "저장 중..."
             : saveStatus === "saved" ? `✓ 저장됨${loadedVersion ? ` (v${loadedVersion})` : ""}`
             : saveStatus === "error" ? "저장 실패 — 재시도"
             : `편집 도면 저장${loadedVersion ? ` (현재 v${loadedVersion})` : ""}`}
         </button>
      </div>

      {/* ── Bottom HUD: Coordinate System ── */}
      <div className="absolute bottom-8 left-1/2 -translate-x-1/2 flex items-center gap-6 rounded-full bg-[#0a0f14]/80 backdrop-blur-xl border border-white/10 px-8 py-3 shadow-2xl">
         <div className="flex items-center gap-2">
            <span className="text-[9px] font-black text-white/30 uppercase tracking-widest">Project Space</span>
            <span className="text-xs font-black text-white">EPSG:5186 (GRS80)</span>
         </div>
         <div className="w-px h-3 bg-white/10" />
         <div className="flex items-center gap-2 px-2">
           <div className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
           <span className="text-[10px] font-black text-white/70 uppercase">Linked Database</span>
         </div>
      </div>
    </div>
  );
}
