"use client";

import { motion } from "framer-motion";
import { Card, CardContent } from "@propai/ui";

const MOCK_PERMITS = [
  {
    id: "PMT-2040-A01",
    projectName: "강남 스마트 플라자 신축공사",
    type: "건축 허가",
    status: "processing",
    progress: 75,
    dueDate: "2040. 05. 30",
    agency: "강남구청 건축과",
    aiConfidence: 98,
  },
  {
    id: "PMT-2040-B12",
    projectName: "판교 데이터센터 증축",
    type: "환경 영향 평가",
    status: "approved",
    progress: 100,
    dueDate: "2040. 05. 25",
    agency: "환경청",
    aiConfidence: 99,
  },
  {
    id: "PMT-2040-C44",
    projectName: "성수 IT밸리 지식산업센터",
    type: "교통 영향 평가",
    status: "reviewing",
    progress: 40,
    dueDate: "2040. 06. 15",
    agency: "서울시 교통정책과",
    aiConfidence: 92,
  },
];

export default function PermitsPage() {
  return (
    <div className="flex flex-col gap-10 pb-20 max-w-7xl mx-auto font-sans">
      <div className="space-y-4 relative z-10">
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          className="flex items-center gap-3"
        >
          <span className="flex h-2.5 w-2.5 rounded-full bg-[var(--accent-strong)] shadow-[0_0_10px_rgba(45,212,191,0.8)] animate-pulse" />
          <span className="text-[10px] font-black uppercase tracking-[0.4em] text-[var(--accent-strong)]">
            AI Automated System
          </span>
        </motion.div>
        
        <h1 className="text-5xl lg:text-6xl font-[900] tracking-tighter text-[var(--text-primary)]">
          인허가 관제 대시보드<span className="text-[var(--accent-strong)]">.</span>
        </h1>
        <p className="text-[var(--text-secondary)] font-medium text-lg max-w-2xl">
          전국 주요 관공서망과 실시간으로 연동되어, 각 프로젝트별 인허가 진행률과 법규 충돌 가능성을 AI가 예측합니다.
        </p>
      </div>

      <div className="grid gap-6 grid-cols-1 md:grid-cols-3 mb-4">
        {[
          { label: "활성 인허가 건수", value: "24", suffix: "건", glow: "border-teal-500/30" },
          { label: "AI 승인 예측률 (평균)", value: "96.4", suffix: "%", glow: "border-blue-500/30" },
          { label: "최근 30일 지연 건수", value: "0", suffix: "건", glow: "border-green-500/30" }
        ].map((stat, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
            className={`relative overflow-hidden rounded-[2rem] border bg-[var(--surface-soft)] p-8 shadow-[var(--shadow-xl)] backdrop-blur-xl group transition-all hover:-translate-y-1 ${stat.glow}`}
          >
            <div className="absolute -right-10 -top-10 h-32 w-32 rounded-full bg-[var(--accent-strong)]/5 blur-[40px] group-hover:bg-[var(--accent-strong)]/10 transition-colors" />
            <p className="text-[11px] font-black uppercase tracking-[0.2em] text-[var(--text-hint)] mb-2">
              {stat.label}
            </p>
            <p className="text-4xl font-[900] tracking-tighter text-[var(--text-primary)]">
              {stat.value}
              <span className="text-xl text-[var(--text-tertiary)] ml-1">{stat.suffix}</span>
            </p>
          </motion.div>
        ))}
      </div>

      <Card className="overflow-hidden rounded-[2.5rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] shadow-[var(--shadow-2xl)] backdrop-blur-xl">
        <div className="border-b border-[var(--line-strong)] px-8 py-6 bg-[var(--surface)]">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold tracking-tight text-[var(--text-primary)] flex items-center gap-3">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent-strong)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="m9 15 2 2 4-4"/></svg>
              실시간 인허가 파이프라인
            </h2>
            <button className="text-[11px] font-black tracking-widest uppercase text-[var(--accent-strong)] hover:text-white transition-colors bg-[var(--accent-strong)]/10 px-4 py-2 rounded-full border border-[var(--accent-strong)]/20">
              새 인허가 등록
            </button>
          </div>
        </div>
        <CardContent className="p-0">
          <div className="overflow-x-auto custom-scrollbar">
            <table className="w-full text-left text-sm whitespace-nowrap">
              <thead className="bg-[var(--surface-muted)] text-[10px] uppercase tracking-widest text-[var(--text-tertiary)] font-black">
                <tr>
                  <th className="px-8 py-5">추적 ID</th>
                  <th className="px-8 py-5">프로젝트 및 유형</th>
                  <th className="px-8 py-5">진행 상태</th>
                  <th className="px-8 py-5">AI 통과 예측</th>
                  <th className="px-8 py-5 text-right">관할 기관 및 기한</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--line-strong)] text-[var(--text-secondary)] font-medium">
                {MOCK_PERMITS.map((permit) => (
                  <tr key={permit.id} className="transition-colors hover:bg-[var(--surface-muted)]/50 group">
                    <td className="px-8 py-6 font-mono text-xs font-bold text-[var(--text-primary)]">
                      {permit.id}
                    </td>
                    <td className="px-8 py-6">
                      <p className="font-bold text-[var(--text-primary)] text-base mb-1">{permit.projectName}</p>
                      <p className="text-xs text-[var(--text-tertiary)] flex items-center gap-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-[var(--line-strong)]" />
                        {permit.type}
                      </p>
                    </td>
                    <td className="px-8 py-6">
                      <div className="flex flex-col gap-2 w-40">
                        <div className="flex items-center justify-between text-xs">
                          <span className={`font-black uppercase tracking-wide ${
                            permit.status === 'approved' ? 'text-teal-400' :
                            permit.status === 'processing' ? 'text-blue-400' : 'text-amber-400'
                          }`}>
                            {permit.status === 'approved' ? '승인 완료' :
                             permit.status === 'processing' ? '심사 중' : '서류 검토'}
                          </span>
                          <span className="text-[var(--text-primary)] font-bold">{permit.progress}%</span>
                        </div>
                        <div className="h-1.5 w-full rounded-full bg-[var(--surface-strong)] overflow-hidden">
                          <div 
                            className={`h-full rounded-full ${
                              permit.status === 'approved' ? 'bg-teal-400 shadow-[0_0_10px_rgba(45,212,191,0.5)]' :
                              permit.status === 'processing' ? 'bg-blue-400 shadow-[0_0_10px_rgba(96,165,250,0.5)]' : 'bg-amber-400'
                            }`}
                            style={{ width: `${permit.progress}%` }}
                          />
                        </div>
                      </div>
                    </td>
                    <td className="px-8 py-6">
                      <div className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/10 px-3 py-1.5 text-xs font-bold text-[var(--accent-strong)]">
                        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="m9 12 2 2 4-4"/><circle cx="12" cy="12" r="10"/></svg>
                        {permit.aiConfidence}% 통과 예측
                      </div>
                    </td>
                    <td className="px-8 py-6 text-right">
                      <p className="font-bold text-[var(--text-primary)]">{permit.agency}</p>
                      <p className="text-xs text-[var(--text-hint)] mt-1">{permit.dueDate} 기한</p>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
