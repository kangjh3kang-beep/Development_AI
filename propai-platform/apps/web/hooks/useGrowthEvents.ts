/**
 * 자가성장 엔진 — 프론트 텔레메트리 마운트 훅 (설계서 §3.1, Phase 1).
 *
 * AppStateBridge(providers.tsx)에서 1회 마운트한다.
 * - 마운트 시 수집기 초기화(세션ID 생성·전역 오류/Web Vitals 핸들러 등록·flush 타이머).
 * - 라우트 변경마다 page_view 수집(샘플링은 collector 가 적용).
 * - 언마운트 시 잔여 이벤트 flush 후 핸들러 해제.
 *
 * 안전: 전부 논블로킹·SSR 가드. 수집 실패가 앱 동작을 막지 않는다.
 */

"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import {
  initEventCollector,
  teardownEventCollector,
  trackEvent,
} from "@/lib/growth/event-collector";

export function useGrowthEvents(): void {
  const pathname = usePathname();

  // 수집기 초기화·정리(1회). 의존성 없음 → 마운트/언마운트에만 동작.
  useEffect(() => {
    if (typeof window === "undefined") return;
    initEventCollector();
    return () => {
      teardownEventCollector();
    };
  }, []);

  // 라우트 변경 시 page_view 수집.
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!pathname) return;
    trackEvent("page_view", { route: pathname });
  }, [pathname]);
}
