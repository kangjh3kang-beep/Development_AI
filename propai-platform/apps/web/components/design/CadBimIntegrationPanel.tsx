"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { CameraControls, Grid } from "@react-three/drei";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import * as THREE from "three";
import { motion } from "framer-motion";
import CADEditor from "./CADEditor";
import { GenerativeDesignPanel } from "@/components/cad/GenerativeDesignPanel";
import { DesignOutcomeSummary } from "@/components/design/DesignOutcomeSummary";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { apiClient, ApiClientError } from "@/lib/api-client";

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

// ── 카메라 시점 프리셋(비전문가용 시점 전환) ──────────────────────
// 각 프리셋은 카메라 위치(pos)와 바라보는 중심(target)을 "건물크기 배수"로 정의한다.
// 실제 좌표는 모델 크기(span)에 비례해 계산하므로 작은 단독주택·큰 아파트 모두 잘 잡힌다.
type CamPresetKey = "aerial" | "perspective" | "front" | "side" | "reset";

interface CamPreset {
  label: string; // 버튼 한글 라벨(비전문가용)
  icon: string;
  // span(건물 한 변 기준 크기)을 받아 [카메라위치, 바라보는중심]을 돌려준다.
  compute: (span: number, height: number) => { pos: [number, number, number]; target: [number, number, number] };
}

const CAM_PRESETS: Record<CamPresetKey, CamPreset> = {
  // 조감도: 위에서 약 45° 내려다보기(전체 배치 파악)
  aerial: {
    label: "조감도",
    icon: "▲",
    compute: (s, h) => ({ pos: [s * 0.9, s * 1.3, s * 0.9], target: [0, h * 0.3, 0] }),
  },
  // 투시도: 사람 눈높이(보행자 시점)에서 비스듬히 보기
  perspective: {
    label: "투시도",
    icon: "◉",
    compute: (s, h) => ({ pos: [s * 1.6, h * 0.18, s * 1.6], target: [0, h * 0.35, 0] }),
  },
  // 정면도: 건물 정면을 똑바로 보기
  front: {
    label: "정면",
    icon: "▮",
    compute: (s, h) => ({ pos: [0, h * 0.5, s * 2.1], target: [0, h * 0.5, 0] }),
  },
  // 측면도: 건물 옆면을 똑바로 보기
  side: {
    label: "측면",
    icon: "◧",
    compute: (s, h) => ({ pos: [s * 2.1, h * 0.5, 0], target: [0, h * 0.5, 0] }),
  },
  // 리셋: 기본 진입 시점으로 복귀
  reset: {
    label: "리셋",
    icon: "↺",
    compute: (s, h) => ({ pos: [s * 1.1, s * 0.9, s * 1.1], target: [0, h * 0.3, 0] }),
  },
};

/**
 * 카메라 제어 + 시점 프리셋 보간.
 * drei <CameraControls>는 setLookAt(.., enableTransition)로 목표 시점까지 "부드럽게 보간"하며,
 * 보간 중에만 내부적으로 invalidate()를 호출하고 도달하면 멈춘다(frameloop="demand"와 완벽 호환).
 * 따라서 수동 useFrame/lerp 없이도 성능 처방(보간 중에만 렌더, 도달 후 정지)이 그대로 지켜진다.
 *
 * @param preset    현재 적용할 프리셋 키(변경 시 해당 시점으로 보간)
 * @param presetSeq 같은 프리셋을 다시 눌러도 재적용되도록 하는 단조 증가 카운터
 * @param span      모델 크기(한 변 기준) — 프리셋 거리 산정의 기준값
 * @param height    모델 높이 — 시선 높이/중심 산정의 기준값
 * @param autoRotate 기존 자동회전 토글(신규 추가 아님, 기존 기능 유지)
 */
