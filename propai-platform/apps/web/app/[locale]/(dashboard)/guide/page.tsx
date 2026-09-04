"use client";

import React from "react";
import { motion } from "framer-motion";
import Image from "next/image";

const guideSteps = [
  {
    title: "1단계: 입지 및 사업성 분석",
    desc: "지번 입력 또는 토지조서 업로드를 통해 대상지의 개발 가능성과 종변경 확률을 분석합니다. AI 비서가 실시간으로 분석 노트를 제공합니다.",
    screenshot: "/images/guide/step1.png",
    tags: ["지적도 오버레이", "종변경 분석", "공공데이터 연동"]
  },
  {
    title: "2단계: AI 자동 설계 및 BIM",
    desc: "분석된 대지 데이터를 기반으로 AI가 최적의 평면도를 자동 생성합니다. 2D/3D BIM 뷰어를 통해 실시간으로 도면을 검토하고 수정할 수 있습니다.",
    screenshot: "/images/guide/step2.png",
    tags: ["파라메트릭 설계", "3D BIM", "법규 자동 검토"]
  },
  {
    title: "3단계: 수지분석 및 타당성 검토",
    desc: "시공비, 분양가, 금리 등 변수를 활용하여 몬테카를로 시뮬레이션을 실행합니다. ROI와 NPV를 포함한 종합적인 수익성을 예측합니다.",
    screenshot: "/images/guide/step3.png",
    tags: ["몬테카를로 시뮬레이션", "ROI/NPV 예측", "리스크 진단"]
  }
];

