import type { ReactNode } from "react";

interface WorkspaceShellProps {
  title: string;
  description?: string;
  status?: "live" | "mock" | "loading" | "error";
  statusLabel?: string;
  children: ReactNode;
  headerActions?: ReactNode;
  className?: string;
}

const STATUS_STYLES: Record<
  NonNullable<WorkspaceShellProps["status"]>,
  { dot: string; bg: string; text: string; defaultLabel: string }
> = {
  live: {
    dot: "bg-[var(--status-success)]",
    bg: "bg-[var(--status-success)]/10 border-[var(--status-success)]/20",
    text: "text-[var(--status-success)]",
    defaultLabel: "실연동",
  },
  mock: {
    dot: "bg-[var(--status-warning)]",
    bg: "bg-[var(--status-warning)]/10 border-[var(--status-warning)]/20",
    text: "text-[var(--status-warning)]",
    defaultLabel: "모의",
  },
  loading: {
    dot: "bg-[var(--status-info)] animate-pulse",
    bg: "bg-[var(--status-info)]/10 border-[var(--status-info)]/20",
    text: "text-[var(--status-info)]",
    defaultLabel: "로딩 중",
  },
  error: {
    dot: "bg-[var(--status-error)]",
    bg: "bg-[var(--status-error)]/10 border-[var(--status-error)]/20",
    text: "text-[var(--status-error)]",
    defaultLabel: "오류",
  },
};

export function WorkspaceShell({
  title,
  description,
  status,
  statusLabel,
  children,
  headerActions,
  className = "",
}: WorkspaceShellProps) {
  const statusStyle = status ? STATUS_STYLES[status] : null;

  return (
    <div className={`flex flex-col gap-10 pb-20 ${className}`}>
      {/* Hero Header */}
      <section className="relative overflow-hidden rounded-[2.5rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-10 lg:p-16 shadow-[var(--shadow-lg)] backdrop-blur-2xl">
        {/* Subtle gradient background */}
        <div className="absolute inset-0 bg-gradient-to-br from-[var(--accent-soft)] via-transparent to-transparent opacity-50" />
        <div className="absolute inset-0 bg-[linear-gradient(var(--line-subtle)_1px,transparent_1px),linear-gradient(90deg,var(--line-subtle)_1px,transparent_1px)] bg-[size:32px_32px] opacity-15" />

        <div className="relative z-10 flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-4">
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-3xl font-bold tracking-tighter text-[var(--text-primary)] sm:text-4xl lg:text-5xl">
                {title}
              </h1>
              {statusStyle && (
                <span
                  className={`inline-flex items-center gap-2 rounded-full border px-4 py-1.5 text-[11px] font-bold uppercase tracking-[0.15em] ${statusStyle.bg} ${statusStyle.text}`}
                >
                  <span className={`h-2 w-2 rounded-full ${statusStyle.dot}`} />
                  {statusLabel || statusStyle.defaultLabel}
                </span>
              )}
            </div>
            {description && (
              <p className="max-w-2xl text-base font-medium leading-relaxed text-[var(--text-secondary)]">
                {description}
              </p>
            )}
          </div>
          {headerActions && (
            <div className="flex items-center gap-3 shrink-0">
              {headerActions}
            </div>
          )}
        </div>
      </section>

      {/* Content Area */}
      <div className="w-full">{children}</div>
    </div>
  );
}
