/**
 * 유료 산출물 **계정 격리** — 세 축을 따로 잠근다(탐지 · 특이도 · 배선).
 *
 * ## 무엇을 막나
 *
 * `propai-paid-renders`(렌더 3,000원/건) · `propai-registry-analysis`(등기 권리분석
 * 1,200원/필지)는 **지울 수 없는 유료 산출물**이라 계정 격리 와이프에서 면제돼 있었다
 * (`#810` `WIPE_EXEMPT`). 그래서 같은 브라우저의 **다음 계정이 이전 계정의 산출물**
 * (등기 쪽은 **소유자 정보**)을 봤다. 처방은 와이프가 아니라 **계정별 키**다.
 *
 * ## ★판단을 순수 함수로 태운다
 *
 * "현재 위반 0건"인 래칫은 그 자체로 **공허한 참**이 될 수 있다 — 밖에 대상이 없으면
 * 무엇을 넣어도 초록이다. 그래서 귀속 판단(`decideMigration`)을 **합성 입력**으로 직접
 * 태우고, 배선은 배선대로 따로 잠근다.
 */
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { accountScopedKey, currentUserId, GUEST_SCOPE } from "@/lib/account-scope";
import {
  createAccountScopedStorage,
  decideMigration,
  UNATTRIBUTED_BUCKET,
} from "@/lib/account-scoped-storage";
import { __stripCommentsForScan } from "@/lib/source-invariant";
import { migrateOneStore } from "@/lib/paid-artifact-migration";

const WEB_ROOT = join(__dirname, "..", "..");

/** 서명 검증을 하지 않는 코드용 가짜 JWT — `sub` 만 실어 나른다. */
function fakeToken(sub: string): string {
  const b64 = Buffer.from(JSON.stringify({ sub })).toString("base64");
  return `h.${b64}.s`;
}
function loginAs(sub: string | null): void {
  if (sub === null) window.localStorage.removeItem("propai_access_token");
  else window.localStorage.setItem("propai_access_token", fakeToken(sub));
}

beforeEach(() => {
  window.localStorage.clear();
});

