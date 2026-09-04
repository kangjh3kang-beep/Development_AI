import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";
import { buildPrimaryNav } from "@/components/layout/nav-config";
import { DashboardChromeGate } from "@/components/layout/DashboardChromeGate";
import { runtimeMode } from "@/lib/runtime-mode";
type DashboardLayoutProps = Readonly<{
  children: React.ReactNode;
  params: Promise<{
    locale: string;
  }>;
}>;

export default async function DashboardLayout({
  children,
  params,
}: DashboardLayoutProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return children;
  }

  const dictionary = await getDictionary(locale as Locale);
  const runtimeModeLabel =
    runtimeMode() === "live"
      ? dictionary.workspace.modeLive
      : dictionary.workspace.modeMock;

  // 워크스페이스 내비게이션 단일 출처(SSOT) — IA 원칙은 components/layout/nav-config.tsx +
  // docs/design/navigation-ia-system.md. 상단 요약형(L1 섹션 → 우선순위 L2/L3 링크)으로 구동한다.
  const sections = buildPrimaryNav(locale);

  // layout은 서버로 유지(dictionary·nav 데이터만 서버에서 조립)하고, 크롬 표시 여부는
  // 클라이언트 게이트(DashboardChromeGate)에 위임한다 — "미인증 + 홈 라우트"일 때만
  // 앱 크롬을 숨기고 children(랜딩)을 풀블리드로 렌더한다(그 외는 회귀 0로 크롬 유지).
  return (
    <DashboardChromeGate
      locale={locale as Locale}
      localeLabel={dictionary.nav.locale}
      runtimeModeLabel={runtimeModeLabel}
      sections={sections}
    >
      {children}
    </DashboardChromeGate>
  );
}
