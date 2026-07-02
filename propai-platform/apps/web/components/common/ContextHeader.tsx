"use client";

/**
 * ContextHeader — 생성허브 공용 "대상 컨텍스트" 상단 바 (공용).
 *
 * 왜 필요한가(사용자 지적 직접 해소):
 * 생성허브 6산출물(후보지진단서·사업성검토서·시장분양리포트·인허가체크리스트·AI설계검토서·
 * 건축개요CAD)이 서로 다른 셸에 흩어져, "이 산출물이 '어느 프로젝트·어느 토지'를 대상으로
 * 분석한 것인지" 화면에 나타나지 않았다. 이 공용 바를 6페이지 상단에 상시 얹어, 어디서 무엇을
 * 보든 대상(프로젝트명·주소·PNU·용도지역·대지면적)을 한 줄로 확인하게 한다.
 *
 * 데이터원(SSOT): useProjectContextStore — projectId/projectName/siteAnalysis. 파생은 순수 함수
 * deriveContextHeaderData(lib/context-header)로 위임(다필지 통합면적·용도 정규화 재사용).
 *
 * ★무목업: 컨텍스트가 없으면 "대상 미선택"으로 정직 안내(가짜 값 표시 금지).
 * ★디자인 토큰만 사용(--accent-strong·--surface-secondary·--line 등). 컴팩트 바 형태.
 * ★근거 툴팁: 용도지역·면적 근거를 EvidencePanel(LegalRefChip 재사용)로 접이식 노출(있을 때만).
 */

import { useState } from "react";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import {
  deriveContextHeaderData,
  type ContextHeaderData,
} from "@/lib/context-header";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";

/** ㎡ → 표시 문자열(정수 반올림 + 천단위 콤마). 미확보면 null. */
function areaText(sqm: number | null): string | null {
  if (typeof sqm !== "number" || !(sqm > 0)) return null;
  return `${Math.round(sqm).toLocaleString()}㎡`;
}

/** 개별 컨텍스트 항목 칩(라벨 + 값). 값이 없으면 "—"로 정직 표기. */
function ContextChip({
  label,
  value,
  badge,
}: {
  label: string;
  value: string | null;
  badge?: string | null;
}) {
  return (
    <span className="inline-flex min-w-0 items-baseline gap-1.5">
      <span className="shrink-0 text-[10px] font-bold uppercase tracking-wider text-[var(--text-hint)]">
        {label}
      </span>
      <span
        className={`truncate text-[12px] font-semibold ${
          value ? "text-[var(--text-primary)]" : "text-[var(--text-hint)]"
        }`}
        title={value ?? undefined}
      >
        {value ?? "—"}
      </span>
      {badge && (
        <span className="shrink-0 rounded-full border border-[var(--accent-strong)]/40 bg-[var(--accent-strong)]/10 px-1.5 py-0.5 text-[10px] font-bold leading-none text-[var(--accent-strong)]">
          {badge}
        </span>
      )}
    </span>
  );
}

/** 용도지역·면적 근거 트레이스를 store SSOT에서 구성(있을 때만·무목업). */
function buildEvidenceItems(
  data: ContextHeaderData,
  farBasis: string | null,
): EvidenceItem[] {
  const items: EvidenceItem[] = [];
  if (data.zoneLabel) {
    items.push({
      label: "용도지역",
      value: data.zoneLabel,
      basis: data.isMultiParcel ? "다필지 통합 우세 용도지역(dominant)" : "부지분석 확정 용도지역",
    });
  }
  const area = areaText(data.landAreaSqm);
  if (area) {
    items.push({
      label: "대지면적",
      value: area,
      basis: data.isMultiParcel
        ? `다필지 통합면적(유효필지 ${data.parcelCount ?? "?"}필지 합계)`
        : "단일필지 대지면적",
    });
  }
  if (farBasis && data.zoneLabel) {
    items.push({ label: "실효 용적률 근거", value: farBasis });
  }
  return items;
}

export function ContextHeader({ className = "" }: { className?: string }) {
  const projectId = useProjectContextStore((s) => s.projectId);
  const projectName = useProjectContextStore((s) => s.projectName);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const [showEvidence, setShowEvidence] = useState(false);

  const data = deriveContextHeaderData({ projectId, projectName, siteAnalysis });
  const farBasis =
    typeof siteAnalysis?.farBasis === "string" && siteAnalysis.farBasis.trim()
      ? siteAnalysis.farBasis.trim()
      : null;
  const evidenceItems = buildEvidenceItems(data, farBasis);

  // 컨텍스트 미선택 — 정직 안내(무목업). 프로젝트도 주소도 없으면 "대상 미선택".
  if (!data.hasContext) {
    return (
      <div
        className={`flex items-center gap-2 rounded-xl border border-dashed border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2.5 ${className}`}
      >
        <span
          className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--surface-secondary)] text-[var(--text-hint)]"
          aria-hidden="true"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 8v4" />
            <path d="M12 16h.01" />
            <circle cx="12" cy="12" r="9" />
          </svg>
        </span>
        <span className="text-[12px] font-semibold text-[var(--text-secondary)]">
          대상 미선택 — 분석할 프로젝트·토지를 먼저 선택하세요.
        </span>
      </div>
    );
  }

  const area = areaText(data.landAreaSqm);

  return (
    <div
      className={`rounded-xl border border-[var(--line)] bg-[var(--surface-secondary)] px-4 py-2.5 shadow-[var(--shadow-sm,0_1px_2px_rgba(0,0,0,0.04))] ${className}`}
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
        {/* 대상 마커 — accent 강조로 "이 화면의 분석 대상"임을 명시 */}
        <span className="inline-flex shrink-0 items-center gap-1.5">
          <span
            className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-[var(--accent-strong)]/12 text-[var(--accent-strong)]"
            aria-hidden="true"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0z" />
              <circle cx="12" cy="10" r="3" />
            </svg>
          </span>
          <span className="text-[10px] font-black uppercase tracking-wider text-[var(--accent-strong)]">
            분석 대상
          </span>
        </span>

        <ContextChip label="프로젝트" value={data.projectName} />
        <span className="hidden h-3 w-px bg-[var(--line)] sm:block" aria-hidden="true" />
        <ContextChip label="주소" value={data.address} />
        <span className="hidden h-3 w-px bg-[var(--line)] sm:block" aria-hidden="true" />
        <ContextChip label="PNU" value={data.pnu} />
        <span className="hidden h-3 w-px bg-[var(--line)] sm:block" aria-hidden="true" />
        <ContextChip label="용도지역" value={data.zoneLabel} />
        <span className="hidden h-3 w-px bg-[var(--line)] sm:block" aria-hidden="true" />
        <ContextChip
          label="대지면적"
          value={area}
          badge={data.isMultiParcel ? `통합 ${data.parcelCount}필지` : null}
        />

        {/* 근거 토글 — 근거 항목이 있을 때만 노출(무목업: 근거 없으면 버튼 자체 미표시) */}
        {evidenceItems.length > 0 && (
          <button
            type="button"
            onClick={() => setShowEvidence((v) => !v)}
            aria-expanded={showEvidence}
            className="ml-auto shrink-0 text-[11px] font-semibold text-[var(--accent-strong)] hover:underline"
          >
            {showEvidence ? "근거 접기" : "근거 보기"}
          </button>
        )}
      </div>

      {showEvidence && evidenceItems.length > 0 && (
        <div className="mt-2">
          <EvidencePanel title="대상 컨텍스트 근거" items={evidenceItems} defaultOpen />
        </div>
      )}
    </div>
  );
}
