/**
 * 세대(동·호) 상태 SSOT — 배치도(UnitGrid)·실시간 선점보드(UnitLiveBoard)·상세(Unit360Panel)·
 * 3D(Grid3D)가 모두 이 한 부를 소비한다.
 *
 * ★봉합 배경(2026-07-22 화면스펙 감사):
 *  1) 같은 status 가 화면마다 다른 라벨로 표시됐다 — HOLD = "보류"(Grid)/"선점중(타인)"(Live)/
 *     "동·호지정 대기"(360), APPLIED = "청약"(Grid)/"계약 대기"(360), CONTRACTED = "계약"/"계약완료"/
 *     "계약 체결". 사용자가 보드를 옮길 때마다 같은 세대가 다른 이름으로 보였다.
 *  2) 실시간 보드는 3상태(AVAILABLE/HOLD/CONTRACTED)만 알아, 백엔드 board_rows 의 effective_status
 *     가 CANCELLED(또는 APPLIED)를 반환하면 `COLOR[vs] ?? COLOR.AVAILABLE` 폴백이 그 세대를
 *     분양가능(초록)으로 위장했다(계약 취소분이 판매가능처럼 보이는 정합성 결함).
 *
 * 상태 라이프사이클(백엔드 lifecycle_actions/concurrency 정본):
 *   AVAILABLE → HOLD(지정대기) → APPLIED(계약대기) → CONTRACTED(계약완료) / CANCELLED(취소)
 */

export const UNIT_STATUSES = ["AVAILABLE", "HOLD", "APPLIED", "CONTRACTED", "CANCELLED"] as const;
export type UnitStatus = (typeof UNIT_STATUSES)[number];

/** 상태 정본 라벨(전 화면 동일 표기). */
export const UNIT_STATUS_LABEL: Record<UnitStatus, string> = {
  AVAILABLE: "분양가능",
  HOLD: "지정대기",
  APPLIED: "계약대기",
  CONTRACTED: "계약완료",
  CANCELLED: "취소",
};

/**
 * 셀/배지 Tailwind 클래스(색 SSOT: 성공 emerald · 주의 amber · 정보 sky · 위험 rose · 취소 zinc).
 * hover 등 화면별 부가 상태는 소비처에서 클래스를 덧붙인다.
 */
export const UNIT_STATUS_CELL_CLASS: Record<UnitStatus, string> = {
  AVAILABLE: "bg-emerald-500/15 border-emerald-500/40 text-emerald-300",
  HOLD: "bg-amber-500/15 border-amber-500/40 text-amber-300",
  APPLIED: "bg-sky-500/15 border-sky-500/40 text-sky-300",
  CONTRACTED: "bg-rose-500/15 border-rose-500/40 text-rose-300",
  CANCELLED: "bg-zinc-500/15 border-zinc-500/40 text-zinc-400 line-through",
};

/** 3D 큐브(Three.js) hex — 위 색 인코딩과 동일. */
export const UNIT_STATUS_HEX: Record<UnitStatus, number> = {
  AVAILABLE: 0x34d399,
  HOLD: 0xfbbf24,
  APPLIED: 0x38bdf8,
  CONTRACTED: 0xfb7185,
  CANCELLED: 0xa1a1aa,
};

/** 미지 상태(백엔드 스키마 변경 등) — 초록(분양가능)으로 위장하지 않는 중립 회색. */
const UNKNOWN_CELL_CLASS = "bg-zinc-500/10 border-zinc-500/30 text-zinc-400";
const UNKNOWN_HEX = 0x9ca3af;

export const unitStatusLabel = (s: string): string => UNIT_STATUS_LABEL[s as UnitStatus] ?? s;
export const unitStatusCellClass = (s: string): string =>
  UNIT_STATUS_CELL_CLASS[s as UnitStatus] ?? UNKNOWN_CELL_CLASS;
export const unitStatusHex = (s: string): number =>
  UNIT_STATUS_HEX[s as UnitStatus] ?? UNKNOWN_HEX;
