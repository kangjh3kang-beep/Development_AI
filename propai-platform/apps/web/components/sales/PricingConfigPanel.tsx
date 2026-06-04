"use client";

/**
 * 분양가 설정 패널 — 기준가(타입별) + 가중치(층/라인/향) + 구성(토지/건축/커스텀).
 * 엔진(E2: 기준가×(1+Σ가중RATE)+Σ가중FIXED, 확정가 우선, 구성분해 VAT)을 위한 입력 UI.
 * 백엔드 CRUD: /pricing-base · /pricing-weights · /pricing-composition + /pricing/generate
 */

import { useCallback, useEffect, useState } from "react";
import { salesApi } from "@/lib/salesApi";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";

type UnitType = { id: string; type_name: string };
type Base = { id?: string; round_id: string; type_id: string; basis: string; base_unit_price: number; base_area_kind?: string; round_factor?: number };
type Weight = { id?: string; round_id: string; dimension: string; match_key: string; basis: string; value: number; priority?: number };
type Comp = { id?: string; round_id: string; component_type: string; label: string; basis: string; value: number; vat_applicable: boolean; sort_order?: number };

const fcls = "rounded-md border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]";

export default function PricingConfigPanel({
  siteCode, roundId, onChanged,
}: { siteCode: string; roundId: string; onChanged: () => void }) {
  const api = salesApi(siteCode);
  const sa = useProjectContextStore((s) => s.siteAnalysis);
  const [open, setOpen] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [types, setTypes] = useState<UnitType[]>([]);
  const [bases, setBases] = useState<Base[]>([]);
  const [weights, setWeights] = useState<Weight[]>([]);
  const [comps, setComps] = useState<Comp[]>([]);
  const [msg, setMsg] = useState("");

  const load = useCallback(() => {
    api.get<UnitType[]>("/unit-types?limit=500").then((t) => setTypes(t || [])).catch(() => setTypes([]));
    api.get<Base[]>("/pricing-base?limit=500").then((r) => setBases((r || []).filter((x) => x.round_id === roundId))).catch(() => setBases([]));
    api.get<Weight[]>("/pricing-weights?limit=500").then((r) => setWeights((r || []).filter((x) => x.round_id === roundId))).catch(() => setWeights([]));
    api.get<Comp[]>("/pricing-composition?limit=500").then((r) => setComps((r || []).filter((x) => x.round_id === roundId))).catch(() => setComps([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteCode, roundId]);
  useEffect(() => { if (open) load(); }, [open, load]);

  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(""), 2000); };

  // ── 기준가: 타입별 단가 upsert ──
  const saveBase = async (type_id: string, base_unit_price: number, basis: string) => {
    const existing = bases.find((b) => b.type_id === type_id);
    if (existing?.id) await api.patch(`/pricing-base/${existing.id}`, { base_unit_price, basis });
    else await api.post("/pricing-base", { round_id: roundId, type_id, base_unit_price, basis, base_area_kind: "supply" });
    flash("기준가 저장"); load();
  };

  const addWeight = async () => { await api.post("/pricing-weights", { round_id: roundId, dimension: "FLOOR", match_key: "", basis: "RATE", value: 0, priority: 0 }); load(); };
  const saveWeight = async (w: Weight) => { if (w.id) await api.patch(`/pricing-weights/${w.id}`, { dimension: w.dimension, match_key: w.match_key, basis: w.basis, value: w.value, priority: w.priority }); };
  const delWeight = async (id?: string) => { if (id) { await api.del(`/pricing-weights/${id}`); load(); } };

  const addComp = async () => { await api.post("/pricing-composition", { round_id: roundId, component_type: "LAND", label: "토지비", basis: "RATE", value: 0, vat_applicable: false, sort_order: comps.length }); load(); };
  const saveComp = async (c: Comp) => { if (c.id) await api.patch(`/pricing-composition/${c.id}`, { component_type: c.component_type, label: c.label, basis: c.basis, value: c.value, vat_applicable: c.vat_applicable }); };
  const delComp = async (id?: string) => { if (id) { await api.del(`/pricing-composition/${id}`); load(); } };

  const regenerate = async () => { await api.post("/pricing/generate", { round_id: roundId }); flash("분양가 재생성 완료"); onChanged(); };

  // 🤖 AI 분양가 제안 — 공통 LLM으로 기준가(호당)·층 가중치 제안 후 적용+재생성
  const aiSuggest = async () => {
    setAiBusy(true); setMsg("");
    try {
      const ctx = {
        용도지역: sa?.zoneCode || "미상", 대지면적_㎡: sa?.landAreaSqm || null,
        주소: sa?.address || "", 타입: types.map((t) => t.type_name),
      };
      const system = "너는 한국 분양가 산정 전문가다. 입지·용도지역·평형을 고려해 보수적·현실적 기준가와 층별 가중치를 제안한다. 반드시 JSON만 출력.";
      const prompt =
        `다음 현장의 타입별 호당 기준가(원, 정수)와 층 가중치를 제안하라.\n` +
        `현장: ${JSON.stringify(ctx, null, 0)}\n` +
        `출력 JSON 스키마: {"base_per_type":[{"type_name":"84A","base_unit_price":600000000}],` +
        `"floor_weights":[{"match_key":"1","value":-0.05},{"match_key":"15","value":0.05}]}\n` +
        `value는 비율(0.05=+5%). 저층 할인·로열층 할증을 반영. JSON 외 텍스트 금지.`;
      const r = await apiClient.post<{ text: string }>("/ai/llm", { body: { system, prompt }, useMock: false, timeoutMs: 90000 });
      const m = (r.text || "").match(/\{[\s\S]*\}/);
      const data = m ? JSON.parse(m[0]) : null;
      if (!data) { setMsg("AI 응답 파싱 실패"); return; }
      // 적용: 기준가(타입 매칭) + 층 가중치
      for (const b of (data.base_per_type || [])) {
        const t = types.find((x) => x.type_name === b.type_name) || types[0];
        if (t && b.base_unit_price) await saveBase(t.id, Number(b.base_unit_price), "PER_UNIT");
      }
      for (const w of (data.floor_weights || [])) {
        if (w.match_key != null) await api.post("/pricing-weights", { round_id: roundId, dimension: "FLOOR", match_key: String(w.match_key), basis: "RATE", value: Number(w.value || 0), priority: 1 });
      }
      await api.post("/pricing/generate", { round_id: roundId });
      flash("AI 제안 적용·재생성 완료"); load(); onChanged();
    } catch {
      setMsg("AI 제안 실패(잠시 후 재시도)");
    } finally { setAiBusy(false); }
  };

  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)]">
      <button onClick={() => setOpen((v) => !v)} className="flex w-full items-center justify-between px-4 py-3 text-left">
        <span className="text-sm font-black text-[var(--accent-strong)]">⚙ 분양가 설정 (기준가·가중치·구성)</span>
        <span className="text-xs text-[var(--text-tertiary)]">{open ? "접기 ▲" : "펼치기 ▼"}{msg && ` · ${msg}`}</span>
      </button>
      {open && (
        <div className="space-y-5 border-t border-[var(--line)] p-4">
          {/* 기준가 */}
          <div>
            <p className="mb-2 text-xs font-bold text-[var(--text-secondary)]">① 기준가 (타입별 단가)</p>
            <div className="space-y-1.5">
              {types.length === 0 && <p className="text-xs text-[var(--text-hint)]">타입이 없습니다. 먼저 동·호표를 생성하세요.</p>}
              {types.map((t) => {
                const b = bases.find((x) => x.type_id === t.id);
                return (
                  <div key={t.id} className="flex flex-wrap items-center gap-2">
                    <span className="w-20 text-sm font-semibold text-[var(--text-primary)]">{t.type_name}</span>
                    <select defaultValue={b?.basis || "PER_UNIT"} className={`${fcls} w-28`} id={`basis-${t.id}`}>
                      <option value="PER_UNIT">호당(원)</option><option value="PER_AREA">㎡당(원)</option>
                    </select>
                    <input type="number" defaultValue={b?.base_unit_price ?? undefined} placeholder="기준 단가(원)"
                      className={`${fcls} w-40`}
                      onBlur={(e) => { const basis = (document.getElementById(`basis-${t.id}`) as HTMLSelectElement)?.value || "PER_UNIT"; if (e.target.value) void saveBase(t.id, Number(e.target.value), basis); }} />
                  </div>
                );
              })}
            </div>
          </div>

          {/* 가중치 */}
          <div>
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs font-bold text-[var(--text-secondary)]">② 가중치 (층/라인/향)</p>
              <button onClick={addWeight} className="rounded-md border border-dashed border-[var(--line-strong)] px-2 py-1 text-[11px] font-bold text-[var(--accent-strong)]">＋ 가중치</button>
            </div>
            <div className="space-y-1.5">
              {weights.map((w, i) => (
                <div key={w.id || i} className="flex flex-wrap items-center gap-1.5">
                  <select defaultValue={w.dimension} className={`${fcls} w-24`} onChange={(e) => { w.dimension = e.target.value; void saveWeight(w); }}>
                    <option value="FLOOR">층</option><option value="LINE">라인</option><option value="ASPECT">향</option>
                  </select>
                  <input defaultValue={w.match_key} placeholder="값(예:15, 01, 남향)" className={`${fcls} w-32`} onBlur={(e) => { w.match_key = e.target.value; void saveWeight(w); }} />
                  <select defaultValue={w.basis} className={`${fcls} w-24`} onChange={(e) => { w.basis = e.target.value; void saveWeight(w); }}>
                    <option value="RATE">비율(%)</option><option value="FIXED">정액(원)</option>
                  </select>
                  <input type="number" step="0.01" defaultValue={w.value} placeholder="0.05=+5%" className={`${fcls} w-28`} onBlur={(e) => { w.value = Number(e.target.value); void saveWeight(w); }} />
                  <button onClick={() => delWeight(w.id)} className="h-7 w-7 rounded-md border border-rose-500/30 text-rose-500">✕</button>
                </div>
              ))}
              {weights.length === 0 && <p className="text-xs text-[var(--text-hint)]">가중치 없음(기준가만 적용). 예: 층 15 / 비율 / 0.05 = 15층 +5%.</p>}
            </div>
          </div>

          {/* 구성 */}
          <div>
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs font-bold text-[var(--text-secondary)]">③ 가격 구성 (토지/건축, VAT)</p>
              <button onClick={addComp} className="rounded-md border border-dashed border-[var(--line-strong)] px-2 py-1 text-[11px] font-bold text-[var(--accent-strong)]">＋ 구성</button>
            </div>
            <div className="space-y-1.5">
              {comps.map((c, i) => (
                <div key={c.id || i} className="flex flex-wrap items-center gap-1.5">
                  <select defaultValue={c.component_type} className={`${fcls} w-24`} onChange={(e) => { c.component_type = e.target.value; void saveComp(c); }}>
                    <option value="LAND">토지비</option><option value="BUILD">건축비</option><option value="CUSTOM">기타</option>
                  </select>
                  <input defaultValue={c.label} placeholder="표시명" className={`${fcls} w-32`} onBlur={(e) => { c.label = e.target.value; void saveComp(c); }} />
                  <select defaultValue={c.basis} className={`${fcls} w-24`} onChange={(e) => { c.basis = e.target.value; void saveComp(c); }}>
                    <option value="RATE">비율</option><option value="FIXED">정액</option>
                  </select>
                  <input type="number" step="0.01" defaultValue={c.value} placeholder="0.3" className={`${fcls} w-24`} onBlur={(e) => { c.value = Number(e.target.value); void saveComp(c); }} />
                  <label className="flex items-center gap-1 text-xs text-[var(--text-secondary)]">
                    <input type="checkbox" defaultChecked={c.vat_applicable} onChange={(e) => { c.vat_applicable = e.target.checked; void saveComp(c); }} /> VAT
                  </label>
                  <button onClick={() => delComp(c.id)} className="h-7 w-7 rounded-md border border-rose-500/30 text-rose-500">✕</button>
                </div>
              ))}
              {comps.length === 0 && <p className="text-xs text-[var(--text-hint)]">구성 없음. 예: 토지비 비율 0.3(VAT X) + 건축비 비율 0.7(VAT O).</p>}
            </div>
          </div>

          <div className="flex flex-wrap justify-end gap-2">
            <button onClick={aiSuggest} disabled={aiBusy || types.length === 0} title="입지·용도지역·평형 기반 AI 기준가/가중치 제안"
              className="rounded-lg border border-[var(--accent-strong)] px-4 py-2 text-sm font-black text-[var(--accent-strong)] hover:bg-[var(--accent-soft)] disabled:opacity-50">
              {aiBusy ? "AI 제안 중…" : "🤖 AI 분양가 제안"}
            </button>
            <button onClick={regenerate} className="rounded-lg bg-[var(--accent-strong)] px-4 py-2 text-sm font-black text-white hover:opacity-90">설정 적용 → 분양가 재생성</button>
          </div>
        </div>
      )}
    </div>
  );
}
