'use client';
import { useEffect, useMemo } from "react";
import * as THREE from "three";

// 클라이언트 절차생성 3D 매스 — 건축개요(폭·깊이·층수·층고)만으로 즉시 생성.
// 서버 IFC 파이프라인과 무관하게 "항상 무언가를 렌더"하는 것이 핵심(에디터가 빈 화면이 되지 않도록).
// 서버 정밀 glb가 도착하면 그쪽을 우선 사용(아래 BuildingModel).
export function ProceduralBuilding({
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
    // §4-D: gizmo 선택 대상 표시 — 건축 요소(메시)만 선택 가능(격자·헬퍼 제외).
    g.traverse((o) => { if ((o as THREE.Mesh).isMesh) o.userData.selectable = true; });
    return g;
  }, [width, depth, floors, floorHeight, daylightNorth]);

  // 매스 group이 바뀌거나(치수 변경) 언마운트될 때 직전 group의 geometry/material을 GPU에서 해제.
  // <primitive>로 주입한 사전생성 객체는 R3F가 자동 dispose하지 않으므로 직접 처분(누수 방지).
  // dispose는 멱등이라 공유 geometry/material에 중복 호출돼도 안전.
  useEffect(() => {
    return () => {
      group.traverse((o) => {
        const m = o as THREE.Mesh;
        if (!m.isMesh) return;
        m.geometry?.dispose();
        const mat = m.material;
        if (Array.isArray(mat)) mat.forEach((x) => x.dispose());
        else mat?.dispose();
      });
    };
  }, [group]);

  return <primitive object={group} />;
}
