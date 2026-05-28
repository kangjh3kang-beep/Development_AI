"use client";

import { useCallback, useState } from "react";
import { Button, Card, CardContent, Input } from "@propai/ui";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";

/* ── Types ── */

type ZoningResult = {
  zone_type: string;
  max_bcr: number;
  max_far: number;
  max_height: number;
  land_area: number;
  pnu: string;
  official_price: number;
};

type AVMResult = {
  estimated_price: number;
  price_per_sqm: number;
  confidence: number;
  comparables: Array<{
    address: string;
    price: number;
    area_sqm: number;
    transaction_date: string;
  }>;
};

type Parcel = {
  id: string;
  address: string;
  areaOverride: string;
  status: "idle" | "analyzing" | "done" | "error";
  zoning?: ZoningResult;
  avm?: AVMResult;
  error?: string;
};

/* ── Helpers ── */

function formatKRW(value: number): string {
  if (value >= 1_0000_0000) {
    const eok = value / 1_0000_0000;
    return `${eok.toFixed(eok % 1 === 0 ? 0 : 1)}억원`;
  }
  if (value >= 1_0000) {
    const man = value / 1_0000;
    return `${man.toFixed(man % 1 === 0 ? 0 : 1)}만원`;
  }
  return `${value.toLocaleString("ko-KR")}원`;
}

function nextId(parcels: Parcel[]): string {
  const max = parcels.reduce((m, p) => Math.max(m, Number(p.id) || 0), 0);
  return String(max + 1);
}

/* ── Component ── */

