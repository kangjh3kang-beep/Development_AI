"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

const Icons = {
  Search: () => <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>,
  Upload: () => <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/></svg>,
  Cpu: () => <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="16" height="16" x="4" y="4" rx="2"/><rect width="6" height="6" x="9" y="9" rx="1"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/></svg>,
  Help: () => <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/></svg>,
  ArrowRight: () => <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>,
  Check: () => <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5"/></svg>,
  Alert: () => <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>,
};

interface SiteInitiatorProps {
  onInitiate: (data: { address?: string; file?: File | null; fileName?: string }) => void;
  loading: boolean;
}

export function SiteInitiator({ onInitiate, loading }: SiteInitiatorProps) {
  const [address, setAddress] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [activeTab, setActiveTab] = useState<"search" | "upload">("search");

  const handleSearch = () => {
    if (!address) return;
    onInitiate({ address });
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
      // In a real app, parse Excel here. For now, simulate.
      onInitiate({ fileName: selectedFile.name });
    }
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Search Header */}
      <div className="flex flex-col gap-2">
        <h2 className="text-2xl font-black tracking-tight text-[var(--text-primary)]">프로젝트 부지 식별</h2>
        <p className="text-sm text-[var(--text-secondary)]">지번 입력 또는 토지조서 엑셀 업로드를 통해 프로젝트를 시작하세요.</p>
      </div>

      {/* Input Area */}
      <div className="relative group">
        <div className="absolute -inset-1 bg-gradient-to-r from-[var(--accent)]/20 to-indigo-500/20 rounded-[2.5rem] blur-xl opacity-20 group-hover:opacity-40 transition duration-1000"></div>
        <div className="relative rounded-[2rem] border border-[var(--line)] bg-[var(--glass-bg)] p-8 shadow-2xl backdrop-blur-3xl">
          <AnimatePresence mode="wait">
            {activeTab === "search" ? (
              <motion.div
                key="search"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className="flex flex-col gap-6"
              >
                <div className="flex gap-3">
                  <div className="relative flex-1">
                    <div className="absolute left-4 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)] group-focus-within:text-[var(--accent-strong)] transition-colors">
                      <Icons.Search />
                    </div>
                    <input
                      type="text"
                      placeholder="서울시 성동구 성수동 1가 12-3..."
                      value={address}
                      onChange={(e) => setAddress(e.target.value)}
                      className="w-full rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] py-4 pl-12 pr-4 text-sm font-medium text-[var(--text-primary)] placeholder:text-[var(--text-hint)] focus:border-[var(--accent-strong)] focus:outline-none focus:ring-4 focus:ring-[var(--accent-soft)] transition-all shadow-sm"
                    />
                  </div>
                  <button
                    onClick={handleSearch}
                    disabled={loading || !address}
                    className="flex items-center gap-2 rounded-2xl bg-[var(--accent-strong)] px-8 py-4 font-black text-white shadow-lg transition-all hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50 disabled:grayscale"
                  >
                    {loading ? "분석 중..." : "분석 시작"}
                    {!loading && <Icons.ArrowRight />}
                  </button>
                </div>
                
                {/* AI Helper for Search */}
                <div className="flex items-start gap-4 rounded-2xl bg-[var(--surface-muted)] p-5 border border-[var(--line)] backdrop-blur-md">
                  <div className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--accent-soft)] text-[var(--accent-strong)] shadow-sm">
                    <Icons.Cpu />
                  </div>
                  <div className="flex flex-col gap-1">
                      <p className="text-[10px] font-black text-[var(--text-hint)] uppercase tracking-[0.2em] mb-1">AI 분석 노트 (Analyst)</p>
                      <p className="text-xs leading-relaxed text-[var(--text-secondary)] font-medium">
                        지정한 지번의 현재 용도지역은 <span className="text-[var(--accent-strong)] font-bold">'준공업지역'</span>입니다. 
                        인근 성수역 복합개발 사례를 분석한 결과, 종변경을 통해 용적률 상향 가능성이 탐지되었습니다.
                      </p>
                  </div>
                </div>
              </motion.div>
            ) : (
              <motion.div
                key="upload"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className="flex flex-col gap-6"
              >
                <div className="relative flex min-h-[160px] flex-col items-center justify-center rounded-3xl border-2 border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] p-8 transition-colors hover:border-[var(--accent-strong)] hover:bg-[var(--accent-soft)]/20">
                  <input
                    type="file"
                    accept=".xlsx, .xls, .csv"
                    onChange={handleFileUpload}
                    className="absolute inset-0 cursor-pointer opacity-0"
                  />
                  <Icons.Upload />
                  <p className="text-sm font-bold text-[var(--text-primary)]">
                    {file ? file.name : "토지조서 엑셀 파일을 드래그하거나 클릭하세요"}
                  </p>
                  <p className="mt-1 text-xs text-[var(--text-tertiary)]">XLSX, XLS, CSV 지원 (최대 20MB)</p>
                </div>

            {/* AI 가이드 */}
            <div className="flex items-start gap-4 rounded-2xl bg-amber-500/5 p-5 border border-amber-500/10 backdrop-blur-md">
              <div className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber-500/20 text-amber-600">
                <Icons.Help />
              </div>
              <div className="flex flex-col gap-1">
                  <p className="text-[10px] font-black text-[var(--text-hint)] uppercase tracking-[0.2em] shadow-sm mb-1">AI 가이드 (Guide)</p>
                  <p className="text-xs leading-relaxed text-[var(--text-secondary)] font-medium">
                    엑셀 업로드 시 필지번호(PNU) 또는 주소 컬럼을 자동으로 인식합니다. 
                    다수 필지의 <span className="text-amber-600 font-bold underline decoration-amber-500/30">합필 분석</span> 기능이 활성화되어 최적 개발 면적을 제안합니다.
                  </p>
              </div>
            </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Feature Cards for "High Level" look */}
      <div className="grid gap-4 md:grid-cols-3">
         {[
           { title: "다각도 종변경 분석", desc: "주변 개발 압력 및 조례 분석을 통해 용도지역 변경 가능성을 확률로 제시합니다.", icon: <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-blue-500"><rect width="16" height="16" x="4" y="4" rx="2"/><rect width="6" height="6" x="9" y="9" rx="1"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/></svg> },
           { title: "토지 형질 정밀 진단", desc: "경사도, 고도, 접도 상태를 GIS 기반으로 분석하여 토목 비용 리스크를 예측합니다.", icon: <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-emerald-500"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg> },
           { title: "최적 개발방식 추천", desc: "수지분석과 결합하여 해당 토지에 가장 유리한 건축물 용도를 AI가 자동 선별합니다.", icon: <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-amber-500"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg> },
          ].map((feat, i) => (
            <div key={i} className="group/feat flex flex-col gap-3 rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-6 shadow-sm transition-all hover:bg-[var(--surface-strong)] hover:shadow-md hover:-translate-y-1">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--surface-soft)] text-[var(--text-tertiary)] transition-colors group-hover/feat:bg-[var(--accent-soft)] group-hover/feat:text-[var(--accent-strong)] shadow-inner">
                 {feat.icon}
              </div>
              <h4 className="text-sm font-[900] tracking-tight text-[var(--text-primary)]">{feat.title}</h4>
              <p className="text-xs leading-relaxed text-[var(--text-secondary)] font-medium group-hover/feat:text-[var(--text-primary)] transition-colors">
                {feat.desc}
              </p>
            </div>
          ))}
      </div>
    </div>
  );
}
