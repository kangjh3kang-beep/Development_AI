/**
 * [MAP-001 P1] 오버레이 상태 메모 정직 라벨 회귀 테스트.
 *
 * 결함: 지적(cadastre) 레이어가 켜져 있어도 지오메트리 자료가 0건이면
 * 아무 표기가 없어, 용도지역/공시지가/노후도의 '무자료' 정직 패턴과 어긋났다.
 * (레이어를 켰는데 상태 메시지가 없으면 사용자는 자료 부재를 알 수 없다.)
 */
import { describe, expect, it } from "vitest";

import { buildAgeGapDetail, buildOverlayNotes } from "@/components/map/SatongMultiMap";

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
    // ★2026-08-12: 색상 레이어 3개가 켜져 있으나 공시지가는 0건이라 **칠해진 것은 2개**다.
    //   겹침 고지는 '켜짐'이 아니라 '칠해짐'을 센다(0건을 가려졌다고 하면 거짓이다). 그 고지가
    //   뒤에 붙는다. 코로플레스는 같은 필지에 채움을 덧칠해 **마지막 것만 보이는데**,
    //   종전에는 "공시지가 무자료"처럼 건수만 말해 사용자가 "왜 안 보이나"를 알 수 없었다.
    //   ★정확 일치(toBe)를 유지한다 — toContain 으로 낮추면 이 테스트의 잠금이 약해진다.
    expect(note).toBe(
      "지적 1건 · 용도지역 2건 · 공시지가 무자료 · 노후도 4건" +
        " · 색상 레이어 2개 겹침 — 화면 색은 노후도(가려짐: 용도지역)",
    );
  });
});

describe("WP-M3 노후도 무자료 사유 세분화", () => {
  it("buildAgeGapDetail — 0건 사유는 생략, 있는 것만 '·'로 잇는다", () => {
    expect(buildAgeGapDetail({ ageNoBuilding: 3, ageLookupFailed: 9, ageSkippedBulk: 41 })).toBe(
      "나대지추정 3·조회실패 9·대량생략 41",
    );
    expect(buildAgeGapDetail({ ageNoBuilding: 2 })).toBe("나대지추정 2");
    expect(buildAgeGapDetail({ ageLookupFailed: 5 })).toBe("조회실패 5");
    expect(buildAgeGapDetail({})).toBe("");
  });

  it("노후도 0건 + 사유가 있으면 '노후도 무자료(나대지추정 N·조회실패 M)'로 고지한다", () => {
    const note = buildOverlayNotes({
      showCadastre: false,
      cadastreCount: 0,
      showZoning: false,
      zoningCount: 0,
      showPrice: false,
      priceCount: 0,
      showAge: true,
      ageCount: 0,
      markerCount: 0,
      ageNoBuilding: 3,
      ageLookupFailed: 9,
    });
    expect(note).toBe("노후도 무자료(나대지추정 3·조회실패 9)");
  });

  it("노후도 0건이고 사유도 미지정(구 호출부)이면 종전과 동일하게 단일 '노후도 무자료'", () => {
    const note = buildOverlayNotes({
      showCadastre: false,
      cadastreCount: 0,
      showZoning: false,
      zoningCount: 0,
      showPrice: false,
      priceCount: 0,
      showAge: true,
      ageCount: 0,
      markerCount: 0,
    });
    expect(note).toBe("노후도 무자료");
  });

  it("노후도 건수가 있으면 사유 세분과 무관하게 '노후도 N건' 우선(자료 우선)", () => {
    const note = buildOverlayNotes({
      showCadastre: false,
      cadastreCount: 0,
      showZoning: false,
      zoningCount: 0,
      showPrice: false,
      priceCount: 0,
      showAge: true,
      ageCount: 5,
      markerCount: 0,
      ageNoBuilding: 2,
    });
    expect(note).toBe("노후도 5건");
  });
});

describe("WS-D 개발여력 노트(정직 라벨)", () => {
  const base = { showCadastre: false, cadastreCount: 0, showZoning: false, zoningCount: 0,
                 showPrice: false, priceCount: 0, showAge: false, ageCount: 0, markerCount: 0 };

  it("켰는데 산정 가능 필지 0 → '개발여력 무자료(실효·현황 용적률 필요)'", () => {
    expect(buildOverlayNotes({ ...base, showCapacity: true, capacityCount: 0 }))
      .toContain("개발여력 무자료(실효·현황 용적률 필요)");
  });

  it("산정 N건 표기·미지정(구 호출부)은 무언급(무회귀)", () => {
    expect(buildOverlayNotes({ ...base, showCapacity: true, capacityCount: 3 })).toContain("개발여력 3건");
    expect(buildOverlayNotes(base)).not.toContain("개발여력");
  });
});
