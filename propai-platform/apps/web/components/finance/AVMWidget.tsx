import { Card, CardContent, CardHeader, CardTitle } from "@propai/ui";
import type { AvmSnapshot } from "@/mocks/module-data";

type AVMWidgetProps = {
  locale: string;
  snapshot: AvmSnapshot;
  labels: {
    title: string;
    estimateLabel: string;
    changeRateLabel: string;
    confidenceLabel: string;
    comparablesTitle: string;
  };
};

function formatCurrency(locale: string, amount: number) {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
  }).format(amount);
}

export function AVMWidget({ locale, snapshot, labels }: AVMWidgetProps) {
  return (
    <Card className="bg-[var(--surface-strong)]">
      <CardHeader>
        <CardTitle>{labels.title}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 pt-0">
        <div className="grid gap-3 md:grid-cols-3">
          <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 py-4">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-hint)]">
              {labels.estimateLabel}
            </p>
            <p className="mt-3 text-xl font-semibold text-[var(--text-primary)]">
              {formatCurrency(locale, snapshot.estimate)}
            </p>
          </div>
          <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 py-4">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-hint)]">
              {labels.changeRateLabel}
            </p>
            <p className="mt-3 text-xl font-semibold text-[var(--accent-strong)]">
              {snapshot.changeRate}
            </p>
          </div>
          <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 py-4">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-hint)]">
              {labels.confidenceLabel}
            </p>
            <p className="mt-3 text-xl font-semibold text-[var(--text-primary)]">
              {snapshot.confidence}
            </p>
          </div>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-hint)]">
            {labels.comparablesTitle}
          </p>
          <div className="mt-3 grid gap-3">
            {snapshot.comparables.map((item) => (
              <div
                key={item.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 py-4"
              >
                <div>
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    {item.title}
                  </p>
                  <p className="mt-1 text-xs text-[var(--text-tertiary)]">
                    {item.distance}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-semibold text-[var(--text-secondary)]">
                    {formatCurrency(locale, item.amount)}
                  </p>
                  <p className="mt-1 text-xs text-[var(--accent-strong)]">
                    {item.change}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
