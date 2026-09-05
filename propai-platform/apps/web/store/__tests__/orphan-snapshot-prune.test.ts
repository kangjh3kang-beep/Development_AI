/**
 * 사라진 프로젝트의 스냅샷 정리 — **도달 불가능한 것만** 지운다.
 *
 * ## 왜 (2026-09-05 실측 · 성장루프가 신고한 지연을 추적하다 나왔다)
 *
 * `/api/v1/store/projects` 응답 **3,173,373 bytes** 중 `contextStore.snapshots` 가
 * **2,373,142 bytes**. 라이브 계정 1개에서 **45개 중 24개(1,418,509 · 60%)** 가
 * **이미 존재하지 않는 프로젝트**의 것이었다.
 * `snapshots` 는 `projectSync.ts` 의 `CTX_KEYS` 에 있어 **syncUp/syncDown 마다 왕복**하는데,
 * 쌓는 곳만 있고(`snapshots: { ...state.snapshots, [id]: … }`) **지우는 곳이 없었다.**
 *
 * ## ★임의 상한을 쓰지 않는 이유
 *
 * 「최근 N개 유지」의 N 은 **지어낸 수**이고, 넘긴 **살아 있는** 프로젝트의 스냅샷을 죽인다.
 * 스냅샷은 `snapshots[id]` 로만 읽히므로, 그 id 가 목록에 없으면 **어떤 경로로도 읽히지 않는다**
 * — **도달 불가능한 것**만 정리한다. 그래서 이 처방은 **데이터를 잃지 않는다.**
 *
 * ★상위 호출부는 `useProjectStore.syncFromBackend` 의 **`listComplete` 분기 안**이다.
 *   절단된 목록으로 정리하면 **살아 있는 것을 고아로 오판**한다(`#822` 가 그 전례).
 */
import { readFileSync } from "node:fs";

import { beforeEach, describe, expect, it } from "vitest";

import { useProjectContextStore } from "@/store/useProjectContextStore";

const snap = (tag: string) => ({ siteAnalysis: { address: tag } }) as never;

describe("고아 스냅샷 정리", () => {
  beforeEach(() => {
    useProjectContextStore.setState({
      projectId: null,
      snapshots: { a: snap("A"), b: snap("B"), c: snap("C") },
    } as never);
  });

  it("★두 모집단을 같은 실행에서 가른다 — 고아는 지우고 살아 있는 것은 남긴다", () => {
    useProjectContextStore.getState().pruneOrphanSnapshots(["a", "c"]);
    const s = useProjectContextStore.getState().snapshots;
    expect(Object.keys(s).sort()).toEqual(["a", "c"]);   // 남아야 할 것이 남고
    expect(s.b).toBeUndefined();                          // 지워져야 할 것이 지워진다
  });

  it("★★목록이 비면 아무것도 지우지 않는다 — 「모른다」를 「전부 없다」로 읽지 않는다", () => {
    // 로딩 중·동기화 실패가 이 모양이다. 전멸시키면 원래 결함보다 나쁘다.
    useProjectContextStore.getState().pruneOrphanSnapshots([]);
    expect(Object.keys(useProjectContextStore.getState().snapshots).sort())
      .toEqual(["a", "b", "c"]);
  });

  it("★현재 열려 있는 프로젝트는 목록에 없어도 보존한다(방금 생성 등)", () => {
    useProjectContextStore.setState({ projectId: "b" } as never);
    useProjectContextStore.getState().pruneOrphanSnapshots(["a"]);
    const s = useProjectContextStore.getState().snapshots;
    expect(s.b).toBeDefined();      // 전환 중 자기 스냅샷을 지우면 복원이 깨진다
    expect(s.c).toBeUndefined();    // 음성 대조군 — 그렇다고 전부 남기지는 않는다
  });

  it("지울 것이 없으면 상태 객체를 새로 만들지 않는다(불필요한 리렌더 억제)", () => {
    const before = useProjectContextStore.getState().snapshots;
    useProjectContextStore.getState().pruneOrphanSnapshots(["a", "b", "c"]);
    expect(useProjectContextStore.getState().snapshots).toBe(before);
  });

  it("★undefined·null 이 섞여 와도 살아 있는 것을 죽이지 않는다", () => {
    useProjectContextStore.getState().pruneOrphanSnapshots(
      ["a", undefined as never, null as never, "b"],
    );
    expect(Object.keys(useProjectContextStore.getState().snapshots).sort()).toEqual(["a", "b"]);
  });
});

describe("★배선 — 정리가 실제로 호출되는가", () => {
  /**
   * ★「함수를 만들었다」가 아니라 **「그 함수가 불린다」**를 본다.
   *   이 저장소가 반복해 데인 형태: 정의만 하고 **소비처 0**.
   *   ★그리고 **절단된 목록으로는 부르지 않는다**를 같은 축에서 태운다 —
   *   `#822`(목록 20건 절단)의 전례가 있어, 절단 시 정리하면 **살아 있는 것을 고아로 오판**한다.
   */
  it("syncFromBackend 가 listComplete 분기에서만 정리를 부른다(소스 계약)", () => {
    // ★형제(`feasibility-completeness-wiring.test.tsx`)와 같은 관례 — cwd 기준 상대 경로.
    //   `import.meta.url` 은 이 러너에서 file 스킴이 아니라 못 쓴다(실측).
    const src = readFileSync("store/useProjectStore.ts", "utf-8");
    // 주석·문자열에 뚫리지 않게 **실행 줄**만 본다.
    const code = src
      .split("\n")
      .filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l))
      .join("\n");

    expect(code).toContain("pruneOrphanSnapshots");

    // ★위치 계약: 정리 호출이 `if (listComplete) {` **뒤**, 그 else 분기 **앞**에 있어야 한다.
    const iIf = code.indexOf("if (listComplete)");
    const iCall = code.indexOf("pruneOrphanSnapshots");
    const iElse = code.indexOf("} else {", iIf);
    expect(iIf).toBeGreaterThan(-1);          // ★공허 방지 — 앵커가 사라지면 판정 불가다
    expect(iElse).toBeGreaterThan(iIf);
    expect(iCall).toBeGreaterThan(iIf);
    expect(iCall).toBeLessThan(iElse);        // 절단 분기에서는 부르지 않는다
  });

  it("★정리 대상이 syncUp 이 보내는 키에 실제로 들어 있다(줄어든 것이 나가야 의미가 있다)", () => {
    const src = readFileSync("lib/projectSync.ts", "utf-8");
    const m = src.match(/const CTX_KEYS = \[([\s\S]*?)\]/);
    expect(m).toBeTruthy();                    // ★공허 방지
    expect(m![1]).toContain('"snapshots"');    // 여기서 빠지면 이 PR 의 이득이 0이 된다
  });
});
