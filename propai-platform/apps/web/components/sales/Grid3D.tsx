"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";
import type { Unit } from "@/store/useSalesStore";

const C: Record<string, number> = {
  AVAILABLE: 0x34d399, HOLD: 0xfbbf24, APPLIED: 0x38bdf8, CONTRACTED: 0xfb7185, CANCELLED: 0xa1a1aa,
};

export default function Grid3D({ units, onSelect }: { units: Unit[]; onSelect: (u: Unit) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const w = ref.current.clientWidth || 640;
    const h = 480;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0c0e16);
    const cam = new THREE.PerspectiveCamera(55, w / h, 0.1, 1000);
    cam.position.set(20, 24, 32);
    cam.lookAt(0, 8, 0);
    const rdr = new THREE.WebGLRenderer({ antialias: true });
    rdr.setSize(w, h);
    ref.current.innerHTML = "";
    ref.current.appendChild(rdr.domElement);
    scene.add(new THREE.AmbientLight(0xffffff, 0.85));
    const dl = new THREE.DirectionalLight(0xffffff, 0.6);
    dl.position.set(10, 20, 10);
    scene.add(dl);
    const dongs = [...new Set(units.map((u) => u.dong))];
    const meshes: { mesh: THREE.Mesh; unit: Unit }[] = [];
    units.forEach((u) => {
      const g = new THREE.BoxGeometry(1.4, 1.0, 1.4);
      const m = new THREE.MeshLambertMaterial({ color: C[u.status] ?? 0xcccccc });
      const cube = new THREE.Mesh(g, m);
      const dx = dongs.indexOf(u.dong) * 6;
      const lx = parseInt(u.line || "1", 10);
      cube.position.set(dx + lx * 1.6, (u.floor || 1) * 1.1, 0);
      scene.add(cube);
      meshes.push({ mesh: cube, unit: u });
    });
    const ray = new THREE.Raycaster();
    const mouse = new THREE.Vector2();
    const onClick = (e: MouseEvent) => {
      const r = rdr.domElement.getBoundingClientRect();
      mouse.x = ((e.clientX - r.left) / w) * 2 - 1;
      mouse.y = -((e.clientY - r.top) / h) * 2 + 1;
      ray.setFromCamera(mouse, cam);
      const hit = ray.intersectObjects(meshes.map((x) => x.mesh))[0];
      if (hit) {
        const f = meshes.find((x) => x.mesh === hit.object);
        if (f) onSelect(f.unit);
      }
    };
    rdr.domElement.addEventListener("click", onClick);
    let raf = 0;
    const loop = () => {
      raf = requestAnimationFrame(loop);
      rdr.render(scene, cam);
    };
    loop();
    return () => {
      cancelAnimationFrame(raf);
      rdr.domElement.removeEventListener("click", onClick);
      rdr.dispose();
    };
  }, [units, onSelect]);
  return <div ref={ref} className="w-full rounded-xl border border-[var(--line)]" />;
}
