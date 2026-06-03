"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiClient } from "@/lib/api-client";

type Project = {
  id: string;
  name: string;
  status: string;
  address?: string;
  total_area?: number;
  profit_rate?: number;
  npv?: number;
  type?: string;
};

type ProjectsResponse = {
  projects: Project[];
};

function fmt(n: number): string {
  return new Intl.NumberFormat("ko-KR").format(Math.round(n));
}

function fmtBillion(n: number): string {
  if (n >= 1_000_000_000_000) {
    return `${(n / 1_000_000_000_000).toFixed(1)}조`;
  }
  if (n >= 100_000_000) {
    return `${(n / 100_000_000).toFixed(0)}억`;
  }
  return fmt(n);
}

const STATUS_COLORS: Record<string, string> = {
  "진행중": "bg-blue-500/10 text-blue-500 border-blue-500/20",
  "검토중": "bg-amber-500/10 text-amber-500 border-amber-500/20",
  "완료": "bg-emerald-500/10 text-emerald-500 border-emerald-500/20",
  "중단": "bg-red-500/10 text-red-500 border-red-500/20",
};

export default function AiPortfolioPage() {
  const { locale } = useParams() as { locale: string };
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function fetchProjects() {
      try {
        const res = await apiClient.get<ProjectsResponse | Project[]>("/projects");
        if (cancelled) return;

        // 백엔드 PaginatedResponse는 items, 일부 mock은 projects — 둘 다 수용
        const list = Array.isArray(res)
          ? res
          : ((res as { items?: Project[] }).items ?? (res as ProjectsResponse).projects ?? []);
        setProjects(
          list.map((p: any) => ({
            id: p.id ?? p.project_id ?? "",
            name: p.name ?? p.project_name ?? "Untitled",
            status: p.status ?? "진행중",
            address: p.address ?? p.location ?? "",
            total_area: p.total_area ?? p.area ?? 0,
            profit_rate: p.profit_rate ?? p.roi ?? 0,
            npv: p.npv ?? p.net_present_value ?? 0,
            type: p.type ?? p.tag ?? "CORE",
          })),
        );
      } catch {
        if (!cancelled) setError(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchProjects();
    return () => { cancelled = true; };
  }, []);

  const totalNpv = projects.reduce((sum, p) => sum + (p.npv ?? 0), 0);
  const activeCount = projects.filter((p) => p.status !== "완료" && p.status !== "중단").length;
  const atRiskCount = projects.filter((p) => p.status === "중단").length;
  const avgProfitRate = projects.length > 0
    ? projects.reduce((sum, p) => sum + (p.profit_rate ?? 0), 0) / projects.length
    : 0;

  return (
    <div className="flex flex-col gap-6">
      <header className="rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface)] p-8 shadow-sm">
        <p className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)]">
          Portfolio
        </p>
        <h1 className="mt-2 text-3xl font-black tracking-tight text-[var(--text-primary)]">
          AI 포트폴리오 맵 (Portfolio Map)
        </h1>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">
          전국 주요 입지에 진행 중인 자산 포트폴리오의 실시간 상태 및 예상 NPV 총합을 모니터링합니다.
        </p>
      </header>

      {/* Summary Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-[var(--radius-xl)] bg-[var(--accent-strong)] p-6 shadow-[var(--shadow-xl)]">
          <p className="text-xs font-bold uppercase tracking-widest text-white/60">총 예상 순현재가치 (Total NPV)</p>
          <p className="mt-2 text-3xl font-black text-white">
            {loading ? (
              <span className="inline-block h-9 w-40 animate-pulse rounded-lg bg-white/20" />
            ) : totalNpv > 0 ? (
              `${fmtBillion(totalNpv)} 원`
            ) : (
              "데이터 수집 중"
            )}
          </p>
        </div>

        <div className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface)] p-6 shadow-[var(--shadow-sm)]">
          <p className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)]">활성화된 프로젝트</p>
          <p className="mt-2 text-3xl font-black text-[var(--text-primary)]">
            {loading ? (
              <span className="inline-block h-9 w-20 animate-pulse rounded-lg bg-[var(--surface-soft)]" />
            ) : (
              `${activeCount}개 현장`
            )}
          </p>
        </div>

        <div className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface)] p-6 shadow-[var(--shadow-sm)]">
          <p className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)]">평균 수익률</p>
          <p className="mt-2 text-3xl font-black text-[var(--text-primary)]">
            {loading ? (
              <span className="inline-block h-9 w-20 animate-pulse rounded-lg bg-[var(--surface-soft)]" />
            ) : (
              `${avgProfitRate.toFixed(1)}%`
            )}
          </p>
        </div>

        <div className="rounded-[var(--radius-xl)] border border-[var(--error)]/20 bg-[var(--error-soft)] p-6 shadow-[var(--shadow-sm)]">
          <p className="text-xs font-bold uppercase tracking-widest text-[var(--error)]">리스크 감지 (At Risk)</p>
          <p className="mt-2 text-3xl font-black text-[var(--error)]">
            {loading ? (
              <span className="inline-block h-9 w-20 animate-pulse rounded-lg bg-[var(--error)]/10" />
            ) : (
              `${atRiskCount}개 현장`
            )}
          </p>
        </div>
      </div>

      {/* Project List */}
      {loading ? (
        <div className="space-y-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-28 animate-pulse rounded-2xl bg-[var(--surface-soft)] border border-[var(--line)]" />
          ))}
        </div>
      ) : error && projects.length === 0 ? (
        <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-12 text-center">
          <p className="text-sm font-medium text-[var(--text-secondary)]">
            프로젝트 데이터를 불러올 수 없습니다. 백엔드 API 연결을 확인해 주세요.
          </p>
        </div>
      ) : projects.length === 0 ? (
        <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-12 text-center">
          <p className="text-sm font-medium text-[var(--text-secondary)]">
            등록된 프로젝트가 없습니다. 새 프로젝트를 생성해 보세요.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <a
              key={project.id}
              href={`/${locale}/projects/${project.id}`}
              className="group rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-6 transition-all hover:shadow-[var(--shadow-lg)] hover:border-[var(--accent-strong)]/30 hover:-translate-y-1"
            >
              <div className="flex items-start justify-between mb-4">
                <span className={`rounded-lg border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider ${STATUS_COLORS[project.status] ?? "bg-[var(--surface-muted)] text-[var(--text-secondary)] border-[var(--line)]"}`}>
                  {project.status}
                </span>
                <span className="rounded-md bg-[var(--surface-muted)] px-2 py-0.5 text-[10px] font-bold text-[var(--text-hint)] uppercase">
                  {project.type}
                </span>
              </div>

              <h3 className="text-base font-bold text-[var(--text-primary)] leading-tight mb-2 group-hover:text-[var(--accent-strong)] transition-colors">
                {project.name}
              </h3>

              {project.address && (
                <p className="text-xs text-[var(--text-secondary)] mb-4 truncate">
                  {project.address}
                </p>
              )}

              <div className="grid grid-cols-2 gap-3 pt-4 border-t border-[var(--line)]">
                {(project.total_area ?? 0) > 0 && (
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-hint)]">면적</p>
                    <p className="text-sm font-bold text-[var(--text-primary)]">{fmt(project.total_area!)} m2</p>
                  </div>
                )}
                {(project.profit_rate ?? 0) > 0 && (
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-hint)]">수익률</p>
                    <p className="text-sm font-bold text-[var(--accent-strong)]">{project.profit_rate!.toFixed(1)}%</p>
                  </div>
                )}
                {(project.npv ?? 0) > 0 && (
                  <div className="col-span-2">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-hint)]">NPV</p>
                    <p className="text-sm font-bold text-[var(--text-primary)]">{fmtBillion(project.npv!)} 원</p>
                  </div>
                )}
              </div>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
