"use client";

import { startTransition, useState } from "react";
import { Button, Card, CardContent, CardHeader, CardTitle } from "@propai/ui";
import type {
  AgentConnectionStatus,
  AgentSnapshot,
  AgentStepStatus,
} from "@/mocks/module-data";

type AgentTimelineProps = {
  locale: string;
  snapshot: AgentSnapshot;
  labels: {
    title: string;
    description: string;
    connectionTitle: string;
    reconnectLabel: string;
    updatedAtLabel: string;
    connectionLabels: Record<AgentConnectionStatus, string>;
    statusLabels: Record<AgentStepStatus, string>;
  };
};

function formatDate(locale: string, value: string) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function AgentTimeline({
  locale,
  snapshot,
  labels,
}: AgentTimelineProps) {
  const [connection, setConnection] = useState(snapshot.connection);

  const simulateReconnect = () => {
    startTransition(() => {
      setConnection("reconnecting");
    });

    window.setTimeout(() => {
      setConnection("connected");
    }, 900);
  };

  return (
    <Card className="bg-[var(--surface-strong)]">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle>{labels.title}</CardTitle>
            <p className="mt-2 text-sm leading-7 text-[rgba(19,33,47,0.72)]">
              {labels.description}
            </p>
          </div>
          <Button variant="secondary" onClick={simulateReconnect}>
            {labels.reconnectLabel}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="grid gap-5 pt-0 xl:grid-cols-[0.95fr_1.05fr]">
        <div className="rounded-[1.5rem] border border-[var(--line)] bg-[var(--surface-soft)] px-5 py-5">
          <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.54)]">
            {labels.connectionTitle}
          </p>
          <p className="mt-3 text-lg font-semibold text-[var(--foreground)]">
            {labels.connectionLabels[connection]}
          </p>
          <p className="mt-2 text-sm text-[rgba(19,33,47,0.64)]">
            {labels.updatedAtLabel}: {formatDate(locale, snapshot.lastEventAt)}
          </p>
        </div>
        <ol className="grid gap-4">
          {snapshot.stages.map((stage, index) => (
            <li
              key={stage.id}
              className="grid gap-3 rounded-[1.35rem] border border-[var(--line)] bg-[var(--surface-soft)] px-5 py-4 md:grid-cols-[auto_1fr]"
            >
              <div className="flex items-start gap-3">
                <span
                  className={`mt-1 flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold ${
                    stage.status === "completed"
                      ? "bg-[var(--accent)] text-[#ffffff]"
                      : stage.status === "active"
                        ? "bg-[var(--spot)] text-[#ffffff]"
                        : "bg-[var(--surface-muted)] text-[var(--foreground)]"
                  }`}
                >
                  {index + 1}
                </span>
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-3">
                  <p className="text-sm font-semibold text-[var(--foreground)]">
                    {stage.title}
                  </p>
                  <span className="rounded-full bg-[#ffffff] px-3 py-1 text-xs font-medium text-[rgba(19,33,47,0.72)]">
                    {labels.statusLabels[stage.status]}
                  </span>
                </div>
                <p className="mt-3 text-sm leading-7 text-[rgba(19,33,47,0.76)]">
                  {stage.detail}
                </p>
                <p className="mt-3 text-xs text-[rgba(19,33,47,0.56)]">
                  {labels.updatedAtLabel}: {formatDate(locale, stage.updatedAt)}
                </p>
              </div>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}