function CameraRig({
  controlsRef,
  preset,
  presetSeq,
  span,
  height,
  autoRotate,
}: {
  controlsRef: React.RefObject<CameraControls | null>;
  preset: CamPresetKey;
  presetSeq: number;
  span: number;
  height: number;
  autoRotate: boolean;
}) {
  const invalidate = useThree((s) => s.invalidate);

  // 프리셋(또는 재적용 카운터) 변경 시 → 목표 시점으로 부드럽게 보간 이동
  useEffect(() => {
    const cc = controlsRef.current;
    if (!cc) return;
    const { pos, target } = CAM_PRESETS[preset].compute(span, height);
    // setLookAt(camX,camY,camZ, tgtX,tgtY,tgtZ, enableTransition=true) → 보간 이동
    cc.setLookAt(pos[0], pos[1], pos[2], target[0], target[1], target[2], true);
    invalidate(); // 첫 프레임 렌더 트리거(이후는 CameraControls가 보간 동안만 자동 요청)
  }, [controlsRef, preset, presetSeq, span, height, invalidate]);

  // 자동회전(기존 기능 유지) — 켜진 동안에만 azimuth를 조금씩 돌리고 invalidate.
  // 꺼지면 루프를 멈춰 메인스레드 점유 0(정지). 신규 autoRotate 추가가 아니라 기존 토글 이식.
  useEffect(() => {
    if (!autoRotate) return;
    let raf = 0;
    let last = performance.now();
    const loop = (now: number) => {
      const cc = controlsRef.current;
      if (cc) {
        const dt = (now - last) / 1000;
        cc.rotate(0.3 * dt, 0, false); // 초당 0.3rad 천천히 회전
        cc.update(dt);
        invalidate();
      }
      last = now;
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [autoRotate, controlsRef, invalidate]);

  return null;
}

export function CadBimIntegrationPanel({ projectId, dictionary }: { projectId: string; dictionary: Record<string, string> }) {
  // 기본 진입 화면은 2D 도면. 3D는 사용자가 명시적으로 전환할 때만 캔버스를 마운트(과거 진입멈춤 방지).
  const [viewMode, setViewMode] = useState<"cad_2d" | "bim_3d">("cad_2d");
  // 3D 자동회전은 기본 꺼짐(무한회전이 과거 메인스레드 점유→멈춤의 직접원인). 버튼으로만 켠다.
  const [autoRotate, setAutoRotate] = useState(false);
  const t = dictionary;

  // 선택한 건축개요(모세혈관 스토어) — CAD/BIM 기하의 단일 출처
  const designData = useProjectContextStore((s) => s.designData);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);

  // 설계(건축개요)가 있는지 — 3D 캔버스는 "설계 생성 후"에만 마운트하는 게이트.
  // 선택한 개요(GFA) 또는 부지분석(대지면적·용도지역) 중 하나라도 있으면 매스 산출이 가능하다.
  const hasDesignBasis = !!(designData?.totalGfaSqm || siteAnalysis?.landAreaSqm || siteAnalysis?.zoneCode);

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

  // ── 3D 카메라 시점 프리셋(비전문가용 시점 전환) ──
  const camControlsRef = useRef<CameraControls | null>(null);
  // 현재 활성 시점(버튼 활성 표시용). 기본은 리셋(기본 진입 시점).
  const [camPreset, setCamPreset] = useState<CamPresetKey>("reset");
  // 같은 버튼을 다시 눌러도 보간이 재적용되도록 하는 단조 증가 카운터.
  const [camPresetSeq, setCamPresetSeq] = useState(0);
  // 로드된 모델의 크기(한 변 기준 span·높이) — 프리셋 거리 산정 기준값(모델 없으면 기본값).
  const [modelDims, setModelDims] = useState<{ span: number; height: number }>({ span: 30, height: 18 });

  // 시점 프리셋 버튼 핸들러: 같은 프리셋 재선택도 보간 재적용(seq 증가).
  const applyPreset = useCallback((key: CamPresetKey) => {
    setCamPreset(key);
    setCamPresetSeq((n) => n + 1);
  }, []);

  // ── 3D 렌더러(gl) 참조 — AI 포토리얼 렌더용 뷰포트 캡처에 사용 ──
  const glRef = useRef<THREE.WebGLRenderer | null>(null);

  // ── AI 포토리얼 렌더(과금 게이트) 상태 ──
  // 결과 표시는 모달. status: idle→confirm(과금확인)→loading→result|nokey|error
  type RenderPhase = "idle" | "confirm" | "loading" | "result" | "nokey" | "error";
  const [renderPhase, setRenderPhase] = useState<RenderPhase>("idle");
  const [renderStyle, setRenderStyle] = useState<"주간" | "야간" | "실사">("주간");
  const [renderImage, setRenderImage] = useState<string | null>(null); // 결과 이미지(data URL 또는 원격 URL)
  const [renderMsg, setRenderMsg] = useState<string | null>(null);
  const [renderCharged, setRenderCharged] = useState<number | null>(null);
  // 이 기능 1회 소요 코인(비전문가용 안내). 실제 청구는 백엔드가 charged로 회신.
  const RENDER_COST_COIN = 5;

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

  // 마운트 시 1회 기하 산출 — 단, 설계 기반(개요·부지)이 있을 때만(무목업·게이트)
  useEffect(() => {
    if (hasDesignBasis && !spec && !specLoading) resolveSpec();
  }, [hasDesignBasis, spec, specLoading, resolveSpec]);

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
      // 모델 크기 측정(바운딩박스) → 카메라 프리셋 거리 산정 기준값.
      // span=평면 최대 변(폭/깊이 중 큰 값), height=높이. 작은/큰 건물 모두 시점이 잘 잡힌다.
      const box = new THREE.Box3().setFromObject(gltf.scene);
      const size = new THREE.Vector3();
      box.getSize(size);
      const span = Math.max(8, Math.max(size.x, size.z));
      const height = Math.max(4, size.y);
      setModelDims({ span, height });
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

  // 생성 UX(Phase 2)에서 설계안 적용 시 — 파생 기하·도면·3D를 초기화해
  // 새 SSOT(designData)로 spec을 재산출하고 2D/3D를 재생성한다(기존 로드 경로 재사용).
  const handleGeneratedApplied = useCallback(() => {
    setSpec(null);
    setBimScene(null);
    setBimError(null);
    setBimMass(null);
    setDesignAi(null);
    setDrawingCodes([]);
    setSvgMap({});
    setActiveCode(null);
  }, []);

  // ── AI 포토리얼 렌더 실행 ──────────────────────────────────────
  // 현재 3D 뷰포트를 PNG로 캡처해 백엔드로 보내고, AI가 사실적으로 다시 그린 이미지를 받는다.
  // 과금 게이트: confirm 단계에서 사용자가 "결제하고 렌더"를 눌러야 실제 호출(아래)이 시작된다.
  const runPhotorealRender = useCallback(async () => {
    const gl = glRef.current;
    if (!gl || !bimScene) {
      // 모델이 없으면 캡처할 화면이 없음 — 정직 안내(가짜 호출 금지).
      setRenderMsg("먼저 3D 모델을 불러온 뒤 렌더할 수 있습니다.");
      setRenderPhase("error");
      return;
    }
    setRenderPhase("loading");
    setRenderMsg(null);
    setRenderImage(null);
    setRenderCharged(null);

    let imageBase64 = "";
    try {
      // 현재 뷰포트를 PNG로 캡처. Canvas에 preserveDrawingBuffer=true를 줘서
      // demand 루프(정지 화면)에서도 마지막 프레임이 버퍼에 남아 캡처가 빈 화면이 되지 않는다.
      imageBase64 = gl.domElement.toDataURL("image/png");
    } catch {
      setRenderMsg("뷰포트 캡처에 실패했습니다. 화면을 한 번 움직인 뒤 다시 시도하세요.");
      setRenderPhase("error");
      return;
    }

    try {
      // 백엔드 계약: status가 ok|no_key|error로 회신(HTTP는 200). apiClient는 비-2xx만 throw.
      const resp = await apiClient.post<{
        status: "ok" | "no_key" | "error";
        image_url?: string;
        image_base64?: string;
        message?: string;
        charged?: number;
      }>(`/design/${encodeURIComponent(projectId)}/render-photoreal`, {
        body: { image_base64: imageBase64, style: renderStyle },
        timeoutMs: 120_000,
      });

      if (resp.status === "no_key") {
        // 서버에 렌더 API 키 미설정 — 정직 안내(가짜 이미지 금지).
        setRenderMsg(resp.message || "AI 렌더는 관리자 키 설정 후 이용 가능합니다.");
        setRenderPhase("nokey");
        return;
      }
      if (resp.status !== "ok") {
        setRenderMsg(resp.message || "AI 렌더에 실패했습니다. 잠시 후 다시 시도하세요.");
        setRenderPhase("error");
        return;
      }
      // 성공: 원격 URL 우선, 없으면 base64. 둘 다 없으면 결과 없음(가짜 표시 금지).
      const img = resp.image_url || (resp.image_base64
        ? (resp.image_base64.startsWith("data:") ? resp.image_base64 : `data:image/png;base64,${resp.image_base64}`)
        : null);
      if (!img) {
        setRenderMsg("렌더 결과 이미지를 받지 못했습니다.");
        setRenderPhase("error");
        return;
      }
      setRenderImage(img);
      setRenderCharged(typeof resp.charged === "number" ? resp.charged : null);
      setRenderMsg(resp.message || null);
      setRenderPhase("result");
    } catch (err) {
      // 인증·서버 오류 등 HTTP 비-2xx
      const msg = err instanceof ApiClientError
        ? (err.status === 402 ? "코인이 부족합니다. 충전 후 다시 시도하세요." : "AI 렌더 요청이 거부되었습니다.")
        : "네트워크 오류로 AI 렌더에 실패했습니다.";
      setRenderMsg(msg);
      setRenderPhase("error");
    }
  }, [projectId, bimScene, renderStyle]);

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
        <div className="ml-auto flex items-center gap-3">
          {!designData?.totalGfaSqm && (
            <span className="text-[10px] text-[var(--text-hint)]">※ 사업모델 추천에서 개요 선택 시 정밀 반영(현재 대지·용도지역 자동산출)</span>
          )}
          <button
            type="button"
            onClick={() => {
              setSpec(null); setBimScene(null); setBimError(null); setBimMass(null);
              setDesignAi(null); setDrawingCodes([]); setSvgMap({}); setActiveCode(null);
            }}
            disabled={specLoading}
            className="rounded-lg border border-[var(--line-strong)] px-3 py-1 text-[10px] font-bold text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-strong)] disabled:opacity-50"
            title="선택한 건축개요를 다시 불러와 도면·모델을 재생성"
          >
            ↻ 개요 재적용
          </button>
        </div>
      </div>

      {/* ── Phase 2 · 생성 UX(자연어→Top3 설계안→스튜디오 로드) ── */}
      <GenerativeDesignPanel projectId={projectId} onApplied={handleGeneratedApplied} />

      {/* ── Phase 4 · 설계 결과 → 사업성·환경·해설·은행제출 연결 요약 ──
          설계 적용/변경 시 designData를 기준으로 공사비(estimate-overview) 1회 산정 → 수지/ROI·ESG(SSOT)
          요약 + 설계해설(designAi 6섹션) + 은행제출 패키지 원클릭. 기존 분석/보고서 로직은 재구현 없이 연결만. */}
      <DesignOutcomeSummary projectId={projectId} designAi={designAi} />

      <div className="relative h-[650px] w-full overflow-hidden rounded-[4rem] border border-[var(--line-strong)] bg-[#0d1520] shadow-[var(--shadow-2xl)] group">
        {/* Cinematic Backdrop */}
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-black/20 to-black/60 pointer-events-none z-10" />

        {/* 3D Canvas or 2D SVG */}
        {viewMode === "bim_3d" && !hasDesignBasis ? (
          /* ── 게이트: 설계 기반(개요·부지)이 없으면 3D 캔버스를 마운트하지 않고 정직 안내 ── */
          <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-4 bg-[#0a0f14] px-8 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl border border-white/10 bg-white/5">
              <span className="text-2xl">🏗️</span>
            </div>
            <p className="text-base font-black text-white/80">먼저 설계를 생성하세요</p>
            <p className="max-w-sm text-xs leading-relaxed text-white/40">
              부지분석에서 대지·용도지역을 불러오거나 사업모델 추천에서 건축개요를 선택하면 3D BIM 모델을 자동 생성합니다.
            </p>
            <button
              onClick={() => setViewMode("cad_2d")}
              className="mt-2 rounded-full bg-white/10 px-6 py-2 text-[11px] font-black uppercase tracking-widest text-white hover:bg-white/20"
            >
              2D 도면으로 이동
            </button>
          </div>
        ) : viewMode === "bim_3d" ? (
          <div className="absolute inset-0">
            {/* frameloop="demand": 정적 화면에서는 렌더를 멈춰 메인스레드 점유 0.
                preserveDrawingBuffer=true: AI 렌더용 뷰포트 캡처(toDataURL)가 빈 화면이 되지 않도록 마지막 프레임 보존.
                onCreated: gl(렌더러) 참조 확보(캡처용). */}
            <Canvas
              frameloop="demand"
              camera={{ position: [25, 20, 25], fov: 40 }}
              gl={{ preserveDrawingBuffer: true }}
              onCreated={({ gl }) => { glRef.current = gl; }}
            >
              <ambientLight intensity={0.8} />
              <directionalLight position={[10, 20, 10]} intensity={1.4} castShadow />
              <directionalLight position={[-10, 10, -10]} intensity={0.5} />
              <pointLight position={[-10, 10, -10]} intensity={0.5} color="#60a5fa" />
              {/* HDR Environment 제거(네트워크 다운로드·GPU 부하). 기본 조명만 사용. 자동회전은 버튼으로만.
                  CameraControls: 시점 프리셋을 setLookAt으로 "부드럽게 보간 이동"(보간 중에만 invalidate→도달 후 정지). */}
              <CameraControls ref={camControlsRef} makeDefault dampingFactor={0.06} />
              <CameraRig
                controlsRef={camControlsRef}
                preset={camPreset}
                presetSeq={camPresetSeq}
                span={modelDims.span}
                height={modelDims.height}
                autoRotate={autoRotate}
              />
              <BuildingModel scene={bimScene} />
            </Canvas>

            {/* ── 카메라 시점 프리셋 바(비전문가용 시점 전환) ── 모델 없으면 비활성+안내 ── */}
            <div className="absolute left-6 top-6 z-30 flex flex-col gap-2">
              <div className="flex items-center gap-1.5 rounded-2xl border border-white/10 bg-black/45 p-1.5 backdrop-blur-xl shadow-2xl">
                {(Object.keys(CAM_PRESETS) as CamPresetKey[]).map((key) => {
                  const active = camPreset === key;
                  return (
                    <button
                      key={key}
                      type="button"
                      disabled={!bimScene}
                      onClick={() => applyPreset(key)}
                      title={CAM_PRESETS[key].label}
                      className={`flex items-center gap-1.5 rounded-xl px-3 py-2 text-[10px] font-black uppercase tracking-widest transition-colors disabled:cursor-not-allowed disabled:opacity-30 ${
                        active
                          ? "bg-[var(--accent-strong)] text-white shadow-lg"
                          : "text-white/55 hover:text-white hover:bg-white/10"
                      }`}
                    >
                      <span className="text-[11px] leading-none">{CAM_PRESETS[key].icon}</span>
                      {CAM_PRESETS[key].label}
                    </button>
                  );
                })}
              </div>
              {!bimScene && (
                <span className="rounded-lg bg-black/40 px-3 py-1 text-[10px] font-bold text-white/45 backdrop-blur-md">
                  모델을 불러오면 시점 전환을 사용할 수 있어요
                </span>
              )}
            </div>

            {/* 자동회전 토글(기본 꺼짐) — 사용자가 명시적으로 켤 때만 회전 */}
            {bimScene && (
              <button
                onClick={() => setAutoRotate((v) => !v)}
                className={`absolute right-6 bottom-6 z-30 rounded-full border px-4 py-2 text-[10px] font-black uppercase tracking-widest transition-colors ${
                  autoRotate
                    ? "border-[var(--accent-strong)] bg-[var(--accent-strong)]/20 text-[var(--accent-strong)]"
                    : "border-white/10 bg-black/40 text-white/50 hover:text-white"
                }`}
              >
                {autoRotate ? "■ 회전 정지" : "▶ 자동 회전"}
              </button>
            )}

            {/* ── AI 포토리얼 렌더 버튼(과금 게이트) — 모델 있을 때만 노출 ── */}
            {bimScene && (
              <button
                type="button"
                onClick={() => setRenderPhase("confirm")}
                className="absolute right-6 top-6 z-30 flex items-center gap-2 rounded-full border border-[var(--accent-strong)]/60 bg-[var(--accent-strong)]/15 px-5 py-2.5 text-[10px] font-black uppercase tracking-widest text-[var(--accent-strong)] backdrop-blur-xl shadow-lg transition-colors hover:bg-[var(--accent-strong)]/25"
              >
                <span className="text-[12px] leading-none">✦</span>
                AI 포토리얼 렌더
              </button>
            )}
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
            {/* 상단 바: 도면 선택 드롭다운(공간 최적화) + 편집모드 전환 */}
            <div className="flex items-center justify-between gap-3 border-b border-white/5 px-6 py-3">
              <label className="flex items-center gap-2">
                <span className="text-[10px] font-black uppercase tracking-widest text-white/40">도면</span>
                <select
                  value={activeCode}
                  onChange={(e) => setActiveCode(e.target.value)}
                  className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-bold text-white focus:border-[var(--accent-strong)] focus:outline-none"
                >
                  {drawingCodes.map((code) => (
                    <option key={code} value={code} className="bg-[#0a0f14] text-white">
                      {DRAWING_LABELS[code] || code}
                    </option>
                  ))}
                </select>
              </label>
              <button
                onClick={() => setEditMode(true)}
                className="shrink-0 rounded-full border border-white/10 px-4 py-2 text-[10px] font-black uppercase tracking-widest text-[var(--accent-strong)] hover:bg-white/5"
              >
                편집 모드
              </button>
            </div>

            {/* 도면 표시 영역 */}
            <div className="relative flex-1 flex items-center justify-center overflow-auto p-8">
              {/* 게이트: 설계 기반(개요·부지)이 없으면 도면을 만들지 않고 정직 안내 */}
              {!hasDesignBasis && !drawingLoading && (
                <div className="flex flex-col items-center gap-3 text-center">
                  <span className="text-2xl">📐</span>
                  <p className="text-sm font-black text-white/70">먼저 설계를 생성하세요</p>
                  <p className="max-w-xs text-xs leading-relaxed text-white/40">
                    부지분석에서 대지·용도지역을 불러오거나 사업모델 추천에서 건축개요를 선택하면 2D 도면을 자동 생성합니다.
                  </p>
                </div>
              )}
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
            <div className="absolute right-6 top-[5.5rem] flex max-h-[80%] w-[340px] flex-col gap-3 z-20 overflow-y-auto">
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

        {/* ══════════════ AI 포토리얼 렌더 모달(과금 게이트 + 결과/정직안내) ══════════════ */}
        {renderPhase !== "idle" && (
          <div className="absolute inset-0 z-40 flex items-center justify-center bg-black/70 p-6 backdrop-blur-sm">
            <div className="w-full max-w-2xl overflow-hidden rounded-3xl border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)]">
              {/* 헤더 */}
              <div className="flex items-center justify-between border-b border-[var(--line)] px-6 py-4">
                <div className="flex items-center gap-2.5">
                  <span className="text-[var(--accent-strong)]">✦</span>
                  <h5 className="text-sm font-black uppercase tracking-widest text-[var(--text-primary)]">AI 포토리얼 렌더</h5>
                </div>
                <button
                  type="button"
                  onClick={() => { setRenderPhase("idle"); setRenderImage(null); setRenderMsg(null); }}
                  className="rounded-full px-2 text-lg text-[var(--text-hint)] hover:text-[var(--text-primary)]"
                  aria-label="닫기"
                >
                  ×
                </button>
              </div>

              <div className="px-6 py-6">
                {/* ── 1) 과금 확인(실행 전) ── */}
                {renderPhase === "confirm" && (
                  <div className="space-y-5">
                    <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
                      지금 보이는 <b className="text-[var(--text-primary)]">3D 화면 그대로</b>를 AI가 사실적인 사진처럼 다시 그려드립니다.
                      원본 3D 모델은 <b className="text-[var(--text-primary)]">바뀌지 않습니다(비파괴)</b>.
                    </p>
                    {/* 스타일 선택(쉬운 한글) */}
                    <div>
                      <p className="mb-2 text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">렌더 스타일</p>
                      <div className="flex gap-2">
                        {(["주간", "야간", "실사"] as const).map((s) => (
                          <button
                            key={s}
                            type="button"
                            onClick={() => setRenderStyle(s)}
                            className={`rounded-xl px-4 py-2 text-xs font-bold transition-colors ${
                              renderStyle === s
                                ? "bg-[var(--accent-strong)] text-white"
                                : "border border-[var(--line-strong)] text-[var(--text-secondary)] hover:bg-[var(--surface-soft)]"
                            }`}
                          >
                            {s === "주간" ? "낮(주간)" : s === "야간" ? "밤(야간)" : "실사(사진풍)"}
                          </button>
                        ))}
                      </div>
                    </div>
                    {/* 과금 안내(쉬운 문구) */}
                    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3">
                      <p className="text-xs leading-relaxed text-[var(--text-secondary)]">
                        이 기능은 1회 실행에 <b className="text-[var(--accent-strong)]">약 {RENDER_COST_COIN}코인</b>이 소요됩니다.
                        실제 차감 금액은 완료 후 안내해 드립니다.
                      </p>
                    </div>
                    <div className="flex justify-end gap-3 pt-1">
                      <button
                        type="button"
                        onClick={() => setRenderPhase("idle")}
                        className="rounded-full border border-[var(--line-strong)] px-5 py-2.5 text-xs font-bold text-[var(--text-secondary)] hover:bg-[var(--surface-soft)]"
                      >
                        취소
                      </button>
                      <button
                        type="button"
                        onClick={runPhotorealRender}
                        className="rounded-full bg-[var(--accent-strong)] px-6 py-2.5 text-xs font-black uppercase tracking-widest text-white hover:opacity-90"
                      >
                        결제하고 렌더 ({RENDER_COST_COIN}코인)
                      </button>
                    </div>
                  </div>
                )}

                {/* ── 2) 렌더 진행 중 ── */}
                {renderPhase === "loading" && (
                  <div className="flex flex-col items-center gap-4 py-8">
                    <div className="h-12 w-12 animate-spin rounded-full border-4 border-[var(--accent-strong)] border-t-transparent" />
                    <p className="text-sm font-bold text-[var(--text-secondary)]">AI가 사진처럼 그리는 중입니다…</p>
                    <p className="text-xs text-[var(--text-hint)]">최대 1~2분 걸릴 수 있어요</p>
                  </div>
                )}

                {/* ── 3) 결과(성공) ── */}
                {renderPhase === "result" && renderImage && (
                  <div className="space-y-4">
                    {/* 결과 이미지 — 백엔드가 회신한 실제 렌더 결과만 표시(가짜 이미지 금지) */}
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={renderImage}
                      alt="AI 포토리얼 렌더 결과"
                      className="w-full rounded-2xl border border-[var(--line)] shadow-lg"
                    />
                    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3 text-xs leading-relaxed text-[var(--text-secondary)]">
                      <p>· 원본 3D 모델은 <b className="text-[var(--text-primary)]">그대로 유지</b>됩니다(이 이미지는 별도 결과물).</p>
                      {renderCharged != null && (
                        <p className="mt-1">· 이번 렌더로 <b className="text-[var(--accent-strong)]">{renderCharged}코인</b>이 차감되었습니다.</p>
                      )}
                      {renderMsg && <p className="mt-1 text-[var(--text-hint)]">{renderMsg}</p>}
                    </div>
                    <div className="flex justify-end gap-3">
                      <a
                        href={renderImage}
                        download="propai-render.png"
                        className="rounded-full border border-[var(--line-strong)] px-5 py-2.5 text-xs font-bold text-[var(--text-secondary)] hover:bg-[var(--surface-soft)]"
                      >
                        이미지 저장
                      </a>
                      <button
                        type="button"
                        onClick={() => setRenderPhase("idle")}
                        className="rounded-full bg-[var(--accent-strong)] px-6 py-2.5 text-xs font-black uppercase tracking-widest text-white hover:opacity-90"
                      >
                        완료
                      </button>
                    </div>
                  </div>
                )}

                {/* ── 4) 서버 키 미설정(정직 안내, 가짜 이미지 금지) ── */}
                {renderPhase === "nokey" && (
                  <div className="space-y-4 text-center">
                    <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)]">
                      <span className="text-2xl">🔑</span>
                    </div>
                    <p className="text-sm font-bold text-[var(--text-primary)]">AI 렌더가 아직 준비되지 않았어요</p>
                    <p className="mx-auto max-w-md text-xs leading-relaxed text-[var(--text-secondary)]">
                      {renderMsg || "AI 렌더는 관리자 키 설정 후 이용 가능합니다."}
                    </p>
                    <p className="text-[11px] text-[var(--text-hint)]">키가 없어 코인은 차감되지 않았습니다.</p>
                    <button
                      type="button"
                      onClick={() => setRenderPhase("idle")}
                      className="rounded-full bg-[var(--surface-soft)] px-6 py-2.5 text-xs font-black uppercase tracking-widest text-[var(--text-primary)] hover:bg-[var(--surface-strong)] border border-[var(--line-strong)]"
                    >
                      확인
                    </button>
                  </div>
                )}

                {/* ── 5) 오류 ── */}
                {renderPhase === "error" && (
                  <div className="space-y-4 text-center">
                    <p className="text-sm font-bold text-red-400">{renderMsg || "AI 렌더에 실패했습니다."}</p>
                    <div className="flex justify-center gap-3">
                      <button
                        type="button"
                        onClick={() => setRenderPhase("idle")}
                        className="rounded-full border border-[var(--line-strong)] px-5 py-2.5 text-xs font-bold text-[var(--text-secondary)] hover:bg-[var(--surface-soft)]"
                      >
                        닫기
                      </button>
                      <button
                        type="button"
                        onClick={() => setRenderPhase("confirm")}
                        className="rounded-full bg-[var(--accent-strong)] px-6 py-2.5 text-xs font-black uppercase tracking-widest text-white hover:opacity-90"
                      >
                        다시 시도
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
