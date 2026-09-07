/**
 * [MAP-001 P0] 레이어 상태 정직 라벨 회귀 테스트.
 *
 * 무날조 원칙(양방향):
 *  1) 원천이 미연동('연동 필요')인데 status를 ready로 위장 금지.
 *  2) 실데이터가 이미 렌더링되는데 source를 '연동 필요'(미연동)로 위장 금지.
 *
 * 실연동 근거(코드):
 *  - zoning: SatongMultiMap.tsx 용도지역 폴리곤(feature.zoneType) 렌더링
 *    ← apps/api/routers/auto_zoning.py parcel-at-point zone_type(L744).
 *  - official-price: 공시지가 폴리곤(officialPricePerSqm) 렌더링
 *    ← auto_zoning.py official_price_per_sqm(L748-749).
 *  - age: 노후도 폴리곤(buildingAgeYears) 렌더링 ← built_year(L755-766).
 *  - terrain: 기본/위성/항공 타일이 VWorld WMTS 프록시(/tiles/vworld/wmts)로
 *    실제 렌더링(createOfficialBaseMapLayer).
 *  - transactions: 실거래·시세 레이어 배선(#188) — 레이어 ON + 선택필지 시
 *    /zoning/nearby-map 조회 후 marketPayload/marketLayer props로 SatongMultiMap에
 *    주변 실거래 마커 렌더링(SatongMapShell.tsx marketEnabled 경로). 컨트롤 자체는
 *    필터(향후 제공)라 mapEffect:false지만 렌더 경로는 props로 배선됨.
 */

// 전용 배선(props/내부 fetch)으로 렌더되는 레이어 — 컨트롤 mapEffect 플래그로 렌더
// 여부를 판정할 수 없다. 아래 mapEffect 휴리스틱 검사에서 제외한다:
//  - transactions: marketPayload props(#188)
//  - presale/auction: 청약홈·온비드 배선(#197, 컨트롤은 필터 전용)
const PROP_RENDERED_LAYERS = new Set(["transactions", "presale", "auction"]);
import { describe, expect, it, vi } from "vitest";

// SatongMapShell은 모듈 스코프에서 next/dynamic을 호출하므로 메타데이터 검증용으로 무해화한다.
vi.mock("next/dynamic", () => ({
  default: () => () => null,
}));

import { SATONG_MAP_SHELL_LAYERS } from "../SatongMapShell";

describe("MAP-001 SatongMapShell 레이어 status 정직 라벨", () => {
  it("source가 '연동 필요'인 레이어는 ready/active로 위장하지 않는다", () => {
    const dishonest = SATONG_MAP_SHELL_LAYERS.filter(
      (layer) => layer.source.includes("연동 필요") && layer.status !== "needs-source",
    ).map((layer) => layer.id);
    expect(dishonest).toEqual([]);
  });

  it("poi는 Kakao Local 반경검색 배선(#197)으로 active다", () => {
    const layer = SATONG_MAP_SHELL_LAYERS.find((candidate) => candidate.id === "poi");
    expect(layer).toBeDefined();
    expect(layer?.status).toBe("active");
    expect(layer?.source).not.toContain("연동 필요");
  });

  it("transactions는 실거래 배선(#188)으로 active다", () => {
    const layer = SATONG_MAP_SHELL_LAYERS.find((c) => c.id === "transactions");
    expect(layer?.status).toBe("active");
    expect(layer?.source).not.toContain("연동 필요");
  });

  it("mapEffect 컨트롤도 props 렌더 경로도 없는 레이어는 ready/active일 수 없다", () => {
    const offenders = SATONG_MAP_SHELL_LAYERS.filter(
      (layer) =>
        !PROP_RENDERED_LAYERS.has(layer.id) &&
        !layer.controls.some((control) => control.mapEffect) &&
        layer.status !== "needs-source",
    ).map((layer) => layer.id);
    expect(offenders).toEqual([]);
  });

  // ★2026-09-07(사용자 신고②) — 모집단에서 `terrain` 을 뺐다. 그 레이어는 **베이스맵 스위처의
  //   복제본**이라 레일에서 사라졌다(`SatongMapShell.tsx` 참조). 남은 셋의 명제는 그대로다.
  it("실데이터가 렌더링되는 zoning·official-price·age는 '연동 필요'(미연동)로 위장하지 않는다", () => {
    for (const id of ["zoning", "official-price", "age"]) {
      const layer = SATONG_MAP_SHELL_LAYERS.find((candidate) => candidate.id === id);
      expect(layer, id).toBeDefined();
      // 실제 지도 반영 컨트롤(mapEffect)이 존재한다 = 렌더 경로가 배선돼 있다.
      expect(layer?.controls.some((control) => control.mapEffect), id).toBe(true);
      // 렌더링되는 레이어를 미연동('연동 필요')으로 표기하면 반대 방향 위장이다.
      expect(layer?.source, id).not.toContain("연동 필요");
    }
  });

  // ★★위 케이스는 **손 목록**이라 곧 상한이 된다(§«목록은 곧 상한»). 같은 명제를 **파생형**으로
  //   한 번 더 건다 — 새 레이어가 추가돼도 자동으로 감시망에 들어온다.
  it("★파생형 — `mapEffect` 컨트롤을 가진 레일 레이어는 하나도 '연동 필요'로 위장하지 않는다", () => {
    const wired = SATONG_MAP_SHELL_LAYERS.filter((l) => l.controls.some((c) => c.mapEffect));
    // ★공허 진리 가드 — 손 목록(3)보다 많아야 한다. 0건이면 아래 단언이 무의미하다.
    expect(wired.length).toBeGreaterThan(3);
    const liars = wired.filter((l) => (l.source ?? "").includes("연동 필요")).map((l) => l.id);
    expect(liars).toEqual([]);
  });
});
