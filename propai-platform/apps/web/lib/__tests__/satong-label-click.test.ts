/**
 * ★★사용자 신고③의 **나머지 절반**(2026-09-09) — *"토지로 필지로 표시되고 **인식되는건가**"*.
 *
 * #1018 이 「표시」를 고쳤다(유형 배지). 여기서 「인식」을 고친다:
 * **가격 라벨을 클릭하면 지도 클릭이 발화하고, 그것이 필지 선택 팝오버를 연다.**
 *
 * ★★이 파일이 **진짜 Leaflet 을 jsdom 에서** 돌린다 — 이 저장소의 첫 사례다.
 *   #1012·#1017·#1018 세 PR 이 *"`SatongMultiMap` 용 **Leaflet 목이 없어** 지도 동작을 못 잠근다"*
 *   로 같은 벽에 부딪혔는데, **목은 필요 없었다**: `leaflet` 이 의존성에 선언돼 있고
 *   jsdom 에서 맵·마커·툴팁·팝업이 **그대로 돈다**(탐침으로 실증).
 *
 * ★jsdom 과 브라우저의 **경로가 다르다**(정직 표기):
 *   · 브라우저 — `pointer-events:none` 이면 라벨이 클릭을 **안 받고** 아래(지도)로 통과
 *   · jsdom    — `pointer-events` 를 **무시**하고 라벨이 받아 **버블링**
 *   **결과는 같다**(지도 click 발화). 그래서 여기서는 **결과**를 재고,
 *   `pointer-events` 자체는 아래 «CSS 계약» 락이 파일에서 파생해 본다.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { bindSatongLabel } from "@/lib/satong-map-labels";

type LeafletNS = typeof import("leaflet");

let L: LeafletNS;
let host: HTMLDivElement;
let map: ReturnType<LeafletNS["map"]>;

const mount = () => {
  host = document.createElement("div");
  Object.defineProperty(host, "clientWidth", { value: 800 });
  Object.defineProperty(host, "clientHeight", { value: 600 });
  document.body.appendChild(host);
  map = L.map(host, { center: [37.5, 127.0], zoom: 15, attributionControl: false });
};

beforeEach(async () => {
  L = (await import("leaflet")).default as unknown as LeafletNS;
  mount();
});
afterEach(() => {
  map.remove();
  host.remove();
});

/** 라벨 DOM 을 꺼낸다 — 툴팁은 **열린 뒤에야** DOM 이 생긴다(permanent 는 add 시점). */
const labelEl = (marker: { getTooltip: () => { getElement: () => HTMLElement | undefined } | undefined }) => {
  const el = marker.getTooltip()?.getElement();
  expect(el, "라벨 DOM 이 없다 — 툴팁이 안 열렸다(조회기 사망)").toBeTruthy();
  return el as HTMLElement;
};

