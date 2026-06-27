"use client";

/**
 * AdvancedDrawer — 접이식 '고급 설정' 공용 섹션(기본 접힘).
 *
 * 쉬운 설명:
 *   일반인에게는 꼭 필요한 값만 보여주고, 전문가용 세부 조정 항목은 이 서랍 안에 숨긴다.
 *   서랍 헤더(톱니 아이콘 + 라벨 + 펼침/접힘 화살표)를 누르면 본문이 펼쳐진다.
 *   기본은 접힌 상태(defaultOpen=false)라 화면이 깔끔하게 유지된다.
 *
 * 접근성:
 *   - 헤더는 진짜 버튼(button type="button")이라 키보드(Enter/Space)로 펼침/접힘이 된다.
 *   - aria-expanded로 현재 펼침 상태를 스크린리더에 알린다.
 *   - 본문은 hidden 속성으로 접힘 시 완전히 숨겨(읽기 대상에서 제외) 혼선을 막는다.
 *
 * 사용:
 *   <AdvancedDrawer label="직접 조정(고급)">…편집 폼 등…</AdvancedDrawer>
 *
 * 순수 presentational — 네트워크 호출·store 접근 없음. 디자인 토큰(CSS 변수)만 사용.
 */

import React, { useId, useState } from "react";
import { ChevronDown, Settings2 } from "lucide-react";

export function AdvancedDrawer({
  label = "고급 설정",
  defaultOpen = false,
  className = "",
  children,
}: {
  label?: string;       // 서랍 헤더 라벨(예: "직접 조정(고급)")
  defaultOpen?: boolean; // 처음부터 펼쳐 둘지 — 기본은 접힘
  className?: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  // 헤더 버튼과 본문을 연결해 스크린리더가 무엇을 펼치는지 알 수 있게 한다.
  const bodyId = useId();

  return (
    <div className={`rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] ${className}`}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={bodyId}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 rounded-2xl px-4 py-3 text-left transition-colors hover:bg-[var(--surface-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50"
      >
        <span className="inline-flex items-center gap-2 text-xs font-bold text-[var(--text-secondary)]">
          <Settings2 className="size-3.5 text-[var(--text-tertiary)]" aria-hidden />
          {label}
        </span>
        <ChevronDown
          className={`size-4 text-[var(--text-tertiary)] transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden
        />
      </button>
      <div id={bodyId} hidden={!open} className="border-t border-[var(--line)] px-4 py-4">
        {children}
      </div>
    </div>
  );
}
