"use client";

import { useEffect } from "react";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";
import { apiClient } from "@/lib/api-client";

type ProjectMetaLite = { id: string; name?: string; status?: string; address?: string };

/**
 * 프로젝트 컨텍스트 단일 writer (SSOT).
 *
 * 프로젝트 레이아웃에 마운트되어, 모든 서브라우트(/site-analysis, /design 등 직접 진입 포함)에서
 * URL의 projectId를 useProjectContextStore에 바인딩한다. 이전에는 page.tsx(index)와
 * ProjectAnalysisFlow가 각각 setProject를 호출(중복 writer)하고 서브라우트는 누락되어,
 * 헤더(projectName)·주소바·부지분석탭이 서로 다른 출처를 봤다.
 *
 *   - projectId가 실제로 바뀔 때만 cross-module 데이터를 리셋(스냅샷 존재 시 복원).
 *   - name/address는 로컬 스토어 → 백엔드 meta 순으로 resolve 후 원자 갱신.
 *   - 같은 projectId 재바인딩은 리셋하지 않는다(회귀 방지).
 */
export function ProjectContextBinder({ projectId }: { projectId: string }) {
  useEffect(() => {
    let cancelled = false;

    // 1) 즉시 로컬 스토어 값으로 바인딩(헤더/주소바 stale 방지).
    const local = useProjectStore.getState().getProjectById(projectId);
    useProjectContextStore
      .getState()
      .setProject(
        projectId,
        local?.name || "",
        (local?.status as string) || "draft",
        local?.address || undefined,
      );

    // 2) 백엔드 meta가 resolve되면 name/status/address를 보강(동일 projectId라 리셋 없음).
    (async () => {
      try {
        const meta = await apiClient.get<ProjectMetaLite>(`/projects/${projectId}`);
        if (cancelled || !meta) return;
        const cur = useProjectContextStore.getState();
        if (cur.projectId !== projectId) return;
        useProjectContextStore
          .getState()
          .setProject(
            projectId,
            meta.name || local?.name || "",
            (meta.status as string) || (local?.status as string) || "draft",
            meta.address || local?.address || undefined,
          );
      } catch {
        /* meta 미가용 — 로컬 바인딩 유지 */
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [projectId]);

  return null;
}
