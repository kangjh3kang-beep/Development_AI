"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { fetchAuthMeRole, fetchIsAdmin } from "@/lib/use-is-admin";
import {
  type NavNode,
  type NavSection,
  activeSectionIds,
  isHrefActive,
} from "./nav-config";

function flattenLinks(items: NavNode[]): NavNode[] {
  const out: NavNode[] = [];
  const walk = (node: NavNode) => {
    if (node.href) out.push(node);
    for (const child of node.children ?? []) walk(child);
  };
  for (const item of items) walk(item);
  return out;
}

export function WorkspaceNavBar({ sections }: { sections: NavSection[] }) {
  const pathname = usePathname();
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const [isAssetOps, setIsAssetOps] = useState<boolean | null>(null);
  const [openSectionId, setOpenSectionId] = useState<string | null>(null);
  const navRef = useRef<HTMLElement | null>(null);
  const closeTimerRef = useRef<number | null>(null);

  const clearCloseTimer = useCallback(() => {
    if (closeTimerRef.current) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }, []);

  const openSection = useCallback((sectionId: string) => {
    clearCloseTimer();
    setOpenSectionId(sectionId);
  }, [clearCloseTimer]);

  const closeSection = useCallback((sectionId: string) => {
    clearCloseTimer();
    setOpenSectionId((current) => (current === sectionId ? null : current));
  }, [clearCloseTimer]);

  const scheduleCloseSection = useCallback((sectionId: string) => {
    clearCloseTimer();
    closeTimerRef.current = window.setTimeout(() => {
      setOpenSectionId((current) => (current === sectionId ? null : current));
      closeTimerRef.current = null;
    }, 140);
  }, [clearCloseTimer]);

  useEffect(() => {
    let alive = true;
    Promise.all([
      fetchIsAdmin().catch(() => false),
      fetchAuthMeRole().catch(() => ""),
    ])
      .then(([admin, role]) => {
        if (!alive) return;
        setIsAdmin(admin);
        setIsAssetOps(
          admin || ["asset_manager", "operations", "운영관리자", "자산운용"].includes(role),
        );
      })
      .catch(() => {
        if (!alive) return;
        setIsAdmin(false);
        setIsAssetOps(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      clearCloseTimer();
      setOpenSectionId(null);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [pathname, clearCloseTimer]);

  useEffect(() => {
    return () => clearCloseTimer();
  }, [clearCloseTimer]);

  useEffect(() => {
    const closeOnOutside = (event: MouseEvent) => {
      if (!navRef.current?.contains(event.target as Node)) {
        clearCloseTimer();
        setOpenSectionId(null);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        clearCloseTimer();
        setOpenSectionId(null);
      }
    };
    document.addEventListener("mousedown", closeOnOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [clearCloseTimer]);

  const activeSections = useMemo(
    () => new Set(activeSectionIds(sections, pathname)),
    [sections, pathname],
  );

  const visibleSections = sections.filter(
    (section) =>
      (!section.adminOnly || isAdmin === true) &&
      (!section.assetOpsOnly || isAssetOps === true),
  );

  return (
    <nav
      ref={navRef}
      aria-label="Workspace navigation"
      className="hidden rounded-lg border border-[var(--line)] bg-[var(--surface-secondary)] px-3 py-2 shadow-[var(--shadow-sm)] lg:block"
    >
      <div className="flex flex-wrap items-center gap-1">
        {/* ★절단(slice) 금지: 과거 slice(0,5)가 '비관리자 5섹션' 시절 상수라, 역할 게이트
            (admin 등) 통과로 6섹션이 되는 관리자에게서 마지막 '관리' 섹션을 잘라내
            관리자 메뉴가 사라지던 근본원인. 역할 필터를 통과한 섹션은 전부 렌더한다
            (제목이 짧아 lg 이상 한 줄 수용, 초과 시 flex-wrap 줄바꿈). */}
        {visibleSections.map((section) => {
          // ★드롭다운은 섹션 전 항목을 노출한다(과거 slice(0,3) 3개 상한이 근본원인: 프로젝트 섹션의
          //   4번째+ 링크[투자·적산·ESG]가 잘려 사용자가 상단 네비에서 발견 불가 — 라이브 그라운드
          //   트루스로 확정). 항목이 많아 뷰포트를 넘겨도 팝오버 패널의 max-h+overflow-y-auto로
          //   스크롤 접근(아래 role=menu). 슬라이스 제거로 시장·획득 등 항목 많은 섹션도 전부 노출.
          const links = flattenLinks(section.items);
          const active = activeSections.has(section.id);
          const open = openSectionId === section.id;
          // 단일-리프 섹션(항목 1개 + 하위메뉴 없음, 예: 적산·시공비): 드롭다운 대신 섹션 버튼 자체를
          // 곧바로 그 링크로 렌더한다(빈 드롭다운 방지). 다항목 섹션은 기존 hover 드롭다운 유지(무회귀).
          const singleLeaf =
            section.items.length === 1 && !section.items[0].children?.length
              ? section.items[0]
              : null;
          if (singleLeaf?.href) {
            return (
              <div key={section.id} className="relative">
                <Link
                  href={singleLeaf.href}
                  prefetch={singleLeaf.prefetch}
                  className={`flex h-10 items-center gap-2 rounded-[var(--r-pill)] px-3 text-sm font-bold transition ${
                    active
                      ? "bg-[var(--accent-strong)] text-[var(--on-primary)]"
                      : "text-[var(--text-secondary)] hover:bg-[var(--surface-soft)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  <span>{section.title}</span>
                  {active && <span className="sr-only">현재 섹션</span>}
                </Link>
              </div>
            );
          }
          return (
            <div
              key={section.id}
              className="relative"
              onMouseEnter={() => openSection(section.id)}
              onMouseLeave={() => scheduleCloseSection(section.id)}
              onFocus={() => openSection(section.id)}
              onBlur={(event) => {
                const nextFocused = event.relatedTarget as Node | null;
                if (nextFocused && event.currentTarget.contains(nextFocused)) return;
                closeSection(section.id);
              }}
            >
              <button
                type="button"
                aria-expanded={open}
                aria-haspopup="menu"
                onClick={() => openSection(section.id)}
                className={`flex h-10 cursor-pointer list-none items-center gap-2 rounded-[var(--r-pill)] px-3 text-sm font-bold transition [&::-webkit-details-marker]:hidden ${
                  active
                    ? "bg-[var(--accent-strong)] text-[var(--on-primary)]"
                    : "text-[var(--text-secondary)] hover:bg-[var(--surface-soft)] hover:text-[var(--text-primary)]"
                }`}
              >
                <span>{section.title}</span>
                <ChevronDown
                  aria-hidden="true"
                  className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`}
                />
                {active && (
                  <span className="sr-only">현재 섹션</span>
                )}
              </button>
              {open && (
                <>
                  <div
                    aria-hidden="true"
                    data-testid={`workspace-nav-hover-bridge-${section.id}`}
                    className="absolute left-0 top-10 z-40 h-2 min-w-64"
                    onMouseEnter={() => openSection(section.id)}
                  />
                  <div
                    role="menu"
                    // ★max-h+overflow-y-auto: 항목 많은 섹션(프로젝트·시장·획득 등)의 팝오버가 화면
                    //   하단 근처에서 열려 뷰포트를 넘겨도 잘리지 않고 스크롤로 전 항목 접근 가능하게 한다.
                    //   Tailwind 임의값은 '_'(언더스코어) 공백 표기 필수 — calc(100dvh_-_5rem)로 써야
                    //   CSS `calc(100dvh - 5rem)`가 되고, 무공백 calc(100dvh-5rem)은 브라우저가 무시한다.
                    //   모든 섹션 드롭다운에 공통(공용 role=menu 패널) 적용.
                    className="absolute left-0 top-12 z-50 max-h-[calc(100dvh_-_5rem)] min-w-64 overflow-y-auto rounded-lg border border-[var(--line)] bg-[var(--surface-secondary)] p-2 shadow-[var(--shadow-md)]"
                    onMouseEnter={() => openSection(section.id)}
                  >
                    {links.map((link) => {
                      const linkActive = isHrefActive(link.href, pathname);
                      return (
                        <Link
                          key={link.id}
                          href={link.href!}
                          prefetch={link.prefetch}
                          onClick={() => {
                            clearCloseTimer();
                            setOpenSectionId(null);
                          }}
                          className={`flex items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm font-bold transition ${
                            linkActive
                              ? "bg-[var(--accent-soft)] text-[var(--accent-strong)]"
                              : "text-[var(--text-secondary)] hover:bg-[var(--surface-soft)] hover:text-[var(--text-primary)]"
                          }`}
                        >
                          <span>{link.label}</span>
                          {linkActive && <span className="h-2 w-2 rounded-full bg-[var(--accent-strong)]" />}
                        </Link>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          );
        })}
        <Link
          href={pathname?.replace(/\/$/, "") || "/"}
          aria-label="현재 워크스페이스 새로고침"
          className="ml-auto inline-flex h-10 items-center rounded-[var(--r-pill)] border border-[var(--line)] bg-[var(--surface-soft)] px-3 text-sm font-bold text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
        >
          워크스페이스
        </Link>
      </div>
    </nav>
  );
}
