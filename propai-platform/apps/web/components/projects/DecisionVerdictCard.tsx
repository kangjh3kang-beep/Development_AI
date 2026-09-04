"use client";

/**
 * DecisionVerdictCard — Stage1 통합 의사결정 '종합 판정' 카드.
 *
 * 비전문가도 "이 땅, 추진할까?"에 한 화면에서 답을 얻도록:
 *   - decision 큰 배지: GO(녹색) / CONDITIONAL(황색) / HOLD(적색)
 *   - confidence(신뢰도) + go_nogo 디벨로퍼 Go/No-Go 배지
 *   - 핵심 KPI(통합면적·실효용적률·예상GFA·예상분양가·1순위 사업성) — parts에서 추출
 *   - reasons(판정 근거) / blockers(차단 사유)
 *   - ★일반인/전문가 모드 토글
 *       · 일반인: 한 줄 결론 + 핵심 근거 3개(쉬운 설명)
 *       · 전문가: 수치·근거 전체(KPI 그리드·전체 reasons·blockers·게이트)
 *
 * 순수 presentational — 네트워크 호출·store 접근 없음. lucide-react 아이콘(이모지 금지)·
 * 디자인 토큰(CSS 변수)만 사용.
 */

import { useState } from "react";
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ShieldAlert,
} from "lucide-react";
import type {
  DecisionBrief,
  DecisionBriefPart,
  DecisionVerdictDecision,
} from "@/components/projects/decision-brief-types";

/** decision별 색·라벨·아이콘·한줄결론(일반인용). */
const DECISION_META: Record<
  DecisionVerdictDecision,
  {
    label: string;
    token: string;
    icon: typeof CheckCircle2;
    plain: string;
  }
> = {
  GO: {
    label: "추진 권고 (GO)",
    token: "--status-success",
    icon: CheckCircle2,
    plain: "지금 조건에서 사업을 추진해 볼 만합니다.",
  },
  CONDITIONAL: {
    label: "조건부 추진 (CONDITIONAL)",
    token: "--status-warning",
    icon: AlertTriangle,
    plain: "몇 가지 선행 조건을 충족하면 추진할 수 있습니다.",
  },
  HOLD: {
    label: "보류 (HOLD)",
    token: "--status-error",
    icon: XCircle,
    plain: "지금은 추진을 보류하고 제약을 먼저 해소해야 합니다.",
  },
};

/** confidence 한국어 라벨. */
const CONFIDENCE_LABEL: Record<string, string> = {
  high: "높음",
  medium: "보통",
  low: "낮음",
};

/** go_nogo.status 한국어 폴백 라벨 — decision 문구가 없을 때 영문 status 노출을 막는다. */
const GO_NOGO_STATUS_LABEL: Record<string, string> = {
  go: "추진 권고",
  conditional: "조건부",
  hold: "보류",
};

/**
 * 상태(go/conditional/hold) → CSS 색 토큰 단일 매핑(헬퍼 단일화).
 * go_nogo 배지 색·테두리·배경이 같은 매핑을 중복 인라인하던 것을 한 곳으로 모은다(드리프트 방지).
 * 알 수 없는 상태는 보수적으로 error 토큰(가짜 성공색 금지).
 */
function statusToken(status: string | null | undefined): string {
  if (status === "go") return "--status-success";
  if (status === "conditional") return "--status-warning";
  return "--status-error";
}

/**
 * 디벨로퍼 권고('추진/Go')가 최종 verdict 보다 낙관적인데 최종이 CONDITIONAL/HOLD 로 강등됐는지.
 *
 * ★주의: 백엔드 _go_nogo_passthrough 는 go_nogo.status 를 '최종 verdict' 기준으로 맞춰 보내므로
 *   status 로는 강등을 알 수 없다. 디벨로퍼의 '원' 권고는 go_nogo.decision 한국어 문구에 있다
 *   (예 'Go(추진 권고)'·'조건부 Go'·'보류'·'No-Go'). 이 원 권고가 최종보다 낙관적이면 게이트
 *   강등(특이부지/법규/잠정)으로 보고 '(게이트 강등)' 보조표기를 단다(텍스트만 보고 GO로 오인 방지).
 */
function devRecoRank(decision: string | null | undefined): number {
  const d = decision ?? "";
  if (d.includes("No-Go") || d.toLowerCase().includes("no-go")) return 0; // 차단(가장 보수적)
  if (d.includes("보류")) return 0;
  if (d.includes("조건부")) return 1;
  if (d.includes("추진") || d === "Go" || d.startsWith("Go(")) return 2; // 추진(가장 낙관)
  return -1; // 알 수 없음 — 비교 생략
}

