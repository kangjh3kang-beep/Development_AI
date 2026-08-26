// @vitest-environment node
/**
 * **파생형 잠금** — 렌더 경로에서 라이브 저장소를 읽는 자리가 **늘지 않는다**.
 *
 * 목록형이 아니다: 모집단을 `git ls-files` 로 파생하므로 **새 파일·새 컴포넌트가 자동으로 감시망에
 * 들어온다.** (저장소 교훈: *"목록은 곧 상한이 된다 — 수집은 파생형으로, 판정은 파서로."*)
 *
 * 판정은 **정규식이 아니라 TypeScript AST** 로 한다 — `getState()` 는 이펙트·콜백 안에도 많고
 * 그건 렌더 중에 실행되지 않아 **안전**하다. 문자열로 세면 위양성이 쏟아진다.
 *
 * ★독립 리뷰가 초판에서 실측으로 잡아낸 것들(전부 여기서 대조군으로 고정한다):
 *   · 모집단 pathspec `lib/**\/*.ts` 가 **디렉토리 직속 파일을 통째로 뺐다**(`hooks/`·`store/` 전부).
 *   · 조상 탐색 루프가 **한 번도 상승하지 않아** `.map` 콜백·중첩 화살표·모듈 헬퍼가 전부 위음성.
 *   · 그 결함이 eslint `prefer-const` 로 **이미 신고되고 있었다** — 린트 결함과 논리 결함이 같은 줄.
 */
import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { scanSource } from "@/lib/hydration/render-path-store-reads";

/** ★`'lib/**\/*.ts'` 는 git pathspec 에서 **중간 디렉토리 1개를 강제**한다 — 전부 걷고 여기서 거른다. */
const REPO_FILES = execSync("git ls-files '*.ts' '*.tsx'", { encoding: "utf8", maxBuffer: 1 << 26 })
  .split("\n")
  .filter((f) => f && !f.includes("__tests__") && !/\.test\.tsx?$/.test(f) && !f.startsWith("e2e/"));

/** 모집단에 **반드시 있어야 하는** 파일 — 하나라도 빠지면 pathspec 이 또 새는 것이다. */
const MUST_COLLECT = [
  "components/common/GlobalAddressSearch.tsx",
  "hooks/useHydrated.ts",                 // 디렉토리 직속(초판이 놓쳤다)
  "store/useProjectContextStore.ts",      // 디렉토리 직속(초판이 놓쳤다)
  "lib/api-client.ts",                    // 디렉토리 직속(초판이 놓쳤다)
  "app/layout.tsx",                       // 디렉토리 직속(초판이 놓쳤다)
];

/** 양성 대조군 — **전부 렌더 중에 실행된다.** 하나라도 놓치면 탐지가 죽은 것이다. */
const POSITIVE: Record<string, string> = {
  "useState 지연 초기값": `export function W(){ const [a]=useState(()=>useS.getState().x); return null; }`,
  "중첩 화살표": `export function W(){ const [a]=useState(()=>{ const pick=()=>useS.getState().x; return pick(); }); return null; }`,
  "useMemo 안의 map": `export function W(){ const b=useMemo(()=>items.map(i=>useS.getState().x),[]); return null; }`,
  "JSX map 콜백": `export function W(){ return <div>{items.map(()=>useS.getState().x)}</div>; }`,
  "모듈 헬퍼 경유": `function helper(){ return useS.getState().x; }\nexport function W(){ return <div>{items.map(()=>helper())}</div>; }`,
  "memo 래퍼": `const W = memo(function(){ const x = useS.getState().x; return null; });`,
  "익명 default export": `export default function(){ const x = useS.getState().x; return null; }`,
  "React.useState 형태": `export function W(){ const [a]=React.useState(()=>useS.getState().x); return null; }`,
  "스토어 별칭": `export function W(){ const x = useProjectContext.getState().y; return null; }`,
  "localStorage.length": `export function W(){ const n = localStorage.length; return null; }`,
  "localStorage 인덱스": `export function W(){ const n = localStorage["k"]; return null; }`,
};
/** 음성 대조군 — 렌더 중 실행되지 않는다. 여기서 걸리면 **정상 코드를 막는다**(위양성도 결함). */
const NEGATIVE: Record<string, string> = {
  useEffect: `export function W(){ useEffect(()=>{ useS.getState().x; },[]); return null; }`,
  useCallback: `export function W(){ const h=useCallback(()=>localStorage.getItem("k"),[]); return null; }`,
  "이벤트 핸들러": `export function W(){ const onClick=()=>useS.getState().x; return null; }`,
  "쓰기(setItem)": `export function W(){ localStorage.setItem("k","v"); return null; }`,
  "재수화 게이트 뒤": `export function W(){ const hydrated=useHydrated(); const x = hydrated && useS.getState().y; return null; }`,
  "&& 사슬 게이트": `export function W(){ const hydrated=useHydrated(); const f=(id)=>hydrated && !g(id) && useS.getState().y; return null; }`,
};

/**
 * ── **비성장 래칫**(파일 → 호출자 → 건수) ──
 * ★이 자리들은 **라이브에서 재현하지 않았다 — "미측정" 이다. 결함이라고 부르지 않는다.**
 *   `getState()`·스토어 메서드를 렌더 중에 부르면 zustand 의 서버 스냅샷을 우회하므로
 *   **불일치가 날 수 있는 형태**이지만, 실제로 나는지는 그 값이 렌더 텍스트에 실리는지와
 *   그 라우트가 SSR 되는지에 달렸다. 각각 따로 재야 판정된다.
 * ★**건수까지 못 박는다** — 파일만 키로 쓰면 같은 파일에 같은 호출을 더 넣어도 안 걸린다
 *   (독립 리뷰 지적: `NextStageCta` 는 같은 메서드를 2회 부르는데 초판 래칫엔 1줄이었다).
 */
