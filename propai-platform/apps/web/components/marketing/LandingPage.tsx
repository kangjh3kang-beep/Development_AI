import "./marketing.css";
import { MarketingNav } from "./MarketingNav";
import { HeroSection } from "./HeroSection";
import { ModulesSection } from "./ModulesSection";
import { WhySection } from "./WhySection";
import { ReportPanelSection } from "./ReportPanelSection";
import { CtaFooter } from "./CtaFooter";

/**
 * PropAI 마케팅 랜딩(Part A · Warm Amber).
 * 미인증 방문자에게 노출된다. 항상 라이트(Part A) — 앱 다크/라이트 테마와 무관.
 * 최상위 `.mkt-root` 스코프 안에서만 `--mkt-*` 토큰을 사용한다.
 */
export function LandingPage({ locale }: { locale: string }) {
  return (
    <div className="mkt-root" data-mkt-landing="">
      <MarketingNav locale={locale} />
      <HeroSection locale={locale} />
      <ModulesSection />
      <WhySection />
      <ReportPanelSection locale={locale} />
      <CtaFooter locale={locale} />
    </div>
  );
}
