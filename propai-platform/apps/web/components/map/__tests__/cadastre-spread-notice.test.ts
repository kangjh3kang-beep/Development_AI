/**
 * 선택이 **너무 멀리 흩어졌을 때**의 지적도 안내 — 일반 안내가 이 상황에서 **막다른 안내**였다.
 *
 * ## 사용자가 본 것(2026-08-24 스크린샷)
 *
 * 선택 6필지가 제천 성내리(위도 37.0367)와 제천 모산동(37.1759)으로 갈려 **약 15.9km** 떨어져
 * 있었다. `fitBounds` 가 둘을 한 화면에 담으려 하면 계산 줌이 **z12~13** 이 되고, 지적 레이어의
 * `minZoom = CADASTRE_MIN_ZOOM(17)` 게이트는 **구조적으로** 통과할 수 없다.
 * (`maxZoom: 17` 은 **상한 캡**이라 하한이 없어 아무 역할을 못 한다.)
 *
 * 그때 화면은 *"확대하면 지번·경계가 표시됩니다"* 라고 안내했는데, **어떤 배율에서도 6필지를
 * 함께 볼 수 없으므로** 그건 막다른 안내다. 이 파일이 스스로 세운 규칙
 * ("막다른 안내를 하지 않는다 · 이 배율에서 해 볼 것을 말한다")을 다중·원거리 선택에서만
 * 어기고 있었다 — 기존 계약 테스트에 **다중선택 시나리오가 0건**이라 빠져나갔다.
 *
 * ★판정은 `map.getZoom()` 이 아니라 **선택 자체의 이격**으로 한다. 줌만 보면 사용자가 손으로
 *   축소한 경우와 구분하지 못해 원인이 아닌 안내를 하게 된다.
 */
import { describe, expect, it } from "vitest";

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { assertWiredThrough } from "@/lib/source-invariant";
import {
  CADASTRE_MIN_ZOOM,
  CADASTRE_VIEW_WIDTH_KM,
  CADASTRE_ZOOM_HINT,
  cadastreHintFor,
  cadastreSpreadHint,
  haversineKm,
  selectionSpreadKm,
} from "@/components/map/SatongMultiMap";

/** 사용자 스크린샷의 실제 좌표(프로덕션 스냅샷에서 그대로 가져옴). */
const 성내리 = [
  { lat: 37.036774796729205, lon: 128.15 },
  { lat: 37.03679040853061, lon: 128.1501 },
];
const 모산동 = [
  { lat: 37.1766866945329, lon: 128.19 },
  { lat: 37.17597027129945, lon: 128.1901 },
];

describe("선택 이격 산정", () => {
  it("★좌표가 2개 미만이면 null — **미상은 0이 아니다**", () => {
    expect(selectionSpreadKm([])).toBeNull();
    expect(selectionSpreadKm([{ lat: 37, lon: 127 }])).toBeNull();
    // 좌표 없는 필지만 있는 경우(프로덕션 필지의 47.5%가 이 형상이다)
    expect(selectionSpreadKm([{ lat: null, lon: null }, { lat: null, lon: null }])).toBeNull();
  });

  it("★사용자 사례가 지적 화면 폭을 넘는다 — 확대해도 함께 볼 수 없다", () => {
    const spread = selectionSpreadKm([...성내리, ...모산동]);
    expect(spread).not.toBeNull();
    expect(spread!).toBeGreaterThan(CADASTRE_VIEW_WIDTH_KM);
    // 자릿수 확인 — 실측 약 15.9km(경도는 대표값이라 정확값이 아니라 대역으로 본다)
    expect(spread!).toBeGreaterThan(10);
  });

  it("[양성 대조군] 같은 블록의 인접 필지는 넘지 않는다 — 정상 선택을 이격으로 오판하지 않는다", () => {
    const spread = selectionSpreadKm(성내리);
    expect(spread).not.toBeNull();
    expect(spread!, "인접 필지를 '멀리 떨어졌다'고 말하면 위양성").toBeLessThan(
      CADASTRE_VIEW_WIDTH_KM,
    );
  });

  it("거리 산식 자체가 살아 있다(대조군) — 서울↔부산 ≈ 325km", () => {
    const d = haversineKm({ lat: 37.5665, lon: 126.978 }, { lat: 35.1796, lon: 129.0756 });
    expect(d).toBeGreaterThan(300);
    expect(d).toBeLessThan(350);
  });
});

describe("이격 안내 문구", () => {
  it("★막다른 안내를 하지 않는다 — '확대하라'고 말하지 않는다", () => {
    const hint = cadastreSpreadHint(15.9);
    expect(hint, "확대해도 함께 볼 수 없는데 확대하라고 했다").not.toMatch(/확대하면/);
    expect(hint, "이 상황에서 해 볼 것을 말해야 한다").toMatch(/개별/);
  });

  it("★일반 안내와 **다른 문구**다 — 같으면 분기가 장식이 된다", () => {
    expect(cadastreSpreadHint(15.9)).not.toBe(CADASTRE_ZOOM_HINT);
  });

  it("★얼마나 떨어졌는지 숫자로 말한다 — 사용자가 판단할 근거를 준다", () => {
    expect(cadastreSpreadHint(15.94)).toMatch(/16km|15\.9km/);
    expect(cadastreSpreadHint(1.24)).toMatch(/1\.2km/);
  });

  it("★임계는 상수에 결속된다 — 대역이 아니라 상수", () => {
    // 지적 최소줌이 바뀌면 화면 폭 가정도 함께 재야 한다는 사실을 고정한다.
    expect(CADASTRE_MIN_ZOOM).toBe(17);
    expect(CADASTRE_VIEW_WIDTH_KM).toBeGreaterThan(0);
    expect(CADASTRE_VIEW_WIDTH_KM).toBeLessThan(2);
  });
});

describe("★판단과 배선 — 재료만 잠그면 분기를 통째로 없애도 초록이다", () => {
  const FILE = "components/map/SatongMultiMap.tsx";

  it("★이격이 임계를 넘으면 이격 안내를 **고른다**(판단 자체를 태운다)", () => {
    expect(cadastreHintFor(15.94)).toMatch(/개별로 확대/);
    expect(cadastreHintFor(15.94)).not.toBe(CADASTRE_ZOOM_HINT);
  });

  it("[양성 대조군] 가까우면 일반 안내를 고른다 — 분기가 한쪽으로 굳지 않았다", () => {
    expect(cadastreHintFor(0.2)).toBe(CADASTRE_ZOOM_HINT);
  });

  it("★이격 미상(좌표 부족)이면 일반 안내 — 모르는 것을 '멀다'고 말하지 않는다", () => {
    expect(cadastreHintFor(null)).toBe(CADASTRE_ZOOM_HINT);
  });

  it("★안내 선택이 실제로 **배선돼 있다** — 순수 함수만 있고 아무도 안 부르면 화면은 그대로다", () => {
    expect(() =>
      assertWiredThrough({
        file: FILE,
        scope: /const hint = cadastreHintFor/,
        mustContain: "selectionSpreadKm",
        minMatches: 1,
      }),
    ).not.toThrow();
    // 공허 진리 방지 — 대상 파일이 실재하고 충분히 크다.
    expect(readFileSync(resolve(process.cwd(), FILE), "utf-8").length).toBeGreaterThan(1000);
  });
});
