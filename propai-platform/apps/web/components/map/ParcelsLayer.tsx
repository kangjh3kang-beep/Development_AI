"use client";

import type { CSSProperties } from "react";
import type { ParcelShape } from "@/mocks/module-data";

type ParcelsLayerProps = {
  parcels: ParcelShape[];
  selectedParcelId: string;
  onSelect: (parcelId: string) => void;
};

const parcelStatusClassName = {
  available: "bg-[rgba(14,116,144,0.28)] text-[var(--accent-strong)]",
  review: "bg-[rgba(217,119,6,0.22)] text-[var(--spot)]",
  restricted: "bg-[rgba(19,33,47,0.2)] text-[var(--foreground)]",
} as const;

export function ParcelsLayer({
  parcels,
  selectedParcelId,
  onSelect,
}: ParcelsLayerProps) {
  return (
    <div className="absolute inset-0">
      {parcels.map((parcel) => {
        const style: CSSProperties = {
          left: `${parcel.x}%`,
          top: `${parcel.y}%`,
          width: `${parcel.width}%`,
          height: `${parcel.height}%`,
        };

        return (
          <button
            key={parcel.id}
            type="button"
            aria-pressed={selectedParcelId === parcel.id}
            className={`absolute rounded-[1.1rem] border border-white/70 px-3 py-2 text-left text-xs font-semibold shadow-[0_10px_24px_rgba(19,33,47,0.08)] transition hover:scale-[1.01] ${
              parcelStatusClassName[parcel.status]
            } ${
              selectedParcelId === parcel.id
                ? "ring-2 ring-[var(--foreground)]"
                : ""
            }`}
            style={style}
            onClick={() => onSelect(parcel.id)}
          >
            <span className="block">{parcel.label}</span>
            <span className="mt-1 block text-[11px] font-medium opacity-80">
              {parcel.areaSqm.toFixed(1)}㎡
            </span>
          </button>
        );
      })}
    </div>
  );
}
