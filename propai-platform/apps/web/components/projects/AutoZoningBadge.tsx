"use client";

import { useEffect, useState } from "react";
import { useProjectContextStore } from "@/store/useProjectContextStore";

/* ── Response type ── */

type ZoneLimits = {
  max_bcr_pct: number;
  max_far_pct: number;
  max_height_m: number | null;
  zone_key: string;
  legal_basis: string;
};

type SpecialDistrict = {
  name: string;
  bonus_far: number | null;
};

type ZoningAnalysisResponse = {
  address: string;
  pnu: string | null;
  zone_type: string | null;
  zone_limits: ZoneLimits | null;
  land_area_sqm: number | null;
  land_category: string | null;
  official_price_per_sqm: number | null;
  special_districts: SpecialDistrict[];
  warnings: string[];
};

/* ── Component ── */

export function AutoZoningBadge({ address }: { address: string }) {
  const [result, setResult] = useState<ZoningAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const updateSiteAnalysis = useProjectContextStore(
    (s) => s.updateSiteAnalysis,
  );
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);

  useEffect(() => {
    if (!address || address.trim().length < 3) {
      setResult(null);
      return;
    }

    let cancelled = false;

    async function fetchZoning() {
      setLoading(true);
      setError("");
      try {
        const data = await (async () => ({} as ZoningAnalysisResponse))() },
          },
        );
        if (!cancelled) {
          setResult(data);

          // Update project context store with zoning data
          updateSiteAnalysis({
            estimatedValue: siteAnalysis?.estimatedValue ?? null,
            landAreaSqm: data.land_area_sqm ?? siteAnalysis?.landAreaSqm ?? null,
            zoneCode: data.zone_limits?.zone_key ?? data.zone_type ?? null,
            address: data.address,
            pnu: data.pnu ?? siteAnalysis?.pnu ?? null,
          });
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "용도지역 조회 실패",
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    // Debounce: wait 600ms after address changes
    const timer = setTimeout(fetchZoning, 600);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [address]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] px-4 py-3">
        <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-[var(--accent-strong)] border-t-transparent" />
        <span className="text-xs text-[var(--text-secondary)]">
          용도지역 조회 중...
        </span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-[var(--radius-xl)] border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] px-4 py-3 text-xs text-[var(--spot)]">
        {error}
      </div>
    );
  }

  if (!result || !result.zone_type) {
    return null;
  }

  const limits = result.zone_limits;

  return (
    <div className="space-y-2">
      {/* Badge row: zone type + metrics */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Zone type badge */}
        <span className="rounded-full bg-[rgba(14,116,144,0.12)] px-4 py-2 text-xs font-semibold text-[var(--accent-strong)]">
          {result.zone_type}
        </span>

        {/* Compact metric tiles */}
        {limits && (
          <>
            <MetricChip label="건폐율" value={`${limits.max_bcr_pct}%`} />
            <MetricChip label="용적률" value={`${limits.max_far_pct}%`} />
            {limits.max_height_m != null && (
              <MetricChip label="높이" value={`${limits.max_height_m}m`} />
            )}
          </>
        )}

        {/* Land area if available */}
        {result.land_area_sqm != null && (
          <MetricChip
            label="면적"
            value={`${result.land_area_sqm.toLocaleString()}m2`}
          />
        )}
      </div>

      {/* Special districts */}
      {result.special_districts.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {result.special_districts.map((d, i) => (
            <span
              key={`district-${i}`}
              className="rounded-full border border-[rgba(14,116,144,0.2)] px-3 py-1 text-[10px] font-medium text-[var(--accent-strong)]"
            >
              {d.name}
              {d.bonus_far != null && ` (FAR ${d.bonus_far}%)`}
            </span>
          ))}
        </div>
      )}

      {/* Warnings */}
      {result.warnings.length > 0 && (
        <div className="space-y-1">
          {result.warnings.map((w, i) => (
            <p
              key={`warn-${i}`}
              className="text-[10px] leading-5 text-[var(--spot)]"
            >
              {w}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── MetricChip ── */

function MetricChip({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-[var(--radius-lg)] bg-[var(--surface-soft)] px-3 py-1.5">
      <span className="text-[10px] uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
        {label}
      </span>
      <span className="text-xs font-semibold text-[var(--text-primary)]">
        {value}
      </span>
    </span>
  );
}
