"use client";

import { useState } from "react";
import { SidebarNav } from "./SidebarNav";
import { type NavSection } from "./nav-config";

export function MobileSidebarToggle({ sections }: { sections: NavSection[] }) {
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Hamburger button — visible only below lg */}
      <button
        type="button"
        aria-label="메뉴 열기"
        onClick={() => setOpen(true)}
        className="lg:hidden flex h-10 w-10 items-center justify-center rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-muted)] hover:text-[var(--text-primary)]"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <line x1="4" x2="20" y1="12" y2="12" />
          <line x1="4" x2="20" y1="6" y2="6" />
          <line x1="4" x2="20" y1="18" y2="18" />
        </svg>
      </button>

      {/* Backdrop overlay */}
      {open && (
        <div
          className="fixed inset-0 z-[100] bg-black/50 backdrop-blur-sm lg:hidden"
          onClick={() => setOpen(false)}
        />
      )}

      {/* Slide-in drawer */}
      <aside
        className={`fixed left-0 top-0 z-[101] h-full w-[280px] overflow-y-auto bg-[var(--surface-secondary)] border-r border-[var(--line)] p-5 shadow-2xl transition-transform duration-300 ease-in-out lg:hidden ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Close button */}
        <div className="flex items-center justify-between mb-6">
          <p className="text-sm font-bold text-[var(--text-primary)] tracking-tight">
            메뉴
          </p>
          <button
            type="button"
            aria-label="메뉴 닫기"
            onClick={() => setOpen(false)}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--line)] text-[var(--text-secondary)] hover:bg-[var(--surface-muted)] hover:text-[var(--text-primary)] transition-colors"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </button>
        </div>

        {/* Nav links — clicking closes the drawer */}
        <div onClick={() => setOpen(false)}>
          <SidebarNav sections={sections} />
        </div>
      </aside>
    </>
  );
}
