/**
 * clearAllProjectData 계정격리 구멍 봉합(레인F P0-3).
 *
 * 증상: 비밀번호 변경·전체 세션 로그아웃(AccountSecurityClient)은 router.push 소프트 이동이라
 *   SPA 세션 토큰이 유지되는데, clearAllProjectData가 sessionStorage의 사통맵 선택필지 미러
 *   (satong_map_selection)를 지우지 않아 다음 계정에서 이전 계정 선택 필지가 복원될 수 있었다.
 *
 * 정본 상수 SATONG_MAP_SELECTION_KEY(문자열 하드코딩 금지)를 와이프 목록에 추가했는지 고정한다.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { clearAllProjectData } from "@/lib/projectSync";
import { SATONG_MAP_SELECTION_KEY } from "@/components/precheck/satong-map-selection";

describe("clearAllProjectData — 사통맵 선택필지 세션캐시 와이프(계정격리)", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    window.localStorage.clear();
  });

  it("satong_map_selection 세션캐시를 제거한다(다음 계정으로 이전 선택 잔존 복원 차단)", () => {
    window.sessionStorage.setItem(
      SATONG_MAP_SELECTION_KEY,
      JSON.stringify({
        savedAt: new Date().toISOString(),
        spaSession: "prev-account-session",
        parcels: [{ id: "P-prev", address: "이전 계정 필지", source: "map" }],
      }),
    );

    clearAllProjectData();

    expect(window.sessionStorage.getItem(SATONG_MAP_SELECTION_KEY)).toBeNull();
  });

  it("현장앱 토큰·프리체크 핸드오프 등 기존 와이프 대상도 그대로 제거된다(회귀 없음)", () => {
    window.sessionStorage.setItem("propai_site_token:proj-1", "token-value");
    window.sessionStorage.setItem("propai_precheck_handoff", "{}");

    clearAllProjectData();

    expect(window.sessionStorage.getItem("propai_site_token:proj-1")).toBeNull();
    expect(window.sessionStorage.getItem("propai_precheck_handoff")).toBeNull();
  });
});
