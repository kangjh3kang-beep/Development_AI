import { describe, expect, it } from "vitest";

import {
  satongSelectionAddresses,
  satongSelectionToParcelRows,
  selectionToSiteAnalysisPatch,
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
});
