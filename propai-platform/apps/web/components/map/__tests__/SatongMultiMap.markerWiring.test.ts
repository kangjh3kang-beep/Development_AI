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

import { afterEach, beforeEach, describe, expect, it } from "vitest";

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
const 열린맵: ReturnType<LeafletNS["map"]>[] = [];
const 열린엘: HTMLElement[] = [];
afterEach(() => {
  // ★정리는 **teardown 에서** — 본문에 두면 단언이 먼저 터졌을 때 도달하지 못한다
  //   (형제 하네스 `lib/__tests__/satong-label-click.test.ts` 가 그렇게 하고 있다).
  for (const m of 열린맵.splice(0)) { try { m.remove(); } catch { /* noop */ } }
  for (const e of 열린엘.splice(0)) e.remove();
});

const onMap = () => {
  const el = document.createElement("div");
  Object.defineProperty(el, "clientWidth", { value: 800 });
  Object.defineProperty(el, "clientHeight", { value: 600 });
  document.body.appendChild(el);
  const m = L.map(el, { center: [37.6, 127.3], zoom: 15, attributionControl: false });
  열린맵.push(m); 열린엘.push(el);
  return m;
};

type BuildOpts = Partial<{
  kind: "trade" | "rent";
  pyeongFirst: boolean;
  ordinal: number;
  typeLabelLimit: number;
  group: unknown;
}>;

const mk = (key: string, over: Partial<SatongMarketGroup> = {}, o: BuildOpts = {}) =>
  buildMarketMarker(L as never, { ...그룹, ...over }, entryOf(key), {
    kind: o.kind ?? "trade",
    pyeongFirst: o.pyeongFirst ?? false,
    // 기본은 «상시 라벨» — `ordinal(0) < typeLabelLimit(1)`.
    ordinal: o.ordinal ?? 0,
    typeLabelLimit: o.typeLabelLimit ?? 1,
    group: o.group,
  });

