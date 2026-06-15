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
  // 시공감리(WP-17 운영 그룹 extraRoute) — 클립보드/체크리스트
  supervision: <><path d="M9 2h6a1 1 0 0 1 1 1v1a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z" /><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" /><path d="m9 14 2 2 4-4" /></>,
  // 드론측량(WP-17 운영 그룹 extraRoute) — 쿼드콥터
  drone: <><rect x="9" y="9" width="6" height="6" rx="1" /><circle cx="5" cy="5" r="2.5" /><circle cx="19" cy="5" r="2.5" /><circle cx="5" cy="19" r="2.5" /><circle cx="19" cy="19" r="2.5" /><path d="M7 7 9 9M17 7l-2 2M7 17l2-2M17 17l-2-2" /></>,
  // ── 프로젝트 도구 인덱스(고아 라우트 surface) 아이콘 (lifecycle-stages.PROJECT_TOOLS) ──
  // 설계도면(CAD) — 자/룰러
  tool_cad: <><path d="M21.3 15.3a2.4 2.4 0 0 1 0 3.4l-2.6 2.6a2.4 2.4 0 0 1-3.4 0L2.7 8.7a2.4 2.4 0 0 1 0-3.4l2.6-2.6a2.4 2.4 0 0 1 3.4 0Z" /><path d="m14.5 12.5 2-2" /><path d="m11.5 9.5 2-2" /><path d="m8.5 6.5 2-2" /><path d="m17.5 15.5 2-2" /></>,
  // 회의방 — 인원
  tool_collab: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" /></>,
  // 공사비 — 코인
  tool_cost: <><circle cx="8" cy="8" r="6" /><path d="M18.09 10.37A6 6 0 1 1 10.34 18" /><path d="M7 6h1v4" /><path d="m16.71 13.88.7.71-2.82 2.82" /></>,
  // 공내역서(BOQ) — 체크리스트
  tool_boq: <><rect width="8" height="4" x="8" y="2" rx="1" ry="1" /><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" /><path d="M12 11h4" /><path d="M12 16h4" /><path d="M8 11h.01" /><path d="M8 16h.01" /></>,
  // 다필지 통합 — 그리드
  tool_parcel: <><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 12h18" /><path d="M12 3v18" /></>,
  // 블록체인 — 링크
  tool_chain: <><path d="M9 17H7A5 5 0 0 1 7 7h2" /><path d="M15 7h2a5 5 0 1 1 0 10h-2" /><line x1="8" x2="16" y1="12" y2="12" /></>,
  // AI 에이전트 — 봇
  tool_agent: <><path d="M12 8V4H8" /><rect width="16" height="12" x="4" y="8" rx="2" /><path d="M2 14h2" /><path d="M20 14h2" /><path d="M15 13v2" /><path d="M9 13v2" /></>,
};

export function StageIcon({ id, size = 20 }: { id: string; size?: number }) {
  const body = ICONS[id] ?? <circle cx="12" cy="12" r="9" />;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...P}>
      {body}
    </svg>
  );
}
