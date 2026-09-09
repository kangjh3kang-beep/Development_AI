/**
 * ★★사용자 신고③의 **나머지 절반**(2026-09-09) — *"토지로 필지로 표시되고 **인식되는건가**"*.
 *
 * #1018 이 「표시」를 고쳤다(유형 배지). 여기서 「인식」을 고친다:
 * **가격 라벨을 클릭하면 지도 클릭이 발화하고, 그것이 필지 선택 팝오버를 연다.**
 *
 * ★★이 파일은 **진짜 Leaflet 을 jsdom 에서** 돌린다 — 이 저장소의 첫 사례다.
 *   #1012·#1017·#1018 세 PR 이 *"Leaflet **목이 없어** 지도 동작을 못 잠근다"* 로 같은 벽에
 *   부딪혔는데 **목은 필요 없었다**: `leaflet` 이 의존성에 선언돼 있고 그대로 돈다.
 *
 * ★★그리고 **클릭은 실제 DOM 으로** 보낸다(`dispatchEvent`). `map.fire("click", …)` 는
 *   Evented **합성 발화**라 사용자 클릭 경로(컨테이너 DOM 리스너 → `_handleDOMEvent`)를
 *   **한 번도 안 태운다** — 적대 리뷰가 그것으로 「두 모집단」 락이 **공허**함을 변이로 실증했다.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { bindSatongLabel } from "@/lib/satong-map-labels";

type LeafletNS = typeof import("leaflet");
let L: LeafletNS;
let host: HTMLDivElement;
let map: ReturnType<LeafletNS["map"]>;

beforeEach(async () => {
  L = (await import("leaflet")).default as unknown as LeafletNS;
  host = document.createElement("div");
  Object.defineProperty(host, "clientWidth", { value: 800 });
  Object.defineProperty(host, "clientHeight", { value: 600 });
  document.body.appendChild(host);
  map = L.map(host, { center: [37.5, 127.0], zoom: 15, attributionControl: false });
});
afterEach(() => { map.remove(); host.remove(); });

/**
 * ★Leaflet 의 `bindTooltip` 시그니처는 좁고(`content: Tooltip|fn|Content`), `bindSatongLabel` 은
 *   `content: unknown` 을 받는 **구조적 타입**이라 반공변성으로 tsc 가 거부한다(실측 TS2345).
 *   프로덕션 호출부는 마커가 `any` 경로로 들어와 조용했고 **이 테스트가 그 간극을 처음 드러냈다.**
 */
const label = (m: unknown, text: string, opts: { permanent: boolean; offsetY?: number }) =>
  bindSatongLabel(m as Parameters<typeof bindSatongLabel>[0], text, opts);

const labelEl = (m: { getTooltip: () => { getElement: () => HTMLElement | undefined } | undefined }) => {
  const el = m.getTooltip()?.getElement();
  expect(el, "라벨 DOM 이 없다 — 툴팁이 안 열렸다(조회기 사망)").toBeTruthy();
  return el as HTMLElement;
};
const click = (el: HTMLElement) => el.dispatchEvent(new MouseEvent("click", { bubbles: true }));

/**
 * ★프로덕션 마커 옵션을 **그대로** 쓴다 — `bubblingMouseEvents: false`.
 *   `SatongMultiMap.tsx` 의 마커 10곳이 전부 이 옵션을 쓰고, 그 자리 주석이 사유를 적어 뒀다:
 *   *"L.Path(circleMarker) 기본 bubblingMouseEvents=true 라 점 클릭이 지도 click 으로 번져
 *     필지선택이 함께 발동했다. 점 클릭 = 정보 팝업만."*
 *   ★내 초판 픽스처는 이 옵션을 빠뜨렸다 — 그래서 hover 케이스에서 마커 클릭이 지도로 **번져**
 *     실패했고, 나는 하마터면 그것을 **처방의 결함으로 오독**할 뻔했다.
 *     ***내가 잰 것이 사용자가 실제로 쓰는 그것인가.***
 */
const prodMarker = (lat: number, lon: number, radius = 8) =>
  L.circleMarker([lat, lon], { radius, bubblingMouseEvents: false });

