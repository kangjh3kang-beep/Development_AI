import { OperationsIntelligenceWorkspaceClient } from "@/components/analytics/OperationsIntelligenceWorkspaceClient";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { AdvancedDrawer } from "@/components/common/AdvancedDrawer";
import { ParkingLogView } from "@/components/safety/ParkingLogView";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";
import { runtimeMode } from "@/lib/runtime-mode";

// ★P2-3(배선설계도 G7 최우선): ParkingLogView는 /parking/dashboard(라이브 API)를
// 실호출하는 유일한 완성 오펀 컴포넌트다(2026-07-11 트리아지). 프로젝트 스코프 없이
// 테넌트 단위로 동작하므로(백엔드 parking.py도 project_id 불요) 별도 프로젝트 게이트
// 없이 그대로 마운트한다. 접힘 섹션(기본 닫힘)으로 additive 마운트 — 값/흐름 불변.
const PARKING_SECTION_LABEL: Record<Locale, string> = {
  ko: "주차 관제 (실시간)",
  en: "Parking Control (Live)",
  "zh-CN": "停车管理（实时）",
};

type MaintenancePageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function MaintenancePage({
  params,
}: MaintenancePageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  const dictionary = await getDictionary(locale as Locale);
  const runtimeModeLabel =
    runtimeMode() === "live"
      ? dictionary.workspace.modeLive
      : dictionary.workspace.modeMock;

  return (
    <div className="grid grid-cols-1 gap-6 min-w-0">
            <ModulePlaceholder
        eyebrow={dictionary.modulePlaceholders["maintenance"].eyebrow}
        title={dictionary.modulePlaceholders["maintenance"].title}
        description={dictionary.modulePlaceholders["maintenance"].description}
        statusLabel={runtimeModeLabel}
        localeLabel={locale}
        items={dictionary.modulePlaceholders["maintenance"].items}
      />
      <OperationsIntelligenceWorkspaceClient
        locale={locale as Locale}
        sections={["maintenance"]}
        showHero={false}
      />
      <AdvancedDrawer label={PARKING_SECTION_LABEL[locale as Locale] ?? PARKING_SECTION_LABEL.ko}>
        <ParkingLogView />
      </AdvancedDrawer>
    </div>
  );
}
