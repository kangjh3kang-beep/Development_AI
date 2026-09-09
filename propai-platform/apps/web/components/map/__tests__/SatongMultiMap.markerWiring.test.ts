/**
 * ★★배선의 **동일성 축** — #1018 적대 리뷰 MAJOR-6 의 미해결분을 닫는다.
 *
 * 그때 실측: 호출부에서 `const { type, … } = entry` 를 `const type = "apt"` 로 바꿔치기하면
 * **모든 마커가 「아파트」라고 말하는데 2412건이 초록**이었다(SURVIVED). 그 배선이 Leaflet
 * effect 안의 **지역변수**라 태울 수 없었기 때문이다.
 *
 * ★처방은 «락을 더 만드는 것»이 아니라 **바꿔치기할 지역변수를 없애는 것**이었다 —
 *   `buildMarketMarker` 가 유형 문자열이 아니라 **`entry` 를 통째로** 받는다.
 *   그래서 팝업이 말하는 유형과 마커 색이 **같은 인자에서** 나오고, 그 짝이 여기서 잠긴다.
 *
 * ★★그리고 이제 **진짜 Leaflet 으로** 잰다 — #1024 가 목이 필요 없음을 실증했다.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { buildMarketMarker, type SatongMarketGroup } from "@/components/map/SatongMultiMap";
import { MARKET_TRADE_TYPES } from "@/lib/satong-map-layers";
import { __stripCommentsForScan } from "@/lib/source-invariant";

type LeafletNS = typeof import("leaflet");
let L: LeafletNS;

beforeEach(async () => {
  L = (await import("leaflet")).default as unknown as LeafletNS;
});

const 그룹: SatongMarketGroup = {
  name: "화도읍 창현리 736-1",
  dong: "창현리",
  jibun: "736-1",
  lat: 37.6,
  lon: 127.3,
  count: 5,
  avg_area_m2: 32.4,
  avg_price_10k: 8250,
  price_per_pyeong_10k: 842,
  build_year: 2012,
  land_use: "근린상업",
};

const entryOf = (key: string) => {
  const t = MARKET_TRADE_TYPES.find((x) => x.key === key);
  expect(t, `유형 어휘에 ${key} 가 없다 — 조회기 사망`).toBeTruthy();
  return { type: t!.key, color: t!.color, label: t!.label };
};

/** 마커의 팝업 HTML 과 채움색을 꺼낸다(진짜 Leaflet 인스턴스에서). */
const readMarker = (m: unknown) => {
  const marker = m as {
    getPopup: () => { getContent: () => string } | undefined;
    options: { fillColor?: string; radius?: number; bubblingMouseEvents?: boolean };
    getTooltip: () => { getElement?: () => HTMLElement | undefined } | undefined;
  };
  const popup = marker.getPopup();
  expect(popup, "팝업이 안 붙었다").toBeTruthy();
  return {
    html: String(popup!.getContent()),
    fill: marker.options.fillColor,
    radius: marker.options.radius,
    bubbling: marker.options.bubblingMouseEvents,
    tooltipText: marker.getTooltip()?.getElement?.()?.textContent ?? null,
  };
};

/** ★`permanent` 툴팁은 **맵에 올려야** 열린다(레이어가 add 될 때 `openTooltip` 이 돈다).
 *  내 초판은 맵 없이 만들고 `getElement()` 를 읽어 **null 을 보고 「라벨이 안 그려졌다」로 오독**했다. */
const onMap = () => {
  const el = document.createElement("div");
  Object.defineProperty(el, "clientWidth", { value: 800 });
  Object.defineProperty(el, "clientHeight", { value: 600 });
  document.body.appendChild(el);
  return L.map(el, { center: [37.6, 127.3], zoom: 15, attributionControl: false });
};

const build = (
  key: string,
  over: Partial<SatongMarketGroup> = {},
  permanent = true,
  map?: ReturnType<LeafletNS["map"]>,
) => {
  const m = buildMarketMarker(L as never, { ...그룹, ...over }, entryOf(key), {
    kind: "trade",
    permanent,
    pyeongFirst: false,
  });
  if (map) (m as { addTo: (x: unknown) => unknown }).addTo(map);
  return readMarker(m);
};

