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

  it("labelPane 은 폴리곤(overlay=400)과 마커(600) 사이 — 라벨이 폴리곤 위·마커 흐름 아래", () => {
    expect(SATONG_PANE_Z.label).toBeGreaterThan(LEAFLET_PANE_Z.overlay);
    expect(SATONG_PANE_Z.label).toBeLessThan(LEAFLET_PANE_Z.marker);
  });

  it("★팝업 최상위 사슬(2026-07-17 겹침 신고): overlay < label < marker < tooltip < popup — 지명 타일·상시 라벨이 팝업을 가리면 안 된다", () => {
    expect(LEAFLET_PANE_Z.overlay).toBeLessThan(SATONG_PANE_Z.label);
    expect(SATONG_PANE_Z.label).toBeLessThan(LEAFLET_PANE_Z.marker);
    expect(LEAFLET_PANE_Z.marker).toBeLessThan(LEAFLET_PANE_Z.tooltip);
    expect(LEAFLET_PANE_Z.tooltip).toBeLessThan(LEAFLET_PANE_Z.popup);
  });
});
