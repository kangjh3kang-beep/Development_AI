"use client";

/**
 * 가상준공 3D 디지털트윈 씬 — 지도(지형·항공) 위에 필지·AI 건물 매스·주변건물을 합성.
 *
 * 모태: components/design/CadBimIntegrationPanel.tsx (진짜 @react-three/fiber + GLTFLoader.parseAsync).
 * 그 패턴(Canvas / directionalLight / OrbitControls / GLTFLoader / dynamic ssr:false)을 확장한다.
 *
 * ⚠ 정직성 가드(비협상): 표고=광역 DEM(실측 아님), 주변=footprint 추정(점선·반투명),
 *   매스=AI 절차생성(인허가 도면 아님), 항공=촬영시점 상이 가능. 추정/실측 시각 구분.
 */

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { TextureLoader } from "three";
import * as THREE from "three";
import { apiClient, resolveApiOrigin } from "@/lib/api-client";
import {
  useAnalysisCache,
  analysisSignature,
  relativeKoreanTime,
} from "@/lib/use-analysis-cache";
import { AnalysisCacheStatus } from "@/components/common/AnalysisCacheStatus";
import type {
  DigitalTwinScenePayload,
  DigitalTwinTerrain,
  DigitalTwinParcel,
  DigitalTwinNeighbor,
  DigitalTwinAerial,
  DigitalTwinBuilding,
  DigitalTwinLayers,
} from "./types";
import type { EnvironmentResult, SunPosition } from "@/components/environment/types";
import type { TerrainResult } from "@/components/terrain/types";
import { DigitalTwinAiCard } from "./DigitalTwinAiCard";

const ACCENT = "#3b82f6";

/** 용도지역명(한글) → 절대 높이한도(m). 대부분 비주거는 FAR 기반(절대높이 없음)이라 미수록 → null.
 *  주거지역의 약식 높이한도(정북 일조사선 외 별도 절대 상한이 통상 적용되지 않으므로
 *  여기서는 가시화용 보수적 참고치). 자료 없는 zone은 키 미존재 → 고도제한 면 미생성. */
const ZONE_MAX_HEIGHT_M: Record<string, number> = {
  제1종전용주거지역: 12,
  제2종전용주거지역: 16,
  제1종일반주거지역: 16,
  제2종일반주거지역: 25,
};

/** 용도지역명에 "주거"가 포함되면 정북 일조사선 적용 대상으로 본다(상업/공업/녹지 제외). */
function isResidentialZone(zone: string | null | undefined): boolean {
  return !!zone && zone.includes("주거");
}

/** zone_type(한글) → 절대 높이한도(m) 또는 null(FAR 기반·절대높이 없음). */
function zoneMaxHeightM(zone: string | null | undefined): number | null {
  if (!zone) return null;
  const key = Object.keys(ZONE_MAX_HEIGHT_M).find((k) => zone.includes(k));
  return key ? ZONE_MAX_HEIGHT_M[key] : null;
}

/** 항공 프록시 URL 절대화 — 백엔드가 상대경로(/api/...)를 주면 API 오리진과 결합.
 *  절대 URL이면 그대로. Cloudflare 프론트 오리진에서 api.4t8t.net로 보내기 위함(WARN-1). */
