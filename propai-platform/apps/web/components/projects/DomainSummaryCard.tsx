"use client";

/**
 * DomainSummaryCard — 도메인 무관 표준 요약 카드(공용).
 *
 * Stage1 통합 의사결정 브리프의 3개 통합 도메인 카드(①부지·입지·시장 통합 ②법규·규제
 * ③인허가·사업모델 Top3/설계개요)를 동일한 모양으로 렌더한다. 백엔드 표준 요약 계약
 * (DecisionBriefPart)을 그대로 받아:
 *   - title + 아이콘
 *   - summary_oneliner(한 줄 요약)
 *   - key_metrics 그리드(label · value · unit)
 *   - confidence 배지(high/medium/low)
 *   - status='unavailable'이면 정직하게 '데이터 없음 + 사유' 표시(가짜값 생성 금지)
 *   - evidence·legal_links → 공용 EvidencePanel 재사용(근거·법령 원문 링크)
 *   - detail_route CTA('상세 →') — locale prefix는 프론트가 붙인다(detailHref).
 *
 * 순수 presentational — 네트워크 호출·store 접근 없음. lucide-react 아이콘(이모지 금지)·
 * 디자인 토큰(CSS 변수)만 사용.
 */

import {
  Building2,
  Scale,
  ClipboardCheck,
  ArrowRight,
  AlertCircle,
} from "lucide-react";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";
import type {
  DecisionBriefPart,
  DecisionConfidence,
} from "@/components/projects/decision-brief-types";

/** part 식별자별 아이콘 요소(이모지 금지·lucide). 미상 part는 ClipboardCheck로 폴백. */
function partIconNode(part: string) {
  if (part === "site_market") return <Building2 className="size-5" />;
  if (part === "regulation") return <Scale className="size-5" />;
  return <ClipboardCheck className="size-5" />; // permit_design 등
}

/** confidence 라벨·색 토큰 매핑(high=success·medium=warning·low=error). */
const CONFIDENCE_META: Record<
  DecisionConfidence,
  { label: string; token: string }
> = {
  high: { label: "신뢰도 높음", token: "--status-success" },
  medium: { label: "신뢰도 보통", token: "--status-warning" },
  low: { label: "신뢰도 낮음", token: "--status-error" },
};

/** key_metric value를 사람이 읽는 문자열로(미확보=null이면 '미확보', 숫자는 천단위 콤마). */
function formatMetricValue(value: string | number | null): string {
  if (value === null || value === undefined || value === "") return "미확보";
  if (typeof value === "number") return value.toLocaleString();
  return value;
}

/**
 * 백엔드 evidence + legal_links → 공용 EvidencePanel의 EvidenceItem[]로 변환.
 * - evidence[{label,value,basis}] → {label,value,basis}
 * - legal_links[{label,url}] → {label,value:'법령',legalRef:{lawName:label,url}}
 *   (LegalRefChip이 url 없으면 텍스트만 렌더 — 죽은링크 금지 보장)
 */
function toEvidenceItems(part: DecisionBriefPart): EvidenceItem[] {
  const items: EvidenceItem[] = [];
  for (const e of part.evidence ?? []) {
    if (!e || !e.label) continue;
    items.push({
      label: e.label,
      value: e.value ?? "—",
      basis: e.basis ?? null,
    });
  }
  for (const l of part.legal_links ?? []) {
    if (!l || !l.label) continue;
    items.push({
      label: l.label,
      value: "법령",
      legalRef: { lawName: l.label, url: l.url ?? null },
    });
  }
  return items;
}

