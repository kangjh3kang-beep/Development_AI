"use client";

/**
 * BuildableOptionsCard — 건축가능항목 선정·랭킹(Stage 1) 공용 표시 카드(DRY·재사용).
 *
 * 백엔드 comprehensive_analysis_service가 result.buildable_options(rank_buildable_options 산출)에
 * 싣는 '이 부지에서 무엇을 지을 수 있는가'를 인허가가능성×가용용적률 랭킹으로 노출한다.
 * 그간 LLM 그라운딩(내러티브)으로만 소비되고 화면 정량 카드가 없던 orphan handoff를 해소한다.
 *
 * 계약(result.buildable_options):
 *   { options[], top_recommendation, current_zone, summary, disclaimer }
 *   options[] 각 항목: { product, achievable_far_pct, permit_feasibility(현행|상|중|하),
 *                        permit_difficulty, via, is_current, score, similar_designs? }
 *
 * 정직·무목업: 키 없음/options 비었으면 렌더하지 않는다. 종상향 far는 예상치(현행은 사실값)임을 표기.
 */

import { useState } from "react";

interface SimilarDesigns {
  results?: Array<{ title?: string; drawing_type?: string; total_area_sqm?: number | null; score?: number }>;
  count?: number;
  skipped_reason?: string | null;
}

export interface BuildableOption {
  product?: string;
  achievable_far_pct?: number | null;
  permit_feasibility?: string; // 현행 | 상 | 중 | 하
  permit_difficulty?: string;
  via?: string;
  zone?: string;
  is_current?: boolean;
  is_upzoning?: boolean;
  score?: number;
  similar_designs?: SimilarDesigns | null;
}

export interface BuildableOptions {
  options?: BuildableOption[];
  top_recommendation?: BuildableOption | null;
  current_zone?: string | null;
  summary?: string;
  disclaimer?: string;
}

// 인허가가능성 → 배지 토큰(현행=용이=success, 상=info, 중=warning, 하=error).
const FEASIBILITY_TOKEN: Record<string, string> = {
  현행: "var(--status-success)",
  상: "var(--status-info)",
  중: "var(--status-warning)",
  하: "var(--status-error)",
};

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

export function BuildableOptionsCard({
  data,
  defaultOpen = true,
}: {
  data?: BuildableOptions | null;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const options = (data?.options ?? []).filter((o) => o && o.product);
  if (!data || options.length === 0) return null;

  const top = data.top_recommendation ?? options[0];

  return (
    <div className="overflow-hidden rounded-2xl border border-[var(--accent-strong)]/25 bg-[var(--surface-strong)]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 p-4 text-left transition-colors hover:bg-[var(--surface-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-strong)]"
        aria-expanded={open}
      >
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="text-sm font-black text-[var(--text-primary)]">건축가능항목 랭킹</span>
          <span className="text-[10px] text-[var(--text-secondary)]">인허가가능성 × 가용용적률</span>
          {top?.product ? (
            <Chip token="var(--accent-strong)">최우선 {top.product}</Chip>
          ) : null}
        </div>
        <span className="shrink-0 text-[11px] text-[var(--text-secondary)]">{open ? "접기 ▲" : "자세히 ▼"}</span>
      </button>

      {open ? (
        <div className="space-y-2.5 border-t border-[var(--line)] p-4">
          {data.summary ? (
            <p className="text-xs leading-relaxed text-[var(--text-secondary)]">{data.summary}</p>
          ) : null}

          <ul className="space-y-1.5">
            {options.map((o, i) => {
              const token = FEASIBILITY_TOKEN[o.permit_feasibility ?? ""] ?? "var(--status-warning)";
              return (
                <li
                  key={`${o.product}-${o.zone}-${i}`}
                  className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[11px] font-bold text-[var(--text-tertiary)]">{i + 1}</span>
                    <span className="text-sm font-bold text-[var(--text-primary)]">{o.product}</span>
                    {o.achievable_far_pct != null ? (
                      <span className="text-xs font-semibold text-[var(--accent-strong)]">
                        가용 용적률 {o.achievable_far_pct}%
                      </span>
                    ) : null}
                    <Chip token={token}>인허가 {o.permit_feasibility}</Chip>
                    <Chip token={o.is_current ? "var(--status-success)" : "var(--status-info)"}>
                      {o.is_current ? "현행 가능" : "종상향 전제(예상)"}
                    </Chip>
                  </div>
                  <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
                    {o.via ? `달성경로: ${o.via}` : ""}
                    {o.zone ? ` · ${o.zone}` : ""}
                    {o.permit_difficulty ? ` · ${o.permit_difficulty}` : ""}
                  </p>

                  {/* 유사 설계 도면(Stage 3 시장조사 — 참조 라이브러리 검색) */}
                  {o.similar_designs && (o.similar_designs.count ?? 0) > 0 ? (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      <span className="text-[10px] text-[var(--text-tertiary)]">유사 설계:</span>
                      {(o.similar_designs.results ?? []).slice(0, 4).map((m, k) => (
                        <span
                          key={k}
                          title={m.title}
                          className="max-w-[12rem] truncate rounded border border-[var(--line)] bg-[var(--surface-muted)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)]"
                        >
                          {m.drawing_type ? `[${m.drawing_type}] ` : ""}
                          {m.title}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>

          {data.disclaimer ? (
            <p className="text-[10px] leading-relaxed text-[var(--text-tertiary)]">※ {data.disclaimer}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
