"use client";

/**
 * 규제 계층 종합 렌더 — 공용 컴포넌트.
 *
 * /regulation/analyze 응답(계층·정량 한도·영향도·LLM 통합 해석)을 분류별로 렌더한다.
 * 부동산 규제 연동(RegulationsWorkspaceClient)과 프로젝트 법규 검토
 * (ProjectLegalWorkspaceClient)에서 공용으로 사용한다. (회귀 0 — 기존 렌더 1:1 동일)
 */

import { Card, CardContent } from "@propai/ui";
import { LegalRefChip } from "@/components/common/LegalRefChip";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";
import type { Locale } from "@/i18n/config";

/* ── Types (기존 RegulationsWorkspaceClient와 1:1 동일) ── */

export type LimitTrio = { legal: number | null; ordinance: number | null; effective: number | null; unit: string };
export type HierItem = { name: string; ref?: string; desc?: string };
/** 법령 원문링크 근거(레지스트리 get_legal_refs 출력) — url은 백엔드 제공값만. */
export type LegalRef = {
  key?: string | null;
  law_name?: string | null;
  article?: string | null;
  title?: string | null;
  url?: string | null;
  url_status?: string | null;
};
/** 수치 산출 트레이스 1건(EvidencePanel 항목 원천). */
export type EvidenceTrace = {
  label?: string | null;
  value?: string | number | null;
  basis?: string | null;
  /** 이 항목과 연결할 법령 근거키(legal_refs[].key와 매칭해 url 주입). */
  legal_ref_key?: string | null;
};
/** 계층 레벨 — WP-H 신뢰 레이어로 legal_refs[]가 가산될 수 있음(옵셔널·하위호환). */
export type HierLevel = { level: string; items: HierItem[]; legal_refs?: LegalRef[] | null };
export type District = { name: string; code?: string; impact: "상" | "중" | "하" | string; status?: string; register_date?: string };
export type RegAI = {
  generated?: boolean;
  summary?: string;
  key_constraints?: string[];
  dev_impact?: string;
  strategies?: string[];
  opportunities?: string[];
  risks?: string[];
};
export type RegResult = {
  address: string;
  pnu: string | null;
  zone_type: string | null;
  zone_type_secondary: string | null;
  land_area_sqm: number | null;
  land_category: string | null;
  land_use_situation: string | null;
  limits: { bcr: LimitTrio; far: LimitTrio; height: { value: number | null; unit: string }; parking: { description: string } };
  hierarchy: HierLevel[];
  districts: District[];
  ai: RegAI | null;
  /** WP-H 신뢰 메타데이터(가산·옵셔널) — 없으면(구버전) 렌더 생략. */
  evidence?: EvidenceTrace[] | null;
};

const IMPACT_STYLE: Record<string, string> = {
  상: "bg-rose-500/15 text-rose-400 border-rose-500/30",
  중: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  하: "bg-emerald-500/12 text-emerald-400 border-emerald-500/25",
};
const LEVEL_META: Record<string, { color: string; icon: string }> = {
  "상위법령": { color: "var(--accent-strong)", icon: "⚖️" },
  "도시·군계획 / 지구단위계획": { color: "#8b5cf6", icon: "🗺️" },
  "지자체 조례": { color: "#3b82f6", icon: "📋" },
  "개별 적용 규제·지구·구역": { color: "#f59e0b", icon: "🚧" },
};

function pyeong(sqm: number | null): string {
  return sqm ? `${Math.round(sqm / 3.305785).toLocaleString()}평` : "";
}

/** legal_refs[]를 key로 인덱싱(법령 근거 url 주입용). 잘못된 항목은 건너뛴다. */
function indexLegalRefs(refs?: LegalRef[] | null): Record<string, LegalRef> {
  const map: Record<string, LegalRef> = {};
  for (const ref of refs ?? []) {
    if (ref && typeof ref.key === "string" && ref.key.trim()) map[ref.key.trim()] = ref;
  }
  return map;
}

/** evidence[] + 계층 전체 legal_refs[]를 EvidencePanel 항목으로 결합.
 *  각 trace의 legal_ref_key를 legal_refs 인덱스와 매칭해 url(백엔드 제공값)을 주입한다.
 *  매칭 실패/부재 시 legalRef 생략(텍스트만) — 가짜 링크 금지. label 없는 항목은 제외. */
function buildEvidenceItems(
  evidence?: EvidenceTrace[] | null,
  legalRefs?: LegalRef[] | null,
): EvidenceItem[] {
  const traces = Array.isArray(evidence) ? evidence : [];
  if (traces.length === 0) return [];
  const refIndex = indexLegalRefs(legalRefs);
  const items: EvidenceItem[] = [];
  for (const trace of traces) {
    if (!trace || typeof trace !== "object") continue;
    const label = (trace.label ?? "").toString().trim();
    if (!label) continue;
    const value = trace.value ?? "—";
    const key = trace.legal_ref_key?.trim();
    const ref = key ? refIndex[key] : undefined;
    items.push({
      label,
      value: typeof value === "number" ? value : String(value),
      basis: trace.basis ?? null,
      legalRef:
        ref && typeof ref.law_name === "string" && ref.law_name.trim()
          ? { lawName: ref.law_name, article: ref.article, title: ref.title, url: ref.url }
          : null,
    });
  }
  return items;
}

