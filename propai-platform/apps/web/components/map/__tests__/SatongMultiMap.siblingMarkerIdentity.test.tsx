/**
 * ★★형제 마커(분양·경매·POI·개발계획)의 **동일성 축** — 2026-09-09 부채 상환.
 *
 * ## 왜 (실측)
 *
 * `#1018`·`#1026` 이 실거래 마커에서 닫은 결함 —— *"모든 마커가 「아파트」라고 말해도 초록"* ——
 * 과 **같은 클래스가 형제 넷에 남아 있었다.** 재측정(2026-09-12, 라벨 승계 안 함):
 *
 *     presalePopupHtml 의 `status` 를 "미정" 으로 고정
 *     → 스코프 `components lib` · 기준선 초록 **3,539** · **::VERDICT=SURVIVED**
 *
 * ## ★내가 남긴 부채 기록이 **틀렸다**
 *
 * 그때 `it.todo` 에 *"`presalePopupHtml`·`auctionPopupHtml` 은 **export 조차 안 돼**
 * 지금 구조로는 행위 검증 불가"* 라고 적었다. **거짓이다.** `#1026` 이 만든 effect 하네스로
 * 재 보니 **네 형제 전부 DOM 에 그려지고 팝업까지 열린다**(divIcon·path 모두).
 * export 는 필요 없었다. ***「구조상 불가」도 재 봐야 하는 라벨이다.***
 *
 * ## 판별 축 (탐침으로 실측)
 *
 * | 형제 | 축 | 매체 |
 * |---|---|---|
 * | 분양 | `status` → 아이콘 배경색 + 팝업 문구 | `.leaflet-marker-icon` 인라인 스타일 · 팝업 |
 * | 경매 | `status` → 아이콘 배경색 | 같음 |
 * | POI | `control` → 아이콘 **테두리**색 | 같음 |
 * | 개발계획 | ★**색이 상수**(`#7c3aed`)라 색으로 못 가른다 → **팝업이 유일한 축** | 팝업 |
 */
import { render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SatongMultiMap } from "@/components/map/SatongMultiMap";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      request: vi.fn(pending), get: vi.fn(pending), post: vi.fn(pending), put: vi.fn(pending),
      patch: vi.fn(pending), delete: vi.fn(pending), getV2: vi.fn(pending), postV2: vi.fn(pending),
      putV2: vi.fn(pending), deleteV2: vi.fn(pending),
    },
  };
});

const 선택필지 = [{ address: "화도읍 창현리 736-1", lat: 37.5, lon: 127.0 } as never];

const 그리기 = async (props: Record<string, unknown>) => {
  const view = render(
    <SatongMultiMap focusTarget={{ lat: 37.5, lon: 127.0 }} selectedParcels={선택필지} {...props} />,
  );
  await waitFor(
    () => expect(view.container.querySelector(".leaflet-container"), "지도가 안 떴다").toBeTruthy(),
    { timeout: 5000 },
  );
  await waitFor(
    () =>
      expect(
        view.container.querySelectorAll(".leaflet-marker-icon, path.leaflet-interactive").length,
      ).toBeGreaterThan(0),
    { timeout: 5000 },
  );
  return view;
};