function absolutizeAerialUrl(url: string): string {
  if (/^https?:\/\//.test(url)) return url;
  const origin = resolveApiOrigin();
  return url.startsWith("/") ? `${origin}${url}` : `${origin}/${url}`;
}

/** 표고 그라데이션(저→고): 청록 → 초록 → 황 → 적갈. */
function elevationColor(t: number): THREE.Color {
  const stops: [number, [number, number, number]][] = [
    [0.0, [0.13, 0.55, 0.55]],
    [0.4, [0.18, 0.65, 0.36]],
    [0.7, [0.86, 0.7, 0.27]],
    [1.0, [0.6, 0.35, 0.25]],
  ];
  let lo = stops[0];
  let hi = stops[stops.length - 1];
  for (let i = 0; i < stops.length - 1; i++) {
    if (t >= stops[i][0] && t <= stops[i + 1][0]) {
      lo = stops[i];
      hi = stops[i + 1];
      break;
    }
  }
  const span = hi[0] - lo[0] || 1;
  const k = (t - lo[0]) / span;
  return new THREE.Color(
    lo[1][0] + (hi[1][0] - lo[1][0]) * k,
    lo[1][1] + (hi[1][1] - lo[1][1]) * k,
    lo[1][2] + (hi[1][2] - lo[1][2]) * k,
  );
}

/** 경사도 컬러맵(0=평지 → 1=급경사): 초록 → 황 → 적. */
function slopeColor(t: number): THREE.Color {
  const stops: [number, [number, number, number]][] = [
    [0.0, [0.06, 0.72, 0.51]], // 평지(초록)
    [0.5, [0.96, 0.62, 0.07]], // 경사(황)
    [1.0, [0.94, 0.27, 0.27]], // 급경사(적)
  ];
  let lo = stops[0];
  let hi = stops[stops.length - 1];
  for (let i = 0; i < stops.length - 1; i++) {
    if (t >= stops[i][0] && t <= stops[i + 1][0]) {
      lo = stops[i];
      hi = stops[i + 1];
      break;
    }
  }
  const span = hi[0] - lo[0] || 1;
  const k = (t - lo[0]) / span;
  return new THREE.Color(
    lo[1][0] + (hi[1][0] - lo[1][0]) * k,
    lo[1][1] + (hi[1][1] - lo[1][1]) * k,
    lo[1][2] + (hi[1][2] - lo[1][2]) * k,
  );
}

/** 지형 메시: verts/indices → BufferGeometry. 항공 드레이프(텍스처) 또는 표고/경사도 vertexColors. */
function TerrainMesh({
  terrain,
  aerial,
  useAerial,
  colorMode,
}: {
  terrain: DigitalTwinTerrain;
  aerial: DigitalTwinAerial | null;
  useAerial: boolean;
  /** "elevation" | "slope" — 신규 백엔드 호출 0(씬이 받은 verts로 경사도 계산). */
  colorMode: "elevation" | "slope";
}) {
  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry();
    const positions = new Float32Array(terrain.verts.length * 3);
    let minY = Infinity;
    let maxY = -Infinity;
    let minX = Infinity;
    let maxX = -Infinity;
    let minZ = Infinity;
    let maxZ = -Infinity;
    (terrain.verts ?? []).forEach((v, i) => {
      positions[i * 3] = v[0];
      positions[i * 3 + 1] = v[1];
      positions[i * 3 + 2] = v[2];
      if (v[1] < minY) minY = v[1];
      if (v[1] > maxY) maxY = v[1];
      if (v[0] < minX) minX = v[0];
      if (v[0] > maxX) maxX = v[0];
      if (v[2] < minZ) minZ = v[2];
      if (v[2] > maxZ) maxZ = v[2];
    });
    g.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    g.setIndex(terrain.indices);
    g.computeVertexNormals();

    const colors = new Float32Array(terrain.verts.length * 3);
    if (colorMode === "slope") {
      // 정점 법선의 수평면 기준 경사각(=수직축 y와 이루는 각)으로 경사도 재색.
      // 경사도 ≈ tan(각). 0~50% 구간을 0~1로 정규화(급경사 적색 포화).
      const normalAttr = g.getAttribute("normal") as THREE.BufferAttribute;
      for (let i = 0; i < terrain.verts.length; i++) {
        const ny = Math.min(1, Math.max(-1, normalAttr.getY(i)));
        const slopeAngle = Math.acos(Math.abs(ny)); // rad, 수평면 대비 경사각
        const slopePct = Math.tan(slopeAngle); // 경사도(비율)
        const c = slopeColor(Math.min(1, slopePct / 0.5));
        colors[i * 3] = c.r;
        colors[i * 3 + 1] = c.g;
        colors[i * 3 + 2] = c.b;
      }
    } else {
      // 표고 그라데이션 vertexColors
      const ySpan = maxY - minY || 1;
      (terrain.verts ?? []).forEach((v, i) => {
        const c = elevationColor((v[1] - minY) / ySpan);
        colors[i * 3] = c.r;
        colors[i * 3 + 1] = c.g;
        colors[i * 3 + 2] = c.b;
      });
    }
    g.setAttribute("color", new THREE.BufferAttribute(colors, 3));

    // 항공 드레이프용 UV(평면 투영 XZ → 0..1)
    const xSpan = maxX - minX || 1;
    const zSpan = maxZ - minZ || 1;
    const uvs = new Float32Array(terrain.verts.length * 2);
    (terrain.verts ?? []).forEach((v, i) => {
      uvs[i * 2] = (v[0] - minX) / xSpan;
      uvs[i * 2 + 1] = 1 - (v[2] - minZ) / zSpan;
    });
    g.setAttribute("uv", new THREE.BufferAttribute(uvs, 2));

    return g;
  }, [terrain, colorMode]);

  // 항공 텍스처 정합: 실사 영상의 실제 지상 커버(가로 cover_lon_m·세로 cover_lat_m)를
  // 지형 메시 폭(bbox)에 맞춰 UV repeat/offset으로 보정 → 늘어짐 없이 1:1 정렬.
  const bboxM = terrain?.bbox_m?.size_m ?? aerial?.cover_m ?? 300;
  const aerialAny = aerial as (DigitalTwinAerial & { cover_lon_m?: number; cover_lat_m?: number }) | null;
  const coverLon = aerialAny?.cover_lon_m ?? aerial?.cover_m ?? bboxM;
  const coverLat = aerialAny?.cover_lat_m ?? aerial?.cover_m ?? bboxM;
  const repeatX = coverLon > 0 ? Math.min(1, bboxM / coverLon) : 1;
  const repeatY = coverLat > 0 ? Math.min(1, bboxM / coverLat) : 1;

  return (
    <mesh geometry={geometry} receiveShadow>
      {useAerial && aerial?.image_proxy_url ? (
        <Suspense fallback={<meshStandardMaterial color="#1e293b" roughness={1} metalness={0} />}>
          <AerialMaterial
            url={absolutizeAerialUrl(aerial.image_proxy_url)}
            repeatX={repeatX}
            repeatY={repeatY}
          />
        </Suspense>
      ) : (
        <meshStandardMaterial vertexColors flatShading roughness={0.95} metalness={0} />
      )}
    </mesh>
  );
}

/** 항공 텍스처 머티리얼(절대 프록시 URL). 로드 실패(404/CORS) 시 회색 폴백 유지.
 *  repeatX/Y: 실사 커버리지 vs 지형 bbox 비율 — 텍스처를 중앙 기준으로 메시 실폭에 정합. */
function AerialMaterial({
  url,
  repeatX = 1,
  repeatY = 1,
}: {
  url: string;
  repeatX?: number;
  repeatY?: number;
}) {
  const [texture, setTexture] = useState<THREE.Texture | null>(null);

  useEffect(() => {
    let cancelled = false;
    const loader = new TextureLoader();
    // three TextureLoader 기본 crossOrigin=anonymous(CORS 응답 필요).
    loader.setCrossOrigin("anonymous");
    loader.load(
      url,
      (tex) => {
        if (cancelled) {
          tex.dispose();
          return;
        }
        setTexture(tex);
      },
      undefined,
      () => {
        /* 로드 실패는 무시 — 회색 폴백 유지 */
      },
    );
    return () => {
      cancelled = true;
    };
  }, [url]);

  // 커버리지 정합: 텍스처의 실지상폭을 메시 폭에 맞춰 중앙 크롭(늘어짐 제거).
  useEffect(() => {
    if (!texture) return;
    texture.wrapS = THREE.ClampToEdgeWrapping;
    texture.wrapT = THREE.ClampToEdgeWrapping;
    texture.repeat.set(repeatX, repeatY);
    texture.offset.set((1 - repeatX) / 2, (1 - repeatY) / 2);
    texture.needsUpdate = true;
  }, [texture, repeatX, repeatY]);

  if (!texture) {
    return <meshStandardMaterial color="#1e293b" roughness={1} metalness={0} />;
  }
  return <meshStandardMaterial map={texture} roughness={0.95} metalness={0} />;
}

