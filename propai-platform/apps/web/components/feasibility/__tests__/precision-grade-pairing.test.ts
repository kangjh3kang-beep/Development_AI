/**
 * `grade` 와 `precision` 은 **짝이다** — 개략(E) 뒤 정밀 재계산에서 배지가 **거짓으로 남던 것**.
 *
 * ## 무엇이 있었나
 *
 * `updateFeasibilityData` 는 **merge 패치**라 빠뜨린 키가 남는다. 그런데 `precision` 을
 * **비우는 writer 가 전수 0** 이었다(읽는 곳은 `ProjectAnalysisSummary` 한 곳,
 * 조건은 `grade && precision === "E"`).
 *
 *     ① 개략수지 실행      → grade="F", precision="E"   → 배지 "개략(추정) — 설계 미반영" (정직)
 *     ② 정밀 수지 재계산    → grade="A" 만 갱신          → precision 은 "E" 로 **잔존**
 *     ③ 화면                                            → 설계 반영 결과 위에 배지가 **거짓으로** 뜬다
 *
 * `#794` 가 고친 "배지가 안 뜬다"의 **반대 방향**이다.
 *
 * ## 왜 목록·소스 스캔이 아니라 타입인가
 *
 * 이 저장소의 정직성 스윕·파생형 수집기·조건부 타입이 차례로 **`patch.grade = …` 매퍼 형태**를
 * 놓쳤다. 판별 유니온(`FeasibilityPatch`)은 리터럴도 매퍼 대입도 컴파일 타임에 막는다.
 * 이 파일은 그 계약이 **런타임에서도 의도대로 동작하는지**를 태운다(타입은 실행을 안 태운다).
 */
import { beforeEach, describe, expect, it } from "vitest";

import { roughResultToFeasibilityPatch } from "@/components/feasibility/rough-scenario-commit";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import type { FeasibilityData } from "@/store/useProjectContextStore";

describe("grade ↔ precision 짝 계약", () => {
  beforeEach(() => {
    useProjectContextStore.setState({ feasibilityData: {} } as never);
  });

  it("★정밀도를 모르는 엔진이 새 등급을 쓰면 이전 개략치 배지가 사라진다(거짓 잔존 차단)", () => {
    const st = useProjectContextStore.getState();
    // ① 개략수지 — 배지가 떠야 하는 정직한 상태
    st.updateFeasibilityData({ grade: "F", precision: "E", precisionLabel: "개략(추정)" });
    expect(useProjectContextStore.getState().feasibilityData?.precision).toBe("E");

    // ② 정밀도를 산출하지 않는 엔진(정밀 수지·파이프라인·Top3 추천)이 새 등급을 쓴다
    useProjectContextStore.getState().updateFeasibilityData({ grade: "A", precision: null });

    // ③ 배지 조건(grade && precision === "E")이 더는 성립하지 않아야 한다
    const f = useProjectContextStore.getState().feasibilityData;
    expect(f?.grade).toBe("A");
    expect(f?.precision, "이전 개략치의 E 가 남으면 배지가 거짓으로 뜬다").toBeNull();
  });

  it("[양성 대조군] grade 를 안 건드리는 부분 패치는 정밀도를 보존한다(과잉 초기화 금지)", () => {
    const st = useProjectContextStore.getState();
    st.updateFeasibilityData({ grade: "F", precision: "E", precisionLabel: "개략(추정)" });

    // 자기자본만 바꾸는 부분 writer — 정밀도와 무관하다
    useProjectContextStore.getState().updateFeasibilityData({ totalCostWon: 12_345 });

    const f = useProjectContextStore.getState().feasibilityData;
    expect(f?.precision, "무관한 패치가 정밀도를 지우면 #770 이 되살아난다").toBe("E");
    expect(f?.totalCostWon).toBe(12_345);
  });

  it("★매퍼: 백엔드가 정밀도를 주면 그대로 옮긴다", () => {
    const patch = roughResultToFeasibilityPatch({
      summary: { grade: "F", total_cost_won: 100, total_revenue_won: 200 },
      precision: "E",
      precision_label: "개략(추정)",
      precision_basis: "설계 산출물 없이 부지 정보만으로 추정",
    } as never);
    expect(patch?.grade).toBe("F");
    expect(patch?.precision).toBe("E");
  });

  it("★매퍼: 등급은 있는데 백엔드가 정밀도를 안 주면 null 로 **명시**한다(생략하면 옛 값이 남는다)", () => {
    const patch = roughResultToFeasibilityPatch({
      summary: { grade: "F", total_cost_won: 100, total_revenue_won: 200 },
    } as never);
    expect(patch?.grade).toBe("F");
    expect("precision" in (patch ?? {}), "키를 생략하면 merge 패치라 이전 E 가 잔존한다").toBe(true);
    expect(patch?.precision).toBeNull();
  });

  it("★계약 타입 자체를 잠근다 — 유니온이 느슨해지면 tsc 가 실패한다", () => {
    // ★왜 이 형태인가: 변이 검증에서 `FeasibilityPatch` 를 `Partial<FeasibilityData>` 로
    //   되돌리는 변이가 **생존**했다(tsc 0 오류). 계약을 만들어 놓고 그 계약에 결속시키지
    //   않으면 상수가 장식이 된다. `@ts-expect-error` 는 **오류가 사라지면 그 지시자가
    //   '미사용'(TS2578)이 되어** 타입 검사를 빨갛게 만든다 — 양방향 락이다.
    //   ※vitest 는 타입을 보지 않는다. 이 락은 CI 의 `type-check` 단계가 태운다.
    const st = useProjectContextStore.getState();

    // @ts-expect-error grade 만 쓰면 precision 이 빠진다 — 계약이 이걸 막아야 한다(리터럴 경로)
    st.updateFeasibilityData({ grade: "F" });

    const viaMapper: Partial<FeasibilityData> = { grade: "A" };
    // @ts-expect-error 매퍼 경유(변수 대입)도 막아야 한다 — 이 형태가 검출기 셋을 통과했던 것이다
    st.updateFeasibilityData(viaMapper);
  });

  it("[양성 대조군] 등급이 없으면 정밀도 키를 만들지 않는다(기존 SSOT 보존)", () => {
    const patch = roughResultToFeasibilityPatch({
      summary: { total_cost_won: 100, total_revenue_won: 200 },
    } as never);
    expect(patch).not.toBeNull();
    expect("grade" in (patch ?? {})).toBe(false);
    expect("precision" in (patch ?? {}), "등급을 안 쓰면서 정밀도를 지우면 안 된다").toBe(false);
  });
});
