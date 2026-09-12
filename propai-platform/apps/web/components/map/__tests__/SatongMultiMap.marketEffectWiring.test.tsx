/**
 * ★★★**effect 를 통째로 태운다** — `#1026` R2 적대 리뷰 MAJOR-1.
 *
 * ## 왜 이 파일이 생겼나
 *
 * `#1018` 이 남긴 결함(*"모든 마커가 「아파트」라고 말해도 2,412건 초록"*)을 닫으려고
 * `buildMarketMarker` 를 꺼냈다. **그런데 같은 결함이 한 칸 위로 옮겨갔을 뿐**이었다 —
 * effect 가 그 함수에 넘기는 `opts` 네 값이 **전부 무잠금**이었고, R2 가 넣은 변이
 * **4/4 가 SURVIVED** 했다:
 *
 * | 호출부 변이 | 사용자에게 보이는 결과 |
 * |---|---|
 * | `ordinal: 0` 고정 | 모든 마커가 **상시 라벨** — 라벨 스팸 |
 * | `typeLabelLimit: 999` | 위와 동일(버짓 무효) |
 * | `pyeongFirst: false` 고정 | 「평당가」 토글이 **아무 일도 안 한다** |
 * | `kind: "trade"` 고정 | **전월세 모드에서 모든 팝업이 매매 문구** |
 *
 * ★그때 나는 *"레이어는 effect 관심사"* · *"목 없이는 못 태운다"* 라고 적었다.
 *   **둘 다 이 PR 자신이 기각한 논법이다**(§P3 — *"목은 필요 없었다"*).
 *   ***한 층씩 따라가면 매번 바깥이 생존한다*** — 그래서 축을 **effect 자체**로 옮긴다.
 *
 * ## 왜 이제 가능한가 (관측)
 *
 * `lib/leaflet-loader.ts` 가 **CDN 스크립트가 아니라 번들 `import("leaflet")`** 이다.
 * 그래서 jsdom 에서 `render(<SatongMultiMap …/>)` 만으로 **진짜 지도가 초기화되고 마커가
 * DOM 에 그려진다**(실측: `path.leaflet-interactive` 3개 · `.leaflet-tooltip` 2개).
 * 형제 스모크 파일의 *"CDN 이라 onload 가 발화하지 않는다"* 는 주석은 **낡았다**.
 *
 * ## 매체 — **사용자가 보는 DOM**
 *
 * 마커 핸들이 아니라 **그려진 결과**를 본다. 「배포됐다 ≠ 작동한다」의 그 축이다.
 */
import { render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SatongMultiMap, type SatongMarketPayload } from "@/components/map/SatongMultiMap";
import { SATONG_LABEL_BUDGET } from "@/lib/satong-map-labels";
import type { SatongMapLayerState } from "@/lib/satong-map-layers";

// 네트워크 차단 — 필지 조회는 영구 pending(형제 스모크와 같은 규약).
vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      request: vi.fn(pending), get: vi.fn(pending), post: vi.fn(pending),
      put: vi.fn(pending), patch: vi.fn(pending), delete: vi.fn(pending),
      getV2: vi.fn(pending), postV2: vi.fn(pending), putV2: vi.fn(pending), deleteV2: vi.fn(pending),
    },
  };
});

/** 마커 n 개짜리 실거래 페이로드. 좌표를 흩어 놓아야 fitBounds 가 유효하다. */
const payloadOf = (
  n: number,
  kind: "trade" | "rent",
  type = "apt",
): SatongMarketPayload =>
  ({
    center: { lat: 37.5, lon: 127.0, address: "분석 대상지" },
    categories: {
      [`${type}_${kind}`]: {
        type, kind, count: n,
        groups: Array.from({ length: n }, (_, i) => ({
          name: `가동 ${i + 1}`,
          dong: "창현리", jibun: `${i + 1}-1`,
          lat: 37.5 + i * 0.0005, lon: 127.0 + i * 0.0005,
          count: 2,
          avg_area_m2: 32.4,
          // ★★가격 필드를 **양쪽 다** 싣는다. 전월세에만 보증금을 실으면 「kind 를 trade 로
          //   고정」하는 변이가 **바꿀 것이 없어 조용히 통과**한다(실측 SURVIVED ×1) —
          //   ***분기를 만들었으면 그 분기를 태우는 행이 픽스처에 있어야 한다.***
          avg_price_10k: 8250,
          price_per_pyeong_10k: 842,
          avg_deposit_10k: 1000,
          avg_monthly_10k: 50,
        })),
      },
    },
  }) as unknown as SatongMarketPayload;

