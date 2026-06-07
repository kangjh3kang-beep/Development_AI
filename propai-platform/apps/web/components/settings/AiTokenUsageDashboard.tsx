"use client";

/**
 * LLM 사용량 모니터링 (실데이터).
 *
 * GET /billing/token-usage?days=30 → 총 토큰·마진포함 비용·서비스별·일별
 * GET /billing/balance            → 월기본 잔여·충전 잔여·이번주기 사용·마진율
 *
 * 무목업: 실 API만 사용하며, 데이터가 없으면 정직하게 안내한다.
 * 모든 LLM 분석은 호출 시 토큰계측·코인차감이 자동 반영(BaseInterpreter)되며,
 * 비용은 등급별 마진(낮은 등급 +50% / 중위 +40% / 최상위 +30%)이 포함된 금액이다.
 */

import { useEffect, useState, useRef, useCallback } from "react";
import { Card, CardContent } from "@propai/ui";
import { apiClient, ApiClientError } from "@/lib/api-client";

type ServiceUsage = { service: string; tokens: number; cost_krw: number };
type DailyUsage = { date: string; tokens: number; cost_krw: number };

type TokenUsage = {
  days: number;
  total_tokens: number;
  total_cost_krw: number;
  by_service: ServiceUsage[];
  daily: DailyUsage[];
};

type Balance = {
  tier: string;
  tier_label: string;
  monthly_base_krw: number;
  monthly_base_remaining: number;
  topup_krw: number;
  topup_remaining: number;
  used_this_cycle_krw: number;
  markup_pct: number;
  cycle_start: string | null;
};

const SERVICE_LABELS: Record<string, string> = {
  site_analysis: "부지분석 AI",
  market: "시장·시세 AI",
  feasibility: "수지분석 AI",
  esg: "ESG/탄소 AI",
  permit: "인허가 AI",
  cost: "공사비 AI",
  design: "설계 AI",
  tax: "세금분석 AI",
  avm: "자동감정평가 (AVM)",
  report: "보고서 AI",
  digital_twin: "디지털트윈 AI",
  llm: "기타 LLM",
};