export function DomainSummaryCard({
  part,
  detailHref,
}: {
  part: DecisionBriefPart;
  /** locale prefix가 적용된 상세 페이지 경로(프론트 책임). 없으면 CTA 숨김. */
  detailHref?: string | null;
}) {
  const iconNode = partIconNode(part.part);
  const conf = CONFIDENCE_META[part.confidence] ?? CONFIDENCE_META.low;
  const unavailable = part.status === "unavailable";
  const evidenceItems = toEvidenceItems(part);

  return (
    <div className="flex flex-col gap-4 rounded-3xl border border-[var(--line)] bg-[var(--surface-soft)] p-6 shadow-sm">
      {/* 헤더: 아이콘 + 제목 + confidence 배지 */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-[var(--accent-strong)]"
            aria-hidden
          >
            {iconNode}
          </span>
          <h4 className="text-base font-black tracking-tight text-[var(--text-primary)]">
            {part.title}
          </h4>
        </div>
        <span
          className="shrink-0 rounded-full px-2.5 py-1 text-[10px] font-black uppercase tracking-wider"
          style={{
            color: `var(${conf.token})`,
            backgroundColor: `color-mix(in srgb, var(${conf.token}) 14%, transparent)`,
          }}
        >
          {conf.label}
        </span>
      </div>

      {/* 한 줄 요약 */}
      <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
        {part.summary_oneliner}
      </p>

      {unavailable ? (
        // 정직 미확보 — 가짜값 금지. 사유를 명시 표기한다.
        <div className="flex items-start gap-2.5 rounded-2xl border border-dashed border-[var(--line-strong)] bg-[var(--surface-strong)] px-4 py-3">
          <AlertCircle
            className="mt-0.5 size-4 shrink-0 text-[var(--status-warning)]"
            aria-hidden
          />
          <div className="flex flex-col gap-0.5">
            <span className="text-xs font-black text-[var(--text-primary)]">
              데이터 없음
            </span>
            <span className="text-[11px] leading-relaxed text-[var(--text-tertiary)]">
              {part.reason || "데이터 미확보(정직 고지)."}
            </span>
          </div>
        </div>
      ) : (
        // key_metrics 그리드 — 실값만 표시(미확보는 '미확보' 정직 표기).
        part.key_metrics.length > 0 && (
          <div className="grid grid-cols-2 gap-2.5">
            {part.key_metrics.map((m, i) => (
              <div
                key={`${m.key ?? m.label}-${i}`}
                className="flex flex-col gap-1 rounded-2xl bg-[var(--surface-strong)] px-3.5 py-2.5 border border-[var(--line)]"
              >
                <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-hint)]">
                  {m.label}
                </span>
                <span className="text-sm font-black tracking-tight text-[var(--text-primary)]">
                  {formatMetricValue(m.value)}
                  {m.unit && m.value !== null && m.value !== "" ? (
                    <span className="ml-0.5 text-[11px] font-bold text-[var(--text-tertiary)]">
                      {m.unit}
                    </span>
                  ) : null}
                </span>
              </div>
            ))}
          </div>
        )
      )}

      {/* 잠정 시나리오(선행절차 전제) 정직 신호 — 인허가 part */}
      {part.scenario_status === "tentative" && (
        <p className="text-[11px] font-bold text-[var(--status-warning)]">
          ※ 잠정 시나리오 — 선행절차(인허가·도로조건 등) 충족을 전제로 한 추정입니다.
        </p>
      )}
      {part.honest_disclosure && (
        <p className="text-[11px] leading-relaxed text-[var(--text-tertiary)]">
          {part.honest_disclosure}
        </p>
      )}

      {/* 근거·법령 원문 — 공용 EvidencePanel 재사용(항목 없으면 자동 미렌더) */}
      {evidenceItems.length > 0 && (
        <EvidencePanel title="근거 보기" items={evidenceItems} defaultOpen={false} />
      )}

      {/* 상세 CTA — locale prefix는 detailHref에 이미 적용됨(프론트 책임) */}
      {detailHref && (
        <a
          href={detailHref}
          className="mt-1 inline-flex w-fit items-center gap-1.5 rounded-full bg-[var(--accent-soft)] px-4 py-2 text-[11px] font-black uppercase tracking-wider text-[var(--accent-strong)] transition-all hover:gap-2.5"
        >
          상세 분석
          <ArrowRight className="size-3.5" aria-hidden />
        </a>
      )}
    </div>
  );
}
