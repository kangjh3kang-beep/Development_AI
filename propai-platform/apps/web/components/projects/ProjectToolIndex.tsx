"use client";

/**
 * 프로젝트 도구 인덱스 — 라이프사이클 진행레일(11단계)에 없는 독립 도구(고아 라우트)를
 * 접이식으로 surface한다. IA 원칙(docs/design/navigation-ia-system.md §5.5: "프로젝트 상세 탭 등
 * 후속 화면은 동일 NavNode 개념을 재사용")에 따라 nav-config의 순수 활성판정 헬퍼를 재사용한다.
 *
 *  - 결정론 활성판정: nav-config.isHrefActive(하위경로 포함) 재사용 — DOM/네트워크 무관.
 *  - 기본 접힘(IA §6: L2 그룹 기본 접힘) — 활성 도구가 있으면 자동 펼침.
 *  - 명시 토글만 localStorage('propai-project-tools-expanded')에 기억(SidebarNav와 동일 규약).
 *  - 진행레일·STAGE_GROUPS는 무수정. 본 컴포넌트만 신설(additive).
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { StageIcon } from "@/components/common/StageIcon";
import { isHrefActive } from "@/components/layout/nav-config";
import { PROJECT_TOOLS, projectToolHref } from "@/lib/lifecycle-stages";

const STORAGE_KEY = "propai-project-tools-expanded";

function ChevronDown({ open }: { open: boolean }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`shrink-0 transition-transform duration-200 ${open ? "" : "-rotate-90"}`}
      aria-hidden="true"
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

export function ProjectToolIndex({ locale, projectId }: { locale: string; projectId: string }) {
  const pathname = usePathname();

  const tools = useMemo(
    () => PROJECT_TOOLS.map((t) => ({ ...t, href: projectToolHref(locale, projectId, t.route) })),
    [locale, projectId],
  );
  const anyActive = useMemo(
    () => tools.some((t) => isHrefActive(t.href, pathname)),
    [tools, pathname],
  );

  // 명시 토글만 저장 — 미설정 시 활성 도구 유무로 기본 펼침 결정(IA §6).
  const [override, setOverride] = useState<boolean | null>(null);
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      // 마운트 시 펼침상태 1회 하이드레이트(SSR 안전·기본동작 보존). SidebarNav/AIAssistant와 동일 규약.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (raw !== null) setOverride(raw === "1");
    } catch {
      /* localStorage 불가 환경 — 기본 동작 유지 */
    }
  }, []);

  const open = override ?? anyActive;

  const toggle = useCallback(() => {
    setOverride((prev) => {
      const next = !(prev ?? anyActive);
      try {
        window.localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
      } catch {
        /* 무시 */
      }
      return next;
    });
  }, [anyActive]);

  return (
    <section className="px-1" aria-label="프로젝트 도구">
      <button
        type="button"
        aria-expanded={open}
        onClick={toggle}
        className={`flex items-center gap-1.5 pb-1.5 text-[11px] font-bold tracking-normal transition-colors ${
          anyActive
            ? "text-[var(--accent-strong)]"
            : "text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
        }`}
      >
        <ChevronDown open={open} />
        프로젝트 도구
      </button>
      {open && (
        <nav className="flex flex-wrap gap-1.5">
          {tools.map((t) => {
            const active = isHrefActive(t.href, pathname);
            return (
              <Link
                key={t.route}
                href={t.href}
                aria-current={active ? "page" : undefined}
                className={`group inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-bold transition-colors ${
                  active
                    ? "border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] text-[var(--accent-strong)]"
                    : "border-[var(--line-strong)] bg-[var(--surface-soft)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                }`}
              >
                <span
                  className={`shrink-0 ${
                    active
                      ? "text-[var(--accent-strong)]"
                      : "text-[var(--text-hint)] group-hover:text-[var(--text-primary)]"
                  }`}
                >
                  <StageIcon id={t.icon} size={15} />
                </span>
                <span className="truncate">{t.label}</span>
              </Link>
            );
          })}
        </nav>
      )}
    </section>
  );
}
