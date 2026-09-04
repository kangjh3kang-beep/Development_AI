"use client";

/**
 * 관리자 — AI 학습 사례 승인.
 *
 * 자가학습 엔진이 모아둔 "좋은 분석 사례"를 사람이 하나씩 보고 승인해야만
 * AI 프롬프트에 참고 자료로 들어간다(자동 활성 금지). 이 화면이 그 승인 창구다.
 * 실제 목록·승인·다운로드 로직은 components/settings/LearningApprovalPanel.tsx.
 */

import LearningApprovalPanel from "@/components/settings/LearningApprovalPanel";

export default function LearningApprovalAdminPage() {
  return (
    <div className="space-y-6 p-4 sm:p-8">
      <div className="cc-bracketed relative overflow-hidden rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-6 shadow-[var(--shadow-lg)]">
        <div className="cc-grid-bg opacity-50" />
        <i className="cc-bracket cc-bracket--tl" />
        <i className="cc-bracket cc-bracket--tr" />
        <i className="cc-bracket cc-bracket--bl" />
        <i className="cc-bracket cc-bracket--br" />
        <div className="relative z-10 space-y-1.5">
          <span className="cc-meta">LEARNING · HUMAN APPROVAL</span>
          <h1 className="text-2xl font-black text-[var(--text-primary)]">AI 학습 사례 승인</h1>
          <p className="text-sm text-[var(--text-secondary)] break-keep">
            사용자가 좋게 평가한 분석 결과가 여기에 후보로 쌓입니다. 관리자가 한 건씩 확인해
            승인해야만 AI 가 그 사례를 참고합니다 (자동 승인은 하지 않습니다).
          </p>
        </div>
      </div>

      <LearningApprovalPanel />
    </div>
  );
}
