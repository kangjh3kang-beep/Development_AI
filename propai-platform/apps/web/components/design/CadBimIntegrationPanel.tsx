"use client";

import { useState, useEffect, useCallback } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Environment, Grid } from "@react-three/drei";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import * as THREE from "three";
import { motion } from "framer-motion";
import CADEditor from "./CADEditor";

// 도면 코드 → 한글 명칭 (SVGDrawingService.generate_full_drawing_set 기준)
const DRAWING_LABELS: Record<string, string> = {
  "B-01": "배치도",
  "B-02-STD": "기준층 평면도",
  "B-03": "단면도",
  "B-04-F": "정면도",
  "B-04-S": "측면도",
  "C-01": "투시도",
  "C-02": "음영 분석",
  "C-03": "상세도",
};

// v1 API base URL (apiClient와 동일 규칙). SVG는 텍스트라 직접 fetch.
function designApiBase(): string {
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host === "4t8t.net" || host === "www.4t8t.net" || host.endsWith(".pages.dev") || host === "propai.kr") {
      return "https://api.4t8t.net/api/v1";
    }
  }
  return "http://localhost:8000/api/v1";
}

// 백엔드가 생성한 IFC→glTF 모델을 렌더. scene이 없으면 격자만(로딩/실패 graceful).
function BuildingModel({ scene }: { scene: THREE.Group | null }) {
  return (
    <group position={[0, 0, 0]}>
      {scene && <primitive object={scene} />}
      <Grid
        infiniteGrid
        fadeDistance={50}
        sectionColor="var(--accent-strong)"
        cellColor="var(--line-strong)"
        cellThickness={0.5}
        sectionThickness={1.5}
        position={[0, 0, 0]}
        opacity={0.2}
      />
    </group>
  );
}

