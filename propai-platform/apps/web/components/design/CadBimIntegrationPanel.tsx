"use client";

import { useState, useEffect, useCallback } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Grid } from "@react-three/drei";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import * as THREE from "three";
import { motion } from "framer-motion";
import CADEditor from "./CADEditor";
import { useProjectContextStore } from "@/store/useProjectContextStore";

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

const r2 = (n: number) => Math.round(n * 100) / 100;

// 건축물 용도 → 백엔드 building_use 매핑(세대/평면 배치에 사용)
function mapUse(bt?: string | null): string {
  const s = (bt || "").toString();
  if (/오피스텔/.test(s)) return "오피스텔";
  if (/상가|근린|판매|업무|오피스(?!텔)/.test(s)) return "상가";
  return "공동주택";
}

/** CAD 2D·3D BIM이 공유하는 단일 건축 기하(선택한 건축개요에서 파생). */
interface DesignSpec {
  building_width_m: number;
  building_depth_m: number;
  floor_count: number;
  floor_height_m: number;
  site_width_m: number;
  site_depth_m: number;
  setback_m: number;
  unit_width_m: number;
  basement_floors: number;
  land_area_sqm?: number;
  zone_code: string;
  building_use: string;
  building_type?: string | null;
  gfa?: number | null;
  bcr?: number | null;
  far?: number | null;
  total_units?: number | null;
  project_name: string;
}

