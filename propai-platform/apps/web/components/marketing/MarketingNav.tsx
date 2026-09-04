import Link from "next/link";
import { ArrowRight, Layers3 } from "lucide-react";

/**
 * 랜딩 상단 내비게이션(Part A).
 *  • 좌: 32px 잉크 사각 + 심볼 + "사통팔땅" 워드마크.
 *  • 우: 로그인 텍스트 링크 + CTA pill "무료로 시작 →"(잉크 → hover 앰버).
 */
export function MarketingNav({ locale }: { locale: string }) {
  return (
    <header className="mkt-section--paper" style={{ paddingBlock: 20 }}>
      <nav className="mkt-container flex items-center justify-between gap-4">
        <Link
          href={`/${locale}`}
          className="flex items-center gap-3"
          style={{ textDecoration: "none" }}
          aria-label="사통팔땅 홈"
        >
          <span
            aria-hidden="true"
            className="inline-flex items-center justify-center"
            style={{
              height: 32,
              width: 32,
              borderRadius: 9,
              background: "var(--mkt-ink)",
              color: "var(--mkt-accent)",
            }}
          >
            <Layers3 className="h-[18px] w-[18px]" strokeWidth={1.5} />
          </span>
          <span
            style={{
              fontFamily: "var(--mkt-font-sans)",
              fontWeight: 600,
              fontSize: 19,
              letterSpacing: "-0.01em",
              color: "var(--mkt-ink)",
            }}
          >
            사통팔땅
          </span>
        </Link>

        <div className="flex items-center gap-4 sm:gap-6">
          <Link
            href={`/${locale}/login`}
            style={{
              fontSize: 15,
              fontWeight: 500,
              color: "var(--mkt-ink-soft)",
              textDecoration: "none",
            }}
          >
            로그인
          </Link>
          <Link
            href={`/${locale}/login`}
            className="mkt-pill-btn"
            style={{ padding: "11px 22px", fontSize: 15 }}
          >
            무료로 시작
            <ArrowRight aria-hidden="true" className="mkt-arrow h-4 w-4" />
          </Link>
        </div>
      </nav>
    </header>
  );
}
