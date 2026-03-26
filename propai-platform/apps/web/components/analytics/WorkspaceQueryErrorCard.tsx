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
      className="rounded-[1.5rem] border border-[rgba(217,119,6,0.24)] bg-[rgba(255,247,237,0.92)] p-5"
      role="alert"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-[var(--foreground)]">{title}</p>
          <p className="mt-2 text-sm leading-7 text-[rgba(19,33,47,0.68)]">
            {description}
          </p>
          <p className="mt-3 text-sm leading-7 text-[var(--spot)]">{message}</p>
        </div>
        <button
          type="button"
          onClick={onRetry}
          className="rounded-full border border-[var(--line)] bg-white px-4 py-2 text-sm font-medium text-[var(--foreground)] transition hover:border-[var(--accent)] hover:text-[var(--accent-strong)]"
        >
          {actionLabel}
        </button>
      </div>
    </div>
  );
}