const SERVICE_COLORS: Record<string, string> = {
  site_analysis: "bg-[var(--chart-1)]",
  market: "bg-[var(--chart-2)]",
  feasibility: "bg-[var(--chart-3)]",
  esg: "bg-[var(--chart-4)]",
  permit: "bg-[var(--chart-5)]",
  cost: "bg-indigo-500",
  design: "bg-emerald-500",
  tax: "bg-amber-500",
  avm: "bg-sky-500",
  report: "bg-rose-500",
  digital_twin: "bg-violet-500",
  llm: "bg-slate-500",
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

const won = (n: number) => (n ?? 0).toLocaleString("ko-KR") + "원";

export function AiTokenUsageDashboard() {
  const [usage, setUsage] = useState<TokenUsage | null>(null);
  const [balance, setBalance] = useState<Balance | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [authed, setAuthed] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const [u, b] = await Promise.all([
        apiClient.get<TokenUsage>("/billing/token-usage?days=30", { useMock: false }),
        apiClient.get<Balance>("/billing/balance", { useMock: false }),
      ]);
      setUsage(u);
      setBalance(b);
      setAuthed(true);
    } catch (e) {
      if (e instanceof ApiClientError && (e.status === 401 || e.status === 403)) {
        setAuthed(false);
      } else {
        setError("사용량 데이터를 불러오지 못했습니다.");
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((n) => (
          <div key={n} className="h-28 animate-pulse rounded-2xl bg-[var(--surface-soft)]" />
        ))}
      </div>
    );
  }

  if (!authed) {
    return (
      <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-8 text-center text-sm text-[var(--text-secondary)]">
        로그인 후 LLM 사용량을 확인할 수 있습니다.
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] p-8 text-center text-sm text-[var(--spot)]">
        {error}
      </div>
    );
  }

  if (!usage || !balance) return null;

  const totalTokens = usage.total_tokens || 0;
  const hasUsage = totalTokens > 0 || (usage.by_service?.length ?? 0) > 0;
  const totalRemaining = (balance.monthly_base_remaining || 0) + (balance.topup_remaining || 0);
  const maxDailyTokens = Math.max(...(usage.daily || []).map((d) => d.tokens), 1);

  return (
    <div className="space-y-6">
      {/* 요약 카드 */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardContent className="p-6">
            <p className="text-xs font-bold uppercase tracking-[0.15em] text-[var(--text-tertiary)]">
              최근 {usage.days}일 총 토큰 사용량
            </p>
            <p className="mt-3 text-3xl font-[900] tracking-tight text-[var(--text-primary)]">
              <AnimatedCounter target={totalTokens} />
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <p className="text-xs font-bold uppercase tracking-[0.15em] text-[var(--text-tertiary)]">
              최근 {usage.days}일 비용 (마진 포함)
            </p>
            <p className="mt-3 text-3xl font-[900] tracking-tight text-[var(--text-primary)]">
              {won(usage.total_cost_krw)}
            </p>
            <p className="mt-1 text-xs text-[var(--text-hint)]">
              {balance.tier_label} 등급 · 마진 +{balance.markup_pct}% 포함
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <p className="text-xs font-bold uppercase tracking-[0.15em] text-[var(--text-tertiary)]">
              코인 잔여 (월기본 + 충전)
            </p>
            <p className="mt-3 text-3xl font-[900] tracking-tight text-[var(--accent-strong)]">
              {won(totalRemaining)}
            </p>
            <div className="mt-3 space-y-1 text-xs text-[var(--text-hint)]">
              <div className="flex justify-between">
                <span>월 기본 잔여</span>
                <span className="font-bold text-[var(--text-secondary)]">{won(balance.monthly_base_remaining)} / {won(balance.monthly_base_krw)}</span>
              </div>
              <div className="flex justify-between">
                <span>충전 잔여</span>
                <span className="font-bold text-[var(--text-secondary)]">{won(balance.topup_remaining)} / {won(balance.topup_krw)}</span>
              </div>
              <div className="flex justify-between border-t border-[var(--line)] pt-1">
                <span>이번 주기 사용</span>
                <span className="font-bold text-[var(--text-secondary)]">{won(balance.used_this_cycle_krw)}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {!hasUsage ? (
        <Card>
          <CardContent className="p-8 text-center">
            <p className="text-sm font-medium text-[var(--text-secondary)]">
              최근 {usage.days}일간 LLM 분석 사용 내역이 없습니다.
            </p>
            <p className="mt-1.5 text-xs text-[var(--text-hint)]">
              부지분석·시장·수지·ESG·인허가·공사비 등 AI 분석을 실행하면 사용량과 코인 차감이 여기에 집계됩니다.
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* 서비스별 사용량 */}
          <Card>
            <CardContent className="p-6">
              <p className="text-xs font-bold uppercase tracking-[0.15em] text-[var(--text-tertiary)]">
                서비스별 사용량 (마진 포함 비용)
              </p>
              <div className="mt-4 space-y-3">
                {(usage.by_service ?? []).map((svc) => {
                  const pct = totalTokens ? (svc.tokens / totalTokens) * 100 : 0;
                  const colorClass = SERVICE_COLORS[svc.service] ?? "bg-[var(--accent)]";
                  return (
                    <div key={svc.service} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="font-medium text-[var(--text-primary)]">
                          {SERVICE_LABELS[svc.service] ?? svc.service}
                        </span>
                        <span className="text-[var(--text-secondary)]">
                          {svc.tokens.toLocaleString("ko-KR")} 토큰 &middot; {won(svc.cost_krw)}
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

          {/* 일별 추이 */}
          {(usage.daily?.length ?? 0) > 0 && (
            <Card>
              <CardContent className="p-6">
                <p className="text-xs font-bold uppercase tracking-[0.15em] text-[var(--text-tertiary)]">
                  일별 토큰 사용량 (최근 {usage.days}일)
                </p>
                <div className="mt-4 flex items-end gap-1.5" style={{ height: 160 }}>
                  {(usage.daily ?? []).map((day) => {
                    const heightPct = (day.tokens / maxDailyTokens) * 100;
                    return (
                      <div key={day.date} className="group relative flex-1" style={{ height: "100%" }}>
                        <div
                          className="absolute bottom-0 w-full rounded-t-md bg-[var(--accent-strong)] transition-all duration-300 hover:bg-[var(--accent)]"
                          style={{ height: `${heightPct}%` }}
                        />
                        <div className="pointer-events-none absolute -top-16 left-1/2 z-10 -translate-x-1/2 whitespace-nowrap rounded-lg bg-[var(--surface-strong)] px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] opacity-0 shadow-lg transition-opacity group-hover:opacity-100 border border-[var(--line)]">
                          <span>{day.date.slice(5)}</span>
                          <br />
                          <span className="text-[var(--accent-strong)]">{day.tokens.toLocaleString("ko-KR")} 토큰</span>
                          <br />
                          <span className="text-[var(--text-secondary)]">{won(day.cost_krw)}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
                <div className="mt-2 flex justify-between text-[10px] text-[var(--text-hint)]">
                  <span>{usage.daily[0]?.date.slice(5)}</span>
                  <span>{usage.daily[usage.daily.length - 1]?.date.slice(5)}</span>
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
