"use client";

/**
 * 프로젝트/분석 서버 동기화 부트스트랩.
 * 대시보드 진입 시 서버→로컬 1회 pull, 이후 스토어 변경을 서버로 debounced push.
 */

import { useEffect } from "react";
import { useProjectStore } from "@/store/useProjectStore";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useLandScheduleStore } from "@/store/useLandScheduleStore";
import { syncDown, scheduleSyncUp } from "@/lib/projectSync";

export function ProjectSyncProvider() {
  useEffect(() => {
    // 1) 서버 → 로컬 (로그인 시)
    void syncDown();
    // 2) 로컬 변경 → 서버 (debounced)
    const unsubA = useProjectStore.subscribe(() => scheduleSyncUp());
    const unsubB = useProjectContextStore.subscribe(() => scheduleSyncUp());
    const unsubC = useLandScheduleStore.subscribe(() => scheduleSyncUp());
    return () => { unsubA(); unsubB(); unsubC(); };
  }, []);
  return null;
}
