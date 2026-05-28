"use client";

import { useState, useMemo, useEffect } from "react";
import { AreaChart, Area, XAxis, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";
import { motion } from "framer-motion";
import { apiClient } from "@/lib/api-client";
import { formatCurrencyKRW, formatCurrencyCompact } from "@/lib/formatters";

interface SimulationResult {
  results?: {
    npv_mean_krw?: number;
    var_5_krw?: number;
    profitability_index?: number;
  };
}

export function FeasibilitySimulationWidget({ projectId, dictionary }: { projectId: string; dictionary: Record<string, string> }) {
  const [isMounted, setIsMounted] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [npv, setNpv] = useState(1250000000);
  const [var5, setVar5] = useState(-210000000);
  const [profitIndex, setProfitIndex] = useState(1.18);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  const t = dictionary;

  const data = useMemo(() => {
    const arr = [];
    const mean = 1250000000;
    const stdDev = 150000000;
    for (let i = 500000000; i <= 2000000000; i += 50000000) {
      const exponent = Math.exp(-Math.pow(i - mean, 2) / (2 * Math.pow(stdDev, 2)));
      const value = (1 / (stdDev * Math.sqrt(2 * Math.PI))) * exponent;
      arr.push({ x: i, y: Number((value * 10000000000).toFixed(0)) });
    }
    return arr;
  }, []);

  const runSimulation = async () => {
    setIsRunning(true);
    try {
      const res = await apiClient.post<SimulationResult>(`/projects/${projectId}/simulate-feasibility`);
      if (res && res.results) {
        if (res.results.npv_mean_krw) setNpv(res.results.npv_mean_krw);
        if (res.results.var_5_krw) setVar5(res.results.var_5_krw);
        if (res.results.profitability_index) setProfitIndex(Number(res.results.profitability_index.toFixed(2)));
      }
    } catch (err) {
      console.error("Failed to execute simulation", err);
    } finally {
      setIsRunning(false);
    }
  };

  if (!isMounted) return <div className="h-[500px] w-full animate-pulse rounded-[3.5rem] bg-[var(--surface-soft)]" />;

  return (
    <div className="flex flex-col gap-10">
      <div className="flex items-end justify-between px-2">
        <div className="space-y-4">
          <div className="flex items-center gap-3">
             <div className="h-2 w-10 rounded-full bg-[var(--accent-strong)]" />
             <h4 className="text-3xl font-[1000] tracking-tighter text-[var(--text-primary)] uppercase">{t.title || "AI 사업성 시뮬레이터"}</h4>
          </div>
          <p className="max-w-2xl text-sm font-medium leading-relaxed text-[var(--text-secondary)] italic underline decoration-[var(--line-strong)] decoration-2 underline-offset-8">
            {t.description || "몬테카를로 시뮬레이션을 통해 공사비 및 이자율 변동에 따른 기대 NPV와 리스크를 예측합니다."}
          </p>
        </div>
        <button
          onClick={runSimulation}
          disabled={isRunning}
          className="group relative overflow-hidden rounded-[2rem] bg-[var(--accent-strong)] px-10 py-5 text-xs font-black uppercase tracking-widest text-white shadow-[var(--shadow-glow)] transition-all hover:scale-105 active:scale-95 disabled:opacity-50"
        >
          <span className="relative z-10 flex items-center gap-3">
            {isRunning ? (t.runningBtn || "시뮬레이션 중...") : (t.runBtn || "시뮬레이션 실행 →")}
          </span>
          <div className="absolute inset-0 bg-white/20 opacity-0 group-hover:opacity-100 transition-opacity" />
        </button>
      </div>

      <div className="grid gap-8 xl:grid-cols-[380px_1fr]">
        <div className="flex flex-col gap-8 rounded-[3.5rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-12 shadow-[var(--shadow-lg)]">
          <h5 className="text-[10px] font-black uppercase tracking-[0.4em] text-[var(--text-hint)]">
            {t.inputTitle || "VARIABLE CONTROL"}
          </h5>
          
          <div className="space-y-10">
            {[
              { label: t.costVol || "공사비 변동성", min: 1, max: 15, unit: "%", value: 5 },
              { label: t.interestRate || "이자율", min: 2, max: 10, unit: "%", value: 4.5 },
              { label: t.salesDelay || "분양 지연 확률", min: 0, max: 30, unit: "%", value: 10 },
            ].map((input) => (
              <div key={input.label} className="group/input">
                <div className="flex items-center justify-between mb-4">
                   <label className="text-xs font-black text-[var(--text-secondary)] uppercase tracking-widest">{input.label}</label>
                   <span className="text-xs font-black text-[var(--accent-strong)] italic">{input.value}{input.unit}</span>
                </div>
                <input 
                  type="range" 
                  className="w-full cursor-pointer accent-[var(--accent-strong)]" 
                  min={input.min} 
                  max={input.max} 
                  defaultValue={input.value} 
                />
                <div className="mt-2 flex justify-between text-[9px] font-black uppercase tracking-widest text-[var(--text-hint)] opacity-40">
                   <span>{input.min}{input.unit}</span>
                   <span>{input.max}{input.unit}</span>
                </div>
              </div>
            ))}
          </div>
          
          <div className="mt-auto rounded-3xl bg-[var(--surface-soft)] p-6 italic border border-[var(--line)]">
             <p className="text-[10px] font-black text-[var(--text-hint)] leading-relaxed uppercase tracking-tighter">
               "파라미터 변동에 따른 확률론적 기댓값 분석 모드가 활성화되었습니다."
             </p>
          </div>
        </div>

        <div className="relative min-h-[550px] flex flex-col overflow-hidden rounded-[3.5rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-12 shadow-[var(--shadow-2xl)] backdrop-blur-3xl">
          <div className="flex items-center justify-between mb-10">
             <h5 className="text-[10px] font-black uppercase tracking-[0.4em] text-[var(--text-hint)]">
               {t.outputTitle || "AI PREDICTION OVERVIEW"}
             </h5>
             <div className="flex h-10 items-center gap-3 rounded-full bg-[var(--accent-soft)] px-5">
               <div className="h-1.5 w-1.5 rounded-full bg-[var(--accent-strong)] animate-pulse" />
               <span className="text-[9px] font-black uppercase tracking-widest text-[var(--accent-strong)]">Live Simulation Data</span>
             </div>
          </div>

          <div className="grid grid-cols-2 gap-10 md:grid-cols-3">
             <div className="md:col-span-1">
                <p className="text-[9px] font-black uppercase tracking-[0.3em] text-[var(--success)] mb-2 italic">{t.meanNpv || "평균 NPV"}</p>
                <p className="text-5xl font-[1000] tracking-tighter text-[var(--text-primary)] italic">{formatCurrencyCompact(npv)}</p>
             </div>
             <div>
                <p className="text-[9px] font-black uppercase tracking-[0.3em] text-[var(--spot)] mb-2 italic">{t.var5 || "하위 5% 리스크 (VaR)"}</p>
                <p className="text-2xl font-black text-[var(--text-secondary)] tracking-tight">{formatCurrencyCompact(var5)}</p>
             </div>
             <div>
                <p className="text-[9px] font-black uppercase tracking-[0.3em] text-[var(--info)] mb-2 italic">{t.profitIndex || "수익성 지수 (PI)"}</p>
                <p className="text-2xl font-black text-[var(--text-secondary)] tracking-tight">{profitIndex}</p>
             </div>
          </div>
          
          <div className="mt-12 flex-1 w-full relative">
            {isRunning && (
              <div className="absolute inset-0 flex items-center justify-center bg-[var(--surface)]/40 backdrop-blur-md z-20 rounded-[2.5rem]">
                 <div className="flex flex-col items-center gap-6">
                    <div className="h-20 w-20 animate-spin rounded-full border-[6px] border-[var(--accent-soft)] border-t-[var(--accent-strong)] shadow-[var(--shadow-glow)]"></div>
                    <p className="text-xs font-black uppercase tracking-[0.5em] text-[var(--text-hint)] animate-pulse">Running Monte Carlo...</p>
                 </div>
              </div>
            )}
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 20, right: 20, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorSimulation" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--accent-strong)" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="var(--accent-strong)" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <XAxis 
                  dataKey="x" 
                  tick={{ fontSize: 10, fontWeight: 900, fill: "var(--text-hint)" }} 
                  axisLine={false} 
                  tickLine={false} 
                  tickFormatter={(v) => formatCurrencyCompact(Number(v))}
                />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: "var(--surface-strong)", 
                    borderRadius: "2rem", 
                    border: "1px solid var(--line-strong)",
                    boxShadow: "var(--shadow-2xl)",
                    padding: "1.5rem"
                  }}
                  itemStyle={{ fontWeight: "900", textTransform: "uppercase", fontSize: "10px" }}
                  labelStyle={{ fontWeight: "900", marginBottom: "0.5rem", color: "var(--text-primary)" }}
                  labelFormatter={(val) => formatCurrencyKRW(Number(val))}
                />
                <ReferenceLine 
                  x={1050000000} 
                  stroke="var(--spot)" 
                  strokeWidth={2}
                  strokeDasharray="10 10" 
                  label={{ position: 'top', value: 'VALUE AT RISK (5%)', fill: 'var(--spot)', fontSize: 9, fontWeight: 900 }} 
                />
                <ReferenceLine 
                  x={1250000000} 
                  stroke="var(--success)" 
                  strokeWidth={2}
                  strokeDasharray="10 10" 
                  label={{ position: 'top', value: 'EXPECTED MEAN', fill: 'var(--success)', fontSize: 9, fontWeight: 900 }} 
                />
                <Area 
                  type="monotone" 
                  dataKey="y" 
                  stroke="var(--accent-strong)" 
                  strokeWidth={5} 
                  fillOpacity={1} 
                  fill="url(#colorSimulation)" 
                  animationDuration={2000}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}