export default function GuidePage() {
  return (
    <div className="flex flex-col gap-16 pb-32">
      {/* ── Header — 관제 매뉴얼 브리핑 ── */}
      <section className="cc-bracketed relative overflow-hidden rounded-[var(--radius-2xl)] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-16 lg:p-24 shadow-[var(--shadow-2xl)]">
        <div className="cc-grid-bg cc-grid-bg--radial opacity-60" />
        <div className="cc-scanline" />
        <i className="cc-bracket cc-bracket--tl" />
        <i className="cc-bracket cc-bracket--tr" />
        <i className="cc-bracket cc-bracket--bl" />
        <i className="cc-bracket cc-bracket--br" />

        <div className="relative z-10 flex flex-col gap-8 text-center max-w-4xl mx-auto">
          <div className="flex justify-center">
            <span className="cc-live"><i />OPERATIONS MANUAL</span>
          </div>

          <h1 className="text-5xl font-black tracking-tighter text-[var(--text-primary)] sm:text-6xl lg:text-8xl leading-none">
            이용 <span className="text-[var(--accent-strong)] italic">가이드.</span>
          </h1>

          <p className="mx-auto max-w-2xl text-xl font-bold leading-relaxed text-[var(--text-secondary)] tracking-tight">
            &quot;사통팔땅의 AI 기반 개발 전주기 자동화 솔루션을 100% 활용하는 방법을 안내해 드립니다.
            초기 부지 분석부터 최종 수익성 검토까지 시스템의 핵심 워크플로우를 확인하세요.&quot;
          </p>
        </div>
      </section>

      {/* ── Guide Steps ── */}
      <div className="flex flex-col gap-40">
        {guideSteps.map((step, i) => (
          <motion.div 
            key={i}
            initial={{ opacity: 0, y: 50 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 0.8, ease: "easeOut" }}
            className="flex flex-col lg:flex-row gap-20 items-center"
          >
            <div className={`cc-interactive flex-1 flex flex-col gap-8 p-8 lg:p-12 rounded-[var(--radius-2xl)] bg-[var(--surface-soft)] border border-[var(--line-strong)] backdrop-blur-2xl shadow-[var(--shadow-xl)] relative overflow-hidden group/card ${i % 2 === 1 ? 'lg:order-2' : ''}`}>
               <div className="cc-grid-bg opacity-40" />
               {/* Cyber Glow Background */}
               <div className="absolute -inset-20 bg-gradient-to-tr from-[var(--data-accent-soft)] via-transparent to-[var(--accent-soft)] opacity-0 group-hover/card:opacity-100 transition-opacity duration-1000 blur-2xl" />
               
               <div className="relative z-10 space-y-4">
                 <div className="flex items-center gap-4">
                    <span className="cc-num flex h-12 w-12 items-center justify-center rounded-2xl bg-[var(--accent-soft)] border border-[var(--line-strong)] text-[var(--accent-strong)] font-black text-xl shadow-[var(--shadow-glow)]">
                      {i + 1}
                    </span>
                    <span className="cc-meta">STAGE 0{i + 1}</span>
                 </div>
                 <h2 className="text-4xl font-black text-[var(--text-primary)] tracking-tighter leading-tight lg:text-5xl">{step.title}</h2>
               </div>

               <p className="relative z-10 text-lg leading-relaxed text-[var(--text-secondary)] font-medium">
                 {step.desc}
               </p>

               <div className="flex flex-wrap gap-3">
                 {(step.tags ?? []).map(tag => (
                   <span key={tag} className="relative z-10 rounded-xl border border-[var(--line-strong)] bg-[var(--surface-muted)] px-4 py-2 text-[10px] font-black uppercase tracking-widest text-[var(--accent-strong)] backdrop-blur-md shadow-sm">
                     #{tag}
                   </span>
                 ))}
               </div>
            </div>

            <div className={`flex-[1.5] relative group ${i % 2 === 1 ? 'lg:order-1' : ''}`}>
               <div className="absolute -inset-1 rounded-[var(--radius-2xl)] bg-gradient-to-tr from-[var(--data-accent-soft)] via-transparent to-[var(--accent-soft)] blur-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-1000" />
               <div className="relative overflow-hidden rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-soft)] shadow-[var(--shadow-2xl)] transition-all duration-700 group-hover:scale-[1.03] group-hover:border-[var(--data-accent-line)]">
                  <div className="flex items-center gap-2 border-b border-[var(--line-subtle)] bg-[var(--surface-muted)] px-6 py-4">
                     <div className="flex gap-1.5">
                       <div className="h-2.5 w-2.5 rounded-full bg-[var(--status-error)]/60" />
                       <div className="h-2.5 w-2.5 rounded-full bg-[var(--status-warning)]/60" />
                       <div className="h-2.5 w-2.5 rounded-full bg-[var(--status-success)]/60" />
                     </div>
                     <div className="cc-num mx-auto rounded-lg bg-[var(--surface-muted)] px-4 py-1 text-[10px] font-medium text-[var(--text-tertiary)] uppercase tracking-widest border border-[var(--line-subtle)]">
                        satong.ai / console / stage_0{i+1}
                     </div>
                  </div>
                  <img
                    src={step.screenshot}
                    alt={step.title}
                    className="w-full h-auto object-cover transition-opacity duration-700"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-[var(--surface-soft)] via-transparent to-transparent opacity-30" />
               </div>

               <motion.div
                 animate={{ y: [0, -10, 0] }}
                 transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
                 className="absolute -right-6 -top-6 h-20 w-20 rounded-3xl bg-[var(--data-accent-soft)] border border-[var(--data-accent-line)] backdrop-blur-2xl p-5 shadow-2xl text-[var(--data-accent)]"
               >
                 <svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2v20"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
               </motion.div>
            </div>
          </motion.div>
        ))}
      </div>

      {/* ── Final Call to Action ── */}
      <section className="cc-bracketed relative mt-24 overflow-hidden rounded-[var(--radius-2xl)] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-16 lg:p-24 text-center group shadow-[var(--shadow-2xl)]">
         <div className="cc-grid-bg cc-grid-bg--radial opacity-50" />
         <div className="cc-scanline" />
         <i className="cc-bracket cc-bracket--tl" />
         <i className="cc-bracket cc-bracket--tr" />
         <i className="cc-bracket cc-bracket--bl" />
         <i className="cc-bracket cc-bracket--br" />
         <div className="absolute inset-0 bg-gradient-to-br from-[var(--data-accent-soft)] via-transparent to-[var(--accent-soft)] opacity-50 group-hover:opacity-80 transition-opacity duration-1000" />

         <div className="relative z-10 flex flex-col items-center gap-10">
            <div className="space-y-4">
              <h3 className="text-4xl font-black text-[var(--text-primary)] tracking-tighter sm:text-5xl lg:text-6xl uppercase italic">
                Ready to <span className="text-[var(--accent-strong)]">Transform?</span>
              </h3>
              <p className="mx-auto max-w-xl text-lg font-bold text-[var(--text-secondary)] leading-relaxed">
                모든 준비가 완료되었습니다. 입지 분석부터 시작하여 AI가 제안하는 가치를 직접 확인해 보세요.
              </p>
            </div>

            <button className="group relative overflow-hidden rounded-[var(--radius-lg)] bg-[var(--accent-strong)] h-20 px-16 text-xl font-black text-white uppercase tracking-widest transition-all hover:scale-[1.05] active:scale-95 shadow-[var(--shadow-glow)]">
               <span className="relative z-10">새 프로젝트 생성하기</span>
               <div className="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-500" />
            </button>

            <p className="cc-label text-[var(--text-tertiary)]">Satong Intelligence Engine v58.5 Active</p>
         </div>
      </section>
    </div>
  );
}
