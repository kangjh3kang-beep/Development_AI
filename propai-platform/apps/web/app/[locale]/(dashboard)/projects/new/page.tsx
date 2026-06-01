"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useProjectStore } from "@/store/useProjectStore";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { GlobalAddressSearch, type AddressEntry } from "@/components/common/GlobalAddressSearch";
import { ImageUpload } from "@/components/ui/ImageUpload";

export default function NewProjectPage() {
  const router = useRouter();
  const { locale } = useParams() as { locale: string };
  const addProject = useProjectStore(state => state.addProject);
  const clearProject = useProjectContextStore(state => state.clearProject);
  const setProject = useProjectContextStore(state => state.setProject);

  // 새 프로젝트 진입 시 이전 데이터 초기화 (mount 1회)
  useState(() => { clearProject(); });

  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [siteImageUrl, setSiteImageUrl] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  // 주소가 선택되면 GlobalAddressSearch가 /zoning/comprehensive를 호출하여
  // PNU·용도지역·면적·조례 등 부지분석 데이터를 store(siteAnalysis)에 자동 저장한다.
  const handleAddressChange = (entries: AddressEntry[]) => {
    if (entries.length > 0) {
      setLocation(entries[0].fullAddress);
    } else {
      setLocation("");
    }
  };

  const handleSubmit = async () => {
    if (!name.trim() || !location.trim()) return;
    setIsSubmitting(true);

    const currentSiteAnalysis = useProjectContextStore.getState().siteAnalysis;
    let projectId = "";

    // store 저장은 localStorage 용량초과(QuotaExceededError) 등으로 실패할 수 있으나
    // 그래도 프로젝트 생성·이동은 반드시 진행되도록 각 단계를 개별 try로 격리한다.
    try {
      projectId = addProject({
        name,
        address: location,
        pnu: currentSiteAnalysis?.pnu ?? "",
        area: currentSiteAnalysis?.landAreaSqm ? String(currentSiteAnalysis.landAreaSqm) : "0",
        type: "mixed",
        siteImageUrl: siteImageUrl || undefined,
      });
    } catch (err) {
      console.error("프로젝트 저장 경고(이동은 계속):", err);
    }

    try {
      setProject(projectId || crypto.randomUUID(), name, "draft");
      const restored = currentSiteAnalysis ?? {
        estimatedValue: null, landAreaSqm: null, zoneCode: null, address: location, pnu: null,
      };
      if (!restored.address) restored.address = location;
      useProjectContextStore.getState().updateSiteAnalysis(restored);
    } catch (err) {
      console.error("컨텍스트 저장 경고(이동은 계속):", err);
    }

    // 이동: projectId가 없으면(저장 실패) 임시 ID로라도 진입해 부지분석 시작.
    const targetId = projectId || `tmp-${Date.now()}`;
    try {
      router.push(`/${locale}/projects/${targetId}?new=1`);
    } catch (err) {
      console.error("이동 실패:", err);
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-10 pb-20 max-w-3xl mx-auto mt-4">
      <div className="space-y-2">
        <h1 className="text-4xl font-[900] tracking-tighter text-[var(--text-primary)]">
          새 프로젝트 <span className="text-[var(--accent-strong)]">_</span>
        </h1>
        <p className="text-[var(--text-secondary)] font-medium">
          프로젝트명과 주소만 입력하면 됩니다. 주소를 선택하는 즉시 AI 부지분석이 시작되며,
          이어서 최적 사업모델을 추천합니다.
        </p>
      </div>

      {/* ── 단일 입력 카드 ── */}
      <section className="relative overflow-hidden rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-8 shadow-[var(--shadow-xl)] backdrop-blur-xl transition-all focus-within:border-[var(--accent-strong)]/50 focus-within:shadow-[0_0_30px_rgba(45,212,191,0.1)]">
        <div className="absolute top-0 left-0 w-1 h-full bg-gradient-to-b from-[var(--accent-strong)] to-transparent opacity-50 pointer-events-none" />

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
              className="w-full rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-muted)] py-4 px-5 text-sm font-bold placeholder:text-[var(--text-hint)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/30 focus:border-[var(--accent-strong)] transition-all text-[var(--text-primary)] relative z-10"
            />
          </div>

          <div className="grid gap-2 relative z-10">
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)]">소재지 (주소 검색)</label>
            <GlobalAddressSearch
              onChange={handleAddressChange}
              placeholder="주소를 검색하세요 (다필지 입력 가능)"
            />
            <p className="text-[11px] font-medium text-[var(--text-hint)] mt-1">
              주소를 선택하면 용도지역·대지면적·공시지가·지자체 조례를 자동 조회합니다.
            </p>
          </div>

          <div className="grid gap-2 mt-4 relative z-10">
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)]">현장(부지) 이미지 등록</label>
            <ImageUpload 
              value={siteImageUrl}
              onChange={setSiteImageUrl}
              label="클릭하거나 현장 사진을 드래그하여 업로드하세요"
            />
          </div>
        </div>
      </section>

      {/* ── 요약 + 시작 ── */}
      <section className="rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-8 shadow-[var(--shadow-xl)] backdrop-blur-xl relative overflow-hidden">
        <div className="absolute top-0 right-0 w-32 h-32 bg-[var(--accent-strong)]/10 blur-[50px] rounded-full pointer-events-none" />

        <div className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm">
              <span className="text-[var(--text-tertiary)] font-medium w-16">프로젝트</span>
              <span className="text-[var(--text-primary)] font-bold truncate max-w-[280px]">{name || "-"}</span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-[var(--text-tertiary)] font-medium w-16">위치</span>
              <span className="text-[var(--text-primary)] font-bold truncate max-w-[280px]">{location || "-"}</span>
            </div>
          </div>

          <button
            onClick={handleSubmit}
            disabled={!name.trim() || !location.trim() || isSubmitting}
            className="w-full sm:w-auto relative overflow-hidden rounded-2xl py-4 px-10 text-sm font-black transition-all shadow-[var(--shadow-md)] flex items-center justify-center gap-2
            disabled:opacity-50 disabled:cursor-not-allowed
            bg-gradient-to-r from-[var(--accent-strong)] to-[#085d73] text-white hover:shadow-[0_0_20px_rgba(45,212,191,0.4)]"
          >
            {isSubmitting ? (
              <>
                <span className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                분석 시작 중...
              </>
            ) : (
              "프로젝트 시작 →"
            )}
          </button>
        </div>

        <div className="mt-6 pt-6 border-t border-[var(--line)] flex items-start gap-3 text-[var(--text-hint)]">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 mt-0.5"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
          <p className="text-xs leading-relaxed font-medium">
            프로젝트가 생성되면 부지분석이 자동으로 진행되고, 결과를 확인한 뒤 최적 사업모델 Top 3 추천으로 이어집니다.
            용도·활성 모듈은 분석 과정에서 자동으로 결정됩니다.
          </p>
        </div>
      </section>
    </div>
  );
}
