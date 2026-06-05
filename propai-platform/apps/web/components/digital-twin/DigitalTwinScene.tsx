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
import { Canvas, useLoader } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { TextureLoader } from "three";
import * as THREE from "three";
import { apiClient } from "@/lib/api-client";
import type {
  DigitalTwinScenePayload,
  DigitalTwinTerrain,
  DigitalTwinParcel,
  DigitalTwinNeighbor,
  DigitalTwinAerial,
  DigitalTwinBuilding,
  DigitalTwinLayers,
} from "./types";

const ACCENT = "#3b82f6";

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

/** 지형 메시: verts/indices → BufferGeometry. 항공 드레이프(텍스처) 또는 표고 vertexColors. */
function TerrainMesh({
  terrain,
  aerial,
  useAerial,
}: {
  terrain: DigitalTwinTerrain;
  aerial: DigitalTwinAerial | null;
  useAerial: boolean;
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
    terrain.verts.forEach((v, i) => {
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

    // 표고 그라데이션 vertexColors
    const ySpan = maxY - minY || 1;
    const colors = new Float32Array(terrain.verts.length * 3);
    terrain.verts.forEach((v, i) => {
      const c = elevationColor((v[1] - minY) / ySpan);
      colors[i * 3] = c.r;
      colors[i * 3 + 1] = c.g;
      colors[i * 3 + 2] = c.b;
    });
    g.setAttribute("color", new THREE.BufferAttribute(colors, 3));

    // 항공 드레이프용 UV(평면 투영 XZ → 0..1)
    const xSpan = maxX - minX || 1;
    const zSpan = maxZ - minZ || 1;
    const uvs = new Float32Array(terrain.verts.length * 2);
    terrain.verts.forEach((v, i) => {
      uvs[i * 2] = (v[0] - minX) / xSpan;
      uvs[i * 2 + 1] = 1 - (v[2] - minZ) / zSpan;
    });
    g.setAttribute("uv", new THREE.BufferAttribute(uvs, 2));

    g.computeVertexNormals();
    return g;
  }, [terrain]);

  return (
    <mesh geometry={geometry} receiveShadow>
      {useAerial && aerial?.image_proxy_url ? (
        <Suspense fallback={<meshStandardMaterial color="#1e293b" roughness={1} metalness={0} />}>
          <AerialMaterial url={aerial.image_proxy_url} />
        </Suspense>
      ) : (
        <meshStandardMaterial vertexColors flatShading roughness={0.95} metalness={0} />
      )}
    </mesh>
  );
}

/** 항공 텍스처 머티리얼(프록시 URL). useLoader는 Suspense로 처리. */
function AerialMaterial({ url }: { url: string }) {
  const texture = useLoader(TextureLoader, url);
  return <meshStandardMaterial map={texture} roughness={0.95} metalness={0} />;
}

/** 필지 경계: ring_enu → LineLoop(실선·강조색). y는 지형표고 근처. */
function ParcelOutline({ parcel, baseY }: { parcel: DigitalTwinParcel; baseY: number }) {
  const geometry = useMemo(() => {
    const pts = parcel.ring_enu.map((p) => new THREE.Vector3(p[0], baseY + 0.6, p[1]));
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
      nb.footprint_enu.forEach((p, i) => {
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

/** 씬 본체(레이어 토글 반영). */
function SceneContent({
  payload,
  layers,
  autoRotate,
}: {
  payload: DigitalTwinScenePayload;
  layers: DigitalTwinLayers;
  autoRotate: boolean;
}) {
  const baseY = payload.terrain?.elev0 ?? 0;
  const span = payload.terrain?.bbox_m?.size_m ?? payload.aerial?.cover_m ?? 200;
  const camDist = Math.max(120, span * 0.9);

  return (
    <>
      <ambientLight intensity={0.85} />
      <directionalLight position={[span, span * 1.2, span]} intensity={1.3} castShadow />
      <directionalLight position={[-span, span * 0.6, -span]} intensity={0.4} />

      {layers.terrain && payload.terrain && (
        <TerrainMesh terrain={payload.terrain} aerial={payload.aerial ?? null} useAerial={layers.aerial} />
      )}
      {layers.parcel && payload.parcel && <ParcelOutline parcel={payload.parcel} baseY={baseY} />}
      {layers.neighbors && payload.neighbors && payload.neighbors.length > 0 && (
        <NeighborBuildings neighbors={payload.neighbors} baseY={baseY} />
      )}
      {layers.building && payload.building?.glb_url && <BuildingGlb building={payload.building} />}

      <OrbitControls
        makeDefault
        autoRotate={autoRotate}
        autoRotateSpeed={0.25}
        enableDamping
        dampingFactor={0.05}
        maxDistance={camDist * 3}
        target={[0, baseY, 0]}
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
  onClick,
}: {
  label: string;
  active: boolean;
  estimated?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-3 py-1.5 text-[10px] font-black uppercase tracking-widest transition-all ${
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

export default function DigitalTwinScene({
  address,
  pnu,
  designVersionId,
}: {
  /** 상위 부지분석 화면에서 확보된 대상지 주소 */
  address?: string;
  pnu?: string | null;
  /** 있으면 해당 설계버전 glb를 건물로 사용 */
  designVersionId?: string | null;
}) {
  const [addr, setAddr] = useState(address ?? "");
  const [payload, setPayload] = useState<DigitalTwinScenePayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // autoRotate는 사용자 진입 게이트 뒤(메인스레드 점유 회피).
  const [entered, setEntered] = useState(false);
  const [layers, setLayers] = useState<DigitalTwinLayers>({
    terrain: true,
    aerial: false,
    parcel: true,
    building: true,
    neighbors: true,
  });

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
  }, [addr, address, pnu, designVersionId]);

  const inp =
    "h-9 w-full rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]";
  const hasBuildingGlb = !!payload?.building?.glb_url;

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

      {payload && (
        <>
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
          </div>

          {/* 정직성 배지 */}
          <HonestyBadges payload={payload} />

          {/* 3D 캔버스 */}
          <div className="relative h-[560px] w-full overflow-hidden rounded-3xl border border-[var(--line-strong)] bg-[#0d1520]">
            <Canvas
              shadows
              camera={{
                position: [
                  (payload.terrain?.bbox_m?.size_m ?? 200) * 0.7,
                  (payload.terrain?.bbox_m?.size_m ?? 200) * 0.6 + (payload.terrain?.elev0 ?? 0),
                  (payload.terrain?.bbox_m?.size_m ?? 200) * 0.7,
                ],
                fov: 45,
                near: 0.5,
                far: 100000,
              }}
            >
              <SceneContent payload={payload} layers={layers} autoRotate={entered} />
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
        </>
      )}
    </div>
  );
}