// ── 축 ① 탐지 — 귀속 판단이 실제로 갈린다 ──────────────────────────────
describe("귀속 판단 — 합성 입력으로 직접 태운다", () => {
  const legacy = {
    "proj-A": [{ id: "r1" }],
    "proj-B": [{ id: "r2" }],
    [UNATTRIBUTED_BUCKET]: [{ id: "r3" }],
  };

  it("★전제: 대조군이 통과한다 — 보이는 프로젝트는 실제로 승계된다(공허한 초록 방지)", () => {
    const d = decideMigration({
      legacy,
      owned: {},
      visibleProjectIds: new Set(["proj-A"]),
      truncated: false,
    });
    expect(d.action).toBe("migrate");
    if (d.action !== "migrate") return;
    expect(d.adopted).toEqual(["proj-A"]);
    expect(d.merged["proj-A"]).toEqual([{ id: "r1" }]);
  });

  it("안전장치 3 — 목록이 **절단**이면 미룬다(불완전한 목록으로 귀속하면 본인 것이 사라진다)", () => {
    const d = decideMigration({
      legacy,
      owned: {},
      visibleProjectIds: new Set(["proj-A"]),
      truncated: true,
    });
    expect(d).toEqual({ action: "defer", reason: "truncated" });
  });

  it("안전장치 3 — 목록이 **비었으면** 미룬다", () => {
    const d = decideMigration({
      legacy,
      owned: {},
      visibleProjectIds: new Set<string>(),
      truncated: false,
    });
    expect(d).toEqual({ action: "defer", reason: "no-projects" });
  });

  it("안전장치 2 — `_default` 는 **추측하지 않는다**(프로젝트 없이 만든 산출물)", () => {
    const d = decideMigration({
      legacy,
      owned: {},
      visibleProjectIds: new Set(["proj-A", UNATTRIBUTED_BUCKET]),
      truncated: false,
    });
    expect(d.action).toBe("migrate");
    if (d.action !== "migrate") return;
    // ★목록에 `_default` 를 일부러 넣어도 승계되지 않는다 — 버킷 이름이 우연히 겹쳐도 안 된다.
    expect(d.adopted).not.toContain(UNATTRIBUTED_BUCKET);
    expect(d.merged[UNATTRIBUTED_BUCKET]).toBeUndefined();
    expect(d.left).toContainEqual({ bucket: UNATTRIBUTED_BUCKET, reason: "unattributable" });
  });

  it("★핵심 — **안 보이는 프로젝트는 남의 것**이라 가져오지 않는다(이게 격리 자체다)", () => {
    const d = decideMigration({
      legacy,
      owned: {},
      visibleProjectIds: new Set(["proj-A"]),
      truncated: false,
    });
    expect(d.action).toBe("migrate");
    if (d.action !== "migrate") return;
    expect(d.merged["proj-B"]).toBeUndefined();
    expect(d.left).toContainEqual({ bucket: "proj-B", reason: "not-visible" });
  });

  it("현행이 있으면 **덮지 않는다** — 레거시로 덮으면 방금 산 것이 옛것으로 되돌아간다", () => {
    const d = decideMigration({
      legacy,
      owned: { "proj-A": [{ id: "fresh" }] },
      visibleProjectIds: new Set(["proj-A"]),
      truncated: false,
    });
    expect(d.action).toBe("noop");
    if (d.action !== "noop") return;
    expect(d.reason).toBe("nothing-owned");
  });

  it("레거시가 없으면 noop — 빈 배열 버킷도 레거시로 세지 않는다", () => {
    expect(
      decideMigration({ legacy: null, owned: {}, visibleProjectIds: new Set(["a"]), truncated: false }),
    ).toEqual({ action: "noop", reason: "no-legacy" });
    expect(
      decideMigration({ legacy: { a: [] }, owned: {}, visibleProjectIds: new Set(["a"]), truncated: false }),
    ).toEqual({ action: "noop", reason: "no-legacy" });
  });

  it("멱등 — 두 번 돌려도 같은 결과이고 두 번째는 아무것도 안 옮긴다", () => {
    let owned: Record<string, unknown[]> = {};
    const run = () =>
      migrateOneStore({
        store: "t", legacyKey: "t", owned,
        visibleProjectIds: new Set(["proj-A"]), truncated: false,
        commit: (m) => { owned = m; },
        readLegacy: () => legacy,
      });
    expect(run().action).toBe("migrate");
    const second = run();
    expect(second.action).toBe("noop");
    expect(owned["proj-A"]).toEqual([{ id: "r1" }]);
  });
});

