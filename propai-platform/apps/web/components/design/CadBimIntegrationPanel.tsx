"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { CameraControls, Grid } from "@react-three/drei";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import * as THREE from "three";
import { motion } from "framer-motion";
import CADEditor, { type CADEditorMetrics } from "./CADEditor";
import { sectionCutHeightM, visibleFloorCount } from "./bimSection";
import { GenerativeDesignPanel } from "@/components/cad/GenerativeDesignPanel";
import { DesignOutcomeSummary } from "@/components/design/DesignOutcomeSummary";
import { UnitMixSimulatorPanel } from "@/components/design/UnitMixSimulatorPanel";
import { LiveProFormaStrip, type LiveProFormaDesign } from "@/components/design/LiveProFormaStrip";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { apiClient, ApiClientError, apiV1BaseUrl } from "@/lib/api-client";

// 도면 코드 → 한글 명칭 (SVGDrawingService.generate_full_drawing_set 기준)
const DRAWING_LABELS: Record<string, string> = {
  "B-01": "배치도",
  "B-02-UNIT": "단위세대 평면도",
  "B-02-UNIT-R": "단위세대 평면도(정밀·실배치)",
  "B-02-STD": "기준층 평면도",
  "B-03": "단면도",
  "B-04-F": "정면도",
  "B-04-S": "측면도",
  "C-01": "투시도",
  "C-02": "음영 분석",
  "C-03": "상세도",
};

// DXF 도면종류(export-dxf drawing_type) — 평면/상세/단면/입면/배치 5종.
const DXF_TYPE_LABELS: Record<string, string> = {
  floor_plan: "평면도",
  detail: "상세도",
  section: "단면도",
  elevation: "입면도",
  site: "배치도",
};
const DXF_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: "floor_plan", label: "평면도" },
  { value: "detail", label: "상세도" },
  { value: "section", label: "단면도" },
  { value: "elevation", label: "입면도" },
  { value: "site", label: "배치도" },
];

// v1 API base는 apiV1BaseUrl()(api-client 단일 출처) 사용 — SVG·바이너리는 텍스트/blob이라 직접 fetch.
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
  daylightNorth?: boolean;   // P5: 정북일조 단계후퇴(북측 상부 매스 후퇴)
  project_name: string;
}

// 클라이언트 절차생성 3D 매스 — 건축개요(폭·깊이·층수·층고)만으로 즉시 생성.
// 서버 IFC 파이프라인과 무관하게 "항상 무언가를 렌더"하는 것이 핵심(에디터가 빈 화면이 되지 않도록).
// 서버 정밀 glb가 도착하면 그쪽을 우선 사용(아래 BuildingModel).
function ProceduralBuilding({
  width, depth, floors, floorHeight, daylightNorth,
}: { width: number; depth: number; floors: number; floorHeight: number; daylightNorth?: boolean }) {
  const group = useMemo(() => {
    const w = Math.max(4, width || 20);
    const d = Math.max(4, depth || 15);
    const nf = Math.max(1, Math.round(floors || 5));
    const fh = Math.max(2.2, floorHeight || 3);
    const wallT = 0.3;
    // P5: 정북일조 단계후퇴. 북(-z)면을 층별로 후퇴(높이/2 사선). 남(+z)면은 고정.
    const baseNorth = 1.5;
    const minDepth = Math.max(4, d * 0.35);
    // 층 f(0-base)의 윗변 높이 = (f+1)*fh → 필요 북측 이격 = max(base, h/2), inset = 그 초과분.
    const floorGeom = (f: number) => {
      if (!daylightNorth) return { depth: d, zc: 0 };
      const topH = (f + 1) * fh;
      const inset = Math.max(0, topH / 2 - baseNorth);
      const depthF = Math.max(minDepth, d - inset);
      return { depth: depthF, zc: (d - depthF) / 2 }; // 남면 고정, 북면만 안으로
    };

    const matSlab = new THREE.MeshStandardMaterial({ color: "#94a3b8", roughness: 0.9, metalness: 0.05 });
    const matGlass = new THREE.MeshStandardMaterial({ color: "#60a5fa", roughness: 0.12, metalness: 0.5, transparent: true, opacity: 0.5 });
    const matMull = new THREE.MeshStandardMaterial({ color: "#e2e8f0", roughness: 0.6 });
    const matCore = new THREE.MeshStandardMaterial({ color: "#475569", roughness: 0.85 });

    const g = new THREE.Group();
    let lastDepth = d;
    let lastZc = 0;
    for (let f = 0; f < nf; f++) {
      const y = f * fh;
      const { depth: df, zc } = floorGeom(f);
      lastDepth = df; lastZc = zc;
      // 바닥 슬래브
      const slab = new THREE.Mesh(new THREE.BoxGeometry(w, 0.25, df), matSlab);
      slab.position.set(0, y, zc); slab.castShadow = true; slab.receiveShadow = true;
      g.add(slab);
      // 외피(커튼월 유리) 4면 — 남(+z)/북(-z)은 후퇴 깊이 반영
      const fb = new THREE.BoxGeometry(w * 0.98, fh * 0.86, wallT);
      const front = new THREE.Mesh(fb, matGlass); front.position.set(0, y + fh / 2, zc + df / 2); g.add(front);
      const back = new THREE.Mesh(fb, matGlass); back.position.set(0, y + fh / 2, zc - df / 2); g.add(back);
      const lr = new THREE.BoxGeometry(wallT, fh * 0.86, df * 0.98);
      const left = new THREE.Mesh(lr, matGlass); left.position.set(-w / 2, y + fh / 2, zc); g.add(left);
      const right = new THREE.Mesh(lr, matGlass); right.position.set(w / 2, y + fh / 2, zc); g.add(right);
      // 층간 멀리언(테두리 띠)
      const band = new THREE.Mesh(new THREE.BoxGeometry(w + 0.1, 0.18, df + 0.1), matMull);
      band.position.set(0, y + fh * 0.9, zc); g.add(band);
    }
    // 코어(중앙 EV·계단실) 전체 높이
    const coreW = Math.min(w * 0.32, 7);
    const coreD = Math.min(d * 0.32, 7);
    const core = new THREE.Mesh(new THREE.BoxGeometry(coreW, nf * fh, coreD), matCore);
    core.position.set(0, (nf * fh) / 2, 0); core.castShadow = true;
    g.add(core);
    // 옥상 파라펫(최상층 후퇴 깊이 따름)
    const roof = new THREE.Mesh(new THREE.BoxGeometry(w, 0.7, lastDepth), matSlab);
    roof.position.set(0, nf * fh, lastZc); g.add(roof);
    return g;
  }, [width, depth, floors, floorHeight, daylightNorth]);

  return <primitive object={group} />;
}

