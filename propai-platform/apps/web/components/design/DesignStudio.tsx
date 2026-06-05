"use client";

/**
 * AI 건축 설계 스튜디오 — 한국 건축법 기반 즉시 계산 + AI 심층 분석 + 매싱 옵션.
 * 프로젝트 탭과 독립 메뉴(/design-studio) 양쪽에서 재사용(projectId 주입).
 */

import React, { useState, useMemo, useEffect } from "react";
import { motion } from "framer-motion";
import { useAIAnalyze, useAIReady } from "@/lib/ai-analyze-client";
import { getZoningSpec, calcMaxGrossArea, calcParkingRequired } from "@/lib/kr-building-regulations";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { NumberInput } from "@/components/common/NumberInput";
import { SolarEnvelopeCard } from "@/components/projects/SolarEnvelopeCard";

// 일반인용 쉬운 설명(용어 풀이) — '쉬운 설명' 토글 시 표시
const EASY: Record<string, string> = {
  건폐율: "땅 면적 중 건물 1층이 덮을 수 있는 비율. 높을수록 넓게 지음.",
  용적률: "땅 면적 대비 전체 층 바닥면적 합의 비율. 높을수록 많이(높이) 지음.",
  "예상 층수": "용적률·높이제한으로 지을 수 있는 대략의 층수.",
  "주차 대수": "법으로 확보해야 하는 최소 주차 칸 수.",
  "최대 연면적": "모든 층 바닥면적을 합한 최대 건축 가능 면적(분양·사업성의 기준).",
  매싱: "건물 덩어리의 배치 모양(판상형=일자, 타워형=고층 1동 등).",
  일조: "겨울에도 햇빛이 드는지(정북일조)·그림자 길이. 인접 대지·민원과 직결.",
};

type DesignResult = {
  buildingCoverage?: { value: number; max: number; unit: string };
  floorAreaRatio?: { value: number; max: number; unit: string };
  maxFloors?: number;
  maxHeight?: { value: number; unit: string };
  totalGrossArea?: { value: number; unit: string };
  parkingRequired?: number;
  setbacks?: { front: number; side: number; rear: number; unit: string };
  massingOptions?: Array<{ name: string; description: string; efficiency: number }>;
  summary?: string;
};

// 매싱 유형별 간이 3D 도식(SVG) — 일반인 직관용(판상/타워/ㄱ자/중정 등)
function MassingDiagram({ name, active }: { name: string; active?: boolean }) {
  const c = active ? "var(--accent-strong)" : "var(--text-tertiary)";
  const fill = active ? "var(--accent-soft)" : "var(--surface-muted)";
  const n = name || "";
  const blocks =
    n.includes("타워") ? [{ x: 40, y: 14, w: 20, h: 46 }]
    : n.includes("ㄱ") || n.includes("L") ? [{ x: 18, y: 34, w: 44, h: 16 }, { x: 18, y: 18, w: 16, h: 32 }]
    : n.includes("중정") || n.includes("ㅁ") ? [{ x: 16, y: 18, w: 14, h: 40 }, { x: 70, y: 18, w: 14, h: 40 }, { x: 16, y: 18, w: 68, h: 12 }, { x: 16, y: 46, w: 68, h: 12 }]
    : [{ x: 14, y: 22, w: 30, h: 38 }, { x: 56, y: 22, w: 30, h: 38 }]; // 판상형(기본)
  return (
    <svg viewBox="0 0 100 70" className="h-16 w-full">
      <line x1="6" y1="62" x2="94" y2="62" stroke={c} strokeWidth="1" opacity="0.4" />
      {blocks.map((b, i) => (
        <g key={i}>
          <rect x={b.x} y={b.y} width={b.w} height={b.h} rx="1.5" fill={fill} stroke={c} strokeWidth="1.4" />
          <polygon points={`${b.x},${b.y} ${b.x + 5},${b.y - 5} ${b.x + b.w + 5},${b.y - 5} ${b.x + b.w},${b.y}`} fill={c} opacity="0.25" />
          <polygon points={`${b.x + b.w},${b.y} ${b.x + b.w + 5},${b.y - 5} ${b.x + b.w + 5},${b.y + b.h - 5} ${b.x + b.w},${b.y + b.h}`} fill={c} opacity="0.4" />
        </g>
      ))}
    </svg>
  );
}