/** 필지 경계: ring_enu → LineLoop(실선·강조색). y는 지형표고 근처. */
function ParcelOutline({ parcel, baseY }: { parcel: DigitalTwinParcel; baseY: number }) {
  const geometry = useMemo(() => {
    const pts = (parcel.ring_enu ?? []).map((p) => new THREE.Vector3(p[0], baseY + 0.6, p[1]));
    return new THREE.BufferGeometry().setFromPoints(pts);
  }, [parcel, baseY]);
  return (
    <lineLoop geometry={geometry}>
      <lineBasicMaterial color={ACCENT} linewidth={2} />
    </lineLoop>
  );
}

/** 주변 건물: footprint_enu를 height_m로 압출. 추정=반투명 회색+점선 윤곽. */
function NeighborBuildings({ neighbors, baseY }: { neighbors: DigitalTwinNeighbor[]; baseY: number }) {
  const meshes = useMemo(() => {
    return neighbors.map((nb) => {
      const shape = new THREE.Shape();
      (nb.footprint_enu ?? []).forEach((p, i) => {
        if (i === 0) shape.moveTo(p[0], p[1]);
        else shape.lineTo(p[0], p[1]);
      });
      const geom = new THREE.ExtrudeGeometry(shape, {
        depth: Math.max(3, nb.height_m),
        bevelEnabled: false,
      });
      // ExtrudeGeometry는 XY 평면에 +Z로 압출 → XZ 지면에 세우려 X축 -90° 회전
      geom.rotateX(-Math.PI / 2);
      // 윤곽선(점선=추정)용 라인
      const edges = new THREE.EdgesGeometry(geom);
      return { geom, edges };
    });
  }, [neighbors]);

  return (
    <group position={[0, baseY, 0]}>
      {meshes.map(({ geom, edges }, i) => (
        <group key={i}>
          <mesh geometry={geom}>
            <meshStandardMaterial
              color="#94a3b8"
              transparent
              opacity={0.32}
              roughness={0.9}
              metalness={0}
              depthWrite={false}
            />
          </mesh>
          <lineSegments
            geometry={edges}
            ref={(ls) => {
              // 점선(추정 표시)은 computeLineDistances 필요
              if (ls) ls.computeLineDistances();
            }}
          >
            <lineDashedMaterial color="#cbd5e1" dashSize={1.4} gapSize={0.9} transparent opacity={0.6} />
          </lineSegments>
        </group>
      ))}
    </group>
  );
}

/** 우리 건물(AI 절차생성 glb). glb 재배치 금지 — group.position만 이동. */
function BuildingGlb({ building }: { building: DigitalTwinBuilding }) {
  const [scene, setScene] = useState<THREE.Group | null>(null);
  const urlRef = useRef<string | null>(null);

  useEffect(() => {
    if (!building.glb_url || urlRef.current === building.glb_url) return;
    urlRef.current = building.glb_url;
    let cancelled = false;
    const loader = new GLTFLoader();
    loader
      .loadAsync(building.glb_url)
      .then((gltf) => {
        if (cancelled) return;
        gltf.scene.traverse((obj) => {
          if ((obj as THREE.Mesh).isMesh) {
            (obj as THREE.Mesh).castShadow = true;
            (obj as THREE.Mesh).receiveShadow = true;
          }
        });
        setScene(gltf.scene);
      })
      .catch(() => {
        /* glb 로드 실패는 무시 — 지형·필지는 계속 표시 */
      });
    return () => {
      cancelled = true;
    };
  }, [building.glb_url]);

  if (!scene) return null;
  // place_at_enu = [x, elev0, z] — glb 내부 기하는 건드리지 않고 group만 앉힌다.
  return (
    <group position={[building.place_at_enu[0], building.place_at_enu[1], building.place_at_enu[2]]}>
      <primitive object={scene} />
    </group>
  );
}

/** 필지 ENU 링의 XZ bbox(min/max). 고도제한 평면·envelope 크기 산출에 공용. */
function parcelBboxEnu(parcel: DigitalTwinParcel): { minX: number; maxX: number; minZ: number; maxZ: number } {
  let minX = Infinity;
  let maxX = -Infinity;
  let minZ = Infinity;
  let maxZ = -Infinity;
  (parcel.ring_enu ?? []).forEach((p) => {
    if (p[0] < minX) minX = p[0];
    if (p[0] > maxX) maxX = p[0];
    if (p[1] < minZ) minZ = p[1];
    if (p[1] > maxZ) maxZ = p[1];
  });
  return { minX, maxX, minZ, maxZ };
}

