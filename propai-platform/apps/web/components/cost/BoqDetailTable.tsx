"use client";

/**
 * BOQ 상세 내역서(수백행) + D4 단가 3중 비교 + AI 해설.
 *  ① POST /api/v1/cost/{pid}/boq → 공종별 코드·물량·단가·금액 내역서 + summary(직접·간접·총·신뢰등급).
 *     각 단가에 price_source·basis_year·qto_source(bim ±5% / derived ±12%) 배지.
 *  ② GET /api/v1/cost/unit-prices → 표준(품셈)/시장(KCCI)/실적(null) 단가 3중 비교.
 *  ③ ai_cost_analysis(있으면) AI 해설 카드.
 * 정직성 note·전문 적산사 검토 배지.
 */

import { useCallback, useMemo, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import type {
  BoqResponse,
  UnitPricesResponse,
} from "@/components/cost/cmTypes";

const fcls =
  "w-full rounded-lg border border-[var(--line-strong)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]";

function won(v?: number | null): string {
  if (v == null || isNaN(v)) return "—";
  return `${Math.round(v).toLocaleString()}원`;
}
function eok(v?: number | null): string {
  if (v == null || isNaN(v)) return "—";
  return `${(v / 1e8).toLocaleString(undefined, { maximumFractionDigits: 2 })}억`;
}

function QtoBadge({ source }: { source?: string }) {
  const isBim = source === "bim";
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${
        isBim ? "bg-emerald-500/15 text-emerald-400" : "bg-[var(--surface-muted)] text-[var(--text-tertiary)]"
      }`}
    >
      {isBim ? "BIM ±5%" : "추정 ±12%"}
    </span>
  );
}

export function BoqDetailTable({ projectId: projectIdProp }: { projectId?: string }) {
  const ctxProjectId = useProjectContextStore((s) => s.projectId);
  const designData = useProjectContextStore((s) => s.designData);
  const projectId = projectIdProp || ctxProjectId || "default";

  const [bt, setBt] = useState("apartment");
  const [gfa, setGfa] = useState<string>(
    designData?.totalGfaSqm ? String(Math.round(designData.totalGfaSqm)) : "",
  );
  const [floorsAbove, setFloorsAbove] = useState<string>(
    designData?.floorCount ? String(designData.floorCount) : "15",
  );
  const [floorsBelow, setFloorsBelow] = useState<string>("2");
  const [structure, setStructure] = useState("RC");

  const [boq, setBoq] = useState<BoqResponse | null>(null);
  const [prices, setPrices] = useState<UnitPricesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const run = useCallback(async () => {
    const gfaNum = Number(gfa);
    if (!gfaNum || gfaNum <= 0) {
      setErr("연면적(GFA)을 입력하세요.");
      return;
    }
    setLoading(true);
    setErr("");
    try {
      const [boqRes, priceRes] = await Promise.all([
        apiClient.post<BoqResponse>(`/cost/${projectId}/boq`, {
          body: {
            building_type: bt,
            total_gfa_sqm: gfaNum,
            floor_count_above: Number(floorsAbove) || 1,
            floor_count_below: Number(floorsBelow) || 0,
            structure_type: structure,
            persist: true,
          },
          useMock: false,
          timeoutMs: 60000,
        }),
        apiClient
          .get<UnitPricesResponse>("/cost/unit-prices", { useMock: false, timeoutMs: 30000 })
          .catch(() => null),
      ]);
      setBoq(boqRes);
      if (priceRes) setPrices(priceRes);
    } catch {
      setErr("BOQ 상세적산에 실패했습니다. 입력값을 확인하세요.");
    } finally {
      setLoading(false);
    }
  }, [bt, gfa, floorsAbove, floorsBelow, structure, projectId]);

  const items = boq?.items ?? [];
  const summary = boq?.summary;

  const priceItems = useMemo(() => prices?.items ?? [], [prices]);

  return (
    <section className="grid gap-5">
      <div>
        <h2 className="text-xl font-black text-[var(--text-primary)]">상세 내역서 (BOQ) · 단가 3중 비교</h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          공종별 물량·단가·금액 내역서와 표준/시장(KCCI)/실적 단가 3중 비교를 제공합니다. 산출물은 원가계산서로 영속화됩니다.
        </p>
      </div>

      {/* 건축개요 입력 */}
      <div className="grid gap-4 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5 sm:grid-cols-2 lg:grid-cols-5">
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold text-[var(--text-secondary)]">건축유형</span>
          <select value={bt} onChange={(e) => setBt(e.target.value)} className={fcls}>
            <option value="apartment">아파트/공동주택</option>
            <option value="officetel">오피스텔</option>
            <option value="office">업무시설</option>
            <option value="townhouse">연립·다세대</option>
            <option value="warehouse">지식산업센터/창고</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold text-[var(--text-secondary)]">연면적(㎡)</span>
          <input value={gfa} onChange={(e) => setGfa(e.target.value)} inputMode="decimal" className={fcls} placeholder="예: 30000" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold text-[var(--text-secondary)]">구조</span>
          <select value={structure} onChange={(e) => setStructure(e.target.value)} className={fcls}>
            {["RC", "SRC", "SC", "PC"].map((s) => (
              <option key={s} value={s}>{s}조</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold text-[var(--text-secondary)]">지상 층수</span>
          <input value={floorsAbove} onChange={(e) => setFloorsAbove(e.target.value)} inputMode="numeric" className={fcls} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold text-[var(--text-secondary)]">지하 층수</span>
          <input value={floorsBelow} onChange={(e) => setFloorsBelow(e.target.value)} inputMode="numeric" className={fcls} />
        </label>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={run}
          disabled={loading}
          className="rounded-xl bg-[var(--accent-strong)] px-8 py-3 text-sm font-black text-white shadow-[var(--shadow-glow)] hover:opacity-90 disabled:opacity-50"
        >
          {loading ? "상세적산 중…" : "BOQ 상세적산 실행"}
        </button>
        {err && <span className="text-xs font-semibold text-rose-400">{err}</span>}
      </div>

      {/* AI 해설 */}
      {boq?.ai_cost_analysis && (
        <div className="rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] p-5">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-base">🤖</span>
            <h3 className="text-sm font-black text-[var(--text-primary)]">AI 공사비 해설</h3>
          </div>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--text-secondary)]">
            {boq.ai_cost_analysis}
          </p>
        </div>
      )}

      {/* summary */}
      {summary && (
        <div className="grid gap-4 sm:grid-cols-4">
          <div className="rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] p-5">
            <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">총 공사비</p>
            <p className="mt-2 text-2xl font-[1000] text-[var(--accent-strong)]">{eok(summary.total)}</p>
          </div>
          <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-5">
            <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">직접비</p>
            <p className="mt-2 text-lg font-[1000] text-[var(--text-primary)]">{eok(summary.direct)}</p>
          </div>
          <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-5">
            <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">간접비</p>
            <p className="mt-2 text-lg font-[1000] text-[var(--text-primary)]">{eok(summary.indirect)}</p>
          </div>
          <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-5">
            <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">신뢰등급</p>
            <p className="mt-2 text-lg font-[1000] text-[var(--text-primary)]">{summary.confidence_grade || "—"}</p>
            {summary.confidence_band && (
              <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">{summary.confidence_band}</p>
            )}
          </div>
        </div>
      )}

      {/* BOQ 내역서 테이블 */}
      {items.length > 0 && (
        <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-black text-[var(--text-primary)]">공종별 내역서 ({items.length}행)</h3>
            {boq?.estimate_id && (
              <span className="text-[10px] text-[var(--text-hint)]">원가계산서 ID: {boq.estimate_id.slice(0, 8)}…</span>
            )}
          </div>
          <div className="max-h-[560px] overflow-auto">
            <table className="w-full text-[11px]">
              <thead className="sticky top-0">
                <tr className="bg-[var(--surface-strong)] text-[var(--text-tertiary)]">
                  <th className="px-3 py-2 text-left font-bold">코드</th>
                  <th className="px-3 py-2 text-left font-bold">공종</th>
                  <th className="px-3 py-2 text-right font-bold">물량</th>
                  <th className="px-3 py-2 text-left font-bold">단위</th>
                  <th className="px-3 py-2 text-right font-bold">단가</th>
                  <th className="px-3 py-2 text-right font-bold">금액</th>
                  <th className="px-3 py-2 text-left font-bold">출처</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it, i) => (
                  <tr key={`${it.code}-${i}`} className="border-t border-[var(--line)]/60">
                    <td className="px-3 py-2 font-mono text-[var(--text-tertiary)]">{it.code}</td>
                    <td className="px-3 py-2 font-semibold text-[var(--text-primary)]">
                      {it.name}
                      {it.work_type && (
                        <span className="ml-1 text-[9px] text-[var(--text-hint)]">{it.work_type}</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right text-[var(--text-secondary)]">
                      {it.quantity != null ? Math.round(it.quantity).toLocaleString() : "—"}
                    </td>
                    <td className="px-3 py-2 text-[var(--text-tertiary)]">{it.unit || "—"}</td>
                    <td className="px-3 py-2 text-right text-[var(--text-secondary)]">{won(it.unit_price)}</td>
                    <td className="px-3 py-2 text-right font-bold text-[var(--text-primary)]">{won(it.amount)}</td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap items-center gap-1">
                        <span className="rounded bg-[var(--surface-muted)] px-1.5 py-0.5 text-[9px] font-bold text-[var(--text-tertiary)]">
                          {it.price_source}
                          {it.price_basis_year ? ` ${it.price_basis_year}` : ""}
                        </span>
                        <QtoBadge source={it.qto_source} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {boq?.badges?.note && (
            <p className="mt-3 text-[11px] text-[var(--text-hint)]">{boq.badges.note}</p>
          )}
        </div>
      )}

      {/* D4 단가 3중 비교 */}
      {priceItems.length > 0 && (
        <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5">
          <h3 className="mb-1 text-sm font-black text-[var(--text-primary)]">단가 3중 비교 (표준 · 시장 · 실적)</h3>
          <p className="mb-3 text-[11px] text-[var(--text-hint)]">
            표준=품셈/단가DB, 시장=KCCI 변동모델, 실적=실데이터 없음(정직성 표기).
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="text-[var(--text-tertiary)]">
                  <th className="px-3 py-2 text-left font-bold">자재</th>
                  <th className="px-3 py-2 text-left font-bold">단위</th>
                  <th className="px-3 py-2 text-right font-bold">표준</th>
                  <th className="px-3 py-2 text-right font-bold">시장(KCCI)</th>
                  <th className="px-3 py-2 text-right font-bold">실적</th>
                  <th className="px-3 py-2 text-left font-bold">기준연도</th>
                </tr>
              </thead>
              <tbody>
                {priceItems.map((p, i) => {
                  const diff =
                    p.market != null && p.standard > 0
                      ? ((p.market - p.standard) / p.standard) * 100
                      : null;
                  return (
                    <tr key={`${p.code}-${i}`} className="border-t border-[var(--line)]/60">
                      <td className="px-3 py-2 font-semibold text-[var(--text-primary)]">{p.name}</td>
                      <td className="px-3 py-2 text-[var(--text-tertiary)]">{p.unit}</td>
                      <td className="px-3 py-2 text-right text-[var(--text-secondary)]">{won(p.standard)}</td>
                      <td className="px-3 py-2 text-right text-[var(--text-secondary)]">
                        {p.market != null ? won(p.market) : <span className="text-[var(--text-hint)]">—</span>}
                        {diff != null && (
                          <span className={`ml-1 text-[9px] font-bold ${diff >= 0 ? "text-rose-400" : "text-emerald-400"}`}>
                            {diff >= 0 ? "+" : ""}{diff.toFixed(0)}%
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right text-[var(--text-hint)]">데이터 없음</td>
                      <td className="px-3 py-2 text-[var(--text-tertiary)]">{p.basis_year ?? "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {prices?.note && <p className="mt-3 text-[11px] text-[var(--text-hint)]">{prices.note}</p>}
        </div>
      )}
    </section>
  );
}
