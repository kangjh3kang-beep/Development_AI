/**
 * ★**행위** 락 — 로그아웃·계정전환 뒤에 **유료 산출물이 실제로 살아 있는지** 본다.
 *
 * ## 왜 이 파일이 생겼나 (2026-08-26 · `#839` 가 만든 CRITICAL 회귀)
 *
 * `#839` 는 계정 격리를 넣으면서 `clearAllProjectData()` 에 이렇게 적었다:
 *
 *     setState({ byProject: {} })     // 메모리 비우기
 *     void persist.rehydrate()        // "대기 쓰기를 덮어쓰므로 마지막 값이 남는다"
 *
 * **그 주석이 거짓이었다.** zustand `hydrate()` 는 `set(stateFromStorage, true)` 뒤
 * **`if (migrated) return setItem()`** — 버전 마이그레이션 때만 쓴다. 그래서 예약된 **빈 값**이
 * 그대로 flush 돼 **첫 로그아웃에 유료 산출물이 영구 소실**됐다(렌더 3,000원/건 · 등기 1,200원/필지).
 *
 * ## ★락 26건이 전부 초록이었다 — 무엇이 빠졌나
 *
 * 소스 문자열로 *"`rehydrate` 를 부른다"* 만 잠갔다. **부른다는 사실이 곧 복원은 아니다.**
 * 재료(순수 함수·소스 배선)는 잠갔는데 **행위를 태우는 단언이 0건**이었다.
 * 이 파일은 실제 스토어 + 실제 `projectSync` 로 **행위**를 태운다.
 *
 * ## ★두 모집단을 가른다 (동료 세션 지적)
 *
 * *"유료 키에 값이 남아 있다"* 만 단언하면 **처음부터 아무것도 안 지우는 구현**도 통과한다.
 * 그래서 같은 실행에서 **와이프 대상 스토어는 실제로 지워지는 것**을 함께 단언한다.
 * 두 모집단이 갈리지 않으면 이 테스트는 아무것도 잠그지 않는다.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/** 서명 검증을 하지 않는 코드용 가짜 JWT — `sub` 만 실어 나른다. */
function fakeToken(sub: string): string {
  return `h.${Buffer.from(JSON.stringify({ sub })).toString("base64")}.s`;
}
function loginAs(sub: string | null): void {
  if (sub === null) window.localStorage.removeItem("propai_access_token");
  else window.localStorage.setItem("propai_access_token", fakeToken(sub));
}
/** 디바운스(기본 500ms) 를 지나 flush 되게 한다. */
const settle = () => new Promise<void>((r) => setTimeout(r, 900));

const PAID = "propai-paid-renders";
const WIPED = "propai-project-context"; // ★음성 대조군 — 이쪽은 실제로 지워져야 한다

/** 모듈 캐시를 비우고 **토큰이 있는 상태에서** 스토어를 하이드레이션한다. */
async function loadModules() {
  vi.resetModules();
  const stores = await import("@/store/usePaidRenderStore");
  const ctx = await import("@/store/useProjectContextStore");
  const sync = await import("@/lib/projectSync");
  return { ...stores, ...ctx, ...sync };
}

beforeEach(() => {
  window.localStorage.clear();
  vi.useRealTimers();
});
afterEach(() => {
  window.localStorage.clear();
});