/** 고도제한 평면: y=baseY+maxHeightM 에 필지 bbox 크기 반투명 plane(절대 높이한도 가시화). */
function HeightLimitPlane({
  parcel,
  baseY,
  maxHeightM,
}: {
  parcel: DigitalTwinParcel;
  baseY: number;
  maxHeightM: number;
}) {
  const { geometry, cx, cz } = useMemo(() => {
    // 빈/부족한 필지 링이면 Infinity bbox→NaN 지오메트리 방지(가드)
    if (!parcel.ring_enu || parcel.ring_enu.length < 3) {
      return { geometry: null as THREE.PlaneGeometry | null, cx: 0, cz: 0 };
    }
    const b = parcelBboxEnu(parcel);
    const w = Math.max(4, b.maxX - b.minX);
    const d = Math.max(4, b.maxZ - b.minZ);
    const g = new THREE.PlaneGeometry(w, d);
    g.rotateX(-Math.PI / 2); // XZ 지면 평행
    return { geometry: g, cx: (b.minX + b.maxX) / 2, cz: (b.minZ + b.maxZ) / 2 };
  }, [parcel]);

  if (!geometry) return null;
  return (
    <mesh geometry={geometry} position={[cx, baseY + maxHeightM, cz]}>
      <meshStandardMaterial
        color="#ef4444"
        transparent
        opacity={0.15}
        roughness={1}
        metalness={0}
        depthWrite={false}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
}

/** 정북 일조사선 envelope(주거지역만): 필지 북측 경계 기준 H(d)=max(9, 2·(d−1.5)) 사선면.
 *  parcel.ring_enu의 z(=북) 최대를 북측 경계로 본다(ENU: z=북). 필지 폭 전체에 사선 단면 압출. */
function NorthLightEnvelope({ parcel, baseY }: { parcel: DigitalTwinParcel; baseY: number }) {
  const geometry = useMemo(() => {
    // 빈/부족한 필지 링이면 Infinity bbox→NaN 지오메트리 방지(가드)
    if (!parcel.ring_enu || parcel.ring_enu.length < 3) return null as THREE.BufferGeometry | null;
    const b = parcelBboxEnu(parcel);
    const w = Math.max(4, b.maxX - b.minX);
    const depth = Math.max(4, b.maxZ - b.minZ); // 북-남 깊이
    const northZ = b.maxZ; // 북측 경계
    // 사선 단면(XZ 절단면을 z방향 거리 d에 따른 높이로): d=0(북측경계)에서 H=9, 이후 2:1 사선.
    // 남쪽으로 갈수록 d 증가 → 허용높이 증가. envelope 윗면을 사선으로 표현.
    // BufferGeometry로 사변형 스트립(북측 저, 남측 고) 1면 생성.
    const dMax = depth;
    const hNorth = Math.max(9, 2 * (0 - 1.5)); // = 9
    const hSouth = Math.max(9, 2 * (dMax - 1.5));
    const minX = b.minX;
    const maxX = b.minX + w;
    const zNorth = northZ;
    const zSouth = northZ - depth; // 남쪽(z 감소)
    // 4 꼭짓점: 북서·북동(낮음) / 남서·남동(높음)
    const verts = new Float32Array([
      minX, baseY + hNorth, zNorth,
      maxX, baseY + hNorth, zNorth,
      maxX, baseY + hSouth, zSouth,
      minX, baseY + hSouth, zSouth,
    ]);
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(verts, 3));
    g.setIndex([0, 1, 2, 0, 2, 3]);
    g.computeVertexNormals();
    return g;
  }, [parcel, baseY]);

  if (!geometry) return null;
  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial
        color="#f59e0b"
        transparent
        opacity={0.16}
        roughness={1}
        metalness={0}
        depthWrite={false}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
}

/** 시각별 태양 위치(고도·방위) → directionalLight 방향벡터(광원 위치). 방위 0=북, 시계방향(동=90). */
function sunDirectionEnu(sp: SunPosition, span: number): [number, number, number] {
  const alt = (sp.altitude_deg * Math.PI) / 180;
  const az = (sp.azimuth_deg * Math.PI) / 180;
  // ENU: x=동, z=북(주의: 씬 z는 북 방향). 방위 az: 북에서 시계방향.
  // 동 성분 = sin(az), 북 성분 = cos(az). 광원은 태양 방향 쪽 멀리 배치.
  const horiz = Math.cos(alt);
  const x = Math.sin(az) * horiz;
  const zNorth = Math.cos(az) * horiz;
  const y = Math.sin(alt);
  const r = span * 1.5;
  return [x * r, Math.max(y, 0.05) * r, zNorth * r];
}

/**
 * frameloop="demand" 보조기.
 * 자동회전이 켜진 동안에만 매 프레임 invalidate()를 호출해 렌더를 계속 요청한다.
 * (정지 화면에서는 렌더가 멈춰 메인스레드 점유 0 — 1102/프리징 회귀 차단)
 */
function DemandInvalidator({ active }: { active: boolean }) {
  const invalidate = useThree((s) => s.invalidate);
  // 마운트 직후 1회 강제 렌더(demand 모드 초기 흰 화면 방지).
  useEffect(() => {
    invalidate();
  }, [invalidate]);
  useFrame(() => {
    if (active) invalidate();
  });
  return null;
}

/** 씬 본체(레이어 토글 반영). */
function SceneContent({
  payload,
  layers,
  autoRotate,
  colorMode,
  sunPos,
  maxHeightM,
  residential,
}: {
  payload: DigitalTwinScenePayload;
  layers: DigitalTwinLayers;
  autoRotate: boolean;
  colorMode: "elevation" | "slope";
  /** sunPath ON + environment 일조데이터 확보 시 선택 시각 태양위치(없으면 기본광). */
  sunPos: SunPosition | null;
  /** zone 절대 높이한도(m) — null이면 고도제한 면 미생성. */
  maxHeightM: number | null;
  /** 주거지역 여부 — 정북 일조사선 envelope 생성 게이트. */
  residential: boolean;
}) {
  // frameloop="demand"에서 드래그/줌/댐핑 중 렌더를 이어가기 위한 invalidate.
  const invalidate = useThree((s) => s.invalidate);
  const baseY = payload.terrain?.elev0 ?? 0;
  const span = payload.terrain?.bbox_m?.size_m ?? payload.aerial?.cover_m ?? 200;
  const camDist = Math.max(120, span * 0.9);
  const sunLightPos: [number, number, number] =
    layers.sunPath && sunPos ? sunDirectionEnu(sunPos, span) : [span, span * 1.2, span];

  return (
    <>
      <ambientLight intensity={0.85} />
      <directionalLight position={sunLightPos} intensity={1.3} castShadow />
      <directionalLight position={[-span, span * 0.6, -span]} intensity={0.4} />

      {layers.terrain && payload.terrain && (
        <TerrainMesh
          terrain={payload.terrain}
          aerial={payload.aerial ?? null}
          useAerial={layers.aerial}
          colorMode={colorMode}
        />
      )}
      {layers.parcel && payload.parcel && <ParcelOutline parcel={payload.parcel} baseY={baseY} />}
      {layers.neighbors && payload.neighbors && payload.neighbors.length > 0 && (
        <NeighborBuildings neighbors={payload.neighbors} baseY={baseY} />
      )}
      {layers.building && payload.building?.glb_url && <BuildingGlb building={payload.building} />}
      {layers.heightLimit && payload.parcel && maxHeightM != null && (
        <HeightLimitPlane parcel={payload.parcel} baseY={baseY} maxHeightM={maxHeightM} />
      )}
      {layers.northLight && payload.parcel && residential && (
        <NorthLightEnvelope parcel={payload.parcel} baseY={baseY} />
      )}

      {/* 자동회전 중에만 매 프레임 렌더 요청(정지 시 0). */}
      <DemandInvalidator active={autoRotate} />

      <OrbitControls
        makeDefault
        autoRotate={autoRotate}
        autoRotateSpeed={0.25}
        enableDamping
        dampingFactor={0.05}
        maxDistance={camDist * 3}
        target={[0, baseY, 0]}
        onChange={() => invalidate()} // 드래그·줌·댐핑 중 렌더 이어가기
      />
    </>
  );
}

