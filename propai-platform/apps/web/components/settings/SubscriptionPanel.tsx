"use client";

import { useState, useEffect } from "react";
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

type PlanInfo = {
  tier: PlanTier;
  name: string;
  price: string;
  description: string;
  features: string[];
  usage: UsageItem[];
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
/*  Mock current plan data                                            */
/* ------------------------------------------------------------------ */

const MOCK_PLAN: PlanInfo = {
  ...PLAN_DEFINITIONS.free,
  usage: [
    { label: "프로젝트", current: 2, limit: 3, unit: "개" },
    { label: "API 호출", current: 347, limit: 500, unit: "회" },
    { label: "AI 분석", current: 18, limit: 30, unit: "회" },
    { label: "스토리지", current: 156, limit: 500, unit: "MB" },
  ],
};

/* ------------------------------------------------------------------ */
/*  UsageBar component                                                */
/* ------------------------------------------------------------------ */

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
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setPlan(MOCK_PLAN);
    setIsLoading(false);
  }, []);

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
          <div className="space-y-5">
            {(plan.usage ?? []).map((item) => (
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
