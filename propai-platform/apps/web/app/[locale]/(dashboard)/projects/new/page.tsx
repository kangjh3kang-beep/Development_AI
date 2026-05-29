"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { useProjectStore } from "@/store/useProjectStore";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { GlobalAddressSearch, type AddressEntry } from "@/components/common/GlobalAddressSearch";

const PROJECT_TYPES = [
  { value: "residential", label: "주거" },
  { value: "commercial", label: "상업" },
  { value: "mixed", label: "복합" },
  { value: "logistics", label: "물류" },
  { value: "industrial", label: "산업" },
];

const AVAILABLE_MODULES = [
  { key: "design", label: "설계", defaultOn: true },
  { key: "bim", label: "BIM 3D", defaultOn: true },
  { key: "finance", label: "금융 분석", defaultOn: true },
  { key: "drone", label: "드론 점검", defaultOn: false },
  { key: "blockchain", label: "에스크로", defaultOn: false },
  { key: "tax", label: "세금 시뮬레이션", defaultOn: false },
  { key: "inspection", label: "현장 점검", defaultOn: false },
  { key: "report", label: "보고서", defaultOn: true },
];

export default function NewProjectPage() {
  const router = useRouter();
  const addProject = useProjectStore(state => state.addProject);
  const clearProject = useProjectContextStore(state => state.clearProject);
  const setProject = useProjectContextStore(state => state.setProject);
  const siteAnalysis = useProjectContextStore(state => state.siteAnalysis);

  // 새 프로젝트 진입 시 이전 데이터 초기화
  useState(() => { clearProject(); });

  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [pnu, setPnu] = useState("");
  const [area, setArea] = useState("");
  const [projectType, setProjectType] = useState("mixed");
  const [modules, setModules] = useState<Set<string>>(
    new Set(AVAILABLE_MODULES.filter(m => m.defaultOn).map(m => m.key))
  );
  const [isSubmitting, setIsSubmitting] = useState(false);

  const toggleModule = (key: string) => {
    setModules(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const handleSubmit = async () => {
    if (!name.trim() || !location.trim()) return;
    setIsSubmitting(true);

    const projectId = addProject({
      name,
      address: location,
      pnu: pnu || "",
      area: area || "0",
      type: projectType
    });

    // GlobalAddressSearch가 수집한 siteAnalysis 데이터를 임시 저장
    const currentSiteAnalysis = useProjectContextStore.getState().siteAnalysis;

    // ProjectContextStore에 프로젝트 ID 설정
    setProject(projectId, name, "draft");

    // setProject가 cross-module 데이터를 초기화하므로 siteAnalysis를 복원
    if (currentSiteAnalysis) {
      useProjectContextStore.getState().updateSiteAnalysis(currentSiteAnalysis);
    }

    setTimeout(() => {
      router.push(`/ko/projects/${projectId}`);
    }, 1500);
  };

  return (
    <div className="flex flex-col gap-10 pb-20 max-w-5xl mx-auto mt-4">
      <div className="space-y-2">
        <h1 className="text-4xl font-[900] tracking-tighter text-[var(--text-primary)]">
          새 프로젝트 <span className="text-[var(--accent-strong)]">_</span>
        </h1>
        <p className="text-[var(--text-secondary)] font-medium">
          새로운 디지털 트윈 기반 부동산 프로젝트를 생성하고 AI 분석을 시작합니다.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column: Form Steps */}
        <div className="lg:col-span-2 space-y-8">
          {/* Step 1 */}
          <section className="relative overflow-hidden rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-8 shadow-[var(--shadow-xl)] backdrop-blur-xl group transition-all focus-within:border-[var(--accent-strong)]/50 focus-within:shadow-[0_0_30px_rgba(45,212,191,0.1)]">
            <div className="absolute top-0 left-0 w-1 h-full bg-gradient-to-b from-[var(--accent-strong)] to-transparent opacity-50" />
            
            <div className="flex items-center gap-4 mb-8">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--surface)] border border-[var(--line-strong)] text-[var(--text-secondary)] font-black">
                01
              </div>
              <h3 className="text-xl font-bold text-[var(--text-primary)] tracking-wide">프로젝트 메타데이터</h3>
            </div>

            <div className="space-y-6">
              <div className="grid gap-2">
                <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)]">프로젝트 명칭</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="예: 성수 IT밸리 복합개발"
                  className="w-full rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-muted)] py-4 px-5 text-sm font-bold placeholder:text-[var(--text-hint)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/30 focus:border-[var(--accent-strong)] transition-all text-[var(--text-primary)]"
                />
              </div>

              <div className="grid gap-2">
                <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)]">소재지 (주소 검색)</label>
                <GlobalAddressSearch
                  onChange={(entries: AddressEntry[]) => {
                    if (entries.length > 0) {
                      setLocation(entries[0].fullAddress);
                    }
                  }}
                  placeholder="주소를 검색하세요 (다필지 입력 가능)"
                />
              </div>

              <div className="grid gap-2">
                <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)]">프로젝트 용도</label>
                <div className="flex flex-wrap gap-3">
                  {PROJECT_TYPES.map((type) => (
                    <button
                      key={type.value}
                      type="button"
                      onClick={() => setProjectType(type.value)}
                      className={`rounded-xl px-5 py-3 text-sm font-black tracking-wide transition-all ${
                        projectType === type.value
                          ? "bg-[var(--accent-soft)] border border-[var(--accent-strong)] text-[var(--accent-strong)] shadow-[0_0_15px_rgba(45,212,191,0.2)]"
                          : "border border-[var(--line-strong)] bg-[var(--surface)] text-[var(--text-tertiary)] hover:border-[var(--text-secondary)]"
                      }`}
                    >
                      {type.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </section>

          {/* Step 2 */}
          <section className="relative overflow-hidden rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-8 shadow-[var(--shadow-xl)] backdrop-blur-xl">
             <div className="flex items-center gap-4 mb-8">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--surface)] border border-[var(--line-strong)] text-[var(--text-secondary)] font-black">
                02
              </div>
              <h3 className="text-xl font-bold text-[var(--text-primary)] tracking-wide">활성화 모듈 선택</h3>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
              {AVAILABLE_MODULES.map((mod) => (
                <button
                  key={mod.key}
                  type="button"
                  onClick={() => toggleModule(mod.key)}
                  className={`relative overflow-hidden flex flex-col items-start gap-3 rounded-2xl px-5 py-4 text-left transition-all ${
                    modules.has(mod.key)
                      ? "bg-[var(--accent-strong)]/10 border border-[var(--accent-strong)] text-[var(--accent-strong)]"
                      : "bg-[var(--surface)] border border-[var(--line-strong)] text-[var(--text-tertiary)] hover:bg-[var(--surface-muted)]"
                  }`}
                >
                  <div className={`h-4 w-4 rounded-full border-2 flex items-center justify-center ${
                    modules.has(mod.key) ? "border-[var(--accent-strong)]" : "border-[var(--line-strong)]"
                  }`}>
                    {modules.has(mod.key) && <div className="h-2 w-2 rounded-full bg-[var(--accent-strong)]" />}
                  </div>
                  <span className="text-sm font-black tracking-tight">{mod.label}</span>
                </button>
              ))}
            </div>
          </section>
        </div>

        {/* Right Column: Summary & Actions */}
        <div className="relative">
          <div className="sticky top-24 space-y-6">
            <section className="rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-8 shadow-[var(--shadow-xl)] backdrop-blur-xl relative overflow-hidden">
               <div className="absolute top-0 right-0 w-32 h-32 bg-[var(--accent-strong)]/10 blur-[50px] rounded-full" />
               <h3 className="text-lg font-black text-[var(--text-primary)] mb-6">프로젝트 요약</h3>
               
               <div className="space-y-4 mb-8">
                 <div className="flex justify-between items-center text-sm">
                   <span className="text-[var(--text-tertiary)] font-medium">프로젝트</span>
                   <span className="text-[var(--text-primary)] font-bold truncate max-w-[120px]">{name || "-"}</span>
                 </div>
                 <div className="flex justify-between items-center text-sm">
                   <span className="text-[var(--text-tertiary)] font-medium">위치</span>
                   <span className="text-[var(--text-primary)] font-bold truncate max-w-[120px]">{location || "-"}</span>
                 </div>
                 <div className="flex justify-between items-center text-sm">
                   <span className="text-[var(--text-tertiary)] font-medium">선택 모듈</span>
                   <span className="text-[var(--accent-strong)] font-black">{modules.size}개</span>
                 </div>
               </div>

               <button
                  onClick={handleSubmit}
                  disabled={!name.trim() || !location.trim() || isSubmitting}
                  className="w-full relative overflow-hidden rounded-2xl py-4 text-sm font-black transition-all shadow-[var(--shadow-md)] flex items-center justify-center gap-2
                  disabled:opacity-50 disabled:cursor-not-allowed
                  bg-gradient-to-r from-[var(--accent-strong)] to-[#085d73] text-white hover:shadow-[0_0_20px_rgba(45,212,191,0.4)]"
                >
                  {isSubmitting ? (
                    <>
                      <span className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      초기화 중...
                    </>
                  ) : (
                    "프로젝트 시작"
                  )}
                </button>
            </section>
            
            <div className="rounded-[1.5rem] border border-[var(--line)] bg-[var(--surface-muted)]/50 p-6 backdrop-blur-sm">
              <div className="flex items-start gap-3 text-[var(--text-hint)]">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 mt-0.5"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
                <p className="text-xs leading-relaxed font-medium">
                  프로젝트가 생성되면 지적도(Cadastral Map) 기반의 AI 심층 분석이 백그라운드에서 자동 시작됩니다. 
                  초기 데이터 로드에 5~10초 가량 소요될 수 있습니다.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
