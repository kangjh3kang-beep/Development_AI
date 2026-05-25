"use client";

import { useMemo, useState, useTransition } from "react";
import { Button, Card, CardContent, CardHeader, CardTitle } from "@propai/ui";
import type { FloorPlanDraft, FloorPlanStatus } from "@/mocks/module-data";

type FloorPlanGeneratorProps = {
  plans: FloorPlanDraft[];
  selectedPlanId: string;
  onSelectPlan: (planId: string) => void;
  labels: {
    title: string;
    description: string;
    promptLabel: string;
    uploadLabel: string;
    generateLabel: string;
    referenceIdle: string;
    referenceReady: string;
    optionsTitle: string;
    statusLabels: Record<FloorPlanStatus, string>;
  };
};

export function FloorPlanGenerator({
  plans,
  selectedPlanId,
  onSelectPlan,
  labels,
}: FloorPlanGeneratorProps) {
  const [prompt, setPrompt] = useState(plans[0]?.prompt ?? "");
  const [referenceName, setReferenceName] = useState("");
  const [isPending, startTransition] = useTransition();

  const selectedPlan = useMemo(
    () => plans.find((plan) => plan.id === selectedPlanId) ?? plans[0],
    [plans, selectedPlanId],
  );

  if (!selectedPlan) {
    return null;
  }

  return (
    <Card className="bg-[var(--surface-strong)]">
      <CardHeader>
        <CardTitle>{labels.title}</CardTitle>
        <p className="text-sm leading-7 text-[var(--text-secondary)]">
          {labels.description}
        </p>
      </CardHeader>
      <CardContent className="grid gap-5 pt-0">
        <label className="grid gap-2 text-sm font-medium text-[var(--text-secondary)]">
          {labels.promptLabel}
          <textarea
            className="min-h-[140px] rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--text-primary)] outline-none"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
          />
        </label>
        <label className="grid gap-2 text-sm font-medium text-[var(--text-secondary)]">
          {labels.uploadLabel}
          <input
            className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--text-secondary)]"
            type="file"
            accept="image/*"
            onChange={(event) =>
              setReferenceName(event.target.files?.[0]?.name ?? "")
            }
          />
        </label>
        <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 py-3 text-sm leading-7 text-[var(--text-secondary)]">
          {referenceName
            ? `${labels.referenceReady}: ${referenceName}`
            : labels.referenceIdle}
        </div>
        <Button
          onClick={() => {
            startTransition(() => {
              const normalizedPrompt = prompt.toLowerCase();
              const matchedPlan =
                plans.find((plan) =>
                  normalizedPrompt.includes(plan.name.toLowerCase().split(" ")[0] ?? ""),
                ) ??
                plans.find((plan) =>
                  normalizedPrompt.includes(plan.summary.toLowerCase().slice(0, 4)),
                ) ??
                plans[(plans.findIndex((plan) => plan.id === selectedPlan.id) + 1) % plans.length];

              onSelectPlan(matchedPlan.id);
            });
          }}
          disabled={isPending}
        >
          {isPending ? `${labels.generateLabel}...` : labels.generateLabel}
        </Button>
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-hint)]">
            {labels.optionsTitle}
          </p>
          <div className="mt-3 grid gap-3">
            {plans.map((plan) => (
              <button
                key={plan.id}
                type="button"
                onClick={() => {
                  setPrompt(plan.prompt);
                  onSelectPlan(plan.id);
                }}
                className={`rounded-[var(--radius-md)] border px-4 py-4 text-left transition ${
                  selectedPlanId === plan.id
                    ? "border-[var(--text-primary)] bg-[var(--surface-muted)]"
                    : "border-[var(--line)] bg-[var(--surface)]"
                }`}
              >
                <div className="flex flex-wrap items-center gap-3">
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    {plan.name}
                  </p>
                  <span className="rounded-full bg-[rgba(14,116,144,0.12)] px-3 py-1 text-xs font-medium text-[var(--accent-strong)]">
                    {labels.statusLabels[plan.status]}
                  </span>
                </div>
                <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                  {plan.summary}
                </p>
              </button>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
