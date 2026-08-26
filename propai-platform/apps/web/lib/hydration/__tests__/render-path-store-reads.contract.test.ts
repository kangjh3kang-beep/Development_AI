// @vitest-environment node
/**
 * **파생형 잠금** — 렌더 경로에서 라이브 저장소를 읽는 자리는 0 이어야 한다.
 *
 * 목록형이 아니다: 모집단을 `git ls-files` 로 파생하므로 **새 파일·새 컴포넌트가 자동으로 감시망에
 * 들어온다.** (저장소 교훈: *"목록은 곧 상한이 된다 — 수집은 파생형으로, 판정은 파서로."*)
 *
 * 판정은 **정규식이 아니라 TypeScript AST** 로 한다 — `getState()` 는 이펙트·콜백 안에도 많고
 * (실측 20파일), 그건 렌더 중에 실행되지 않아 **안전**하다. 문자열로 세면 위양성이 쏟아진다.
 *
 * ★이 검사는 **세 축을 따로** 단언한다(하나만 잠그면 나머지가 무잠금이다):
 *   ①모집단 완전성  ②탐지(진짜 위반을 잡는가)  ③특이도(안전한 코드를 안 잡는가)
 */
import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { scanSource } from "@/lib/hydration/render-path-store-reads";

const REPO_FILES = execSync(
  "git ls-files 'components/**/*.tsx' 'components/**/*.ts' 'app/**/*.tsx' 'hooks/**/*.ts' " +
    "'lib/**/*.ts' 'lib/**/*.tsx' 'store/**/*.ts'",
  { encoding: "utf8", maxBuffer: 1 << 26 },
)
  .split("\n")
  .filter((f) => f && !f.includes("__tests__") && !/\.test\.tsx?$/.test(f));

/** 양성 대조군 — 렌더 중 실행되는 네 자리. 하나라도 놓치면 탐지가 죽은 것이다. */
const POSITIVE = `
import { useState, useMemo } from "react";
export function Widget() {
  const [a] = useState(() => useProjectContextStore.getState().siteAnalysis?.parcels ?? []);
  const b = useMemo(() => useProjectStore.getState().projects, []);
  const c = useProjectContextStore.getState().projectId;
  const t = localStorage.getItem("k");
  return null;
}`;
/** 음성 대조군 — 렌더 중 실행되지 않는 자리. 여기서 걸리면 정상 코드를 막는다(위양성도 결함이다). */
const NEGATIVE = `
import { useEffect, useCallback } from "react";
export function Widget2() {
  useEffect(() => { useProjectContextStore.getState().projectId; }, []);
  const h = useCallback(() => localStorage.getItem("k"), []);
  const onClick = () => useProjectStore.getState().projects;
  return null;
}`;

describe("렌더 경로 라이브 저장소 읽기 — 파생형 계약", () => {
  it("①모집단 — 수집이 비면 아래 '0건'은 공허한 참이다", () => {
    expect(REPO_FILES.length).toBeGreaterThan(400);
    expect(REPO_FILES).toContain("components/common/GlobalAddressSearch.tsx");
  });

  it("②탐지 — 렌더 중 실행되는 네 자리를 전부 잡는다", () => {
    const hits = scanSource("POSITIVE.tsx", POSITIVE);
    expect(hits.map((h) => h.via).sort()).toEqual(
      ["component-body", "component-body", "useMemo", "useState-initializer"].sort(),
    );
    expect(hits.filter((h) => h.kind === "localStorage")).toHaveLength(1);
  });

  it("③특이도 — 이펙트·콜백·핸들러 안의 같은 호출은 잡지 않는다", () => {
    expect(scanSource("NEGATIVE.tsx", NEGATIVE)).toEqual([]);
  });

  it("★저장소 전수 — `getState()`·`localStorage` 렌더 읽기 0건(하드 게이트)", () => {
    const hits = REPO_FILES.flatMap((f) => scanSource(f, readFileSync(f, "utf8"))).filter(
      (h) => h.kind !== "store-method",
    );
    const shown = hits.map((h) => `${h.file}:${h.line} [${h.kind}/${h.via}] ${h.text}`).join("\n");
    expect(
      hits,
      "렌더 중 라이브 저장소를 읽으면 서버/클라 첫 렌더가 갈려 React #418(hydration)이 난다.\n" +
        "이펙트(useEffect)나 이벤트 핸들러로 옮겨라 — 셀렉터(useXStore((s) => …))는 안전하다.\n" +
        shown,
    ).toEqual([]);
  });

  /**
   * ── 클래스 ②(스토어 **메서드** 를 렌더 중 호출) 는 **비성장 래칫** 이다 ──
   * 이 형태가 2026-08-13 `LifecycleProgressRail` 사고의 원인이었고, 아래 자리들은 그 뒤로
   * 남아 있던 것이다. ★**이 세션은 이들을 라이브에서 재현하지 않았다 — "미측정" 이다.**
   * 결함이라고 부르지 않는다. 다만 **늘어나지는 않게** 잠근다(#858 린트 래칫과 같은 형태).
   * 각 항목은 실제로 렌더에 값이 실리는지, 그 라우트가 SSR 되는지를 따로 재야 판정된다.
   */
  const STORE_METHOD_RATCHET: ReadonlyArray<string> = [
    "components/cost/BoqAutoWorkspace.tsx:getFieldProvenance",
    "components/feasibility/FeasibilityEditorV2.tsx:isStale",
    "components/feasibility/FeasibilityEditorV2.tsx:feasibilityCompleteness",
    "components/orchestration/OrchestratorPanel.tsx:previewPlan",
    "components/orchestration/OrchestratorPanel.tsx:resolveInputs",
    // ★부분 게이트 — `if (!projectIdProp && !hydrated) return null` 이라 **prop 이 오면 무가드**다.
    //   주석은 `projectId` 가 route param 이라 안전하다고 말하는데, 위험한 것은 그 prop 이 아니라
    //   `getNextRecommendedStage()` 가 읽는 **라이브 스토어**다. ★가장 유력한 다음 후보.
    "components/projects/NextStageCta.tsx:getNextRecommendedStage",
    "components/projects/ProjectHealthBoard.tsx:projectCompleteness",
    "components/projects/ProjectHealthBoard.tsx:getNextRecommendedStage",
    "components/projects/ProjectLifecyclePipeline.tsx:getNextRecommendedStage",
  ];

  it("★클래스 ② — 알려진 자리보다 **늘지 않는다**(비성장 래칫)", () => {
    const hits = REPO_FILES.flatMap((f) => scanSource(f, readFileSync(f, "utf8"))).filter(
      (h) => h.kind === "store-method",
    );
    const key = (h: { file: string; text: string }) => `${h.file}:${h.text.split("(")[0]}`;
    const seen = new Set(hits.map(key));
    const added = [...seen].filter((k) => !STORE_METHOD_RATCHET.includes(k)).sort();
    expect(
      added,
      "렌더 중 스토어 메서드 호출이 **새로 생겼다** — 메서드는 내부에서 `get()`(라이브 상태)을 읽어\n" +
        "zustand 의 서버 스냅샷을 우회한다. `useHydrated()` 게이트 뒤로 옮기거나 셀렉터로 바꿔라.",
    ).toEqual([]);

    // ★죽은 면제도 실패시킨다 — 고쳐 놓고 목록에 남기면 다음 사람이 부채를 과대평가한다.
    const dead = STORE_METHOD_RATCHET.filter((k) => !seen.has(k)).sort();
    expect(dead, "래칫 목록에 **이미 사라진 자리**가 남아 있다 — 목록에서 지워라").toEqual([]);
  });
});