const RATCHET: Record<string, number> = {
  // 로그인 셸 — `hasStoredRefreshToken()` 이 렌더 중 localStorage 를 읽는다.
  // ★라이브 측정 시도했으나 **결론 불가**: 이 구성(회차마다 새 컨텍스트)은 알려진 양성도 재현하지
  //   못한다는 것을 같은 세션에서 실측했다. 그러므로 "0건" 은 부재의 근거가 아니다.
  "components/auth/AuthWorkspaceClient.tsx:hasStoredRefreshToken": 2,
  "components/cost/BoqAutoWorkspace.tsx:getFieldProvenance": 2,
  "components/feasibility/FeasibilityEditorV2.tsx:isStale": 1,
  "components/feasibility/FeasibilityEditorV2.tsx:feasibilityCompleteness": 1,
  // ★독립 리뷰가 찾아낸 자리 — 초판 검출기의 사각(모듈 헬퍼 + `.map` 콜백)에 숨어 있었다.
  //   `hasRealSlotValue(r)` 의 결과가 `✓`/`–` 와 조건부 문구를 가른다.
  "components/orchestration/InputResolveModal.tsx:hasRealSlotValue": 1,
  "components/orchestration/OrchestratorPanel.tsx:previewPlan": 1,
  "components/orchestration/OrchestratorPanel.tsx:resolveInputs": 1,
  // ★부분 게이트 — `if (!projectIdProp && !hydrated) return null` 이라 **prop 이 오면 무가드**다.
  //   주석은 `projectId` 가 route param 이라 안전하다고 말하는데, 위험한 것은 그 prop 이 아니라
  //   `getNextRecommendedStage()` 가 읽는 **라이브 스토어**다. ★가장 유력한 다음 후보.
  "components/projects/NextStageCta.tsx:getNextRecommendedStage": 2,
  "components/projects/ProjectHealthBoard.tsx:projectCompleteness": 1,
  "components/projects/ProjectHealthBoard.tsx:getNextRecommendedStage": 1,
  // 게이트가 **아예 없는** 컴포넌트(형제 `LifecycleProgressRail` 은 2026-08-13 에 고쳐졌다).
  "components/projects/ProjectLifecyclePipeline.tsx:getNextRecommendedStage": 1,
  "components/projects/ProjectLifecyclePipeline.tsx:getStageStatus": 3,
  "components/projects/ProjectLifecyclePipeline.tsx:stageHasData": 2,
};

const siteKey = (h: { file: string; text: string }): string => `${h.file}:${h.text.split("(")[0].trim()}`;
const scanRepo = () => REPO_FILES.flatMap((f) => scanSource(f, readFileSync(f, "utf8")));

describe("렌더 경로 라이브 저장소 읽기 — 파생형 계약", () => {
  it("①모집단 — 수집이 새면 아래 판정이 공허해진다", () => {
    expect(REPO_FILES.length).toBeGreaterThan(600);
    for (const f of MUST_COLLECT) expect(REPO_FILES, `모집단에서 빠졌다: ${f}`).toContain(f);
  });

  it("②탐지 — 렌더 중 실행되는 모든 형태를 잡는다", () => {
    const missed = Object.entries(POSITIVE)
      .filter(([, src]) => scanSource("P.tsx", src).length === 0)
      .map(([name]) => name);
    expect(missed, "이 형태를 놓치면 '전수 0건' 은 검출기 기준 0일 뿐이다").toEqual([]);
  });

  it("③특이도 — 렌더 중 실행되지 않는 같은 호출은 잡지 않는다", () => {
    const falsePositives = Object.entries(NEGATIVE)
      .filter(([, src]) => scanSource("N.tsx", src).length > 0)
      .map(([name]) => name);
    expect(falsePositives, "가드가 정상 코드를 막으면 그것도 결함이다").toEqual([]);
  });

  it("★저장소 전수 — 알려진 자리보다 **늘지 않는다**(비성장 래칫)", () => {
    const counts: Record<string, number> = {};
    for (const h of scanRepo()) counts[siteKey(h)] = (counts[siteKey(h)] ?? 0) + 1;

    const added = Object.keys(counts).filter((k) => !(k in RATCHET)).sort();
    expect(
      added,
      "렌더 중 라이브 저장소를 읽는 자리가 **새로 생겼다** — 서버/클라 첫 렌더가 갈려\n" +
        "React #418(hydration)이 날 수 있다. 이펙트·핸들러로 옮기거나 `useHydrated()` 게이트 뒤로,\n" +
        "또는 셀렉터(`useXStore((s) => …)`)로 바꿔라.",
    ).toEqual([]);

    const grown = Object.entries(counts).filter(([k, n]) => k in RATCHET && n > RATCHET[k]);
    expect(grown, "같은 파일에서 같은 호출이 **늘었다**").toEqual([]);

    // ★죽은 면제도 실패시킨다 — 고쳐 놓고 목록에 남기면 다음 사람이 부채를 과대평가한다.
    const dead = Object.entries(RATCHET)
      .filter(([k, n]) => (counts[k] ?? 0) < n)
      .map(([k, n]) => `${k}: 등재 ${n} → 실제 ${counts[k] ?? 0}`);
    expect(dead, "래칫이 실제보다 크다 — 고쳤으면 목록에서 줄여라(죽은 면제)").toEqual([]);
  });

  it("★고친 자리는 래칫에 없다 — 되돌리면 '새로 생김' 으로 잡힌다", () => {
    expect(Object.keys(RATCHET).some((k) => k.startsWith("components/common/GlobalAddressSearch.tsx"))).toBe(false);
  });
});
