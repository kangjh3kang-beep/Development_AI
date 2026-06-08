import React from "react";

/**
 * 프로젝트 상세 하위 모듈의 "커맨드센터(Spatial Command Center)" HUD 식별 스트립.
 *
 * - 순수 시각/마크업 컴포넌트(데이터·핸들러·상태 없음).
 * - 모듈명(label) + 선택적 보조 메타(meta) + LIVE 점멸 도트만 표시한다.
 * - 색상·모션은 전부 디자인 토큰/cc-* 유틸(globals.css)을 사용하며 하드코딩 색이 없다.
 * - 기존 공용 헤더(ModulePlaceholder)는 건드리지 않고, 그 위에 얇게 얹는 식별 밴드.
 */
type ModuleCommandStripProps = {
  /** 모듈 식별 라벨(예: "FEASIBILITY · 사업성 분석"). 보통 영문코드 + 한글병기. */
  label: string;
  /** 우측에 노출할 보조 메타(예: 모드/단계). 없으면 LIVE 도트만 표시. */
  meta?: string;
};

export function ModuleCommandStrip({ label, meta }: ModuleCommandStripProps) {
  return (
    <div className="cc-bracketed relative flex flex-wrap items-center justify-between gap-3 overflow-hidden rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-5 py-3 shadow-[var(--shadow-inner)]">
      {/* 정밀 그리드 배경(은은) — 커맨드센터 모티프 */}
      <div className="cc-grid-bg opacity-40" />
      {/* HUD 코너 브래킷 */}
      <i className="cc-bracket cc-bracket--tl" />
      <i className="cc-bracket cc-bracket--tr" />
      <i className="cc-bracket cc-bracket--bl" />
      <i className="cc-bracket cc-bracket--br" />

      <span className="relative z-10 cc-meta">{label}</span>
      <div className="relative z-10 flex items-center gap-3">
        {meta ? <span className="cc-label text-[var(--text-secondary)]">{meta}</span> : null}
        <span className="cc-live">
          <i />
          LIVE
        </span>
      </div>
    </div>
  );
}
