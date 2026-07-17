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
  // 부지분석 완료 여부 — primitive(boolean)만 구독해 리렌더 루프(#185)를 피한다.
  // (store의 siteAnalysis 객체 자체가 아니라 "용도지역이 채워졌는지" boolean만 본다.)
  const siteResolved = useProjectContextStore((s) => !!s.siteAnalysis?.zoneCode || s.siteAnalysis?.landAreaSqm != null);

  const [showRecommend, setShowRecommend] = useState(false);

  // 컨텍스트 바인딩(setProject)은 layout의 ProjectContextBinder가 단일 writer로 수행한다.
  // (이전: 여기서도 setProject 호출 → 중복 writer로 출처 불일치 발생)
  void projectName;

  // ★persist hydration race 가드(React #185 방지·"분석 흐름 영역 표시 중 일시 오류" 근본수정):
  //   첫 렌더(hydration 전 storeProjectId=null)에 GlobalAddressSearch를 마운트하면, microtask 뒤
  //   persist 복원이 projectId를 채우며 즉시 언마운트 전환이 일어나고, 그 급전환 중 setProject·
  //   deps 재생성 연쇄로 React #185(max update depth)가 터져 HubErrorBoundary가 폴백을 띄운다.
  //   hydration/바인딩 전(null)엔 스켈레톤만 렌더해 조기 마운트→언마운트 경합을 구조적으로 차단한다
  //   (바인딩 후 재렌더에서 hasAddress를 올바르게 평가 — 새로고침해야 정상이던 현상 해소).
  if (storeProjectId === null) {
    return (
      <div
        className="h-48 animate-pulse rounded-[var(--radius-lg)] border border-[var(--line)] bg-[var(--surface-soft)]"
        aria-hidden
      />
    );
  }

  // store 컨텍스트가 현재 프로젝트와 일치할 때만 저장된 주소를 신뢰한다.
  const contextMatches = storeProjectId === projectId;
  const hasAddress = contextMatches && !!storeAddress;

  // ── 주소 미설정 — 입력 프롬프트 ──
  if (!hasAddress) {
    return (
      <section className="rounded-[var(--radius-lg)] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-8 sm:p-10 shadow-[var(--shadow-xl)] relative overflow-hidden">
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
      {/* 부지분석 진행 신호 — 결과(siteResolved)가 채워지기 전엔 스피너 + '분석 중',
          채워지면 명확한 완료 전환 텍스트를 보여 "지금 무슨 일이 일어나는지" 직관화한다.
          (실제 실행 상태는 하위 ProjectPipelinePanel이 관리 — 여기선 결과 유무만 신호) */}
      <div
        className={`flex items-center gap-3 rounded-2xl border px-5 py-3.5 transition-colors ${
          siteResolved
            ? "border-[var(--accent-strong)]/30 bg-[var(--accent-soft)]"
            : "border-[var(--line)] bg-[var(--surface-soft)]"
        }`}
        aria-live="polite"
        aria-busy={!siteResolved}
      >
        {siteResolved ? (
          <>
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--accent-strong)] text-white">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M20 6 9 17l-5-5" />
              </svg>
            </span>
            <p className="text-sm font-bold text-[var(--accent-strong)]">
              부지분석 완료 — 용도지역·면적·규제가 아래 요약에 반영되었습니다.
            </p>
          </>
        ) : (
          <>
            <span className="h-5 w-5 shrink-0 animate-spin rounded-full border-2 border-[var(--accent-strong)] border-t-transparent" aria-hidden="true" />
            <p className="text-sm font-bold text-[var(--text-secondary)]">
              부지분석 진행 중 — 용도지역·대지면적·조례를 자동 조회하고 있습니다…
            </p>
          </>
        )}
      </div>

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
            className="rounded-[var(--radius-lg)] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-8 lg:p-10 shadow-[var(--shadow-2xl)] relative overflow-hidden"
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