export function CadBimIntegrationPanel({ projectId, dictionary }: { projectId: string; dictionary: Record<string, string> }) {
  const [viewMode, setViewMode] = useState<"cad_2d" | "bim_3d">("bim_3d");
  const t = dictionary;

  // ── AI 생성 도면(SVG) 로딩 — 2D 뷰에서 실제 백엔드 도면을 표시 ──
  const [drawingCodes, setDrawingCodes] = useState<string[]>([]);
  const [activeCode, setActiveCode] = useState<string | null>(null);
  const [svgMap, setSvgMap] = useState<Record<string, string>>({});
  const [drawingLoading, setDrawingLoading] = useState(false);
  const [drawingError, setDrawingError] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);

  // ── 3D BIM 모델(IFC→glTF) 로딩 — 백엔드가 생성한 실제 매스 모델 ──
  const [bimScene, setBimScene] = useState<THREE.Group | null>(null);
  const [bimLoading, setBimLoading] = useState(false);
  const [bimError, setBimError] = useState<string | null>(null);

  const loadBimModel = useCallback(async () => {
    setBimLoading(true);
    setBimError(null);
    try {
      const base = designApiBase();
      const res = await fetch(`${base}/design/${encodeURIComponent(projectId)}/bim/model.glb`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // 매스 미지정 → 백엔드가 대지정보/기본값으로 자동 산출
        body: JSON.stringify({ floor_height_m: 3.0 }),
        signal: AbortSignal.timeout(60000),
      });
      if (!res.ok) throw new Error(`3D 모델 생성 실패 (${res.status})`);
      const buf = await res.arrayBuffer();
      const loader = new GLTFLoader();
      const gltf = await loader.parseAsync(buf, "");
      // 머티리얼 부여(백엔드 glb는 지오메트리만) + 중심 정렬
      gltf.scene.traverse((obj) => {
        if ((obj as THREE.Mesh).isMesh) {
          (obj as THREE.Mesh).material = new THREE.MeshStandardMaterial({
            color: "#5b9bd5",
            metalness: 0.3,
            roughness: 0.55,
            transparent: true,
            opacity: 0.92,
          });
        }
      });
      setBimScene(gltf.scene);
    } catch (err) {
      setBimError(err instanceof Error ? err.message : "3D 모델을 불러오지 못했습니다.");
    } finally {
      setBimLoading(false);
    }
  }, [projectId]);

  // 3D 뷰 진입 시 모델 1회 로드
  useEffect(() => {
    if (viewMode === "bim_3d" && !bimScene && !bimLoading && !bimError) {
      loadBimModel();
    }
  }, [viewMode, bimScene, bimLoading, bimError, loadBimModel]);

  // 도면 세트 목록 조회
  const loadDrawingSet = useCallback(async () => {
    setDrawingLoading(true);
    setDrawingError(null);
    try {
      const base = designApiBase();
      const res = await fetch(`${base}/design/${encodeURIComponent(projectId)}/generate-full-set`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ floor_count: 5, floor_height_m: 3.0, basement_floors: 1 }),
        signal: AbortSignal.timeout(60000),
      });
      if (!res.ok) throw new Error(`도면 생성 실패 (${res.status})`);
      const data = await res.json();
      const codes: string[] = Object.keys(data?.drawings ?? {}).filter(
        (c) => data.drawings[c]?.has_content,
      );
      setDrawingCodes(codes);
      setActiveCode((prev) => prev ?? codes[0] ?? null);
    } catch (err) {
      setDrawingError(err instanceof Error ? err.message : "도면을 불러오지 못했습니다.");
    } finally {
      setDrawingLoading(false);
    }
  }, [projectId]);

  // 개별 도면 SVG 조회(캐시)
  const loadSvg = useCallback(
    async (code: string) => {
      if (svgMap[code]) return;
      try {
        const base = designApiBase();
        const res = await fetch(`${base}/design/${encodeURIComponent(projectId)}/drawings/${code}/svg`, {
          signal: AbortSignal.timeout(60000),
        });
        if (!res.ok) return;
        const svg = await res.text();
        setSvgMap((m) => ({ ...m, [code]: svg }));
      } catch {
        // 개별 도면 실패는 무시(다른 도면은 정상 표시)
      }
    },
    [projectId, svgMap],
  );

  // 2D 뷰 진입 시 도면 세트 1회 로드
  useEffect(() => {
    if (viewMode === "cad_2d" && !editMode && drawingCodes.length === 0 && !drawingLoading && !drawingError) {
      loadDrawingSet();
    }
  }, [viewMode, editMode, drawingCodes.length, drawingLoading, drawingError, loadDrawingSet]);

  // 활성 도면 SVG 로드
  useEffect(() => {
    if (activeCode) loadSvg(activeCode);
  }, [activeCode, loadSvg]);

  return (
    <div className="flex flex-col gap-10">
      <div className="flex items-end justify-between px-2">
        <div className="space-y-4">
          <div className="flex items-center gap-3">
             <div className="h-2 w-10 rounded-full bg-[var(--accent-strong)]" />
             <h4 className="text-3xl font-[1000] tracking-tighter text-[var(--text-primary)] uppercase">{t.title || "CAD / BIM 통합 엔진"}</h4>
          </div>
          <p className="max-w-2xl text-sm font-medium leading-relaxed text-[var(--text-secondary)] italic underline decoration-[var(--line-strong)] decoration-2 underline-offset-8">
            {t.description || "2D 설계 도면과 3D BIM 데이터를 실시간으로 동기화하여 분석하는 가상 건설 환경입니다."}
          </p>
        </div>
        <div className="flex gap-2 rounded-[2rem] bg-[var(--surface-soft)] p-2 border border-[var(--line-strong)] shadow-[var(--shadow-lg)]">
          <button
            onClick={() => setViewMode("cad_2d")}
            className={`rounded-full px-8 py-3 text-[10px] font-black uppercase tracking-widest transition-all ${
              viewMode === "cad_2d" ? "bg-[var(--surface-strong)] text-[var(--accent-strong)] shadow-lg" : "text-[var(--text-hint)] hover:text-[var(--text-primary)]"
            }`}
          >
            {t.btn2D || "2D 도면"}
          </button>
          <button
            onClick={() => setViewMode("bim_3d")}
            className={`rounded-full px-8 py-3 text-[10px] font-black uppercase tracking-widest transition-all ${
              viewMode === "bim_3d" ? "bg-[var(--surface-strong)] text-[var(--accent-strong)] shadow-lg" : "text-[var(--text-hint)] hover:text-[var(--text-primary)]"
            }`}
          >
            {t.btn3D || "3D BIM"}
          </button>
        </div>
      </div>

      <div className="relative h-[650px] w-full overflow-hidden rounded-[4rem] border border-[var(--line-strong)] bg-[#0d1520] shadow-[var(--shadow-2xl)] group">
        {/* Cinematic Backdrop */}
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-black/20 to-black/60 pointer-events-none z-10" />
        
        {/* 3D Canvas or 2D SVG */}
        {viewMode === "bim_3d" ? (
          <div className="absolute inset-0">
            <Canvas camera={{ position: [25, 20, 25], fov: 40 }}>
              <ambientLight intensity={0.6} />
              <directionalLight position={[10, 20, 10]} intensity={1.2} />
              <pointLight position={[-10, 10, -10]} intensity={0.6} color="var(--info)" />
              <Environment preset="city" />
              <OrbitControls makeDefault autoRotate={!bimScene} autoRotateSpeed={0.3} enableDamping dampingFactor={0.05} />
              <BuildingModel scene={bimScene} />
            </Canvas>
            {/* 로딩/에러 오버레이 */}
            {(bimLoading || bimError) && (
              <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/30 pointer-events-none">
                {bimLoading ? (
                  <div className="flex flex-col items-center gap-4">
                    <div className="h-12 w-12 animate-spin rounded-full border-4 border-[var(--accent-strong)] border-t-transparent" />
                    <p className="text-[11px] font-bold uppercase tracking-widest text-white/60">3D BIM 모델 생성 중...</p>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-3 text-center pointer-events-auto">
                    <p className="text-sm font-bold text-red-300">{bimError}</p>
                    <button
                      onClick={() => { setBimError(null); loadBimModel(); }}
                      className="rounded-full bg-white/10 px-6 py-2 text-[11px] font-black uppercase tracking-widest text-white hover:bg-white/20"
                    >
                      다시 시도
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        ) : editMode ? (
          <div className="absolute inset-0 z-30 bg-[#0a0f14] flex flex-col overflow-hidden [&>div]:h-full [&>div]:rounded-none [&>div]:border-none">
            <CADEditor projectId={projectId} />
          </div>
        ) : (
          <div className="absolute inset-0 z-30 bg-[#0a0f14] flex flex-col">
            {/* 상단 바: 도면 탭 + 편집모드 전환 */}
            <div className="flex items-center justify-between gap-3 border-b border-white/5 px-6 py-3 overflow-x-auto">
              <div className="flex gap-2">
                {drawingCodes.map((code) => (
                  <button
                    key={code}
                    onClick={() => setActiveCode(code)}
                    className={`whitespace-nowrap rounded-full px-4 py-2 text-[10px] font-black uppercase tracking-widest transition-all ${
                      activeCode === code
                        ? "bg-[var(--accent-strong)] text-white shadow-lg"
                        : "bg-white/5 text-white/50 hover:text-white"
                    }`}
                  >
                    {DRAWING_LABELS[code] || code}
                  </button>
                ))}
              </div>
              <button
                onClick={() => setEditMode(true)}
                className="shrink-0 rounded-full border border-white/10 px-4 py-2 text-[10px] font-black uppercase tracking-widest text-[var(--accent-strong)] hover:bg-white/5"
              >
                편집 모드
              </button>
            </div>

            {/* 도면 표시 영역 */}
            <div className="relative flex-1 flex items-center justify-center overflow-auto p-8">
              {drawingLoading && (
                <div className="flex flex-col items-center gap-4">
                  <div className="h-12 w-12 animate-spin rounded-full border-4 border-[var(--accent-strong)] border-t-transparent" />
                  <p className="text-[11px] font-bold uppercase tracking-widest text-white/40">AI 도면 생성 중...</p>
                </div>
              )}
              {!drawingLoading && drawingError && (
                <div className="flex flex-col items-center gap-4 text-center">
                  <p className="text-sm font-bold text-red-400">{drawingError}</p>
                  <button
                    onClick={() => { setDrawingError(null); setDrawingCodes([]); }}
                    className="rounded-full bg-white/10 px-6 py-2 text-[11px] font-black uppercase tracking-widest text-white hover:bg-white/20"
                  >
                    다시 시도
                  </button>
                </div>
              )}
              {!drawingLoading && !drawingError && activeCode && svgMap[activeCode] && (
                <div
                  className="max-h-full max-w-full rounded-2xl bg-white p-4 shadow-2xl [&>svg]:h-auto [&>svg]:max-h-[480px] [&>svg]:w-auto [&>svg]:max-w-full"
                  // SVG는 백엔드 SVGDrawingService가 생성한 신뢰 가능한 자체 컨텐츠
                  dangerouslySetInnerHTML={{ __html: svgMap[activeCode] }}
                />
              )}
              {!drawingLoading && !drawingError && activeCode && !svgMap[activeCode] && (
                <div className="h-10 w-10 animate-spin rounded-full border-4 border-[var(--accent-strong)] border-t-transparent" />
              )}
            </div>
          </div>
        )}

        {/* Overlay Tools (only for 3D) */}
        {viewMode === "bim_3d" && (
          <>
            <div className="absolute right-10 top-10 flex flex-col gap-4 z-20">
              <motion.div 
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                className="rounded-[2.5rem] border border-white/5 bg-black/60 p-8 text-white backdrop-blur-2xl shadow-2xl"
              >
                <div className="flex items-center gap-3 mb-4">
                  <div className="h-1.5 w-1.5 rounded-full bg-[var(--success)] shadow-[0_0_10px_var(--success)] animate-pulse" />
                  <p className="text-[10px] font-black uppercase tracking-[0.4em] opacity-50">{t.legalCheck || "BIM CHECKLIST"}</p>
                </div>
                <div className="space-y-2">
                  <span className="block text-xl font-[1000] tracking-tighter italic">{t.compliant || "법규 적합성 통과"}</span>
                  <p className="text-[10px] font-bold opacity-40 italic underline decoration-white/20 underline-offset-4">{t.autoCorrected || "AI 자동 보정 기능 활성화됨"}</p>
                </div>
              </motion.div>
              
              <button className="group relative overflow-hidden rounded-[2rem] bg-white px-10 py-5 text-xs font-black text-[#0d1520] uppercase tracking-widest shadow-[var(--shadow-glow)] transition-all hover:scale-105 hover:bg-[var(--accent-strong)] hover:text-white active:scale-95">
                <span className="relative z-10 flex items-center gap-3">
                  {t.exportBtn || "3D 모델 데이터 내보내기"}
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M7 17L17 7M17 7H7M17 7V17"/></svg>
                </span>
              </button>
            </div>
            
            {/* HUD Bottom Left */}
            <div className="absolute bottom-10 left-10 z-20 flex items-center gap-6">
              <div className="flex h-12 items-center gap-4 rounded-2xl bg-black/40 px-6 backdrop-blur-xl border border-white/5">
                  <span className="h-2 w-2 rounded-full bg-blue-500 shadow-[0_0_10px_#3b82f6]" />
                  <span className="text-[9px] font-black text-white/50 uppercase tracking-[0.3em]">Telemetry Streaming</span>
              </div>
              <div className="flex h-12 items-center gap-4 rounded-2xl bg-black/40 px-6 backdrop-blur-xl border border-white/5">
                  <span className="text-[9px] font-black text-white/50 uppercase tracking-[0.3em]">FOV: 40°</span>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
