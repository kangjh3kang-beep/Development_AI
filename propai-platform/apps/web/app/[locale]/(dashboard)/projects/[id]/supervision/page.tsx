"use client";

/**
 * 감리·공정 모니터링 — 준비 중(예정 기능). 무목업 원칙:
 *   이전 영어 정적 목업(Supervision Hub·Project Alpha: Block C·Material 아이콘 텍스트노출)을 제거하고,
 *   실제 감리/공정 데이터가 배선되기 전까지 한국어 정직 안내 + 실존 기능 링크로 대체한다.
 */

import { useParams } from "next/navigation";
import Link from "next/link";
import { ClipboardCheck, Hammer, Layers, FileText, ArrowRight, Clock } from "lucide-react";

export default function SupervisionPage() {
  const params = useParams();
  const locale = (params?.locale as string) || "ko";
  const id = params?.id as string;
  const proj = (p: string) => `/${locale}/projects/${id}/${p}`;

  const links: { to: string; label: string; desc: string; icon: typeof Layers }[] = [
    { to: proj("cost"), label: "BIM 적산·공사비", desc: "부위별 물량·공사비(5D) 산출", icon: Hammer },
    { to: proj("design"), label: "설계 스튜디오·CAD/BIM", desc: "도면·모델·법규 검토", icon: Layers },
    { to: proj("report"), label: "통합 보고서", desc: "사업 종합 보고서·PDF", icon: FileText },
  ];

  return (
    <div className="mx-auto max-w-3xl py-8">
      <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-6 sm:p-8">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-[var(--accent-soft)] text-[var(--accent-strong)]">
            <ClipboardCheck className="size-5" aria-hidden />
          </span>
          <div>
            <p className="inline-flex items-center gap-1.5 text-xl font-black text-[var(--text-primary)]">
              감리·공정 모니터링
              <span className="inline-flex items-center gap-1 rounded-md bg-[var(--surface-muted)] px-1.5 py-0.5 text-[10px] font-bold text-[var(--text-hint)]">
                <Clock className="size-3" aria-hidden /> 준비 중
              </span>
            </p>
            <p className="mt-0.5 text-sm text-[var(--text-secondary)]">현장 감리·공정 진척·품질/안전 점검을 실시간으로 모니터링하는 허브</p>
          </div>
        </div>

        <p className="mt-5 rounded-xl border border-[var(--line)] bg-[var(--surface)] p-4 text-sm leading-relaxed text-[var(--text-secondary)]">
          이 화면은 실제 현장 감리·공정 데이터가 연동되기 전이라 <b className="text-[var(--text-primary)]">예시(가짜) 데이터를 표시하지 않습니다</b>.
          시공 단계에서 바로 활용할 수 있는 적산·설계·보고 기능은 아래에서 이용하세요.
        </p>

        <div className="mt-4 grid gap-2">
          {links.map((l) => (
            <Link key={l.to} href={l.to}
              className="group flex items-center gap-3 rounded-xl border border-[var(--line)] bg-[var(--surface)] p-3 transition hover:border-[var(--accent-strong)]">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-soft)] text-[var(--accent-strong)]">
                <l.icon className="size-4" aria-hidden />
              </span>
              <span className="flex-1">
                <span className="block text-sm font-bold text-[var(--text-primary)]">{l.label}</span>
                <span className="block text-xs text-[var(--text-hint)]">{l.desc}</span>
              </span>
              <ArrowRight className="size-4 text-[var(--text-hint)] transition group-hover:text-[var(--accent-strong)]" aria-hidden />
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