// 백엔드가 생성한 IFC→glTF 모델을 렌더. scene이 없으면 격자만(로딩/실패 graceful).
function BuildingModel({ scene }: { scene: THREE.Group | null }) {
  return (
    <group position={[0, 0, 0]}>
      {scene && <primitive object={scene} />}
      <Grid
        infiniteGrid
        fadeDistance={50}
        sectionColor="#2dd4bf"
        cellColor="#334155"
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

  // 선택한 건축개요(모세혈관 스토어) — CAD/BIM 기하의 단일 출처
  const designData = useProjectContextStore((s) => s.designData);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);

  // 공용 건축 기하(spec) — /mass로 1회 산출 후 2D·3D가 공유
  const [spec, setSpec] = useState<DesignSpec | null>(null);
  const [specLoading, setSpecLoading] = useState(false);

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
  // AI 설계 해석(DesignInterpreter 6섹션) + 매스 메타
  const [designAi, setDesignAi] = useState<Record<string, string> | null>(null);
  const [bimMass, setBimMass] = useState<Record<string, unknown> | null>(null);

  // ── 공용 기하 산출: 선택한 건축개요(GFA·층수) 우선, 없으면 대지+용도지역으로 자동 ──
  const resolveSpec = useCallback(async () => {
    setSpecLoading(true);
    const base = designApiBase();
    const landArea = siteAnalysis?.landAreaSqm || undefined;
    const zone = siteAnalysis?.zoneCode || "2R";
    const use = mapUse(designData?.buildingType);
    const floors = designData?.floorCount || undefined;
    const gfa = designData?.totalGfaSqm || undefined;

    // 선택한 개요(GFA+층수)가 있으면 footprint를 역산해 명시 매스로 고정(CAD↔BIM 일치)
    let body: Record<string, unknown>;
    if (gfa && floors) {
      const footprint = gfa / floors;
      const depth = Math.max(8, Math.min(40, Math.sqrt(footprint / 1.6)));
      const width = Math.max(8, footprint / depth);
      body = {
        building_width_m: r2(width), building_depth_m: r2(depth), floor_count: floors,
        floor_height_m: 3.0, land_area_sqm: landArea, zone_code: zone,
      };
    } else {
      body = { land_area_sqm: landArea, zone_code: zone, floor_count: floors, floor_height_m: 3.0 };
    }

    const fallback: DesignSpec = {
      building_width_m: 40, building_depth_m: 20, floor_count: floors || 5, floor_height_m: 3.0,
      site_width_m: 46, site_depth_m: 26, setback_m: 3, unit_width_m: 8, basement_floors: 1,
      land_area_sqm: landArea, zone_code: zone, building_use: use, building_type: designData?.buildingType ?? null,
      gfa: gfa ?? null, bcr: designData?.bcr ?? null, far: designData?.far ?? null,
      total_units: null, project_name: "PropAI",
    };

    try {
      const res = await fetch(`${base}/design/${encodeURIComponent(projectId)}/mass`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(30000),
      });
      if (!res.ok) throw new Error(String(res.status));
      const m = await res.json();
      setSpec({
        building_width_m: m.building_width_m, building_depth_m: m.building_depth_m,
        floor_count: m.num_floors, floor_height_m: m.floor_height_m,
        site_width_m: m.site_width_m, site_depth_m: m.site_depth_m,
        setback_m: m.setback_m ?? 3, unit_width_m: m.unit_width_m ?? 8, basement_floors: 1,
        land_area_sqm: landArea, zone_code: zone, building_use: use,
        building_type: designData?.buildingType ?? null,
        gfa: gfa ?? null,
        bcr: designData?.bcr ?? m.bcr_pct ?? null,
        far: designData?.far ?? m.far_pct ?? null,
        total_units: m.total_units ?? null, project_name: "PropAI",
      });
    } catch {
      setSpec(fallback);
    } finally {
      setSpecLoading(false);
    }
  }, [projectId, designData, siteAnalysis]);

  // 마운트 시 1회 기하 산출
  useEffect(() => {
    if (!spec && !specLoading) resolveSpec();
  }, [spec, specLoading, resolveSpec]);

  // spec → /mass·BIM 요청 바디(명시 매스로 2D와 동일 기하 강제)
  const bimBody = useCallback(() => JSON.stringify({
    building_width_m: spec?.building_width_m,
    building_depth_m: spec?.building_depth_m,
    floor_count: spec?.floor_count,
    floor_height_m: spec?.floor_height_m ?? 3.0,
    land_area_sqm: spec?.land_area_sqm,
    zone_code: spec?.zone_code ?? "2R",
    project_name: spec?.project_name ?? "PropAI",
  }), [spec]);

  // spec → 도면(generate-full-set) 요청 바디
  const drawingBody = useCallback(() => JSON.stringify({
    site_width_m: spec?.site_width_m, site_depth_m: spec?.site_depth_m,
    building_width_m: spec?.building_width_m, building_depth_m: spec?.building_depth_m,
    floor_count: spec?.floor_count, floor_height_m: spec?.floor_height_m ?? 3.0,
    basement_floors: spec?.basement_floors ?? 1, unit_width_m: spec?.unit_width_m ?? 8,
    setback_m: spec?.setback_m ?? 3, project_name: spec?.project_name ?? "PropAI",
  }), [spec]);

  // spec → 개별 도면 SVG(GET) 쿼리스트링(2D·3D 동일 기하 공유)
  const svgQuery = useCallback(() => {
    if (!spec) return "";
    const q = new URLSearchParams({
      site_width_m: String(spec.site_width_m), site_depth_m: String(spec.site_depth_m),
      building_width_m: String(spec.building_width_m), building_depth_m: String(spec.building_depth_m),
      floor_count: String(spec.floor_count), floor_height_m: String(spec.floor_height_m),
      basement_floors: String(spec.basement_floors), unit_width_m: String(spec.unit_width_m),
      setback_m: String(spec.setback_m), project_name: spec.project_name,
    });
    return `?${q.toString()}`;
  }, [spec]);

  const loadBimModel = useCallback(async () => {
    if (!spec) return;
    setBimLoading(true);
    setBimError(null);
    const base = designApiBase();
    const reqBody = bimBody();

    // (1) AI 설계해석 + 메타는 병렬로(실패해도 3D는 표시)
    fetch(`${base}/design/${encodeURIComponent(projectId)}/bim/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: reqBody,
      signal: AbortSignal.timeout(90000),
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d?.ai_interpretation) setDesignAi(d.ai_interpretation);
        if (d?.mass) setBimMass(d.mass);
      })
      .catch(() => { /* 해석 실패는 무시 — 3D 모델은 별도로 로드됨 */ });

    // (2) 3D glb 모델 로드
    try {
      const res = await fetch(`${base}/design/${encodeURIComponent(projectId)}/bim/model.glb`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: reqBody,
        signal: AbortSignal.timeout(60000),
      });
      if (!res.ok) throw new Error(`3D 모델 생성 실패 (${res.status})`);
      const buf = await res.arrayBuffer();
      const loader = new GLTFLoader();
      const gltf = await loader.parseAsync(buf, "");
      gltf.scene.traverse((obj) => {
        if ((obj as THREE.Mesh).isMesh) {
          (obj as THREE.Mesh).castShadow = true;
          (obj as THREE.Mesh).receiveShadow = true;
        }
      });
      setBimScene(gltf.scene);
    } catch (err) {
      setBimError(err instanceof Error ? err.message : "3D 모델을 불러오지 못했습니다.");
    } finally {
      setBimLoading(false);
    }
  }, [projectId, spec, bimBody]);

  // 3D 뷰 진입 시(기하 준비 후) 모델 1회 로드
  useEffect(() => {
    if (viewMode === "bim_3d" && spec && !bimScene && !bimLoading && !bimError) {
      loadBimModel();
    }
  }, [viewMode, spec, bimScene, bimLoading, bimError, loadBimModel]);

  // 도면 세트 목록 조회
  const loadDrawingSet = useCallback(async () => {
    if (!spec) return;
    setDrawingLoading(true);
    setDrawingError(null);
    try {
      const base = designApiBase();
      const res = await fetch(`${base}/design/${encodeURIComponent(projectId)}/generate-full-set`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: drawingBody(),
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
  }, [projectId, spec, drawingBody]);

  // 개별 도면 SVG 조회(캐시)
  const loadSvg = useCallback(
    async (code: string) => {
      if (svgMap[code] || !spec) return;
      try {
        const base = designApiBase();
        const res = await fetch(`${base}/design/${encodeURIComponent(projectId)}/drawings/${code}/svg${svgQuery()}`, {
          signal: AbortSignal.timeout(60000),
        });
        if (!res.ok) return;
        const svg = await res.text();
        setSvgMap((m) => ({ ...m, [code]: svg }));
      } catch {
        // 개별 도면 실패는 무시(다른 도면은 정상 표시)
      }
    },
    [projectId, svgMap, spec, svgQuery],
  );

  // 2D 뷰 진입 시(기하 준비 후) 도면 세트 1회 로드 + AI 설계해석
  useEffect(() => {
    if (viewMode === "cad_2d" && !editMode && spec && drawingCodes.length === 0 && !drawingLoading && !drawingError) {
      loadDrawingSet();
    }
    if (viewMode === "cad_2d" && !editMode && spec && !designAi) {
      const base = designApiBase();
      fetch(`${base}/design/${encodeURIComponent(projectId)}/bim/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: bimBody(),
        signal: AbortSignal.timeout(90000),
      })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => { if (d?.ai_interpretation) setDesignAi(d.ai_interpretation); })
        .catch(() => { /* 무시 */ });
    }
  }, [viewMode, editMode, spec, drawingCodes.length, drawingLoading, drawingError, loadDrawingSet, designAi, projectId, bimBody]);

  // 활성 도면 SVG 로드
  useEffect(() => {
    if (activeCode) loadSvg(activeCode);
  }, [activeCode, loadSvg]);

  return (
    <div className="flex flex-col gap-10">
      <div className="flex flex-wrap items-end justify-between gap-6 px-2">
        <div className="space-y-4">
          <div className="flex items-center gap-3">
             <div className="h-2 w-10 rounded-full bg-[var(--accent-strong)]" />
             <h4 className="text-3xl font-[1000] tracking-tighter text-[var(--text-primary)] uppercase">{t.title || "CAD / BIM 통합 엔진"}</h4>
          </div>
          <p className="max-w-2xl text-sm font-medium leading-relaxed text-[var(--text-secondary)] italic underline decoration-[var(--line-strong)] decoration-2 underline-offset-8">
            {t.description || "선택한 건축개요를 기준으로 2D CAD 도면과 3D BIM을 동일 기하로 동기화 생성합니다."}
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

      {/* ── 적용 건축개요 스트립(선택한 개발종목 기반 — CAD·BIM 공용 기하) ── */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] px-5 py-3 -mt-4">
        <span className="text-[10px] font-black uppercase tracking-[0.2em] text-[var(--accent-strong)]">적용 건축개요</span>
        {specLoading && !spec ? (
          <span className="text-xs text-[var(--text-hint)]">건축개요 산출 중…</span>
        ) : (
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs">
            {[
              ["용도", spec?.building_type || spec?.building_use || "-"],
              ["연면적", spec?.gfa ? `${Math.round(spec.gfa).toLocaleString()}㎡` : "자동산출"],
              ["층수", spec ? `${spec.floor_count}F` : "-"],
              ["건폐율", spec?.bcr != null ? `${spec.bcr}%` : "-"],
              ["용적률", spec?.far != null ? `${spec.far}%` : "-"],
              ["건물규모", spec ? `${spec.building_width_m}×${spec.building_depth_m}m` : "-"],
              ["세대/호실", spec?.total_units != null ? `${spec.total_units}` : "-"],
            ].map(([k, v]) => (
              <span key={k} className="flex items-center gap-1.5">
                <span className="text-[var(--text-hint)]">{k}</span>
                <b className="text-[var(--text-primary)]">{v}</b>
              </span>
            ))}
          </div>
        )}
        {!designData?.totalGfaSqm && (
          <span className="ml-auto text-[10px] text-[var(--text-hint)]">※ 사업모델 추천에서 개요 선택 시 정밀 반영(현재 대지·용도지역 자동산출)</span>
        )}
      </div>

      <div className="relative h-[650px] w-full overflow-hidden rounded-[4rem] border border-[var(--line-strong)] bg-[#0d1520] shadow-[var(--shadow-2xl)] group">
        {/* Cinematic Backdrop */}
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-black/20 to-black/60 pointer-events-none z-10" />

        {/* 3D Canvas or 2D SVG */}
        {viewMode === "bim_3d" ? (
          <div className="absolute inset-0">
            <Canvas camera={{ position: [25, 20, 25], fov: 40 }}>
              <ambientLight intensity={0.8} />
              <directionalLight position={[10, 20, 10]} intensity={1.4} castShadow />
              <directionalLight position={[-10, 10, -10]} intensity={0.5} />
              <pointLight position={[-10, 10, -10]} intensity={0.5} color="#60a5fa" />
              {/* 무거운 HDR Environment 제거(네트워크 다운로드·GPU 부하). 모델 있을 때만 완만 회전. */}
              <OrbitControls makeDefault autoRotate={!!bimScene} autoRotateSpeed={0.3} enableDamping dampingFactor={0.05} />
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

            {/* 2D 도면 AI 해석(평면효율·동선코어 — 평면도 관련 섹션) */}
            {designAi && (designAi.floor_efficiency || designAi.circulation_core) && (
              <div className="border-t border-white/5 px-6 py-4 max-h-[180px] overflow-y-auto">
                <div className="flex items-center gap-2 mb-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 animate-pulse" />
                  <p className="text-[9px] font-black uppercase tracking-[0.3em] text-indigo-300">AI 도면 해석 · Claude</p>
                </div>
                <div className="space-y-2">
                  {designAi.floor_efficiency && (
                    <div>
                      <p className="text-[9px] font-bold text-indigo-300/80 mb-0.5">평면 효율</p>
                      <p className="text-[11px] leading-relaxed text-slate-300">{designAi.floor_efficiency}</p>
                    </div>
                  )}
                  {designAi.circulation_core && (
                    <div>
                      <p className="text-[9px] font-bold text-indigo-300/80 mb-0.5">동선·코어</p>
                      <p className="text-[11px] leading-relaxed text-slate-300">{designAi.circulation_core}</p>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Overlay Tools (only for 3D) */}
        {viewMode === "bim_3d" && (
          <>
            <div className="absolute right-6 top-6 flex max-h-[88%] w-[340px] flex-col gap-3 z-20 overflow-y-auto">
              {/* 매스 메타(실측) */}
              {bimMass && (
                <motion.div
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="rounded-2xl border border-white/10 bg-black/70 p-5 text-white backdrop-blur-2xl shadow-2xl"
                >
                  <p className="text-[9px] font-black uppercase tracking-[0.3em] text-[var(--accent-strong)] mb-2">AI 자동 매스</p>
                  <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
                    <span className="opacity-50">규모</span>
                    <span className="font-bold text-right">{String(bimMass.building_width_m)}×{String(bimMass.building_depth_m)}m</span>
                    <span className="opacity-50">층수</span>
                    <span className="font-bold text-right">{String(bimMass.num_floors)}F / {String(bimMass.building_height_m)}m</span>
                    {bimMass.bcr_pct != null && (<><span className="opacity-50">건폐율</span><span className="font-bold text-right">{String(bimMass.bcr_pct)}%</span></>)}
                    {bimMass.far_pct != null && (<><span className="opacity-50">용적률</span><span className="font-bold text-right">{String(bimMass.far_pct)}%</span></>)}
                    {bimMass.total_units != null && (<><span className="opacity-50">세대수</span><span className="font-bold text-right">{String(bimMass.total_units)}세대</span></>)}
                  </div>
                </motion.div>
              )}

              {/* AI 설계 해석(DesignInterpreter 6섹션) */}
              {designAi && (
                <motion.div
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="rounded-2xl border border-indigo-400/20 bg-black/70 p-5 text-white backdrop-blur-2xl shadow-2xl"
                >
                  <div className="flex items-center gap-2 mb-3">
                    <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 animate-pulse" />
                    <p className="text-[9px] font-black uppercase tracking-[0.3em] text-indigo-300">AI 설계 해석 · Claude</p>
                  </div>
                  <div className="space-y-2.5">
                    {([
                      ["design_overview", "설계 개요"],
                      ["mass_strategy", "매스 전략"],
                      ["floor_efficiency", "평면 효율"],
                      ["compliance_review", "법규 준수"],
                      ["circulation_core", "동선·코어"],
                      ["improvement", "개선 제안"],
                    ] as [string, string][])
                      .filter(([k]) => designAi[k])
                      .map(([k, label]) => (
                        <div key={k}>
                          <p className="text-[9px] font-bold text-indigo-300/80 mb-0.5">{label}</p>
                          <p className="text-[11px] leading-relaxed text-slate-200 whitespace-pre-wrap">{designAi[k]}</p>
                        </div>
                      ))}
                  </div>
                  <p className="mt-3 text-[8px] text-white/30">AI 생성 · 참고용</p>
                </motion.div>
              )}

              {/* 해석 로딩 표시 */}
              {!designAi && bimLoading && (
                <div className="rounded-2xl border border-white/10 bg-black/60 p-4 text-white/50 backdrop-blur-xl text-[10px] font-bold">
                  AI 설계 해석 생성 중...
                </div>
              )}
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
