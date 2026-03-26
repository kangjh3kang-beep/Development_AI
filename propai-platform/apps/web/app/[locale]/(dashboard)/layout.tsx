import Link from "next/link";
import { LocaleSwitcher } from "@/components/ui/LocaleSwitcher";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type DashboardLayoutProps = Readonly<{
  children: React.ReactNode;
  params: Promise<{
    locale: string;
  }>;
}>;

export default async function DashboardLayout({
  children,
  params,
}: DashboardLayoutProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return children;
  }

  const dictionary = await getDictionary(locale as Locale);
  const approvalsLabel =
    (dictionary.nav as { approvals?: string }).approvals ?? "Approval Ops";
  const runtimeModeLabel =
    process.env.NEXT_PUBLIC_USE_MOCKS === "false"
      ? dictionary.workspace.modeLive
      : dictionary.workspace.modeMock;

  const navigation = [
    { href: `/${locale}`, label: dictionary.nav.dashboard },
    { href: `/${locale}/projects`, label: dictionary.nav.projects },
    { href: `/${locale}/tax`, label: dictionary.nav.tax },
    { href: `/${locale}/auction`, label: dictionary.nav.auction },
    { href: `/${locale}/agent`, label: dictionary.nav.agent },
    { href: `/${locale}/inspection`, label: dictionary.nav.inspection },
    { href: `/${locale}/maintenance`, label: "Maintenance" },
    { href: `/${locale}/tenant`, label: "Tenant" },
    { href: `/${locale}/digital-twin`, label: "Digital Twin" },
  ];

  const analyticsNavigation = [
    { href: `/${locale}/analytics/investment`, label: "Investment/AVM" },
    { href: `/${locale}/analytics/iot`, label: "IoT/Proptech" },
    { href: `/${locale}/analytics/esg`, label: "ESG/Climate" },
    { href: `/${locale}/analytics/cost`, label: "Cost/PPI" },
  ];

  const operationsNavigation = [
    { href: `/${locale}/approvals`, label: approvalsLabel },
    { href: `/${locale}/safety`, label: "Safety/Vision AI" },
    { href: `/${locale}/webrtc`, label: "Remote Supervision" },
    { href: `/${locale}/sre`, label: "SRE Admin" },
  ];

  return (
    <div className="mx-auto flex min-h-screen max-w-7xl flex-col gap-6 px-4 py-4 md:px-6">
      <header className="rounded-[1.75rem] border border-[var(--line)] bg-[var(--surface)] px-5 py-4 shadow-[0_20px_60px_rgba(19,33,47,0.08)] md:px-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-[rgba(19,33,47,0.72)]">
              PropAI Workspace
            </p>
            <h1 className="mt-2 text-2xl font-bold text-[var(--foreground)]">
              {dictionary.meta.siteName}
            </h1>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-[var(--surface-soft)] px-4 py-2 text-sm font-medium text-[var(--accent-strong)]">
              {runtimeModeLabel}
            </span>
            <LocaleSwitcher
              currentLocale={locale as Locale}
              label={dictionary.nav.locale}
            />
          </div>
        </div>
      </header>
      <div className="grid gap-6 md:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="rounded-[1.75rem] border border-[var(--line)] bg-[var(--surface)] p-4 shadow-[0_12px_32px_rgba(19,33,47,0.06)]">
          <nav className="grid gap-2" aria-label="Dashboard navigation">
            {navigation.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="rounded-2xl px-4 py-3 text-sm font-medium text-[rgba(19,33,47,0.82)] transition hover:bg-[var(--surface-soft)] hover:text-[var(--accent-strong)]"
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="my-3 h-px bg-[var(--line)]" aria-hidden="true" />
          <p className="px-4 pb-1 text-[10px] uppercase tracking-widest text-[rgba(19,33,47,0.4)]">
            Analytics
          </p>
          <nav className="grid gap-1" aria-label="Analytics navigation">
            {analyticsNavigation.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="rounded-2xl px-4 py-2.5 text-sm font-medium text-[rgba(19,33,47,0.72)] transition hover:bg-[var(--surface-soft)] hover:text-[var(--accent-strong)]"
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="my-3 h-px bg-[var(--line)]" aria-hidden="true" />
          <p className="px-4 pb-1 text-[10px] uppercase tracking-widest text-[rgba(19,33,47,0.4)]">
            Operations
          </p>
          <nav className="grid gap-1" aria-label="Operations navigation">
            {operationsNavigation.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="rounded-2xl px-4 py-2.5 text-sm font-medium text-[rgba(19,33,47,0.72)] transition hover:bg-[var(--surface-soft)] hover:text-[var(--accent-strong)]"
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </aside>
        <div className="min-w-0">{children}</div>
      </div>
    </div>
  );
}
