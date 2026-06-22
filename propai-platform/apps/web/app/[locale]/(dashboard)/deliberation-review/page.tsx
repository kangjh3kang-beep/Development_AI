import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";
import { DeliberationConsole } from "@/components/deliberation/DeliberationConsole";
import { DeliberationResultPanel } from "@/components/analysis/DeliberationResultPanel";

/**
 * AI 심의분석 엔진 — 차세대 비전 페이지.
 *
 * 멀티모달 AI(VLLM) 기반 설계도서 자동해석 → 차세대 심의분석 엔진 비전을 타이틀로 분산배치한다.
 * 엔진 코어(심의분석 11계층)는 별도 백엔드(propai-review)로 구현 완료 · 플랫폼 통합 예정(정직 표기).
 */
export default async function DeliberationReviewPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!isValidLocale(locale)) return null;
  const dict = await getDictionary(locale as Locale);
  const v = dict.vision;
  const pillars = [v.pillars.multimodal, v.pillars.deterministic, v.pillars.frontier];

  return (
    <div className="grid gap-6 pb-20">
      {/* 비전 히어로 — 타이틀 분산배치(badge → title → lead) */}
      <section className="cc-panel cc-bracketed relative overflow-hidden rounded-[var(--radius-2xl)] p-8 shadow-[var(--shadow-md)]">
        <i className="cc-bracket cc-bracket--tl" />
        <i className="cc-bracket cc-bracket--tr" />
        <i className="cc-bracket cc-bracket--bl" />
        <i className="cc-bracket cc-bracket--br" />
        <div className="cc-grid-bg opacity-40" />
        <div className="relative z-10 flex items-center justify-between gap-3">
          <span className="cc-meta text-[var(--accent-strong)]">{v.badge}</span>
          <span className="cc-label rounded-full border border-[var(--line)] px-2.5 py-0.5 text-[10px] text-[var(--text-tertiary)]">
            {v.engineNote}
          </span>
        </div>
        <h1 className="relative z-10 mt-4 max-w-4xl text-2xl font-black leading-tight text-[var(--text-primary)] sm:text-3xl">
          {v.title}
        </h1>
        <p className="relative z-10 mt-3 max-w-3xl text-sm text-[var(--text-secondary)]">{v.lead}</p>
        <p className="relative z-10 mt-1 text-xs font-semibold text-[var(--accent-strong)]">
          {v.areas.engine}
        </p>
      </section>

      {/* 비전 3주 — 타이틀 분산배치(pillar별 제목) */}
      <section className="grid gap-4 md:grid-cols-3">
        {pillars.map((p, i) => (
          <article
            key={i}
            className="cc-panel cc-bracketed relative overflow-hidden rounded-[var(--radius-2xl)] p-5"
          >
            <i className="cc-bracket cc-bracket--tl" />
            <i className="cc-bracket cc-bracket--tr" />
            <i className="cc-bracket cc-bracket--bl" />
            <i className="cc-bracket cc-bracket--br" />
            <span className="cc-label text-[var(--text-tertiary)]">{`0${i + 1}`}</span>
            <h2 className="mt-2 text-base font-black text-[var(--text-primary)]">{p.title}</h2>
            <p className="mt-1.5 text-xs leading-relaxed text-[var(--text-secondary)]">{p.desc}</p>
          </article>
        ))}
      </section>

      {/* 엔진 구성 — 심의분석 11계층(백엔드 구현 완료, 통합 예정) */}
      <section className="cc-panel cc-bracketed relative overflow-hidden rounded-[var(--radius-2xl)] p-6">
        <i className="cc-bracket cc-bracket--tl" />
        <i className="cc-bracket cc-bracket--tr" />
        <i className="cc-bracket cc-bracket--bl" />
        <i className="cc-bracket cc-bracket--br" />
        <div className="relative z-10 flex items-center justify-between gap-3">
          <h2 className="text-lg font-black text-[var(--text-primary)]">{v.engineTitle}</h2>
          <span className="cc-meta text-[var(--text-tertiary)]">PREVIEW</span>
        </div>
        <ol className="relative z-10 mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {v.layers.map((layer, i) => (
            <li
              key={i}
              className="flex items-start gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-3 py-2 text-xs text-[var(--text-secondary)]"
            >
              <span className="font-black text-[var(--accent-strong)]">{`L${i + 1}`}</span>
              <span>{layer}</span>
            </li>
          ))}
        </ol>
        <p className="relative z-10 mt-3 text-[11px] text-[var(--text-tertiary)]">
          {v.engineNote}
        </p>
      </section>

      {/* 심의분석 결과(BFF) — 플랫폼 인증 경유 /api/v1/deliberation/analyze 풀통합(graceful degrade) */}
      <DeliberationResultPanel />

      {/* 라이브 콘솔 — 심의분석 엔진(propai-review) /analyze 직접배선(개발자용 원시입력) */}
      <DeliberationConsole />
    </div>
  );
}
