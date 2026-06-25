"use client";

/**
 * DecisionReuseBanner — Tier2 드릴다운 패널이 Stage1 통합 의사결정 브리프(decisionBrief)에서
 * 해당 도메인 요약을 읽어 'Stage1 통합분석 기반' 컨텍스트로 재사용하는 공용 배너.
 *
 * 목적: 사용자가 Tier1 통합 브리프(DecisionBriefPanel)에서 도메인 카드 '상세'를 눌러 Tier2
 *   상세 페이지(인허가·사업성 등)로 이동하면, 그 페이지가 이미 산출된 Stage1 요약을 한 줄로
 *   보여줘 '같은 부지를 다시 처음부터' 분석하는 중복을 줄인다(인간개입 최소화·전문가 대행).
 *
 * ★재사용일 뿐 대체가 아니다: 이 배너는 기존 Tier2 폼/분석 흐름 위에 얹는 부가 컨텍스트다.
 *   store.decisionBrief(또는 해당 part)가 없으면 아무것도 렌더하지 않는다(폴백=기존 동작·무회귀).
 *
 * 순수 presentational — 네트워크 호출 없음. store에서 읽은 part만 받는다(부모가 주입).
 * lucide-react 아이콘(이모지 금지)·디자인 토큰(CSS 변수)만 사용.
 */

import { Sparkles } from "lucide-react";
import type { DecisionBriefPart } from "@/components/projects/decision-brief-types";

export function DecisionReuseBanner({
  part,
  /** 이 부지분석이 갱신돼 브리프가 stale일 수 있으면 true — 정직 고지(과신 방지). */
  stale = false,
}: {
  part: DecisionBriefPart | null;
  stale?: boolean;
}) {
  // 브리프(해당 part)가 없으면 폴백 — 아무것도 렌더하지 않는다(기존 동작 보존).
  if (!part) return null;
  // 정직성: 미확보(unavailable) part는 가짜 요약 위장 금지 — 배너를 띄우지 않는다.
  if (part.status === "unavailable") return null;
  const oneliner = part.summary_oneliner?.trim();
  if (!oneliner) return null;

  return (
    <div
      className="flex items-start gap-2.5 rounded-2xl border px-4 py-3"
      style={{
        borderColor: "color-mix(in srgb, var(--accent-strong) 30%, transparent)",
        backgroundColor: "color-mix(in srgb, var(--accent-strong) 6%, transparent)",
      }}
      role="note"
    >
      <Sparkles
        className="mt-0.5 size-4 shrink-0 text-[var(--accent-strong)]"
        aria-hidden
      />
      <div className="min-w-0">
        <p className="text-[11px] font-black uppercase tracking-wider text-[var(--accent-strong)]">
          Stage1 통합분석 기반
        </p>
        <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">
          {oneliner}
        </p>
        {stale && (
          <p className="mt-1 text-[11px] font-bold leading-relaxed text-[var(--status-warning)]">
            ※ 부지분석이 갱신되어 위 통합분석 요약이 최신이 아닐 수 있습니다(통합 브리프에서
            재분석 권장).
          </p>
        )}
      </div>
    </div>
  );
}