describe("로그아웃 — 유료 산출물이 살아남는다", () => {
  it("★전제: 구매한 렌더가 계정별 키에 실제로 저장된다(공허한 초록 방지)", async () => {
    loginAs("userA");
    const m = await loadModules();
    m.usePaidRenderStore.getState().add("proj-1", { id: "r1", chargedKrw: 3000, imageUrl: "u" });
    await settle();
    const raw = window.localStorage.getItem(`${PAID}__userA`);
    expect(raw, "저장 자체가 안 됐다 — 이 테스트의 전제가 깨졌다").toBeTruthy();
    expect(raw).toContain("r1");
  });

  it("★★로그아웃해도 **저장분이 남는다** — 사용자가 낸 돈은 사라지지 않는다", async () => {
    loginAs("userA");
    const m = await loadModules();
    m.usePaidRenderStore.getState().add("proj-1", { id: "r1", chargedKrw: 3000, imageUrl: "u" });
    await settle();

    // ★실제 로그아웃 순서 그대로 — 세 호출부 전부 `clearOnLogout()` 이 **토큰 제거보다 먼저**다.
    m.clearOnLogout();
    await settle();

    const raw = window.localStorage.getItem(`${PAID}__userA`);
    expect(raw, "★로그아웃이 유료 산출물을 지웠다 — 3,000원짜리가 사라진다").toBeTruthy();
    expect(raw).toContain("r1");
  });

  it("★음성 대조군 — **와이프 대상은 실제로 지워진다**(두 모집단이 갈린다)", async () => {
    loginAs("userA");
    const m = await loadModules();
    m.useProjectContextStore.setState({ projectName: "지워져야 함" } as never);
    await settle();
    expect(
      window.localStorage.getItem(WIPED),
      "전제: 와이프 대상 스토어가 저장돼 있어야 한다",
    ).toBeTruthy();

    m.clearOnLogout();
    await settle();

    // ★단언은 "키 부재"가 아니라 **"내용이 비워졌다"** 다.
    //   처음엔 `toBeNull()` 로 썼다가 **위양성**을 냈다 — 실측: 와이프는 `removeItem` 을 부르지만
    //   같은 함수의 `setState` 가 예약한 디바운스 쓰기가 그 뒤에 flush 돼 **키가 재생성된다**
    //   (내용은 비워진 채). 즉 원래 계약이 "키가 사라진다"가 아니었다.
    //   **코드를 비틀지 않고 단언을 실제 계약에 맞췄다**(가드의 위양성도 결함이다).
    const wiped = window.localStorage.getItem(WIPED);
    expect(
      wiped ?? "",
      "★와이프 대상에 이전 계정 값이 남았다 — '아무것도 안 지우는 구현'과 구별되지 않는다",
    ).not.toContain("지워져야 함");
  });

  it("로그아웃 뒤 **메모리는 비어 있다** — 격리는 그대로 지킨다", async () => {
    loginAs("userA");
    const m = await loadModules();
    m.usePaidRenderStore.getState().add("proj-1", { id: "r1", chargedKrw: 3000 });
    m.clearOnLogout();
    expect(m.usePaidRenderStore.getState().byProject).toEqual({});
  });
});

describe("세션 만료 후 재로그인 — 쓰기가 조용히 사라지지 않는다", () => {
  it("★`guest` 고착 경로 — 토큰 없이 하이드레이션한 뒤 로그인해도 저장이 **기록된다**", async () => {
    // 세션 만료: 토큰만 지우고 data_owner 는 남긴 채 하드 내비게이션 → 새 페이지는 토큰 없이 하이드레이션
    window.localStorage.setItem("propai_data_owner", "userA");
    loginAs(null);
    const m = await loadModules(); // ← 어댑터 스코프가 `guest` 로 고정된다

    loginAs("userA"); // 같은 계정으로 재로그인(소프트) → owner === uid 라 와이프가 안 돈다
    m.ensureDataOwner(); // ★이 호출이 스코프를 맞춘다(수정 전에는 아무것도 안 했다)

    m.usePaidRenderStore.getState().add("proj-1", { id: "r-new", chargedKrw: 3000 });
    await settle();

    const raw = window.localStorage.getItem(`${PAID}__userA`);
    expect(
      raw,
      "★세션 중 산 3,000원짜리가 **어느 키에도 기록되지 않았다** — 무성 손실",
    ).toBeTruthy();
    expect(raw).toContain("r-new");
  });
});

describe("계정 전환 — 격리와 보존을 동시에", () => {
  it("★B 로 바뀌면 화면엔 A 것이 없고, **A 의 저장분은 온전하다**", async () => {
    loginAs("userA");
    const m = await loadModules();
    m.usePaidRenderStore.getState().add("proj-1", { id: "A-render", chargedKrw: 3000 });
    await settle();

    loginAs("userB");
    m.ensureDataOwner(); // 소유자 불일치 → 와이프 + 스코프 재정렬
    await settle();

    expect(
      JSON.stringify(m.usePaidRenderStore.getState().byProject),
      "★B 화면에 A 의 유료 산출물이 남았다 — 계정 격리 실패",
    ).not.toContain("A-render");

    const rawA = window.localStorage.getItem(`${PAID}__userA`);
    expect(rawA, "★계정 전환이 A 의 유료 산출물을 지웠다").toBeTruthy();
    expect(rawA).toContain("A-render");
  });
});
