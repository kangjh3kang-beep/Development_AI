"use client";

/**
 * 부동산 규제 연동 — 규제 계층 대시보드.
 *
 * 부지에 적용되는 상위법령 → 도시·군계획/지구단위 → 지자체 조례 → 개별 적용규제를
 * 계층으로 시각화하고, 정량 한도(건폐/용적/높이/주차) 법정·조례·실효 비교와
 * AI 통합 해석, 필지 구획도를 함께 제공한다. (POST /regulation/analyze)
 */

import { useCallback, useState } from "react";
import { Card, CardContent, Input } from "@propai/ui";
import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { ParcelBoundaryMap } from "@/components/map/ParcelBoundaryMap";
import { ExpertPanelCard } from "@/components/common/ExpertPanelCard";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import type { Locale } from "@/i18n/config";

type LimitTrio = { legal: number | null; ordinance: number | null; effective: number | null; unit: string };
type HierItem = { name: string; ref?: string; desc?: string };
type HierLevel = { level: string; items: HierItem[] };
type District = { name: string; code?: string; impact: "상" | "중" | "하" | string; status?: string; register_date?: string };
type RegAI = {
  generated?: boolean;
  summary?: string;
  key_constraints?: string[];
  dev_impact?: string;
  strategies?: string[];
  opportunities?: string[];
  risks?: string[];
};
type RegResult = {
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

export function RegulationsWorkspaceClient({ locale: _locale }: { locale: Locale }) {
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const [addr, setAddr] = useState("");
  const [pnu, setPnu] = useState("");
  const [useLlm, setUseLlm] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<RegResult | null>(null);

  const run = useCallback(async () => {
    const target = addr || siteAnalysis?.address || "";
    if (!target) { setError("주소를 먼저 선택하거나 입력하세요."); return; }
    setLoading(true); setError(""); setResult(null);
    try {
      const r = await apiClient.post<RegResult>("/regulation/analyze", {
        body: { address: target, pnu: pnu.trim() || siteAnalysis?.pnu || undefined, use_llm: useLlm },
        useMock: false, timeoutMs: 120000,
      });
      setResult(r);
    } catch {
      setError("규제 분석에 실패했습니다. 잠시 후 다시 시도하세요.");
    } finally {
      setLoading(false);
    }
  }, [addr, pnu, useLlm, siteAnalysis]);

  return (
    <div className="grid gap-6">
      {/* Hero + 입력 */}
      <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
        <CardContent className="p-6">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🏛️</span>
            <div>
              <h1 className="text-lg font-black text-[var(--text-primary)]">부동산 규제 연동</h1>
              <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                해당 토지에 적용되는 상위법령·도시·군계획·지자체 조례·개별 규제를 계층으로 정리하고,
                건폐율·용적률·높이·주차 한도와 AI 통합 해석을 제공합니다.
              </p>
            </div>
          </div>

          <div className="mt-5">
            <ProjectAddressInput
              value={addr}
              onChange={setAddr}
              label="분석 대상지 주소"
              placeholder="프로젝트를 선택하거나 주소를 검색/입력하세요"
              pickerLabel="분석 히스토리"
              disabled={loading}
            />
          </div>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <Input value={pnu} onChange={(e) => setPnu(e.target.value)} placeholder="PNU 코드 (선택)" disabled={loading} />
            <label className="flex items-center gap-2 text-xs font-semibold text-[var(--text-secondary)]">
              <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)}
                className="h-4 w-4 accent-[var(--accent-strong)]" disabled={loading} />
              🤖 AI 통합 해석 포함
            </label>
          </div>
          <div className="mt-4 flex items-center gap-3">
            <button onClick={run} disabled={loading}
              className="rounded-xl bg-[var(--accent-strong)] px-5 py-2.5 text-sm font-black text-white hover:opacity-90 disabled:opacity-50">
              {loading ? "규제 분석 중…" : "🔎 규제 분석 실행"}
            </button>
            {error && <span className="text-xs font-semibold text-rose-500">{error}</span>}
          </div>
        </CardContent>
      </Card>

      {result && (
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
                {result.hierarchy.map((lv, i) => {
                  const meta = LEVEL_META[lv.level] || { color: "var(--text-secondary)", icon: "•" };
                  return (
                    <div key={lv.level} className="relative rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4"
                      style={{ marginLeft: `${i * 14}px`, borderLeftColor: meta.color, borderLeftWidth: 3 }}>
                      <p className="text-xs font-black" style={{ color: meta.color }}>
                        {meta.icon} {lv.level} <span className="text-[var(--text-hint)]">({lv.items.length})</span>
                      </p>
                      <div className="mt-2 grid gap-1.5">
                        {lv.items.map((it, j) => (
                          <div key={j} className="flex flex-wrap items-baseline gap-x-2 text-xs">
                            <span className="font-bold text-[var(--text-primary)]">{it.name}</span>
                            {it.ref && it.ref !== "-" && <span className="text-[var(--accent-strong)]">{it.ref}</span>}
                            {it.desc && <span className="text-[var(--text-secondary)]">— {it.desc}</span>}
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          {/* 적용 규제·지구·구역 전수 (영향도) */}
          {result.districts.length > 0 && (
            <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
              <CardContent className="p-6">
                <p className="text-sm font-black text-[var(--text-primary)]">
                  🚧 적용 규제·지구·구역 전수 <span className="text-[var(--text-hint)]">({result.districts.length})</span>
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {result.districts.map((d, i) => (
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

          {/* 필지 구획도 */}
          <ParcelBoundaryMap parcels={[result.address]} />

          {/* 전문가 패널 검증 */}
          <ExpertPanelCard
            analysisType="regulation"
            address={result.address}
            context={result as unknown as Record<string, unknown>}
          />
        </>
      )}
    </div>
  );
}

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