function isGateDowngraded(
  goNogo: { decision?: string | null; status?: string | null } | null,
  verdictDecision: string,
): boolean {
  if (!goNogo) return false;
  const devRank = devRecoRank(goNogo.decision);
  if (devRank < 0) return false; // 원 권고 불명 → 강등 판정 생략(보수)
  const verdictRank =
    verdictDecision === "GO" ? 2 : verdictDecision === "CONDITIONAL" ? 1 : 0;
  // 디벨로퍼 원 권고가 최종보다 낙관적(큰 값)이면 게이트 강등.
  return devRank > verdictRank;
}

/**
 * part.key_metrics에서 안정 key로 값을 찾아 '값+단위' 문자열로(미확보=null).
 *
 * ★key(백엔드 key_metrics 'key')로 조회한다 — 라벨은 표시 전용이라 라벨 문구가 바뀌어도
 *   silent-null이 나지 않는다(라벨 강결합 제거). 구 응답(key 없음)은 fallbackLabel로 폴백해
 *   하위호환을 유지한다(무회귀).
 */
function findMetric(
  parts: DecisionBriefPart[],
  partId: string,
  key: string,
  fallbackLabel?: string,
): string | null {
  const part = parts.find((p) => p.part === partId);
  if (!part) return null;
  const m =
    part.key_metrics.find((k) => k.key === key) ??
    (fallbackLabel
      ? part.key_metrics.find((k) => k.label === fallbackLabel)
      : undefined);
  if (!m || m.value === null || m.value === undefined || m.value === "") return null;
  const v = typeof m.value === "number" ? m.value.toLocaleString() : m.value;
  return m.unit ? `${v}${m.unit}` : v;
}