// ── 축 ② 배선 — 어댑터가 실제로 계정별 키를 쓴다 ────────────────────────
describe("계정별 저장소 어댑터", () => {
  it("★쓰기가 `<base>__<uid>` 로 간다 — 레거시 공유키에는 쓰지 않는다", () => {
    loginAs("userA");
    const st = createAccountScopedStorage<{ v: number }>(0);
    st.setItem("propai-demo", { state: { v: 1 }, version: 0 });
    // 디바운스(0ms)를 지나 flush 되도록 이벤트 루프를 한 번 돌린다.
    return new Promise<void>((r) => setTimeout(r, 5)).then(() => {
      expect(window.localStorage.getItem(accountScopedKey("propai-demo", "userA"))).toBeTruthy();
      expect(window.localStorage.getItem("propai-demo")).toBeNull();
    });
  });

  it("★두 계정이 **서로의 것을 못 본다**(격리 종단)", async () => {
    loginAs("userA");
    const a = createAccountScopedStorage<{ v: number }>(0);
    a.setItem("propai-demo", { state: { v: 111 }, version: 0 });
    await new Promise((r) => setTimeout(r, 5));

    loginAs("userB");
    const b = createAccountScopedStorage<{ v: number }>(0);
    expect(b.getItem("propai-demo")).toBeNull(); // B 는 A 의 것을 못 읽는다
    b.setItem("propai-demo", { state: { v: 222 }, version: 0 });
    await new Promise((r) => setTimeout(r, 5));

    // ★A 의 것이 **살아 있다** — 격리가 곧 삭제여서는 안 된다(유료 산출물이다).
    const rawA = window.localStorage.getItem(accountScopedKey("propai-demo", "userA"));
    expect(rawA).toContain("111");
    expect(window.localStorage.getItem(accountScopedKey("propai-demo", "userB"))).toContain("222");
  });

  it("★교차계정 쓰기 차단 — 하이드레이션 후 계정이 바뀌면 **쓰지 않는다**", async () => {
    loginAs("userA");
    const st = createAccountScopedStorage<{ v: number }>(0);
    st.getItem("propai-demo"); // A 로 하이드레이션
    loginAs("userB"); // 새로고침 없이 계정 전환(SPA)
    st.setItem("propai-demo", { state: { v: 999 }, version: 0 }); // 메모리엔 아직 A 의 상태
    await new Promise((r) => setTimeout(r, 5));
    // A 의 데이터가 B 의 키로 복사되면 안 된다 — 그게 이 파일이 막으려는 누출이다.
    expect(window.localStorage.getItem(accountScopedKey("propai-demo", "userB"))).toBeNull();
  });

  it("비로그인은 `guest` 스코프이고, 로그인 사용자와 **키가 갈린다**", () => {
    loginAs(null);
    expect(currentUserId()).toBe(GUEST_SCOPE);
    expect(accountScopedKey("propai-demo")).not.toBe(accountScopedKey("propai-demo", "userA"));
  });
});

