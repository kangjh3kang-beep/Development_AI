"use client";

import { useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@propai/ui";
import type { BimSnapshot } from "@/mocks/module-data";

type BIMViewer3DProps = {
  snapshot: BimSnapshot;
  labels: {
    title: string;
    description: string;
    xrReadyLabel: string;
    xrFallbackLabel: string;
  };
};

export function BIMViewer3D({ snapshot, labels }: BIMViewer3DProps) {
  const [selectedLayerId, setSelectedLayerId] = useState(
    snapshot.layers[0]?.id ?? "",
  );

  const selectedLayer = useMemo(
    () =>
      snapshot.layers.find((layer) => layer.id === selectedLayerId) ??
      snapshot.layers[0],
    [selectedLayerId, snapshot.layers],
  );

  if (!selectedLayer) {
    return null;
  }

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
          <span className="rounded-full bg-[var(--surface-soft)] px-4 py-2 text-sm font-medium text-[var(--foreground)]">
            {snapshot.xrReady ? labels.xrReadyLabel : labels.xrFallbackLabel}
          </span>
        </div>
      </CardHeader>
      <CardContent className="grid gap-5 pt-0 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="rounded-[1.75rem] border border-[var(--line)] bg-[linear-gradient(180deg,#fffaf3_0%,#f1ece3_100%)] p-5">
          <div className="relative min-h-[360px] overflow-hidden rounded-[1.5rem] border border-[var(--line)] bg-[linear-gradient(180deg,#fffcf7_0%,#f4ede4_100%)] [perspective:1400px]">
            <div className="absolute inset-x-0 bottom-0 h-16 bg-[linear-gradient(180deg,rgba(19,33,47,0),rgba(19,33,47,0.08))]" />
            {snapshot.layers.map((layer, index) => (
              <button
                key={layer.id}
                type="button"
                aria-pressed={selectedLayer.id === layer.id}
                onClick={() => setSelectedLayerId(layer.id)}
                className={`absolute left-1/2 w-[58%] -translate-x-1/2 rounded-[1.25rem] border border-white/70 shadow-[0_18px_48px_rgba(19,33,47,0.14)] transition ${
                  selectedLayer.id === layer.id
                    ? "ring-2 ring-[var(--foreground)]"
                    : ""
                }`}
                style={{
                  bottom: `${36 + index * 64}px`,
                  height: `${52 + index * 6}px`,
                  transform:
                    "translateX(-50%) rotateX(58deg) rotateZ(-14deg)",
                  backgroundColor: layer.tint,
                  opacity: selectedLayer.id === layer.id ? 0.96 : 0.82,
                }}
              >
                <span className="sr-only">{layer.label}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="grid gap-3">
          <div className="rounded-[1.25rem] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4">
            <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.54)]">
              Layer
            </p>
            <p className="mt-3 text-lg font-semibold text-[var(--foreground)]">
              {selectedLayer.label}
            </p>
          </div>
          <div className="rounded-[1.25rem] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4">
            <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.54)]">
              Level
            </p>
            <p className="mt-3 text-sm font-medium text-[rgba(19,33,47,0.78)]">
              {selectedLayer.level}
            </p>
          </div>
          <div className="rounded-[1.25rem] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4">
            <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.54)]">
              Height
            </p>
            <p className="mt-3 text-sm font-medium text-[rgba(19,33,47,0.78)]">
              {selectedLayer.heightMeters}m
            </p>
          </div>
          <div className="rounded-[1.25rem] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4">
            <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.54)]">
              Footprint
            </p>
            <p className="mt-3 text-sm font-medium text-[rgba(19,33,47,0.78)]">
              {selectedLayer.footprintWidth}m x {selectedLayer.footprintDepth}m
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
