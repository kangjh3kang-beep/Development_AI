"use client";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { LegalRefChip } from "@/components/common/LegalRefChip";
import { mapZoningRich } from "@/lib/zoning-ssot";

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

/** 법령 원문링크 근거(레지스트리 get_legal_refs 출력) — 옵셔널·하위호환.
 * url은 백엔드가 검증한 값만 들어오며(프론트 조립 금지), 없으면 LegalRefChip이
 * 자동으로 텍스트 폴백한다(할루시네이션 링크 금지). 구버전 백엔드는 이 필드 부재. */
type LegalRef = {
  key?: string | null;
  law_name?: string | null;
  article?: string | null;
  title?: string | null;
  url?: string | null;
  url_status?: string | null;
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
  /** WP-D 신뢰 메타데이터(가산·옵셔널) — 없으면(구버전) 렌더 생략. */
  legal_refs?: LegalRef[] | null;
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
        const data = await apiClient.post<ZoningAnalysisResponse>(
          "/zoning/analyze",
          {
            useMock: false,
            body: { address: address.trim() },
          },
        );
        if (!cancelled) {
          setResult(data);

          // Update project context store with zoning data.
          // 토지/법규 심층 결과(rich)를 SSOT에 보존 — 하류(추천·설계·수지)가 /zoning/analyze
          // 재호출 없이 읽도록 한다. mapZoningRich는 현재 주소 기준 값 또는 명시적 null로 기록
          // (주소 변경 시 직전 부지 특이정보 잔류=할루시네이션 가드 오발동 방지, 무목업 유지).
          updateSiteAnalysis({
            estimatedValue: siteAnalysis?.estimatedValue ?? null,
            landAreaSqm: data.land_area_sqm ?? siteAnalysis?.landAreaSqm ?? null,
            zoneCode: data.zone_limits?.zone_key ?? data.zone_type ?? null,
            address: data.address,
            pnu: data.pnu ?? siteAnalysis?.pnu ?? null,
            ...mapZoningRich(data),
          }, { source: "auto" });
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

  // 법령 원문링크 근거 — 백엔드(get_legal_refs)가 보낸 검증 url만 사용(프론트 조립 금지).
  // law_name이 있는 항목만 칩으로 렌더(빈 항목 방지). 구버전 백엔드는 빈 배열 → 미표시.
  const legalRefs = (result.legal_refs ?? []).filter(
    (ref) => ref && typeof ref.law_name === "string" && ref.law_name.trim().length > 0,
  );

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

      {/* 법령 근거: 백엔드가 보낸 legal_refs[] 원문링크 칩(우선) + zone_limits.legal_basis 텍스트 폴백.
          legal_refs는 검증 url을 가질 수 있고, legal_basis는 url 없는 텍스트(LegalRefChip이 자동 텍스트 폴백). */}
      {(legalRefs.length > 0 || limits?.legal_basis) && (
        <div className="flex flex-wrap items-center gap-1.5">
          {legalRefs.length > 0 ? (
            legalRefs.map((ref, i) => (
              <LegalRefChip
                key={`legal-ref-${ref.key ?? i}`}
                lawName={ref.law_name ?? ""}
                article={ref.article}
                title={ref.title}
                url={ref.url}
              />
            ))
          ) : limits?.legal_basis ? (
            /* 구버전 백엔드(legal_refs 부재): legal_basis 텍스트만 칩으로 표기(url 없음 → 텍스트 폴백). */
            <LegalRefChip lawName={limits.legal_basis} />
          ) : null}
        </div>
      )}

      {/* Special districts */}
      {(result.special_districts?.length ?? 0) > 0 && (
        <div className="flex flex-wrap gap-2">
          {(result.special_districts ?? []).map((d, i) => (
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
      {(result.warnings?.length ?? 0) > 0 && (
        <div className="space-y-1">
          {(result.warnings ?? []).map((w, i) => (
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
