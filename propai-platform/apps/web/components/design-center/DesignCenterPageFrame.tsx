import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowRight, CheckCircle2, CircleDashed, FolderOpen, Layers3 } from "lucide-react";

import {
  PRIMARY_ROUTE_REGISTRY,
  localizedHref,
  type RouteStatus,
} from "@/lib/navigation/route-registry";

export type DesignCenterMetric = {
  label: string;
  value: string;
  description?: string;
};

type DesignCenterPageFrameProps = {
  locale: string;
  activeId: string;
  title: string;
  description: string;
  eyebrow?: string;
  status?: RouteStatus | "ready";
  statusLabel?: string;
  metrics?: DesignCenterMetric[];
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
};

const STATUS_META: Record<
  RouteStatus | "ready",
  { label: string; className: string; icon: ReactNode }
> = {
  live: {
    label: "운영 중",
    className: "border-[var(--status-success)]/30 bg-[var(--status-success)]/10 text-[var(--status-success)]",
    icon: <CheckCircle2 className="size-3.5" aria-hidden />,
  },
  beta: {
    label: "고도화 중",
    className: "border-[var(--status-info)]/30 bg-[var(--status-info)]/10 text-[var(--status-info)]",
    icon: <CircleDashed className="size-3.5" aria-hidden />,
  },
  placeholder: {
    label: "준비 중",
    className: "border-[var(--status-warning)]/30 bg-[var(--status-warning)]/10 text-[var(--status-warning)]",
    icon: <CircleDashed className="size-3.5" aria-hidden />,
  },
  hidden: {
    label: "숨김",
    className: "border-[var(--line)] bg-[var(--surface-muted)] text-[var(--text-tertiary)]",
    icon: <CircleDashed className="size-3.5" aria-hidden />,
  },
  ready: {
    label: "준비 완료",
    className: "border-[var(--accent-strong)]/25 bg-[var(--accent-soft)] text-[var(--accent-strong)]",
    icon: <CheckCircle2 className="size-3.5" aria-hidden />,
  },
};

function designCenterRoutes(locale: string) {
  return PRIMARY_ROUTE_REGISTRY.filter(
    (item) => item.sectionId === "design-center" && item.status !== "hidden" && item.path,
  )
    .sort((a, b) => a.order - b.order)
    .map((item) => ({
      ...item,
      href: localizedHref(locale, item.path) ?? "#",
    }));
}

export function DesignCenterPageFrame({
  locale,
  activeId,
  title,
  description,
  eyebrow = "설계 센터",
  status = "live",
  statusLabel,
  metrics = [],
  actions,
  children,
  className = "",
}: DesignCenterPageFrameProps) {
  const statusMeta = STATUS_META[status];
  const routes = designCenterRoutes(locale);

  return (
    <div className={`flex min-w-0 flex-col gap-5 pb-20 ${className}`}>
      <header className="border-b border-[var(--line)] pb-5">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="cc-meta text-[var(--accent-strong)]">{eyebrow}</span>
              <span
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-bold ${statusMeta.className}`}
              >
                {statusMeta.icon}
                {statusLabel ?? statusMeta.label}
              </span>
            </div>
            <h1 className="mt-2 text-2xl font-black leading-tight text-[var(--text-primary)] sm:text-3xl">
              {title}
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
              {description}
            </p>
          </div>
          {actions ? <div className="shrink-0">{actions}</div> : null}
        </div>

        {metrics.length > 0 ? (
          <dl className="mt-5 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            {metrics.map((metric) => (
              <div
                key={`${metric.label}-${metric.value}`}
                className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2"
              >
                <dt className="text-[11px] font-semibold text-[var(--text-tertiary)]">
                  {metric.label}
                </dt>
                <dd className="mt-1 truncate text-sm font-black text-[var(--text-primary)]">
                  {metric.value}
                </dd>
                {metric.description ? (
                  <p className="mt-0.5 truncate text-[11px] text-[var(--text-hint)]">
                    {metric.description}
                  </p>
                ) : null}
              </div>
            ))}
          </dl>
        ) : null}
      </header>

      <nav
        aria-label="설계 센터 화면"
        className="flex gap-1 overflow-x-auto rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] p-1"
      >
        {routes.map((route) => {
          const active = route.id === activeId;
          return (
            <Link
              key={route.id}
              href={route.href}
              prefetch={route.prefetch}
              aria-current={active ? "page" : undefined}
              className={[
                "inline-flex min-h-9 shrink-0 items-center gap-2 rounded-md px-3 py-2 text-xs font-bold transition-colors",
                active
                  ? "bg-[var(--surface)] text-[var(--accent-strong)] shadow-[var(--shadow-xs)]"
                  : "text-[var(--text-secondary)] hover:bg-[var(--surface-muted)] hover:text-[var(--text-primary)]",
              ].join(" ")}
            >
              <Layers3 className="size-3.5" aria-hidden />
              <span>{route.label}</span>
            </Link>
          );
        })}
      </nav>

      <main className="min-w-0">{children}</main>
    </div>
  );
}

export function DesignCenterEmptyState({
  title,
  description,
  actionHref,
  actionLabel = "프로젝트 관리로 이동",
}: {
  title: string;
  description: string;
  actionHref: string;
  actionLabel?: string;
}) {
  return (
    <section className="rounded-lg border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] p-8 text-center">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-lg border border-[var(--line)] bg-[var(--surface)] text-[var(--accent-strong)]">
        <FolderOpen className="size-5" aria-hidden />
      </div>
      <h2 className="mt-4 text-base font-black text-[var(--text-primary)]">{title}</h2>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-[var(--text-secondary)]">
        {description}
      </p>
      <Link
        href={actionHref}
        className="mt-5 inline-flex items-center gap-2 rounded-md bg-[var(--accent-strong)] px-4 py-2 text-sm font-bold text-white transition hover:brightness-110"
      >
        {actionLabel}
        <ArrowRight className="size-4" aria-hidden />
      </Link>
    </section>
  );
}
