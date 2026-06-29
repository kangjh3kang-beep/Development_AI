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
      <div className="flex items-center gap-1">
        {visibleSections.slice(0, 5).map((section) => {
          const links = flattenLinks(section.items).slice(0, 3);
          const active = activeSections.has(section.id);
          const open = openSectionId === section.id;
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
                className={`flex h-10 cursor-pointer list-none items-center gap-2 rounded-lg px-3 text-sm font-bold transition [&::-webkit-details-marker]:hidden ${
                  active
                    ? "bg-[var(--text-primary)] text-white"
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
                    className="absolute left-0 top-12 z-50 min-w-64 rounded-lg border border-[var(--line)] bg-[var(--surface-secondary)] p-2 shadow-[var(--shadow-md)]"
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
          className="ml-auto inline-flex h-10 items-center rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3 text-sm font-bold text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
        >
          워크스페이스
        </Link>
      </div>
    </nav>
  );
}
