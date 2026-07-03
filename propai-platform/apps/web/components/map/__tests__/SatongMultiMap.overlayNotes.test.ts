/**
 * [MAP-001 P1] 오버레이 상태 메모 정직 라벨 회귀 테스트.
 *
 * 결함: 지적(cadastre) 레이어가 켜져 있어도 지오메트리 자료가 0건이면
 * 아무 표기가 없어, 용도지역/공시지가/노후도의 '무자료' 정직 패턴과 어긋났다.
 * (레이어를 켰는데 상태 메시지가 없으면 사용자는 자료 부재를 알 수 없다.)
 */
import { describe, expect, it } from "vitest";

import { buildOverlayNotes } from "@/components/map/SatongMultiMap";

describe("MAP-001 buildOverlayNotes — 지적 레이어 무자료 정직 표기", () => {
  it("지적 레이어 ON + 지오메트리 0건이면 '지적 무자료'를 표기한다", () => {
    const note = buildOverlayNotes({
      showCadastre: true,
      cadastreCount: 0,
      showZoning: false,
      zoningCount: 0,
      showPrice: false,
      priceCount: 0,
      showAge: false,
      ageCount: 0,
      markerCount: 2,
    });
    expect(note).toContain("지적 무자료");
    expect(note).toContain("좌표 2건");
  });

  it("지적 자료가 있으면 건수를 표기한다", () => {
    const note = buildOverlayNotes({
      showCadastre: true,
      cadastreCount: 3,
      showZoning: false,
      zoningCount: 0,
      showPrice: false,
      priceCount: 0,
      showAge: false,
      ageCount: 0,
      markerCount: 0,
    });
    expect(note).toBe("지적 3건");
  });

  it("지적 레이어 OFF면 지적 항목을 표기하지 않는다", () => {
    const note = buildOverlayNotes({
      showCadastre: false,
      cadastreCount: 0,
      showZoning: true,
      zoningCount: 0,
      showPrice: false,
      priceCount: 0,
      showAge: false,
      ageCount: 0,
      markerCount: 1,
    });
    expect(note).not.toContain("지적");
    expect(note).toContain("용도지역 무자료");
  });

  it("기존 레이어(용도지역/공시지가/노후도)의 건수·무자료 표기는 유지된다", () => {
    const note = buildOverlayNotes({
      showCadastre: true,
      cadastreCount: 1,
      showZoning: true,
      zoningCount: 2,
      showPrice: true,
      priceCount: 0,
      showAge: true,
      ageCount: 4,
      markerCount: 0,
    });
    expect(note).toBe("지적 1건 · 용도지역 2건 · 공시지가 무자료 · 노후도 4건");
  });
});
