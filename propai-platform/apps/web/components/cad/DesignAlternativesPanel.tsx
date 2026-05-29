"use client";

import { useCallback, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useCadStore } from "@/store/use-cad-store";
import type {
  AutoDesignResponse,
  DesignAlternativesResponse,
} from "@/components/cad/types";

type DesignAlternativesPanelProps = {
  siteArea: number;
  zoneCode: string;
  buildingUse: string;
  unitTypes: string[];
  floorHeight: number;
  setback: Record<string, number>;
};

const ALT_LABELS = ["A: 최적 균형", "B: 최대 세대수", "C: 최적 일조"];

export function DesignAlternativesPanel({
  siteArea,
  zoneCode,
  buildingUse,
  unitTypes,
  floorHeight,
  setback,
}: DesignAlternativesPanelProps) {
  const loadDesignPayload = useCadStore((s) => s.loadDesignPayload);

  const [alternatives, setAlternatives] = useState<AutoDesignResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);

  const handleGenerate = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const body = {
        site_area_sqm: siteArea,
        zone_code: zoneCode,
        building_use: buildingUse,
        target_unit_types: unitTypes.length > 0 ? unitTypes : ["84A"],
        floor_height_m: floorHeight,
        setback_m: setback,
        count: 3,
      };
      const data = await apiClient.post<DesignAlternativesResponse>(
        "/drawing/design-alternatives",
        { body },
      );
      setAlternatives(data.alternatives);
      setSelectedIdx(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "알 수 없는 오류");
    } finally {
      setLoading(false);
    }
  }, [siteArea, zoneCode, buildingUse, unitTypes, floorHeight, setback]);

  const handleApply = useCallback(
    (idx: number) => {
      const alt = alternatives[idx];
      if (!alt) return;
      loadDesignPayload(alt.design_payload);
      setSelectedIdx(idx);
    },
    [alternatives, loadDesignPayload],
  );

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        onClick={handleGenerate}
        disabled={loading}
        className="rounded-xl bg-[var(--surface-soft)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] border border-[var(--line)] transition-opacity disabled:opacity-50"
      >
        {loading ? "대안 생성 중..." : "대안 3개 비교"}
      </button>

      {error && (
        <p className="text-xs text-red-600" role="alert">
          {error}
        </p>
      )}

      {alternatives.length > 0 && (
        <div className="grid gap-2" role="list" aria-label="설계 대안 목록">
          {alternatives.map((alt, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => handleApply(idx)}
              className={`rounded-xl border p-3 text-left transition-colors ${
                selectedIdx === idx
                  ? "border-[var(--accent)] bg-[var(--accent)]/5"
                  : "border-[var(--line)] bg-white hover:bg-[var(--surface-soft)]"
              }`}
              role="listitem"
              aria-label={`대안 ${ALT_LABELS[idx] ?? `${idx + 1}`}`}
            >
              <div className="mb-1.5 flex items-center justify-between">
                <span className="text-xs font-semibold text-[var(--text-primary)]">
                  {ALT_LABELS[idx] ?? `대안 ${idx + 1}`}
                </span>
                <span
                  className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold ${
                    alt.compliance.all_pass
                      ? "bg-emerald-100 text-emerald-700"
                      : "bg-red-100 text-red-700"
                  }`}
                >
                  {alt.compliance.all_pass ? "적합" : "위반"}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-1 text-[10px] text-[var(--text-secondary)]">
                <span>건폐율 {alt.summary.bcr_percent.toFixed(1)}%</span>
                <span>용적률 {alt.summary.far_percent.toFixed(1)}%</span>
                <span>{alt.summary.num_floors}F</span>
                <span>{alt.summary.total_units}세대</span>
                <span>{alt.summary.parking_count}대</span>
                <span>{alt.summary.building_height_m.toFixed(1)}m</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
