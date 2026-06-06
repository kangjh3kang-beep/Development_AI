import Link from "next/link";
import { defaultLocale } from "@/i18n/config";

export const dynamic = "force-static";

export default function OfflinePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col justify-center gap-6 px-6 py-16" data-testid="offline-shell">
      <div className="rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface)] p-8 shadow-[var(--shadow-lg)]">
        <p className="text-xs uppercase tracking-[0.28em] text-[var(--text-tertiary)]">
          PropAI Offline Shell
        </p>
        <h1 className="mt-3 text-3xl font-bold text-[var(--text-primary)]">
          Offline workspace is ready.
        </h1>
        <p className="mt-4 max-w-2xl text-sm leading-7 text-[var(--text-secondary)]">
          The cached PropAI shell is available, but live API calls still require a
          network connection. Reconnect to resume project analytics, approvals, and
          synchronized field operations.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link
            href={`/${defaultLocale}`}
            className="rounded-full border border-[var(--line)] bg-white px-5 py-3 text-sm font-semibold text-[var(--text-primary)] shadow-[var(--shadow-md)]"
          >
            Open dashboard
          </Link>
          <Link
            href={`/${defaultLocale}/precheck`}
            className="rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-5 py-3 text-sm font-semibold text-[var(--text-primary)]"
          >
            Open precheck workspace
          </Link>
        </div>
      </div>
    </main>
  );
}
