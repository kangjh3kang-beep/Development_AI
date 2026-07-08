"use client";

import { Layers } from "lucide-react";
import { PYEONG_SQM } from "@/lib/formatters";

/**
 * 다필지 통합 분석 메타 — 백엔드(_integrated_context)가 내려주는 통합 결과 요약.
 * 규제·인허가·법규·시장 등 통합 분석 응답이 공통으로 싣는다.
 */
export interface IntegratedMeta {
  parcel_count?: number | null;
  total_area_sqm?: number | null;
  dominant_zone?: string | null;
}

/**
 * 통합 분석 고지 뱃지.
 *
 * 결과가 '대표 1필지'가 아니라 'N필지 통합면적·우세용도' 기준으로 산출됐음을 사용자에게 명시한다
 * (근거·투명성 — 내가 올린 필지대로 분석됐는지 검증 가능). integrated가 없거나 1필지면
 * 아무것도 렌더하지 않는다(단일필지 분석은 기존 그대로 = 무회귀).
 */
export function IntegratedParcelsBadge({
  integrated,
  className = "",
}: {
  integrated?: IntegratedMeta | null;
  className?: string;
}) {
  const n = integrated?.parcel_count ?? 0;
  const area = integrated?.total_area_sqm ?? 0;
  if (!integrated || n < 2 || area <= 0) return null;

  const py = Math.round(area / PYEONG_SQM);
  const zone = (integrated.dominant_zone || "").trim();
  const mixed = zone === "mixed_review_required";

  return (
    <div
      className={`inline-flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-[color-mix(in_srgb,var(--accent-strong)_30%,transparent)] bg-[color-mix(in_srgb,var(--accent-strong)_8%,transparent)] px-3 py-1.5 text-xs font-semibold text-[var(--text-secondary)] ${className}`}
    >
      <span className="inline-flex items-center gap-1.5 text-[var(--accent-strong)]">
        <Layers className="size-3.5" aria-hidden />통합 {n}필지 기준
      </span>
      <span>
        · 통합면적{" "}
        <b className="text-[var(--text-primary)] tabular-nums">{Math.round(area).toLocaleString("ko-KR")}㎡</b>{" "}
        ({py.toLocaleString("ko-KR")}평)
      </span>
      {zone && !mixed && (
        <span>· 우세용도 <b className="text-[var(--text-primary)]">{zone}</b></span>
      )}
      {mixed && (
        <span className="text-[var(--status-warning)]">· 용도지역 혼재 — 개별 검토 필요</span>
      )}
    </div>
  );
}