// ── 축 ③ 배선 락 — 스토어가 스코프를 우회하지 못한다 ───────────────────
describe("배선 락 — 유료 산출물 스토어는 계정 스코프를 우회할 수 없다", () => {
  const STORES = [
    "store/usePaidRenderStore.ts",
    "store/useRegistryAnalysisStore.ts",
    "store/useDevelopmentPlanStore.ts",
  ] as const;

  it("★전제: 검사 대상 파일을 실제로 읽었다(공허한 초록 방지)", () => {
    for (const f of STORES) {
      const src = readFileSync(join(WEB_ROOT, f), "utf8");
      expect(src.length, `${f} 를 못 읽었다`).toBeGreaterThan(500);
      expect(src, `${f} 가 persist 스토어가 아니다 — 검사 전제가 깨졌다`).toContain("persist(");
    }
  });

  it("두 스토어는 `createAccountScopedStorage` 를 쓰고, 스코프 없는 저장소를 **직접 쓰지 않는다**", () => {
    for (const f of STORES) {
      // ★주석은 공용 헬퍼로 걷는다 — 손으로 짜면 JSX/블록 주석에 뚫린다.
      const src = __stripCommentsForScan(readFileSync(join(WEB_ROOT, f), "utf8"), f);
      // ★임포트 존재만 보면 안 된다 — `storage: undefined` 로 바꿔도 임포트는 남아 통과한다
      //   (적대 리뷰가 실측한 생존 변이). 잠가야 할 것은 **`persist(` 옵션의 `storage:` 값**이다.
      expect(
        src,
        `${f}: persist 의 storage 옵션이 계정 스코프 저장소가 아니다 — 임포트만 남기고 배선을 바꾸면 격리가 통째로 우회된다`,
      ).toMatch(/storage:\s*createAccountScopedStorage\s*</);
      expect(
        src,
        `${f}: 스코프 없는 createDebouncedStorage 를 직접 쓴다 — 계정 격리가 우회된다`,
      ).not.toContain("createDebouncedStorage");
    }
  });

  // ★부채를 초록 안에서 보이게 남긴다(커밋 메시지에만 적으면 안 드러난다 · 규율 C-13).
  //   `migratePaidArtifacts` 가 승계 사유를 돌려주는데 **호출부가 버린다** — `defer` 일 때
  //   레거시의 유료 산출물이 화면에 안 보이면서 이유도 없다(데이터는 안 사라진다).
  //   통로가 둘 다 범위를 넘는다: 성장루프 이벤트는 백엔드 화이트리스트와 **같은 커밋** 필요 ·
  //   사용자 고지는 **제품 판단**. 잡을 때 이 todo 를 실제 케이스로 바꾼다.
  it.todo("승계 사유(defer/noop)가 화면이나 계측 중 한 곳에는 도달한다");

  it("★음성 대조군 — 스코프가 **필요 없는** 스토어는 종전 저장소를 그대로 쓴다(무차별 치환 배제)", () => {
    // 와이프 목록에 든 스토어는 계정 전환 때 지워지므로 계정별 키가 필요 없다.
    // 이 케이스가 없으면 "전부 계정 스코프로 바꿔라" 라는 과잉 규칙과 구별되지 않는다.
    const src = __stripCommentsForScan(
      readFileSync(join(WEB_ROOT, "store/useLandScheduleStore.ts"), "utf8"),
      "store/useLandScheduleStore.ts",
    );
    expect(src).toContain("createDebouncedStorage");
    expect(src).not.toContain("createAccountScopedStorage");
  });

  it("★계정 전환이 유료 스토어의 **메모리 상태**를 갈아 끼운다 — 없으면 화면에 이전 계정 것이 남는다", () => {
    const src = __stripCommentsForScan(
      readFileSync(join(WEB_ROOT, "lib/projectSync.ts"), "utf8"),
      "lib/projectSync.ts",
    );
    // ★창에 **끝 경계**를 준다. 종전엔 `slice(indexOf(...))` 라 **파일 끝까지**(19,723자) 먹어
    //   `ensureDataOwner`·`syncDown` 이 전부 창 안이었고, 호출을 뒤쪽 아무 함수로 옮겨도
    //   락이 초록이었다(적대 리뷰 실측). CLAUDE.md 「파서 창이 인접 표를 침범」의 재발이다.
    const start = src.indexOf("export function clearAllProjectData");
    expect(start, "clearAllProjectData 를 못 찾았다 — 검사가 죽었다").toBeGreaterThan(-1);
    const rest = src.slice(start + 1);
    const endRel = rest.search(/\nexport (?:async )?function |\n(?:async )?function /);
    const wipe = endRel === -1 ? rest : rest.slice(0, endRel);
    expect(wipe.length, "창이 비정상적으로 작다 — 경계 정규식이 즉시 매치했다").toBeGreaterThan(200);
    // ★창이 함수 밖으로 새지 않는지 대조군으로 확인한다(공허/과대 둘 다 막는다).
    expect(wipe, "창이 다음 함수까지 먹었다 — 끝 경계가 안 걸렸다").not.toContain(
      "export function ensureDataOwner",
    );
    // ★2026-09-04(#965 적대 리뷰 Finding 1) — **목록형이었고 실제로 빠졌다.**
    //   네 번째 계정별 스토어(`useSatongMapPrefs`)가 이 목록에 없어 소프트 계정 전환 후
    //   ①이전 계정의 값을 그대로 보여 주고 ②새 계정의 변경을 **어느 키에도 안 쓰는**
    //   상태가 됐다(리뷰가 실행으로 실증). 목록이 3에 고정돼 있었기 때문이다.
    //   → **파생형**으로 바꾼다. `store/**` 에서 계정별 어댑터를 쓰는 스토어를 모두 모아
    //     그 훅 이름이 와이프 창에 있는지 본다. 다섯 번째가 생기면 **자동으로** 걸린다.
    const STORES3 = accountScopedStoreHooks();
    // 공허 방지 — 모집단이 실재한다(현재 4개).
    // ★**하한이 아니라 등식**이다(2차 리뷰 MAJOR-2). 하한이면 다섯 번째가 수집기의
    //   사각지대 형태로 들어와도 4 에 머물러 **조용히 통과**한다.
    //   교차검증: 어댑터를 쓰는 **파일 수**와 뽑은 **훅 수**가 같아야 한다(한 파일 한 스토어 가정이
    //   깨지면 위 `matchAll` 이 더 뽑으므로 그때는 이 단언이 시끄럽게 실패해 재검토를 강제한다).
    expect(STORES3.length, "계정별 스토어를 하나도 못 모았다 — 수집기가 죽었다").toBe(
      accountScopedStoreFileCount(),
    );
    expect(STORES3.length, "모집단이 비었다 — 수집기가 죽었다").toBeGreaterThanOrEqual(4);

    // ★계약이 바뀌었다(2026-08-26 회귀 봉합). 리셋은 **쓰기 정지 창 안**에서 하고,
    //   복원은 여기가 아니라 `syncAccountScopedStores()` 가 한다.
    expect(
      wipe,
      "리셋이 쓰기 정지 창 밖에 있다 — persist 가 **빈 값을 계정 키에 기록**해 유료 산출물이 지워진다",
    ).toContain("withWritesSuspended(");
    for (const store of STORES3) {
      expect(wipe, `${store}: 계정 전환 시 메모리 상태를 안 비운다`).toContain(
        `${store}.setState`,
      );
      // ★여기서 복원하면 **로그아웃 경로에서 이전 계정 것을 되살린다.** 복원은 다른 함수 몫이다.
      expect(
        wipe,
        `${store}: clearAllProjectData 안에서 복원하면 로그아웃이 이전 계정 데이터를 되살린다`,
      ).not.toContain(`${store}.persist?.rehydrate()`);
    }

    // ★복원은 **소유자 일치와 무관하게** 도는 자리에 있어야 한다(`guest` 스코프 고착 경로).
    const sIdx = src.indexOf("export function syncAccountScopedStores");
    expect(sIdx, "syncAccountScopedStores 가 없다 — 복원 경로가 통째로 사라졌다").toBeGreaterThan(-1);
    const sRest = src.slice(sIdx + 1);
    const sEnd = sRest.search(/\nexport (?:async )?function |\n(?:async )?function /);
    const syncFn = sEnd === -1 ? sRest : sRest.slice(0, sEnd);
    for (const store of STORES3) {
      expect(syncFn, `${store}: 계정이 바뀌어도 복원하지 않는다`).toContain(
        `${store}.persist?.rehydrate()`,
      );
    }
    const owner = src.slice(src.indexOf("export function ensureDataOwner"));
    expect(
      owner,
      "ensureDataOwner 가 스코프를 안 맞춘다 — 세션 만료 후 재로그인에서 쓰기가 무성으로 사라진다",
    ).toContain("syncAccountScopedStores()");
  });

  it("★레거시 공유키를 **지우지 않는다** — 와이프 목록에 넣으면 사용자가 낸 돈이 사라진다", () => {
    const src = __stripCommentsForScan(
      readFileSync(join(WEB_ROOT, "lib/projectSync.ts"), "utf8"),
      "lib/projectSync.ts",
    );
    const list = src.slice(
      src.indexOf("const PROJECT_PERSIST_KEYS"),
      src.indexOf("const PROJECT_PERSIST_PREFIXES"),
    );
    expect(list.length, "와이프 목록을 못 찾았다 — 검사가 죽었다").toBeGreaterThan(50);
    expect(list, "대조군: 지워야 하는 키는 실제로 목록에 있다").toContain("propai-project-context");
    for (const legacy of ["propai-paid-renders", "propai-registry-analysis", "propai-development-plan"]) {
      expect(list, `${legacy} 가 와이프 목록에 들어갔다 — 유료 산출물 원본이 삭제된다`).not.toContain(
        legacy,
      );
    }
  });
});

