"use client";

import { useState, useEffect } from "react";

import { apiClient, ApiClientError } from "@/lib/api-client";
import { Card, CardContent } from "@propai/ui";

/* ------------------------------------------------------------------ */
/*  Types                                                             */
/* ------------------------------------------------------------------ */

type PlanTier = "free" | "pro" | "enterprise";

type UsageItem = {
  label: string;
  current: number;
  limit: number;
  unit: string;
};

/**
 * 백엔드 `GET /billing/status` 계약(`app/core/billing.public_status`) **그대로**.
 *
 * ★2026-08-27 — 이 패널은 `MOCK_PLAN` 을 렌더했고, 그 안의 사용량이
 *   `프로젝트 2/3개 · API 호출 347/500회 · AI 분석 18/30회 · 스토리지 156/500MB`
 *   였다. **백엔드에는 그런 건수 쿼터가 없다** — 과금 모델은 **예산(원) 기반**이다.
 *   과금 화면의 숫자가 허구인 것은 특히 나쁘다(사용자가 그것으로 판단한다).
 *   → 지어낸 4행은 **지웠고**, 서버가 실제로 주는 값만 그린다.
 *
 * ★플랜 **설명·기능 목록**은 서버가 주지 않는다 — 그건 정적 마케팅 문구이므로
 *   UI 상수로 남긴다. **가짜 데이터와 정적 문구는 다르다.**
 */
type BillingStatus = {
  tier: string | null;
  tier_label: string | null;
  metered: boolean | null;
  fee_krw: number | null;
  included_budget_krw: number | null;
  budget_krw: number | null;
  billed_krw: number | null;
  remaining_krw: number | null;
  usage_pct: number | null;
  blocked: boolean | null;
  service_fee_krw: number | null;
};

/** 서버 오류를 사람 말로 — ★상태코드를 삼키지 않는다. */
function describeErr(e: unknown, fallback: string): string {
  if (e instanceof ApiClientError) {
    if (e.status === 401 || e.status === 403) return "권한이 없습니다. 다시 로그인해 주세요.";
    const d =
      typeof e.payload === "object" && e.payload !== null && "detail" in e.payload
        ? String((e.payload as { detail: unknown }).detail)
        : "";
    return d || `${fallback} (HTTP ${e.status})`;
  }
  return fallback;
}

type PlanInfo = {
  tier: PlanTier;
  name: string;
  price: string;
  description: string;
  features: string[];
  /** ★카탈로그는 사용량을 갖지 않는다 — 사용량은 서버(`/billing/status`)에서 온다. */
  usage?: UsageItem[];
};

/* ------------------------------------------------------------------ */
/*  Plan definitions                                                  */
/* ------------------------------------------------------------------ */

const PLAN_DEFINITIONS: Record<PlanTier, Omit<PlanInfo, "usage">> = {
  free: {
    tier: "free",
    name: "무료",
    price: "0원/월",
    description: "개인 사용자를 위한 기본 플랜",
    features: [
      "프로젝트 3개까지",
      "API 호출 월 500회",
      "AI 분석 월 30회",
      "기본 보고서 생성",
      "이메일 지원",
    ],
  },
  pro: {
    tier: "pro",
    name: "프로",
    price: "99,000원/월",
    description: "전문 디벨로퍼를 위한 고급 플랜",
    features: [
      "프로젝트 무제한",
      "API 호출 월 10,000회",
      "AI 분석 월 500회",
      "은행제출용 보고서",
      "평형 구성 최적화",
      "GRESB ESG 스코어링",
      "우선 기술 지원",
    ],
  },
  enterprise: {
    tier: "enterprise",
    name: "엔터프라이즈",
    price: "별도 문의",
    description: "대규모 조직을 위한 맞춤형 플랜",
    features: [
      "모든 프로 기능 포함",
      "API 호출 무제한",
      "AI 분석 무제한",
      "전용 서버 배포",
      "SSO / SAML 인증",
      "맞춤 SLA",
      "전담 계정 매니저",
    ],
  },
};

/* ------------------------------------------------------------------ */
/*  정적 플랜 카탈로그(마케팅 문구) — **사용자 상태가 아니다**            */
/* ------------------------------------------------------------------ */

