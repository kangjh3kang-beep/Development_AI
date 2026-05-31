"use client";

import React, { useState, useMemo, useEffect } from "react";
import { motion } from "framer-motion";
import { useParams } from "next/navigation";
import { useAIAnalyze, useAIReady } from "@/lib/ai-analyze-client";
import { getZoningSpec, calcMaxGrossArea, calcParkingRequired } from "@/lib/kr-building-regulations";
import { useProjectContextStore } from "@/store/useProjectContextStore";

type DesignResult = {
  buildingCoverage?: { value: number; max: number; unit: string };
  floorAreaRatio?: { value: number; max: number; unit: string };
  maxFloors?: number;
  maxHeight?: { value: number; unit: string };
  totalGrossArea?: { value: number; unit: string };
  parkingRequired?: number;
  setbacks?: { front: number; side: number; rear: number; unit: string };
  massingOptions?: Array<{ name: string; description: string; efficiency: number }>;
  summary?: string;
};

export default function DesignPage() {
  const params = useParams();
  const projectId = (params?.id as string) || "";
  const { isReady } = useAIReady();
  const { mutate, data: aiResult, isPending, error } = useAIAnalyze<DesignResult>();
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);

  const [form, setForm] = useState({
    landArea: "500",
    zoning: "제2종일반주거지역",
    buildingUse: "공동주택",
  });

  // 부지분석 완료 데이터가 있으면 자동 반영
  useEffect(() => {
    if (!siteAnalysis) return;
    setForm((prev) => ({
      ...prev,
      landArea: siteAnalysis.landAreaSqm ? String(siteAnalysis.landAreaSqm) : prev.landArea,
      zoning: siteAnalysis.zoneCode || prev.zoning,
    }));
  }, [siteAnalysis]);

  // ── 로컬 계산 (즉시) ──
  const localCalc = useMemo(() => {
    const area = Number(form.landArea) || 0;
    const spec = getZoningSpec(form.zoning);
    if (!spec || area <= 0) return null;

    const maxGross = calcMaxGrossArea(area, form.zoning);
    const parking = calcParkingRequired(maxGross, form.buildingUse);
    const buildableArea = area * (spec.buildingCoverageMax / 100);
    // 용적률 기준 최소 필요 층수 (건폐율로 나눈 값)
    const minFloorsFromFar = spec.floorAreaRatioMax > 0 ? Math.ceil(maxGross / buildableArea) : 1;
    // 높이 제한이 있으면 그에 맞춤, 없으면 현실적 층수 적용
    const heightPerFloor = 3.3;
    const maxFloorsByHeight = spec.heightLimit ? Math.floor(spec.heightLimit / heightPerFloor) : 25;
    const maxFloors = Math.min(minFloorsFromFar, maxFloorsByHeight);
    const maxHeight = spec.heightLimit || (maxFloors * heightPerFloor);
    const heightNote = spec.heightLimit ? "법적 높이 제한" : "예상 높이 (제한 없음)";

    return {
      buildingCoverage: spec.buildingCoverageMax,
      floorAreaRatio: spec.floorAreaRatioMax,
      maxFloors,
      maxHeight: Math.round(maxHeight * 10) / 10,
      buildableArea: Math.round(buildableArea * 10) / 10,
      maxGrossArea: Math.round(maxGross * 10) / 10,
      parking,
      heightNote,
      setbacks: { front: 6, side: 1.5, rear: 2, unit: "m" },
      massingOptions: [
        { name: "판상형", description: `${maxFloors}층 2개동, 남향 배치`, efficiency: 78 },
        { name: "타워형", description: `${maxFloors + 2}층 1개동, 중앙코어`, efficiency: 72 },
        { name: "ㄱ자형", description: `${maxFloors}층, 소음차폐 배치`, efficiency: 75 },
      ],
    };
  }, [form.landArea, form.zoning, form.buildingUse]);

  const handleAIAnalyze = () => {
    mutate({
      domain: "design",
      context: { landArea: `${form.landArea}㎡`, zoningDistrict: form.zoning, buildingUse: form.buildingUse, projectId },
    });
  };

  // AI > 로컬 통합
  const ai = aiResult?.data;
  const calc = localCalc;

  return (
    <div className="flex flex-col md:flex-row gap-6 h-[calc(100vh-120px)] w-full">
      {/* ── 좌측 패널: Controls & Input ── */}
      <aside className="w-full md:w-[380px] flex flex-col rounded-xl border border-border-light dark:border-border-dark bg-white dark:bg-[#111318] overflow-y-auto flex-shrink-0 shadow-sm">
        <div className="p-6 flex flex-col gap-6">
          {/* Header */}
          <div>
            <h1 className="text-xl font-bold text-slate-900 dark:text-white mb-1">AI Synthesis Engine</h1>
            <p className="text-slate-500 dark:text-gray-400 text-xs">AI 생성을 위한 파라미터 설정</p>
          </div>

          {/* Reference Material */}
          <section>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold text-slate-700 dark:text-gray-200 flex items-center gap-2">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-primary"><rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/></svg>
                참조 이미지
              </h3>
              <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 font-medium">활성</span>
            </div>
            <div className="relative group rounded-lg overflow-hidden border border-border-light dark:border-border-dark bg-slate-100 dark:bg-surface-dark aspect-video mb-3">
              <img alt="Architectural sketch reference" className="w-full h-full object-cover opacity-80 dark:opacity-60 group-hover:opacity-100 dark:group-hover:opacity-40 transition-opacity" src="https://lh3.googleusercontent.com/aida-public/AB6AXuChYWQUVNUet7f8KsdsZalZ0cQodJ8Yc6017y1opu52Ip7fzO_NZ1IViA7Vly6iv4n1unNFlWeehtAbg4VEUMWE0yjrfJVZq6MyixaqNbOtOJw8VlHkT1P9Q_de8Y4LvGON1HY2-Pg521Nh2YBa4lThyZegCZX4wb7pv-bXEMr6urvHkPXfRpummNCTs2dPVQ5joHJaPkTCbEhLIaWUlT8TvnCeh2NgmOOAGH0JzWiYPr1w66b6WuLtBw-P8EyLCwBCBZSKv_gVdak" />
              <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                <button className="bg-black/50 hover:bg-black/80 text-white rounded-full p-2 backdrop-blur-sm">
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/></svg>
                </button>
              </div>
              <div className="absolute bottom-2 left-2 px-2 py-1 bg-black/60 backdrop-blur-md rounded text-[10px] text-white">ref_sketch_v02.jpg</div>
            </div>
            <button className="text-xs text-primary hover:text-primary-dark font-medium flex items-center gap-1 transition-colors">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="M12 5v14"/></svg>
              추가 참조 이미지 업로드
            </button>
          </section>

          <div className="h-px bg-border-light dark:bg-border-dark w-full" />

          {/* Parameters Form */}
          <section className="flex flex-col gap-4">
            <h3 className="text-sm font-bold text-slate-700 dark:text-gray-200 flex items-center gap-2">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-primary"><line x1="4" x2="20" y1="21" y2="21"/><line x1="4" x2="20" y1="14" y2="14"/><line x1="4" x2="20" y1="7" y2="7"/><polyline points="12 18 16 14 12 10"/><polyline points="12 11 8 7 12 3"/></svg>
              제약 조건
            </h3>
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <label className="text-[11px] font-medium text-slate-500 dark:text-gray-400 uppercase tracking-wider">대지면적 (㎡)</label>
                <input 
                  className="bg-white dark:bg-surface-dark border border-border-light dark:border-border-dark rounded text-sm text-slate-900 dark:text-white px-3 py-2 focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all" 
                  type="number" 
                  value={form.landArea} 
                  onChange={e => setForm(f => ({ ...f, landArea: e.target.value }))}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-[11px] font-medium text-slate-500 dark:text-gray-400 uppercase tracking-wider">용도지역</label>
                <div className="relative">
                  <select 
                    className="w-full appearance-none bg-white dark:bg-surface-dark border border-border-light dark:border-border-dark rounded text-sm text-slate-900 dark:text-white px-3 py-2 focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all"
                    value={form.zoning} 
                    onChange={e => setForm(f => ({ ...f, zoning: e.target.value }))}
                  >
                    {["제1종전용주거지역","제2종전용주거지역","제1종일반주거지역","제2종일반주거지역","제3종일반주거지역","준주거지역","일반상업지역","근린상업지역","준공업지역"].map(z => <option key={z} value={z}>{z}</option>)}
                  </select>
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"><path d="m6 9 6 6 6-6"/></svg>
                </div>
              </div>
            </div>
            
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] font-medium text-slate-500 dark:text-gray-400 uppercase tracking-wider">건물 용도</label>
              <div className="relative">
                <select 
                  className="w-full appearance-none bg-white dark:bg-surface-dark border border-border-light dark:border-border-dark rounded text-sm text-slate-900 dark:text-white px-3 py-2 focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all"
                  value={form.buildingUse} 
                  onChange={e => setForm(f => ({ ...f, buildingUse: e.target.value }))}
                >
                  {["공동주택","업무시설","근린생활시설","숙박시설","판매시설","교육연구시설"].map(u => <option key={u} value={u}>{u}</option>)}
                </select>
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"><path d="m6 9 6 6 6-6"/></svg>
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] font-medium text-slate-500 dark:text-gray-400 uppercase tracking-wider">주요 마감재</label>
              <div className="relative">
                <select className="w-full appearance-none bg-white dark:bg-surface-dark border border-border-light dark:border-border-dark rounded text-sm text-slate-900 dark:text-white px-3 py-2 focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all">
                  <option>Glass & Steel Composite</option>
                  <option>Sustainable Timber</option>
                  <option>Brutalist Concrete</option>
                </select>
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"><path d="m6 9 6 6 6-6"/></svg>
              </div>
            </div>
          </section>

          <div className="h-px bg-border-light dark:bg-border-dark w-full" />

          {/* Sliders */}
          <section className="flex flex-col gap-5">
            <div className="flex flex-col gap-2">
              <div className="flex justify-between items-center">
                <label className="text-[11px] font-medium text-slate-500 dark:text-gray-400 uppercase tracking-wider">창의성 지수</label>
                <span className="text-xs font-bold text-primary">High</span>
              </div>
              <input type="range" min="0" max="100" defaultValue="75" className="w-full h-1 bg-slate-200 dark:bg-surface-dark rounded-lg appearance-none cursor-pointer accent-primary" />
            </div>
            <div className="flex flex-col gap-2">
              <div className="flex justify-between items-center">
                <label className="text-[11px] font-medium text-slate-500 dark:text-gray-400 uppercase tracking-wider">법규 준수율</label>
                <span className="text-xs font-bold text-primary">Strict</span>
              </div>
              <input type="range" min="0" max="100" defaultValue="85" className="w-full h-1 bg-slate-200 dark:bg-surface-dark rounded-lg appearance-none cursor-pointer accent-primary" />
            </div>
          </section>
        </div>

        {/* Generate Button */}
        <div className="mt-auto p-6 border-t border-border-light dark:border-border-dark bg-slate-50 dark:bg-[#111318]/95 backdrop-blur">
          <button 
            onClick={handleAIAnalyze} 
            disabled={isPending || !isReady || !form.landArea}
            className="group w-full flex items-center justify-center gap-2 rounded-lg h-12 bg-primary text-white text-sm font-bold hover:bg-primary/90 transition-all shadow-[0_0_20px_rgba(19,91,236,0.3)] hover:shadow-[0_0_25px_rgba(19,91,236,0.5)] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-hover:rotate-180"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.29 1.29L3 12l5.8 1.9a2 2 0 0 1 1.29 1.29L12 21l1.9-5.8a2 2 0 0 1 1.29-1.29L21 12l-5.8-1.9a2 2 0 0 1-1.29-1.29L12 3Z"/></svg>
            <span>{isPending ? "생성 중..." : "설계 생성 시작"}</span>
          </button>
        </div>
      </aside>

      {/* ── 우측 패널: 3D Visualization & Analysis ── */}
      <main className="flex-1 flex flex-col relative rounded-xl overflow-hidden border border-border-light dark:border-border-dark shadow-sm bg-slate-50 dark:bg-[#0a0c10]">
        
        {/* Toolbar Overlay */}
        <div className="absolute top-4 left-4 z-20 flex gap-2">
          <div className="bg-white/90 dark:bg-surface-dark/90 backdrop-blur-md border border-slate-200 dark:border-border-dark rounded-lg p-1 flex items-center gap-1 shadow-sm">
            <button className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-white/10 text-slate-600 dark:text-white transition-colors">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><line x1="3" x2="21" y1="9" y2="9"/><line x1="3" x2="21" y1="15" y2="15"/><line x1="9" x2="9" y1="3" y2="21"/><line x1="15" x2="15" y1="3" y2="21"/></svg>
            </button>
            <button className="p-1.5 rounded bg-primary text-white shadow-sm">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.29 7 12 12 20.71 7"/><line x1="12" x2="12" y1="22" y2="12"/></svg>
            </button>
            <button className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-white/10 text-slate-600 dark:text-white transition-colors">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 21h18"/><path d="M7 21v-4a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v4"/><path d="M12 15V3"/></svg>
            </button>
          </div>
        </div>

        {/* 3D Canvas Area */}
        <div className="flex-1 relative w-full h-full flex items-center justify-center overflow-hidden bg-gradient-to-b from-slate-100 to-white dark:from-[#101622] dark:to-[#0a0c10]">
          {/* Grid Background */}
          <div className="absolute inset-0 opacity-10 dark:opacity-20" style={{ backgroundImage: 'linear-gradient(var(--color-border-dark, #282e39) 1px, transparent 1px), linear-gradient(90deg, var(--color-border-dark, #282e39) 1px, transparent 1px)', backgroundSize: '40px 40px', perspective: '1000px', transform: 'rotateX(60deg) scale(2)' }} />
          
          {/* Generated Model Image */}
          <div className="relative w-[80%] h-[70%] z-10 transition-transform duration-700 hover:scale-[1.02]">
            <img alt="3D rendered modern skyscraper with glass facade" className="w-full h-full object-contain drop-shadow-2xl dark:drop-shadow-[0_20px_50px_rgba(0,0,0,0.5)]" src="https://lh3.googleusercontent.com/aida-public/AB6AXuAYEGb694fJs7BQRGQ_ux-P67qWCFVrOfPTKfC-qMJKNw8kAPmBJUJVN08EYPOP6O3XakLFCMCZR54tZ9AAn8pDCODwEOLUmfLn5AitO16WsOCiQrm5JEXObOSxExJ5AZL9iltopHDBX0PDfCkKQTJktd0h6blSlSXHhQGdi6HQapUVOUxbuLpXkmp4XgAZHvr2aNoBPTksuEbEbjiLDH18FK5B1cJhewcbQbyNMqL4aSQ7Ht8UkPuxMh1mz8q82FImiEm5WSFsAGY" />
            
            {/* Annotations */}
            {calc && (
              <>
                <div className="absolute top-[20%] right-[25%] flex items-center gap-2 animate-bounce">
                  <div className="size-3 bg-primary rounded-full ring-4 ring-primary/20" />
                  <div className="bg-slate-900/80 dark:bg-black/80 text-white text-[10px] px-2 py-1 rounded backdrop-blur border border-white/10 shadow-sm">
                    예상 층수: {ai?.maxFloors ?? calc.maxFloors}층
                  </div>
                </div>
                <div className="absolute bottom-[30%] left-[30%] flex items-center gap-2">
                  <div className="bg-slate-900/80 dark:bg-black/80 text-white text-[10px] px-2 py-1 rounded backdrop-blur border border-white/10 shadow-sm">
                    건축가능면적: {calc.buildableArea.toLocaleString()}㎡
                  </div>
                  <div className="size-3 bg-emerald-500 rounded-full ring-4 ring-emerald-500/20" />
                </div>
              </>
            )}
          </div>
        </div>

        {/* Bottom Analysis Panel */}
        <div className="h-[220px] md:h-[200px] border-t border-border-light dark:border-border-dark bg-white dark:bg-[#111318] z-30 flex flex-col md:flex-row">
          {/* Main KPI */}
          <div className="w-full md:w-[280px] border-b md:border-b-0 md:border-r border-border-light dark:border-border-dark p-6 flex flex-col justify-center items-center gap-3 relative overflow-hidden">
            <h3 className="text-sm font-bold text-slate-500 dark:text-gray-400 uppercase tracking-wider self-start z-10">최대 연면적</h3>
            <div className="relative w-full flex items-center justify-center py-2">
               <span className="text-4xl font-black text-slate-900 dark:text-white">{(ai?.totalGrossArea?.value ?? calc?.maxGrossArea ?? 0).toLocaleString()}</span>
               <span className="text-sm text-slate-500 dark:text-gray-400 ml-1">㎡</span>
            </div>
            <p className="text-center text-xs text-slate-500 dark:text-gray-500 z-10 max-w-[200px]">용적률 {ai?.floorAreaRatio?.value ?? calc?.floorAreaRatio}% 적용 시나리오</p>
          </div>
          
          {/* Compliance Report */}
          <div className="flex-1 p-6 flex flex-col gap-4 overflow-y-auto">
            <div className="flex justify-between items-center mb-1">
              <h3 className="text-sm font-bold text-slate-700 dark:text-gray-400 uppercase tracking-wider flex items-center gap-2">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>
                법규 준수 리포트
              </h3>
              <button className="text-primary text-xs font-medium hover:underline">상세 보기</button>
            </div>
            
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
              {/* Card 1: 건폐율 */}
              <div className="bg-slate-50 dark:bg-surface-dark border border-emerald-900/20 dark:border-emerald-900/30 rounded-lg p-3 flex flex-col gap-2 relative overflow-hidden group">
                <div className="absolute top-0 right-0 w-16 h-16 bg-emerald-500/5 rounded-bl-full -mr-8 -mt-8" />
                <div className="flex justify-between items-start">
                  <span className="text-xs text-slate-600 dark:text-gray-400 font-medium">건폐율 한도</span>
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-emerald-500"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
                </div>
                <div className="mt-auto">
                  <div className="text-lg font-bold text-slate-900 dark:text-white">{ai?.buildingCoverage?.value ?? calc?.buildingCoverage ?? 0} <span className="text-xs font-normal text-slate-500 dark:text-gray-500">/ {ai?.buildingCoverage?.max ?? calc?.buildingCoverage ?? 0} %</span></div>
                  <div className="text-[10px] text-emerald-600 dark:text-emerald-400 mt-1">한도 내 충족</div>
                </div>
              </div>
              
              {/* Card 2: 주차대수 */}
              <div className="bg-slate-50 dark:bg-surface-dark border border-emerald-900/20 dark:border-emerald-900/30 rounded-lg p-3 flex flex-col gap-2 relative overflow-hidden group">
                <div className="absolute top-0 right-0 w-16 h-16 bg-emerald-500/5 rounded-bl-full -mr-8 -mt-8" />
                <div className="flex justify-between items-start">
                  <span className="text-xs text-slate-600 dark:text-gray-400 font-medium">필요 주차대수</span>
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-emerald-500"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
                </div>
                <div className="mt-auto">
                  <div className="text-lg font-bold text-slate-900 dark:text-white">{ai?.parkingRequired ?? calc?.parking ?? 0} <span className="text-xs font-normal text-slate-500 dark:text-gray-500">대</span></div>
                  <div className="text-[10px] text-emerald-600 dark:text-emerald-400 mt-1">법정 기준 확보</div>
                </div>
              </div>
              
              {/* Card 3: 이격거리 */}
              <div className="bg-slate-50 dark:bg-surface-dark border border-amber-900/20 dark:border-amber-900/30 rounded-lg p-3 flex flex-col gap-2 relative overflow-hidden group hidden lg:flex">
                <div className="absolute top-0 right-0 w-16 h-16 bg-amber-500/5 rounded-bl-full -mr-8 -mt-8" />
                <div className="flex justify-between items-start">
                  <span className="text-xs text-slate-600 dark:text-gray-400 font-medium">전면 이격거리</span>
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-amber-500"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
                </div>
                <div className="mt-auto">
                  <div className="text-lg font-bold text-slate-900 dark:text-white">{ai?.setbacks?.front ?? calc?.setbacks?.front ?? 0} <span className="text-xs font-normal text-slate-500 dark:text-gray-500">m 최소</span></div>
                  <div className="text-[10px] text-amber-600 dark:text-amber-500 mt-1">대지 경계 검토 필요</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
