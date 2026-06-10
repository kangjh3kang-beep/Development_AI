"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useUiReset } from "@/store/useUiReset";

/**
 * 로고(홈) 링크 — 이미 홈 라우트에 있을 때 클릭하면 분석뷰를 랜딩으로 리셋(goHome).
 * (서버 레이아웃에서 onClick을 쓸 수 없어 클라이언트 래퍼로 분리)
 */
export function HomeLink({
  href,
  className,
  children,
}: {
  href: string;
  className?: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const goHome = useUiReset((s) => s.goHome);
  return (
    <Link
      href={href}
      className={className}
      onClick={() => {
        // 같은 홈 라우트면 리마운트가 없으므로 전역 리셋 신호로 랜딩 복귀
        if (pathname === href) goHome();
      }}
    >
      {children}
    </Link>
  );
}
