import { isValidLocale, type Locale } from "@/i18n/config";
import { isMockMode } from "@/lib/runtime-mode";
import { getDictionary } from "@/i18n/get-dictionary";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { ModuleCommandStrip } from "@/components/layout/ModuleCommandStrip";
import { NextStageCta } from "@/components/projects/NextStageCta";
import { FeasibilityEditorV2 } from "@/components/feasibility/FeasibilityEditorV2";
import { UnitMixOptimizerPanel } from "@/components/feasibility/UnitMixOptimizerPanel";
import { RoughScenarioPanel } from "@/components/feasibility/RoughScenarioPanel";
import { TrustBadge } from "@/components/common/TrustBadge";

type Props = {
  params: Promise<{ locale: string; id: string }>;
};

export default async function FeasibilityPage({ params }: Props) {
  const { locale, id } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  const dictionary = await getDictionary(locale as Locale);
  const runtimeMode = isMockMode()
    ? dictionary.workspace.modeMock
    : dictionary.workspace.modeLive;
  const t = dictionary.modulePlaceholders["feasibility"];

  return (
    <div className="flex flex-col gap-12 min-h-screen pb-20 transition-colors duration-500">
      {/* ⓪ 커맨드센터 HUD 스트립 — 모듈 식별·LIVE 상태(시각 전용, 데이터 무관) */}
      <ModuleCommandStrip label="FEASIBILITY · 사업성 분석" meta={runtimeMode} />

      {/* ① 컨텍스트 헤더 — 3구역 표준(ModulePlaceholder) */}
      <ModulePlaceholder
        eyebrow={t.eyebrow}
        title={t.title}
        description={t.description}
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={t.items}
      />

      {/* 신뢰도 배지(데이터 출처/검증) */}
      <div>
        <TrustBadge />
      </div>

      {/* ①~⑧ 개략수지 워크플로우 — 프로젝트 선택/수정 → 기본 개략수지 → 2차 실데이터 수정 → 월별 DCF */}
      <div className="animate-premium-fade" style={{ animationDelay: "150ms" }}>
        <RoughScenarioPanel projectId={id} />
      </div>

      {/* ② 위젯 */}
      <div className="animate-premium-fade" style={{ animationDelay: "200ms" }}>
        <FeasibilityEditorV2 projectId={id} />
      </div>

      {/* ②-b 유닛믹스 최적화(SLSQP) — 서버 최적화기로 수익 극대화 평형배분(그동안 미배선 orphan 해소) */}
      <div className="animate-premium-fade" style={{ animationDelay: "300ms" }}>
        <UnitMixOptimizerPanel />
      </div>

      {/* ③ 다음 단계 CTA */}
      <NextStageCta locale={locale} currentStage="feasibility" />
    </div>
  );
}
