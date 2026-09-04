"use client";

import React, { useState } from "react";
import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import { AlertTriangle, Leaf, RefreshCw, Settings } from "lucide-react";
import { useAIAnalyze, useAIReady, extractStructuredFromText, cleanFenceText } from "@/lib/ai-analyze-client";
import { NumberInput } from "@/components/common/NumberInput";
import { VerificationBadge } from "@/components/common/VerificationBadge";
import { CarbonEmissionsWorkspaceClient } from "@/components/analytics/CarbonEmissionsWorkspaceClient";

type ESGResult = {
  carbonFootprint?: { construction: number; operation: number; total: number; unit: string };
  energyGrade?: string;
  gSeedGrade?: string;
  zebLevel?: string;
  recommendations?: Array<{ action: string; impact: string; cost: string }>;
  summary?: string;
};

export default function ESGPage() {
  const { locale } = useParams() as { locale: string };
  const { isReady } = useAIReady();
  const { mutate, data: aiResult, isPending, error } = useAIAnalyze<ESGResult>();

  const [form, setForm] = useState({ buildingType: "공동주택", grossArea: "", energySource: "도시가스", renewableRatio: "10" });
  // (G3) 자재 탄소발자국(EPD) 패널 — 기본 접힘(기존 ESG AI 분석 흐름을 방해하지 않는 additive 배치).
  const [carbonOpen, setCarbonOpen] = useState(false);

  const handleAnalyze = () => {
    mutate({ domain: "esg", context: { buildingType: form.buildingType, grossArea: `${form.grossArea}㎡`, energySource: form.energySource, renewableEnergyRatio: `${form.renewableRatio}%` } });
  };

  // ★raw JSON 노출 해소(전역 공용): 구조화 data 없이 텍스트로만 줄 때 텍스트에서 ESG JSON을
  //  추출해 승격(카드 렌더). 필드 가드(ai.carbonFootprint && 등)가 부분객체를 보호한다.
  const ai = aiResult?.data ?? extractStructuredFromText<ESGResult>(aiResult?.text);
  const gradeColor = (g?: string) => !g ? "bg-slate-500" : g.includes("1") || g === "최우수" ? "bg-emerald-500" : g.includes("2") || g === "우수" ? "bg-blue-500" : g.includes("3") || g === "우량" ? "bg-amber-500" : "bg-slate-500";

  return (
    <div className="space-y-8 p-6">
      <motion.div initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }}>
        <div className="flex items-center gap-3 mb-2">
          <span className="cc-meta">ESG · CARBON CONSOLE</span>
          <span className="cc-live"><i />LIVE</span>
        </div>
        <h1 className="text-3xl font-black tracking-tight text-[var(--text-primary)]">ESG / 탄소 경영</h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">건물 생애주기 탄소 배출량과 녹색 인증 등급을 AI가 분석합니다</p>
      </motion.div>

      <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.1 }} className="cc-panel cc-bracketed glass">
        <i className="cc-bracket cc-bracket--tl" />
        <i className="cc-bracket cc-bracket--tr" />
        <i className="cc-bracket cc-bracket--bl" />
        <i className="cc-bracket cc-bracket--br" />
        <div className="cc-grid-bg opacity-40" />
        <div className="relative cc-panel__head">
          <h2 className="cc-label text-[var(--text-secondary)]">건물 정보 / INPUT</h2>
          <span className="cc-meta">PARAMETERS</span>
        </div>
        <div className="relative cc-panel__body p-8">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">건물유형</label>
            <select value={form.buildingType} onChange={e => setForm(f => ({ ...f, buildingType: e.target.value }))}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] appearance-none cursor-pointer">
              {["공동주택","업무시설","근린생활시설","숙박시설","교육시설"].map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">연면적 (㎡)</label>
            <NumberInput allowDecimal placeholder="3000" value={form.grossArea === "" ? null : Number(form.grossArea)} onChange={n => setForm(f => ({ ...f, grossArea: n != null ? String(n) : "" }))}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50" />
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">에너지원</label>
            <select value={form.energySource} onChange={e => setForm(f => ({ ...f, energySource: e.target.value }))}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] appearance-none cursor-pointer">
              {["도시가스","전기","지열","태양열","복합"].map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">재생에너지: {form.renewableRatio}%</label>
            <input type="range" min="0" max="100" step="5" value={form.renewableRatio} onChange={e => setForm(f => ({ ...f, renewableRatio: e.target.value }))} className="w-full accent-emerald-500" />
          </div>
        </div>
        <button onClick={handleAnalyze} disabled={isPending || !isReady || !form.grossArea}
          className="mt-6 w-full rounded-2xl bg-gradient-to-r from-emerald-600 to-green-600 py-4 font-black text-white shadow-lg transition-all hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed">
          {isPending ? (
            <span className="inline-flex items-center gap-1.5"><RefreshCw className="size-4 animate-spin" aria-hidden />ESG 분석 중...</span>
          ) : !isReady ? (
            <span className="inline-flex items-center gap-1.5"><Settings className="size-4" aria-hidden />API 키를 먼저 등록하세요</span>
          ) : (
            <span className="inline-flex items-center gap-1.5"><Leaf className="size-4" aria-hidden />ESG 분석</span>
          )}
        </button>
        </div>
      </motion.div>

      {error && <div className="rounded-2xl bg-red-500/10 border border-red-500/20 p-4"><p className="text-sm text-red-400 font-bold inline-flex items-center gap-1.5"><AlertTriangle className="size-4" aria-hidden />{error.message}</p></div>}

      {ai && (
        <motion.div initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="space-y-6">
          {/* Carbon Footprint */}
          {ai.carbonFootprint && (
            <div className="grid grid-cols-3 gap-4">
              {[
                { label: "시공 단계 · CONSTRUCTION", val: ai.carbonFootprint.construction, accent: "text-amber-400" },
                { label: "운영 단계 · OPERATION", val: ai.carbonFootprint.operation, accent: "text-blue-400" },
                { label: "전체 · TOTAL", val: ai.carbonFootprint.total, accent: "text-red-400" },
              ].map(c => (
                <div key={c.label} className="cc-panel cc-bracketed cc-interactive glass text-center">
                  <i className="cc-bracket cc-bracket--tl" />
                  <i className="cc-bracket cc-bracket--br" />
                  <div className="cc-grid-bg opacity-30" />
                  <div className="relative cc-panel__body p-5">
                    <p className={`cc-label mb-2 ${c.accent}`}>{c.label}</p>
                    <p className="cc-num text-2xl font-black">{c.val?.toLocaleString() ?? "—"}<span className="cc-label text-[10px] ml-1.5">{ai.carbonFootprint?.unit}</span></p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Grades */}
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: "에너지효율등급 · ENERGY", val: ai.energyGrade },
              { label: "G-SEED 등급 · GREEN", val: ai.gSeedGrade },
              { label: "ZEB 수준 · NET-ZERO", val: ai.zebLevel },
            ].map(g => (
              <div key={g.label} className="cc-panel cc-bracketed cc-interactive glass text-center">
                <i className="cc-bracket cc-bracket--tr" />
                <i className="cc-bracket cc-bracket--bl" />
                <div className="cc-grid-bg cc-grid-bg--radial opacity-30" />
                <div className="relative cc-panel__body p-5">
                  <p className="cc-label text-emerald-400 mb-3">{g.label}</p>
                  <span className={`inline-block rounded-full px-4 py-2 text-sm font-black text-white ${gradeColor(g.val)}`}>{g.val ?? "—"}</span>
                </div>
              </div>
            ))}
          </div>

          {/* Recommendations */}
          {ai.recommendations && ai.recommendations?.length > 0 && (
            <div className="cc-panel glass">
              <div className="cc-panel__head">
                <h3 className="text-lg font-black text-[var(--text-primary)] inline-flex items-center gap-1.5"><Leaf className="size-5" aria-hidden />개선 권고사항</h3>
                <span className="cc-meta">RECOMMENDATIONS</span>
              </div>
              <div className="cc-panel__body space-y-3">
                {(ai.recommendations ?? []).map((r, i) => (
                  <div key={i} className="rounded-xl bg-[var(--surface-muted)] border border-[var(--line)] p-4">
                    <p className="text-sm font-bold text-[var(--text-primary)]">{r.action}</p>
                    <div className="flex gap-4 mt-2">
                      <span className="text-xs text-emerald-400"><span className="cc-label text-[10px]">효과</span> {r.impact}</span>
                      <span className="text-xs text-amber-400"><span className="cc-label text-[10px]">비용</span> {r.cost}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {ai.summary && (
            <div className="cc-panel glass border-emerald-500/20">
              <div className="cc-panel__head">
                <h3 className="text-lg font-black text-emerald-400">AI ESG 종합 평가</h3>
                <span className="cc-meta">SUMMARY · AI</span>
              </div>
              <div className="cc-panel__body bg-emerald-500/5">
                <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{ai.summary}</p>
              </div>
            </div>
          )}
          {/* 신뢰도·할루시네이션 검증 */}
          <VerificationBadge
            analysisType="esg"
            context={ai as unknown as Record<string, unknown>}
            // 응답 ledger_hash(원장 sha256) — useAIAnalyze는 {data,text} 래퍼라 도메인 결과가
            // data 하위일 수 있어 양쪽 모두 수용한다(미노출이면 undefined·안전).
            ledgerHash={
              (aiResult as unknown as { ledger_hash?: string } | undefined)?.ledger_hash
              ?? (ai as unknown as { ledger_hash?: string } | undefined)?.ledger_hash
            }
          />
        </motion.div>
      )}

      {/* 구조화 승격 실패 시에만 정제 텍스트(코드펜스 제거) — raw JSON 코드블록 노출 방지. */}
      {aiResult && !ai && cleanFenceText(aiResult.text) && (
        <div className="glass rounded-2xl p-6 border border-[var(--line)]">
          <h3 className="text-lg font-black text-[var(--text-primary)] mb-2">AI ESG 분석 결과</h3>
          <p className="text-sm text-[var(--text-secondary)] whitespace-pre-wrap leading-relaxed">{cleanFenceText(aiResult.text)}</p>
        </div>
      )}

      {/* (G3) 자재 탄소발자국(EPD) — 위 AI ESG 분석과 별개 도구(additive·기본 접힘).
          EPD Korea Database 기반 자재별 내재탄소를 산출하고, 프로젝트가 연결돼 있으면
          esgData.embodiedCarbonKg(모세혈관 SSOT)에 반영한다. */}
      <div className="cc-panel glass">
        <button
          type="button"
          onClick={() => setCarbonOpen((v) => !v)}
          aria-expanded={carbonOpen}
          className="cc-panel__head flex w-full items-center justify-between gap-3 text-left"
        >
          <div>
            <span className="cc-meta">MATERIALS · EPD CARBON</span>
            <h2 className="mt-1 text-lg font-black text-[var(--text-primary)]">자재 탄소발자국(EPD)</h2>
            <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
              건축자재별 EPD 실데이터로 내재탄소(embodied carbon)를 산출합니다. 필요할 때만 펼쳐 사용하세요.
            </p>
          </div>
          <span className="shrink-0 text-sm font-semibold text-[var(--accent-strong)]">
            {carbonOpen ? "▾ 닫기" : "▸ 열기"}
          </span>
        </button>
        {carbonOpen && (
          <div className="cc-panel__body">
            <CarbonEmissionsWorkspaceClient dictionary={{}} locale={locale} />
          </div>
        )}
      </div>
    </div>
  );
}
