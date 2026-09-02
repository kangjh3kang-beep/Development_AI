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
  // ★store-method 형태의 양성 대조군이 **하나도 없었다**(독립 리뷰 지적) — 래칫의 다수가 이 형태인데
  //   탐지가 죽어도 알 수 없었다. 두 문법 형태를 각각 건다.
  "스토어 메서드(셀렉터 경유)": `export function W(){ const f = useSStore((s) => s.readIt); return <b>{f()}</b>; }`,
  "스토어 메서드(구조분해 경유)": `export function W(){ const { readIt } = useSStore(); return <b>{readIt()}</b>; }`,
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
 * ★이 자리들은 **결함이라고 부르지 않는다.** 아래 실측이 있는 것과 없는 것을 갈라 적는다.
 *
 *   ■ 실측(2026-08-26 · 로컬 `next dev` + 라이브 localStorage 이식 · React 개발 모드)
 *     `/ko/projects/<id>` · `…/finance` · `…/permit` 에서 **하이드레이션 오류 0건**.
 *     ★같은 하네스에서 `GlobalAddressSearch` 결함을 되살리면 `regulations`·`finance`·`permit` 이
 *       **각 1건**을 낸다 — **대조군이 살아 있는 상태의 0** 이다(대조군 없는 0 은 근거가 아니다).
 *     → 그 두 라우트가 렌더하는 `NextStageCta`·`ProjectLifecyclePipeline` 은 **지금은** 불일치를
 *       내지 않는다. 형제 e2e 부채 주석의 가설(*"`useDictionary` 스피너로 우연히 가려져 있다"*)과
 *       일치하지만 **그 가설 자체는 검증하지 않았다.**
 *
 *   ■ 미측정(재 보지 않았다)
 *     프로덕션 번들 · 나머지 소비 라우트(`bim`·`esg`·`drone`·`contracts`·`legal`·`feasibility`) ·
 *     `ProjectHealthBoard` · `BoqAutoWorkspace` · `FeasibilityEditorV2` · `OrchestratorPanel` ·
 *     `InputResolveModal`(사용자 조작 뒤에만 렌더) · `AuthWorkspaceClient`(측정 시도 → **결론 불가**).
 *   `getState()`·스토어 메서드를 렌더 중에 부르면 zustand 의 서버 스냅샷을 우회하므로
 *   **불일치가 날 수 있는 형태**이지만, 실제로 나는지는 그 값이 렌더 텍스트에 실리는지와
 *   그 라우트가 SSR 되는지에 달렸다. 각각 따로 재야 판정된다.
 * ★**건수까지 못 박는다** — 파일만 키로 쓰면 같은 파일에 같은 호출을 더 넣어도 안 걸린다
 *   (독립 리뷰 지적: `NextStageCta` 는 같은 메서드를 2회 부르는데 초판 래칫엔 1줄이었다).
 */
