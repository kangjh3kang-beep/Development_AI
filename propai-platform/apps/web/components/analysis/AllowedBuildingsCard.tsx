"use client";

/**
 * AllowedBuildingsCard — 현행(지금) 허용 건축물 카드 (국토계획법 시행령 별표2~20).
 *
 * 백엔드 comprehensive_analysis_service가 development_type_analyzer를 소비해
 * result.allowed_buildings에 싣는 "이 용도지역에서 지금 지을 수 있는 것"을 화면에 낸다.
 * 자연녹지 등 비주거·비상업 용도지역도 별표17 허용유형(단독주택·제1종근생·종교·교육·수련 등)을
 * 얻지만, 그간 화면 소비처가 없어 orphan handoff였다(감사 적발 — M코드 표시와 별개 갭).
 *
 * 스토리 배치: BuildableOptionsCard(랭킹) 위에 둔다 — "현재 지을 수 있는 것" → "그 중 사업성 1위".
 *
 * 계약(result.allowed_buildings):
 *   { zone_type, source, allowed_types[], restricted_types[], recommended_type,
 *     recommendation_reason, legal_basis }
 *   allowed_types[] 각 항목: { type_name, type_code, conditions, recommended, max_gfa_sqm,
 *                              remarks, legal_basis }
 *   restricted_types[] 각 항목: { type_name, reason }
 *
 * 정직·무목업: allowed_types가 하나도 없으면 렌더하지 않는다(빈 카드 금지).
 */

import { useState } from "react";

export interface AllowedBuildingType {
  type_name?: string | null;
  type_code?: string | null;
  conditions?: string | null;
  recommended?: boolean | null;
  max_gfa_sqm?: number | null;
  remarks?: string | null;
  legal_basis?: string | null;
}

export interface RestrictedBuildingType {
  type_name?: string | null;
  reason?: string | null;
}

export interface AllowedBuildings {
  zone_type?: string | null;
  source?: string | null;
  allowed_types?: AllowedBuildingType[] | null;
  restricted_types?: RestrictedBuildingType[] | null;
  recommended_type?: string | null;
  recommendation_reason?: string | null;
  legal_basis?: string | null;
}

function Chip({ token, children }: { token: string; children: React.ReactNode }) {
  return (
    <span
      className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
      style={{
        color: token,
        background: `color-mix(in srgb, ${token} 14%, transparent)`,
        border: `1px solid color-mix(in srgb, ${token} 38%, transparent)`,
      }}
    >
      {children}
    </span>
  );
}

export function AllowedBuildingsCard({
  data,
  floorCap,
  defaultOpen = true,
}: {
  data?: AllowedBuildings | null;
  /** ★effective_far.floor_cap — 구조상한이 층수로 걸릴 때(예: 4층 이하) 헤더 배지로 연동. 없으면 미표시. */
  floorCap?: number | null;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const allowedTypes = (data?.allowed_types ?? []).filter((t) => t && (t.type_name ?? "").trim());
  const restrictedTypes = (data?.restricted_types ?? []).filter((t) => t && (t.type_name ?? "").trim());
  if (!data || allowedTypes.length === 0) return null;

  return (
    <div className="overflow-hidden rounded-2xl border border-teal-500/30 bg-[var(--surface-strong)]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 p-4 text-left transition-colors hover:bg-[var(--surface-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-strong)]"
        aria-expanded={open}
      >
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="text-sm font-black text-[var(--text-primary)]">현행 허용건축물</span>
          {data.zone_type ? (
            <span className="text-[10px] text-[var(--text-secondary)]">{data.zone_type}</span>
          ) : null}
          {floorCap != null ? (
            <Chip token="var(--status-warning)">{Math.round(floorCap)}층 이하 제한</Chip>
          ) : null}
        </div>
        <span className="shrink-0 text-[11px] text-[var(--text-secondary)]">{open ? "접기 ▲" : "자세히 ▼"}</span>
      </button>

      {open ? (
        <div className="space-y-3 border-t border-[var(--line)] p-4">
          {/* 허용 유형 칩 — 추천 유형은 강조, 나머지는 중립. */}
          <div className="flex flex-wrap gap-2">
            {allowedTypes.map((t, i) => (
              <span
                key={`allowed-${t.type_code ?? i}`}
                title={[t.conditions, t.remarks, t.legal_basis].filter(Boolean).join(" · ") || undefined}
                className={
                  t.recommended
                    ? "inline-flex items-center gap-1.5 rounded-lg border border-[var(--accent-strong)]/40 bg-[var(--accent-strong)]/10 px-3 py-1.5 text-[11px] font-bold text-[var(--accent-strong)]"
                    : "inline-flex items-center gap-1.5 rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-1.5 text-[11px] font-bold text-[var(--text-primary)]"
                }
              >
                {t.type_name}
                {t.conditions ? (
                  <span className="text-[9px] font-medium text-[var(--text-hint)]">{t.conditions}</span>
                ) : null}
              </span>
            ))}
          </div>

          {/* 추천 유형 사유(있을 때만). */}
          {data.recommended_type ? (
            <p className="text-[11px] text-[var(--text-secondary)]">
              <span className="font-bold text-[var(--accent-strong)]">추천 유형: {data.recommended_type}</span>
              {data.recommendation_reason ? ` — ${data.recommendation_reason}` : ""}
            </p>
          ) : null}

          {/* 제한 유형(있을 때만) — 지을 수 없는 유형을 정직 표기. */}
          {restrictedTypes.length > 0 ? (
            <div className="border-t border-[var(--line)] pt-2">
              <p className="mb-1 text-[10px] font-bold text-[var(--text-hint)]">제한 유형</p>
              <div className="flex flex-wrap gap-1.5">
                {restrictedTypes.map((t, i) => (
                  <span
                    key={`restricted-${i}`}
                    title={t.reason || undefined}
                    className="inline-flex items-center rounded-lg border border-[var(--status-error)]/30 bg-[var(--status-error)]/5 px-2.5 py-1 text-[10px] font-semibold text-[var(--status-error)]"
                  >
                    {t.type_name}
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          {/* 법령 근거(별표) — 조문 딥링크 대신 별표 명칭 텍스트로 표기(가짜 링크 금지). */}
          {data.legal_basis || data.source ? (
            <p className="text-[10px] text-[var(--text-hint)]">근거: {data.legal_basis || data.source}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
