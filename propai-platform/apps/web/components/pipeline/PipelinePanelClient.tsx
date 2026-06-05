"use client";

/**
 * ProjectPipelinePanel 클라이언트 전용 래퍼 — Cloudflare Worker SSR 부하(오류 1102) 완화.
 * 대형 패널을 ssr:false로 코드분할해 서버는 가벼운 셸만 렌더, 브라우저에서 하이드레이트.
 */

import dynamic from "next/dynamic";

const ProjectPipelinePanel = dynamic(
  () => import("@/components/pipeline/ProjectPipelinePanel").then((m) => m.ProjectPipelinePanel),
  {
    ssr: false,
    loading: () => (
      <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-8 text-center text-sm text-[var(--text-hint)]">
        분석 패널 불러오는 중…
      </div>
    ),
  },
);

export function PipelinePanelClient() {
  return <ProjectPipelinePanel />;
}
