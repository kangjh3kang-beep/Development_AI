"use client";

type WorkspaceQueryErrorCardProps = {
  title: string;
  description: string;
  message: string;
  actionLabel: string;
  onRetry: () => void;
};

export function WorkspaceQueryErrorCard({
  title,
  description,
  message,
  actionLabel,
  onRetry,
}: WorkspaceQueryErrorCardProps) {
  return (
    <div
      className="rounded-[var(--radius-xl)] border border-[var(--warning)]/20 bg-[var(--warning-soft)] p-5"
      role="alert"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-[var(--text-primary)]">{title}</p>
          <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
            {description}
          </p>
          <p className="mt-3 text-sm leading-7 text-[var(--spot)]">{message}</p>
        </div>
        <button
          type="button"
          onClick={onRetry}
          className="rounded-full border border-[var(--line)] bg-white px-4 py-2 text-sm font-medium text-[var(--text-primary)] transition hover:border-[var(--accent)] hover:text-[var(--accent-strong)]"
        >
          {actionLabel}
        </button>
      </div>
    </div>
  );
}
