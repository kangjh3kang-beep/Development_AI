"use client";

/**
 * 인증 가드 — 로그인하지 않은 사용자를 로그인 페이지로 리다이렉트.
 *
 * localStorage의 propai_access_token 존재 여부로 판단.
 * 토큰이 없으면 /login으로 이동.
 */

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { loginUrlWithReturn } from "@/lib/authReturnPath";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const params = useParams();
  const locale = (params?.locale as string) || "ko";
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);

  useEffect(() => {
    const token = window.localStorage.getItem("propai_access_token")?.trim();
    if (token) {
      setIsAuthenticated(true);
    } else {
      setIsAuthenticated(false);
      // ★앱 컨텍스트 복귀(2026-07-23): 진입하려던 화면(예: 설치형 현장앱의 start_url)을
      //   ?next= 로 실어, 로그인 후 메인 대시보드가 아니라 원래 목적지로 돌아가게 한다.
      router.replace(loginUrlWithReturn(locale));
    }
  }, [locale, router]);

  // 인증 확인 중 — 로딩 표시
  if (isAuthenticated === null) {
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--background)]">
        <div className="flex flex-col items-center gap-4">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-[var(--accent-strong)] border-t-transparent" />
          <p className="text-sm text-[var(--text-secondary)]">인증 확인 중...</p>
        </div>
      </div>
    );
  }

  // 미인증 — 리다이렉트 중
  if (!isAuthenticated) {
    return null;
  }

  // 인증됨 — 자식 렌더링
  return <>{children}</>;
}