const layerStateWith = (controls: string[]): SatongMapLayerState => ({
  enabledLayerIds: ["transactions"],
  controlsByLayer: { transactions: controls },
});

/** ★`fitBounds`(zoom 15) 는 **선택 필지가 있을 때만** 돈다 — 없으면 zoom 12 라 LOD 가
 *  `hover-only` 여서 **상시 라벨이 0개**가 된다(그러면 아래 대조가 전부 공허해진다). */
const 선택필지 = [{ address: "화도읍 창현리 736-1", lat: 37.5, lon: 127.0 } as never];

const 그리기 = async (props: Record<string, unknown>) => {
  const view = render(
    <SatongMultiMap
      focusTarget={{ lat: 37.5, lon: 127.0, label: "초점" }}
      selectedParcels={선택필지}
      {...props}
    />,
  );
  await waitFor(
    () => expect(view.container.querySelector(".leaflet-container"), "지도가 안 떴다").toBeTruthy(),
    { timeout: 5000 },
  );
  // 마커 이펙트는 mapReady 이후 별도 effect 라 한 틱 더 기다린다.
  await waitFor(
    () => expect(view.container.querySelectorAll("path.leaflet-interactive").length).toBeGreaterThan(0),
    { timeout: 5000 },
  );
  return view;
};

/** ★실거래 라벨만 센다 — 선택 필지 라벨(`selectedParcels`)이 같은 클래스로 함께 그려진다.
 *  그것까지 세면 버짓 단언이 **한 개씩 어긋나** 위양성이 된다(실측: 64 이어야 할 자리에 65). */
const 라벨들 = () =>
  Array.from(document.querySelectorAll(".leaflet-tooltip"))
    .map((t) => t.textContent ?? "")
    .filter((t) => t.startsWith("가동 "));

afterEach(() => {
  document.body.innerHTML = "";
});

