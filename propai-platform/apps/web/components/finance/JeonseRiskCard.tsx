import { Card, CardContent, CardHeader, CardTitle } from "@propai/ui";
import type { JeonseRiskSnapshot, RiskLevel } from "@/mocks/module-data";

type JeonseRiskCardProps = {
  snapshot: JeonseRiskSnapshot;
  labels: {
    title: string;
    scoreLabel: string;
    summaryLabel: string;
    factorsTitle: string;
    factorLabels: Record<RiskLevel, string>;
  };
};

const riskColorClassName: Record<RiskLevel, string> = {
  stable: "bg-[rgba(14,116,144,0.12)] text-[var(--accent-strong)]",
  watch: "bg-[rgba(217,119,6,0.14)] text-[var(--spot)]",
  warning: "bg-[var(--surface-muted)] text-[var(--text-primary)]",
};

export function JeonseRiskCard({
  snapshot,
  labels,
}: JeonseRiskCardProps) {
  return (
    <Card className="bg-[var(--surface-strong)]">
      <CardHeader>
        <CardTitle>{labels.title}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 pt-0">
        <div className="grid gap-4 md:grid-cols-[0.65fr_1.35fr]">
          <div className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface)] p-5">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-hint)]">
              {labels.scoreLabel}
            </p>
            <div className="mt-4 flex h-28 w-28 items-center justify-center rounded-full bg-[rgba(14,116,144,0.12)] text-center">
              <div>
                <p className="text-3xl font-semibold text-[var(--text-primary)]">
                  {snapshot.score}
                </p>
                <p className="mt-1 text-xs font-medium text-[var(--text-tertiary)]">
                  {snapshot.grade}
                </p>
              </div>
            </div>
          </div>
          <div className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface)] p-5">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-hint)]">
              {labels.summaryLabel}
            </p>
            <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
              {snapshot.summary}
            </p>
          </div>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-hint)]">
            {labels.factorsTitle}
          </p>
          <ul className="mt-3 grid gap-3">
            {(snapshot.factors ?? []).map((factor) => (
              <li
                key={factor.id}
                className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 py-4"
              >
                <div className="flex flex-wrap items-center gap-3">
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    {factor.label}
                  </p>
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-medium ${riskColorClassName[factor.level]}`}
                  >
                    {labels.factorLabels[factor.level]}
                  </span>
                </div>
                <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                  {factor.detail}
                </p>
              </li>
            ))}
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}
