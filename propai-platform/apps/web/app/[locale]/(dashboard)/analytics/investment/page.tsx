"use client";

import { useParams } from "next/navigation";
import { InvestmentFeasibilityClient } from "@/components/analytics/InvestmentFeasibilityClient";
import { CashflowDcfPanel } from "@/components/analytics/CashflowDcfPanel";
import { InvestmentAnalyticsWorkspaceClient } from "@/components/analytics/InvestmentAnalyticsWorkspaceClient";
import { RoughScenarioPanel } from "@/components/feasibility/RoughScenarioPanel";
import { ContextHeader } from "@/components/common/ContextHeader";
import { deriveFeasibilityPipelineSteps } from "@/lib/context-header";
import { isValidLocale, type Locale } from "@/i18n/config";
import { useProjectContextStore } from "@/store/useProjectContextStore";

/**
 * 투자수익성 분석 — 단일 세로 워크플로우.
 *
 * 예전엔 3개 패널(수동 DCF·수지표시·몬테카를로)이 단절·중복돼 '무엇을 하는 화면인지' 불명했다.
 * 이제 실무 순서대로 한 화면에서 연속 진행한다(각 단계는 앞 단계 결과를 이어받음):
 *   ① 프로젝트 컨텍스트(ContextHeader)
 *   ② 개략수지 base(RoughScenarioPanel) — 프로젝트선택·토지비·공사비·분양수입·20%마진·월별 DCF
 *   ③ 투자수익성 요약(InvestmentFeasibilityClient) — ROI·등급·전문가 검증
 *   ④ 리스크 시뮬(InvestmentAnalyticsWorkspaceClient) — 몬테카를로 손실확률·하방리스크·민감도
 *   보조 CashflowDcfPanel — 은행제출용 수동 세부조정(기본 접힘)
 *
 * 무목업: 프로젝트 미선택 시 하위 단계는 빈 패널 대신 '개략수지 생성 후 이용' 안내로 게이트한다.
 */

/** 워크플로우 단계 구분 헤더(로컬) — 각 단계가 '무엇을 하는지' 상시 명시.
 *  MarketInsights의 SectionDivider와 동일 시각언어(eyebrow=영문 단계 코드, kr=한글 제목)로 통일. */
function WorkflowStep({
  id,
  step,
  kr,
  en,
  desc,
}: {
  id?: string;
  step: string;
  kr: string;
  en: string;
  desc?: string;
}) {
  return (
    <div id={id} className={id ? "scroll-mt-24" : undefined}>
      <div className="flex items-center gap-3">
        <div className="flex flex-col">
          <span className="sa-di-eyebrow">
            {step} · {en}
          </span>
          <span className="text-lg font-black text-[var(--text-primary)]">{kr}</span>
        </div>
        <div className="h-px flex-1 bg-[var(--line)]" aria-hidden />
      </div>
      {desc && (
        <p className="mt-1.5 max-w-3xl text-xs leading-relaxed text-[var(--text-secondary)]">{desc}</p>
      )}
    </div>
  );
}

