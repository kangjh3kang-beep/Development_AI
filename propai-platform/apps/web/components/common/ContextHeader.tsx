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
 *
 * ★옵셔널 pipeline prop: 각 산출물 페이지가 자신이 아는 실제 분석 상태(수집/검증/전문가 LLM)를
 *   PipelineStep[]로 넘기면 AnalysisPipelineStepbar를 헤더 하단에 함께 렌더한다(계약보존 —
 *   미전달 시 기존 헤더만 그대로, 회귀 없음). 상태를 모르는 페이지는 생략(정직: idle 날조 금지 —
 *   호출측이 모르면 아예 prop을 넘기지 않는다).
 * ★sitePipeline=true 단축 옵션: 부지분석(siteAnalysis) SSOT만으로 판정 가능한 산출물(예:
 *   후보지진단)은 원시 상태를 페이지가 다시 조회할 필요 없이 이 플래그만 켜면
 *   deriveSitePipelineSteps(이미 읽고 있는 siteAnalysis 재사용)로 자동 파생한다. 명시적
 *   pipeline prop이 함께 오면 그쪽이 우선(호출측이 더 정확한 상태를 안다고 간주).
 */

import { useState } from "react";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { classifySelection } from "@/lib/selection-integrity";
import {
  deriveContextHeaderData,
  deriveSitePipelineSteps,
  withAsOf,
  type ContextHeaderData,
} from "@/lib/context-header";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";
import {
  AnalysisPipelineStepbar,
  type PipelineStep,
} from "@/components/common/AnalysisPipelineStepbar";

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
/** ★export 하는 이유: 근거 문구는 사용자가 "근거 보기" 로 확인하는 자리라 **거짓이면 근거
 *  없음보다 나쁘다**. 그런데 변이로 확인하니 이 문구가 **무잠금**이었다 — 거짓 문구
 *  ("다필지 통합 우세 용도지역(dominant)")로 되돌려도 전부 초록이었다.
 *  컴포넌트를 띄우지 않고 순수 함수로 잠글 수 있게 공개한다. */
export function buildEvidenceItems(
  data: ContextHeaderData,
  farBasis: string | null,
): EvidenceItem[] {
  const items: EvidenceItem[] = [];
  if (data.zoneLabel) {
    items.push({
      label: "용도지역",
      value: data.zoneLabel,
      // ★거짓 근거를 걷어낸다(2026-08-24) — "우세(dominant)" 라고 적었지만 이 값의 출처는
      //   `dominantZoneCode ?? zoneCode` 이고 둘 다 **대표(첫) 필지** 값이었다. 근거 트레이스는
      //   사용자가 "근거 보기" 를 눌러 확인하는 자리다 — **거짓 근거는 근거 없음보다 나쁘다**.
      //   진짜 우세 용도지역은 서버가 면적합산으로 판정하며 구획도 통합 종합분석에 표시된다.
      // ★근거에 **기준 시각**을 덧붙인다 — 이 값이 언제 확정된 것인지 말하지 않으면
      //   사용자는 낡은 저장본을 현재 사실로 읽는다(2026-08-24 라이브 증상).
      basis: withAsOf(
        data.isMultiParcel
          ? "다필지 대표(첫) 필지 용도지역 — 면적 우세 용도지역은 구획도 '통합 종합분석' 참조"
          : "부지분석 확정 용도지역",
        data.fetchedAt,
      ),
    });
  }
  const area = areaText(data.landAreaSqm);
  if (area) {
    items.push({
      label: "대지면적",
      value: area,
      // ★단정하지 않는다 — SSOT 가 준 basis 를 그대로 말한다.
      //   `representative` 는 **다필지인데 통합면적을 아직 못 구해 대표 1필지 면적을 쓰는**
      //   상태다. 이걸 "N필지 합계"라고 부르면 거짓 근거가 된다(실물: 33필지에 543㎡).
      basis: withAsOf(
        data.landAreaBasis === "integrated"
          ? `다필지 통합면적(유효필지 ${data.parcelCount ?? "?"}필지 합계)`
          : data.landAreaBasis === "representative"
            ? `★대표 1필지 면적 — 통합면적 미확보(선택 ${data.parcelCount ?? "?"}필지 전체 합계가 아닙니다)`
            : "단일필지 대지면적",
        data.fetchedAt,
      ),
    });
  }
  if (farBasis && data.zoneLabel) {
    items.push({ label: "실효 용적률 근거", value: farBasis });
  }
  return items;
}

