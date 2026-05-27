"use client";

import { useEffect, useState, useRef } from "react";
import { Card, CardContent } from "@propai/ui";
import { apiClient } from "@/lib/api-client";

type ServiceUsage = {
  service: string;
  tokens: number;
  cost: number;
};

type UsageData = {
  totalTokens: number;
  totalCost: number;
  budget: number;
  dailyUsage: { date: string; tokens: number }[];
  services: ServiceUsage[];
};

const SERVICE_LABELS: Record<string, string> = {
  design_ai: "설계 AI",
  legal_ai: "법규검토 AI",
  avm: "자동감정평가 (AVM)",
  report_ai: "보고서 AI",
  site_analysis: "부지분석 AI",
  esg_ai: "ESG 분석 AI",
  finance_ai: "수지분석 AI",
};

const SERVICE_COLORS: Record<string, string> = {
  design_ai: "bg-[var(--chart-1)]",
  legal_ai: "bg-[var(--chart-2)]",
  avm: "bg-[var(--chart-3)]",
  report_ai: "bg-[var(--chart-4)]",
  site_analysis: "bg-[var(--chart-5)]",
  esg_ai: "bg-indigo-500",
  finance_ai: "bg-emerald-500",
};

function AnimatedCounter({ target, duration = 1200 }: { target: number; duration?: number }) {
  const [count, setCount] = useState(0);
  const startTimeRef = useRef<number | null>(null);
  const rafRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    startTimeRef.current = null;

    function animate(timestamp: number) {
      if (startTimeRef.current === null) startTimeRef.current = timestamp;
      const elapsed = timestamp - startTimeRef.current;
      const progress = Math.min(elapsed / duration, 1);
      // Ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setCount(Math.floor(eased * target));
      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate);
      }
    }

    rafRef.current = requestAnimationFrame(animate);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [target, duration]);

  return <>{count.toLocaleString("ko-KR")}</>;
}

function formatCurrency(value: number) {
  return new Intl.NumberFormat("ko-KR", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
  }).format(value);
}

// Mock data for when API is not available
const MOCK_USAGE: UsageData = {
  totalTokens: 1_847_320,
  totalCost: 24.56,
  budget: 100.0,
  dailyUsage: Array.from({ length: 14 }, (_, i) => ({
    date: new Date(Date.now() - (13 - i) * 86_400_000).toISOString().slice(0, 10),
    tokens: Math.floor(80_000 + Math.random() * 160_000),
  })),
  services: [
    { service: "design_ai", tokens: 520_400, cost: 6.93 },
    { service: "legal_ai", tokens: 412_100, cost: 5.49 },
    { service: "avm", tokens: 302_800, cost: 4.04 },
    { service: "report_ai", tokens: 268_020, cost: 3.57 },
    { service: "site_analysis", tokens: 198_000, cost: 2.64 },
    { service: "esg_ai", tokens: 96_000, cost: 1.28 },
    { service: "finance_ai", tokens: 50_000, cost: 0.61 },
  ],
};

