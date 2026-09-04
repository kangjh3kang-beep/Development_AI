"use client";

import { useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@propai/ui";
import type { DroneSeverity, DroneSnapshot } from "@/mocks/module-data";

type DefectHeatmapProps = {
  locale: string;
  snapshot: DroneSnapshot;
  labels: {
    title: string;
    description: string;
    capturedAtLabel: string;
    completionLabel: string;
    riskSummaryLabel: string;
    legendTitle: string;
    defectsTitle: string;
    severityLabels: Record<DroneSeverity, string>;
  };
};

const severityColor = {
  low: "#0e7490",
  medium: "#d97706",
  high: "#b91c1c",
} as const;

function formatDate(locale: string, value: string) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function DefectHeatmap({
  locale,
  snapshot,
  labels,
}: DefectHeatmapProps) {
  const [selectedDefectId, setSelectedDefectId] = useState(
    snapshot.defects[0]?.id ?? "",
  );

  const selectedDefect = useMemo(
    () =>
      (snapshot.defects ?? []).find((defect) => defect.id === selectedDefectId) ??
      snapshot.defects[0],
    [selectedDefectId, snapshot.defects],
  );

  if (!selectedDefect) {
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
      <CardContent className="grid gap-5 pt-0 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[linear-gradient(180deg,#fffefb_0%,#f5efe6_100%)] p-4">
          <div className="relative min-h-[340px] overflow-hidden rounded-[var(--radius-md)] border border-[var(--line)] bg-[radial-gradient(circle_at_top,rgba(14,116,144,0.12),transparent_28%),linear-gradient(180deg,#ffffff_0%,#f4ede4_100%)]">
            <div className="absolute inset-0 bg-[linear-gradient(rgba(19,33,47,0.04)_1px,transparent_1px),linear-gradient(90deg,rgba(19,33,47,0.04)_1px,transparent_1px)] bg-[size:40px_40px]" />
            <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100">
              {(snapshot.defects ?? []).map((defect) => (
                <g key={defect.id}>
                  <circle
                    cx={defect.x}
                    cy={defect.y}
                    r={defect.severity === "high" ? 8 : defect.severity === "medium" ? 6 : 5}
                    fill={severityColor[defect.severity]}
                    fillOpacity={selectedDefect.id === defect.id ? 0.88 : 0.52}
                    stroke="#ffffff"
                    strokeWidth="1.5"
                    onClick={() => setSelectedDefectId(defect.id)}
                  />
                  <circle
                    cx={defect.x}
                    cy={defect.y}
                    r={defect.severity === "high" ? 14 : defect.severity === "medium" ? 11 : 9}
                    fill={severityColor[defect.severity]}
                    fillOpacity="0.12"
                  />
                </g>
              ))}
            </svg>
          </div>
        </div>
        <div className="grid gap-4">
          <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-1">
            <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4">
              <p className="label-caps text-[var(--text-tertiary)]">
                {labels.capturedAtLabel}
              </p>
              <p className="mt-3 text-sm font-medium text-[var(--text-secondary)]">
                {formatDate(locale, snapshot.capturedAt)}
              </p>
            </div>
            <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4">
              <p className="label-caps text-[var(--text-tertiary)]">
                {labels.completionLabel}
              </p>
              <p className="mt-3 text-lg font-semibold text-[var(--text-primary)]">
                {snapshot.completionRate}
              </p>
            </div>
            <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4">
              <p className="label-caps text-[var(--text-tertiary)]">
                {labels.riskSummaryLabel}
              </p>
              <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                {snapshot.riskSummary}
              </p>
            </div>
          </div>
          <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4">
            <p className="label-caps text-[var(--text-tertiary)]">
              {labels.legendTitle}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {(Object.keys(labels.severityLabels) as DroneSeverity[]).map(
                (severity) => (
                  <span
                    key={severity}
                    className="inline-flex items-center gap-2 rounded-full border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-xs font-medium text-[var(--text-secondary)]"
                  >
                    <span
                      className="h-2.5 w-2.5 rounded-full"
                      style={{ backgroundColor: severityColor[severity] }}
                    />
                    {labels.severityLabels[severity]}
                  </span>
                ),
              )}
            </div>
          </div>
          <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4">
            <p className="label-caps text-[var(--text-tertiary)]">
              {labels.defectsTitle}
            </p>
            <ul className="mt-3 grid gap-3">
              {(snapshot.defects ?? []).map((defect) => (
                <li key={defect.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedDefectId(defect.id)}
                    className={`w-full rounded-[var(--radius-md)] border px-4 py-3 text-left ${
                      selectedDefect.id === defect.id
                        ? "border-[var(--text-primary)] bg-white"
                        : "border-[var(--line)] bg-[rgba(255,255,255,0.85)]"
                    }`}
                  >
                    <div className="flex flex-wrap items-center gap-3">
                      <p className="text-sm font-semibold text-[var(--text-primary)]">
                        {defect.title}
                      </p>
                      <span className="rounded-full bg-[var(--surface-muted)] px-3 py-1 text-xs font-medium text-[var(--text-secondary)]">
                        {labels.severityLabels[defect.severity]}
                      </span>
                    </div>
                    <p className="mt-2 text-xs text-[var(--text-tertiary)]">
                      {defect.zone} · {defect.confidence}%
                    </p>
                    <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                      {defect.detail}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