/** 계층 전체 노드의 legal_refs[]를 평탄화(중복 key 제거) — evidence url 매칭 인덱스용. */
function flattenLegalRefs(hierarchy?: HierLevel[]): LegalRef[] {
  const seen = new Set<string>();
  const out: LegalRef[] = [];
  for (const lv of hierarchy ?? []) {
    for (const ref of lv?.legal_refs ?? []) {
      const k = typeof ref?.key === "string" ? ref.key.trim() : "";
      if (!k || seen.has(k)) continue;
      seen.add(k);
      out.push(ref);
    }
  }
  return out;
}

/* ── 공용 종합 렌더 ── */

export function RegulationHierarchyView({
  result,
  locale: _locale,
}: {
  result: RegResult;
  locale: Locale;
}) {
  // 한도 산출 근거(evidence[] + 계층 legal_refs[]) — 항목이 없으면(구버전) 자동 미표시.
  const allLegalRefs = flattenLegalRefs(result.hierarchy);
  const evidenceItems = buildEvidenceItems(result.evidence, allLegalRefs);

  return (
    <>
      {/* 부지 요약 + 정량 한도 */}
      <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
        <CardContent className="p-6">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-lg bg-[var(--accent-soft)] px-2.5 py-1 text-xs font-black text-[var(--accent-strong)]">
              {result.zone_type || "용도미상"}
            </span>
            {result.zone_type_secondary && (
              <span className="rounded-lg bg-violet-500/15 px-2.5 py-1 text-xs font-black text-violet-400">
                + {result.zone_type_secondary}
              </span>
            )}
            <span className="text-xs text-[var(--text-secondary)]">
              {result.land_area_sqm ? `${result.land_area_sqm.toLocaleString()}㎡ (${pyeong(result.land_area_sqm)})` : ""}
              {result.land_category ? ` · 지목 ${result.land_category}` : ""}
              {result.land_use_situation ? ` · ${result.land_use_situation}` : ""}
            </span>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <LimitCard label="건폐율" trio={result.limits.bcr} />
            <LimitCard label="용적률" trio={result.limits.far} />
            <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3.5">
              <p className="text-[11px] font-bold text-[var(--text-secondary)]">높이 제한</p>
              <p className="mt-1 text-lg font-black text-[var(--text-primary)]">
                {result.limits.height.value != null ? `${result.limits.height.value}${result.limits.height.unit}` : "제한 없음"}
              </p>
            </div>
            <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3.5">
              <p className="text-[11px] font-bold text-[var(--text-secondary)]">주차 기준</p>
              <p className="mt-1 text-xs font-semibold leading-snug text-[var(--text-primary)]">{result.limits.parking.description}</p>
            </div>
          </div>

          {/* 한도 산출 근거(WP-H evidence[] + legal_refs[]) — 빈 items면 자동 미표시(구버전 무손상). */}
          {evidenceItems.length > 0 && (
            <div className="mt-4">
              <EvidencePanel items={evidenceItems} title="한도 산출 근거" />
            </div>
          )}
        </CardContent>
      </Card>

      {/* AI 통합 해석 */}
      {result.ai && (
        <Card className="rounded-[var(--radius-2xl)] border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/5 shadow-[var(--shadow-md)]">
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <p className="text-sm font-black text-[var(--accent-strong)]">🧠 AI 통합 규제 해석</p>
              <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${result.ai.generated ? "border-[var(--accent-strong)]/30 text-[var(--accent-strong)]" : "border-[var(--line-strong)] text-[var(--text-tertiary)]"}`}>
                {result.ai.generated ? "AI 분석" : "규칙기반"}
              </span>
            </div>
            {result.ai.summary && <p className="mt-2 text-sm leading-relaxed text-[var(--text-primary)]">{result.ai.summary}</p>}
            {result.ai.dev_impact && (
              <p className="mt-2 text-xs leading-relaxed text-[var(--text-secondary)]"><b className="text-[var(--text-primary)]">개발 영향 ·</b> {result.ai.dev_impact}</p>
            )}
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <AiList title="🎯 핵심 제약" items={result.ai.key_constraints} tone="rose" />
              <AiList title="🛠 대응 전략" items={result.ai.strategies} tone="emerald" />
              <AiList title="✨ 기회 요인" items={result.ai.opportunities} tone="sky" />
              <AiList title="⚠ 리스크" items={result.ai.risks} tone="amber" />
            </div>
          </CardContent>
        </Card>
      )}

      {/* 규제 계층 스택 */}
      <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
        <CardContent className="p-6">
          <p className="text-sm font-black text-[var(--text-primary)]">📚 적용 규제 계층 (상위계획 → 개별규제)</p>
          <div className="mt-4 space-y-3">
            {(result.hierarchy ?? []).map((lv, i) => {
              const meta = LEVEL_META[lv.level] || { color: "var(--text-secondary)", icon: "•" };
              return (
                <div key={lv.level} className="relative rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4"
                  style={{ marginLeft: `${i * 14}px`, borderLeftColor: meta.color, borderLeftWidth: 3 }}>
                  <p className="text-xs font-black" style={{ color: meta.color }}>
                    {meta.icon} {lv.level} <span className="text-[var(--text-hint)]">({lv.items?.length})</span>
                  </p>
                  <div className="mt-2 grid gap-1.5">
                    {(lv.items ?? []).map((it, j) => (
                      <div key={j} className="flex flex-wrap items-baseline gap-x-2 text-xs">
                        <span className="font-bold text-[var(--text-primary)]">{it.name}</span>
                        {it.ref && it.ref !== "-" && <span className="text-[var(--accent-strong)]">{it.ref}</span>}
                        {it.desc && <span className="text-[var(--text-secondary)]">— {it.desc}</span>}
                      </div>
                    ))}
                  </div>

                  {/* 노드 법령 원문링크(WP-H legal_refs[]) — 옵셔널 가드(구버전·zone 미확정 시 미표시).
                      url은 백엔드 제공값만(LegalRefChip이 미검증 url은 텍스트로 폴백). */}
                  {Array.isArray(lv.legal_refs) && lv.legal_refs.length > 0 && (
                    <div className="mt-2.5 flex flex-wrap gap-1.5 border-t border-[var(--line)] pt-2">
                      {lv.legal_refs.map((ref, k) =>
                        ref?.law_name ? (
                          <LegalRefChip
                            key={`${ref.key ?? ref.law_name}-${k}`}
                            lawName={ref.law_name}
                            article={ref.article}
                            title={ref.title}
                            url={ref.url}
                          />
                        ) : null,
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* 적용 규제·지구·구역 전수 (영향도) */}
      {(result.districts?.length ?? 0) > 0 && (
        <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
          <CardContent className="p-6">
            <p className="text-sm font-black text-[var(--text-primary)]">
              🚧 적용 규제·지구·구역 전수 <span className="text-[var(--text-hint)]">({result.districts?.length})</span>
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {(result.districts ?? []).map((d, i) => (
                <span key={i} className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[11px] font-bold ${IMPACT_STYLE[d.impact] || "border-[var(--line)] text-[var(--text-secondary)]"}`}>
                  {d.name}
                  <span className="opacity-70">{d.impact}</span>
                </span>
              ))}
            </div>
            <p className="mt-3 text-[11px] text-[var(--text-hint)]">영향도: <span className="text-rose-400">상</span>(개발 결정적) · <span className="text-amber-400">중</span>(밀도·절차 영향) · <span className="text-emerald-400">하</span>(일반)</p>
          </CardContent>
        </Card>
      )}
    </>
  );
}