/**
 * ★종전 `MOCK_PLAN` 은 여기에 **지어낸 사용량 4행**을 붙였다:
 *   `프로젝트 2/3개 · API 호출 347/500회 · AI 분석 18/30회 · 스토리지 156/500MB`.
 *   백엔드에는 그런 **건수 쿼터가 없다**(과금은 예산(원) 기반). 지웠다.
 * ★설명·기능 목록은 서버가 주지 않는 **정적 마케팅 문구**라 그대로 둔다 —
 *   가짜 데이터와 정적 문구는 다르다.
 */
const PLAN_CATALOG = PLAN_DEFINITIONS;

/* ------------------------------------------------------------------ */
/*  UsageBar component                                                */
/* ------------------------------------------------------------------ */

/**
 * 서버가 준 **예산(원)** 을 사용량 막대로. ★없는 값은 **행을 만들지 않는다** —
 * 종전 목업이 지어낸 건수 쿼터(프로젝트/API/AI/스토리지)는 백엔드에 존재하지 않는다.
 */
function budgetUsage(b: BillingStatus | null): UsageItem[] {
  if (!b) return [];
  const rows: UsageItem[] = [];
  const budget = b.budget_krw ?? b.included_budget_krw;
  if (typeof b.billed_krw === "number" && typeof budget === "number" && budget > 0) {
    rows.push({ label: "이번 달 사용액", current: b.billed_krw, limit: budget, unit: "원" });
  }
  if (typeof b.service_fee_krw === "number" && b.service_fee_krw > 0
      && typeof budget === "number" && budget > 0) {
    rows.push({ label: "서비스 사용료", current: b.service_fee_krw, limit: budget, unit: "원" });
  }
  return rows;
}

