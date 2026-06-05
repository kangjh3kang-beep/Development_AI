"use client";

/** 라이프사이클 단계별 세련된 SVG 아이콘(lucide 스타일) — 이모지 대체. */

import type { JSX } from "react";

const P = { fill: "none", stroke: "currentColor", strokeWidth: 1.9, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

const ICONS: Record<string, JSX.Element> = {
  // 입지 분석 — 지도 핀
  site_analysis: <><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" /><circle cx="12" cy="10" r="3" /></>,
  // 법규 검토 — 저울
  legal_compliance: <><path d="M12 3v18" /><path d="M5 7h14" /><path d="m5 7-3 6h6Z" /><path d="m19 7-3 6h6Z" /><path d="M8 21h8" /></>,
  // AI 설계 — 레이어/도면
  design_ai: <><path d="m2 12 5-3 5 3 5-3 5 3" /><path d="m2 17 5-3 5 3 5-3 5 3" /><path d="m2 7 5-3 5 3 5-3 5 3" /></>,
  // 사업성 분석 — 추세 차트
  feasibility: <><path d="M3 3v18h18" /><path d="m7 14 4-4 3 3 5-5" /></>,
  // ESG — 잎
  esg_dashboard: <><path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z" /><path d="M2 21c0-3 1.85-5.36 5.08-6" /></>,
  // 인허가 — 문서/체크
  permit_portal: <><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" /><path d="M14 2v5h5" /><path d="m9 14 2 2 4-4" /></>,
  // 시공 — 크레인/빌딩
  construction: <><path d="M3 21h18" /><path d="M5 21V7l8-4v18" /><path d="M19 21V11l-6-4" /><path d="M9 9h.01M9 13h.01M9 17h.01" /></>,
  // 운영 — 톱니
  operations: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" /></>,
};

export function StageIcon({ id, size = 20 }: { id: string; size?: number }) {
  const body = ICONS[id] ?? <circle cx="12" cy="12" r="9" />;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...P}>
      {body}
    </svg>
  );
}
