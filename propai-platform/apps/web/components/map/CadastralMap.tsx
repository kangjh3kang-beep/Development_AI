"use client";

import { useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@propai/ui";
import { ParcelsLayer } from "@/components/map/ParcelsLayer";
import type { ParcelShape, ParcelStatus } from "@/mocks/module-data";

type CadastralMapProps = {
  parcels: ParcelShape[];
  labels: {
    title: string;
    description: string;
    legendTitle: string;
    parcelInfoTitle: string;
    areaLabel: string;
    ownerLabel: string;
    statusLabel: string;
    statusLabels: Record<ParcelStatus, string>;
  };
};

export function CadastralMap({ parcels, labels }: CadastralMapProps) {
  const [selectedParcelId, setSelectedParcelId] = useState(
    parcels[0]?.id ?? "",
  );

  const selectedParcel = useMemo(
    () => parcels.find((parcel) => parcel.id === selectedParcelId) ?? parcels[0],
    [parcels, selectedParcelId],
  );

  if (!selectedParcel) {
    return null;
  }

  return (
    <section className="grid gap-4 xl:grid-cols-[1.45fr_0.95fr]">
      <Card className="overflow-hidden bg-[var(--surface-strong)]">
        <CardHeader>
          <CardTitle>{labels.title}</CardTitle>
          <p className="text-sm leading-7 text-[var(--text-secondary)]">
            {labels.description}
          </p>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="relative min-h-[360px] overflow-hidden rounded-[var(--radius-xl)] border border-[var(--line)] bg-[linear-gradient(180deg,rgba(255,255,255,0.9),rgba(248,243,233,0.96))]">
            <div className="absolute inset-0 bg-[linear-gradient(rgba(19,33,47,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(19,33,47,0.05)_1px,transparent_1px)] bg-[size:32px_32px]" />
            <ParcelsLayer
              parcels={parcels}
              selectedParcelId={selectedParcel.id}
              onSelect={setSelectedParcelId}
            />
          </div>
          <div className="mt-4">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-hint)]">
              {labels.legendTitle}
            </p>
            <div className="mt-3 flex flex-wrap gap-2 text-xs font-medium">
              {(
                Object.keys(labels.statusLabels) as Array<keyof typeof labels.statusLabels>
              ).map((statusKey) => (
                <span
                  key={statusKey}
                  className="rounded-full border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-[var(--text-secondary)]"
                >
                  {labels.statusLabels[statusKey]}
                </span>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{labels.parcelInfoTitle}</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 pt-0">
          <div className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface)] p-5">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-hint)]">
              Parcel
            </p>
            <p className="mt-3 text-2xl font-semibold text-[var(--text-primary)]">
              {selectedParcel.label}
            </p>
          </div>
          <div className="grid gap-3">
            <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 py-3">
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-hint)]">
                {labels.areaLabel}
              </p>
              <p className="mt-2 text-sm font-medium text-[var(--text-secondary)]">
                {selectedParcel.areaSqm.toFixed(1)}㎡
              </p>
            </div>
            <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 py-3">
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-hint)]">
                {labels.ownerLabel}
              </p>
              <p className="mt-2 text-sm font-medium text-[var(--text-secondary)]">
                {selectedParcel.owner}
              </p>
            </div>
            <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 py-3">
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-hint)]">
                {labels.statusLabel}
              </p>
              <p className="mt-2 text-sm font-medium text-[var(--text-secondary)]">
                {labels.statusLabels[selectedParcel.status]}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
