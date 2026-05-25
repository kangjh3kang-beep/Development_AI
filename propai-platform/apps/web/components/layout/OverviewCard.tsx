import { Card, CardContent } from "@propai/ui";
import Link from "next/link";

type OverviewCardProps = {
  href: string;
  title: string;
  description: string;
};

export function OverviewCard({ href, title, description }: OverviewCardProps) {
  return (
    <Link
      href={href}
      className="transition hover:-translate-y-0.5"
    >
      <Card className="h-full bg-[var(--surface-strong)] hover:bg-[var(--surface-soft)]">
        <CardContent className="p-6">
          <p className="text-xs font-bold uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
            Module
          </p>
          <h3 className="mt-4 text-xl font-semibold text-[var(--text-primary)]">
            {title}
          </h3>
          <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
            {description}
          </p>
        </CardContent>
      </Card>
    </Link>
  );
}