function UsageBar({ item }: { item: UsageItem }) {
  const pct = Math.min((item.current / item.limit) * 100, 100);
  const isWarning = pct > 80;
  const isCritical = pct > 95;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-[var(--text-primary)]">
          {item.label}
        </span>
        <span className="cc-num text-xs text-[var(--text-secondary)]">
          <span className={`font-bold ${isCritical ? "text-[var(--status-error)]" : isWarning ? "text-[var(--status-warning)]" : "text-[var(--text-primary)]"}`}>
            {item.current.toLocaleString("ko-KR")}
          </span>
          {" / "}
          {item.limit.toLocaleString("ko-KR")}
          {item.unit}
        </span>
      </div>
      <div className="overflow-hidden rounded-full bg-[var(--surface-soft)] h-2.5">
        <div
          className={`h-full rounded-full transition-all duration-700 ${
            isCritical
              ? "bg-[var(--status-error)]"
              : isWarning
                ? "bg-[var(--status-warning)]"
                : "bg-[var(--data-accent)]"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main panel                                                        */
/* ------------------------------------------------------------------ */

export function SubscriptionPanel() {
  const [plan, setPlan] = useState<PlanInfo | null>(null);
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const st = await apiClient.get<BillingStatus>("/billing/status");
        if (!alive) return;
        setBilling(st);
        // ★현재 등급은 **서버가 정한다** — 화면이 고르지 않는다.
        //   설명·기능 목록만 정적 카탈로그에서 가져온다(마케팅 문구).
        const tier = (st?.tier ?? "free") as PlanTier;
        setPlan(PLAN_CATALOG[tier] ?? PLAN_CATALOG.free);
        setError("");
      } catch (e) {
        if (!alive) return;
        setBilling(null);
        setPlan(null);
        setError(describeErr(e, "요금제 정보를 불러오지 못했습니다."));
      } finally {
        if (alive) setIsLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  if (!isLoading && error) {
    return (
      <p
        role="alert"
        className="rounded-xl bg-[var(--status-error)]/10 px-3 py-2 text-xs text-[var(--status-error)]"
      >
        {error}
      </p>
    );
  }

  if (isLoading || !plan) {
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

  return (
    <div className="space-y-6">
      {/* Current plan card */}
      <Card className="overflow-hidden">
        <CardContent className="p-0">
          <div className="bg-gradient-to-r from-[var(--accent-strong)]/10 to-transparent p-6 border-b border-[var(--line)]">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-[var(--accent-strong)] border border-[var(--accent-strong)]/20">
                  <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M6 3h12l4 6-10 13L2 9Z" />
                  </svg>
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-lg font-bold text-[var(--text-primary)]">
                      현재 플랜: {plan.name}
                    </h3>
                    <span className="cc-chip-data">
                      {plan.tier.toUpperCase()}
                    </span>
                  </div>
                  <p className="text-sm text-[var(--text-secondary)] mt-0.5">
                    {plan.description}
                  </p>
                </div>
              </div>
              <p className="cc-num text-2xl font-[900] text-[var(--text-primary)]">
                {plan.price}
              </p>
            </div>
          </div>

          {/* Features */}
          <div className="p-6">
            <p className="cc-label mb-3">
              포함된 기능
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {(plan.features ?? []).map((feat, i) => (
                <div key={i} className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--status-success)] shrink-0">
                    <path d="M20 6 9 17l-5-5" />
                  </svg>
                  {feat}
                </div>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Usage */}
      <Card>
        <CardContent className="p-6">
          <p className="cc-label mb-5">
            이번 달 사용량
          </p>
          {/* ★락이 **이 영역만** 검사할 수 있게 표식을 준다 — 플랜 기능 목록의
              마케팅 문구("API 호출 월 500회")와 **사용자 실사용 숫자**는 다르다.
              범위를 안 나누면 락이 정적 문구를 가짜 데이터로 신고한다(첫 실행에서 그랬다). */}
          <div className="space-y-5" data-testid="billing-usage">
            {budgetUsage(billing).map((item) => (
              <UsageBar key={item.label} item={item} />
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Upgrade cards */}
      <div>
        <p className="cc-label mb-4">
          플랜 업그레이드
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          {(["pro", "enterprise"] as PlanTier[])
            .filter((t) => t !== plan.tier)
            .map((tier) => {
              const def = PLAN_DEFINITIONS[tier];
              return (
                <Card key={tier} className="group hover:shadow-[var(--shadow-lg)] transition-shadow">
                  <CardContent className="p-6 space-y-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <h4 className="text-sm font-bold text-[var(--text-primary)]">
                          {def.name}
                        </h4>
                        {tier === "pro" && (
                          <span className="rounded-md bg-[var(--status-warning)]/10 px-1.5 py-0.5 text-[10px] font-bold text-[var(--status-warning)]">
                            추천
                          </span>
                        )}
                      </div>
                      <p className="cc-num text-xl font-[900] text-[var(--text-primary)] mt-1">
                        {def.price}
                      </p>
                      <p className="text-xs text-[var(--text-secondary)] mt-1">
                        {def.description}
                      </p>
                    </div>

                    <div className="space-y-1.5">
                      {def.features.slice(0, 4).map((feat, i) => (
                        <div key={i} className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
                          <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--accent-strong)] shrink-0">
                            <path d="M20 6 9 17l-5-5" />
                          </svg>
                          {feat}
                        </div>
                      ))}
                      {def.features?.length > 4 && (
                        <p className="text-[10px] text-[var(--text-hint)] pl-5">
                          +{def.features.length - 4}개 기능 더
                        </p>
                      )}
                    </div>

                    <button className="w-full rounded-xl bg-[var(--accent-strong)] py-2.5 text-sm font-bold text-white hover:opacity-90 transition-opacity">
                      {tier === "enterprise" ? "문의하기" : "업그레이드"}
                    </button>
                  </CardContent>
                </Card>
              );
            })}
        </div>
      </div>

      {/* Billing info */}
      <div className="rounded-xl bg-[var(--surface-soft)] border border-[var(--line)] p-4 flex items-start gap-3">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--text-hint)] mt-0.5 shrink-0">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 16v-4" />
          <path d="M12 8h.01" />
        </svg>
        <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
          결제 및 청구서 관리는 프로 플랜 이상에서 사용 가능합니다.
          플랜 변경은 다음 결제일부터 적용되며, 미사용 기간은 일할 정산됩니다.
        </p>
      </div>
    </div>
  );
}