describe("★★호출부 배선 — effect 가 `buildMarketMarker` 에 **무엇을 넘기는가**", () => {
  it("★공허 진리 가드 — 하네스가 실제로 마커와 상시 라벨을 그린다", async () => {
    const { container } = await 그리기({
      marketPayload: payloadOf(3, "trade"),
      marketLayer: { kind: "trade", types: ["apt"] },
    });
    // 대상지 마커 1 + 실거래 3
    expect(container.querySelectorAll("path.leaflet-interactive").length, "마커가 안 그려졌다").toBe(4);
    expect(라벨들().length, "상시 라벨이 0개다 — 아래 모든 대조가 공허해진다").toBe(3);
    expect(라벨들()[0]).toContain("가동 1");
  });

  it("★★MAJOR-1a — 라벨 **버짓이 호출부에서 실제로 흐른다**(`ordinal`·`typeLabelLimit`)", async () => {
    // 버짓보다 **훨씬 많은** 마커를 준다. 배선이 살아 있으면 상시 라벨은 버짓에서 끊긴다.
    // 호출부에서 `ordinal: 0` 이나 `typeLabelLimit: 999` 로 고정하면 **전부** 상시가 된다.
    const 초과 = 100;
    const { container } = await 그리기({
      marketPayload: payloadOf(초과, "trade"),
      marketLayer: { kind: "trade", types: ["apt"] },
    });
    expect(
      container.querySelectorAll("path.leaflet-interactive").length,
      "마커가 다 안 그려졌다 — 아래 대조가 공허하다",
    ).toBeGreaterThanOrEqual(초과);
    const 상시 = 라벨들().length;
    expect(상시, "상시 라벨이 마커 수만큼 떴다 — 버짓이 안 먹는다(라벨 스팸)").toBeLessThan(초과);
    // ★대역이 아니라 **상수에 결속**시킨다 — 「좀 적다」가 아니라 「버짓과 같다」여야
    //   버짓을 몰래 키우는 변경도 여기서 죽는다.
    expect(상시, "상시 라벨 수가 버짓 상수와 다르다").toBe(SATONG_LABEL_BUDGET);
    // ★두 모집단 — 버짓 **이하**면 전부 상시여야 한다(«항상 N개만» 구현 배제).
    document.body.innerHTML = "";
    await 그리기({
      marketPayload: payloadOf(3, "trade"),
      marketLayer: { kind: "trade", types: ["apt"] },
    });
    expect(라벨들().length, "버짓 안인데 라벨이 잘렸다").toBe(3);
  });

  it("★★MAJOR-1b — 「평당가」 컨트롤이 **라벨 표기 순서를 실제로 바꾼다**(`pyeongFirst`)", async () => {
    await 그리기({
      marketPayload: payloadOf(1, "trade"),
      marketLayer: { kind: "trade", types: ["apt"] },
      layerState: layerStateWith([]),
    });
    const 총액먼저 = 라벨들()[0] ?? "";
    document.body.innerHTML = "";
    await 그리기({
      marketPayload: payloadOf(1, "trade"),
      marketLayer: { kind: "trade", types: ["apt"] },
      layerState: layerStateWith(["unit-price"]),
    });
    const 평당먼저 = 라벨들()[0] ?? "";

    expect(총액먼저, "라벨이 비었다 — 아래 대조가 공허하다").toContain("만");
    expect(평당먼저, "라벨이 비었다").toContain("만");
    // ★**방향**을 단언한다 — `not.toBe` 만 쓰면 «뒤집힌 구현»도 통과한다(R2 MAJOR-4).
    expect(
      총액먼저.indexOf("8,250만"),
      "컨트롤 OFF 인데 총액이 평당보다 뒤에 있다",
    ).toBeLessThan(총액먼저.indexOf("842만/평"));
    expect(
      평당먼저.indexOf("842만/평"),
      "「평당가」를 켰는데 총액이 앞에 온다 — 토글이 반대로 배선됐다",
    ).toBeLessThan(평당먼저.indexOf("8,250만"));
  });

  it("★★MAJOR-1c — 전월세 모드가 **라벨 표기까지 전월세**다(`kind`)", async () => {
    // ★`composeMarketPriceTag` 는 `kind !== "trade"` 면 **가격 표기를 붙이지 않는다**.
    //   그래서 같은 그룹(가격 필드를 **둘 다** 실어 둔다)이라도 라벨이 갈린다 —
    //   호출부가 `kind` 를 안 넘기고 `"trade"` 로 고정하면 **전월세 라벨에 매매가가 뜬다**.
    // ★★**2026-09-12 — 이 자리에서 주석이 두 번 틀렸다. 세 번째는 실측이다.**
    //   ①초판: *"jsdom 에서 Leaflet path 클릭이 팝업을 열지 못한다(실측)"* → **과잉일반화**였다.
    //   ②1차 정정: *"열린다 · 그때 팝업 없는 path(반경 링)를 집었던 것으로 보인다"* → **거짓**이다.
    //      픽스처에 `radius_m` 이 없어 **반경 링은 애초에 그려지지 않았다**(`SatongMultiMap.tsx:2998`).
    //   ③**전수 프로브 실측**(같은 하네스 · 이벤트 3종 · path 당 2초 대기):
    //        path[0] 중심 마커  → 팝업 **열린다**("분석 대상지…")
    //        path[1] 실거래 마커 → **안 열린다**(2초)
    //        path[2] 실거래 마커 → **안 열린다**(2초)
    //      두 path 는 `bindPopup` 을 달고 있다(`:1325`). 왜 안 열리는지는 **미측정**이다
    //      (jsdom 한정인지, 라벨/팝업 양보 계약 때문인지). ★**반증조건**: 라이브 브라우저에서도
    //      실거래 마커 클릭이 팝업을 안 열면 그것은 **사용자 결함**이고 별건이다.
    //   ★★***짧고 최신인 정정이 더 신뢰받는다*** — 그래서 정정문에 조건과 좌표를 원본만큼 붙인다.
    //   라벨을 매체로 두는 선택 자체는 유지한다(열지 않고도 보이는 축이라 더 싸다).
    await 그리기({
      marketPayload: payloadOf(1, "rent"),
      marketLayer: { kind: "rent", types: ["apt"] },
    });
    const 전월세 = 라벨들()[0] ?? "";
    document.body.innerHTML = "";
    await 그리기({
      marketPayload: payloadOf(1, "trade"),
      marketLayer: { kind: "trade", types: ["apt"] },
    });
    const 매매 = 라벨들()[0] ?? "";

    expect(매매, "매매 라벨에 가격이 없다 — 아래 대조가 공허하다").toContain("8,250만");
    expect(
      전월세,
      "전월세인데 라벨에 **매매가**가 붙었다 — 호출부가 kind 를 안 넘기고 trade 로 고정했나?",
    ).not.toContain("8,250만");
    expect(전월세, "전월세 라벨에 이름조차 없다 — 마커가 안 그려졌다").toContain("가동 1");
  });

});