/** 정직성 배지 스트립. */
function HonestyBadges({ payload }: { payload: DigitalTwinScenePayload }) {
  const b = payload.badges;
  if (!b) return null;
  const items: string[] = [
    `표고: ${b.terrain_source} · ${b.terrain_resolution_m}m`,
    `신뢰도 ${Math.round((b.confidence ?? 0) * 100)}%`,
    "주변건물 추정(점선·반투명)",
    "건물 매스: AI 절차생성 · 실측/인허가 도면 아님",
  ];
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((it) => (
        <span
          key={it}
          className="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-[10px] font-bold text-amber-600 dark:text-amber-400"
        >
          {it}
        </span>
      ))}
      {b.note && (
        <span className="rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-1 text-[10px] font-medium text-[var(--text-hint)]">
          {b.note}
        </span>
      )}
    </div>
  );
}

/** 레이어 토글 버튼. */
function LayerToggle({
  label,
  active,
  estimated,
  disabled,
  onClick,
}: {
  label: string;
  active: boolean;
  estimated?: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded-full border px-3 py-1.5 text-[10px] font-black uppercase tracking-widest transition-all disabled:cursor-not-allowed disabled:opacity-40 ${
        active
          ? "border-[var(--accent-strong)] bg-[var(--accent-soft)] text-[var(--accent-strong)]"
          : "border-[var(--line)] bg-[var(--surface-soft)] text-[var(--text-hint)] hover:text-[var(--text-primary)]"
      }`}
    >
      {label}
      {estimated && <span className="ml-1 opacity-60">(추정)</span>}
    </button>
  );
}

const fmtN0 = (v: number | null | undefined) =>
  v == null ? "—" : Math.round(v).toLocaleString();
const fmtN1 = (v: number | null | undefined) =>
  v == null ? "—" : v.toLocaleString(undefined, { maximumFractionDigits: 1 });

/** 실무 요약 카드: 토공량(terrain) · 조망/스카이라인(environment). 무자료는 정직 "자료 없음" 표기. */
function AnalysisSummary({
  env,
  terrain,
  loading,
}: {
  env: EnvironmentResult | null;
  terrain: TerrainResult | null;
  loading: boolean;
}) {
  const earth = terrain?.earthwork;
  const view = env?.view;
  const sky = env?.skyline;
  const cell =
    "rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3";
  const cap = "text-[8px] font-black uppercase tracking-widest text-[var(--text-hint)]";
  const val = "mt-0.5 text-sm font-black text-[var(--text-primary)]";

  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {/* 토공량 */}
      <div className={cell}>
        <p className={cap}>토공량 (절토·성토·순)</p>
        {earth ? (
          <>
            <p className={val}>
              순 {fmtN0(earth.net_m3)} m³ <span className="text-[10px] font-bold text-[var(--text-hint)]">({earth.balance})</span>
            </p>
            <p className="mt-1 text-[10px] text-[var(--text-secondary)]">
              절토 {fmtN0(earth.cut_volume_m3)} · 성토 {fmtN0(earth.fill_volume_m3)} m³
            </p>
          </>
        ) : (
          <p className="mt-1 text-[11px] text-[var(--text-hint)]">{loading ? "로드 중…" : "자료 없음"}</p>
        )}
      </div>
      {/* 조망 */}
      <div className={cell}>
        <p className={cap}>조망 개방도</p>
        {view ? (
          <>
            <p className={val}>{fmtN0(view.openness_score)} / 100</p>
            <p className="mt-1 text-[10px] text-[var(--text-secondary)]">
              트인 방향: {view.best_directions?.length ? view.best_directions.join(" · ") : "없음(주변 가림)"}
            </p>
          </>
        ) : (
          <p className="mt-1 text-[11px] text-[var(--text-hint)]">{loading ? "로드 중…" : "자료 없음"}</p>
        )}
      </div>
      {/* 스카이라인 */}
      <div className={cell}>
        <p className={cap}>스카이라인</p>
        {sky ? (
          <>
            <p className={val}>
              {sky.position}{" "}
              <span className="text-[10px] font-bold text-[var(--text-hint)]">
                대상 {fmtN1(sky.subject_height_m)}m
              </span>
            </p>
            <p className="mt-1 text-[10px] text-[var(--text-secondary)]">
              주변 평균 {fmtN1(sky.neighbor_avg_m)} · 최고 {fmtN1(sky.neighbor_max_m)} m
            </p>
          </>
        ) : (
          <p className="mt-1 text-[11px] text-[var(--text-hint)]">{loading ? "로드 중…" : "자료 없음"}</p>
        )}
      </div>
    </div>
  );
}

export default function DigitalTwinScene({
  address,
  pnu,
  designVersionId,
  designHref,
  zoneType,
}: {
  /** 상위 부지분석 화면에서 확보된 대상지 주소 */
  address?: string;
  pnu?: string | null;
  /** 있으면 해당 설계버전 glb를 건물로 사용 */
  designVersionId?: string | null;
  /** 설계 단계 진입 경로(건물 매스 없을 때 안내 CTA). 예) /ko/projects/{id}/design */
  designHref?: string;
  /** 용도지역명(한글) — 고도제한/정북사선 레이어 게이트(컨텍스트에서 전달). */
  zoneType?: string | null;
}) {
  const [addr, setAddr] = useState(address ?? "");
  const [payload, setPayload] = useState<DigitalTwinScenePayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // autoRotate는 사용자 진입 게이트 뒤(메인스레드 점유 회피).
  const [entered, setEntered] = useState(false);
  const [layers, setLayers] = useState<DigitalTwinLayers>({
    terrain: true,
    aerial: true, // 항공 기본 ON(WARN-1: 백엔드 cover_m 정합 처리 중 — 육안 어긋나면 토글로 끄기)
    parcel: true,
    building: true,
    neighbors: true,
    slopeColor: false,
    heightLimit: false,
    northLight: false,
    sunPath: false,
  });
  // 분석 레이어 데이터(씬 POST와 분리해 lazy fetch — 토글 ON 시점 1회).
  const [envData, setEnvData] = useState<EnvironmentResult | null>(null);
  const [terrainData, setTerrainData] = useState<TerrainResult | null>(null);
  const [analysisBusy, setAnalysisBusy] = useState(false);
  const [analysisFetched, setAnalysisFetched] = useState(false);
  // 일조 시각 슬라이더(09~15시). sunPath ON 시 directionalLight 방향에 사용.
  const [sunHour, setSunHour] = useState(12);
  // 영속 캐시: 주소·PNU·설계버전 불변이면 검증된 씬 재사용(재방문 시 재생성 방지),
  // 입력 변경 시 재생성 제안.
  const dtSignature = analysisSignature(
    (addr || address || "").trim(),
    pnu,
    designVersionId,
  );
  const {
    cached: dtCached,
    isFresh: dtFresh,
    isStale: dtStale,
    at: dtAt,
    save: saveDt,
  } = useAnalysisCache<DigitalTwinScenePayload>("digitalTwin", dtSignature);
  const dtRestoredRef = useRef(false);
  useEffect(() => {
    if (!payload && dtCached && !dtRestoredRef.current) {
      dtRestoredRef.current = true;
      setPayload(dtCached);
      setLayers((prev) => ({
        ...prev,
        building: !!dtCached.building?.glb_url && prev.building,
      }));
    }
  }, [payload, dtCached]);

  // zone은 prop 우선, 없으면 environment 응답 zone_type 폴백.
  const effectiveZone = zoneType ?? envData?.zone_type ?? null;
  const maxHeightM = zoneMaxHeightM(effectiveZone);
  const residential = isResidentialZone(effectiveZone);

  useEffect(() => {
    if (address && address !== addr) setAddr(address);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [address]);

  const run = useCallback(async () => {
    const a = (addr || address || "").trim();
    if (!a && !pnu) {
      setErr("대상지 주소를 입력하세요.");
      return;
    }
    setBusy(true);
    setErr(null);
    setEntered(false);
    // 새 씬 생성 시 분석 레이어 캐시 리셋(다음 토글 ON 시 재fetch).
    setEnvData(null);
    setTerrainData(null);
    setAnalysisFetched(false);
    try {
      const d = await apiClient.post<DigitalTwinScenePayload>("/digital-twin/scene", {
        body: {
          address: a || null,
          pnu: pnu ?? null,
          design_version_id: designVersionId ?? null,
        },
        timeoutMs: 90000,
      });
      if (d?.ok) {
        setPayload(d);
        saveDt(d); // 검증된 씬 영속 → 재방문 시 재사용(입력 불변이면 재생성 안 함)
        // 건물 glb 없으면 토글 비활성 표시
        setLayers((prev) => ({ ...prev, building: !!d.building?.glb_url && prev.building }));
      } else {
        setPayload(null);
        setErr(d?.message || "가상준공 씬 생성 실패 — 좌표·필지 또는 지형 데이터를 확보하지 못했습니다.");
      }
    } catch {
      setPayload(null);
      setErr("씬 요청 실패 — 네트워크 확인 후 다시 시도하세요.");
    } finally {
      setBusy(false);
    }
  }, [addr, address, pnu, designVersionId, saveDt]);

  // 분석 레이어 데이터 lazy fetch — 토글/요약 진입 시 1회. 씬 POST와 분리(성능 가드).
  // /environment/analyze + /terrain/analyze 동일 엔드포인트 재사용, use_llm 미사용(비용·게이트 회피).
  const ensureAnalysis = useCallback(async () => {
    if (analysisFetched || analysisBusy) return;
    const a = (addr || address || "").trim();
    if (!a && !pnu) return;
    setAnalysisBusy(true);
    setAnalysisFetched(true);
    const [env, terr] = await Promise.allSettled([
      apiClient.post<EnvironmentResult>("/environment/analyze", {
        body: { address: a || null, pnu: pnu ?? null, design_params: null, season: "winter" },
      }),
      apiClient.post<TerrainResult>("/terrain/analyze", {
        body: { address: a || null, pnu: pnu ?? null, target_level_m: null, section_bearing_deg: null },
      }),
    ]);
    if (env.status === "fulfilled" && env.value?.ok) setEnvData(env.value);
    if (terr.status === "fulfilled" && terr.value?.ok) setTerrainData(terr.value);
    setAnalysisBusy(false);
  }, [addr, address, pnu, analysisFetched, analysisBusy]);

  // 분석 레이어 토글: ON 전환 시 데이터 lazy fetch 보장.
  const toggleAnalysisLayer = useCallback(
    (key: "slopeColor" | "heightLimit" | "northLight" | "sunPath") => {
      setLayers((p) => ({ ...p, [key]: !p[key] }));
      void ensureAnalysis();
    },
    [ensureAnalysis],
  );

  const inp =
    "h-9 w-full rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]";
  const hasBuildingGlb = !!payload?.building?.glb_url;
  // 선택 시각(sunHour)에 가장 가까운 태양위치(없으면 null → 기본광 유지).
  const sunPos: SunPosition | null = (() => {
    const ps = envData?.solar?.sun_positions;
    if (!ps || ps.length === 0) return null;
    let best = ps[0];
    let bestDiff = Math.abs(ps[0].hour - sunHour);
    for (const p of ps) {
      const diff = Math.abs(p.hour - sunHour);
      if (diff < bestDiff) {
        best = p;
        bestDiff = diff;
      }
    }
    return best;
  })();
  // 카메라 거리 기준 폭: size_m 우선 → cover_m → 200(SceneContent와 동일 규칙).
  const camSpan = payload?.terrain?.bbox_m?.size_m ?? payload?.aerial?.cover_m ?? 200;

  return (
    <div className="flex flex-col gap-6 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)]/60 p-6 shadow-[var(--shadow-xl)] backdrop-blur-xl">
      {/* 헤더 */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-2">
          <div className="flex items-center gap-3">
            <span className="h-2 w-10 rounded-full bg-[var(--accent-strong)]" />
            <h4 className="text-2xl font-[1000] tracking-tighter text-[var(--text-primary)]">가상준공 3D 디지털트윈</h4>
          </div>
          <p className="max-w-2xl text-sm font-medium leading-relaxed text-[var(--text-secondary)]">
            지도(지형·항공) 위에 필지 경계·AI 절차생성 건물 매스·주변건물 추정을 좌표정합으로 합성합니다.
          </p>
        </div>
        <div className="flex items-end gap-2">
          <div className="w-64">
            <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">
              대상지 주소
            </label>
            <input
              className={inp}
              value={addr}
              onChange={(e) => setAddr(e.target.value)}
              placeholder="예) 서울특별시 강남구 …"
              onKeyDown={(e) => {
                if (e.key === "Enter") run();
              }}
            />
          </div>
          <button
            type="button"
            onClick={run}
            disabled={busy}
            className="h-9 shrink-0 rounded-lg bg-[var(--accent-strong)] px-5 text-[11px] font-black uppercase tracking-widest text-white transition-all hover:brightness-110 disabled:opacity-50"
          >
            {busy ? "생성 중…" : "가상준공 생성"}
          </button>
        </div>
      </div>

      {err && (
        <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-4 text-sm font-medium text-red-500">
          {err}
        </div>
      )}

      <AnalysisCacheStatus
        isFresh={dtFresh && !!payload}
        isStale={dtStale && !!payload}
        at={dtAt}
        relativeLabel={relativeKoreanTime(dtAt)}
        onRerun={() => void run()}
        busy={busy}
        rerunLabel="↻ 재생성"
      />

      {payload && (
        <>
          {/* SP1: 준공 전/후 비교 — building 레이어 가시성을 세그먼트로 제어(신규 상태·fetch 0, additive).
              '전'=필지·항공만, '후'=+AI 절차생성 매스(인허가 아님·정직 표기). hasBuildingGlb일 때만. */}
          {hasBuildingGlb && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="mr-1 text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">준공 비교</span>
              <div
                data-testid="dt-beforeafter"
                className="inline-flex rounded-full border border-[var(--line)] bg-[var(--surface-soft)] p-0.5"
              >
                <button
                  type="button"
                  data-testid="dt-before"
                  onClick={() => setLayers((p) => ({ ...p, building: false }))}
                  className={`rounded-full px-3 py-1.5 text-[10px] font-black uppercase tracking-widest transition-all ${
                    !layers.building
                      ? "bg-[var(--accent-soft)] text-[var(--accent-strong)]"
                      : "text-[var(--text-hint)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  준공 전
                </button>
                <button
                  type="button"
                  data-testid="dt-after"
                  onClick={() => setLayers((p) => ({ ...p, building: true }))}
                  className={`rounded-full px-3 py-1.5 text-[10px] font-black uppercase tracking-widest transition-all ${
                    layers.building
                      ? "bg-[var(--accent-soft)] text-[var(--accent-strong)]"
                      : "text-[var(--text-hint)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  준공 후
                </button>
              </div>
              <span className="text-[10px] font-bold text-[var(--text-hint)]">
                {layers.building ? "필지·항공 + AI 매스(절차생성·인허가 아님)" : "필지·항공(현 상태)"}
              </span>
            </div>
          )}

          {/* 레이어 토글 */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="mr-1 text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">레이어</span>
            <LayerToggle label="지형" active={layers.terrain} onClick={() => setLayers((p) => ({ ...p, terrain: !p.terrain }))} />
            <LayerToggle label="항공" active={layers.aerial} onClick={() => setLayers((p) => ({ ...p, aerial: !p.aerial }))} />
            <LayerToggle label="필지" active={layers.parcel} onClick={() => setLayers((p) => ({ ...p, parcel: !p.parcel }))} />
            {hasBuildingGlb && (
              <LayerToggle label="건물" active={layers.building} onClick={() => setLayers((p) => ({ ...p, building: !p.building }))} />
            )}
            <LayerToggle
              label="주변"
              active={layers.neighbors}
              estimated
              onClick={() => setLayers((p) => ({ ...p, neighbors: !p.neighbors }))}
            />
            {/* ── 분석 레이어(데이터 가용 시에만 의미. 토글 ON 시 lazy fetch) ── */}
            <span className="mx-1 h-4 w-px bg-[var(--line)]" />
            <LayerToggle
              label={layers.slopeColor ? "지형색:경사" : "지형색:표고"}
              active={layers.slopeColor}
              onClick={() => setLayers((p) => ({ ...p, slopeColor: !p.slopeColor }))}
            />
            <LayerToggle label="일조" active={layers.sunPath} onClick={() => toggleAnalysisLayer("sunPath")} />
            {/* 고도제한: 절대 높이한도 있는 zone만 활성(없으면 비활성 + FAR 기반 배지) */}
            <LayerToggle
              label="고도제한"
              active={layers.heightLimit}
              disabled={maxHeightM == null}
              onClick={() => toggleAnalysisLayer("heightLimit")}
            />
            {/* 정북 일조사선: 주거지역만 노출 */}
            {residential && (
              <LayerToggle label="정북사선" active={layers.northLight} onClick={() => toggleAnalysisLayer("northLight")} />
            )}
            {analysisBusy && (
              <span className="text-[10px] font-bold text-[var(--text-hint)]">분석 로드 중…</span>
            )}
          </div>

          {/* 일조 시각 슬라이더(sunPath ON + 태양궤적 확보 시) */}
          {layers.sunPath && (
            <div className="flex items-center gap-3">
              <span className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">일조 시각</span>
              <input
                type="range"
                min={9}
                max={15}
                step={1}
                value={sunHour}
                onChange={(e) => setSunHour(Number(e.target.value))}
                className="h-1.5 w-48 cursor-pointer accent-[var(--accent-strong)]"
              />
              <span className="text-xs font-bold text-[var(--text-primary)]">{sunHour}시</span>
              {!sunPos && (
                <span className="text-[10px] text-[var(--text-hint)]">태양궤적 자료 없음 — 기본광 유지</span>
              )}
            </div>
          )}

          {/* 고도제한 자료 없을 때 정직 배지(비주거 대부분 FAR 기반·절대높이 없음) */}
          {maxHeightM == null && effectiveZone && (
            <p className="text-[10px] text-[var(--text-hint)]">
              고도제한: <b className="text-[var(--text-secondary)]">{effectiveZone}</b> — FAR 기반·절대높이 없음(고도제한 면 미생성)
            </p>
          )}

          {/* 정직성 배지 */}
          <HonestyBadges payload={payload} />

          {/* 실무 요약 카드(토공량·조망·스카이라인) — environment/terrain lazy fetch. 무자료 정직표기 */}
          {(layers.sunPath || layers.heightLimit || layers.northLight || envData || terrainData) && (
            <AnalysisSummary env={envData} terrain={terrainData} loading={analysisBusy} />
          )}

          {/* 건물 매스 없음 안내 — 설계 미연동 시 지형·필지만 표시(가짜 건물 금지) */}
          {!hasBuildingGlb && (
            <div className="flex flex-col gap-3 rounded-2xl border border-amber-500/30 bg-amber-500/5 p-5 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-500/15 text-amber-500">
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M3 21h18" /><path d="M5 21V7l8-4v18" /><path d="M19 21V11l-6-4" /></svg>
                </div>
                <div className="space-y-1">
                  <p className="text-sm font-black text-[var(--text-primary)]">
                    설계가 아직 없어 지형·필지만 표시됩니다.
                  </p>
                  <p className="text-xs font-medium leading-relaxed text-[var(--text-secondary)]">
                    설계를 생성/업로드하면 건물이 합성된 가상준공(준공 전 미리보기)을 볼 수 있습니다.
                    <br className="hidden sm:block" />
                    AI 자동설계로 매스를 즉시 만들거나, 보유한 CAD 도면을 업로드해 연동할 수 있습니다.
                  </p>
                </div>
              </div>
              {designHref && (
                <a
                  href={designHref}
                  className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-[var(--accent-strong)] px-5 py-2.5 text-[11px] font-black uppercase tracking-widest text-white whitespace-nowrap transition-all hover:brightness-110 active:scale-95"
                >
                  건축 설계로 이동
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14" /><path d="m12 5 7 7-7 7" /></svg>
                </a>
              )}
            </div>
          )}

          {/* 3D 캔버스 — 카메라 거리는 size_m 우선(없으면 cover_m→200) */}
          <div className="relative h-[560px] w-full overflow-hidden rounded-3xl border border-[var(--line-strong)] bg-[#0d1520]">
            <Canvas
              shadows
              frameloop="demand"
              camera={{
                position: [
                  camSpan * 0.7,
                  camSpan * 0.6 + (payload.terrain?.elev0 ?? 0),
                  camSpan * 0.7,
                ],
                fov: 45,
                near: 0.5,
                far: 100000,
              }}
            >
              <SceneContent
                payload={payload}
                layers={layers}
                autoRotate={entered}
                colorMode={layers.slopeColor ? "slope" : "elevation"}
                sunPos={sunPos}
                maxHeightM={maxHeightM}
                residential={residential}
              />
            </Canvas>

            {/* 진입 게이트(autoRotate·인터랙션 시작 전 안내) */}
            {!entered && (
              <button
                type="button"
                onClick={() => setEntered(true)}
                className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-black/40 backdrop-blur-sm"
              >
                <span className="rounded-full border border-white/20 bg-white/10 px-6 py-2.5 text-[11px] font-black uppercase tracking-widest text-white">
                  3D 트윈 진입
                </span>
                <span className="text-[10px] font-bold text-white/60">드래그로 회전 · 스크롤로 줌</span>
              </button>
            )}
          </div>

          {/* 출처 */}
          {payload.sources && payload.sources.length > 0 && (
            <p className="text-[10px] text-[var(--text-hint)]">출처: {payload.sources.join(" · ")}</p>
          )}

          {/* 가상준공 AI 해설 */}
          <DigitalTwinAiCard
            address={addr || address}
            pnu={pnu}
            scenePayload={payload}
          />
        </>
      )}
    </div>
  );
}