describe("★신고③ 나머지 절반 — 마커 라벨은 그 거래를 열고, 지도로 새지 않는다", () => {
  it("★★결함 재현(음성 대조군) — 처방이 **없으면** 라벨 클릭이 지도 클릭을 발화한다", () => {
    // ★없으면 아래 「0회」가 «원래 0이었다»와 구별되지 않는다.
    const m = prodMarker(37.5, 127.0)
      .bindTooltip("8,250만", { permanent: true, className: "satong-tooltip" })
      .addTo(map);
    let n = 0;
    map.on("click", () => { n += 1; });
    click(labelEl(m));
    expect(n, "결함이 재현되지 않는다 — 이 락의 전제가 사라졌나?").toBe(1);
  });

  it("★★마커 라벨 — 지도로 **안 새고** 그 마커의 팝업이 열린다", () => {
    const m = prodMarker(37.5, 127.0).bindPopup("<b>상업업무용</b>").addTo(map);
    label(m, "8,250만", { permanent: true, offsetY: 8 });
    let n = 0;
    map.on("click", () => { n += 1; });
    expect(m.isPopupOpen(), "공허 진리 가드 — 시작이 닫힘이어야 전이가 의미를 갖는다").toBe(false);

    click(labelEl(m));
    expect(n, "라벨 클릭이 여전히 지도로 샌다").toBe(0);
    expect(m.isPopupOpen(), "라벨을 눌렀는데 그 거래 팝업이 안 열린다").toBe(true);
  });

  it("★★★두 모집단 — **팝업 없는 앵커 라벨은 여전히 지도로 통과한다**(측정점·필지 선택 보존)", () => {
    // ★★적대 리뷰 MAJOR-2: 내 초판은 클릭을 **무조건** 삼켜 앵커 라벨(측정 면적·누적거리·
    //   선택 필지) 위 클릭까지 죽였다. 그 자리는 `map.on("click")` 안에서 **측정점을 수집**하고
    //   (`measureOnRef`) 필지 선택을 여는 곳이다 — 사용자 가시 기능을 조용히 잃는 것이었다.
    //   ★그리고 내 초판 락이 그 상실을 «그게 옳다» 며 **계약으로 굳히고 있었다.**
    //   ⇒ 「팝업을 가진 라벨만 interactive」로 바꾸면 앵커는 종전대로 통과한다.
    const anchor = prodMarker(37.5, 127.0, 1).addTo(map);
    label(anchor, "1,542㎡", { permanent: true, offsetY: 0 });
    let n = 0;
    map.on("click", () => { n += 1; });

    click(labelEl(anchor));
    expect(n, "앵커 라벨이 클릭을 삼켰다 — 측정점 수집·필지 선택이 죽는다").toBe(1);
    expect(anchor.isPopupOpen()).toBe(false);
  });

  it("★★지도 표면 클릭은 여전히 발화한다 — **실제 DOM 클릭**으로 잰다", () => {
    // ★적대 리뷰 MAJOR-4: 초판은 `map.fire("click", …)` **합성 발화**를 썼다. 그것은
    //   컨테이너 DOM 리스너 경로를 **한 번도 안 태워** «지도 클릭을 통째로 막는» 구현이
    //   그대로 통과했다(변이 SURVIVED 로 실증). 실제 경로로 바꾼다.
    const m = prodMarker(37.5, 127.0).bindPopup("x").addTo(map);
    label(m, "8,250만", { permanent: true, offsetY: 8 });
    let n = 0;
    map.on("click", () => { n += 1; });

    click(map.getContainer());
    expect(n, "지도 클릭까지 죽었다 — 필지 선택이 통째로 막힌다").toBe(1);
  });

  // ★★hover 라벨(permanent:false)은 **못 닫았다 — 부채로 남긴다(측정한 사실과 함께)**.
  //   기대: 상시 라벨과 같은 계약(«상시만 고치면 절반이 샌다»).
  //   실측: `interactive` 옵션은 **설정되고**(`options.interactive === true`) 열린 직후 DOM 에
  //     `leaflet-interactive` 클래스도 **붙는다**. 그런데 **클릭 시점의 이벤트 target 클래스에는
  //     그 클래스가 없고**(계측: `leaflet-tooltip satong-tooltip leaflet-zoom-hide leaflet-tooltip-top`),
  //     그래서 `_findEventTargets` 가 못 찾아 **map click 이 1회 발화**한다.
  //     클릭 후 툴팁은 닫히고 DOM 은 교체되지 않았다. ⇒ **hover 툴팁 생명주기 문제**로 보이나
  //     **원인 미규명**이다.
  //   ★사용자 신고는 **상시 가격 라벨**이고 그 축은 위에서 확실히 잠갔다. hover 라벨을 실제로
  //     클릭할 수 있는지(마커 위 오프셋이라 커서를 옮기면 mouseout 으로 닫힐 수 있다)도 **미측정**이다.
  //   ★«막지 못했다»를 «막았다»로 적지 않는다 — 초록 안에 보이게 둔다(§C-12·C-13).
  it.todo(
    "hover 라벨(permanent:false)도 클릭이 지도로 안 새게 한다 — 클릭 시점 target 에 " +
      "`leaflet-interactive` 가 없어 현재는 map click 1회가 발화한다(원인 미규명). " +
      "먼저 «hover 라벨을 실제로 클릭할 수 있는가»를 브라우저로 재라",
  );

  it("★Leaflet 이 `leaflet-interactive` 를 **붙인다/안 붙인다** — 어포던스(커서)의 근거", () => {
    const m = prodMarker(37.5, 127.0).bindPopup("x").addTo(map);
    label(m, "8,250만", { permanent: true, offsetY: 8 });
    expect(labelEl(m).className, "팝업이 있는데 interactive 가 아니다").toContain("leaflet-interactive");

    const a = prodMarker(37.51, 127.01, 1).addTo(map);
    label(a, "1,542㎡", { permanent: true, offsetY: 0 });
    // ★대칭 — 누를 것이 없으면 `cursor:pointer` 가 붙으면 안 된다(거짓 어포던스 금지).
    expect(labelEl(a).className, "팝업이 없는데 interactive 다 — 거짓 어포던스").not.toContain("leaflet-interactive");
  });
});

