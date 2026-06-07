import { isValidLocale, type Locale } from "@/i18n/config";
import { getDictionary } from "@/i18n/get-dictionary";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { NextStageCta } from "@/components/projects/NextStageCta";
import { FeasibilityEditorV2 } from "@/components/feasibility/FeasibilityEditorV2";
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
  const runtimeMode =
    process.env.NEXT_PUBLIC_USE_MOCKS === "false"
      ? dictionary.workspace.modeLive
      : dictionary.workspace.modeMock;
  const t = dictionary.modulePlaceholders["feasibility"];

  return (
    <div className="flex flex-col gap-12 min-h-screen pb-20 transition-colors duration-500">
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

      {/* ② 위젯 */}
      <div className="animate-premium-fade" style={{ animationDelay: "200ms" }}>
        <FeasibilityEditorV2 projectId={id} />
      </div>

      {/* ③ 다음 단계 CTA */}
      <NextStageCta locale={locale} currentStage="feasibility" />
    </div>
  );
}