// ── 축 ④ 파생형 커버리지 — **다음 스토어가 또 조용히 빠지지 않게** ──────────
//
// 이 결함의 근본은 "propai-paid-renders 를 깜빡했다"가 아니다. **선언한 커버리지와 실제
// 커버리지가 갈리는데 아무것도 그것을 잠그지 않는다**는 것이다(실측: 와이프 접두는 전부
// 언더바 `propai_*` 인데 두 유료 키는 하이픈 `propai-*` 이라 어디에도 안 걸렸다).
// 목록형으로 적으면 **다음에 생기는 persist 스토어가 또 빠진다** — 그래서 소스에서 파생한다.
//
// ★파생의 축을 명시한다: **`store/**` 의 `persist(` 를 쓰는 파일 전수**다.
//   `components/**` 에서 직접 localStorage 를 쓰는 키는 이 축 밖이고,
//   그쪽은 `persist-key-coverage.test.ts` 가 본다(미측정이라고 적지 않는다 — 형제가 덮는다).
/**
 * `store/**` 에서 **계정별 저장 어댑터를 쓰는** 스토어의 **훅 이름**을 파생 수집한다.
 * ★목록형이 아니어야 하는 이유: 2026-09-04 에 네 번째 스토어가 손목록에서 빠져
 *   소프트 계정 전환이 조용히 깨졌다(#965 리뷰 Finding 1).
 */
