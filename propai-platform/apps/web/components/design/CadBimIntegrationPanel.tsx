"use client";

import { useState } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Environment, Grid, Float } from "@react-three/drei";
import { motion } from "framer-motion";

function BuildingModel() {
  return (
    <group position={[0, -2, 0]}>
      <Float speed={1.5} rotationIntensity={0.2} floatIntensity={0.5}>
        <mesh position={[0, 1, 0]}>
          <boxGeometry args={[5, 2, 5]} />
          <meshStandardMaterial color="var(--line-strong)" wireframe={true} opacity={0.2} transparent />
        </mesh>
        <mesh position={[-1, 5, -1]}>
          <boxGeometry args={[1.5, 6, 1.5]} />
          <meshStandardMaterial color="var(--info)" transparent opacity={0.6} metalness={0.9} roughness={0.1} />
        </mesh>
        <mesh position={[1, 6, 1]}>
          <boxGeometry args={[1.8, 8, 1.8]} />
          <meshStandardMaterial color="var(--accent-strong)" transparent opacity={0.7} metalness={0.8} roughness={0.05} />
        </mesh>
      </Float>
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
            <Canvas camera={{ position: [15, 12, 15], fov: 40 }}>
              <ambientLight intensity={0.4} />
              <pointLight position={[10, 15, 10]} intensity={1.5} color="var(--accent-strong)" />
              <pointLight position={[-10, 10, -10]} intensity={1} color="var(--info)" />
              <Environment preset="night" />
              <OrbitControls makeDefault autoRotate autoRotateSpeed={0.3} enableDamping dampingFactor={0.05} />
              <BuildingModel />
            </Canvas>
          </div>
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-white/20 bg-[#0d1520]">
             <motion.span 
               initial={{ scale: 0.8, opacity: 0 }}
               animate={{ scale: 1, opacity: 1 }}
               className="text-8xl mb-8"
             >
              📐
             </motion.span>
             <p className="font-black text-[10px] uppercase tracking-[0.6em] text-[var(--accent-strong)] animate-pulse">
               {t.loading2D || "GENERATING_VECTOR_SCHEMA..."}
             </p>
             <p className="mt-4 text-[9px] opacity-30 font-mono tracking-tighter">PROJECT_ID: {projectId}</p>
          </div>
        )}

        {/* Overlay Tools */}
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
      </div>
    </div>
  );
}
