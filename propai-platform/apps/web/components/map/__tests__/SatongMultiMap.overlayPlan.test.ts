/**
 * ★★계획서 §5 가 **선언했으나 존재하지 않던** 락 두 건(적대 리뷰 MAJOR-3).
 *
 * 선언만 있고 락이 없으면 **빈 §5 보다 나쁘다** — 리뷰어가 이미 잠긴 것으로 오독한다(§C-12).
 * 여기서 실제로 잠근다.
 *
 *   ① 지적 레이어를 **꺼도** 선택·등록 필지 폴리곤은 그려진다
 *   ② 목적이 다른 화면(하드코딩 4곳)은 여전히 `cadastre` 를 포함한다 — §2-b 가 의도임을 고정
 */
import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { resolveSatongOverlayPlan } from "@/components/map/SatongMultiMap";
import { defaultSatongMapControls } from "@/store/useSatongMapPrefsStore";
import {
  SATONG_PARCEL_BOUNDARY_CONTROL_IDS,
  SATONG_SELECTION_LABEL_CONTROL_IDS,
  type SatongMapLayerState,
} from "@/lib/satong-map-layers";

const st = (over: Partial<SatongMapLayerState>): SatongMapLayerState =>
  ({ enabledLayerIds: [], controlsByLayer: defaultSatongMapControls(), ...over }) as SatongMapLayerState;

