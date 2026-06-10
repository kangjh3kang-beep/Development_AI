"use client";

/**
 * 플랫폼 총괄관리자 여부 — 서버(/auth/is-admin, tier 기반)로만 판별.
 * 반환: null=확인 중, false=비관리자, true=관리자.
 * ★관리자 페이지/메뉴/CTA 노출 가드에 사용(데이터 보호는 서버 게이트가 1차).
 */

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";

export function useIsAdmin(): boolean | null {
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  useEffect(() => {
    let alive = true;
    apiClient.get<{ is_admin: boolean }>("/auth/is-admin", { useMock: false })
      .then((r) => alive && setIsAdmin(!!r.is_admin))
      .catch(() => alive && setIsAdmin(false));
    return () => { alive = false; };
  }, []);
  return isAdmin;
}
