"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { clearOnLogout } from "@/lib/projectSync";

export function AuthButton({ locale }: { locale: string }) {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [userName, setUserName] = useState("");

  useEffect(() => {
    const token = typeof window !== "undefined" ? localStorage.getItem("propai_access_token") : null;
    setIsLoggedIn(!!token);

    if (token) {
      // 토큰에서 사용자 정보 추출 (JWT payload)
      try {
        const payload = JSON.parse(atob(token.split(".")[1]));
        setUserName(payload.name || payload.email || "사용자");
      } catch {
        setUserName("사용자");
      }
    }
  }, []);

  const handleLogout = () => {
    // ★분석/프로젝트 로컬데이터 + 소유자표식 완전 제거(계정 간 격리). 토큰도 제거.
    clearOnLogout();
    localStorage.removeItem("propai_access_token");
    localStorage.removeItem("propai_refresh_token");
    setIsLoggedIn(false);
    setUserName("");
    window.location.href = `/${locale}/login`;
  };

  if (isLoggedIn) {
    return (
      <div className="flex items-center gap-1.5">
        <Link
          href={`/${locale}/account`}
          className="text-xs font-bold text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors hidden sm:inline"
          title="내 계정 · 보안"
        >
          {userName}
        </Link>
        <Link
          href={`/${locale}/account`}
          className="rounded-lg px-2.5 py-1 text-xs font-bold text-[var(--text-hint)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-muted)] transition-colors sm:hidden"
        >
          내 계정
        </Link>
        <button
          onClick={handleLogout}
          className="rounded-lg px-2.5 py-1 text-xs font-bold text-[var(--text-hint)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-muted)] transition-colors"
        >
          로그아웃
        </button>
      </div>
    );
  }

  return (
    <Link
      href={`/${locale}/login`}
      className="rounded-lg px-3 py-1 text-xs font-bold text-[var(--accent-strong)] hover:bg-[var(--accent-soft)] transition-colors"
    >
      로그인
    </Link>
  );
}
