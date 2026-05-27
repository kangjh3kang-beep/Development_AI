import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@propai/ui";

type OperationsRouteHeroProps = {
  eyebrow: string;
  title: string;
  description: string;
  localeLabel: string;
  statusLabel: string;
  items: string[];
};

export function OperationsRouteHero({
  eyebrow,
  title,
  description,
  localeLabel,
  statusLabel,
  items,
}: OperationsRouteHeroProps) {
  return (
    <Card className="rounded-[var(--radius-2xl)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
      <CardContent className="p-8">
        <div className="flex flex-wrap items-center gap-3">
          <span className="rounded-full bg-[rgba(14,116,144,0.1)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--accent-strong)]">
            {eyebrow}
          </span>
          <span className="rounded-full border border-[var(--line)] px-4 py-2 text-xs font-medium text-[var(--text-secondary)]">
            {localeLabel}
          </span>
          <span className="rounded-full bg-[var(--accent-soft)] px-4 py-2 text-xs font-semibold text-[var(--accent-strong)] border border-[var(--accent-strong)]/20">
            {statusLabel}
          </span>
        </div>
        <div className="mt-6 grid gap-6 md:grid-cols-[1.4fr_0.9fr]">
          <CardHeader className="space-y-4 p-0">
            <CardTitle className="text-3xl font-bold md:text-4xl">
              {title}
            </CardTitle>
            <CardDescription className="text-sm leading-8 md:text-base">
              {description}
            </CardDescription>
          </CardHeader>
          <Card className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] shadow-none">
            <CardContent className="p-5">
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                Live Scope
              </p>
              <ul className="mt-4 grid gap-3">
                {items.map((item) => (
                  <li
                    key={item}
                    className="rounded-2xl bg-[var(--surface-muted)]/40 px-4 py-3 text-sm leading-7 text-[var(--text-secondary)]"
                  >
                    {item}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>
      </CardContent>
    </Card>
  );
}