export function DesignStudio({ projectId }: { projectId?: string }) {
  const { isReady } = useAIReady();
  const { mutate, data: aiResult, isPending, error } = useAIAnalyze<DesignResult>();
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const [easy, setEasy] = useState(false);   // 일반인용 쉬운 설명 토글

  const [form, setForm] = useState({ landArea: "500", zoning: "제2종일반주거지역", buildingUse: "공동주택" });

  useEffect(() => {
    if (!siteAnalysis) return;
    setForm((prev) => ({
      ...prev,
      landArea: siteAnalysis.landAreaSqm ? String(siteAnalysis.landAreaSqm) : prev.landArea,
      zoning: siteAnalysis.zoneCode || prev.zoning,
    }));
  }, [siteAnalysis]);

  const localCalc = useMemo(() => {
    const area = Number(form.landArea) || 0;
    const spec = getZoningSpec(form.zoning);
    if (!spec || area <= 0) return null;
    const maxGross = calcMaxGrossArea(area, form.zoning);
    const parking = calcParkingRequired(maxGross, form.buildingUse);
    const buildableArea = area * (spec.buildingCoverageMax / 100);
    const minFloorsFromFar = spec.floorAreaRatioMax > 0 ? Math.ceil(maxGross / buildableArea) : 1;
    const heightPerFloor = 3.3;
    const maxFloorsByHeight = spec.heightLimit ? Math.floor(spec.heightLimit / heightPerFloor) : 25;
    const maxFloors = Math.min(minFloorsFromFar, maxFloorsByHeight);
    const maxHeight = spec.heightLimit || (maxFloors * heightPerFloor);
    const heightNote = spec.heightLimit ? "법적 높이 제한" : "예상 높이 (제한 없음)";
    return {
      buildingCoverage: spec.buildingCoverageMax, floorAreaRatio: spec.floorAreaRatioMax,
      maxFloors, maxHeight: Math.round(maxHeight * 10) / 10,
      buildableArea: Math.round(buildableArea * 10) / 10, maxGrossArea: Math.round(maxGross * 10) / 10,
      parking, heightNote, setbacks: { front: 6, side: 1.5, rear: 2, unit: "m" },
      massingOptions: [
        { name: "판상형", description: `${maxFloors}층 2개동, 남향 배치`, efficiency: 78 },
        { name: "타워형", description: `${maxFloors + 2}층 1개동, 중앙코어`, efficiency: 72 },
        { name: "ㄱ자형", description: `${maxFloors}층, 소음차폐 배치`, efficiency: 75 },
      ],
    };
  }, [form.landArea, form.zoning, form.buildingUse]);

  const handleAIAnalyze = () => {
    mutate({ domain: "design", context: { landArea: `${form.landArea}㎡`, zoningDistrict: form.zoning, buildingUse: form.buildingUse, projectId } });
  };

  const ai = aiResult?.data;
  const calc = localCalc;

  return (
    <div className="space-y-8">
      <motion.div initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="flex flex-wrap items-start justify-between gap-3">
        <div>
        <h1 className="text-3xl font-black tracking-tight text-[var(--text-primary)]">AI 건축 설계</h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">한국 건축법 기반 즉시 계산 + AI 심층 분석</p>
        </div>
        <button onClick={() => setEasy((v) => !v)}
          className={`shrink-0 rounded-full border px-3.5 py-1.5 text-xs font-bold transition-colors ${easy ? "border-[var(--accent-strong)] bg-[var(--accent-soft)] text-[var(--accent-strong)]" : "border-[var(--line-strong)] text-[var(--text-secondary)]"}`}>
          {easy ? "🟢 쉬운 설명 켜짐" : "💡 쉬운 설명"}
        </button>
      </motion.div>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        {siteAnalysis?.address && (
          <p className="text-xs text-emerald-500 mt-2 flex items-center gap-1.5">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
            부지분석 연동: {siteAnalysis.address} ({siteAnalysis.zoneCode || "용도지역 미확인"})
          </p>
        )}
      </motion.div>

      <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.1 }} className="glass rounded-3xl p-8 border border-[var(--line-strong)]">
        <h2 className="text-lg font-black text-[var(--text-primary)] mb-6">설계 조건</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">대지면적 (㎡)</label>
            <NumberInput allowDecimal placeholder="500" value={form.landArea === "" ? null : Number(form.landArea)} onChange={(n) => setForm((f) => ({ ...f, landArea: n != null ? String(n) : "" }))}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50" />
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">용도지역</label>
            <select value={form.zoning} onChange={(e) => setForm((f) => ({ ...f, zoning: e.target.value }))}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] appearance-none cursor-pointer">
              {["제1종전용주거지역","제2종전용주거지역","제1종일반주거지역","제2종일반주거지역","제3종일반주거지역","준주거지역","일반상업지역","근린상업지역","준공업지역"].map((z) => <option key={z} value={z}>{z}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">건물용도</label>
            <select value={form.buildingUse} onChange={(e) => setForm((f) => ({ ...f, buildingUse: e.target.value }))}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] appearance-none cursor-pointer">
              {["공동주택","업무시설","근린생활시설","숙박시설","판매시설","교육연구시설"].map((u) => <option key={u} value={u}>{u}</option>)}
            </select>
          </div>
        </div>
        <button onClick={handleAIAnalyze} disabled={isPending || !isReady || !form.landArea}
          className="mt-6 w-full rounded-2xl bg-gradient-to-r from-blue-600 to-cyan-600 py-4 font-black text-white shadow-lg transition-all hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed">
          {isPending ? "AI 심층 분석 중…" : !isReady ? "API 키를 먼저 등록하세요 (아래 법규 계산은 즉시 가능)" : "AI 심층 설계 분석 실행"}
        </button>
      </motion.div>

      {error && <div className="rounded-2xl bg-red-500/10 border border-red-500/20 p-4"><p className="text-sm text-red-400 font-bold">⚠️ {error.message}</p></div>}

      {calc && (
        <motion.div initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="space-y-6">
          <div className="flex items-center gap-2">
            <span className={`inline-block h-2 w-2 rounded-full ${ai ? "bg-emerald-400" : "bg-blue-400"}`} />
            <span className="text-xs font-bold text-[var(--text-secondary)]">{ai ? "AI 분석 결과 반영됨" : "한국 건축법/국토계획법 기반 자동 계산"}</span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: "건폐율", val: `${ai?.buildingCoverage?.value ?? calc.buildingCoverage}%`, sub: `최대 ${ai?.buildingCoverage?.max ?? calc.buildingCoverage}%`, color: "text-blue-400" },
              { label: "용적률", val: `${ai?.floorAreaRatio?.value ?? calc.floorAreaRatio}%`, sub: `최대 ${ai?.floorAreaRatio?.max ?? calc.floorAreaRatio}%`, color: "text-emerald-400" },
              { label: "예상 층수", val: `${ai?.maxFloors ?? calc.maxFloors}층`, sub: `${ai?.maxHeight?.value ?? calc.maxHeight}m (${calc.heightNote})`, color: "text-purple-400" },
              { label: "주차 대수", val: `${ai?.parkingRequired ?? calc.parking}대`, sub: "주차장법 기준", color: "text-amber-400" },
            ].map((k) => (
              <div key={k.label} className="glass rounded-2xl p-5 border border-[var(--line)] text-center">
                <p className={`text-xs font-bold uppercase tracking-widest ${k.color} mb-2`}>{k.label}</p>
                <p className="text-2xl font-black text-[var(--text-primary)]">{k.val}</p>
                <p className="text-[10px] text-[var(--text-hint)]">{k.sub}</p>
                {easy && EASY[k.label] && <p className="mt-1.5 text-[10px] leading-snug text-[var(--accent-strong)]">{EASY[k.label]}</p>}
              </div>
            ))}
          </div>

          {/* 법규 적합 체크리스트 — 적용값이 법정 한도 이내인지 한눈에 */}
          <div className="glass rounded-2xl p-6 border border-[var(--line)]">
            <h3 className="text-sm font-black text-[var(--text-primary)] mb-3">✅ 법규 적합 체크리스트</h3>
            {easy && <p className="mb-2 text-[11px] text-[var(--accent-strong)]">적용 설계값이 법으로 정한 한도 안에 들어오는지 확인합니다. ✓면 통과예요.</p>}
            <div className="space-y-1.5">
              {[
                { k: "건폐율", v: ai?.buildingCoverage?.value ?? calc.buildingCoverage, max: ai?.buildingCoverage?.max ?? calc.buildingCoverage, u: "%" },
                { k: "용적률", v: ai?.floorAreaRatio?.value ?? calc.floorAreaRatio, max: ai?.floorAreaRatio?.max ?? calc.floorAreaRatio, u: "%" },
                { k: "높이", v: ai?.maxHeight?.value ?? calc.maxHeight, max: calc.maxHeight, u: "m" },
                { k: "주차", v: ai?.parkingRequired ?? calc.parking, max: ai?.parkingRequired ?? calc.parking, u: "대" },
              ].map((row) => {
                const ok = Number(row.v) <= Number(row.max) + 1e-6;
                return (
                  <div key={row.k} className="flex items-center justify-between rounded-lg bg-[var(--surface-muted)] px-3 py-2 text-xs">
                    <span className="font-bold text-[var(--text-secondary)]">{row.k}</span>
                    <span className="text-[var(--text-hint)]">적용 {row.v}{row.u} / 한도 {row.max}{row.u}</span>
                    <span className={`font-black ${ok ? "text-emerald-500" : "text-rose-500"}`}>{ok ? "✓ 적합" : "⚠ 초과"}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 일조 · 건축가능 볼륨(정북일조 + 동지 일영) — 부지분석 연동 시 */}
          {(siteAnalysis?.pnu || siteAnalysis?.landAreaSqm) && (
            <div>
              {easy && <p className="mb-2 text-[11px] text-[var(--accent-strong)]">{EASY["일조"]}</p>}
              <SolarEnvelopeCard
                address={siteAnalysis?.address || undefined}
                pnu={siteAnalysis?.pnu || undefined}
                zone={siteAnalysis?.zoneCode || form.zoning}
                landAreaSqm={siteAnalysis?.landAreaSqm ?? (form.landArea ? Number(form.landArea) : undefined)}
              />
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div className="glass rounded-2xl p-5 border border-[var(--line)]">
              <p className="text-xs font-bold text-cyan-400 uppercase tracking-widest mb-1">최대 연면적</p>
              <p className="text-3xl font-black text-[var(--text-primary)]">{(ai?.totalGrossArea?.value ?? calc.maxGrossArea).toLocaleString()} <span className="text-sm">㎡</span></p>
            </div>
            <div className="glass rounded-2xl p-5 border border-[var(--line)]">
              <p className="text-xs font-bold text-orange-400 uppercase tracking-widest mb-1">건축가능면적</p>
              <p className="text-3xl font-black text-[var(--text-primary)]">{calc.buildableArea.toLocaleString()} <span className="text-sm">㎡</span></p>
            </div>
          </div>

          <div className="glass rounded-2xl p-6 border border-[var(--line)]">
            <h3 className="text-sm font-black text-[var(--text-primary)] mb-3">건축선 이격거리</h3>
            <div className="grid grid-cols-3 gap-4 text-center">
              {[
                { label: "전면", val: ai?.setbacks?.front ?? calc.setbacks.front },
                { label: "측면", val: ai?.setbacks?.side ?? calc.setbacks.side },
                { label: "후면", val: ai?.setbacks?.rear ?? calc.setbacks.rear },
              ].map((s) => (
                <div key={s.label} className="rounded-xl bg-[var(--surface-muted)] p-3 border border-[var(--line)]">
                  <p className="text-[10px] font-bold text-[var(--text-hint)] uppercase">{s.label}</p>
                  <p className="text-xl font-black text-[var(--text-primary)]">{s.val}<span className="text-xs ml-0.5">m</span></p>
                </div>
              ))}
            </div>
          </div>

          <div className="glass rounded-2xl p-6 border border-[var(--line)]">
            <h3 className="text-lg font-black text-[var(--text-primary)] mb-1">매싱 대안 비교</h3>
            {easy && <p className="mb-3 text-[11px] text-[var(--accent-strong)]">{EASY["매싱"]} 효율(전용률)이 높을수록 같은 면적에서 분양·임대 면적이 많아 유리합니다. ★가 추천안.</p>}
            {(() => {
              const opts = ai?.massingOptions || calc.massingOptions;
              const best = Math.max(...opts.map((o) => o.efficiency || 0));
              return (
                <div className="mt-2 grid grid-cols-1 gap-3 md:grid-cols-3">
                  {opts.map((m, i) => {
                    const isBest = (m.efficiency || 0) === best;
                    const estGfa = calc.maxGrossArea ? Math.round(calc.maxGrossArea * (m.efficiency / 100)) : null;
                    return (
                      <div key={i} className={`relative rounded-xl border p-4 ${isBest ? "border-[var(--accent-strong)]/50 bg-[var(--accent-soft)]" : "border-[var(--line)] bg-[var(--surface-muted)]"}`}>
                        {isBest && <span className="absolute right-3 top-3 rounded-full bg-[var(--accent-strong)] px-2 py-0.5 text-[9px] font-black text-white">★ 추천</span>}
                        <MassingDiagram name={m.name} active={isBest} />
                        <p className="mt-1 text-sm font-bold text-[var(--text-primary)]">{m.name}</p>
                        <p className="mt-0.5 text-[11px] leading-snug text-[var(--text-secondary)]">{m.description}</p>
                        <div className="mt-2 flex items-center gap-2">
                          <div className="h-2 flex-1 rounded-full bg-[var(--line)]"><div className="h-2 rounded-full" style={{ width: `${m.efficiency}%`, background: isBest ? "var(--accent-strong)" : "#60a5fa" }} /></div>
                          <span className={`text-xs font-black ${isBest ? "text-[var(--accent-strong)]" : "text-blue-400"}`}>{m.efficiency}%</span>
                        </div>
                        {estGfa != null && (
                          <p className="mt-1.5 text-[10px] text-[var(--text-hint)]">예상 전용 연면적 약 {estGfa.toLocaleString()}㎡</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              );
            })()}
          </div>

          {ai?.summary && (
            <div className="glass rounded-2xl p-6 border border-blue-500/20 bg-blue-500/5">
              <h3 className="text-lg font-black text-blue-400 mb-2">AI 설계 의견</h3>
              <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{ai.summary}</p>
            </div>
          )}

          {aiResult && !ai && aiResult.text && (
            <div className="glass rounded-2xl p-6 border border-[var(--line)]">
              <h3 className="text-sm font-black text-[var(--text-primary)] mb-2">AI 설계 결과</h3>
              <p className="text-sm text-[var(--text-secondary)] whitespace-pre-wrap leading-relaxed">{aiResult.text}</p>
            </div>
          )}
        </motion.div>
      )}
    </div>
  );
}