export function DecisionVerdictCard({ brief }: { brief: DecisionBrief }) {
  // 기본 일반인 모드(비전문가 우선). 전문가 토글 시 수치·근거 전체 노출.
  const [expert, setExpert] = useState(false);
  const v = brief.verdict;
  const meta = DECISION_META[v.decision as DecisionVerdictDecision] ?? DECISION_META.HOLD;
  const Icon = meta.icon;
  const parts = brief.parts ?? [];

  // 핵심 KPI — parts(표준 계약)에서 안정 key로 추출(라벨 강결합 제거·SSOT 단일 출처).
  //   fallbackLabel은 구 응답(key 없음) 하위호환용 — 신규 응답은 key로만 매칭된다.
  const landArea = findMetric(parts, "site_market", "land_area", "대지면적");
  const kpis: { label: string; value: string | null }[] = [
    {
      label: "통합 면적",
      value:
        brief.parcel_count > 1 && landArea
          ? `${landArea} (${brief.parcel_count}필지)`
          : landArea,
    },
    {
      label: "실효 용적률",
      value: findMetric(parts, "site_market", "effective_far", "실효 용적률"),
    },
    {
      label: "예상 GFA",
      value: findMetric(parts, "site_market", "gfa", "계획 연면적(GFA)"),
    },
    {
      label: "예상 분양가",
      value: findMetric(parts, "site_market", "presale_price", "예상 분양가"),
    },
    {
      label: "개략 사업성(ROI)",
      value: findMetric(parts, "permit_design", "roi", "1순위 ROI(사업수익률)"),
    },
  ];
  const availableKpis = kpis.filter((k) => k.value !== null);

  return (
    <div
      className="flex flex-col gap-5 rounded-[var(--radius-xl)] border p-7 shadow-[var(--shadow-2xl)]"
      style={{
        borderColor: `color-mix(in srgb, var(${meta.token}) 40%, transparent)`,
        backgroundColor: `color-mix(in srgb, var(${meta.token}) 6%, var(--surface-strong))`,
      }}
    >
      {/* 헤더: 큰 결정 배지 + 모드 토글 */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-4">
          <span
            className="flex h-14 w-14 shrink-0 items-center justify-center rounded-3xl"
            style={{
              color: `var(${meta.token})`,
              backgroundColor: `color-mix(in srgb, var(${meta.token}) 16%, transparent)`,
            }}
            aria-hidden
          >
            <Icon className="size-7" />
          </span>
          <div className="flex flex-col gap-1">
            <span className="label-caps text-[var(--text-hint)]">
              통합 의사결정
            </span>
            <span
              className="text-2xl font-[1000] tracking-tight"
              style={{ color: `var(${meta.token})` }}
            >
              {meta.label}
            </span>
          </div>
        </div>

        {/* 일반인/전문가 모드 토글 */}
        <div
          className="inline-flex items-center gap-0.5 rounded-full border border-[var(--line)] bg-[var(--surface-soft)] p-1"
          role="group"
          aria-label="표시 모드"
        >
          <button
            type="button"
            onClick={() => setExpert(false)}
            aria-pressed={!expert}
            className={`rounded-full px-4 py-1.5 text-[11px] font-black uppercase tracking-wider transition-all ${
              !expert
                ? "bg-[var(--accent-strong)] text-white shadow-sm"
                : "text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
            }`}
          >
            일반인
          </button>
          <button
            type="button"
            onClick={() => setExpert(true)}
            aria-pressed={expert}
            className={`rounded-full px-4 py-1.5 text-[11px] font-black uppercase tracking-wider transition-all ${
              expert
                ? "bg-[var(--accent-strong)] text-white shadow-sm"
                : "text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
            }`}
          >
            전문가
          </button>
        </div>
      </div>

      {/* 신뢰도 + 디벨로퍼 Go/No-Go 배지 줄 */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-[var(--surface-soft)] px-3 py-1 text-[11px] font-bold text-[var(--text-secondary)] border border-[var(--line)]">
          신뢰도 {CONFIDENCE_LABEL[v.confidence] ?? v.confidence}
        </span>
        {v.go_nogo?.status && (
          <span
            className="rounded-full px-3 py-1 text-[11px] font-black"
            style={{
              color: `var(${statusToken(v.go_nogo.status)})`,
              backgroundColor: `color-mix(in srgb, var(${statusToken(v.go_nogo.status)}) 14%, transparent)`,
            }}
          >
            디벨로퍼{" "}
            {v.go_nogo.decision ||
              GO_NOGO_STATUS_LABEL[v.go_nogo.status ?? ""] ||
              v.go_nogo.status}
            {/* ★게이트 강등 보조표기 — 디벨로퍼 원 권고가 최종보다 낙관적이면 모순 오인 방지 */}
            {isGateDowngraded(v.go_nogo, v.decision) && (
              <span className="ml-1 font-bold opacity-80">(게이트 강등)</span>
            )}
          </span>
        )}
        {v.gate && v.gate !== "PASS" && (
          <span className="inline-flex items-center gap-1 rounded-full bg-[color-mix(in_srgb,var(--status-warning)_14%,transparent)] px-3 py-1 text-[11px] font-bold text-[var(--status-warning)]">
            <ShieldAlert className="size-3.5" aria-hidden />
            게이트 {v.gate}
          </span>
        )}
      </div>

      {/* 일반인 결론 한 줄(항상 표시 — 비전문가 우선) */}
      <p className="text-base font-bold leading-relaxed text-[var(--text-primary)]">
        {meta.plain}
      </p>

      {expert ? (
        // ── 전문가 모드: KPI 그리드 + 전체 reasons + blockers + 게이트 ──
        <div className="flex flex-col gap-5">
          {availableKpis.length > 0 && (
            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-5">
              {availableKpis.map((k) => (
                <div
                  key={k.label}
                  className="flex flex-col gap-1 rounded-2xl bg-[var(--surface-soft)] px-3.5 py-3 border border-[var(--line)]"
                >
                  <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-hint)]">
                    {k.label}
                  </span>
                  <span className="text-sm font-black tracking-tight text-[var(--text-primary)]">
                    {k.value}
                  </span>
                </div>
              ))}
            </div>
          )}

          {v.reasons.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <span className="label-caps text-[var(--text-hint)]">
                판정 근거
              </span>
              <ul className="flex flex-col gap-1">
                {v.reasons.map((r, i) => (
                  <li
                    key={i}
                    className="text-[13px] leading-relaxed text-[var(--text-secondary)]"
                  >
                    · {r}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {v.blockers.length > 0 && (
            <div className="flex flex-col gap-1.5 rounded-2xl border border-[color-mix(in_srgb,var(--status-error)_30%,transparent)] bg-[color-mix(in_srgb,var(--status-error)_6%,transparent)] px-4 py-3">
              <span className="inline-flex items-center gap-1.5 label-caps text-[var(--status-error)]">
                <ShieldAlert className="size-3.5" aria-hidden />
                차단 사유
              </span>
              <ul className="flex flex-col gap-1">
                {v.blockers.map((b, i) => (
                  <li
                    key={i}
                    className="text-[13px] leading-relaxed text-[var(--text-secondary)]"
                  >
                    · {b}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : (
        // ── 일반인 모드: 핵심 근거 3개만(쉬운 설명) ──
        v.reasons.length > 0 && (
          <ul className="flex flex-col gap-1.5">
            {v.reasons.slice(0, 3).map((r, i) => (
              <li
                key={i}
                className="flex items-start gap-2 text-[13px] leading-relaxed text-[var(--text-secondary)]"
              >
                <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-[var(--accent-strong)]" aria-hidden />
                {r}
              </li>
            ))}
          </ul>
        )
      )}
    </div>
  );
}
