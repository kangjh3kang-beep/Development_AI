"use client";

/**
 * AI 실행 커맨드 콘솔 — 준비 중(예정 기능). 무목업 원칙:
 *   이전 영어 정적 목업(Project Alpha Execution·가짜 명령 CMD-001…·Material 아이콘 텍스트노출)을
 *   제거하고, 기능이 실제 배선되기 전까지 한국어 정직 안내 + 실존 기능 링크로 대체한다.
 *   (가짜 데이터를 실데이터처럼 보이게 하지 않는다 = CLAUDE.md 무목업.)
 */

import { useParams } from "next/navigation";
import Link from "next/link";
import { Bot, Sparkles, FileText, Hammer, ArrowRight, Clock } from "lucide-react";

export default function AgentControlPage() {
  const params = useParams();
  const locale = (params?.locale as string) || "ko";
  const id = params?.id as string;
  const proj = (p: string) => `/${locale}/projects/${id}/${p}`;

  const links: { to: string; label: string; desc: string; icon: typeof Bot }[] = [
    { to: proj("canvas"), label: "지도 단일창(종합 분석)", desc: "토지·규제·개발방식·수지를 한 화면에서 검토", icon: Sparkles },
    { to: proj("cost"), label: "BIM 적산·공사비", desc: "부위별 물량·공사비 산출", icon: Hammer },
    { to: proj("report"), label: "통합 보고서", desc: "은행제출용 통합 보고서·PDF", icon: FileText },
  ];

  return (
    <div className="mx-auto max-w-3xl py-8">
      <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-6 sm:p-8">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-[var(--accent-soft)] text-[var(--accent-strong)]">
            <Bot className="size-5" aria-hidden />
          </span>
          <div>
            <p className="inline-flex items-center gap-1.5 text-xl font-black text-[var(--text-primary)]">
              AI 실행 커맨드 콘솔
              <span className="inline-flex items-center gap-1 rounded-md bg-[var(--surface-muted)] px-1.5 py-0.5 text-[10px] font-bold text-[var(--text-hint)]">
                <Clock className="size-3" aria-hidden /> 준비 중
              </span>
            </p>
            <p className="mt-0.5 text-sm text-[var(--text-secondary)]">설계변경·발주·인력배치·공정조정 등 실행 단계 명령을 AI가 제안·집행하는 콘솔</p>
          </div>
        </div>

        <p className="mt-5 rounded-xl border border-[var(--line)] bg-[var(--surface)] p-4 text-sm leading-relaxed text-[var(--text-secondary)]">
          이 콘솔은 실제 명령·집행 데이터가 배선되기 전이라 <b className="text-[var(--text-primary)]">예시(가짜) 데이터를 표시하지 않습니다</b>.
          현재 사용 가능한 분석·산출 기능은 아래에서 바로 이용하세요. AI 비서(우하단)는 지금도 사용할 수 있습니다.
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
