"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

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
    localStorage.removeItem("propai_access_token");
    localStorage.removeItem("propai_refresh_token");
    setIsLoggedIn(false);
    setUserName("");
    window.location.href = `/${locale}/login`;
  };

  if (isLoggedIn) {
    return (
      <div className="flex items-center gap-1.5">
        <span className="text-xs font-bold text-[var(--text-secondary)] hidden sm:inline">
          {userName}
        </span>
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
