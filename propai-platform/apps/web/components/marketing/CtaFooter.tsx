import Link from "next/link";
import { ArrowRight, Layers3 } from "lucide-react";

/**
 * 최종 CTA + 푸터 — 다크 섹션.
 * H2 대형 + 앰버 pill CTA + 브랜드/링크/저작권.
 */
const footerLinks = [
  { label: "기능", href: (l: string) => `/${l}/guide` },
  { label: "요금", href: (l: string) => `/${l}/settings` },
  { label: "문의", href: () => "tel:1666-0916" },
] as const;

export function CtaFooter({ locale }: { locale: string }) {
  return (
    <section className="mkt-section--ink">
      <div className="mkt-container" style={{ paddingBlock: "clamp(72px, 10vw, 128px)" }}>
        <div className="flex flex-col gap-10">
          <h2
            style={{
              fontFamily: "var(--mkt-font-sans)",
              fontWeight: 600,
              fontSize: "clamp(40px, 7vw, 84px)",
              lineHeight: 1.0,
              letterSpacing: "-0.03em",
              color: "var(--mkt-white)",
              maxWidth: "18ch",
              textWrap: "balance",
            }}
          >
            다음 프로젝트,
            <br />
            주소만 입력하세요.
          </h2>
          <div>
            <Link href={`/${locale}/precheck`} className="mkt-pill-btn mkt-pill-btn--accent">
              지금 필지 분석하기
              <ArrowRight aria-hidden="true" className="mkt-arrow h-[18px] w-[18px]" />
            </Link>
          </div>
        </div>

        {/* 푸터 */}
        <div
          className="mt-24 flex flex-col gap-6 md:flex-row md:items-center md:justify-between"
          style={{ borderTop: "1px solid rgba(255,255,255,0.14)", paddingTop: 28 }}
        >
          <div className="flex items-center gap-3">
            <span
              aria-hidden="true"
              className="inline-flex items-center justify-center"
              style={{ height: 28, width: 28, borderRadius: 8, background: "var(--mkt-white)", color: "var(--mkt-ink)" }}
            >
              <Layers3 className="h-4 w-4" strokeWidth={1.5} />
            </span>
            <span style={{ fontFamily: "var(--mkt-font-sans)", fontWeight: 600, fontSize: 16, color: "var(--mkt-white)" }}>
              사통팔땅
            </span>
          </div>

          <nav className="flex items-center gap-6">
            {footerLinks.map((link) => (
              <Link
                key={link.label}
                href={link.href(locale)}
                style={{ fontSize: 14, color: "rgba(255,255,255,0.62)", textDecoration: "none" }}
              >
                {link.label}
              </Link>
            ))}
          </nav>

          <p style={{ fontSize: 13, color: "rgba(255,255,255,0.45)" }}>© 2026 사통팔땅 · PropAI</p>
        </div>
      </div>
    </section>
  );
}
