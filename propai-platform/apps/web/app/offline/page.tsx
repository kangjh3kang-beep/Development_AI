import Link from "next/link";
import { defaultLocale } from "@/i18n/config";

export const dynamic = "force-static";

export default function OfflinePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col justify-center gap-6 px-6 py-16">
      <div className="rounded-[2rem] border border-[var(--line)] bg-[var(--surface)] p-8 shadow-[0_20px_60px_rgba(19,33,47,0.08)]">
        <p className="text-xs uppercase tracking-[0.28em] text-[rgba(19,33,47,0.64)]">
          PropAI Offline Shell
        </p>
        <h1 className="mt-3 text-3xl font-bold text-[var(--foreground)]">
          Offline workspace is ready.
        </h1>
        <p className="mt-4 max-w-2xl text-sm leading-7 text-[rgba(19,33,47,0.7)]">
          The cached PropAI shell is available, but live API calls still require a
          network connection. Reconnect to resume project analytics, approvals, and
          synchronized field operations.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link
            href={`/${defaultLocale}`}
            className="rounded-full border border-[var(--line)] bg-[#ffffff] px-5 py-3 text-sm font-semibold text-[var(--foreground)] shadow-[0_8px_20px_rgba(19,33,47,0.08)]"
          >
            Open dashboard
          </Link>
          <Link
            href={`/${defaultLocale}/inspection`}
            className="rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-5 py-3 text-sm font-semibold text-[var(--foreground)]"
          >
            Open inspection workspace
          </Link>
        </div>
      </div>
    </main>
  );
}