export function ContextHeader({
  className = "",
  pipeline,
  pipelineTitle,
  sitePipeline = false,
}: {
  className?: string;
  /** 이 산출물의 실제 분석 3단계 상태(수집/검증/전문가 LLM). 미전달 시 스텝바 미표시(무회귀). */
  pipeline?: PipelineStep[];
  /** 스텝바 제목(미전달 시 AnalysisPipelineStepbar 기본값 "분석 파이프라인" 사용). */
  pipelineTitle?: string;
  /** true면 siteAnalysis SSOT에서 3단계를 자동 파생(deriveSitePipelineSteps). pipeline이 함께
   *  오면 pipeline이 우선. 기본 false(무회귀 — 명시적으로 켠 페이지만 자동 파생). */
  sitePipeline?: boolean;
}) {
  const projectId = useProjectContextStore((s) => s.projectId);
  const projectName = useProjectContextStore((s) => s.projectName);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);

  // ★헤더가 "통합 N필지"라고 **단정**하던 것을 멈춘다(2026-08-24 · 라이브 화면에서 발견).
  //   선택 화면 배너는 이미 "하나의 개발 부지가 아닙니다(최대 290km)"라고 고지하는데,
  //   바로 위 헤더는 같은 순간 "대지면적 162,033㎡ · 통합 3필지"라고 말했다 —
  //   **한 화면이 자기모순**이다. 사용자는 위쪽(헤더)을 먼저 읽는다.
  //   ★판정은 선택 화면과 **같은 판별자**를 쓴다(산식 복제 금지 — 두 표면이 갈리면 그게 결함이다).
  const selectionVerdict = classifySelection(
    (siteAnalysis as { parcels?: Array<{ address?: string | null; lat?: number | null; lon?: number | null }> } | null)
      ?.parcels ?? null,
  ).verdict;
  // 설계 산출(designData) — 부지분석에 용도지역이 없을 때 설계 폼이 쓴 용도지역으로 폴백하기 위해 구독.
  const designData = useProjectContextStore((s) => s.designData);
  const [showEvidence, setShowEvidence] = useState(false);

  const data = deriveContextHeaderData({ projectId, projectName, siteAnalysis, designData });
  const farBasis =
    typeof siteAnalysis?.farBasis === "string" && siteAnalysis.farBasis.trim()
      ? siteAnalysis.farBasis.trim()
      : null;
  const evidenceItems = buildEvidenceItems(data, farBasis);
  // 명시적 pipeline이 우선(호출측이 더 정확한 상태를 안다고 간주), 없으면 sitePipeline 플래그일 때만
  // siteAnalysis SSOT에서 자동 파생(무회귀: 기본 false — 켜지 않은 페이지는 기존 동작 그대로).
  const effectivePipeline =
    pipeline ?? (sitePipeline ? deriveSitePipelineSteps(siteAnalysis) : undefined);

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
        <ContextChip
          label="용도지역"
          value={data.zoneLabel}
          badge={data.zoneSource === "design" ? "직접 입력" : null}
        />
        <span className="hidden h-3 w-px bg-[var(--line)] sm:block" aria-hidden="true" />
        <ContextChip
          label="대지면적"
          value={area}
          // ★하나의 부지가 아니면 "통합"이라 부르지 않는다 — 합계임을 밝힌다.
          badge={
            data.isMultiParcel
              ? selectionVerdict === "single_site"
                ? `통합 ${data.parcelCount}필지`
                : `${data.parcelCount}필지 합계 · 통합 부지 아님`
              : null
          }
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

      {/* 분석 파이프라인 3단계(옵셔널) — 호출측이 실제 상태를 아는 경우(pipeline) 또는
          sitePipeline=true(siteAnalysis SSOT 자동 파생)일 때만 렌더(무목업). */}
      {effectivePipeline && effectivePipeline.length > 0 && (
        <div className="mt-2">
          <AnalysisPipelineStepbar steps={effectivePipeline} title={pipelineTitle} />
        </div>
      )}
    </div>
  );
}
