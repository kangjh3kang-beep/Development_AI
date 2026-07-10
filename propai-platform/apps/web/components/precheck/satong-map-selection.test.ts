import { describe, expect, it } from "vitest";

import {
  satongSelectionAddresses,
  satongSelectionToParcelRows,
  selectionToSiteAnalysisPatch,
  siteAnalysisParcelsToSelection,
  siteAnalysisToSelection,
  type SatongSelectionParcel,
} from "./satong-map-selection";

const parcels: SatongSelectionParcel[] = [
  {
    id: "1111010100100010000",
    pnu: "1111010100100010000",
    address: "서울특별시 종로구 청진동 1",
    areaSqm: 120,
    zoneType: "일반상업지역",
    jimok: "대",
    lat: 37.57,
    lon: 126.98,
    source: "map",
  },
  {
    id: "1111010100100020000",
    pnu: "1111010100100020000",
    address: "서울특별시 종로구 청진동 2",
    areaSqm: 180,
    zoneType: "일반상업지역",
    jimok: "대",
    source: "excel",
  },
];

describe("satong-map-selection", () => {
  it("선택 필지를 프로젝트 컨텍스트용 통합 부지 패치로 변환한다", () => {
    const patch = selectionToSiteAnalysisPatch(parcels);

    expect(patch?.address).toBe("서울특별시 종로구 청진동 1");
    expect(patch?.pnu).toBe("1111010100100010000");
    expect(patch?.landAreaSqm).toBe(300);
    expect(patch?.landAreaSqmTotal).toBe(300);
    expect(patch?.repLandAreaSqm).toBe(120);
    expect(patch?.parcelCount).toBe(2);
    expect(patch?.zoneMixed).toBe(false);
    expect(patch?.parcels).toHaveLength(2);
    expect(patch?.coordinates).toEqual({ lat: 37.57, lon: 126.98 });
  });

  it("분석 화면 입력 주소와 백엔드 다필지 행을 같은 선택 목록에서 만든다", () => {
    expect(satongSelectionAddresses(parcels)).toEqual([
      "서울특별시 종로구 청진동 1",
      "서울특별시 종로구 청진동 2",
    ]);

    expect(satongSelectionToParcelRows(parcels)).toEqual([
      expect.objectContaining({
        address: "서울특별시 종로구 청진동 1",
        area_sqm: 120,
        zone_type: "일반상업지역",
      }),
      expect.objectContaining({
        address: "서울특별시 종로구 청진동 2",
        area_sqm: 180,
        zone_type: "일반상업지역",
      }),
    ]);
  });

  it("빈 선택 목록은 분석 패치를 만들지 않는다", () => {
    expect(selectionToSiteAnalysisPatch([])).toBeNull();
  });

  it("옵션B: 선택필지의 좌표·경계·속성을 SSOT 패치에 보존한다", () => {
    const patch = selectionToSiteAnalysisPatch([
      { ...parcels[0], officialPricePerSqm: 10_600_000, buildingAgeYears: 30, builtYear: 1995, geometry: { type: "Point" } },
    ]);
    const p = patch?.parcels?.[0] as Record<string, unknown> | undefined;
    expect(p?.lat).toBe(37.57);
    expect(p?.lon).toBe(126.98);
    expect(p?.officialPricePerSqm).toBe(10_600_000);
    expect(p?.buildingAgeYears).toBe(30);
    expect(p?.geometry).toEqual({ type: "Point" });
  });

  it("하이드레이션: 스토어 필지→선택필지로 복원(필지별 좌표 우선)", () => {
    const seeded = siteAnalysisParcelsToSelection([
      { pnu: "P1", address: "주소1", areaSqm: 100, landCategory: "대", zoneCode: "제2종일반주거지역", lat: 37.5, lon: 127.0 },
      { pnu: "P2", address: "주소2", areaSqm: 200, landCategory: "대", zoneCode: "제2종일반주거지역" },
    ]);
    expect(seeded).toHaveLength(2);
    expect(seeded[0].lat).toBe(37.5);
    expect(seeded[0].zoneType).toBe("제2종일반주거지역");
    expect(seeded[0].source).toBe("map");
    expect(seeded[1].lat).toBeNull(); // 좌표 없는 필지는 null(무날조)
  });

  it("하이드레이션: 필지별 좌표 없으면 대표점(옵션A)을 첫 필지에만 주입", () => {
    const seeded = siteAnalysisParcelsToSelection(
      [
        { pnu: "P1", address: "주소1", areaSqm: 100, landCategory: "대" },
        { pnu: "P2", address: "주소2", areaSqm: 200, landCategory: "대" },
      ],
      { lat: 37.4, lon: 127.1 },
    );
    expect(seeded[0].lat).toBe(37.4); // 첫 필지 = 대표점
    expect(seeded[0].lon).toBe(127.1);
    expect(seeded[1].lat).toBeNull(); // 나머지는 null(대표점 중복주입 금지)
  });

  it("하이드레이션: 주소 없는 필지는 제외", () => {
    const seeded = siteAnalysisParcelsToSelection([
      { pnu: "P1", address: "", areaSqm: 100, landCategory: "대" },
      { pnu: "P2", address: "주소2", areaSqm: 200, landCategory: "대" },
    ]);
    expect(seeded).toHaveLength(1);
    expect(seeded[0].address).toBe("주소2");
  });

  describe("siteAnalysisToSelection", () => {
    it("parcels[]가 있으면 siteAnalysisParcelsToSelection과 동일 결과(필지별 매핑, 첫 필지 좌표 폴백)", () => {
      const rawParcels = [
        { pnu: "P1", address: "주소1", areaSqm: 100, landCategory: "대" },
        { pnu: "P2", address: "주소2", areaSqm: 200, landCategory: "대" },
      ];
      const fallbackCoord = { lat: 37.4, lon: 127.1 };
      const expected = siteAnalysisParcelsToSelection(rawParcels, fallbackCoord);
      const actual = siteAnalysisToSelection({
        address: "대표주소",
        coordinates: fallbackCoord,
        parcels: rawParcels,
      });
      expect(actual).toEqual(expected);
      expect(actual[0].lat).toBe(37.4); // 첫 필지 = 대표점 폴백
      expect(actual[1].lat).toBeNull();
    });

    it("parcels[] 없음 + address 있음(레거시 단일필지) → 대표 1필지 생성(pnu/좌표/repLandAreaSqm 우선)", () => {
      const seeded = siteAnalysisToSelection({
        address: "서울특별시 종로구 청진동 1",
        pnu: "1111010100100010000",
        coordinates: { lat: 37.57, lon: 126.98 },
        landAreaSqm: 500,
        repLandAreaSqm: 120,
        zoneCode: "일반상업지역",
      });
      expect(seeded).toHaveLength(1);
      expect(seeded[0].address).toBe("서울특별시 종로구 청진동 1");
      expect(seeded[0].pnu).toBe("1111010100100010000");
      expect(seeded[0].lat).toBe(37.57);
      expect(seeded[0].lon).toBe(126.98);
      expect(seeded[0].areaSqm).toBe(120); // repLandAreaSqm 우선
      expect(seeded[0].zoneType).toBe("일반상업지역");
      expect(seeded[0].source).toBe("map");
    });

    it("null 또는 address 없음 → [] (무날조)", () => {
      expect(siteAnalysisToSelection(null)).toEqual([]);
      expect(siteAnalysisToSelection({ address: null })).toEqual([]);
      expect(siteAnalysisToSelection({ address: "  " })).toEqual([]);
    });

    it("repLandAreaSqm 없고 landAreaSqm만 있는 경우 areaSqm=landAreaSqm", () => {
      const seeded = siteAnalysisToSelection({
        address: "주소만있는프로젝트",
        landAreaSqm: 330,
      });
      expect(seeded).toHaveLength(1);
      expect(seeded[0].areaSqm).toBe(330);
    });

    it("parcels가 빈 배열(사용자가 명시적으로 비움) → 주소가 있어도 [] (삭제필지 부활 금지)", () => {
      // 마지막 필지 삭제/전체취소 후 재마운트 시, 남아있는 top-level 주소로
      // 대표필지를 되살리면 안 된다(QA HIGH 회귀 — 주소 채널 부활).
      expect(
        siteAnalysisToSelection({
          address: "서울 어딘가 100",
          pnu: "1111000000000000000",
          coordinates: { lat: 37.5, lon: 127.0 },
          parcels: [],
        }),
      ).toEqual([]);
    });
  });
});
