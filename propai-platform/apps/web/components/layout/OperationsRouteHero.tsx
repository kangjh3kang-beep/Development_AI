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
    <Card className="rounded-[2rem] bg-[var(--surface-strong)] shadow-[0_20px_60px_rgba(19,33,47,0.08)]">
      <CardContent className="p-8">
        <div className="flex flex-wrap items-center gap-3">
          <span className="rounded-full bg-[rgba(14,116,144,0.1)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--accent-strong)]">
            {eyebrow}
          </span>
          <span className="rounded-full border border-[var(--line)] px-4 py-2 text-xs font-medium text-[rgba(19,33,47,0.7)]">
            {localeLabel}
          </span>
          <span className="rounded-full bg-[rgba(13,148,136,0.12)] px-4 py-2 text-xs font-medium text-[rgb(15,118,110)]">
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
          <Card className="rounded-[1.5rem] bg-[var(--surface-soft)] shadow-none">
            <CardContent className="p-5">
              <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.58)]">
                Live Scope
              </p>
              <ul className="mt-4 grid gap-3">
                {items.map((item) => (
                  <li
                    key={item}
                    className="rounded-2xl bg-[rgba(19,33,47,0.04)] px-4 py-3 text-sm leading-7 text-[rgba(19,33,47,0.78)]"
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