function accountScopedStoreHooks(): string[] {
  const dir = join(WEB_ROOT, "store");
  const out: string[] = [];
  for (const f of readdirSync(dir)) {
    if (!f.endsWith(".ts") || f.endsWith(".test.ts")) continue;
    const src = __stripCommentsForScan(readFileSync(join(dir, f), "utf8"), `store/${f}`);
    // ★제네릭 유무를 가리지 않는다 — `createAccountScopedStorage()` 도 계정별이다.
    if (!/createAccountScopedStorage\s*[<(]/.test(src)) continue;
    // 훅 이름. ★`matchAll` — 한 파일에 스토어가 둘이면 첫 것만 집던 결함(2차 리뷰 MAJOR-2).
    //   ★그리고 여러 export 형태를 본다: `export const useX = create` ·
    //     `export const useX: T = create` · `const useX = create` + `export { useX }`.
    const names = hookNamesFrom(src);
    // ★**계정별이라고 분류해 놓고 이름을 못 뽑으면 조용히 흘리지 않는다**(2차 리뷰 MAJOR-2:
    //   초판은 `if (m) out.push(...)` 라 **else 가 없었다** — 분류된 파일이 소리 없이 사라졌고,
    //   하한 가드가 «>= 4» 라 다섯 번째가 그 형태면 4 에 머물러 통과했다).
    if (names.length === 0) {
      throw new Error(
        `${f}: 계정별 저장 어댑터를 쓰는데 훅 이름을 못 뽑았다 — 수집기가 이 형태를 모른다. ` +
          "조용히 흘리면 이 락이 그 스토어를 영영 안 본다(§목록은 곧 상한).",
      );
    }
    out.push(...names);
  }
  return out.sort();
}

/**
 * ★수집기의 **형태 인식**을 합성 입력으로 잠근다(2026-09-04 · 2차 리뷰 MAJOR-2).
 *   경화(throw·matchAll·여러 export 형태)는 **다섯 번째 스토어가 실재해야** 변이로 잡힌다 —
 *   지금은 없으므로 그 경화가 «설명 가능한 생존» 이 된다. 그래서 **패턴 자체**를 태운다.
 *   `hookNamesFrom` 은 수집기와 **같은 정규식**을 쓴다(두 곳에 적으면 갈린다).
 */
export function hookNamesFrom(src: string): string[] {
  return [
    ...src.matchAll(/export const (use[A-Za-z0-9_]*)\s*(?::[^=]+)?=\s*create/g),
    ...src.matchAll(/^const (use[A-Za-z0-9_]*)\s*(?::[^=]+)?=\s*create/gm),
  ].map((m) => m[1]);
}

/** 계정별 어댑터를 쓰는 **파일 수** — 위 수집기와 **다른 경로**로 센다(교차검증용). */
function accountScopedStoreFileCount(): number {
  const dir = join(WEB_ROOT, "store");
  let n = 0;
  for (const f of readdirSync(dir)) {
    if (!f.endsWith(".ts") || f.endsWith(".test.ts")) continue;
    const src = __stripCommentsForScan(readFileSync(join(dir, f), "utf8"), `store/${f}`);
    if (/createAccountScopedStorage\s*[<(]/.test(src)) n += 1;
  }
  return n;
}

describe("★수집기의 형태 인식 — 합성 입력으로 잠근다(2차 리뷰 MAJOR-2)", () => {
  it("A 표준형", () => {
    expect(hookNamesFrom('export const useA = create<S>()(persist(...))')).toEqual(["useA"]);
  });
  it("★B 타입 주석형 — 초판이 놓치던 형태", () => {
    expect(hookNamesFrom('export const useB: UseBoundStore<S> = create(...)')).toEqual(["useB"]);
  });
  it("★C 나중 export 형 — 초판이 놓치던 형태", () => {
    expect(hookNamesFrom('const useC = create<S>()(...)\nexport { useC };')).toEqual(["useC"]);
  });
  it("★D 한 파일 두 스토어 — 초판은 첫 것만 집었다", () => {
    expect(
      hookNamesFrom('export const useD1 = create(...)\nexport const useD2 = create(...)'),
    ).toEqual(["useD1", "useD2"]);
  });
  it("★음성 대조군 — create 가 아닌 것은 안 집는다", () => {
    expect(hookNamesFrom('export const useNot = something(...)')).toEqual([]);
    expect(hookNamesFrom('const helper = create(...)')).toEqual([]); // use 접두가 아니다
  });
});

describe("파생형 — 모든 persist 스토어는 **와이프되거나 계정별이거나** 둘 중 하나다", () => {
  type StoreInfo = { file: string; key: string | null; scoped: boolean };

  function collectPersistStores(): StoreInfo[] {
    const dir = join(WEB_ROOT, "store");
    const out: StoreInfo[] = [];
    for (const f of readdirSync(dir)) {
      if (!f.endsWith(".ts") || f.endsWith(".test.ts")) continue;
      const src = __stripCommentsForScan(readFileSync(join(dir, f), "utf8"), `store/${f}`);
      if (!/\bpersist\s*\(/.test(src)) continue;
      // ★**첫 `name:` 을 집으면 안 된다** — 스토어 파일에는 persist 옵션과 무관한 `name:`
      //   필드가 먼저 나올 수 있다(실측: 4개 파일에서 엉뚱한 값을 집어 "이름 없음"이 됐다.
      //   내 탐지기가 만든 위양성이다). 전부 훑어 **`propai` 네임스페이스인 것**만 고른다.
      let key: string | null = null;
      // ★따옴표 종류를 가리지 않는다 — 처음엔 큰따옴표만 봐서 `name: 'propai-...'` 를 쓰는
      //   두 스토어를 "이름 없음"으로 흘렸다(내 탐지기가 만든 두 번째 위양성).
      for (const m of src.matchAll(/name:\s*(?:["']([^"']+)["']|([A-Za-z_$][\w$]*))/g)) {
        let v: string | null = m[1] ?? null;
        if (!v && m[2]) {
          // 식별자면 같은 파일의 리터럴 선언에서 값을 찾는다(손으로 적지 않는다).
          v = src.match(new RegExp(`${m[2]}\\s*=\\s*["']([^"']+)["']`))?.[1] ?? null;
        }
        if (v?.startsWith("propai")) { key = v; break; }
      }
      out.push({ file: `store/${f}`, key, scoped: src.includes("createAccountScopedStorage") });
    }
    return out;
  }

  const stores = collectPersistStores();
  const syncSrc = __stripCommentsForScan(
    readFileSync(join(WEB_ROOT, "lib", "projectSync.ts"), "utf8"),
    "lib/projectSync.ts",
  );
  const wipeList = syncSrc.slice(
    syncSrc.indexOf("const PROJECT_PERSIST_KEYS"),
    syncSrc.indexOf("const PROJECT_PERSIST_PREFIXES"),
  );

  it("★수집기가 살아 있다 — 아는 스토어가 실제로 잡힌다(전수 0건이 초록이 되지 않게)", () => {
    expect(stores.length, "persist 스토어를 하나도 못 모았다 — 수집기가 죽었다").toBeGreaterThan(3);
    const keys = stores.map((s) => s.key);
    expect(keys, "대조군: 와이프 대상 스토어").toContain("propai-land-schedule");
    expect(keys, "대조군: 계정별 스토어").toContain("propai-paid-renders");
    expect(stores.every((s) => s.key !== null), `이름을 못 뽑은 스토어: ${
      stores.filter((s) => !s.key).map((s) => s.file).join(", ")
    }`).toBe(true);
  });

  it("★양쪽 모집단이 실제로 갈린다 — 한쪽이 비면 이 검사는 공허하다", () => {
    expect(stores.filter((s) => s.scoped).length, "계정별 스토어가 0개").toBeGreaterThan(0);
    expect(stores.filter((s) => !s.scoped).length, "비계정별 스토어가 0개").toBeGreaterThan(0);
  });

  /**
   * ★**미트리아지 래칫** — 늘어나면 실패한다(줄이는 방향으로만 움직인다).
   *
   * 이 락을 켜자마자 드러난 것이다. **처방이 갈려서** 급히 못 정한다:
   *  · **와이프**하면 계정 전환마다 사용자가 만든 **커스텀 워크플로 프로필이 사라진다**
   *  · **계정별 키**로 바꾸면 기존 공유키 저장분에 **마이그레이션**이 필요하고, 그 귀속
   *    재료(`customProfiles` 는 프로젝트별이 아니다)가 유료 산출물 쪽과 다르다
   *
   * 누출 자체는 실재한다(같은 브라우저의 다음 계정이 이전 계정의 프로젝트별 실행상태를
   * 본다). 다만 **유료·비가역 산출물이 아니고** 개인정보도 아니라, 근거 없이 한쪽으로
   * 밀면 사용자 데이터를 지우거나 격리를 깬다(`#810` 이 같은 이유로 미분류를 남긴 선례).
   * ★**"미수정"이지 "무잠금"이 아니다** — 여기 적혀 있어 다음 사람이 초록 안에서 본다.
   */
  const UNTRIAGED_STORES: Record<string, string> = {
    "propai-orchestration":
      "★부채 · 처방 미정(와이프하면 커스텀 프로필 소실 · 계정별 키로 바꾸면 마이그레이션 귀속 재료가 없다). 누출은 실재하나 유료·비가역 산출물이 아니다",
  };

  it("★미트리아지 래칫은 늘어나지 않고, **죽은 항목도 막는다**", () => {
    const keys = new Set(stores.map((s) => s.key));
    const stale = Object.keys(UNTRIAGED_STORES).filter((k) => !keys.has(k));
    expect(stale, `소스에 없는 미트리아지 스토어가 남아 있다: ${stale.join(", ")}`).toEqual([]);
    for (const [k, why] of Object.entries(UNTRIAGED_STORES)) {
      expect(why.length, `${k} 의 사유가 너무 짧다 — 부채를 뭉뚱그리지 마라`).toBeGreaterThan(20);
    }
  });

  it("★계정별이 아닌 persist 스토어는 **와이프 목록에 있어야 한다**", () => {
    const uncovered = stores
      .filter(
        (s) =>
          !s.scoped &&
          s.key &&
          !wipeList.includes(`"${s.key}"`) &&
          !(s.key in UNTRIAGED_STORES),
      )
      .map((s) => `${s.file}(${s.key})`);
    expect(
      uncovered,
      "계정 전환 때 지워지지도 않고 계정별로 갈리지도 않는 persist 스토어 — " +
        "같은 브라우저의 다음 계정이 이전 계정 데이터를 본다.\n" +
        "→ 지워도 되면 PROJECT_PERSIST_KEYS 에, 지우면 안 되는 산출물이면 " +
        "createAccountScopedStorage 로 계정별 키를 주라.",
    ).toEqual([]);
  });
});
