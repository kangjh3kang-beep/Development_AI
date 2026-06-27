'use client';
import { useEffect, useMemo } from "react";
import * as THREE from "three";

// 클라이언트 절차생성 3D 매스 — 건축개요(폭·깊이·층수·층고)만으로 즉시 생성.
// 서버 IFC 파이프라인과 무관하게 "항상 무언가를 렌더"하는 것이 핵심(에디터가 빈 화면이 되지 않도록).
// 서버 정밀 glb가 도착하면 그쪽을 우선 사용(아래 BuildingModel).
//
// ★podium/tower(옵셔널): 주상복합 실무 매스(저층 podium 큰 판 + 고층 tower 작은 판)를 받으면
//   단일 박스 대신 2-volume(저층 넓고 낮게 + 고층 좁고 높게)으로 렌더한다. 미전달이면 기존 단일
//   박스(width/depth/floors) 그대로(무회귀).
type PtVol = { width: number; depth: number; floors: number };

export function ProceduralBuilding({
  width, depth, floors, floorHeight, daylightNorth, podium, tower,
}: {
  width: number; depth: number; floors: number; floorHeight: number;
  daylightNorth?: boolean; podium?: PtVol | null; tower?: PtVol | null;
}) {
  const group = useMemo(() => {
    const w = Math.max(4, width || 20);
    const d = Math.max(4, depth || 15);
    const nf = Math.max(1, Math.round(floors || 5));
    const fh = Math.max(2.2, floorHeight || 3);
    const wallT = 0.3;

    const matSlab = new THREE.MeshStandardMaterial({ color: "#94a3b8", roughness: 0.9, metalness: 0.05 });
    const matGlass = new THREE.MeshStandardMaterial({ color: "#60a5fa", roughness: 0.12, metalness: 0.5, transparent: true, opacity: 0.5 });
    const matMull = new THREE.MeshStandardMaterial({ color: "#e2e8f0", roughness: 0.6 });
    const matCore = new THREE.MeshStandardMaterial({ color: "#475569", roughness: 0.85 });

    // 한 볼륨(podium 또는 tower)의 층 스택을 yBase부터 nf개 쌓는다(정북단계후퇴 없음·직육면체).
    const addStack = (g: THREE.Group, vw: number, vd: number, count: number, yBase: number) => {
      for (let f = 0; f < count; f++) {
        const y = yBase + f * fh;
        const slab = new THREE.Mesh(new THREE.BoxGeometry(vw, 0.25, vd), matSlab);
        slab.position.set(0, y, 0); slab.castShadow = true; slab.receiveShadow = true; g.add(slab);
        const fb = new THREE.BoxGeometry(vw * 0.98, fh * 0.86, wallT);
        const front = new THREE.Mesh(fb, matGlass); front.position.set(0, y + fh / 2, vd / 2); g.add(front);
        const back = new THREE.Mesh(fb, matGlass); back.position.set(0, y + fh / 2, -vd / 2); g.add(back);
        const lr = new THREE.BoxGeometry(wallT, fh * 0.86, vd * 0.98);
        const left = new THREE.Mesh(lr, matGlass); left.position.set(-vw / 2, y + fh / 2, 0); g.add(left);
        const right = new THREE.Mesh(lr, matGlass); right.position.set(vw / 2, y + fh / 2, 0); g.add(right);
        const band = new THREE.Mesh(new THREE.BoxGeometry(vw + 0.1, 0.18, vd + 0.1), matMull);
        band.position.set(0, y + fh * 0.9, 0); g.add(band);
      }
    };

    // ── Podium-Tower 2-volume(주상복합 실무 매스) ──
    const pf = podium && podium.floors > 0 ? Math.round(podium.floors) : 0;
    const tf = tower && tower.floors > 0 ? Math.round(tower.floors) : 0;
    if (pf > 0 && tf > 0) {
      const g = new THREE.Group();
      const pw = Math.max(4, podium!.width || w);
      const pd = Math.max(4, podium!.depth || d);
      const tw = Math.max(4, tower!.width || w * 0.5);
      const td = Math.max(4, tower!.depth || d * 0.5);
      addStack(g, pw, pd, pf, 0);                 // 저층 podium(넓고 낮게)
      addStack(g, tw, td, tf, pf * fh);           // 고층 tower(좁고 높게) — podium 위
      const totalH = (pf + tf) * fh;
      // 코어(EV·계단실) — tower footprint 기준, podium~tower 전체 높이 관통.
      const coreW = Math.min(tw * 0.32, 7);
      const coreD = Math.min(td * 0.32, 7);
      const core = new THREE.Mesh(new THREE.BoxGeometry(coreW, totalH, coreD), matCore);
      core.position.set(0, totalH / 2, 0); core.castShadow = true; g.add(core);
      // 옥상 파라펫(tower 상부).
      const roof = new THREE.Mesh(new THREE.BoxGeometry(tw, 0.7, td), matSlab);
      roof.position.set(0, totalH, 0); g.add(roof);
      g.traverse((o) => { if ((o as THREE.Mesh).isMesh) o.userData.selectable = true; });
      return g;
    }
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
  }, [
    width, depth, floors, floorHeight, daylightNorth,
    podium?.width, podium?.depth, podium?.floors, tower?.width, tower?.depth, tower?.floors,
  ]);

  // 매스 group이 바뀌거나(치수 변경) 언마운트될 때 직전 group의 geometry/material을 GPU에서 해제.
  // <primitive>로 주입한 사전생성 객체는 R3F가 자동 dispose하지 않으므로 직접 처분(누수 방지).
  // dispose는 멱등이라 공유 geometry/material에 중복 호출돼도 안전.
  //
  // ★박스 떴다 사라짐 근본수정: group을 "동기 dispose"하면, 치수/스펙 변경으로 useMemo가
  //  새 group을 만드는 순간 직전 group의 geometry가 즉시 해제돼 — R3F가 새 <primitive>를
  //  커밋·렌더하기 전 1프레임 동안 빈(해제된) 지오메트리가 그려져 "박스가 사라진 것처럼" 보였다.
  //  해제를 requestAnimationFrame으로 한 틱 미뤄(새 group 커밋·렌더 이후) 시각적 깜빡임을 없앤다.
  //  언마운트(영구 제거)는 even safe — 다음 프레임에 해제해도 누수가 아니다(멱등·일회성).
  useEffect(() => {
    const disposed = group;
    return () => {
      const raf = requestAnimationFrame(() => {
        disposed.traverse((o) => {
          const m = o as THREE.Mesh;
          if (!m.isMesh) return;
          m.geometry?.dispose();
          const mat = m.material;
          if (Array.isArray(mat)) mat.forEach((x) => x.dispose());
          else mat?.dispose();
        });
      });
      // rAF 핸들은 클로저 외부로 노출하지 않고, 다음 프레임 1회 실행 후 종료된다.
      // (effect 재실행/언마운트가 같은 프레임에 연쇄해도 각 group은 독립 캡처라 안전.)
      void raf;
    };
  }, [group]);

  return <primitive object={group} />;
}