describe("★배선 동일성 — 팝업 유형과 마커 색이 **같은 entry** 에서 나온다", () => {
  it("★★두 모집단 — 같은 그룹이 entry 에 따라 **유형도 색도** 갈린다", () => {
    const 상업 = build("commercial");
    const 토지 = build("land");

    // 유형(팝업)
    expect(상업.html).toContain("상업업무용");
    expect(상업.html).not.toContain("토지");
    expect(토지.html).toContain("토지");
    expect(토지.html).not.toContain("상업업무용");

    // 색(마커) — ★한쪽만 재면 «색은 맞는데 팝업은 항상 아파트» 같은 구현이 통과한다.
    expect(상업.fill).toBe(entryOf("commercial").color);
    expect(토지.fill).toBe(entryOf("land").color);
    expect(상업.fill, "두 유형의 색이 같다 — 판별력 0").not.toBe(토지.fill);
  });

  it("★★★#1018 이 못 잡던 것 — **유형 전수**에서 팝업과 색이 서로 어긋나지 않는다", () => {
    // ★이것이 「모든 마커가 아파트라고 말하는」 구현을 배제한다: 6종을 돌면서
    //   각자 **자기 라벨**과 **자기 색**이 나와야 한다. 하나라도 고정되면 여기서 죽는다.
    expect(MARKET_TRADE_TYPES.length, "공허 진리 가드").toBeGreaterThanOrEqual(6);
    const seenFills = new Set<string>();
    for (const t of MARKET_TRADE_TYPES) {
      const got = build(t.key);
      expect(got.html, `${t.key}: 팝업이 자기 유형을 말하지 않는다`).toContain(t.label);
      expect(got.fill, `${t.key}: 마커 색이 자기 색이 아니다`).toBe(t.color);
      seenFills.add(String(got.fill));
    }
    // ★색이 전부 달라야 한다 — 하나로 고정하는 구현을 배제한다.
    expect(seenFills.size, "색이 유형 수만큼 갈리지 않는다").toBe(MARKET_TRADE_TYPES.length);
  });

  it("★크기 배선 — `count` 가 반지름에 실리고 상한 18 이다", () => {
    expect(build("apt", { count: 1 }).radius).toBe(9);
    const 큰 = build("apt", { count: 10_000 }).radius;
    expect(큰, "상한을 넘었다").toBe(18);
    expect(build("apt", { count: 1 }).radius, "count 가 반지름에 안 실린다").not.toBe(큰);
  });

  it("★점 클릭 격리가 유지된다 — 마커 클릭이 지도로 번지면 필지선택이 함께 발동한다", () => {
    expect(build("apt").bubbling).toBe(false);
  });

  it("★라벨 — 이름과 가격이 실리고 `permanent` 가 옵션대로다", () => {
    const map = onMap();
    const 상시 = build("apt", {}, true, map);
    expect(상시.tooltipText ?? "", "상시 라벨이 안 그려졌다").toContain("화도읍 창현리 736-1");
    expect(상시.tooltipText ?? "", "가격이 라벨에 안 실렸다").toMatch(/8,250만|8250/);
    // ★대비 — hover 라벨은 열기 전엔 DOM 이 없다. 그 차이가 `permanent` 배선의 증거다
    //   (한쪽만 재면 «항상 상시» 도 통과한다).
    expect(build("apt", {}, false, map).tooltipText, "permanent:false 인데 라벨이 이미 떠 있다").toBeNull();
    map.remove();
  });
});

describe("★호출부 배선 — effect 가 `entry` 를 **통째로** 넘긴다(소스 락 · 약함을 명시)", () => {
  it("지역변수로 풀어 쓰지 않는다 — 그것이 #1018 의 바꿔치기 표면이었다", () => {
    // ★소스 락이라 행위 락보다 약하다. 다만 이 축(호출부가 무엇을 넘기는가)은 effect 안이라
    //   목 없이는 행위로 못 태운다 — 그래서 **명제를 좁혀** 「지역변수 재도입」만 본다.
    // ★★**주석을 먼저 걷어낸다.** 걷지 않았더니 «종전엔 `const { type, color } = entry` 로 풀어
    //   썼고» 라고 **내가 적은 설명 주석**이 이 검사에 걸려 **위양성**을 냈다 — §검증규율 8 의
    //   *"주석에 예시를 적으면 그 예시가 다음 검사의 위양성이 된다"* 그대로다.
    const raw = readFileSync(resolve(process.cwd(), "components/map/SatongMultiMap.tsx"), "utf-8");
    const src = __stripCommentsForScan(raw, "components/map/SatongMultiMap.tsx");
    // ★대조군 — 스트리퍼가 살아 있다(죽으면 아래 음성 단언이 그대로 위양성으로 돌아온다).
    expect(raw, "표식 주석이 사라졌다 — 대조군을 새로 잡아라").toContain("바꿔치기할 지역변수를 없앤다");
    expect(src, "★스트리퍼가 죽었다").not.toContain("바꿔치기할 지역변수를 없앤다");
    const i = src.indexOf("for (const entry of marketRenderPlan) {\n      const typeLabelLimit");
    expect(i, "실거래 렌더 루프를 못 찾았다 — 조회기 사망(리팩토링됐나?)").toBeGreaterThan(-1);
    const block = src.slice(i, i + 1200);
    // ★양성 — entry 를 통째로 넘긴다.
    expect(block).toContain("buildMarketMarker(L, item, entry, {");
    // ★음성 — 유형/색을 지역변수로 풀지 않았다(그것이 바꿔치기 표면이다).
    expect(block, "유형을 지역변수로 풀었다 — 바꿔치기 표면이 되돌아왔다").not.toMatch(
      /const\s*\{[^}]*\btype\b[^}]*\}\s*=\s*entry/,
    );
  });
});