describe("★신고③ 나머지 절반 — 라벨 클릭이 필지 선택으로 새지 않는다", () => {
  it("★★결함 재현(음성 대조군) — **처방이 없으면** 라벨 클릭이 지도 클릭을 발화한다", () => {
    // ★이 케이스가 없으면 아래 「0회」가 «원래 0이었다»와 구별되지 않는다.
    //   `bindSatongLabel` 을 **쓰지 않고** 맨 `bindTooltip` 으로 붙인다 = 처방 이전 상태.
    const marker = L.circleMarker([37.5, 127.0], { radius: 8 })
      .bindTooltip("8,250만", { permanent: true, className: "satong-tooltip" })
      .addTo(map);
    let mapClicks = 0;
    map.on("click", () => { mapClicks += 1; });

    labelEl(marker).dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(mapClicks, "결함이 재현되지 않는다 — 이 락의 전제가 사라졌나?").toBe(1);
  });

  it("★★처방 후 — 라벨 클릭이 지도로 **새지 않는다**", () => {
    const marker = L.circleMarker([37.5, 127.0], { radius: 8 })
      .bindPopup("<b>상업업무용</b>")
      .addTo(map);
    bindSatongLabel(marker, "8,250만", { permanent: true, offsetY: 8 });
    let mapClicks = 0;
    map.on("click", () => { mapClicks += 1; });

    labelEl(marker).dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(mapClicks, "라벨 클릭이 여전히 지도로 샌다").toBe(0);
  });

  it("★★두 모집단 — 그런데 **지도 빈 곳 클릭은 여전히 발화**한다", () => {
    // ★위 케이스만 재면 «지도 클릭을 통째로 막는» 구현도 만점이다.
    const marker = L.circleMarker([37.5, 127.0], { radius: 8 }).bindPopup("x").addTo(map);
    bindSatongLabel(marker, "8,250만", { permanent: true, offsetY: 8 });
    let mapClicks = 0;
    map.on("click", () => { mapClicks += 1; });

    map.fire("click", { latlng: L.latLng(37.51, 127.01) });
    expect(mapClicks, "지도 클릭까지 죽었다 — 필지 선택이 통째로 막힌다").toBe(1);
  });

  it("★★마커 라벨은 **그 마커의 팝업을 연다**(사용자가 기대하는 것)", () => {
    const marker = L.circleMarker([37.5, 127.0], { radius: 8 })
      .bindPopup("<b>상업업무용</b> 8,250만")
      .addTo(map);
    bindSatongLabel(marker, "8,250만", { permanent: true, offsetY: 8 });
    // ★공허 진리 가드 — 시작 상태가 닫힘이어야 아래 전이가 의미를 갖는다.
    expect(marker.isPopupOpen()).toBe(false);

    labelEl(marker).dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(marker.isPopupOpen(), "라벨을 눌렀는데 그 거래 팝업이 안 열린다").toBe(true);
  });

  it("★팝업이 **없는** 라벨(측정·선택 앵커)은 아무 일도 안 한다 — 그래도 지도로는 안 샌다", () => {
    // 앵커 3곳(선택 필지 라벨·측정 면적·측정 누적거리)이 이 모집단이다.
    const anchor = L.circleMarker([37.5, 127.0], { radius: 1, opacity: 0 }).addTo(map);
    bindSatongLabel(anchor, "1,542㎡", { permanent: true, offsetY: 0 });
    let mapClicks = 0;
    map.on("click", () => { mapClicks += 1; });

    expect(() => labelEl(anchor).dispatchEvent(new MouseEvent("click", { bubbles: true }))).not.toThrow();
    expect(mapClicks).toBe(0);
    expect(anchor.isPopupOpen()).toBe(false);
  });

  it("★hover 라벨(permanent:false)도 같은 계약이다 — 상시 라벨만 고치면 절반이 샌다", () => {
    const marker = L.circleMarker([37.5, 127.0], { radius: 8 }).bindPopup("x").addTo(map);
    bindSatongLabel(marker, "8,250만", { permanent: false, offsetY: 8 });
    marker.openTooltip(); // hover 를 흉내 낸다
    let mapClicks = 0;
    map.on("click", () => { mapClicks += 1; });

    labelEl(marker).dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(mapClicks).toBe(0);
    expect(marker.isPopupOpen()).toBe(true);
  });
});

describe("★CSS 계약 — jsdom 이 **원리적으로 못 재는** 축(파일에서 파생해 단언)", () => {
  it("`.satong-tooltip` 이 `pointer-events: auto` 다 — 브라우저에서 라벨이 클릭을 받아야 한다", () => {
    const css = readFileSync(resolve(process.cwd(), "app/globals.css"), "utf-8");
    const i = css.indexOf(".leaflet-tooltip.satong-tooltip {");
    expect(i, "규칙을 못 찾았다 — 조회기 사망(리네임됐나?)").toBeGreaterThan(-1);
    const end = css.indexOf("}", i);
    expect(end, "규칙의 끝을 못 찾았다").toBeGreaterThan(i);
    const rule = css.slice(i, end);
    // ★양성 — 필요한 값이 실재한다.
    expect(rule, `규칙: ${rule.slice(0, 200)}`).toContain("pointer-events: auto");
    // ★음성 — 되돌려지지 않았다(그러면 라벨이 클릭을 못 받아 위 락이 전부 공허해진다).
    expect(rule).not.toContain("pointer-events: none");
  });
});
