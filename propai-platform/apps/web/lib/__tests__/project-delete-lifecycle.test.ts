/**
 * 프로젝트를 지워도 **되살아나던 것** — 삭제 생명주기 트리거.
 *
 * ## 무엇이 있었나(실측)
 *
 * `deleteProject` 는 프로젝트 **목록에서만** 지웠다. 남는 것:
 *   · `useProjectContextStore.snapshots[id]` — 삭제 액션이 **전 코드베이스에 0건**
 *     (`snapshots` 참조 14건 중 지우는 곳 없음 · 대조군으로 조회기 검증함)
 *   · `useLandScheduleStore.byProject[id]`
 *   · 활성 `projectId` 가 지워진 프로젝트를 가리킨 채로 잔존
 *
 * ★`snapshots` 는 `CTX_KEYS` 라 **매 syncUp 마다 서버 blob 으로 재업로드**된다 →
 *   다음 `syncDown` 이 다시 내려 준다. **삭제가 동기화로 되돌려진다.**
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { purgeProjectLocalData } from "@/lib/project-lifecycle";
import { __stripCommentsForScan } from "@/lib/source-invariant";
import { useLandScheduleStore } from "@/store/useLandScheduleStore";
import { useProjectContextStore } from "@/store/useProjectContextStore";

const A = "aaaaaaaa-1111-4111-8111-111111111111";
const B = "bbbbbbbb-2222-4222-8222-222222222222";

function seed(activeId: string | null) {
  useProjectContextStore.setState({
    projectId: activeId,
    projectName: activeId ? "테스트" : "",
    siteAnalysis: activeId ? ({ address: "서울특별시 동작구 상도동 1" } as never) : null,
    snapshots: { [A]: { siteAnalysis: { address: "A 분석" } }, [B]: { siteAnalysis: { address: "B 분석" } } },
  } as never);
  useLandScheduleStore.setState({
    byProject: { [A]: [{ id: "r1" }], [B]: [{ id: "r2" }] },
  } as never);
}

describe("삭제 생명주기 — 지운 프로젝트가 되살아나지 않는다", () => {
  beforeEach(() => seed(A));

  it("★분석 스냅샷을 지운다 — 남으면 syncUp 이 서버로 다시 올리고 syncDown 이 되돌린다", () => {
    const r = purgeProjectLocalData(A);
    expect(r.snapshotRemoved).toBe(true);
    const snaps = useProjectContextStore.getState().snapshots as Record<string, unknown>;
    expect(A in snaps, "지운 프로젝트의 분석이 남았다").toBe(false);
    expect(B in snaps, "남의 프로젝트까지 지웠다 — 과삭제").toBe(true);
  });

  it("★토지조서도 함께 지운다", () => {
    const r = purgeProjectLocalData(A);
    expect(r.landScheduleRemoved).toBe(true);
    const by = useLandScheduleStore.getState().byProject as Record<string, unknown>;
    expect(A in by).toBe(false);
    expect(B in by, "남의 토지조서까지 지웠다").toBe(true);
  });

  it("★활성 프로젝트를 지우면 컨텍스트도 비운다 — 존재하지 않는 프로젝트를 가리킨 채 두지 않는다", () => {
    const r = purgeProjectLocalData(A);
    expect(r.activeContextCleared).toBe(true);
    const st = useProjectContextStore.getState();
    expect(st.projectId).toBeNull();
    expect(st.siteAnalysis, "지운 프로젝트의 분석이 화면에 남는다").toBeNull();
  });

  it("[양성 대조군] 활성이 아닌 프로젝트를 지우면 현재 작업은 그대로 둔다", () => {
    const r = purgeProjectLocalData(B);
    expect(r.snapshotRemoved).toBe(true);
    expect(r.activeContextCleared, "무관한 삭제가 현재 작업을 날렸다").toBe(false);
    const st = useProjectContextStore.getState();
    expect(st.projectId).toBe(A);
    expect(st.siteAnalysis).not.toBeNull();
  });

  it("★멱등하다 — 없는 것을 지워도 아무것도 바꾸지 않는다", () => {
    const before = JSON.stringify(useProjectContextStore.getState().snapshots);
    const r = purgeProjectLocalData("does-not-exist");
    expect(r).toEqual({ snapshotRemoved: false, landScheduleRemoved: false, activeContextCleared: false });
    expect(JSON.stringify(useProjectContextStore.getState().snapshots)).toBe(before);
  });

  it("★빈 id 는 무시한다 — 실수로 전체를 날리지 않는다", () => {
    const r = purgeProjectLocalData("");
    expect(r.snapshotRemoved).toBe(false);
    const snaps = useProjectContextStore.getState().snapshots as Record<string, unknown>;
    expect(Object.keys(snaps)).toHaveLength(2);
  });

  it("★★실제로 **배선돼 있다** — 함수만 있고 삭제가 안 부르면 아무것도 안 지워진다", () => {
    const src = __stripCommentsForScan(
      readFileSync(join(__dirname, "..", "..", "store", "useProjectStore.ts"), "utf8"),
      "store/useProjectStore.ts",
    );
    expect(src.length, "대상 파일을 못 읽었다").toBeGreaterThan(500);
    expect(src, "deleteProject 가 생명주기 트리거를 부르지 않는다").toContain(
      "purgeProjectLocalData(id)",
    );
  });
});