/** divIcon 마커들의 **배경색**(분양·경매) — 인라인 스타일에서 뽑는다. */
const 배경색들 = (root: HTMLElement) =>
  Array.from(root.querySelectorAll(".leaflet-marker-icon"))
    .map((el) => /background:\s*([^;"']+)/.exec((el as HTMLElement).innerHTML)?.[1]?.trim() ?? "")
    .filter(Boolean);

/** divIcon 마커들의 **테두리색**(POI). */
const 테두리색들 = (root: HTMLElement) =>
  Array.from(root.querySelectorAll(".leaflet-marker-icon"))
    .map((el) => /border:\s*3px solid\s*([^;"']+)/.exec((el as HTMLElement).innerHTML)?.[1]?.trim() ?? "")
    .filter(Boolean);

/** 마커를 실제로 눌러 팝업을 연다(사용자가 하는 그 동작). */
const 팝업열기 = async (el: Element) => {
  for (const t of ["mousedown", "mouseup", "click"]) {
    el.dispatchEvent(new MouseEvent(t, { bubbles: true, cancelable: true, clientX: 50, clientY: 50 }));
  }
  await waitFor(
    () => expect(document.querySelector(".leaflet-popup-content"), "팝업이 안 열렸다").toBeTruthy(),
    { timeout: 3000 },
  );
  return document.querySelector(".leaflet-popup-content")!.textContent ?? "";
};

afterEach(() => {
  document.body.innerHTML = "";
});

/**
 * ★★2026-09-12 정정(독립 렌즈 M-6) — 초판은 **「동일성」이라 이름 붙이고 「차이」만 잠갔다.**
 * `not.toBe(색[1])` 형태라 **두 색을 서로 바꿔치기하면 그대로 초록**이다(스왑 변이 4/4 SURVIVED).
 * ★특히 경매 **진행↔매각 스왑**이 통과했는데, `it.todo` 가 묘사한 증상이 정확히 그 축이다.
 *
 * ⇒ **입력 i 의 상태에서 기대색을 파생시켜 마커 i 와 대조**한다. 색 상수는 export 되지 않아
 *   import 할 수 없으므로, **관측된 짝**을 여기 고정한다(값이 바뀌면 빨개진다 — 그것이 옳다).
 *   ★그러면 「i 번 마커가 **자기** 상태의 색인가」를 보게 되어 **스왑이 죽는다.**
 */
const PRESALE_색 = { 접수중: "#ef4444", 분양완료: "#94a3b8", 분양예정: "#0ea5e9" } as const;
const AUCTION_색 = { 진행: "#ef4444", 매각: "#22c55e", 유찰: "#f59e0b" } as const;
const POI_색 = { station: "#0ea5e9", school: "#8b5cf6" } as const;

describe("★형제 마커 동일성 — **자기 상태의** 색·문구여야 한다", () => {
  it("★★분양 — 두 status 가 **다른 색**을 내고 팝업이 **자기 status** 를 말한다", async () => {
    const { container } = await 그리기({
      marketLayer: {
        kind: "trade", types: [], showPresale: true,
        presaleItems: [
          { name: "행복마을", area_name: "경기", status: "접수중", lat: 37.5, lon: 127.0 },
          { name: "미래타운", area_name: "경기", status: "분양완료", lat: 37.501, lon: 127.001 },
        ],
      },
    });
    const 색 = 배경색들(container);
    expect(색.length, "분양 마커가 둘 다 안 그려졌다 — 아래 대조가 공허하다").toBe(2);
    // ★차이만 보면 **스왑이 통과한다** — 각 마커가 **자기** status 의 색인지 본다.
    expect(색[0], "첫 마커가 자기 status(접수중) 색이 아니다").toBe(PRESALE_색.접수중);
    expect(색[1], "둘째 마커가 자기 status(분양완료) 색이 아니다").toBe(PRESALE_색.분양완료);
    expect(색[0], "두 status 의 색이 같다 — 판별력 0").not.toBe(색[1]);

    const 팝업 = await 팝업열기(container.querySelectorAll(".leaflet-marker-icon")[0]);
    expect(팝업, "팝업이 자기 status 를 말하지 않는다").toContain("접수중");
    expect(팝업, "다른 마커의 status 가 섞였다").not.toContain("분양완료");
  });

  it("★★경매 — 두 status 가 **다른 색**을 낸다", async () => {
    const { container } = await 그리기({
      marketLayer: {
        kind: "trade", types: [], showAuction: true,
        auctionItems: [
          { address: "창현리 1-1", status: "진행", lat: 37.5, lon: 127.0 },
          { address: "창현리 2-2", status: "매각", lat: 37.501, lon: 127.001 },
        ],
      },
    });
    const 색 = 배경색들(container);
    expect(색.length, "경매 마커가 둘 다 안 그려졌다").toBe(2);
    // ★★스왑 축 — `it.todo` 가 묘사한 증상(처분방식 "매각" → 「매각 완료」 초록)이 바로 이 자리다.
    expect(색[0], "진행 물건이 진행 색이 아니다 — 상수가 뒤바뀌었나?").toBe(AUCTION_색.진행);
    expect(색[1], "매각 물건이 매각 색이 아니다").toBe(AUCTION_색.매각);
    expect(색[0], "두 status 의 색이 같다").not.toBe(색[1]);
  });

  it("★★POI — 두 유형이 **다른 테두리색**을 낸다", async () => {
    const { container } = await 그리기({
      // ★컨트롤 어휘는 `POI_CONTROL_CODES` 가 SSOT 다 — `station`(≠`subway`)·`school`.
      //   내가 처음 `subway` 로 짐작했다가 마커가 1개만 떴고, 아래 개수 단언이 그것을 잡았다.
      //   ***어휘를 짐작하지 마라 — 그리고 공허 진리 가드가 그것을 잡게 하라.***
      layerState: { enabledLayerIds: ["poi"], controlsByLayer: { poi: ["station", "school"] } },
      poiPayload: {
        available: true,
        coordinates: { lat: 37.5, lon: 127.0 },
        categories: {
          SW8: { label: "지하철", items: [{ name: "역", lat: 37.5, lon: 127.0 }] },
          SC4: { label: "학교", items: [{ name: "초등학교", lat: 37.501, lon: 127.001 }] },
        } as never,
      },
    });
    const 색 = 테두리색들(container);
    expect(색.length, "POI 마커가 둘 다 안 그려졌다 — 컨트롤 어휘가 바뀌었나").toBe(2);
    // ★순회 순서는 `POI_CONTROL_CODES` 선언 순(station → school)이다.
    expect(색[0], "역 마커가 역 색이 아니다 — 상수가 뒤바뀌었나?").toBe(POI_색.station);
    expect(색[1], "학교 마커가 학교 색이 아니다").toBe(POI_색.school);
    expect(색[0], "두 POI 유형의 색이 같다").not.toBe(색[1]);
  });

  // ★★부채를 **초록 안에** 남긴다(§C-13). 커밋 메시지에만 적으면 드러나지 않는다 —
  //   나는 `#1026` 에서 정확히 그것으로 잡혔고, 이 PR 초판에서 **또 그랬다**(선언 2건이
  //   전부 산문이었다 · §F-24). 그래서 여기 코드로 둔다.
  it.todo(
    "★경매 `status` 가 **처분방식**이다 — `onbid_client.py:810` 이 `dspsMthodNm`(처분방식명)을 " +
      "`status` 로 싣는다. 처분**방식**을 진행**상태**로 쓰는 **범주 오류**이고, 프론트는 그것을 " +
      "`AUCTION_STATUS_COLORS` 로 칠한다(예: 처분방식 \"매각\" → 「매각 완료」 초록). " +
      "★**이 PR 에서 고치지 않았다**: 라이브가 `data_source:\"unavailable\"` 이라 경매 마커가 " +
      "하나도 안 떠 **도달 불가**이고, 온비드 어휘 매핑을 검증할 **실표본이 0**이다(2026-09-12 실측). " +
      "★데이터원이 살아나면 **즉시 발화**한다 — 그때 별건 PR 로 온비드 어휘를 실표본에서 파생시켜라",
  );

  it("★★개발계획 — **색이 상수**라 팝업이 유일한 축이고, 그 팝업이 자기 유형·상태를 말한다", async () => {
    const { container } = await 그리기({
      developmentPayload: {
        facilities: [
          { name: "○○역사", type: "철도", status: "사업중", lat: 37.5, lon: 127.0 } as never,
          { name: "△△도로", type: "도로", status: "계획", lat: 37.501, lon: 127.001 } as never,
        ],
      },
    });
    const paths = Array.from(container.querySelectorAll("path.leaflet-interactive"));
    expect(paths.length, "개발계획 마커가 안 그려졌다").toBeGreaterThanOrEqual(2);

    // ★★두 마커를 **각각** 연다. 초판은 하나만 열어서, 팝업이 **항상 facilities[0]** 을 쓰는
    //   변이가 **SURVIVED** 했다(독립 렌즈 M-6 S4) — 계획서가 *"팝업이 유일한 축"* 이라 적은
    //   바로 그 자리인데 그 축이 무잠금이었다.
    const 팝업들: string[] = [];
    for (const path of paths.slice(-2)) {
      document.querySelectorAll(".leaflet-popup-content").forEach((e) => e.remove());
      팝업들.push(await 팝업열기(path));
    }
    const 합 = 팝업들.join(" || ");
    expect(합, "철도/사업중 시설이 팝업에 없다").toContain("철도");
    expect(합, "도로/계획 시설이 팝업에 없다").toContain("도로");
    // ★★각 팝업이 **자기 시설의 유형과 상태 짝**을 말해야 한다 — 짝이 섞이면 동일성이 깨진다.
    for (const 팝업 of 팝업들) {
      const 철도 = 팝업.includes("철도");
      expect(
        철도 ? 팝업.includes("사업중") : 팝업.includes("계획"),
        `팝업의 유형·상태가 서로 다른 시설에서 왔다: ${팝업}`,
      ).toBe(true);
    }
    expect(new Set(팝업들).size, "두 마커가 **같은 팝업**을 낸다 — 항상 첫 시설을 쓰고 있다").toBe(2);
  });
});
