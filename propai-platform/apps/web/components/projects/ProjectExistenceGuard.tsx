"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Search } from "lucide-react";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { useProjectStore } from "@/store/useProjectStore";

/**
 * 프로젝트 존재성 게이트(graceful 404).
 *
 * 계정에 없는(또는 삭제된) projectId로 직접 진입했을 때, 백엔드 GET /projects/{id}가 404를
 * 반환한다. 이때 부분/undefined 데이터로 렌더해 크래시하거나 무한 바인딩 스피너에 멈추는 대신,
 * 로컬 스냅샷(useProjectStore)이 없으면 "프로젝트를 찾을 수 없습니다 + 목록으로" graceful 화면을
 * 보여준다.
 *
 * 정상 프로젝트 흐름 보존:
 *   - 백엔드 404 + 로컬 스냅샷 존재(오프라인/로컬 전용 프로젝트) → children 그대로 렌더.
 *   - 404 외 오류(네트워크·5xx 등) → 일시적 장애일 수 있으므로 children 렌더(기존 폴백 유지).
 *   - 메타 resolve 전(로딩) → children 렌더(레이아웃/바인더가 로컬 값으로 즉시 동작).
 */
export function ProjectExistenceGuard({
  projectId,
  locale,
  children,
}: {
  projectId: string;
  locale: string;
  children: React.ReactNode;
}) {
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setNotFound(false);

    (async () => {
      try {
        await apiClient.get(`/projects/${projectId}`);
        // 200 — 존재함. children 렌더 유지.
      } catch (err) {
        if (cancelled) return;
        // 404이고 로컬 스냅샷도 없으면 not-found. (그 외 오류·로컬 존재 시는 기존 흐름 보존)
        const isNotFound = err instanceof ApiClientError && err.status === 404;
        const hasLocal = !!useProjectStore.getState().getProjectById(projectId);
        if (isNotFound && !hasLocal) {
          setNotFound(true);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [projectId]);

  if (notFound) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-6 text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] text-[var(--text-secondary)]">
          <Search className="size-7" aria-label="프로젝트를 찾을 수 없음" />
        </div>
        <div className="space-y-2">
          <h1 className="text-2xl font-[900] tracking-tight text-[var(--text-primary)]">
            프로젝트를 찾을 수 없습니다
          </h1>
          <p className="max-w-md text-sm leading-relaxed text-[var(--text-secondary)]">
            요청하신 프로젝트가 존재하지 않거나 접근 권한이 없습니다. 주소를 다시 확인하거나
            프로젝트 목록에서 선택해 주세요.
          </p>
          <p className="text-[11px] font-mono text-[var(--text-hint)]">ID: {projectId}</p>
        </div>
        <Link
          href={`/${locale}/projects`}
          className="rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-5 py-2.5 text-sm font-bold text-[var(--accent-strong)] transition-colors hover:bg-[var(--accent-strong)] hover:text-white"
        >
          프로젝트 목록으로
        </Link>
      </div>
    );
  }

  return <>{children}</>;
}
