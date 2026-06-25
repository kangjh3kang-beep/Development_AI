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
    <section className="grid gap-6 xl:grid-cols-[1.6fr_1fr]">
      <div className="relative overflow-hidden rounded-[2.5rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] shadow-[var(--shadow-2xl)] backdrop-blur-xl group">
        <div className="absolute top-0 right-0 h-64 w-64 rounded-full bg-[var(--accent-strong)]/10 blur-[80px] transition-all duration-700 group-hover:bg-[var(--accent-strong)]/20" />
        <div className="p-8">
          <div className="mb-6">
            <h2 className="text-2xl font-bold tracking-tight text-[var(--text-primary)]">{labels.title}</h2>
            <p className="mt-2 text-sm font-medium text-[var(--text-secondary)]">
              {labels.description}
            </p>
          </div>
          
          <div className="relative min-h-[440px] overflow-hidden rounded-[1.5rem] border border-[var(--accent-strong)]/30 bg-[#060b14]/90 shadow-[inset_0_0_50px_rgba(45,212,191,0.05)]">
            <div className="absolute inset-0 bg-[linear-gradient(rgba(45,212,191,0.1)_1px,transparent_1px),linear-gradient(90deg,rgba(45,212,191,0.1)_1px,transparent_1px)] bg-[size:40px_40px] opacity-20 pointer-events-none" />
            <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')] opacity-20 mix-blend-overlay pointer-events-none" />
            
            <div className="absolute top-4 left-4 z-10 flex gap-2 pointer-events-none">
              <span className="flex h-3 w-3 animate-ping rounded-full bg-[var(--accent-strong)] opacity-75"></span>
              <span className="text-[10px] font-black uppercase tracking-widest text-[var(--accent-strong)]">Radar Active</span>
            </div>

            <ParcelsLayer
              parcels={parcels}
              selectedParcelId={selectedParcel.id}
              onSelect={setSelectedParcelId}
            />
          </div>
          
          <div className="mt-8">
            <p className="text-[10px] font-black uppercase tracking-[0.3em] text-[var(--text-hint)] mb-4">
              {labels.legendTitle}
            </p>
            <div className="flex flex-wrap gap-3 text-xs font-bold">
              {(
                Object.keys(labels.statusLabels) as Array<keyof typeof labels.statusLabels>
              ).map((statusKey) => (
                <span
                  key={statusKey}
                  className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface-muted)] px-4 py-2.5 text-[var(--text-primary)] shadow-[var(--shadow-sm)] hover:border-[var(--accent-strong)]/50 transition-colors cursor-default"
                >
                  <span className="mr-2 inline-block h-2 w-2 rounded-full bg-[var(--accent-strong)]" />
                  {labels.statusLabels[statusKey]}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="relative overflow-hidden rounded-[2.5rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-8 shadow-[var(--shadow-xl)] backdrop-blur-xl">
         <div className="absolute -bottom-20 -left-20 h-64 w-64 rounded-full bg-[var(--accent-strong)]/5 blur-[80px]" />
         <h2 className="text-xl font-bold tracking-tight text-[var(--text-primary)] mb-8">{labels.parcelInfoTitle}</h2>
         
         <div className="grid grid-cols-1 gap-6 min-w-0">
          <div className="relative overflow-hidden rounded-[1.5rem] border border-[var(--accent-strong)]/40 bg-gradient-to-br from-[var(--accent-strong)]/10 to-transparent p-6 shadow-[inset_0_0_20px_rgba(45,212,191,0.05)]">
            <p className="text-[10px] font-black uppercase tracking-[0.3em] text-[var(--accent-strong)] mb-2">
              Selected Parcel
            </p>
            <p className="text-3xl font-[1000] tracking-tighter text-[var(--text-primary)]">
              {selectedParcel.label}
            </p>
            <div className="absolute top-4 right-4 text-[var(--accent-strong)]/30">
              <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s-8-4.5-8-11.8A8 8 0 0 1 12 2a8 8 0 0 1 8 8.2c0 7.3-8 11.8-8 11.8z"/><circle cx="12" cy="10" r="3"/></svg>
            </div>
          </div>
          
          <div className="grid gap-4">
            <div className="group rounded-[1.25rem] border border-[var(--line-strong)] bg-[var(--surface-muted)] px-5 py-4 transition-all hover:border-[var(--accent-strong)]/30 hover:bg-[var(--surface-soft)]">
              <p className="text-[10px] font-black uppercase tracking-[0.3em] text-[var(--text-hint)] group-hover:text-[var(--accent-strong)] transition-colors">
                {labels.areaLabel}
              </p>
              <p className="mt-2 text-lg font-bold text-[var(--text-primary)]">
                {selectedParcel.areaSqm.toFixed(1)} ㎡
              </p>
            </div>
            
            <div className="group rounded-[1.25rem] border border-[var(--line-strong)] bg-[var(--surface-muted)] px-5 py-4 transition-all hover:border-[var(--accent-strong)]/30 hover:bg-[var(--surface-soft)]">
              <p className="text-[10px] font-black uppercase tracking-[0.3em] text-[var(--text-hint)] group-hover:text-[var(--accent-strong)] transition-colors">
                {labels.ownerLabel}
              </p>
              <p className="mt-2 text-lg font-bold text-[var(--text-primary)] truncate">
                {selectedParcel.owner}
              </p>
            </div>
            
            <div className="group rounded-[1.25rem] border border-[var(--line-strong)] bg-[var(--surface-muted)] px-5 py-4 transition-all hover:border-[var(--accent-strong)]/30 hover:bg-[var(--surface-soft)]">
              <p className="text-[10px] font-black uppercase tracking-[0.3em] text-[var(--text-hint)] group-hover:text-[var(--accent-strong)] transition-colors">
                {labels.statusLabel}
              </p>
              <p className="mt-2 inline-flex items-center gap-2 text-lg font-bold text-[var(--text-primary)]">
                <span className="h-2 w-2 rounded-full bg-[var(--accent-strong)] shadow-[0_0_10px_rgba(45,212,191,0.5)]" />
                {labels.statusLabels[selectedParcel.status]}
              </p>
            </div>
          </div>
         </div>
      </div>
    </section>
  );
}