export function ProjectSiteAnalysisWorkspaceClient({
  locale,
  projectId,
}: {
  locale: Locale;
  projectId: string;
}) {
  const updateSiteAnalysis = useProjectContextStore(
    (s) => s.updateSiteAnalysis,
  );
  const markStageComplete = useProjectContextStore(
    (s) => s.markStageComplete,
  );
  const addAnalysisResult = useProjectContextStore(
    (s) => s.addAnalysisResult,
  );

  const [parcels, setParcels] = useState<Parcel[]>([
    { id: "1", address: "", areaOverride: "", status: "idle" },
  ]);
  const [activeParcelId, setActiveParcelId] = useState("1");

  const activeParcel = parcels.find((p) => p.id === activeParcelId) ?? parcels[0]!;
  const doneParcels = parcels.filter((p) => p.status === "done");

  /* ── Parcel CRUD ── */

  const addParcel = useCallback(() => {
    setParcels((prev) => {
      const id = nextId(prev);
      return [
        ...prev,
        { id, address: "", areaOverride: "", status: "idle" as const },
      ];
    });
  }, []);

  const removeParcel = useCallback(
    (id: string) => {
      setParcels((prev) => {
        if (prev.length <= 1) return prev;
        const next = prev.filter((p) => p.id !== id);
        if (activeParcelId === id) {
          setActiveParcelId(next[0]!.id);
        }
        return next;
      });
    },
    [activeParcelId],
  );

  const updateParcel = useCallback(
    (id: string, patch: Partial<Parcel>) => {
      setParcels((prev) =>
        prev.map((p) => (p.id === id ? { ...p, ...patch } : p)),
      );
    },
    [],
  );

  /* ── Analysis ── */

  const analyzeParcel = useCallback(
    async (parcelId: string) => {
      const parcel = parcels.find((p) => p.id === parcelId);
      if (!parcel) return;

      const address = parcel.address.trim();
      if (!address) {
        updateParcel(parcelId, {
          status: "error",
          error: "주소를 입력해주세요.",
        });
        return;
      }

      updateParcel(parcelId, { status: "analyzing", error: undefined });

      try {
        // Step 1: Zoning analysis
        const zoning = await apiClient.post<ZoningResult>("/zoning/analyze", {
          body: {
            address,
            area_sqm: parcel.areaOverride
              ? Number(parcel.areaOverride)
              : undefined,
          },
        });

        // Step 2: AVM estimate
        const avm = await apiClient.post<AVMResult>("/avm/estimate", {
          body: {
            address,
            area_sqm:
              parcel.areaOverride
                ? Number(parcel.areaOverride)
                : zoning.land_area || 300,
            pnu: zoning.pnu || undefined,
          },
        });

        updateParcel(parcelId, { status: "done", zoning, avm });

        // Save first completed parcel to context store
        updateSiteAnalysis({
          estimatedValue: avm.estimated_price,
          landAreaSqm: zoning.land_area || Number(parcel.areaOverride) || 0,
          zoneCode: zoning.zone_type || null,
          address,
          pnu: zoning.pnu || null,
        });
        markStageComplete("site-analysis");
        addAnalysisResult({
          module: "site-analysis",
          completedAt: new Date().toISOString(),
          summary: {
            estimatedPrice: avm.estimated_price,
            confidence: avm.confidence,
            address,
          },
        });
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : "분석 중 오류가 발생했습니다.";
        updateParcel(parcelId, { status: "error", error: message });
      }
    },
    [
      parcels,
      updateParcel,
      updateSiteAnalysis,
      markStageComplete,
      addAnalysisResult,
    ],
  );

  return (
    <section className="grid gap-6">
      {/* Hero */}
      <Card className="rounded-[var(--radius-2xl)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
        <CardContent className="p-8">
          <span className="rounded-full bg-[rgba(14,116,144,0.1)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--accent-strong)]">
            부지 분석
          </span>
          <h3 className="mt-5 text-3xl font-bold text-[var(--text-primary)]">
            주소 검색으로 부지 가치를 즉시 분석합니다
          </h3>
          <p className="mt-4 max-w-3xl text-sm leading-8 text-[var(--text-secondary)]">
            주소를 입력하면 용도지역, 건폐율/용적률, 공시지가, AVM 시세 추정을
            자동으로 조회합니다. 여러 필지를 추가하여 비교 분석할 수 있습니다.
          </p>
        </CardContent>
      </Card>

      {/* Parcel Tabs */}
      <div className="flex flex-wrap items-center gap-2">
        {parcels.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => setActiveParcelId(p.id)}
            className={`group relative rounded-[var(--radius-xl)] border px-4 py-2.5 text-sm font-medium transition-all ${
              p.id === activeParcelId
                ? "border-[var(--accent-strong)] bg-[rgba(14,116,144,0.08)] text-[var(--accent-strong)]"
                : "border-[var(--line)] bg-[var(--surface)] text-[var(--text-secondary)] hover:border-[var(--accent-strong)] hover:text-[var(--text-primary)]"
            }`}
          >
            <span className="flex items-center gap-2">
              {p.status === "done" && (
                <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
              )}
              {p.status === "analyzing" && (
                <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-amber-400" />
              )}
              {p.status === "error" && (
                <span className="inline-block h-2 w-2 rounded-full bg-red-500" />
              )}
              {p.address.trim() || `필지 ${p.id}`}
            </span>
            {parcels.length > 1 && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  removeParcel(p.id);
                }}
                className="ml-2 text-xs text-[var(--text-tertiary)] opacity-0 transition-opacity group-hover:opacity-100 hover:text-red-500"
                aria-label="필지 삭제"
              >
                &times;
              </button>
            )}
          </button>
        ))}
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={addParcel}
          className="rounded-[var(--radius-xl)]"
        >
          + 필지 추가
        </Button>
      </div>

      {/* Active Parcel Input */}
      <Card>
        <CardContent className="p-6">
          <p className="mb-4 text-xs font-semibold uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
            주소 입력
          </p>
          <div className="grid gap-3 sm:grid-cols-[1fr_auto_auto]">
            <Input
              value={activeParcel.address}
              onChange={(e) =>
                updateParcel(activeParcelId, { address: e.target.value })
              }
              placeholder="주소를 입력하세요 (예: 서울특별시 강남구 삼성동 123)"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void analyzeParcel(activeParcelId);
                }
              }}
            />
            <Input
              type="number"
              value={activeParcel.areaOverride}
              onChange={(e) =>
                updateParcel(activeParcelId, { areaOverride: e.target.value })
              }
              placeholder="면적 (m2) — 자동감지"
              className="w-full sm:w-44"
            />
            <Button
              type="button"
              onClick={() => void analyzeParcel(activeParcelId)}
              disabled={activeParcel.status === "analyzing"}
              className="whitespace-nowrap"
            >
              {activeParcel.status === "analyzing" ? "분석 중..." : "분석 실행"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Loading */}
      {activeParcel.status === "analyzing" && (
        <SkeletonLoader count={2} itemClassName="h-40" />
      )}

      {/* Error */}
      {activeParcel.status === "error" && activeParcel.error && (
        <Card className="border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950">
          <CardContent className="p-6">
            <p className="text-sm font-semibold text-red-700 dark:text-red-400">
              분석 오류
            </p>
            <p className="mt-2 text-sm leading-7 text-red-600 dark:text-red-300">
              {activeParcel.error}
            </p>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="mt-4"
              onClick={() => void analyzeParcel(activeParcelId)}
            >
              재시도
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Results */}
      {activeParcel.status === "done" && (
        <div className="grid gap-6 xl:grid-cols-2">
          {/* Zoning Card */}
          {activeParcel.zoning && (
            <Card>
              <CardContent className="p-6">
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                  용도지역 분석
                </p>
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <MetricTile
                    label="용도지역"
                    value={activeParcel.zoning.zone_type || "-"}
                  />
                  <MetricTile
                    label="건폐율 한도"
                    value={`${activeParcel.zoning.max_bcr}%`}
                  />
                  <MetricTile
                    label="용적률 한도"
                    value={`${activeParcel.zoning.max_far}%`}
                  />
                  <MetricTile
                    label="높이 한도"
                    value={
                      activeParcel.zoning.max_height
                        ? `${activeParcel.zoning.max_height}m`
                        : "제한 없음"
                    }
                  />
                  <MetricTile
                    label="토지 면적"
                    value={`${activeParcel.zoning.land_area.toLocaleString("ko-KR")} m2`}
                  />
                  <MetricTile
                    label="PNU"
                    value={activeParcel.zoning.pnu || "-"}
                    small
                  />
                  <MetricTile
                    label="공시지가"
                    value={
                      activeParcel.zoning.official_price
                        ? formatKRW(activeParcel.zoning.official_price)
                        : "-"
                    }
                  />
                </div>
              </CardContent>
            </Card>
          )}

          {/* AVM Card */}
          {activeParcel.avm && (
            <Card>
              <CardContent className="p-6">
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                  AVM 시세 추정
                </p>
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <MetricTile
                    label="추정 시세"
                    value={formatKRW(activeParcel.avm.estimated_price)}
                    highlight
                  />
                  <MetricTile
                    label="m2당 단가"
                    value={formatKRW(activeParcel.avm.price_per_sqm)}
                  />
                  <MetricTile
                    label="신뢰도"
                    value={`${(activeParcel.avm.confidence * 100).toFixed(1)}%`}
                  />
                  <MetricTile
                    label="비교사례"
                    value={`${activeParcel.avm.comparables?.length ?? 0}건`}
                  />
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Comparables Table */}
      {activeParcel.status === "done" &&
        activeParcel.avm?.comparables &&
        activeParcel.avm.comparables.length > 0 && (
          <Card>
            <CardContent className="p-6">
              <p className="mb-4 text-xs font-semibold uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                비교 거래 사례
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[var(--line)]">
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
                        주소
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
                        거래가격
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
                        면적
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
                        거래일
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {activeParcel.avm.comparables.map((comp, i) => (
                      <tr
                        key={`comp-${i}`}
                        className="border-b border-[var(--line)] last:border-0"
                      >
                        <td className="px-4 py-3 text-[var(--text-primary)]">
                          {comp.address}
                        </td>
                        <td className="px-4 py-3 text-right font-semibold text-[var(--text-primary)]">
                          {formatKRW(comp.price)}
                        </td>
                        <td className="px-4 py-3 text-right text-[var(--text-secondary)]">
                          {comp.area_sqm.toLocaleString("ko-KR")} m2
                        </td>
                        <td className="px-4 py-3 text-right text-[var(--text-secondary)]">
                          {comp.transaction_date}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        )}

      {/* Multi-Parcel Comparison */}
      {doneParcels.length >= 2 && (
        <Card>
          <CardContent className="p-6">
            <p className="mb-4 text-xs font-semibold uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              필지 비교 분석
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--line)]">
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
                      항목
                    </th>
                    {doneParcels.map((p) => (
                      <th
                        key={p.id}
                        className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]"
                      >
                        {p.address.length > 20
                          ? `${p.address.slice(0, 20)}...`
                          : p.address}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <ComparisonRow
                    label="용도지역"
                    parcels={doneParcels}
                    getValue={(p) => p.zoning?.zone_type ?? "-"}
                  />
                  <ComparisonRow
                    label="건폐율"
                    parcels={doneParcels}
                    getValue={(p) =>
                      p.zoning?.max_bcr != null ? `${p.zoning.max_bcr}%` : "-"
                    }
                  />
                  <ComparisonRow
                    label="용적률"
                    parcels={doneParcels}
                    getValue={(p) =>
                      p.zoning?.max_far != null ? `${p.zoning.max_far}%` : "-"
                    }
                  />
                  <ComparisonRow
                    label="토지 면적"
                    parcels={doneParcels}
                    getValue={(p) =>
                      p.zoning?.land_area
                        ? `${p.zoning.land_area.toLocaleString("ko-KR")} m2`
                        : "-"
                    }
                  />
                  <ComparisonRow
                    label="추정 시세"
                    parcels={doneParcels}
                    getValue={(p) =>
                      p.avm?.estimated_price
                        ? formatKRW(p.avm.estimated_price)
                        : "-"
                    }
                    highlight
                  />
                  <ComparisonRow
                    label="m2당 단가"
                    parcels={doneParcels}
                    getValue={(p) =>
                      p.avm?.price_per_sqm
                        ? formatKRW(p.avm.price_per_sqm)
                        : "-"
                    }
                  />
                  <ComparisonRow
                    label="신뢰도"
                    parcels={doneParcels}
                    getValue={(p) =>
                      p.avm?.confidence != null
                        ? `${(p.avm.confidence * 100).toFixed(1)}%`
                        : "-"
                    }
                  />
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Placeholder when no analysis yet */}
      {parcels.every((p) => p.status === "idle") && (
        <Card className="bg-[var(--surface-soft)]">
          <CardContent className="p-8 text-center">
            <p className="text-sm leading-7 text-[var(--text-secondary)]">
              주소를 입력하고 &quot;분석 실행&quot; 버튼을 클릭하면 용도지역 정보와
              AVM 시세 추정 결과가 표시됩니다.
            </p>
          </CardContent>
        </Card>
      )}
    </section>
  );
}

/* ── MetricTile ── */

function MetricTile({
  label,
  value,
  highlight,
  small,
}: {
  label: string;
  value: string;
  highlight?: boolean;
  small?: boolean;
}) {
  return (
    <div
      className={`rounded-[var(--radius-xl)] p-4 ${
        highlight
          ? "bg-[rgba(14,116,144,0.08)] ring-1 ring-[var(--accent-strong)]"
          : "bg-[var(--surface-soft)]"
      }`}
    >
      <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p
        className={`mt-2 font-semibold text-[var(--text-primary)] ${
          small ? "break-all text-xs" : "text-sm"
        }`}
      >
        {value}
      </p>
    </div>
  );
}

/* ── ComparisonRow ── */

function ComparisonRow({
  label,
  parcels,
  getValue,
  highlight,
}: {
  label: string;
  parcels: Parcel[];
  getValue: (p: Parcel) => string;
  highlight?: boolean;
}) {
  return (
    <tr
      className={`border-b border-[var(--line)] last:border-0 ${
        highlight ? "bg-[rgba(14,116,144,0.04)]" : ""
      }`}
    >
      <td className="px-4 py-3 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
        {label}
      </td>
      {parcels.map((p) => (
        <td
          key={p.id}
          className={`px-4 py-3 text-right text-sm ${
            highlight
              ? "font-bold text-[var(--accent-strong)]"
              : "font-semibold text-[var(--text-primary)]"
          }`}
        >
          {getValue(p)}
        </td>
      ))}
    </tr>
  );
}