describe("★CSS 계약 — jsdom 이 **원리적으로 못 재는** 축(파일에서 파생해 단언)", () => {
  // ★주석을 **걷어내고** 본다 — 이 PR 이 그 블록에 넣은 주석에 `pointer-events`·`none`·`auto`
  //   토큰이 **전부 들어 있다**. 지금은 정확한 부분문자열이 달라 통과하지만, 그것은
  //   §검증규율 8 이 경고하는 바로 그 모양이다(«주석에 예시를 적으면 그 예시가 다음 검사의
  //   위양성이 된다»).
  // ★저장소 정본 스트리퍼(`__stripCommentsForScan`)는 **쓸 수 없다** — 그건 TypeScript 파서라
  //   CSS 를 못 읽고, 실제로 «진단 2346건 · 주석 제거가 불완전해 락이 거짓 초록이 될 수 있어
  //   중단한다» 로 **옳게 거부한다**(실측). 그래서 CSS 전용으로 짧게 걷어내되,
  //   **대조군으로 「정말 걷어냈는지」를 먼저 증명한다** — 스트리퍼가 죽으면 이 락이 통째로 공허해진다.
  const rawCss = () => readFileSync(resolve(process.cwd(), "app/globals.css"), "utf-8");
  const css = () => rawCss().replace(/\/\*[\s\S]*?\*\//g, "");

  it("★대조군 — CSS 주석 스트리퍼가 살아 있다(죽으면 아래 두 락이 공허해진다)", () => {
    const raw = rawCss();
    const stripped = css();
    // 이 PR 이 넣은 주석 문구가 원문엔 있고 스트립본엔 없어야 한다.
    expect(raw, "표식 주석이 사라졌다 — 대조군을 새로 잡아라").toContain("클릭할 것이 있는 라벨만");
    expect(stripped, "★스트리퍼가 죽었다 — 주석이 그대로 남아 아래 락이 위양성/위음성이 된다").not.toContain(
      "클릭할 것이 있는 라벨만",
    );
    // 그리고 규칙 자체는 남아 있어야 한다(«전부 지우는» 스트리퍼 배제).
    expect(stripped).toContain(".leaflet-tooltip.satong-tooltip {");
  });

  it("interactive 라벨만 `pointer-events: auto` 다 — 그리고 **명시도로** Leaflet 을 이긴다", () => {
    const src = css();
    const i = src.indexOf(".leaflet-tooltip.satong-tooltip.leaflet-interactive {");
    expect(i, "규칙을 못 찾았다 — 조회기 사망(리네임됐나?)").toBeGreaterThan(-1);
    const rule = src.slice(i, src.indexOf("}", i));
    expect(rule).toContain("pointer-events: auto");
    expect(rule).toContain("cursor: pointer");
  });

  it("★기본 라벨은 여전히 `pointer-events: none` — 전역으로 열지 않았다", () => {
    const src = css();
    const i = src.indexOf(".leaflet-tooltip.satong-tooltip {");
    expect(i, "기본 규칙을 못 찾았다").toBeGreaterThan(-1);
    const rule = src.slice(i, src.indexOf("}", i));
    expect(rule, "기본 라벨까지 클릭 대상이 됐다 — 아래 요소를 가린다").toContain("pointer-events: none");
  });
});
