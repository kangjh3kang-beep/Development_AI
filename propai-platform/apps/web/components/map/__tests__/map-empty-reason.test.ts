/**
 * 지도 상태줄 정직 계약 — "숫자는 있는데 화면엔 없다"를 설명한다.
 *
 * ★왜 (2026-08-12 사용자 지적, 라이브 실측으로 원인 분리):
 *   한 화면에서 서로 다른 원인 둘이 같은 얼굴을 하고 있었다.
 *
 *   ① 실거래 0건 — 원천 데이터 한계다. 국토부 공개자료가 **지번을 가려서** 준다
 *      (호미곶 land_trade: 322건·29그룹이 전부 `2**`·`3**` 형태 → 좌표 불가).
 *      그런데 지도 문구는 "실거래 무자료 · 지오코딩 전 사전컷 67건 생략 · 좌표미확보
 *      47건 제외 · 반경밖 301건 제외" 였다 — **우리 파이프라인 내부 용어**라
 *      사용자는 시스템 결함으로 읽는다.
 *      ★같은 사유 문장이 이미 있었다: 탁상감정은 정확히 말하고 있었고, 프론트에도
 *        `noSampleReason` 이 백엔드와 글자까지 일치하도록 공유 골든으로 잠겨 있다.
 *        **지도만 그 통로를 안 쓰고 있었다**(코드는 있는데 소비처가 없음).
 *
 *   ② 공시지가가 안 보임 — 데이터도 있고 **실제로 칠해지고 있었다**(priceCount 는 폴리곤을
 *      그린 뒤에만 증가한다). 같은 필지에 용도지역(0.34) → 공시지가(0.42) → 개발여력(0.50)
 *      → 노후도 순으로 **채움을 덧칠**해서 마지막 것만 보였을 뿐이다.
 */
import { describe, expect, it } from "vitest";

import {
  buildChoroplethOverlapNote,
  buildMaskedSampleReason,
  buildOverlayNotes,
} from "@/components/map/SatongMultiMap";

const BASE = {
  showCadastre: false, showZoning: false, showPrice: false, showAge: false, showCapacity: false,
  cadastreCount: 0, zoningCount: 0, priceCount: 0, ageCount: 0, capacityCount: 0, markerCount: 0,
};

describe("코로플레스 겹침 고지", () => {
  it("★두 개 이상 켜지면 '무엇이 보이고 무엇이 가려졌는지'를 말한다", () => {
    const note = buildChoroplethOverlapNote({
      ...BASE, showPrice: true, showCapacity: true, priceCount: 2, capacityCount: 1,
    });
    // 그리는 순서상 개발여력이 공시지가를 덮는다 — 그 방향을 틀리면 안내가 거짓말이 된다.
    expect(note).toContain("개발여력");
    expect(note).toContain("공시지가");
    expect(note).toMatch(/가려짐:/);
  });

  it("★자료가 0건인 레이어는 '가려짐'에 넣지 않는다 — 가릴 것이 없다", () => {
    // 적대검증 반례B: 켜짐만 보면 "용도지역는 가려짐"이라고 말했다(사실도 틀리고 조사도 틀렸다).
    const note = buildChoroplethOverlapNote({
      ...BASE, showZoning: true, zoningCount: 0, showPrice: true, priceCount: 2,
    });
    expect(note).toBe("");  // 실제로 칠해진 것이 1개뿐이면 겹침이 아니다
  });

  it("★마지막 레이어가 0건이면 그 아래 것이 보인다고 말한다", () => {
    // 적대검증 반례A: 공시지가 2건 + 노후도 0건인데 "화면 색은 노후도"라고 말했다.
    const note = buildChoroplethOverlapNote({
      ...BASE, showPrice: true, priceCount: 2, showAge: true, ageCount: 0,
      showCapacity: true, capacityCount: 1,
    });
    expect(note).toContain("화면 색은 개발여력");
    expect(note).not.toContain("노후도");
  });

  it("★조사를 붙이지 않는다 — 받침에 따라 는/은이 갈려 또 틀린다", () => {
    const note = buildChoroplethOverlapNote({
      ...BASE, showZoning: true, zoningCount: 1, showPrice: true, priceCount: 2,
    });
    expect(note).not.toMatch(/용도지역는|공시지가은/);
    expect(note).toContain("가려짐:");
  });

  it("★하나만 켜져 있으면 고지하지 않는다(소음 금지)", () => {
    expect(buildChoroplethOverlapNote({ ...BASE, showPrice: true, priceCount: 2 })).toBe("");
    expect(buildChoroplethOverlapNote(BASE)).toBe("");
  });

  it("★칠해진 건수와 함께 나온다 — '2건인데 왜 안 보이나'가 한 줄로 설명된다", () => {
    const notes = buildOverlayNotes({
      ...BASE, showPrice: true, showCapacity: true, priceCount: 2, capacityCount: 2,
    });
    expect(notes).toContain("공시지가 2건");
    expect(notes).toMatch(/겹침/);
  });
});

describe("실거래 0건 사유", () => {
  const payload = {
    // ★center 는 SatongMarketPayload 의 **필수** 필드다(값은 null 허용).
    //   빠뜨렸다가 CI 가 잡았다 — 워크트리에서는 프론트 타입체크가 안 돌아 CI 가 유일한 검증자다.
    center: null,
    radius_m: 1500,
    radius_applied: true,
    categories: {
      land_trade: { sample_basis: { located_count: 0, unlocated_count: 322, masked_jibun_count: 322, masked_jibun_group_count: 29 } },
      house_trade: { sample_basis: { located_count: 0, unlocated_count: 96, masked_jibun_count: 96, masked_jibun_group_count: 19 } },
    },
  };

  it("★원인을 우리 내부 용어가 아니라 사용자의 말로 설명한다", () => {
    const reason = buildMaskedSampleReason(payload);
    // 공용 함수(noSampleReason)가 만드는 문장이어야 한다 — 여기서 새로 짜면 백엔드와 갈린다.
    expect(reason).toContain("지번을 가려서");
    expect(reason).not.toMatch(/사전컷|좌표미확보/);
  });

  it("★거래 건수를 합산한다 — 카테고리끼리 서로소라 합이 정직하다", () => {
    expect(buildMaskedSampleReason(payload)).toContain((322 + 96).toLocaleString("ko-KR"));
  });

  it("★가려진 것도 위치 미확인도 없으면 사유를 지어내지 않는다", () => {
    expect(
      buildMaskedSampleReason({
        center: null, radius_m: 1500, radius_applied: true,
        categories: { land_trade: { sample_basis: { located_count: 0, unlocated_count: 0, masked_jibun_count: 0 } } },
      }),
    ).toBe("");
  });
});
