"use client";

/**
 * 분석 결과 영속 캐시(localStorage) — 한 번 분석한 결과를 재사용해 재진입 시 재분석을 막는다.
 * 키별 TTL로 신선도 관리(용도지역=길게, 실거래=짧게). 입력(주소) 변경 시 키가 달라져 자동 재분석.
 */

type Cached<T> = { data: T; ts: number };
const PREFIX = "propai_afc:";

export function getCachedAnalysis<T>(key: string, ttlMs: number): T | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(PREFIX + key);
    if (!raw) return null;
    const c = JSON.parse(raw) as Cached<T>;
    if (!c || typeof c.ts !== "number" || Date.now() - c.ts > ttlMs) return null;
    return c.data;
  } catch {
    return null;
  }
}

export function setCachedAnalysis<T>(key: string, data: T): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify({ data, ts: Date.now() }));
  } catch {
    /* 용량 초과 등은 무시(캐시는 best-effort) */
  }
}

// 자주 쓰는 TTL(ms)
export const TTL_30D = 30 * 24 * 60 * 60 * 1000;
export const TTL_7D = 7 * 24 * 60 * 60 * 1000;
export const TTL_3D = 3 * 24 * 60 * 60 * 1000;