describe("★★① 지적 레이어를 꺼도 **선택 필지 폴리곤**은 그려진다(신고① 이후의 회귀 방지)", () => {
  it("★★두 모집단 — 레이어 OFF 에서도 base 는 켜지고, `boundary` 를 끄면 꺼진다", () => {
    // 모집단 A — 이 PR 의 새 기본 상태(레이어 전부 꺼짐 · 컨트롤은 기본값).
    const off = resolveSatongOverlayPlan(st({ enabledLayerIds: [] }));
    expect(off.showCadastre).toBe(true);
    // ★그리고 **조기반환하지 않는다** — 이것이 실제로 사라졌던 그 값이다.
    expect(off.needsOverlay).toBe(true);

    // 모집단 B — 사용자가 「필지 경계」를 **직접 껐다**. A 만 재면 «항상 true» 도 만점이다.
    const controls = defaultSatongMapControls();
    const noBoundary = {
      ...controls,
      cadastre: (controls.cadastre ?? []).filter((c) => c !== "boundary"),
    };
    const hidden = resolveSatongOverlayPlan(st({ enabledLayerIds: [], controlsByLayer: noBoundary }));
    expect(hidden.showCadastre).toBe(false);
    // 다른 레이어도 없으므로 이때는 오버레이가 필요 없다.
    expect(hidden.needsOverlay).toBe(false);
  });

  it("★공허 진리 가드 — 기본 컨트롤이 실제로 `boundary` 를 담고 있다", () => {
    // 이것이 거짓이면 위 모집단 A 는 «무엇도 켜지 않는» 구현에서도 통과할 수 있다.
    expect(defaultSatongMapControls().cadastre).toContain("boundary");
  });

  it("★레이어를 켜도 base 판정은 **바뀌지 않는다** — 축이 분리됐다는 것의 대칭", () => {
    const on = resolveSatongOverlayPlan(st({ enabledLayerIds: ["cadastre"] }));
    expect(on.showCadastre).toBe(true);
  });

  it("★컨트롤을 **선언하지 않은** 화면은 종전대로 그린다(끄는 UI 가 없는 화면 보호)", () => {
    const bare = resolveSatongOverlayPlan({ enabledLayerIds: [], controlsByLayer: {} } as SatongMapLayerState);
    expect(bare.showCadastre).toBe(true);
  });

  it("★★어휘가 **두 벌**이다 — `parcel-boundary` 만 선언한 화면도 그려진다", () => {
    // ★내 초판이 `includes("boundary")` 한 줄이라 이 두 화면에서 폴리곤이 사라질 뻔했다.
    //   형제 `SATONG_SELECTION_LABEL_CONTROL_IDS` 가 같은 함정을 이미 기록해 두고 있었다.
    const alt = resolveSatongOverlayPlan(
      st({ enabledLayerIds: [], controlsByLayer: { cadastre: ["parcel-boundary", "selected-parcel"] } }),
    );
    expect(alt.showCadastre).toBe(true);
    // ★대칭 — 어느 벌도 없으면 꺼진다(«항상 true» 를 배제한다).
    const none = resolveSatongOverlayPlan(
      st({ enabledLayerIds: [], controlsByLayer: { cadastre: ["selected-parcel"] } }),
    );
    expect(none.showCadastre).toBe(false);
  });

  it("★닫힌 집합이 **실제 선언과 일치**한다 — 세 번째 어휘가 조용히 생기지 않는다", () => {
    const WEB2 = path.resolve(__dirname, "../../..");
    const declared = new Set<string>();
    for (const rel of [
      "store/useSatongMapPrefsStore.ts",
      "components/precheck/ZoningSignalMap.tsx",
      "components/map/ParcelBoundaryMap.tsx",
    ]) {
      const src = fs.readFileSync(path.join(WEB2, rel), "utf8");
      const m = src.match(/cadastre:\s*\[([^\]]*)\]/);
      expect(m, `${rel} 에서 cadastre 컨트롤 선언을 못 찾았다 — 조회기 사망`).toBeTruthy();
      for (const raw of m![1].split(",")) {
        const id = raw.trim().replace(/^["']|["']$/g, "");
        if (id) declared.add(id);
      }
    }
    // 대조군 — 실제로 무언가를 걷었다(0건이면 아래 비교가 공허하다).
    expect(declared.size).toBeGreaterThanOrEqual(4);
    const known = new Set<string>([
      ...SATONG_PARCEL_BOUNDARY_CONTROL_IDS,
      ...SATONG_SELECTION_LABEL_CONTROL_IDS,
    ]);
    const unknown = [...declared].filter((id) => !known.has(id));
    expect(unknown, `닫힌 집합에 없는 cadastre 컨트롤 어휘: ${unknown.join(", ")}`).toEqual([]);
  });

  it("★다른 축은 여전히 레이어에 매인다 — 이 변경이 zoning 까지 풀어 준 게 아니다", () => {
    const off = resolveSatongOverlayPlan(st({ enabledLayerIds: [] }));
    expect(off.showZoning).toBe(false);
    const on = resolveSatongOverlayPlan(st({ enabledLayerIds: ["zoning"] }));
    expect(on.showZoning).toBe(true);
  });
});

describe("★★② 목적이 다른 화면 4곳은 **여전히 지적을 켠 채**다(§2-b 가 의도임을 잠근다)", () => {
  // ★목록형이 아니라 **파일에서 파생**한다 — 손으로 센 목록은 곧 상한이 된다.
  const WEB = path.resolve(__dirname, "../../..");
  const SCREENS = [
    "components/common/GlobalAddressSearch.tsx",
    "components/operations/LandScheduleClient.tsx",
    "components/precheck/ZoningSignalMap.tsx",
    "components/map/ParcelBoundaryMap.tsx",
  ];

  it("★대조군 먼저 — 네 파일이 실재하고 `layerState` 를 실제로 넘긴다", () => {
    // 조회기가 죽으면 본판정과 대조군이 **똑같이 빈다**. 그 «같음»이 유일한 신호이므로 먼저 찍는다.
    for (const rel of SCREENS) {
      const src = fs.readFileSync(path.join(WEB, rel), "utf8");
      expect(src, rel).toContain("layerState");
    }
  });

  it("네 화면 모두 `enabledLayerIds` 에 `cadastre` 를 리터럴로 담고 있다", () => {
    for (const rel of SCREENS) {
      const src = fs.readFileSync(path.join(WEB, rel), "utf8");
      // 「경계 확인 자체가 목적」인 화면들 — 일괄 치환은 신고와 무관한 회귀다.
      // ★기대값을 계획서 문장이 아니라 **코드에서 파생**한다 — 초판은 `enabledLayerIds:` 바로
      //   뒤에 `[` 가 온다고 가정했는데 `ParcelBoundaryMap` 은 타입 주석과 삼항이 사이에 있다.
      //   그 가정은 내 계획서에서 나온 것이지 코드에서 나온 것이 아니었다.
      expect(src, `${rel} 에 enabledLayerIds 가 없다`).toContain("enabledLayerIds");
      expect(src, `${rel} 에서 cadastre 가 사라졌다 — §2-b 의 의도를 확인하라`).toMatch(
        /\[\s*"cadastre"/,
      );
    }
  });
});
