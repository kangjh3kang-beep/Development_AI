"use client";

import { useEffect, useState } from "react";

const ACCESS_TOKEN_KEY = "propai_access_token";

function readAccessToken(): string {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(ACCESS_TOKEN_KEY)?.trim() ?? "";
  } catch {
    return "";
  }
}

/**
 * 인증 상태 단일 판정 소스(localStorage 토큰 존재 여부).
 *
 * 토큰은 localStorage에만 있어 서버는 인증 여부를 알 수 없다 — SSR/첫 렌더는
 * 항상 `false`(미인증)를 반환하고, 마운트 시 실제 값으로 1회 동기화한다.
 * 다른 탭에서의 로그인/로그아웃도 `storage` 이벤트로 반영한다.
 *
 * `HomeGate`(홈 콘텐츠: 랜딩 ↔ DashboardHome 분기)와 `DashboardChromeGate`
 * (앱 크롬 표시 여부 분기)가 이 훅을 공유해 인증 판정 로직이 두 곳에서
 * 중복 구현되지 않게 한다.
 */
export function useIsAuthenticated(): boolean {
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    // 마운트 시 외부 저장소(localStorage 토큰)와 1회 동기화.
    /* eslint-disable-next-line react-hooks/set-state-in-effect */
    setAuthed(readAccessToken().length > 0);

    function onStorage(event: StorageEvent) {
      if (event.key === ACCESS_TOKEN_KEY) {
        setAuthed(readAccessToken().length > 0);
      }
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  return authed;
}
