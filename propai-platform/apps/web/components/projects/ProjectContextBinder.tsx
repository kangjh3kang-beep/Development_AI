"use client";

import { useEffect } from "react";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";
import { apiClient } from "@/lib/api-client";
import { applyRemoteSnapshot } from "@/lib/projectSync";
import { buildSiteMetaPatch } from "@/lib/project-site-meta";

type ProjectMetaLite = {
  id: string;
  name?: string;
  status?: string;
  address?: string;
  total_area_sqm?: number | null;
  zone_type?: string | null;
  pnu_codes?: string[] | null;
  analysis_snapshot?: Record<string, unknown> | null;
};

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

    // 0) 프로젝트 진입 시 페이지 상단으로 스크롤(이력/프로젝트관리에서 들어올 때
    //    입지분석 보고서 상단에서 시작 — 가독성·직관성).
    if (typeof window !== "undefined") {
      window.scrollTo({ top: 0, behavior: "auto" });
    }

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
        const ctxStore = useProjectContextStore.getState();
        ctxStore.setProject(
          projectId,
          meta.name || local?.name || "",
          (meta.status as string) || (local?.status as string) || "draft",
          meta.address || local?.address || undefined,
        );

        // 백엔드 analysis_snapshot 복원(기기무관 단일출처). 로컬이 더 최신이면 보존.
        // setProject(step1)가 이미 localStorage 스냅샷을 복원한 뒤이므로,
        // 백엔드가 더 최신일 때만 덮어써 기기간 동기화를 달성한다.
        applyRemoteSnapshot(projectId, meta.analysis_snapshot);

        // 메타 병합(컨텍스트 우선, 빈 필드만 백엔드 meta로 보강).
        // 사용자 분석(컨텍스트)이 이미 채운 값은 절대 덮어쓰지 않는다.
        // ★U1: address 포함 — 스냅샷 복원이 address 없는 siteAnalysis로 덮어도 meta.address로
        //   보강해 통합분석 게이트(hasContext=address||pnu)가 막히지 않게 한다.
        const site = useProjectContextStore.getState().siteAnalysis;
        const patch = buildSiteMetaPatch(site, meta);
        if (Object.keys(patch).length > 0) {
          useProjectContextStore.getState().updateSiteAnalysis(patch);
        }
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
