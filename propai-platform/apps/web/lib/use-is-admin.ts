"use client";

/**
 * 플랫폼 총괄관리자 여부 — 서버(/auth/is-admin, tier 기반)로만 판별.
 * 반환: null=확인 중, false=비관리자, true=관리자.
 * ★관리자 페이지/메뉴/CTA 노출 가드에 사용(데이터 보호는 서버 게이트가 1차).
 */

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";

// ★세션 캐시: /auth/is-admin은 tier 기반이라 세션 내 불변인데, SidebarNav 등 다수 컴포넌트가
//   매 마운트·페이지 전환마다 재호출하면 불필요한 네트워크 왕복(콜드 ~900ms)이 쌓여 화면 전환이
//   느려진다. 모듈 레벨 promise 캐시로 세션당 1회만 호출하고 결과를 전 소비처가 공유한다.
//   실패는 캐시하지 않아(promise를 비움) 다음 마운트에서 재시도한다. fetchIsAdmin은 SidebarNav도 공유.
let _adminPromise: Promise<boolean> | null = null;
export function fetchIsAdmin(): Promise<boolean> {
  if (!_adminPromise) {
    _adminPromise = apiClient
      .get<{ is_admin: boolean }>("/auth/is-admin", { useMock: false })
      .then((r) => !!r.is_admin)
      .catch(() => {
        _adminPromise = null;
        return false;
      });
  }
  return _adminPromise;
}

export function useIsAdmin(): boolean | null {
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  useEffect(() => {
    let alive = true;
    fetchIsAdmin().then((v) => alive && setIsAdmin(v));
    return () => { alive = false; };
  }, []);
  return isAdmin;
}
