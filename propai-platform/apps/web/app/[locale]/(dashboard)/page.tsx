import Link from "next/link";
import { DashboardClientPanel } from "@/components/dashboard/DashboardClientPanel";
import { OverviewCard } from "@/components/layout/OverviewCard";
import { PwaStatusCard } from "@/components/pwa/PwaStatusCard";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type DashboardPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function DashboardPage({ params }: DashboardPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  const dictionary = await getDictionary(locale as Locale);
  const approvalsLabel =
    (dictionary.nav as { approvals?: string }).approvals ?? "Approval Ops";

  const cards = [
    {
      href: `/${locale}/tax`,
      title: dictionary.nav.tax,
      description: "Calculate project-linked tax scenarios through the live tax API.",
    },
    {
      href: `/${locale}/auction`,
      title: dictionary.nav.auction,
      description:
        "Validate auction analysis, contractor matching, and chatbot queries through live APIs.",
    },
    {
      href: `/${locale}/maintenance`,
      title: "Maintenance",
      description:
        "Jump into the live maintenance, tenant-signal, and asset-intelligence chain.",
    },
    {
      href: `/${locale}/approvals`,
      title: approvalsLabel,
      description:
        "Review tenant-wide approval queues, resolved decisions, and batch actions from one live control surface.",
    },
  ];

  return (
    <section className="grid gap-6">
      <div className="rounded-[2rem] border border-[var(--line)] bg-[var(--surface-strong)] p-8 shadow-[0_20px_60px_rgba(19,33,47,0.08)]">
        <p className="text-xs uppercase tracking-[0.3em] text-[rgba(19,33,47,0.74)]">
          {dictionary.hero.badge}
        </p>
        <h2 className="mt-3 text-3xl font-bold md:text-4xl">
          {dictionary.dashboard.title}
        </h2>
        <p className="mt-4 max-w-3xl text-sm leading-7 text-[rgba(19,33,47,0.72)] md:text-base">
          {dictionary.dashboard.description}
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link
            href={`/${locale}/projects`}
            className="rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-5 py-3 text-sm font-semibold text-[var(--foreground)] shadow-[0_8px_20px_rgba(19,33,47,0.08)]"
          >
            {dictionary.nav.projects}
          </Link>
          <Link
            href={`/${locale}/auction`}
            className="rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-5 py-3 text-sm font-semibold"
          >
            {dictionary.nav.auction}
          </Link>
        </div>
      </div>
      <DashboardClientPanel
        locale={locale}
        summaryTitle={dictionary.dashboard.summaryTitle}
        labels={dictionary.workspace}
      />
      <PwaStatusCard labels={dictionary.pwa} />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {cards.map((card) => (
          <OverviewCard key={card.href} {...card} />
        ))}
      </div>
    </section>
  );
}
