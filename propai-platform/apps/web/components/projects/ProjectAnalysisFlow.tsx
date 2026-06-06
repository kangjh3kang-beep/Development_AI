"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { ProjectPipelinePanel } from "@/components/pipeline/ProjectPipelinePanel";
import { AutoRecommendPanel } from "@/components/feasibility/AutoRecommendPanel";
import { GlobalAddressSearch, type AddressEntry } from "@/components/common/GlobalAddressSearch";

/**
 * 프로젝트 상세 허브의 통합 분석 흐름.
 *
 *   1단계 부지분석  — store의 프로젝트 주소로 자동 실행 (projectMode + autoStart)
 *   2단계 사업모델 추천 — 1단계 결과 확인 후 "사업모델 추천 보기"로 진입 (embedded)
 *
 * 주소는 새 프로젝트 생성 시 한 번만 입력되며 store(siteAnalysis)에서 공유된다.
 * 기존 프로젝트에 주소 정보가 없으면 주소 입력 프롬프트를 먼저 노출한다.
 */
export function ProjectAnalysisFlow({
  projectId,
  projectName = "",
}: {
  projectId: string;
  projectName?: string;
}) {
  const storeProjectId = useProjectContextStore((s) => s.projectId);
  const storeAddress = useProjectContextStore((s) => s.siteAnalysis?.address ?? "");

  const [showRecommend, setShowRecommend] = useState(false);

  // 컨텍스트 바인딩(setProject)은 layout의 ProjectContextBinder가 단일 writer로 수행한다.
  // (이전: 여기서도 setProject 호출 → 중복 writer로 출처 불일치 발생)
  void projectName;

  // store 컨텍스트가 현재 프로젝트와 일치할 때만 저장된 주소를 신뢰한다.
  const contextMatches = storeProjectId === projectId;
  const hasAddress = contextMatches && !!storeAddress;

  // ── 주소 미설정 — 입력 프롬프트 ──
  if (!hasAddress) {
    return (
      <section className="rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-8 sm:p-10 shadow-[var(--shadow-xl)] relative overflow-hidden">
        <div className="absolute top-0 right-0 w-40 h-40 bg-[var(--accent-strong)]/10 blur-[60px] rounded-full pointer-events-none" />
        <div className="relative z-10 max-w-2xl space-y-5">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--accent-soft)] text-[var(--accent-strong)]">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0"/><circle cx="12" cy="10" r="3"/></svg>
            </span>
            <h2 className="text-2xl font-[900] tracking-tight text-[var(--text-primary)]">프로젝트 주소를 입력하세요</h2>
          </div>
          <p className="text-sm font-medium text-[var(--text-secondary)]">
            주소를 선택하면 용도지역·대지면적·조례를 자동 조회하고 부지분석을 시작합니다.
          </p>
          <GlobalAddressSearch
            onChange={(entries: AddressEntry[]) => {
              // GlobalAddressSearch가 store(siteAnalysis)를 자동 갱신한다.
              // 주소가 채워지면 hasAddress가 true가 되어 분석 흐름으로 전환된다.
              void entries;
            }}
            placeholder="주소를 검색하세요 (예: 서울 강남구 역삼동)"
          />
        </div>
      </section>
    );
  }

  // ── 통합 분석 흐름 ──
  return (
    <div className="space-y-12">
      {/* 1단계 — 부지분석 (자동 실행) */}
      <ProjectPipelinePanel
        projectMode
        autoStart
        onSiteAnalysisComplete={() => setShowRecommend(true)}
      />

      {/* 2단계 — 사업모델 추천 (부지분석 확인 후) */}
      <AnimatePresence>
        {showRecommend && (
          <motion.section
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={{ duration: 0.4 }}
            className="rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-8 lg:p-10 shadow-[var(--shadow-2xl)] relative overflow-hidden"
          >
            <div className="absolute -right-24 -top-24 h-72 w-72 rounded-full bg-[var(--accent-strong)]/8 blur-[90px] pointer-events-none" />
            <div className="relative z-10 space-y-8">
              <div className="flex items-center gap-3">
                <span className="rounded-lg bg-[var(--accent-soft)] px-3 py-1 text-[10px] font-[900] uppercase tracking-[0.25em] text-[var(--accent-strong)]">
                  2단계
                </span>
                <h2 className="text-2xl font-[900] tracking-tight text-[var(--text-primary)]">
                  최적 사업모델 추천
                </h2>
              </div>
              <AutoRecommendPanel embedded />
            </div>
          </motion.section>
        )}
      </AnimatePresence>
    </div>
  );
}