const build = (key: string, over: Partial<SatongMarketGroup> = {}, o: BuildOpts = {}) =>
  readMarker(mk(key, over, o));

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

  it("★★MAJOR-1 — 마커가 **레이어에 실제로 붙는다**(안 붙으면 지도에 하나도 안 뜬다)", () => {
    // ★★적대 리뷰: 초판은 `addTo(group)` 을 *"레이어는 effect 관심사"* 라며 밖에 뒀는데,
    //   그 한 줄을 지우면 **실거래 마커가 하나도 안 뜨는데 2,103건이 초록**이었다(SURVIVED).
    //   ***태울 수 없는 자리에 배선을 남기고 「관심사 분리」로 부르지 않는다.***
    const group = L.layerGroup();
    expect(group.getLayers().length, "공허 진리 가드 — 시작이 0이어야 증가가 의미를 갖는다").toBe(0);
    mk("apt", {}, { group });
    expect(group.getLayers().length, "마커가 레이어에 안 붙었다 — 지도에 아무것도 안 뜬다").toBe(1);
    mk("land", {}, { group });
    expect(group.getLayers().length, "두 번째 마커가 안 붙었다").toBe(2);
  });

  it("★대칭 — `group` 을 안 주면 **붙이지 않는다**(«항상 붙인다» 배제)", () => {
    const group = L.layerGroup();
    mk("apt", {}, {});
    expect(group.getLayers().length).toBe(0);
  });

  it("★★MAJOR-3 — 라벨 버짓이 판정된다(`ordinal < typeLabelLimit`)", () => {
    // ★*"한 유형이 전역 라벨 버짓을 독식하지 않게"* 라는 **선언된 계약**인데 단언이 0건이었다.
    const map = onMap();
    // 버짓 안 → 상시(DOM 존재)
    expect(build("apt", {}, { group: map, ordinal: 0, typeLabelLimit: 3 }).tooltipText ?? "").toContain(
      "화도읍 창현리 736-1",
    );
    // ★두 모집단 — 버짓 밖 → hover(열기 전엔 DOM 없음)
    expect(
      build("apt", {}, { group: map, ordinal: 3, typeLabelLimit: 3 }).tooltipText,
      "버짓을 넘겼는데 상시 라벨이다 — 라벨 스팸",
    ).toBeNull();
    // ★경계 — 정확히 `<` 인가(`<=` 면 하나 더 샌다)
    expect(build("apt", {}, { group: map, ordinal: 2, typeLabelLimit: 3 }).tooltipText ?? "").toContain(
      "화도읍",
    );
  });

  it("★★MAJOR-2 — `pyeongFirst` 가 라벨 표기 **순서를 바꾼다**(한쪽만 재면 무잠금)", () => {
    const map = onMap();
    const 총액먼저 = build("apt", {}, { group: map, pyeongFirst: false }).tooltipText ?? "";
    const 평당먼저 = build("apt", {}, { group: map, pyeongFirst: true }).tooltipText ?? "";
    expect(총액먼저, "가격 표기가 비었다 — 아래 대조가 공허하다").not.toBe("");
    expect(평당먼저, "`pyeongFirst` 가 라벨에 아무 영향이 없다 — 배선이 끊겼다").not.toBe(총액먼저);
  });

  it("★★전월세 모집단 — `kind:\"rent\"` 도 돈다(매매만 태우면 절반이 샌다)", () => {
    const 월세 = build("apt", { avg_deposit_10k: 1000, avg_monthly_10k: 50 }, { kind: "rent" });
    expect(월세.html, "전월세 팝업이 보증금 축을 안 그린다").toContain("보증금");
    expect(월세.html, "전월세인데 유형이 안 실렸다").toContain("아파트");
  });

  it("★순서 의존 — `bindPopup` 이 라벨보다 **먼저**여야 라벨이 클릭 가능해진다(#1024)", () => {
    // `bindSatongLabel` 이 `getPopup()` 유무로 interactive 를 정한다. 순서가 뒤집히면
    // 라벨 클릭이 다시 **필지 선택**으로 샌다 — 사용자 신고③의 그 결함이다.
    const m = mk("apt", {}, {}) as { getTooltip: () => { options: { interactive?: boolean } } };
    expect(m.getTooltip().options.interactive, "라벨이 클릭 불가다 — bindPopup 순서가 뒤집혔나?").toBe(true);
  });

  it("★라벨 — 이름과 가격이 실리고 `permanent` 가 옵션대로다", () => {
    const map = onMap();
    const 상시 = build("apt", {}, { group: map });
    expect(상시.tooltipText ?? "", "상시 라벨이 안 그려졌다").toContain("화도읍 창현리 736-1");
    expect(상시.tooltipText ?? "", "가격이 라벨에 안 실렸다").toMatch(/8,250만|8250/);
    // ★대비 — hover 라벨은 열기 전엔 DOM 이 없다. 그 차이가 `permanent` 배선의 증거다
    //   (한쪽만 재면 «항상 상시» 도 통과한다).
    expect(build("apt", {}, { group: map, ordinal: 5, typeLabelLimit: 3 }).tooltipText, "permanent:false 인데 라벨이 이미 떠 있다").toBeNull();
  });

  // ★★부채를 **초록 안에** 남긴다(§C-13). 계획서가 `it.todo` 를 약속했는데 초판은 **산문에만**
  //   적고 코드에 0건이었다 — 적대 리뷰가 산출물로 잡았다(§F-24).
  it.todo(
    "★형제 마커의 동일성 축 — **미측정이 아니라 실측 SURVIVED ×2**(2026-09-09 적대 리뷰): " +
      "분양 `status` 를 \"미정\"으로 고정 → 386파일 3528건 초록 · POI 색을 하나로 고정 → 같음. " +
      "★대조군: 같은 도구·스코프에서 실거래 축 변이는 CAUGHT 다(도구 사망 아님). " +
      "★`presalePopupHtml`·`auctionPopupHtml` 은 **export 조차 안 돼** 지금 구조로는 행위 검증 불가 — " +
      "별건 PR 에서 이 함수와 같은 형태로 꺼낸다",
  );
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