const RATCHET: Record<string, number> = {
  // ★2026-08-27 스캐너를 **구조분해 형태**까지 넓히면서 새로 보인 자리(전에는 사각이라 안 보였다).
  //   `const { hasValidKey } = useSystemStore()` → 렌더 중 `hasValidKey()`(내부 `get()`).
  //   ★**게이트는 실재한다**: 같은 파일 136줄 `if (!isMounted || isAdmin === null) return …` 이
  //     완전 조기 반환이라 하이드레이션 렌더에서 이 줄에 **도달하지 않는다**.
  //     다만 이 검사기의 게이트 인식은 `useHydrated` 만 보므로 위양성으로 잡힌다 —
  //     이름만 보고 `isMounted` 를 게이트로 인정하면 **가짜 게이트**도 통과하므로 넓히지 않는다.
  //   ★부채: 그 조기 반환을 지우면 이 자리는 **진짜 결함**이 된다(래칫은 그 변화를 못 본다).
  // ★제거됨(2026-08-28) — `hasValidKey` 는 **쓰이지 않는 사용자 키**의 길이만 보고
  //   초록 "Connected" 를 그렸다. 스토어에서 키를 걷어내며 이 호출도 사라졌다.
  //   래칫 항목을 지우지 않으면 "죽은 면제" 로 빨개진다(등재 수 > 실제 수).
  // 로그인 셸 — `hasStoredRefreshToken()` 이 렌더 중 localStorage 를 읽는다.
  // ★라이브 측정 시도했으나 **결론 불가**: 이 구성(회차마다 새 컨텍스트)은 알려진 양성도 재현하지
  //   못한다는 것을 같은 세션에서 실측했다. 그러므로 "0건" 은 부재의 근거가 아니다.
  "components/auth/AuthWorkspaceClient.tsx:hasStoredRefreshToken": 2,
  "components/cost/BoqAutoWorkspace.tsx:getFieldProvenance": 2,
  // ★`isStale` 은 `if (!result || result.is_baseline) return false;` 뒤다 — `result` 는 **비-persist**
  //   스토어(`use-feasibility-v2-store`)의 값이라 서버/클라 초기값이 같고, 하이드레이션 렌더에서는
  //   그 조기 반환에 걸려 **도달하지 않는다**(2026-08-27 실측).
  //   ★형제 `feasibilityCompleteness` 는 이 목록에서 **빠졌다** — 게이트가 없어 실제로 #418 을 냈고
  //     셀렉터+순수 판정으로 고쳤다(라이브 귀속: 무개변 1 / 그 블록만 서버에서 일치시키면 0 / 무관 개변 1).
  "components/feasibility/FeasibilityEditorV2.tsx:isStale": 1,
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
    // ★수(하한)만으로는 절단을 못 잡는다 — **줄어든 모집단 안에서 하한이 만족**되기 때문이다.
    //   실측(2026-08-26): pathspec `lib/**\/*.ts` 가 디렉토리 직속 164파일을 조용히 뺐는데
    //   그걸 막으라고 둔 `>400` 가드가 **통과**했다. 즉 가드가 자기가 지켜야 할 모집단 안에서
    //   만족돼 **공범**이 됐다. 하한은 남기되, 아래 두 축을 함께 건다.
    expect(REPO_FILES.length).toBeGreaterThan(600);

    // 축1 — **이름 대조군**(구체·즉시 진단): 반드시 있어야 할 파일
    for (const f of MUST_COLLECT) expect(REPO_FILES, `모집단에서 빠졌다: ${f}`).toContain(f);

    // 축2 — **성질 대조군**(파생·새 축 방어): 이름을 몰라도 닫히도록, 모집단을
    //   **더 넓은 조회에서 선언된 제외만 뺀 것**과 대조한다. 디렉토리 이름을 쓰지 않는다
    //   (★초판은 `["lib","hooks","store","app","components"]` 를 손으로 나열했다가
    //     `components/` **직속이 0개인 것이 정상**이라 위양성을 냈다 — 목록은 또 상한이 된다).
    const BROAD = execSync("git ls-files", { encoding: "utf8", maxBuffer: 1 << 26 })
      .split("\n")
      .filter((f) => /\.tsx?$/.test(f))
      .filter((f) => !f.includes("__tests__") && !/\.test\.tsx?$/.test(f) && !f.startsWith("e2e/"));
    // ★**양방향**으로 건다 — 한쪽만 걸면 반대쪽이 무제한이 된다(저장소 §D-19).
    //   누락(절단)만 보면 *"너무 넓힘"* 은 **원리적으로 탐지 불가**다: 제외를 지워
    //   테스트·`e2e/` 까지 긁어도 `missing` 은 비어 있어 초록이다(동료 세션 실측이 같은 형태를
    //   자기 락에서 잡았다 — 하한은 파생형, 상한은 목록형이라 오구현이 정답과 구별되지 않았다).
    const missing = BROAD.filter((f) => !REPO_FILES.includes(f)).sort();
    const extra = REPO_FILES.filter((f) => !BROAD.includes(f)).sort();
    expect(
      missing,
      "모집단이 **더 넓은 조회보다 작다** — pathspec 이나 필터가 조용히 잘라 냈다.\n" +
        "(실측 2026-08-26: `lib/**\/*.ts` 형태가 디렉토리 **직속** 164파일을 지웠고,\n" +
        " 그걸 막으라고 둔 하한 가드는 **줄어든 모집단 안에서 만족**돼 통과했다.)",
    ).toEqual([]);
    expect(
      extra,
      "모집단이 **선언된 제외를 넘어 넓다** — 테스트·`e2e/` 를 긁으면 래칫이 남의 파일로 오염된다.",
    ).toEqual([]);  });

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
    // 2026-08-27 — 라이브에서 #418 이 **실제로 났던** 자리. 스토어 메서드 호출을 되살리면 여기 걸린다.
    expect(Object.keys(RATCHET)).not.toContain("components/feasibility/FeasibilityEditorV2.tsx:feasibilityCompleteness");
  });
});
