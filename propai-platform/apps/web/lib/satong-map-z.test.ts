/**
 * ★★이 파일의 pane 관련 단언은 **같은 모듈 리터럴끼리의 항등식**이다 — 런타임을 보증하지 않는다.
 *
 * 2026-08-17 까지 아래 "팝업 최상위 사슬" 테스트는 **초록이면서 런타임은 정반대**였다:
 * `globals.css` 의 `.leaflet-pane { z-index:1 !important }` 가 pane 을 전부 1 로 눌러
 * 페인트 순서가 DOM 순서로 떨어졌고, 그 순서에서 **label pane 이 팝업 위**였다
 * (라이브 실측: `.leaflet-popup-pane` 계산 z = 1 · DOM 순서 … popup < proxy < label).
 * 공허한 락을 넘어 **거짓을 보증하는 락**이었다.
 *
 * → 효과를 보증하는 것은 `lib/__tests__/satong-pane-ladder.test.ts`(CSS 불변식)이고,
 *   최종 판정은 `elementFromPoint` 를 쓰는 e2e 다(CLAUDE.md §회귀망 D.18).
 *   여기 단언들은 **상수를 손댈 때 순서가 흐트러지는 것**만 막는 용도로 읽어라.
 */
import { describe, expect, it } from "vitest";

import { LEAFLET_PANE_Z, SATONG_PANE_Z, SATONG_UI_Z } from "./satong-map-z";

describe("satong-map-z — z-index 계약", () => {
  it("모든 UI 오버레이 층위는 양수(격리된 지도 z=0 위)", () => {
    for (const value of Object.values(SATONG_UI_Z)) {
      expect(value).toBeGreaterThan(0);
    }
  });

  it("확인 카드가 항상 최상위(사용자 결정 흐름은 어떤 오버레이에도 가리지 않는다)", () => {
    const max = Math.max(...Object.values(SATONG_UI_Z));
    expect(SATONG_UI_Z.confirmCard).toBe(max);
  });

  it("오버레이 상대 순서: 전체화면버튼 ≤ 코너도크 < 타일실패 < 하단바 < 클릭팝오버 < 확인카드", () => {
    expect(SATONG_UI_Z.fullscreenButton).toBeLessThanOrEqual(SATONG_UI_Z.cornerDock);
    expect(SATONG_UI_Z.cornerDock).toBeLessThan(SATONG_UI_Z.tileFailure);
    expect(SATONG_UI_Z.tileFailure).toBeLessThan(SATONG_UI_Z.bottomBar);
    // 클릭 팝오버는 하단바 위(액션 메뉴 가림 금지), 확인 카드 아래(사용자 결정 최우선).
    expect(SATONG_UI_Z.bottomBar).toBeLessThan(SATONG_UI_Z.clickMenu);
    expect(SATONG_UI_Z.clickMenu).toBeLessThan(SATONG_UI_Z.confirmCard);
  });

  it("[상수 항등식] labelPane 은 폴리곤(overlay=400)과 마커(600) 사이 — ★런타임 보증은 satong-pane-ladder.test.ts", () => {
    expect(SATONG_PANE_Z.label).toBeGreaterThan(LEAFLET_PANE_Z.overlay);
    expect(SATONG_PANE_Z.label).toBeLessThan(LEAFLET_PANE_Z.marker);
  });

  it("[상수 항등식] 팝업 최상위 사슬 overlay < label < marker < tooltip < popup — ★2026-08-17 까지 런타임은 정반대였다(satong-pane-ladder.test.ts 참조)", () => {
    expect(LEAFLET_PANE_Z.overlay).toBeLessThan(SATONG_PANE_Z.label);
    expect(SATONG_PANE_Z.label).toBeLessThan(LEAFLET_PANE_Z.marker);
    expect(LEAFLET_PANE_Z.marker).toBeLessThan(LEAFLET_PANE_Z.tooltip);
    expect(LEAFLET_PANE_Z.tooltip).toBeLessThan(LEAFLET_PANE_Z.popup);
  });
});
