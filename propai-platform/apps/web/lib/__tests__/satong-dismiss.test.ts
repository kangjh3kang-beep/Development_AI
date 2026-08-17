/**
 * ESC 해제 조정기 락 — **가장 위 하나만** 닫는가.
 *
 * 이 파일이 잠그는 것은 문구가 아니라 **순서의 근거**다.
 * 종전 결함은 "둘 다 닫힌다"였고, 그 원인은 두 컴포넌트가 각자 `window` 에 ESC 를 걸어
 * 같은 keydown 에 조율 없이 발화한 것이다. 최소 처방(`defaultPrevented` 양보)은
 * **등록 순서가 승부를 정해** z 서열과 어긋날 수 있다 — 그래서 z 를 받는다.
 * → 그러므로 **"등록 순서와 무관하게 z 가 이긴다"** 를 반드시 태워야 한다(아래 ②③).
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { SATONG_UI_Z } from "../satong-map-z";
import { __dismissibleSnapshot, registerDismissible } from "../satong-dismiss";

const esc = () => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", cancelable: true }));

const cleanups: Array<() => void> = [];
const reg = (z: number, close: () => void) => {
  const off = registerDismissible(z, close);
  cleanups.push(off);
  return off;
};

afterEach(() => {
  while (cleanups.length) cleanups.pop()!();
  expect(__dismissibleSnapshot().count, "등록이 새고 있다 — 테스트 간 오염").toBe(0);
});

describe("ESC 해제 조정기", () => {
  it("전제: 등록하면 스냅샷에 보인다(공허 진리 가드)", () => {
    expect(__dismissibleSnapshot().count).toBe(0); // 음성대조 — 시작은 비어 있다
    reg(430, () => {});
    expect(__dismissibleSnapshot().count).toBe(1); // 양성대조 — 조회기 생존
  });

  it("★ESC 한 번은 **하나만** 닫는다 — 이 결함의 본체", () => {
    const high = vi.fn();
    const low = vi.fn();
    reg(SATONG_UI_Z.clickMenu, high); // 470
    reg(SATONG_UI_Z.railPopover, low); // 430

    esc();
    expect(high, "가장 위(470)가 닫혀야 한다").toHaveBeenCalledTimes(1);
    expect(low, "★아래(430)까지 같이 닫혔다 — 종전 결함 그대로다").not.toHaveBeenCalled();
  });

  it("★★등록 **순서를 뒤집어도** z 가 이긴다 — 순서에 기대지 않는다", () => {
    // 이 케이스가 없으면 위 ②는 "우연히 먼저 등록된 게 이긴 것"과 구분되지 않는다.
    const high = vi.fn();
    const low = vi.fn();
    reg(SATONG_UI_Z.railPopover, low); // 낮은 것을 **먼저** 등록
    reg(SATONG_UI_Z.clickMenu, high);

    esc();
    expect(high).toHaveBeenCalledTimes(1);
    expect(low).not.toHaveBeenCalled();
  });

  it("다음 ESC 가 그 다음 표면을 닫는다(단계적 해제 보존)", () => {
    const high = vi.fn();
    const low = vi.fn();
    const offHigh = reg(SATONG_UI_Z.clickMenu, high);
    reg(SATONG_UI_Z.railPopover, low);

    esc();
    offHigh(); // 실제 컴포넌트는 닫히면서 등록을 해제한다
    esc();
    expect(low, "두 번째 ESC 로 아래 표면이 닫혀야 한다").toHaveBeenCalledTimes(1);
  });

  it("★측정 해제(z 음수)는 열린 표면이 없을 때만 차례가 온다", () => {
    const surface = vi.fn();
    const measure = vi.fn();
    reg(-1, measure); // MEASURE_DISMISS_Z
    const offSurface = reg(SATONG_UI_Z.clickMenu, surface);

    esc();
    expect(surface).toHaveBeenCalledTimes(1);
    expect(measure, "표면이 열려 있는데 측정이 먼저 풀렸다").not.toHaveBeenCalled();

    offSurface();
    esc();
    expect(measure).toHaveBeenCalledTimes(1);
  });

  it("등록이 없으면 아무것도 하지 않는다(음성대조)", () => {
    const spy = vi.fn();
    const off = reg(430, spy);
    off();
    cleanups.pop(); // 이미 해제함
    esc();
    expect(spy).not.toHaveBeenCalled();
  });

  it("ESC 가 아닌 키는 무시한다(판별력 대조군)", () => {
    const spy = vi.fn();
    reg(430, spy);
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", cancelable: true }));
    expect(spy, "아무 키에나 닫히면 이 조정기는 판별력이 없다").not.toHaveBeenCalled();
  });
});
