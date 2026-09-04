/**
 * 사통맵 레이어 컨트롤 **영속** (2026-09-04)
 *
 * ★사용자 요구의 잔여분: `#954` 가 「끌 수 있게」, `#960` 이 「기본 화면 밀도」를 줬는데
 *   **끈 것이 새로고침하면 되돌아왔다.** 이 파일이 그 축을 잠근다.
 */
import { beforeEach, describe, expect, it } from "vitest";

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