// 3D 렌더: 서버 glb(scene)가 있으면 그것을, 없으면 spec 기반 절차생성 모델을 표시.
// 둘 다 없으면 격자만(게이트 단계). → 빈 화면 방지.
function BuildingModel({ scene, spec }: { scene: THREE.Group | null; spec: DesignSpec | null }) {
  return (
    <group position={[0, 0, 0]}>
      {scene ? (
        <primitive object={scene} />
      ) : spec ? (
        <ProceduralBuilding
          width={spec.building_width_m}
          depth={spec.building_depth_m}
          floors={spec.floor_count}
          floorHeight={spec.floor_height_m ?? 3}
          daylightNorth={spec.daylightNorth}
        />
      ) : null}
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

// §4-E: 단면(slicer) — 전역 클립평면으로 절단선(world-y=cutHeight) 위를 잘라 내부를 본다.
// THREE.Plane((0,-1,0), cutHeight)는 y<=cutHeight를 남긴다(절단선 아래만 표시). frameloop=
// "demand"라 클립 변경 시 invalidate로 1프레임 강제 렌더. Canvas 내부에서만 사용(useThree).
function SectionClipper({ enabled, cutHeight }: { enabled: boolean; cutHeight: number }) {
  const gl = useThree((s) => s.gl);
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => {
    gl.clippingPlanes = enabled
      ? [new THREE.Plane(new THREE.Vector3(0, -1, 0), cutHeight)]
      : [];
    invalidate();
    return () => {
      gl.clippingPlanes = [];
      invalidate();
    };
  }, [gl, invalidate, enabled, cutHeight]);
  return null;
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
  const updateDesignData = useProjectContextStore((s) => s.updateDesignData);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);

  // P4: 세대믹스 시뮬레이터가 "평면 반영"한 명시 믹스(타입:면적:총세대). 도면 SVG에 mix= 로 전달.
  const [appliedMix, setAppliedMix] = useState<string | null>(null);
  const [dxfBusy, setDxfBusy] = useState(false);
  // §4-E: IFC(.ifc) 내보내기 진행 상태 — BIM 저작도구(Revit/ArchiCAD)용 export.
  const [ifcBusy, setIfcBusy] = useState(false);
  // DXF 내보내기 도면종류(평면/상세/단면/입면/배치) — design_v61 export-dxf drawing_type.
  const [dxfType, setDxfType] = useState<string>("floor_plan");
  // 편집모드 정점 드래그가 통지한 라이브 메트릭(footprint·매스치수) — 라이브 수지에 즉시 반영.
  const [editMetrics, setEditMetrics] = useState<CADEditorMetrics | null>(null);

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
  // 보안: SVG 문자열을 DOM에 직접 주입하지 않고 Blob URL + <img>로 렌더(스크립트 실행 차단).
  const [activeSvgUrl, setActiveSvgUrl] = useState<string | null>(null);
  const [drawingLoading, setDrawingLoading] = useState(false);
  const [drawingError, setDrawingError] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);
  // 3단계 스테퍼 단계(①생성 → ②확인 → ③다듬기). 진입 동선·진행 표시용(읽기 전용 시각화).
  type StudioStep = 1 | 2 | 3;
  const studioStep: StudioStep = editMode ? 3 : (spec ? 2 : 1);

  // ── 라이브 수지 스트립 입력(읽기 전용) ──
  // 스튜디오 상시: spec 치수. 편집모드: 정점 드래그가 통지한 editMetrics(footprint·매스치수)를 우선.
  const liveProFormaDesign: LiveProFormaDesign = useMemo(() => {
    const useEdit = editMode && editMetrics != null;
    return {
      footprintSqm: useEdit ? editMetrics!.footprintSqm : null,
      buildingWidthM: useEdit ? editMetrics!.buildingWidthM : (spec?.building_width_m ?? null),
      buildingDepthM: useEdit ? editMetrics!.buildingDepthM : (spec?.building_depth_m ?? null),
      floorCount: useEdit ? editMetrics!.floorCount : (spec?.floor_count ?? null),
      buildingUse: designData?.buildingType ?? spec?.building_use ?? null,
      landAreaSqm: spec?.land_area_sqm ?? null,
      unitTypes: designData?.unitTypes ?? null,
      efficiencyPct: designData?.efficiencyPct ?? null,
    };
  }, [editMode, editMetrics, spec, designData]);

  // ── 3D BIM 모델(IFC→glTF) 로딩 — 백엔드가 생성한 실제 매스 모델 ──
  const [bimScene, setBimScene] = useState<THREE.Group | null>(null);
  const [bimLoading, setBimLoading] = useState(false);
  const [bimError, setBimError] = useState<string | null>(null);
  // AI 설계 해석(DesignInterpreter 6섹션) + 매스 메타
  const [designAi, setDesignAi] = useState<Record<string, string> | null>(null);
  const [bimMass, setBimMass] = useState<Record<string, unknown> | null>(null);
  // AI 해석 패널 접기(기본 열림) — 접으면 3D가 전폭이 되고 휠 스크롤이 캔버스(CameraControls)로 직접 전달.
  const [aiPanelOpen, setAiPanelOpen] = useState(true);

  // ── 3D 카메라 시점 프리셋(비전문가용 시점 전환) ──
  const camControlsRef = useRef<CameraControls | null>(null);
  // 현재 활성 시점(버튼 활성 표시용). 기본은 리셋(기본 진입 시점).
  const [camPreset, setCamPreset] = useState<CamPresetKey>("reset");
  // 같은 버튼을 다시 눌러도 보간이 재적용되도록 하는 단조 증가 카운터.
  const [camPresetSeq, setCamPresetSeq] = useState(0);
  // 로드된 모델의 크기(한 변 기준 span·높이) — 프리셋 거리 산정 기준값(모델 없으면 기본값).
  // §4-E: minY=모델 실측 base의 world-y(절차모델=0, 서버 glTF는 Y중심화로 음수). 단면 클립평면
  // 접지에 사용 — glTF가 y=0에 접지돼 있지 않아도 절단선이 실제 모델 범위에 맞게 정렬된다.
  const [modelDims, setModelDims] = useState<{ span: number; height: number; minY: number }>({ span: 30, height: 18, minY: 0 });
  // §4-E: 단면(slicer) — 절단선 위를 잘라 내부를 본다. pct 100=전체(절단 없음).
  const [sectionOn, setSectionOn] = useState(false);
  const [sectionPct, setSectionPct] = useState(100);

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
  // 렌더 요청 in-flight 여부 — 모달을 닫아도 뷰포트 버튼 스피너로 진행 상태를 계속 표시.
  const [renderBusy, setRenderBusy] = useState(false);
  // 이 기능 1회 소요 코인(비전문가용 안내). 실제 청구는 백엔드가 charged로 회신.
  const RENDER_COST_COIN = 5;

  // ── 공용 기하 산출: 선택한 건축개요(GFA·층수) 우선, 없으면 대지+용도지역으로 자동 ──
  const resolveSpec = useCallback(async () => {
    setSpecLoading(true);
    const base = apiV1BaseUrl();
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

    // 폴백 매스도 프로젝트 개요(GFA·층수)에서 역산 — /mass 실패 시에도 "프로젝트와 무관한
    // 40×20 박스"가 잠깐 뜨던 문제 해소(정보 있으면 실제에 근접).
    const fbFloors = floors || 5;
    let fbW = 40, fbD = 20;
    if (gfa && fbFloors) {
      const fp = gfa / fbFloors;
      fbD = Math.max(8, Math.min(40, Math.sqrt(fp / 1.6)));
      fbW = Math.max(8, fp / fbD);
    } else if (landArea) {
      const side = Math.sqrt(landArea) * 0.6;  // 대지의 ~60% 변길이 가정
      fbW = Math.max(8, side); fbD = Math.max(8, side * 0.6);
    }
    const fallback: DesignSpec = {
      building_width_m: r2(fbW), building_depth_m: r2(fbD), floor_count: fbFloors, floor_height_m: 3.0,
      site_width_m: r2(fbW + 6), site_depth_m: r2(fbD + 6), setback_m: 3, unit_width_m: 8, basement_floors: 1,
      land_area_sqm: landArea, zone_code: zone, building_use: use, building_type: designData?.buildingType ?? null,
      gfa: gfa ?? null, bcr: designData?.bcr ?? null, far: designData?.far ?? null,
      total_units: null, daylightNorth: designData?.daylightNorth ?? false, project_name: "PropAI",
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
        total_units: m.total_units ?? null,
        daylightNorth: designData?.daylightNorth ?? false, project_name: "PropAI",
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
    // 세대 구성(SSOT) — 평면 세대배치·AI 해석의 "세대수·평형 부재" 해소.
    building_use: designData?.buildingType ?? "공동주택",
    unit_types: designData?.unitTypes ?? undefined,
  }), [spec, designData]);

  // spec → 도면(generate-full-set) 요청 바디
  // building_use·unit_types를 함께 보내 기준층 평면도를 실제 평형믹스로 분할.
  const drawingBody = useCallback(() => JSON.stringify({
    site_width_m: spec?.site_width_m, site_depth_m: spec?.site_depth_m,
    building_width_m: spec?.building_width_m, building_depth_m: spec?.building_depth_m,
    floor_count: spec?.floor_count, floor_height_m: spec?.floor_height_m ?? 3.0,
    basement_floors: spec?.basement_floors ?? 1, unit_width_m: spec?.unit_width_m ?? 8,
    setback_m: spec?.setback_m ?? 3, project_name: spec?.project_name ?? "PropAI",
    building_use: designData?.buildingType ?? "공동주택",
    unit_types: designData?.unitTypes ?? undefined,
  }), [spec, designData]);

  // spec → 개별 도면 SVG(GET) 쿼리스트링(2D·3D 동일 기하 공유)
  const svgQuery = useCallback(() => {
    if (!spec) return "";
    const q = new URLSearchParams({
      site_width_m: String(spec.site_width_m), site_depth_m: String(spec.site_depth_m),
      building_width_m: String(spec.building_width_m), building_depth_m: String(spec.building_depth_m),
      floor_count: String(spec.floor_count), floor_height_m: String(spec.floor_height_m),
      basement_floors: String(spec.basement_floors), unit_width_m: String(spec.unit_width_m),
      setback_m: String(spec.setback_m), project_name: spec.project_name,
      building_use: designData?.buildingType ?? "공동주택",
    });
    // 평형믹스(실제 세대 분할) — 있을 때만 전달, 없으면 백엔드 기본(59A,84A)
    const ut = designData?.unitTypes;
    if (ut && ut.length > 0) q.set("unit_types", ut.join(","));
    // P4: 시뮬레이터가 명시 반영한 믹스가 있으면 그대로(type:area:total) 전달 → 평면이 정확한 비율로 분할
    if (appliedMix) q.set("mix", appliedMix);
    return `?${q.toString()}`;
  }, [spec, designData, appliedMix]);

  const loadBimModel = useCallback(async () => {
    if (!spec) return;
    setBimLoading(true);
    setBimError(null);
    const base = apiV1BaseUrl();
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
      let meshCount = 0;
      gltf.scene.traverse((obj) => {
        if ((obj as THREE.Mesh).isMesh) {
          meshCount++;
          (obj as THREE.Mesh).castShadow = true;
          (obj as THREE.Mesh).receiveShadow = true;
        }
      });
      // ★서버 glb가 비어있으면(메시 0 — ifcopenshell 퇴화) 절차모델을 덮어쓰지 않는다.
      //  (덮어쓰면 1초 뒤 빈 화면으로 사라지던 버그). 절차모델을 그대로 유지.
      const box = new THREE.Box3().setFromObject(gltf.scene);
      const size = new THREE.Vector3();
      box.getSize(size);
      if (meshCount === 0 || (size.x < 0.1 && size.y < 0.1 && size.z < 0.1)) {
        // 정밀 IFC가 비었음 — 절차모델 유지(조용히). 사용자에겐 절차모델이 계속 보인다.
        return;
      }
      // 모델 크기 측정(바운딩박스) → 카메라 프리셋 거리 산정 기준값. minY=실측 base(단면 접지용).
      const span = Math.max(8, Math.max(size.x, size.z));
      const height = Math.max(4, size.y);
      setModelDims({ span, height, minY: box.min.y });
      setBimScene(gltf.scene);
    } catch (err) {
      setBimError(err instanceof Error ? err.message : "3D 모델을 불러오지 못했습니다.");
    } finally {
      setBimLoading(false);
    }
  }, [projectId, spec, bimBody]);

  // 절차생성 모델용 카메라 프레이밍 — spec이 준비되고 서버 glb가 아직 없으면 spec 치수로 시점 산정.
  // (서버 glb가 도착하면 loadBimModel이 실측 bbox로 다시 setModelDims → 자연 전환)
  useEffect(() => {
    if (spec && !bimScene) {
      const span = Math.max(8, spec.building_width_m || 0, spec.building_depth_m || 0);
      const height = Math.max(4, (spec.floor_count || 5) * (spec.floor_height_m || 3));
      setModelDims({ span, height, minY: 0 });  // 절차모델은 base가 y=0(층 y=f*fh)
    }
  }, [spec, bimScene]);

  // 3D 뷰 진입 시(기하 준비 후) 서버 정밀 IFC 모델 1회 로드(실패해도 절차모델은 계속 표시)
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
      const base = apiV1BaseUrl();
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
      // 기본 도면을 "단위세대 평면도(B-02-UNIT)"로 — 실배치·실명·면적·문스윙·창호·치수·방위·
      // 표제란을 갖춘 실제 건축 평면도. 없으면 기준층 평면도→첫 도면 순 폴백.
      setActiveCode((prev) => prev
        ?? (codes.includes("B-02-UNIT") ? "B-02-UNIT"
            : codes.includes("B-02-STD") ? "B-02-STD" : codes[0]) ?? null);
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
        const base = apiV1BaseUrl();
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
      const base = apiV1BaseUrl();
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

  // 활성 도면 SVG → Blob URL 변환(언마운트/교체 시 revoke). img 로드된 SVG는 스크립트 미실행.
  useEffect(() => {
    const svg = activeCode ? svgMap[activeCode] : undefined;
    if (!svg) { setActiveSvgUrl(null); return; }
    const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
    setActiveSvgUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [activeCode, svgMap]);

  // P4: 세대믹스 시뮬레이터 "평면 반영" — 명시 믹스를 도면 쿼리에 싣고, 캐시를 비워 재로드.
  // unitTypes도 스토어에 반영(다음 진입·3D 해석과 정합).
  const handleApplyMix = useCallback((mixParam: string, types: string[]) => {
    setAppliedMix(mixParam);
    setSvgMap({});  // 캐시 무효화 → svgQuery(mix 포함)로 활성 도면 재로드(아래 effect가 트리거)
    if (designData && types.length > 0) {
      updateDesignData({ ...designData, unitTypes: types });
    }
  }, [designData, updateDesignData]);

  // DXF(캐드) 내보내기 — 실제 AutoCAD 호환 .dxf 파일 다운로드(벡터 CAD 도면임을 증명).
  // drawing_type으로 평면/상세/단면/입면/배치 5종 분기(design_v61 export-dxf). 미전달 시 floor_plan(하위호환).
  const exportDxf = useCallback(async () => {
    if (!spec) return;
    setDxfBusy(true);
    try {
      const base = apiV1BaseUrl();
      const res = await fetch(`${base}/design/${encodeURIComponent(projectId)}/drawings/export-dxf`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          // 5종 도면이 각기 다른 필드를 소비하므로 spec 기반 전체 치수를 동봉(미상 필드는 백엔드 기본값).
          site_width_m: spec.site_width_m,
          site_depth_m: spec.site_depth_m,
          building_width_m: spec.building_width_m,
          building_depth_m: spec.building_depth_m,
          floor_count: spec.floor_count,
          floor_height_m: spec.floor_height_m ?? 3.0,
          basement_floors: spec.basement_floors ?? 1,
          unit_width_m: spec.unit_width_m ?? 8,
          setback_m: spec.setback_m ?? 3,
          project_name: spec.project_name ?? "PropAI",
          drawing_type: dxfType,
        }),
        signal: AbortSignal.timeout(30000),
      });
      if (!res.ok) throw new Error(String(res.status));
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${(spec.project_name || "PropAI")}_${DXF_TYPE_LABELS[dxfType] || dxfType}.dxf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      /* 다운로드 실패는 무시(사용자는 재시도 가능) */
    } finally {
      setDxfBusy(false);
    }
  }, [projectId, spec, dxfType]);

  // §4-E: IFC(.ifc) 내보내기 — 설계 매스를 IFC4 STEP 파일로 다운로드(BIM 저작도구 호환).
  // /drawing/export-ifc(파라미터→build_ifc_from_mass·DB-free)를 호출해 blob 다운로드.
  const exportIfc = useCallback(async () => {
    if (!spec) return;
    setIfcBusy(true);
    try {
      const base = apiV1BaseUrl();
      const res = await fetch(`${base}/drawing/export-ifc`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          building_width_m: spec.building_width_m,
          building_depth_m: spec.building_depth_m,
          num_floors: spec.floor_count,
          floor_height_m: spec.floor_height_m ?? 3.0,
          project_name: spec.project_name ?? "PropAI",
        }),
        signal: AbortSignal.timeout(60000),
      });
      if (!res.ok) throw new Error(String(res.status));
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${spec.project_name || "PropAI"}.ifc`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      /* 다운로드 실패는 무시(사용자는 재시도 가능) */
    } finally {
      setIfcBusy(false);
    }
  }, [spec]);

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
    if (!gl || (!bimScene && !spec)) {
      // 모델(절차/서버)이 없으면 캡처할 화면이 없음 — 정직 안내(가짜 호출 금지).
      setRenderMsg("먼저 설계를 생성한 뒤 렌더할 수 있습니다.");
      setRenderPhase("error");
      return;
    }
    setRenderPhase("loading");
    setRenderMsg(null);
    setRenderImage(null);
    setRenderCharged(null);
    setRenderBusy(true);

    try {
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
        // W-B(서버 폴링) 이후 시간 내 미완료면 202류 본문(pending|processing)이 올 수 있다 — 지연 안내+재시도.
        const resp = await apiClient.post<{
          status: "ok" | "no_key" | "error" | "pending" | "processing";
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
        if (resp.status === "pending" || resp.status === "processing") {
          // 서버가 아직 처리 중(202/폴링 미완) — 실패가 아님을 정직 안내, 재시도 유도.
          setRenderMsg(resp.message || "렌더가 오래 걸리고 있습니다. 잠시 후 '다시 시도'를 눌러 주세요.");
          setRenderPhase("error");
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
        // 인증·서버 오류 등 HTTP 비-2xx. 408은 apiClient 자체 타임아웃, 202/504는 지연 계열로 분기.
        const msg = err instanceof ApiClientError
          ? (err.status === 402 ? "코인이 부족합니다. 충전 후 다시 시도하세요."
            : err.status === 401 ? "로그인이 만료되었습니다. 다시 로그인 후 시도하세요."
            : err.status === 403 ? "이 기능 사용 권한이 없습니다."
            : err.status === 202 || err.status === 408 || err.status === 504
              ? "렌더가 오래 걸리고 있습니다. 서버에서 계속 처리 중일 수 있어요 — 잠시 후 다시 시도해 주세요."
            : "AI 렌더 요청이 거부되었습니다.")
          : "네트워크 오류로 AI 렌더에 실패했습니다.";
        setRenderMsg(msg);
        setRenderPhase("error");
      }
    } finally {
      setRenderBusy(false);
    }
  }, [projectId, bimScene, spec, renderStyle]);

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
        {/* 2D/3D 전환 토글은 결과 뷰포트 상단 중앙의 세그먼트 칩으로 이동(아래 뷰포트 컨테이너 내부) —
            "보는 화면과 전환 버튼"이 한곳에 있도록(헤더↔뷰포트 시선 왕복 제거). */}
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

      {/* ── 3단계 스테퍼(①AI로 생성 → ②도면·3D 확인 → ③직접 다듬고 내보내기) — 쉬운 모드 동선 안내 ── */}
      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] px-5 py-3 -mt-4">
        {([
          [1, "AI로 생성", "슬라이더·자연어로 설계안 생성"],
          [2, "도면·3D 확인", "평면·단면·3D 매스 확인"],
          [3, "다듬고 내보내기", "정점 드래그·Ctrl+Z·DXF"],
        ] as [StudioStep, string, string][]).map(([n, label, hint], i) => {
          const active = studioStep === n;
          const done = studioStep > n;
          return (
            <div key={n} className="flex items-center gap-2">
              {i > 0 && <span className="text-[var(--text-hint)]">→</span>}
              <div
                className={`flex items-center gap-2 rounded-full px-3 py-1.5 transition-colors ${
                  active
                    ? "bg-[var(--accent-strong)]/15 border border-[var(--accent-strong)]/50"
                    : done
                      ? "bg-[var(--surface-strong)] border border-[var(--line)]"
                      : "border border-transparent"
                }`}
                title={hint}
              >
                <span
                  className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-black ${
                    active
                      ? "bg-[var(--accent-strong)] text-white"
                      : done
                        ? "bg-[var(--accent-strong)]/40 text-[var(--text-primary)]"
                        : "bg-[var(--surface-strong)] text-[var(--text-hint)]"
                  }`}
                >
                  {done ? "✓" : n}
                </span>
                <span
                  className={`text-[11px] font-black ${
                    active ? "text-[var(--accent-strong)]" : "text-[var(--text-secondary)]"
                  }`}
                >
                  {label}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── 편집화면(2D/3D 뷰포트) — 생성 UX 바로 아래(상단 배치). 설계 해석 요약은 뷰포트 아래로 이동. ── */}
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
              <BuildingModel scene={bimScene} spec={spec} />
              {/* §4-E 단면: 절단선을 모델 실측 base(minY)에 접지 — world-y = minY + 상대절단높이.
                  서버 glTF가 Y중심화돼 base가 y=0이 아니어도 슬라이더 전 범위가 정확히 작동한다. */}
              <SectionClipper
                enabled={sectionOn && (!!bimScene || !!spec)}
                cutHeight={modelDims.minY + sectionCutHeightM(sectionPct, modelDims.height)}
              />
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
                      disabled={!bimScene && !spec}
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
              {!bimScene && !spec && (
                <span className="rounded-lg bg-black/40 px-3 py-1 text-[10px] font-bold text-white/45 backdrop-blur-md">
                  설계를 생성하면 시점 전환을 사용할 수 있어요
                </span>
              )}
            </div>

            {/* 자동회전 토글(기본 꺼짐) — 절차모델/서버모델 모두에서 사용 */}
            {(bimScene || spec) && (
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

            {/* §4-E 단면(slicer) — 절단선 높이를 내려 건물 내부(층별)를 들여다본다 */}
            {(bimScene || spec) && (
              <div className="absolute bottom-6 left-1/2 z-30 flex -translate-x-1/2 items-center gap-3 rounded-2xl border border-white/10 bg-black/45 px-4 py-2 backdrop-blur-xl shadow-2xl">
                <button
                  type="button"
                  onClick={() => setSectionOn((v) => !v)}
                  aria-pressed={sectionOn}
                  title="건물을 수평으로 잘라 내부(층별)를 봅니다"
                  className={`rounded-full px-3 py-1.5 text-[10px] font-black uppercase tracking-widest transition-colors ${
                    sectionOn
                      ? "bg-[var(--accent-strong)] text-white"
                      : "text-white/55 hover:text-white hover:bg-white/10"
                  }`}
                >
                  {sectionOn ? "■ 단면 ON" : "▤ 단면"}
                </button>
                {sectionOn && (
                  <>
                    <input
                      type="range"
                      min={0}
                      max={100}
                      step={1}
                      value={sectionPct}
                      onChange={(e) => setSectionPct(Number(e.target.value))}
                      aria-label="단면 절단 높이(%)"
                      className="w-40 cursor-pointer accent-[var(--accent-strong)]"
                    />
                    <span className="whitespace-nowrap text-[10px] font-bold tabular-nums text-white/70">
                      보이는 층 {visibleFloorCount(
                        sectionCutHeightM(sectionPct, modelDims.height),
                        spec?.floor_height_m ?? 3,
                        spec?.floor_count ?? 0,
                      )}/{spec?.floor_count ?? "—"} · 절단 {sectionCutHeightM(sectionPct, modelDims.height).toFixed(1)}m
                    </span>
                  </>
                )}
              </div>
            )}

            {/* ── AI 포토리얼 렌더 버튼(과금 게이트) — 모델(절차/서버) 있을 때 노출.
                렌더 in-flight면 스피너로 진행 표시(모달을 닫았다가 눌러도 진행 모달로 복귀). ── */}
            {(bimScene || spec) && (
              <button
                type="button"
                onClick={() => setRenderPhase(renderBusy ? "loading" : "confirm")}
                className="absolute right-6 top-6 z-30 flex items-center gap-2 rounded-full border border-[var(--accent-strong)]/60 bg-[var(--accent-strong)]/15 px-5 py-2.5 text-[10px] font-black uppercase tracking-widest text-[var(--accent-strong)] backdrop-blur-xl shadow-lg transition-colors hover:bg-[var(--accent-strong)]/25"
              >
                {renderBusy ? (
                  <>
                    <span className="h-3 w-3 animate-spin rounded-full border-2 border-[var(--accent-strong)] border-t-transparent" />
                    렌더 중…
                  </>
                ) : (
                  <>
                    <span className="text-[12px] leading-none">✦</span>
                    AI 포토리얼 렌더
                  </>
                )}
              </button>
            )}
            {/* ── 비차폐 상태 칩 — 절차모델은 즉시 렌더되므로 전체화면 오버레이로 막지 않는다 ── */}
            {bimLoading && (
              <div className="absolute bottom-6 left-1/2 z-20 flex -translate-x-1/2 items-center gap-2 rounded-full bg-black/55 px-4 py-2 backdrop-blur-xl border border-white/10 pointer-events-none">
                <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-[var(--accent-strong)] border-t-transparent" />
                <span className="text-[10px] font-bold uppercase tracking-widest text-white/65">정밀 IFC 모델 생성 중 · 현재 절차모델 표시</span>
              </div>
            )}
            {bimError && !bimLoading && (
              <div className="absolute bottom-6 left-1/2 z-20 flex -translate-x-1/2 items-center gap-3 rounded-full bg-black/65 px-4 py-2 backdrop-blur-xl border border-amber-400/30">
                <span className="text-[10px] font-bold text-amber-200">절차모델 표시 중 · 정밀 IFC 생성 실패</span>
                <button
                  onClick={() => { setBimError(null); loadBimModel(); }}
                  className="rounded-full bg-white/10 px-3 py-1 text-[10px] font-black uppercase tracking-widest text-white hover:bg-white/20"
                >
                  다시 시도
                </button>
              </div>
            )}
          </div>
        ) : editMode ? (
          <div className="absolute inset-0 z-30 bg-[#0a0f14] flex flex-col overflow-hidden [&>div]:h-full [&>div]:rounded-none [&>div]:border-none">
            {/* 편집 종료 → 도면 확인(②) 화면으로 복귀. CADEditor 내부 칩과 비충돌 위치(좌상단). */}
            <button
              onClick={() => { setEditMode(false); setEditMetrics(null); }}
              className="absolute left-4 top-4 z-40 rounded-full border border-white/15 bg-black/60 px-4 py-2 text-[10px] font-black uppercase tracking-widest text-white/80 backdrop-blur-xl hover:bg-white/15"
            >
              ← 편집 종료
            </button>
            <CADEditor
              projectId={projectId}
              siteAreaSqm={spec?.land_area_sqm}
              initialWidthM={spec?.building_width_m}
              initialDepthM={spec?.building_depth_m}
              initialFloors={spec?.floor_count}
              initialFloorHeightM={spec?.floor_height_m ?? 3}
              zoneCode={spec?.zone_code}
              onMetricsChange={setEditMetrics}
            />
          </div>
        ) : (
          <div className="absolute inset-0 z-30 bg-[#0a0f14] flex flex-col">
            {/* 상단 바: 도면 선택 드롭다운(공간 최적화) + 편집모드 전환.
                pt-16 = 뷰포트 상단 중앙의 플로팅 2D/3D 토글(absolute top-6)과 겹치지 않도록 상단 여백 확보.
                flex-wrap = 좁은 폭/확대 시 우측 버튼군(내보내기·다듬기)이 토글 위로 올라타지 않게 줄바꿈. */}
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/5 px-6 pt-16 pb-3">
              <label className="flex items-center gap-2">
                <span className="text-[10px] font-black uppercase tracking-widest text-white/40">도면</span>
                <select
                  value={activeCode ?? ""}
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
              <div className="flex shrink-0 items-center gap-2">
                {/* DXF 도면종류 셀렉트(평면/상세/단면/입면/배치) — export-dxf drawing_type 분기 */}
                <label className="flex items-center gap-1.5">
                  <span className="text-[9px] font-black uppercase tracking-widest text-white/35">종류</span>
                  <select
                    value={dxfType}
                    onChange={(e) => setDxfType(e.target.value)}
                    title="내보낼 DXF 도면 종류"
                    className="rounded-lg border border-white/10 bg-white/5 px-2 py-1.5 text-[11px] font-bold text-white focus:border-[var(--accent-strong)] focus:outline-none"
                  >
                    {DXF_TYPE_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value} className="bg-[#0a0f14] text-white">
                        {o.label}
                      </option>
                    ))}
                  </select>
                </label>
                {/* DXF(캐드) 내보내기 — 실제 AutoCAD 호환 벡터 도면 파일 다운로드 */}
                <button
                  onClick={exportDxf}
                  disabled={dxfBusy || !spec}
                  title="AutoCAD 등에서 열 수 있는 벡터 CAD 도면(.dxf)으로 내보냅니다"
                  className="rounded-full border border-white/10 px-4 py-2 text-[10px] font-black uppercase tracking-widest text-white/70 hover:bg-white/5 disabled:opacity-50"
                >
                  {dxfBusy ? "내보내는 중…" : "⬇ DXF(캐드) 내보내기"}
                </button>
                {/* §4-E: IFC(.ifc) 내보내기 — Revit/ArchiCAD 등 BIM 저작도구 호환(read-only 해소) */}
                <button
                  onClick={exportIfc}
                  disabled={ifcBusy || !spec}
                  title="Revit·ArchiCAD 등 BIM 저작도구에서 열 수 있는 IFC4(.ifc) 모델로 내보냅니다"
                  className="rounded-full border border-white/10 px-4 py-2 text-[10px] font-black uppercase tracking-widest text-white/70 hover:bg-white/5 disabled:opacity-50"
                >
                  {ifcBusy ? "내보내는 중…" : "⬇ IFC(BIM) 내보내기"}
                </button>
                {/* ③ 도면 다듬기 CTA — 편집모드 직행(쉬운 모드 동선) */}
                <button
                  onClick={() => setEditMode(true)}
                  className="rounded-full border border-[var(--accent-strong)]/60 bg-[var(--accent-strong)]/15 px-4 py-2 text-[10px] font-black uppercase tracking-widest text-[var(--accent-strong)] hover:bg-[var(--accent-strong)]/25"
                >
                  ③ 도면 다듬기
                </button>
              </div>
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
              {!drawingLoading && !drawingError && activeCode && activeSvgUrl && (
                <div className="flex h-full w-full max-w-[920px] items-center justify-center rounded-2xl bg-white p-5 shadow-2xl">
                  {/* 보안: dangerouslySetInnerHTML 대신 Blob URL <img>로 렌더 — img로 로드된
                      SVG는 스크립트·이벤트핸들러가 실행되지 않는다(XSS 차단).
                      모든 도면이 viewBox+100%(반응형)라 컨테이너를 꽉 채워 크게 렌더된다. */}
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={activeSvgUrl} alt={DRAWING_LABELS[activeCode] || activeCode} className="max-h-full w-full" />
                </div>
              )}
              {!drawingLoading && !drawingError && activeCode && !activeSvgUrl && (
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
            {/* ── AI 해석 패널(접이식) — 기본 열림. 접으면 슬림 세로 칩만 남아 3D 전폭 + 휠이 캔버스로 직접 전달 ── */}
            {aiPanelOpen ? (
            <motion.div
              initial={{ opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.25, ease: "easeOut" }}
              className="absolute right-6 top-[5.5rem] flex max-h-[80%] w-[340px] flex-col gap-3 z-20 overflow-y-auto"
            >
              {/* 헤더 행: 제목 + 접기 버튼 */}
              <div className="flex shrink-0 items-center justify-between rounded-2xl border border-white/10 bg-black/70 px-4 py-2.5 text-white backdrop-blur-2xl shadow-2xl">
                <p className="text-[9px] font-black uppercase tracking-[0.3em] text-indigo-300">AI 설계 해석</p>
                <button
                  type="button"
                  onClick={() => setAiPanelOpen(false)}
                  title="패널을 접고 3D를 넓게 봅니다"
                  className="rounded-full px-2 py-0.5 text-[10px] font-black uppercase tracking-widest text-white/50 transition-colors hover:bg-white/10 hover:text-white"
                >
                  접기 ▸
                </button>
              </div>
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
            </motion.div>
            ) : (
            /* 접힘 상태: 슬림 세로 칩만 — 클릭하면 다시 펼침 */
            <motion.button
              initial={{ opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.25, ease: "easeOut" }}
              type="button"
              onClick={() => setAiPanelOpen(true)}
              title="AI 설계 해석 패널 펼치기"
              className="absolute right-0 top-[5.5rem] z-20 rounded-l-2xl border border-r-0 border-white/10 bg-black/70 px-2 py-4 text-[10px] font-black uppercase tracking-[0.25em] text-indigo-300 backdrop-blur-2xl shadow-2xl transition-colors hover:bg-black/85 [writing-mode:vertical-rl]"
            >
              AI 해석 ▸
            </motion.button>
            )}

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

        {/* ── 2D/3D 전환 세그먼트 칩 — 뷰포트 상단 중앙(헤더에서 이동). 프리셋 바와 동일 토큰.
            편집모드에서는 숨김(편집 종료 버튼과 동선 충돌 방지). 3D 클릭 시 editMode 해제 선행. ── */}
        {!editMode && (
          <div className="absolute left-1/2 top-6 z-30 flex -translate-x-1/2 items-center gap-1.5 rounded-2xl border border-white/10 bg-black/45 p-1.5 backdrop-blur-xl shadow-2xl">
            <button
              type="button"
              onClick={() => setViewMode("cad_2d")}
              className={`rounded-xl px-4 py-2 text-[10px] font-black uppercase tracking-widest transition-colors ${
                viewMode === "cad_2d"
                  ? "bg-[var(--accent-strong)] text-white shadow-lg"
                  : "text-white/55 hover:text-white hover:bg-white/10"
              }`}
            >
              {t.btn2D || "2D 도면"}
            </button>
            <button
              type="button"
              onClick={() => { setEditMode(false); setViewMode("bim_3d"); }}
              className={`rounded-xl px-4 py-2 text-[10px] font-black uppercase tracking-widest transition-colors ${
                viewMode === "bim_3d"
                  ? "bg-[var(--accent-strong)] text-white shadow-lg"
                  : "text-white/55 hover:text-white hover:bg-white/10"
              }`}
            >
              {t.btn3D || "3D BIM"}
            </button>
          </div>
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
                        disabled={renderBusy}
                        className="flex items-center gap-2 rounded-full bg-[var(--accent-strong)] px-6 py-2.5 text-xs font-black uppercase tracking-widest text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {renderBusy ? (
                          <>
                            <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
                            렌더 중…
                          </>
                        ) : (
                          <>결제하고 렌더 ({RENDER_COST_COIN}코인)</>
                        )}
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

      {/* ── 라이브 수지 스트립(TestFit 차별화) — 스튜디오 상시 마운트 + 편집모드 정점 드래그 즉시 갱신 ──
          읽기 전용: 기존 unit-mix/simulate(+footprint_sqm)를 400ms 디바운스로 재사용, SSOT 비침범. ── */}
      {hasDesignBasis && spec && (
        <LiveProFormaStrip
          projectId={projectId}
          design={liveProFormaDesign}
          contextLabel={editMode ? "편집 반영" : undefined}
        />
      )}

      {/* ── P4: 세대믹스 시뮬레이터(비율 슬라이더 → 평면 재배치 + 약식 수지 실시간) ── */}
      {hasDesignBasis && spec && (
        <UnitMixSimulatorPanel
          projectId={projectId}
          buildingWidthM={spec.building_width_m}
          buildingDepthM={spec.building_depth_m}
          floorCount={spec.floor_count}
          landAreaSqm={spec.land_area_sqm}
          buildingUse={designData?.buildingType ?? spec.building_use}
          defaultTypes={designData?.unitTypes ?? undefined}
          onApplyMix={handleApplyMix}
        />
      )}

      {/* ── 설계 결과 요약 + AI 설계 해석(designAi 6섹션) — 편집화면(뷰포트) 아래로 재배치 ── */}
      <DesignOutcomeSummary projectId={projectId} designAi={designAi} />
    </div>
  );
}
