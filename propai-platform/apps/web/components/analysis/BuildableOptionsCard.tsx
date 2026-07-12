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
 *   ★신규(additive): tier("current"|"upzoning" — 부재 시 is_current에서 파생),
 *                     blocked_reasons?(종상향 항목이 비연접 등으로 구역성립 불확실할 때 사유 배열)
 *
 * 정직·무목업: 키 없음/options 비었으면 렌더하지 않는다. 종상향 far는 예상치(현행은 사실값)임을 표기.
 *
 * ★스토리라인 정정(2026-07): 그간 헤드라인("최우선 X") 칩이 백엔드 top_recommendation을
 *   무조건 신뢰해, 종상향(예상치) 항목이 "최우선"으로 보여 현행 가능한 것처럼 오독될 위험이
 *   있었다. 이제 ①현행 가능 그룹과 ②종상향 잠재 그룹으로 나눠 렌더하고, 헤드라인은 현행
 *   1위 기준으로 고정한다(종상향 1위는 별도 조건부 문장으로 분리).
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
  /** ★신규(additive): 백엔드가 명시하면 그대로 신뢰, 없으면 is_current로 파생(하위호환). */
  tier?: "current" | "upzoning" | null;
  /** ★신규(additive): 종상향 항목이 막혀있는 사유(예: "비연접 파편 — 구역 성립 불확실"). */
  blocked_reasons?: string[] | null;
  score?: number;
  similar_designs?: SimilarDesigns | null;
}

/** 항목의 현행/종상향 구분 — tier 명시값 우선, 없으면 is_current에서 파생(무회귀). */
function resolveTier(o: BuildableOption): "current" | "upzoning" {
  if (o.tier === "current" || o.tier === "upzoning") return o.tier;
  return o.is_current ? "current" : "upzoning";
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

/** 랭킹 1건 행(현행·종상향 그룹 공용 — 중복 렌더 방지). */
function OptionRow({ o, rank }: { o: BuildableOption; rank: number }) {
  const token = FEASIBILITY_TOKEN[o.permit_feasibility ?? ""] ?? "var(--status-warning)";
  const tier = resolveTier(o);
  const blockedReasons = (o.blocked_reasons ?? []).filter((r) => r && r.trim());

  return (
    <li className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-bold text-[var(--text-tertiary)]">{rank}</span>
        <span className="text-sm font-bold text-[var(--text-primary)]">{o.product}</span>
        {o.achievable_far_pct != null ? (
          <span className="text-xs font-semibold text-[var(--accent-strong)]">
            가용 용적률 {o.achievable_far_pct}%
          </span>
        ) : null}
        <Chip token={token}>인허가 {o.permit_feasibility ?? "확인필요"}</Chip>
        <Chip token={tier === "current" ? "var(--status-success)" : "var(--status-info)"}>
          {tier === "current" ? "현행 가능" : "종상향 전제(예상)"}
        </Chip>
        {/* 종상향인데 비연접 등으로 구역 성립이 불확실한 경우 정직 배지(가짜 가능성 표시 금지). */}
        {tier === "upzoning" && blockedReasons.length > 0 ? (
          <Chip token="var(--status-error)">구역 성립 불확실</Chip>
        ) : null}
      </div>
      <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
        {o.via ? `달성경로: ${o.via}` : ""}
        {o.zone ? ` · ${o.zone}` : ""}
        {o.permit_difficulty ? ` · ${o.permit_difficulty}` : ""}
      </p>

      {/* 종상향 차단 사유(있을 때만) — 예: "비연접 파편 — 구역 성립 불확실". */}
      {blockedReasons.length > 0 ? (
        <p className="mt-1 text-[10px] leading-relaxed text-[var(--status-error)]">
          {blockedReasons.join(" · ")}
        </p>
      ) : null}

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

  // ① 현행 가능(즉시 추진) 그룹 먼저, ② 종상향 잠재(조건부·예상치) 그룹 뒤 — 스토리라인 분리.
  const currentOptions = options.filter((o) => resolveTier(o) === "current");
  const upzoningOptions = options.filter((o) => resolveTier(o) === "upzoning");

  // 헤드라인 "최우선 사업유형"은 현행 1위 기준으로 고정한다(백엔드 top_recommendation이
  // 종상향 항목이면, 종상향을 "최우선"인 것처럼 오독시킬 수 있어 현행 1위로 정정한다).
  const topRecTier = data.top_recommendation ? resolveTier(data.top_recommendation) : null;
  const headlineTop =
    topRecTier === "current" ? data.top_recommendation : currentOptions[0] ?? data.top_recommendation ?? options[0];
  const upzoningTop = upzoningOptions[0] ?? null;

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
          {headlineTop?.product ? (
            <Chip token="var(--accent-strong)">최우선 {headlineTop.product}</Chip>
          ) : null}
        </div>
        <span className="shrink-0 text-[11px] text-[var(--text-secondary)]">{open ? "접기 ▲" : "자세히 ▼"}</span>
      </button>

      {open ? (
        <div className="space-y-2.5 border-t border-[var(--line)] p-4">
          {data.summary ? (
            <p className="text-xs leading-relaxed text-[var(--text-secondary)]">{data.summary}</p>
          ) : null}

          {/* 종상향 1위는 "최우선"과 분리된 조건부 문장으로만 언급(현행과 혼동 방지).
              현행 옵션이 하나도 없으면 헤드라인 자체가 이미 이 종상향 항목이므로 중복 표기하지 않는다. */}
          {currentOptions.length > 0 && upzoningTop?.product ? (
            <p className="text-[11px] text-[var(--text-secondary)]">
              참고(조건부 예상치): 종상향 전제 시 <span className="font-semibold text-[var(--status-info)]">{upzoningTop.product}</span>가
              유력하나, 구역 성립·조례 개정 등 전제 조건 충족이 필요합니다.
            </p>
          ) : null}

          {currentOptions.length > 0 ? (
            <div className="space-y-1.5">
              <p className="text-[10px] font-bold text-[var(--text-hint)]">① 현행 가능 (즉시 추진)</p>
              <ul className="space-y-1.5">
                {currentOptions.map((o, i) => (
                  <OptionRow key={`current-${o.product}-${o.zone}-${i}`} o={o} rank={i + 1} />
                ))}
              </ul>
            </div>
          ) : null}

          {upzoningOptions.length > 0 ? (
            <div className="space-y-1.5">
              <p className="text-[10px] font-bold text-[var(--text-hint)]">② 종상향 잠재 (조건부 — 예상치)</p>
              <ul className="space-y-1.5">
                {upzoningOptions.map((o, i) => (
                  <OptionRow key={`upzoning-${o.product}-${o.zone}-${i}`} o={o} rank={i + 1} />
                ))}
              </ul>
            </div>
          ) : null}

          {data.disclaimer ? (
            <p className="text-[10px] leading-relaxed text-[var(--text-tertiary)]">※ {data.disclaimer}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
