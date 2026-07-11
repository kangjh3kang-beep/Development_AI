"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

export function ThemeToggle() {
  // 다크가 기본 부팅 테마(P2a) → 초기값 true 로 첫 페인트를 기본 상태와 정합
  // (하이드레이션 불일치 없음). localStorage 사용자 선택은 아래 useEffect가 반영.
  const [isDark, setIsDark] = useState(true);

  useEffect(() => {
    // 실제 적용된 테마(부트스트랩이 .dark 클래스로 확정)와 동기화 — 라이트 선택도 반영
    const isDarkTheme = document.documentElement.classList.contains("dark");
    setIsDark(isDarkTheme);
  }, []);

  const toggleTheme = () => {
    const nextDark = !isDark;
    setIsDark(nextDark);
    const root = document.documentElement;
    // 클래스(.dark)와 속성([data-theme])을 함께 갱신 — 부트스트랩/토큰 셀렉터 양쪽과 정합
    if (nextDark) {
      root.classList.add("dark");
      root.setAttribute("data-theme", "dark");
      localStorage.setItem("theme", "dark");
    } else {
      root.classList.remove("dark");
      root.setAttribute("data-theme", "light");
      localStorage.setItem("theme", "light");
    }
  };

  return (
    <button
      onClick={toggleTheme}
      className="relative flex h-10 w-10 items-center justify-center rounded-full bg-[var(--surface-muted)] border border-[var(--line)] shadow-sm transition-all hover:bg-[var(--surface-strong)] active:scale-90"
      aria-label="Toggle Theme"
    >
      <AnimatePresence mode="wait" initial={false}>
        {isDark ? (
          <motion.div
            key="moon"
            initial={{ y: 10, opacity: 0, rotate: -45 }}
            animate={{ y: 0, opacity: 1, rotate: 0 }}
            exit={{ y: -10, opacity: 0, rotate: 45 }}
            transition={{ duration: 0.2 }}
            className="text-teal-400"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>
          </motion.div>
        ) : (
          <motion.div
            key="sun"
            initial={{ y: 10, opacity: 0, rotate: -45 }}
            animate={{ y: 0, opacity: 1, rotate: 0 }}
            exit={{ y: -10, opacity: 0, rotate: 45 }}
            transition={{ duration: 0.2 }}
            className="text-amber-500"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>
          </motion.div>
        )}
      </AnimatePresence>
    </button>
  );
}
