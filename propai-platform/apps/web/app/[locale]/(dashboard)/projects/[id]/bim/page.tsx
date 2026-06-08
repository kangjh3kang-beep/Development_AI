import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { ProjectBimWorkspaceClient } from "@/components/projects/ProjectBimWorkspaceClient";
import { CadBimIntegrationPanel } from "@/components/design/CadBimIntegrationPanel";
import { NextStageCta } from "@/components/projects/NextStageCta";
import { isValidLocale, type Locale } from "@/i18n/config";
import { getDictionary } from "@/i18n/get-dictionary";

type BimPageProps = {
  params: Promise<{
    locale: string;
    id: string;
  }>;
};

export default async function BimPage({ params }: BimPageProps) {
  const { locale, id } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  const dictionary = await getDictionary(locale as Locale);
  const runtimeMode =
    process.env.NEXT_PUBLIC_USE_MOCKS === "false"
      ? dictionary.workspace.modeLive
      : dictionary.workspace.modeMock;

  return (
    <div className="grid gap-6">
            <ModulePlaceholder
        eyebrow={dictionary.modulePlaceholders["bim"].eyebrow}
        title={dictionary.modulePlaceholders["bim"].title}
        description={dictionary.modulePlaceholders["bim"].description}
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={dictionary.modulePlaceholders["bim"].items}
      />
      {/* 진짜 동작하는 3D BIM 뷰어(IFC→glTF 실모델) — 가짜 CSS 3D 대신 실제 절차생성 모델.
          기본 진입은 2D, 사용자가 3D BIM 탭으로 전환 시에만 캔버스 마운트(진입멈춤 방지). */}
      <CadBimIntegrationPanel projectId={id} dictionary={{}} />
      {/* BIM 물량 산출(수치) 워크스페이스 — 3D 뷰와 함께 표시 */}
      <ProjectBimWorkspaceClient locale={locale as Locale} projectId={id} />
      <NextStageCta locale={locale} currentStage="bim" />
    </div>
  );
}
