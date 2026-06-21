"use client";

import { useEffect, useMemo, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { getCachedAnalysis, setCachedAnalysis, TTL_7D } from "@/lib/analysis-fetch-cache";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { LegalRefChip } from "@/components/common/LegalRefChip";
import { mapZoningRich, DEVELOPABILITY_LABEL } from "@/lib/zoning-ssot";

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

/** far_tier_service.calc_effective_far 산출(법정/조례/실효 분리). 옵셔널·하위호환 — 구버전 백엔드는 부재. */
type EffectiveFar = {
  national_far_pct?: number | null;   // 법정 상한 용적률
  national_bcr_pct?: number | null;   // 법정 상한 건폐율
  effective_far_pct?: number | null;  // 실효 용적률(min 법정/조례/계획)
  effective_bcr_pct?: number | null;  // 실효 건폐율
  far_basis?: string | null;
};

/** special_parcel.detect_special_parcel 산출(임야·학교용지·GB·맹지 등 특이부지 게이트). 옵셔널. */
type SpecialParcel = {
  is_special?: boolean | null;
  developability?: string | null;     // POSSIBLE|CONDITIONAL|PRECONDITION|RESTRICTED|BLOCKED
  resolvable?: string | null;         // YES|CONDITIONAL|NO
  severity_label?: string | null;
  factors?: Array<{ category?: string | null } | string> | null;
  honest_disclosure?: string | null;
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
  /** 실효용적률 계층(가산·옵셔널) — 법정상한을 실효처럼 오인하지 않도록 분리 제공. */
  effective_far?: EffectiveFar | null;
  /** 특이부지 게이트(가산·옵셔널) — is_special일 때만 배지/경고 렌더(무목업). */
  special_parcel?: SpecialParcel | null;
};

/** 다필지 통합분석 응답(부분) — 배지에 필요한 dominant_zone/혼재 신호만(읽기 소비). 옵셔널. */
type IntegratedZoneSummary = {
  dominant_zone?: string | null;
  dominant_basis?: string | null;
  parcel_count?: number | null;
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

  // ── 다필지 통합 배지(읽기 소비·로컬 state) — parcelCount>1 && 필지목록>1일 때만 ──
  //   dominant_zone+'혼재' 배지를 단일 배지 앞에 보강. 미확보 시 기존 단일 배지만(degrade).
  const ssotParcels = siteAnalysis?.parcels ?? null;
  const isMultiParcel = (siteAnalysis?.parcelCount ?? 1) > 1 && (ssotParcels?.length ?? 0) > 1;
  const parcelsSig = useMemo(() => {
    if (!isMultiParcel || !ssotParcels) return "";
    return ssotParcels.map((p) => `${p.pnu}:${p.areaSqm ?? ""}`).sort().join("|");
  }, [isMultiParcel, ssotParcels]);
  const [integrated, setIntegrated] = useState<IntegratedZoneSummary | null>(null);
  useEffect(() => {
    if (!isMultiParcel || !ssotParcels || ssotParcels.length < 2) { setIntegrated(null); return; }
    const iKey = `integrated:${ssotParcels.length}:${parcelsSig}`;
    const cached = getCachedAnalysis<IntegratedZoneSummary>(iKey, TTL_7D);
    if (cached) { setIntegrated(cached); return; }
    let alive = true;
    const triggeredProjectId = useProjectContextStore.getState().projectId;
    void apiClient.post<IntegratedZoneSummary>("/zoning/integrated-analysis", {
      useMock: false,
      body: {
        parcels: ssotParcels.map((p) => ({ pnu: p.pnu, address: p.address, area_sqm: p.areaSqm, land_category: p.landCategory })),
        use_llm: false,
      },
    }).then((res) => {
      if (!alive) return;
      if (useProjectContextStore.getState().projectId !== triggeredProjectId) return;
      setIntegrated(res);
      setCachedAnalysis(iKey, res);
    }).catch(() => { /* 무목업: 실패 시 통합 배지 미표시(단일 degrade) */ });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isMultiParcel, parcelsSig]);

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
          //
          // ★다필지 통합면적 보존 가드: 이 호출은 "대표 1필지"(단일 PNU) 분석이라
          //   data.land_area_sqm은 대표 면적(작은 값)이다. 현재 SSOT가 이미 다필지 통합
          //   (parcelCount>1 && landAreaSqmTotal>0)이면 landAreaSqm을 대표값으로 덮어쓰면
          //   설계·수지가 부지를 너무 작게 본다(상도동 779㎡→236㎡ 회귀). 이 경우 landAreaSqm
          //   키 자체를 페이로드에서 빼서 통합 면적/메타(Total·Rep·parcelCount)를 그대로 보존한다.
          // 라이브 SSOT를 읽는다(effect deps=[address]라 클로저의 siteAnalysis는 stale일 수 있어,
          // enrichParcels가 통합값을 막 기록한 직후에도 정확히 판정하려면 getState 사용).
          const cur = useProjectContextStore.getState().siteAnalysis;
          const isMultiParcel =
            (cur?.parcelCount ?? 1) > 1 &&
            typeof cur?.landAreaSqmTotal === "number" &&
            cur.landAreaSqmTotal > 0;
          // ★#185 무한렌더 가드(LandIntelligencePanel과 동일 전역계약): SSOT address는 입력 정체성이라
          //   분석 결과(data.address·백엔드 정규화)로 덮어쓰지 않는다. 덮어쓰면 data.address≠입력 시
          //   이 effect(deps=[address])가 재발화→재분석→재기록 순환으로 렌더 폭주(#185). address는 SSOT 보존.
          const basePayload = {
            estimatedValue: cur?.estimatedValue ?? null,
            zoneCode: data.zone_limits?.zone_key ?? data.zone_type ?? null,
            pnu: data.pnu ?? cur?.pnu ?? null,
            ...mapZoningRich(data),
          };
          updateSiteAnalysis(
            isMultiParcel
              ? basePayload // 다필지: landAreaSqm 미포함 → 통합 면적 보존
              : {
                  ...basePayload,
                  landAreaSqm: data.land_area_sqm ?? cur?.landAreaSqm ?? null,
                },
            { source: "auto" },
          );
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

  // 실효 우선 표시 — 실효용적률 계층(effective_far)이 있으면 실효값, 없으면 법정상한(zone_limits)으로 폴백.
  //   법정상한을 라벨 없이 '용적률'로 표시해 사용자가 실효로 오인하던 결함을 SiteAnalysisDetail/GlobalAddressSearch
  //   정답 패턴으로 교정한다(실효<법정이면 법정상한을 보조로 병기, 무목업·과다표시 방지).
  const ef = result.effective_far ?? null;
  const effBcr =
    typeof ef?.effective_bcr_pct === "number" ? ef.effective_bcr_pct : null;
  const effFar =
    typeof ef?.effective_far_pct === "number" ? ef.effective_far_pct : null;
  const legalBcr =
    (typeof ef?.national_bcr_pct === "number" ? ef.national_bcr_pct : null) ??
    limits?.max_bcr_pct ??
    null;
  const legalFar =
    (typeof ef?.national_far_pct === "number" ? ef.national_far_pct : null) ??
    limits?.max_far_pct ??
    null;
  // 칩에 쓸 대표값: 실효 우선, 없으면 법정상한.
  const showBcr = effBcr ?? legalBcr;
  const showFar = effFar ?? legalFar;

  // 특이부지 게이트 — is_special일 때만 배지/경고 렌더(없으면 미표시, 가짜 금지).
  const sp = result.special_parcel ?? null;
  const isSpecial = sp?.is_special === true;
  const spFactors = (sp?.factors ?? [])
    .map((f) =>
      typeof f === "string" ? f.trim() : (f?.category ?? "").toString().trim(),
    )
    .filter((t) => t.length > 0);
  // developability(영문 게이트) → 한국어 라벨. 미지/누락 시 severity_label 폴백, 그것도 없으면 미표기.
  // DEVELOPABILITY_LABEL은 zoning-ssot.ts 공용 상수 사용.
  const developabilityLabel =
    (sp?.developability && DEVELOPABILITY_LABEL[sp.developability]) ||
    (typeof sp?.severity_label === "string" ? sp.severity_label : null);

  // 법령 원문링크 근거 — 백엔드(get_legal_refs)가 보낸 검증 url만 사용(프론트 조립 금지).
  // law_name이 있는 항목만 칩으로 렌더(빈 항목 방지). 구버전 백엔드는 빈 배열 → 미표시.
  const legalRefs = (result.legal_refs ?? []).filter(
    (ref) => ref && typeof ref.law_name === "string" && ref.law_name.trim().length > 0,
  );

  return (
    <div className="space-y-2">
      {/* Badge row: zone type + metrics */}
      <div className="flex flex-wrap items-center gap-3">
        {/* 다필지 통합 대표 용도지역 배지(integrated 확보 시만) — 단일 배지 앞에 '혼재' 신호와 함께. */}
        {isMultiParcel && integrated?.dominant_zone && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--accent-soft)] px-4 py-2 text-xs font-bold text-[var(--accent-strong)]">
            {integrated.dominant_zone}
            <span className="rounded-full bg-[color-mix(in_srgb,var(--status-warning)_18%,transparent)] px-2 py-0.5 text-[10px] font-bold text-[var(--status-warning)]">
              통합 {integrated.parcel_count ?? siteAnalysis?.parcelCount ?? (ssotParcels?.length ?? 0)}필지 · 혼재
            </span>
          </span>
        )}
        {/* Zone type badge (대표 단일 필지) */}
        <span className="rounded-full bg-[rgba(14,116,144,0.12)] px-4 py-2 text-xs font-semibold text-[var(--accent-strong)]">
          {result.zone_type}
        </span>

        {/* Compact metric tiles — 실효 우선 표시(실효 라벨), 실효<법정이면 법정상한 보조 병기.
            실효값이 없으면(구버전 백엔드) 법정상한을 '법정상한' 라벨로 명시(실효 오인 방지). */}
        {showBcr != null && (
          <MetricChip
            label={effBcr != null ? "건폐율(실효)" : "건폐율(법정상한)"}
            value={`${showBcr}%`}
            sub={
              effBcr != null && legalBcr != null && legalBcr > effBcr
                ? `법정 ${legalBcr}%`
                : undefined
            }
          />
        )}
        {showFar != null && (
          <MetricChip
            label={effFar != null ? "용적률(실효)" : "용적률(법정상한)"}
            value={`${showFar}%`}
            sub={
              effFar != null && legalFar != null && legalFar > effFar
                ? `법정 ${legalFar}%`
                : undefined
            }
          />
        )}
        {limits?.max_height_m != null && (
          <MetricChip label="높이" value={`${limits.max_height_m}m`} />
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

      {/* 특이부지 게이트 — is_special일 때만 배지+경고. 임야·학교용지·GB·맹지 등은 법정상한이
          그대로 실현되지 않으므로 개발가능성(developability)·정직고지(honest_disclosure)를 표시한다.
          SiteAnalysisDetail/GlobalAddressSearch 정답 패턴 복제(--status-warning 토큰). */}
      {isSpecial && (
        <div className="space-y-1.5 rounded-[var(--radius-lg)] border border-[color-mix(in_srgb,var(--status-warning)_36%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_10%,transparent)] px-3 py-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-[color-mix(in_srgb,var(--status-warning)_18%,transparent)] px-2.5 py-1 text-[10px] font-bold text-[var(--status-warning)]">
              ⚠ 특이부지
              {spFactors.length > 0 ? ` · ${spFactors.join(" · ")}` : ""}
            </span>
            {developabilityLabel && (
              <span className="text-[10px] font-semibold text-[var(--status-warning)]">
                개발가능성: {developabilityLabel}
              </span>
            )}
          </div>
          {sp?.honest_disclosure && (
            <p className="text-[10px] leading-5 text-[var(--text-secondary)]">
              {sp.honest_disclosure}
            </p>
          )}
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

function MetricChip({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-[var(--radius-lg)] bg-[var(--surface-soft)] px-3 py-1.5">
      <span className="text-[10px] tracking-[0.12em] text-[var(--text-tertiary)]">
        {label}
      </span>
      <span className="text-xs font-semibold text-[var(--text-primary)]">
        {value}
      </span>
      {/* 실효<법정일 때만 법정상한을 보조로 병기(정직 표기·과다표시 방지) */}
      {sub && (
        <span className="text-[10px] text-[var(--text-hint)]">{sub}</span>
      )}
    </span>
  );
}
