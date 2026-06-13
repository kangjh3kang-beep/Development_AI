"use client";

/**
 * 데이터 출처 정직 배지(market 공용).
 *
 * 가짜 데이터·가짜 차트 금지 원칙에 따라, 백엔드가 내려준 data_source 상태를 그대로 노출한다.
 * - live      : 실데이터 (초록 배지)
 * - fallback  : 합성·추정값 (주황 배지 — "추정")
 * - unavailable: 데이터 없음 (회색 배지 — 차트 대신 안내문구)
 *
 * 색상은 토큰만 사용, WCAG AA 대비 유지.
 */

import type { DataSource } from "./marketTypes";

const MAP: Record<DataSource, { label: string; color: string; bg: string }> = {
  live: { label: "실데이터", color: "var(--status-success)", bg: "color-mix(in srgb, var(--status-success) 12%, transparent)" },
  fallback: { label: "추정·합성", color: "var(--status-warning)", bg: "color-mix(in srgb, var(--status-warning) 12%, transparent)" },
  unavailable: { label: "데이터 없음", color: "var(--text-tertiary)", bg: "var(--surface-muted)" },
};

export function DataSourceBadge({ source }: { source?: DataSource }) {
  // 출처 미지정이면 표기하지 않는다(과대 표기 금지).
  if (!source) return null;
  const m = MAP[source];
  return (
    <span
      className="rounded-full px-2 py-0.5 text-[10px] font-bold"
      style={{ color: m.color, backgroundColor: m.bg }}
      title={`데이터 출처: ${m.label}`}
    >
      {m.label}
    </span>
  );
}