export function AiTokenUsageDashboard() {
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function fetchUsage() {
      try {
        const data = await apiClient.get<UsageData>("/ai-costs/usage");
        if (!cancelled) setUsage(data);
      } catch {
        // Fallback to mock data
        if (!cancelled) setUsage(MOCK_USAGE);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    fetchUsage();
    return () => {
      cancelled = true;
    };
  }, []);

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((n) => (
          <div
            key={n}
            className="h-28 animate-pulse rounded-2xl bg-[var(--surface-soft)]"
          />
        ))}
      </div>
    );
  }

  if (!usage) return null;

  const budgetPercent = Math.min((usage.totalCost / usage.budget) * 100, 100);
  const budgetRemaining = Math.max(usage.budget - usage.totalCost, 0);
  const maxDailyTokens = Math.max(...usage.dailyUsage.map((d) => d.tokens), 1);

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardContent className="p-6">
            <p className="text-xs font-bold uppercase tracking-[0.15em] text-[var(--text-tertiary)]">
              이번 달 총 토큰 사용량
            </p>
            <p className="mt-3 text-3xl font-[900] tracking-tight text-[var(--text-primary)]">
              <AnimatedCounter target={usage.totalTokens} />
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <p className="text-xs font-bold uppercase tracking-[0.15em] text-[var(--text-tertiary)]">
              이번 달 총 비용
            </p>
            <p className="mt-3 text-3xl font-[900] tracking-tight text-[var(--text-primary)]">
              {formatCurrency(usage.totalCost)}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <p className="text-xs font-bold uppercase tracking-[0.15em] text-[var(--text-tertiary)]">
              예산 잔여
            </p>
            <p className="mt-3 text-3xl font-[900] tracking-tight text-[var(--accent-strong)]">
              {formatCurrency(budgetRemaining)}
            </p>
            <div className="mt-3 overflow-hidden rounded-full bg-[var(--surface-soft)] h-2">
              <div
                className={`h-full rounded-full transition-all duration-700 ${
                  budgetPercent > 80
                    ? "bg-[var(--spot)]"
                    : "bg-[var(--accent-strong)]"
                }`}
                style={{ width: `${budgetPercent}%` }}
              />
            </div>
            <p className="mt-1 text-xs text-[var(--text-hint)]">
              {budgetPercent.toFixed(1)}% 사용
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Service breakdown */}
      <Card>
        <CardContent className="p-6">
          <p className="text-xs font-bold uppercase tracking-[0.15em] text-[var(--text-tertiary)]">
            서비스별 비용 내역
          </p>
          <div className="mt-4 space-y-3">
            {usage.services.map((svc) => {
              const pct = usage.totalTokens
                ? (svc.tokens / usage.totalTokens) * 100
                : 0;
              const colorClass =
                SERVICE_COLORS[svc.service] ?? "bg-[var(--accent)]";
              return (
                <div key={svc.service} className="space-y-1">
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium text-[var(--text-primary)]">
                      {SERVICE_LABELS[svc.service] ?? svc.service}
                    </span>
                    <span className="text-[var(--text-secondary)]">
                      {svc.tokens.toLocaleString("ko-KR")} 토큰 &middot;{" "}
                      {formatCurrency(svc.cost)}
                    </span>
                  </div>
                  <div className="overflow-hidden rounded-full bg-[var(--surface-soft)] h-2">
                    <div
                      className={`h-full rounded-full ${colorClass} transition-all duration-500`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Daily usage chart */}
      <Card>
        <CardContent className="p-6">
          <p className="text-xs font-bold uppercase tracking-[0.15em] text-[var(--text-tertiary)]">
            일별 토큰 사용량 (최근 14일)
          </p>
          <div className="mt-4 flex items-end gap-1.5" style={{ height: 160 }}>
            {usage.dailyUsage.map((day) => {
              const heightPct = (day.tokens / maxDailyTokens) * 100;
              return (
                <div
                  key={day.date}
                  className="group relative flex-1"
                  style={{ height: "100%" }}
                >
                  <div
                    className="absolute bottom-0 w-full rounded-t-md bg-[var(--accent-strong)] transition-all duration-300 hover:bg-[var(--accent)]"
                    style={{ height: `${heightPct}%` }}
                  />
                  {/* Tooltip */}
                  <div className="pointer-events-none absolute -top-14 left-1/2 z-10 -translate-x-1/2 whitespace-nowrap rounded-lg bg-[var(--surface-strong)] px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] opacity-0 shadow-lg transition-opacity group-hover:opacity-100 border border-[var(--line)]">
                    <span>{day.date.slice(5)}</span>
                    <br />
                    <span className="text-[var(--accent-strong)]">
                      {day.tokens.toLocaleString("ko-KR")}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-2 flex justify-between text-[10px] text-[var(--text-hint)]">
            <span>{usage.dailyUsage[0]?.date.slice(5)}</span>
            <span>{usage.dailyUsage[usage.dailyUsage.length - 1]?.date.slice(5)}</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