export default function InvestmentPage() {
  const { locale } = useParams() as { locale: string };
  const projectId = useProjectContextStore((s) => s.projectId);
  const feasibilityData = useProjectContextStore((s) => s.feasibilityData);
  const safeLocale: Locale = isValidLocale(locale) ? locale : "ko";

  // ★무목업 게이트 — 진입점(RoughScenarioPanel의 프로젝트 선택기)에서 프로젝트를 골라야
  //  하위 단계(요약·리스크·세부조정)를 의미있게 소비할 수 있다. 미선택이면 빈 패널 대신 안내.
  const hasProject = !!projectId;

  return (
    <div className="space-y-8">
      {/* 생성허브 공용 대상 컨텍스트 헤더 — 어느 프로젝트·토지 대상 사업성분석인지 상시 표시.
          pipeline: 수지(feasibilityData) SSOT에서 실제 상태 파생(수집=매출·원가, 검증=idle,
          전문가=등급 산출 여부). */}
      <ContextHeader pipeline={deriveFeasibilityPipelineSteps(feasibilityData)} />

      <div>
        <div className="mb-2 flex items-center gap-3">
          <span className="cc-meta">INVESTMENT · FEASIBILITY CONSOLE</span>
          <span className="cc-live">
            <i />
            LIVE
          </span>
        </div>
        <h1 className="text-3xl font-black tracking-tight text-[var(--text-primary)]">투자수익성 분석</h1>
        <p className="mt-1.5 max-w-3xl text-sm text-[var(--text-secondary)]">
          프로젝트를 고르면 <b className="text-[var(--text-primary)]">개략수지(base)</b> →{" "}
          <b className="text-[var(--text-primary)]">투자수익성 요약</b> →{" "}
          <b className="text-[var(--text-primary)]">리스크 시뮬</b> 순으로 한 화면에서 연속 진행합니다. 각
          단계는 앞 단계 결과를 이어받습니다.
        </p>
      </div>

      {/* ── ② 개략수지 base(진입점) — CTA 스크롤 대상 anchor(id) ── */}
      <WorkflowStep
        id="rough-scenario-base"
        step="STEP 1"
        en="ROUGH FEASIBILITY · BASE"
        kr="개략수지 (기준 산출)"
        desc="프로젝트를 선택하면 토지비(적정가)·국토부 공사비·Top1 실거래 분양수입·20% 개발마진과 월별 DCF를 자동 산출합니다. 이 결과가 아래 모든 단계의 기준(base)이 됩니다."
      />
      <RoughScenarioPanel projectId={projectId ?? undefined} />

      {hasProject ? (
        <>
          {/* ── ③ 투자수익성 요약 ── */}
          <WorkflowStep
            step="STEP 2"
            en="ROI · SSOT SUMMARY"
            kr="투자수익성 요약"
            desc="개략수지 결과(SSOT)를 읽어 순이익·수익률·ROI·자기자본수익률(ROE)·NPV·사업성 등급과 할루시네이션 검증·전문가 패널을 표시합니다."
          />
          <InvestmentFeasibilityClient />

          {/* ── ④ 리스크 시뮬(몬테카를로) — '목적 불명' 해소 캡션 ── */}
          <WorkflowStep
            step="STEP 3"
            en="RISK · MONTE CARLO"
            kr="리스크 시뮬레이션 (손실확률·민감도)"
            desc="위 실수지 base를 기준으로 몬테카를로 시뮬레이션을 돌려 손실확률(NPV<0)·하방리스크 분포·민감도(어떤 변수가 수익을 가장 흔드는지)를 산출합니다."
          />
          <InvestmentAnalyticsWorkspaceClient locale={safeLocale} projectId={projectId} />

          {/* ── 보조: 은행제출용 수동 세부조정(기본 접힘·자체 헤더) ── */}
          <WorkflowStep
            step="보조"
            en="MANUAL · BANK-READY DCF"
            kr="수동 세부조정 (선택)"
            desc="개략수지·리스크 분석으로 충분하지 않을 때만 쓰는 선택 도구입니다. 앞 단계 수지 결과를 이어받아 손으로 정밀 조정합니다(기본 접힘)."
          />
          <CashflowDcfPanel />
        </>
      ) : (
        // 무목업 게이트 — 프로젝트 미선택 시 가짜 기본값 대신 진입점(위 STEP 1)으로 유도.
        <div className="sa-di-block">
          <div className="sa-di-block__body">
            <p className="text-sm font-bold text-[var(--text-primary)]">
              먼저 프로젝트를 선택하세요.
            </p>
            <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">
              위 <b className="text-[var(--text-primary)]">개략수지 (기준 산출)</b>에서 프로젝트를 고르고
              &lsquo;개략수지 생성&rsquo;을 실행하면 투자수익성 요약 · 리스크 시뮬 · 수동 세부조정 단계가 여기에
              이어집니다.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
