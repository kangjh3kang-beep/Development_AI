import { Card, CardContent, CardHeader, CardTitle } from "@propai/ui";
import type { EscrowSnapshot, EscrowState } from "@/mocks/module-data";

type EscrowCardProps = {
  locale: string;
  snapshot: EscrowSnapshot;
  labels: {
    title: string;
    description: string;
    balanceLabel: string;
    feeLabel: string;
    expiresAtLabel: string;
    milestoneLabel: string;
    subcontractorLabel: string;
    contractLabel: string;
    txLabel: string;
    eventsTitle: string;
    stateLabels: Record<EscrowState, string>;
  };
};

function formatCurrency(locale: string, amount: number) {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
  }).format(amount);
}

function formatDate(locale: string, value: string) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function EscrowCard({ locale, snapshot, labels }: EscrowCardProps) {
  return (
    <Card className="bg-[var(--surface-strong)]">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle>{labels.title}</CardTitle>
            <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
              {labels.description}
            </p>
          </div>
          <span className="rounded-full bg-[var(--surface-soft)] px-4 py-2 text-sm font-medium text-[var(--text-primary)]">
            {labels.stateLabels[snapshot.state]}
          </span>
        </div>
      </CardHeader>
      <CardContent className="grid gap-5 pt-0 xl:grid-cols-[1.05fr_0.95fr]">
        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.balanceLabel}
            </p>
            <p className="mt-3 text-lg font-semibold text-[var(--text-primary)]">
              {formatCurrency(locale, snapshot.balance)}
            </p>
          </div>
          <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.feeLabel}
            </p>
            <p className="mt-3 text-lg font-semibold text-[var(--text-primary)]">
              {snapshot.feeBps / 100}%
            </p>
          </div>
          <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.expiresAtLabel}
            </p>
            <p className="mt-3 text-sm font-medium text-[var(--text-secondary)]">
              {formatDate(locale, snapshot.expiresAt)}
            </p>
          </div>
          <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.subcontractorLabel}
            </p>
            <p className="mt-3 text-sm font-medium text-[var(--text-secondary)]">
              {snapshot.subcontractor}
            </p>
          </div>
          <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4 md:col-span-2">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.milestoneLabel}
            </p>
            <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
              {snapshot.milestone}
            </p>
          </div>
          <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4 md:col-span-2">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.contractLabel}
            </p>
            <p className="mt-3 font-mono text-sm text-[var(--text-secondary)]">
              {snapshot.contractAddress}
            </p>
          </div>
          <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4 md:col-span-2">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.txLabel}
            </p>
            <a
              href={`https://amoy.polygonscan.com/tx/${snapshot.transactionHash}`}
              target="_blank"
              rel="noreferrer"
              className="mt-3 inline-flex font-mono text-sm text-[var(--accent-strong)] underline underline-offset-4"
            >
              {snapshot.transactionHash}
            </a>
          </div>
        </div>
        <div className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-soft)] px-5 py-5">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
            {labels.eventsTitle}
          </p>
          <ol className="mt-4 grid gap-3">
            {snapshot.events.map((event, index) => (
              <li
                key={event.id}
                className="rounded-[1.15rem] border border-[var(--line)] bg-white px-4 py-4"
              >
                <div className="flex items-center gap-3">
                  <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--foreground)] text-xs font-semibold text-[#ffffff]">
                    {index + 1}
                  </span>
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    {event.title}
                  </p>
                </div>
                <p className="mt-3 text-xs text-[var(--text-tertiary)]">
                  {formatDate(locale, event.time)}
                </p>
              </li>
            ))}
          </ol>
        </div>
      </CardContent>
    </Card>
  );
}
