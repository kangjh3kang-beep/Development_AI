import { afterEach, describe, expect, it } from "vitest";

import {
  dominantConstraintKey,
  readSatongMapSelection,
  satongSelectionAddresses,
  satongSelectionToParcelRows,
  selectionToSiteAnalysisPatch,
  siteAnalysisParcelsToSelection,
  siteAnalysisToSelection,
  writeSatongMapSelection,
  SATONG_MAP_SELECTION_KEY,
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

describe("readSatongMapSelection — SPA 세션 스탬프(T1: 미연결 잔존 차단)", () => {
  afterEach(() => {
    window.sessionStorage.clear();
  });

  it("이번 세션에서 write→read 하면 sameSpaSession=true (SPA 내 복귀 유지)", () => {
    writeSatongMapSelection(parcels);
    const read = readSatongMapSelection();
    expect(read?.parcels).toHaveLength(2);
    expect(read?.sameSpaSession).toBe(true);
  });

  it("다른 세션 토큰으로 저장된 payload는 sameSpaSession=false (하드 리로드/새 탭 잔존)", () => {
    window.sessionStorage.setItem(
      SATONG_MAP_SELECTION_KEY,
      JSON.stringify({
        savedAt: new Date().toISOString(),
        spaSession: "이전-세션-토큰",
        parcels,
      }),
    );
    const read = readSatongMapSelection();
    expect(read?.parcels).toHaveLength(2); // 파싱은 되지만
    expect(read?.sameSpaSession).toBe(false); // 이번 SPA 세션 것이 아님
  });

  it("토큰 없는 구 payload(하위호환)는 sameSpaSession=false 로 취급", () => {
    window.sessionStorage.setItem(
      SATONG_MAP_SELECTION_KEY,
      JSON.stringify({ savedAt: new Date().toISOString(), parcels }),
    );
    expect(readSatongMapSelection()?.sameSpaSession).toBe(false);
  });

  it("write([])는 캐시를 제거하고 read 는 null", () => {
    writeSatongMapSelection(parcels);
    writeSatongMapSelection([]);
    expect(readSatongMapSelection()).toBeNull();
  });
});

// ────────────────────────────────────────────────────────────────────────────
// 2026-08-20 — PNU 칸에 **PNU 가 아닌 것**이 저장되던 근본 결함의 회귀 잠금.
//
// 종전 코드: `pnu: parcel.pnu || parcel.id`. `parcel.id` 는 PNU 미확보 시 주소 합성값이라
// PNU 칸에 `"경기도 오산시 내삼미동"` 이 들어앉았다. 그 결과 ①지번 파생 무동작
// ②경계응답의 진짜 PNU 승격 차단 ③경계 요청에 실려 나가 보강 전체가 죽음
// (라이브 실측 2026-08-20: 서버가 echo + area 0 + zone null + lookup_failed).
// ────────────────────────────────────────────────────────────────────────────
describe("PNU 오염 차단 — 저장(write)과 복원(read) 양쪽", () => {
  const DONG = "경기도 오산시 내삼미동";
  const REAL_PNU = "4137011000104670001";

  it("★저장: PNU 미확보 필지의 PNU 칸에 **id(주소 합성값)를 넣지 않는다**", () => {
    const patch = selectionToSiteAnalysisPatch([
      { id: DONG, pnu: null, address: DONG, areaSqm: 100, source: "excel" },
    ]);
    const stored = patch?.parcels?.[0] as { pnu?: string } | undefined;
    expect(stored?.pnu).toBe(""); // 미확보 = 빈 문자열(가짜 PNU 아님)
    expect(stored?.pnu).not.toBe(DONG);
    expect(patch?.pnu).toBeNull(); // 대표 PNU 도 마찬가지
  });

  it("저장: 진짜 PNU 는 그대로 보존한다(무회귀)", () => {
    const patch = selectionToSiteAnalysisPatch([
      { id: REAL_PNU, pnu: REAL_PNU, address: DONG, areaSqm: 100, source: "map" },
    ]);
    expect((patch?.parcels?.[0] as { pnu?: string }).pnu).toBe(REAL_PNU);
    expect(patch?.pnu).toBe(REAL_PNU);
  });

  it("★복원: **이미 오염돼 저장된** 프로젝트를 읽는 순간 가짜 PNU 를 버린다(자가치유)", () => {
    // 사용자 프로젝트에 이미 이렇게 들어 있다 — 코드만 고치면 기존 데이터는 안 낫는다.
    const restored = siteAnalysisParcelsToSelection([
      { pnu: DONG, address: DONG, areaSqm: 100, landCategory: "임야" },
      { pnu: DONG, address: DONG, areaSqm: 200, landCategory: "임야" },
    ]);
    expect(restored.map((p) => p.pnu)).toEqual([null, null]);
    // ★id 도 가짜 PNU 를 쓰면 안 된다 — 77필지가 전부 같은 id 면 React key 충돌·삭제 오작동.
    expect(new Set(restored.map((p) => p.id)).size).toBe(2);
  });

  it("★세 모집단이 왕복 후 **다른 상태**로 남는다(같으면 배선을 끊어도 통과한다)", () => {
    const restored = siteAnalysisParcelsToSelection([
      { pnu: REAL_PNU, address: DONG, areaSqm: 1, landCategory: "임야" },   // (A)
      { pnu: "", address: `${DONG} 114-1`, areaSqm: 1, landCategory: "임야" }, // (B)
      { pnu: DONG, address: DONG, areaSqm: 1, landCategory: "임야" },        // (C) 오염값
    ]);
    expect(restored[0].pnu).toBe(REAL_PNU);
    expect(restored[1].pnu).toBeNull();
    expect(restored[2].pnu).toBeNull();
    // (B)와 (C)는 pnu 가 같지만 **주소가 갈린다** — 지번 보유 여부가 두 집합의 실제 차이다.
    expect(restored[1].address).not.toBe(restored[2].address);
  });
});

// ────────────────────────────────────────────────────────────────────────────
// 적대리뷰 CRITICAL 연쇄 — 뷰 캐시 키도 `pnu || address` 라 **같은 동 필지가 한 칸에 몰린다**.
// 경사도·배치 캐시는 이 키로 **쓰고 또 읽는다**(자기 왕복) → 한 필지의 결과가 나머지 76필지에
// 교차 표시된다. 가짜 PNU 가 우연히 제공하던 유일성을 정화하면서 드러난 자리다.
// ────────────────────────────────────────────────────────────────────────────
describe("dominantConstraintKey — 같은 동 필지를 한 칸에 몰지 않는다", () => {
  const DONG = "경기도 오산시 내삼미동";

  it("★주소가 같고 PNU 가 없는 두 필지는 **다른 키**를 갖는다(경사도·배치 교차오염 차단)", () => {
    const a = dominantConstraintKey({ id: `store-0-${DONG}`, pnu: null, address: DONG });
    const b = dominantConstraintKey({ id: `store-1-${DONG}`, pnu: null, address: DONG });
    expect(a).not.toBe(b);
  });

  it("진짜 PNU 가 있으면 **PNU 가 키다** — 서버가 쓰는 키(경계 응답)와 대칭 유지", () => {
    const pnu = "4137011000104670001";
    // 조회 측(클라이언트 id 보유)과 저장 측(서버 응답, id 없음)이 같은 키를 낸다.
    expect(dominantConstraintKey({ id: "store-0-x", pnu, address: DONG })).toBe(pnu);
    expect(dominantConstraintKey({ pnu, address: DONG })).toBe(pnu);
  });

  it("★두 모집단이 다른 결과다 — PNU 있는 쪽은 수렴(대칭), 없는 쪽은 분리", () => {
    const pnu = "4137011000104670001";
    const withPnu = new Set([
      dominantConstraintKey({ id: "a", pnu, address: DONG }),
      dominantConstraintKey({ id: "b", pnu, address: DONG }),
    ]);
    const withoutPnu = new Set([
      dominantConstraintKey({ id: "a", pnu: null, address: DONG }),
      dominantConstraintKey({ id: "b", pnu: null, address: DONG }),
    ]);
    expect(withPnu.size).toBe(1);
    expect(withoutPnu.size).toBe(2);
  });

  it("id 도 PNU 도 없으면 주소로 떨어진다(하위호환 — 서버 응답 shape)", () => {
    expect(dominantConstraintKey({ pnu: null, address: `  ${DONG}  ` })).toBe(DONG);
  });

  it("★주소에 **지번이 있으면** 주소가 키다 — 서버(경계 응답)와 대칭을 지킨다", () => {
    // 서버는 id 를 모르고, 지번 주소로 조회한 필지는 pnu: null 로 돌아올 수 있다.
    // 이때 id 로 떨어지면 저장(주소 키)과 조회(id 키)가 갈려 배너가 조용히 사라진다.
    const addr = "경상북도 포항시 남구 호미곶면 대보리 산1-1";
    expect(dominantConstraintKey({ id: "P-noPnu", pnu: null, address: addr })).toBe(addr);
    expect(dominantConstraintKey({ id: "B-noPnu", pnu: null, address: addr })).toBe(addr);
  });

  it("★세 갈래가 **서로 다른 규칙**을 탄다(하나로 뭉뚱그리면 한쪽이 깨진다)", () => {
    const pnu = "4137011000104670001";
    const jibunAddr = "경기도 오산시 내삼미동 114-1";
    expect(dominantConstraintKey({ id: "x", pnu, address: DONG })).toBe(pnu);         // ① PNU
    expect(dominantConstraintKey({ id: "x", pnu: null, address: jibunAddr })).toBe(jibunAddr); // ② 주소
    expect(dominantConstraintKey({ id: "x", pnu: null, address: DONG })).toBe("x");   // ③ id
  });
});