/* ── Sub-components (기존 RegulationsWorkspaceClient와 1:1 동일) ── */

function LimitCard({ label, trio }: { label: string; trio: LimitTrio }) {
  const eff = trio.effective;
  const tightened = trio.legal != null && trio.ordinance != null && trio.ordinance < trio.legal;
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3.5">
      <p className="text-[11px] font-bold text-[var(--text-secondary)]">{label} 한도</p>
      <p className="mt-1 text-lg font-black text-[var(--accent-strong)]">{eff != null ? `${eff}${trio.unit}` : "-"}</p>
      <div className="mt-1.5 space-y-0.5 text-[10px] text-[var(--text-hint)]">
        <div className="flex justify-between"><span>법정</span><span>{trio.legal != null ? `${trio.legal}${trio.unit}` : "-"}</span></div>
        <div className="flex justify-between"><span>조례</span><span className={tightened ? "text-amber-400 font-bold" : ""}>{trio.ordinance != null ? `${trio.ordinance}${trio.unit}` : "-"}</span></div>
      </div>
      {tightened && <p className="mt-1 text-[10px] font-bold text-amber-400">조례 강화 ↓</p>}
    </div>
  );
}

function AiList({ title, items, tone }: { title: string; items?: string[]; tone: string }) {
  if (!items || items.length === 0) return null;
  const color: Record<string, string> = {
    rose: "text-rose-400", emerald: "text-emerald-400", sky: "text-sky-400", amber: "text-amber-400",
  };
  return (
    <div>
      <p className={`text-xs font-bold ${color[tone] || "text-[var(--text-primary)]"}`}>{title}</p>
      <ul className="mt-1 space-y-0.5 text-xs text-[var(--text-secondary)]">
        {items.map((it, i) => <li key={i}>· {it}</li>)}
      </ul>
    </div>
  );
}
