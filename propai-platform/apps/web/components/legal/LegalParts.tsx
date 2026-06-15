/**
 * 법적 문서(개인정보처리방침·이용약관) 공용 표현 컴포넌트.
 * 디자인 토큰 기반 가독성 요소만 제공(로직 없음). 서버 컴포넌트.
 */
import type { ReactNode } from "react";

export function DocHeader({ title, effectiveDate, intro }: { title: string; effectiveDate: ReactNode; intro?: ReactNode }) {
  return (
    <div className="mb-8">
      <h1 className="text-2xl font-black tracking-tight text-[var(--text-primary)] sm:text-3xl">{title}</h1>
      <p className="mt-2 flex items-center gap-1 text-xs text-[var(--text-tertiary)]">시행일: {effectiveDate}</p>
      {intro && <div className="mt-4 text-sm leading-relaxed text-[var(--text-secondary)]">{intro}</div>}
    </div>
  );
}

export function Article({ no, title, children }: { no: number | string; title: string; children: ReactNode }) {
  return (
    <section className="mb-7 scroll-mt-20" id={`article-${no}`}>
      <h2 className="mb-2 text-base font-bold text-[var(--text-primary)] sm:text-lg">
        제{no}조 ({title})
      </h2>
      <div className="space-y-2 text-sm leading-relaxed text-[var(--text-secondary)]">{children}</div>
    </section>
  );
}

/** 번호 없는 일반 섹션(목차·부칙 등) */
export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-7">
      <h2 className="mb-2 text-base font-bold text-[var(--text-primary)] sm:text-lg">{title}</h2>
      <div className="space-y-2 text-sm leading-relaxed text-[var(--text-secondary)]">{children}</div>
    </section>
  );
}

export function OL({ children }: { children: ReactNode }) {
  return <ol className="ml-4 list-decimal space-y-1.5 marker:text-[var(--text-tertiary)]">{children}</ol>;
}
export function UL({ children }: { children: ReactNode }) {
  return <ul className="ml-4 list-disc space-y-1.5 marker:text-[var(--text-tertiary)]">{children}</ul>;
}

/** 표 — 헤더 배열 + 행 배열(셀은 문자열/노드) */
export function Table({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <div className="my-3 overflow-x-auto rounded-xl border border-[var(--line)]">
      <table className="w-full text-xs sm:text-sm">
        <thead>
          <tr className="border-b border-[var(--line)] bg-[var(--surface-strong)] text-left text-[var(--text-secondary)]">
            {head.map((h, i) => (
              <th key={i} className="px-3 py-2 font-semibold">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-[var(--line)] align-top last:border-0">
              {r.map((c, j) => (
                <td key={j} className="px-3 py-2 text-[var(--text-primary)]">{c}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * 운영자(사업자) 입력 필요 표시 — 사업자등록번호·대표자·보호책임자 등 법적 식별정보는
 * 임의 생성(할루시네이션) 금지. 공개 전 관리자가 실제 값으로 반드시 채워야 함을 명시한다.
 */
export function Fill({ label }: { label: string }) {
  return (
    <span className="rounded bg-[var(--accent-soft)] px-1.5 py-0.5 font-mono text-[0.7em] font-bold text-[var(--accent-strong)]" title="공개 전 운영자 입력 필요">
      〔{label} 입력〕
    </span>
  );
}

/** 페이지 상단 운영자 안내 배너 — 미기입 식별정보 환기(공개 전 제거/대체). */
export function AdminFillBanner() {
  return (
    <div className="mb-6 rounded-xl border border-[var(--accent-strong)]/40 bg-[var(--accent-soft)] px-4 py-3 text-xs text-[var(--text-secondary)]">
      <b className="text-[var(--text-primary)]">운영자 안내</b> · 〔…입력〕으로 표시된 사업자 식별정보(상호·대표자·사업자등록번호·주소·
      개인정보 보호책임자·연락처·시행일)는 법적 효력을 위해 <b>공개 전 실제 값으로 반드시 입력</b>해야 합니다.
      값은 임의로 생성하지 않았습니다(부정확 고지 방지).
    </div>
  );
}
