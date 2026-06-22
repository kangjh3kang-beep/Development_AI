"use client";

/**
 * 설계 AI 페이지 — 스펙 §2 단절 해소판.
 *
 * 변경 전: ModulePlaceholder → DesignStudio(바로 렌더) → NextStageCta
 * 변경 후: ModulePlaceholder → 설계 검증 패널 → [설계 스튜디오 열기] CTA
 *          → DesignStudio(게이트 통과 후) → NextStageCta
 *
 * 설계 스튜디오 게이트: WebGL+HDR Environment+무한 autoRotate가 기본탭 자동마운트되면
 * 메인스레드를 점유해 프로젝트 진입이 멈추는 버그(b5f216e 참고)가 재발한다.
 * 사용자가 명시적으로 "열기"를 누를 때만 DesignStudio를 마운트한다.
 *
 * 설계 검증 패널: AnalysisVerificationPanel(nodeId="design")으로
 * 기존 설계 분석 결과를 VerificationBadge+ExpertPanelCard(design노드·expertPanel=false)로
 * 표시한다. design 노드는 expertPanel=false이므로 ExpertPanelCard는 렌더되지 않는다.
 * verify.verifyAnalysis=true이므로 VerificationBadge는 designData가 있을 때 자동 활성화.
 */

import { useState } from "react";
import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import { Construction } from "lucide-react";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { NextStageCta } from "@/components/projects/NextStageCta";
import { DesignStudio } from "@/components/design/DesignStudio";
import { AnalysisVerificationPanel } from "@/components/common/AnalysisVerificationPanel";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { isValidLocale, type Locale } from "@/i18n/config";
import { useDictionary } from "@/hooks/use-dictionary";

export default function DesignPage() {
  const { locale, id } = useParams() as { locale: string; id: string };
  const { dictionary, isLoading } = useDictionary(locale as Locale);

  // 설계 스튜디오 게이트 — 명시적 "열기" 전까지 마운트 지연(WebGL 점유 방지)
  const [studioOpen, setStudioOpen] = useState(false);

  // 검증 패널용: designData 읽기 소비(store 미기록·계정격리 미접촉)
  const designData = useProjectContextStore((s) => s.designData);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);

  if (isLoading || !dictionary) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <div className="h-12 w-12 animate-spin rounded-full border-4 border-[var(--accent-strong)] border-t-transparent" />
      </div>
    );
  }

  if (!isValidLocale(locale)) {
    return null;
  }

  const runtimeMode =
    process.env.NEXT_PUBLIC_USE_MOCKS === "false"
      ? dictionary.workspace.modeLive
      : dictionary.workspace.modeMock;

  const t = dictionary.modulePlaceholders["design"];

  // 검증 패널 context — designData가 있을 때만 JSON 직렬화 가능 핵심값 전달
  const designContext: Record<string, unknown> | null = designData
    ? {
        totalGfaSqm: designData.totalGfaSqm,
        floorCount: designData.floorCount,
        bcr: designData.bcr,
        far: designData.far,
        buildingType: designData.buildingType,
        address: siteAnalysis?.address,
      }
    : null;

  return (
    <div className="flex flex-col gap-12 pb-20">
      {/* ① 컨텍스트 헤더 */}
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <ModulePlaceholder
          eyebrow={t.eyebrow}
          title={t.title}
          description={t.description}
          statusLabel={runtimeMode}
          localeLabel={locale}
          items={t.items}
        />
      </motion.div>

      {/* ② 설계 검증 패널 — 설계 AI 결과 검증 (design 노드 · expertPanel=false · verify=true) */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.12 }}
      >
        <AnalysisVerificationPanel
          nodeId="design"
          analysisType="design"
          address={siteAnalysis?.address ?? undefined}
          context={designContext}
        />
      </motion.div>

      {/* ③ 설계 스튜디오 — 명시적 "열기" CTA 게이트(WebGL 지연 마운트) */}
      {studioOpen ? (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
        >
          <DesignStudio projectId={id} />
        </motion.div>
      ) : (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="flex flex-col items-center justify-center gap-4 rounded-2xl border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] py-12"
        >
          <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-[var(--accent-strong)]">
            <Construction className="size-7" aria-hidden />
          </span>
          <div className="text-center">
            <p className="text-base font-bold text-[var(--text-primary)]">설계 스튜디오</p>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              2D CAD 편집, 3D BIM 뷰어, AI 건축개요 산출, 법규 검증을 실행합니다.
            </p>
            <p className="mt-0.5 text-xs text-[var(--text-hint)]">
              고사양 3D 뷰어가 포함돼 있어 버튼을 누를 때만 로드됩니다.
            </p>
          </div>
          <button
            onClick={() => setStudioOpen(true)}
            className="rounded-xl bg-[var(--accent-strong)] px-6 py-2.5 text-sm font-black text-white hover:opacity-90 transition-opacity"
          >
            설계 스튜디오 열기
          </button>
        </motion.div>
      )}

      {/* ④ 다음 단계 CTA */}
      <NextStageCta locale={locale} currentStage="design" />
    </div>
  );
}
