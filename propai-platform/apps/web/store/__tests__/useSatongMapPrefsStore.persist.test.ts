/**
 * 사통맵 레이어 컨트롤 **영속** (2026-09-04)
 *
 * ★사용자 요구의 잔여분: `#954` 가 「끌 수 있게」, `#960` 이 「기본 화면 밀도」를 줬는데
 *   **끈 것이 새로고침하면 되돌아왔다.** 이 파일이 그 축을 잠근다.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { SATONG_MAP_SHELL_LAYERS } from "@/components/precheck/SatongMapShell";
import { accountScopedKey } from "@/lib/account-scope";
import { satongSelectionLabelsVisible } from "@/lib/satong-map-layers";
import {
  SATONG_MAP_PREFS_STORE_KEY,
  defaultSatongMapControls,
  useSatongMapPrefs,
} from "@/store/useSatongMapPrefsStore";

const KEY = accountScopedKey(SATONG_MAP_PREFS_STORE_KEY);

beforeEach(() => {
  window.localStorage.clear();
  useSatongMapPrefs.setState({ controlsByLayer: defaultSatongMapControls() });
});

describe("기본값 — 사용자 요구 「기본은 나타나도록」", () => {
  it("★기본 상태에서 「선택 필지」가 켜져 있다(값으로)", () => {
    expect(
      satongSelectionLabelsVisible({
        enabledLayerIds: [],
        controlsByLayer: useSatongMapPrefs.getState().controlsByLayer,
      }),
    ).toBe(true);
  });

  it("★★기본값의 **소유자가 하나**다 — 셸이 자기 목록을 따로 갖지 않는다", async () => {
    // 2026-09-04 실측: 이 목록을 **기억으로** 다시 썼다가 원본과 **세 군데** 달랐다
    //   (transactions 에서 토지·상업업무용 누락 · poi 5→2 · development 통째 누락).
    //   그대로 나갔으면 **남의 의도된 기본값을 조용히 되돌리는 회귀**였다.
    const { readFileSync } = await import("node:fs");
    const { join } = await import("node:path");
    const shell = readFileSync(join(process.cwd(), "components/precheck/SatongMapShell.tsx"), "utf8");
    expect(shell).not.toMatch(/function\s+defaultControlsByLayer/);
    expect(shell).not.toMatch(/const\s+initialLayerControls/);
    // ★대조군 — 셸이 스토어를 실제로 쓴다(위 두 단언이 «파일이 비어서» 참인 게 아니다).
    expect(shell).toMatch(/useSatongMapPrefs/);
  });
});

describe("★★기본값 커버리지 — **내가 실제로 낸 결함**을 잡는 락", () => {
  // 2026-09-04 실측: 이 기본값을 **기억으로** 다시 썼다가 `development: ["facilities"]` 를
  //   **통째로 누락**하고 `poi` 를 5→2 로 줄였다. 그때 그것을 잡은 것은 **아무 락도 아니었고**
  //   내가 원본과 대조해 봐서 알았다. → 그 대조를 **기계로** 만든다.
  const layersWithControls = SATONG_MAP_SHELL_LAYERS.filter((l) => (l.controls?.length ?? 0) > 0).map(
    (l) => l.id as string,
  );

  it("★모집단이 실재한다(공허 방지)", () => {
    expect(layersWithControls.length).toBeGreaterThanOrEqual(8);
  });

  it("★★기본값이 없는 「컨트롤 보유 레이어」는 정확히 셋뿐이다(래칫)", () => {
    // 늘면 = 누군가(또는 내가) 기본값을 빠뜨렸다. 줄면 = 기본값을 새로 줬으니 래칫을 내려라.
    // ★이 단언이 `development` 누락을 **즉시** 잡는다.
    const defaults = Object.keys(defaultSatongMapControls());
    const missing = layersWithControls.filter((id) => !defaults.includes(id)).sort();
    expect(missing).toEqual(["auction", "presale", "roadview"]);
  });

  it("★★기본값 **내용**을 통째로 못 박는다 — 커버리지 락은 「있다/없다」만 본다", () => {
    // ★2026-09-04 변이 실측: 커버리지 락을 넣고도 `poi` 를 5개 → 2개로 줄이는 변이가
    //   **SURVIVED** 했다. 키는 그대로 있으니 «없는 레이어» 집합이 안 변한다.
    //   ★그런데 그것이 **내가 실제로 낸 두 번째 결함**이다(상권·공원·병원을 지웠다).
    //
    //   내용을 «파생» 시킬 방법은 없다 — 어떤 컨트롤을 기본으로 켤지는 **제품 판단**이고,
    //   선언된 컨트롤 전부를 켜는 것도 아니다(`land-use-wide` 등은 의도적으로 꺼져 있다).
    //   → **골든 스냅샷**으로 못 박는다. 바꾸려면 **여기를 함께 고쳐야** 하고, 그것이
    //     «이 값들은 누군가 이유를 갖고 넣은 것» 이라는 사실을 다음 사람에게 강제로 알린다.
    //   ★원본 주석이 그 이유를 적고 있다 — *"개발 실무 기본값(레인G 권고) — 아파트만 보이던
    //     종전 하드코딩 대신 토지·상업업무용을 기본 포함해…"*
    expect(defaultSatongMapControls()).toEqual({
      cadastre: ["boundary", "selected"],
      zoning: ["land-use"],
      "official-price": ["unit-price"],
      age: ["building-age"],
      transactions: ["kind-trade", "type-apt", "type-land", "type-commercial"],
      poi: ["station", "school", "commerce", "park", "hospital"],
      development: ["facilities"],
      terrain: ["base"],
      capacity: ["far-headroom"],
    });
  });

  it("★역방향 — 기본값 키에 **레이어가 아닌 것**이 없다(오타·유령 키)", () => {
    const layerIds = new Set(SATONG_MAP_SHELL_LAYERS.map((l) => l.id as string));
    const ghosts = Object.keys(defaultSatongMapControls()).filter((k) => !layerIds.has(k));
    expect(ghosts).toEqual([]);
  });

  it("★각 기본값이 **그 레이어가 실제로 선언한 컨트롤**만 담는다 — 죽은 기본값 금지", () => {
    const bad: string[] = [];
    for (const layer of SATONG_MAP_SHELL_LAYERS) {
      const declared = new Set((layer.controls ?? []).map((c) => c.id as string));
      const defs = defaultSatongMapControls() as Record<string, string[] | undefined>;
      for (const id of defs[layer.id as string] ?? []) {
        if (!declared.has(id)) bad.push(`${layer.id}: ${id}`);
      }
    }
    expect(bad).toEqual([]);
  });
});

describe("★영속 — 끈 것이 되돌아오지 않는다", () => {
  it("★★바꾼 값이 계정별 키에 저장된다", () => {
    useSatongMapPrefs.getState().setControlsByLayer((prev) => ({ ...prev, cadastre: ["boundary"] }));
    // ★쓰기는 500ms 디바운스다(`lib/debounced-storage.ts`). 타이머를 흉내 내지 않고
    //   **프로덕션과 같은 플러시 경로**(pagehide)를 태운다 — 그 배선이 끊기면 여기서 죽는다.
    window.dispatchEvent(new Event("pagehide"));
    const raw = window.localStorage.getItem(KEY);
    expect(raw).toBeTruthy();
    expect(JSON.parse(raw!).state.controlsByLayer.cadastre).toEqual(["boundary"]);
  });

  it("★★저장분이 있으면 재수화 후 **그 값**이 산다 — 새로고침 시나리오", async () => {
    window.localStorage.setItem(
      KEY,
      JSON.stringify({ state: { controlsByLayer: { cadastre: ["boundary"] } }, version: 0 }),
    );
    await useSatongMapPrefs.persist.rehydrate();
    const on = satongSelectionLabelsVisible({
      enabledLayerIds: [],
      controlsByLayer: useSatongMapPrefs.getState().controlsByLayer,
    });
    // 껐으면 **꺼진 채로** 돌아온다 = 사용자 요구 그 자체.
    expect(on).toBe(false);
  });

  it("★대칭 — 켠 상태를 저장하면 켜진 채로 돌아온다(한쪽만 재면 반대쪽이 무제한)", async () => {
    window.localStorage.setItem(
      KEY,
      JSON.stringify({ state: { controlsByLayer: { cadastre: ["boundary", "selected"] } }, version: 0 }),
    );
    await useSatongMapPrefs.persist.rehydrate();
    expect(
      satongSelectionLabelsVisible({
        enabledLayerIds: [],
        controlsByLayer: useSatongMapPrefs.getState().controlsByLayer,
      }),
    ).toBe(true);
  });

  it("★저장분이 **없으면** 기본값이다(첫 방문은 종전과 동일 = 회귀 아님)", async () => {
    window.localStorage.clear();
    await useSatongMapPrefs.persist.rehydrate();
    expect(useSatongMapPrefs.getState().controlsByLayer).toEqual(defaultSatongMapControls());
  });
});

describe("★되돌리기 — 나쁜 상태에 갇히지 않는다", () => {
  it("resetControlsByLayer 가 기본값으로 되돌린다", () => {
    useSatongMapPrefs.getState().setControlsByLayer({ cadastre: [] });
    useSatongMapPrefs.getState().resetControlsByLayer();
    expect(useSatongMapPrefs.getState().controlsByLayer).toEqual(defaultSatongMapControls());
  });
});

describe("★계정 격리", () => {
  it("저장키가 **계정별**이다 — 공유키를 쓰지 않는다", () => {
    useSatongMapPrefs.getState().setControlsByLayer({ cadastre: ["boundary"] });
    window.dispatchEvent(new Event("pagehide"));
    expect(KEY).not.toBe(SATONG_MAP_PREFS_STORE_KEY); // 대조군 — 두 키가 실제로 다르다
    expect(window.localStorage.getItem(KEY)).toBeTruthy();
    // ★공유키(레거시 이름 그 자체)에는 쓰지 않는다 — 계정 전환 시 섞이는 경로.
    expect(window.localStorage.getItem(SATONG_MAP_PREFS_STORE_KEY)).toBeNull();
  });
});
