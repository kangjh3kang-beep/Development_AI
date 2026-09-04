/**
 * 공용 Leaflet 로더 계약.
 *
 * ★이 파일이 생긴 이유는 **변이 검증에서 생존이 나왔기 때문**이다.
 *   `scripts/mutate_changed.py` 가 `loading = null;`(재시도 허용) 줄을 지웠는데 **아무도
 *   알아채지 못했다.** 커밋은 *"실패하면 캐시를 비워 다시 시도할 수 있게 한다(kakao-map 선례)"*
 *   라고 선언해 놓고 그 계약에 잠금이 없었다 — CLAUDE.md §A.1(분기를 만들면 테스트는 같은 커밋).
 *
 *   그 줄이 없으면 **한 번 실패한 뒤 페이지를 새로고침할 때까지 지도가 영영 안 뜬다.**
 *   이건 바로 이 PR 이 `KakaoAddressSearch` 에서 고친 결함과 **같은 형태**다.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

describe("loadLeaflet — 공용 로더 계약", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.doUnmock("leaflet");
    delete (window as unknown as Record<string, unknown>).L;
  });

  it("★번들에서 불러와 `window.L` 을 채운다 — 소비처 36곳이 이 전역을 읽는다", async () => {
    const marker = { name: "leaflet-stub" };
    vi.doMock("leaflet", () => ({ default: marker }));

    const { loadLeaflet } = await import("@/lib/leaflet-loader");
    await loadLeaflet();

    expect(window.L, "window.L 이 안 채워지면 지도 컴포넌트 전부가 깨진다").toBe(marker);
  });

  it("★실패하면 **다음 호출이 다시 시도**한다 — 한 번 실패로 영구 차단되지 않는다", async () => {
    let attempts = 0;
    vi.doMock("leaflet", () => {
      attempts += 1;
      if (attempts === 1) throw new Error("네트워크 실패");
      return { default: { name: "leaflet-stub" } };
    });

    const { loadLeaflet } = await import("@/lib/leaflet-loader");

    await expect(loadLeaflet(), "첫 시도는 실패해야 한다(픽스처 전제)").rejects.toThrow();
    // ★여기가 핵심 — `loading = null` 이 빠지면 두 번째 호출이 **실패한 프로미스를 그대로
    //   돌려줘** 재시도가 일어나지 않는다(attempts 가 1에 머문다).
    await loadLeaflet();

    expect(attempts, "재시도가 안 됐다 — 실패 시 캐시(loading)를 비우지 않는다").toBe(2);
    expect(window.L, "재시도가 성공했는데 window.L 이 비어 있다").toBeTruthy();
  });

  it("★음성 대조 — 성공한 뒤에는 다시 불러오지 않는다(매번 재로드하면 낭비다)", async () => {
    let attempts = 0;
    vi.doMock("leaflet", () => {
      attempts += 1;
      return { default: { name: "leaflet-stub" } };
    });

    const { loadLeaflet } = await import("@/lib/leaflet-loader");
    await loadLeaflet();
    await loadLeaflet();
    await loadLeaflet();

    expect(attempts, "성공 후에도 매번 다시 불러온다").toBe(1);
  });
});
