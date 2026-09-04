/**
 * 스태킹 컨텍스트 판정기 자체의 계약.
 *
 * ★왜 판정기에 테스트를 다는가 — 이 저장소가 실제로 데인 자리다. 조상 가드는 두 벌 있었고
 *   둘 다 **Tailwind v3 토큰**을 찾고 있었다(`backdrop-filter` 저장소 실재 0건 vs
 *   `backdrop-blur-*` 120건). "가드가 있다"와 "그 가드가 현재 스택에서 성립한다"는 다르다.
 *
 * ★픽스처는 **두 모집단을 가른다**(규율 A-2·B): 층 상자를 만드는 표기와, 이름이 비슷하지만
 *   만들지 **않는** 표기를 짝으로 둔다. 둘이 같은 답을 내면 정규식을 아무렇게나 고쳐도 초록이다.
 *
 * ★변이 검증 결과(2026-08-12 · `scripts/mutate_changed.py`, 13변이) — **설명 가능한 생존만 남겼다**:
 *   · `LayerTrap.kind` / `scanAncestorTraps` 시그니처의 **타입 라인** 3건 → vitest 는 타입을 안 보므로
 *     생존하지만, 실제로 주입해 `tsc --noEmit` 을 돌려 **오류 5건으로 잡히는 것을 확인**했다
 *     (CI 의 type-check 잡이 이 층을 지킨다 — 추정이 아니라 실측).
 *   · 주석 줄 1건 → 실행되지 않는다.
 *   · `describeTraps` 의 출력 문자열 1건 → **진짜 구멍이었다.** 아래 케이스로 잠갔다.
 *
 * ★R1(2026-08-12 · 16변이 · kill 8 / skip 3 / 생존 5) — 생존 트리아지:
 *   · `culpritTokens` 의 **클리핑 분기** 2건 → **진짜 구멍이었다**(메시지 문자열만 보면 클래스 줄에
 *     같은 토큰이 이미 있어 분기를 망가뜨려도 초록). 범인 토큰을 **종류별로** 단언해 잠갔고
 *     변이 재주입으로 CAUGHT 확인.
 *   · 함수 시그니처의 타입 리터럴 1건 → 주입해 `tsc --noEmit` 이 잡는 것을 확인(TS2345).
 *   · `culpritTokens(cls, "stacking")` 인자 1건 → **등가 변이**다. 구현이 `kind === "clipping"`
 *     만 분기하므로 "clipping" 이 아닌 어떤 값이어도 결과가 같다 — 잡을 수 없는 게 맞다.
 *   · 진단 **라벨 문구** 1건 → 표시 문구는 계약이 아니다(범인 토큰·클래스는 위에서 잠겼다).
 */
import { describe, expect, it } from "vitest";

import { clipsDescendants, createsStackingContext, describeTraps, scanAncestorTraps } from "@/lib/stacking-context";

/** 층 상자를 **만드는** 표기 — Tailwind v4 실사용형. */
const CREATES: Array<[string, string]> = [
  ["isolate", "isolation:isolate"],
  ["relative z-10", "positioned + z"],
  ["sticky top-0 z-[600]", "sticky + 임의값 z"],
  ["absolute -z-10", "음수 z"],
  ["backdrop-blur-3xl", "v4 유리효과 — 종전 가드가 못 보던 바로 그 유틸"],
  ["blur-[60px]", "임의값 blur"],
  ["blur-sm", "필터"],
  ["opacity-40", "반투명"],
  ["opacity-[0.2]", "임의값 반투명"],
  ["drop-shadow-lg", "필터형 그림자"],
  ["grayscale-0", "필터 항등값도 none 이 아니면 층 상자를 만든다"],
  ["scale-105", "개별 transform 속성"],
  ["-translate-x-1/2", "음수 transform"],
  ["rotate-45", "회전"],
  ["rotate-0", "★항등 회전도 none 이 아니다 — tailwind 4.2.1 실측 `rotate: 0deg`"],
  ["scale-100", "★항등 배율도 층 상자 — 실측 `scale: 100% 100%`"],
  ["transform-gpu", "GPU 승격 — 실측 `translateZ(0)` 포함"],
  ["sticky top-0", "★z 없이도 sticky 는 층 상자다"],
  ["fixed inset-0", "★z 없이도 fixed 는 층 상자다"],
  ["mix-blend-multiply", "합성 모드"],
  ["will-change-transform", "승격 힌트"],
  ["contain-paint", "페인트 격리 — 실측 `contain: paint`"],
  ["hover:backdrop-blur-md", "variant 접두사 — 그 상태에서 실제로 갇힌다"],
  ["group-hover:opacity-40", "group variant"],
  ["md:relative md:z-20", "반응형 variant"],
  // ★아래 셋은 종전 접두사 정규식(`[a-z0-9-]+:`)이 **표기를 몰라서** 통째로 놓치던 형태다.
  ["@4xl:sticky", "컨테이너 쿼리 variant — 저장소에 실재"],
  ["group-hover/sensor:scale-105", "이름 붙은 group variant(슬래시)"],
  ["data-[state=open]:isolate", "data 속성 variant"],
];

/** 이름은 비슷하지만 층 상자를 **만들지 않는** 표기 — 위양성 방지(규율 A-6). */
const DOES_NOT: Array<[string, string]> = [
  ["", "빈 문자열"],
  ["relative", "z 없는 positioned 는 층 상자가 아니다"],
  ["absolute left-0 right-0 top-full", "위치만 잡은 팝오버 자신"],
  // ★정확히는 "부모가 flex/grid 가 **아닐 때만**" 무효다 — flex·grid **아이템**은 static 이어도
  //   `z-index ≠ auto` 면 층 상자를 만든다(CSS Flexbox §5.4 · Grid §6). 클래스 문자열만으로는
  //   부모의 display 를 알 수 없어 여기서는 무효로 둔다(저장소 실사용 1건). 아래 it.todo 참조.
  ["z-10", "positioned 아닌 z — 부모가 flex/grid 가 아닐 때만 무효"],
  ["shadow-lg", "box-shadow 는 필터가 아니다"],
  ["shadow-[var(--shadow-lg)]", "임의값 box-shadow"],
  // ★★v4 실측(tailwind 4.2.1 컴파일): 맨몸 `transform`·`filter`·`backdrop-filter` 는
  //   빈 변수 합성(`transform: var(--tw-rotate-x,) …`)이라 선언이 무효 → `none` → 층 상자 없음.
  //   종전 가드가 찾던 4토큰 중 3개가 **v4 에서는 위반이 아니었다.**
  ["transform", "v4 맨몸 transform — 빈 변수 합성이라 none"],
  ["filter", "v4 맨몸 filter — 빈 변수 합성이라 none"],
  ["backdrop-filter", "v4 맨몸 backdrop-filter — 빈 변수 합성이라 none"],
  ["opacity-100", "불투명 — 층 상자 없음"],
  ["blur-none", "필터 해제"],
  ["backdrop-blur-none", "배경필터 해제"],
  ["transform-none", "변형 해제"],
  ["mask-none", "마스크 해제"],
  ["mix-blend-normal", "기본 합성"],
  ["will-change-auto", "힌트 없음"],
  ["drop-shadow-none", "필터형 그림자 해제"],
  ["flex flex-col gap-3 xl:flex-row", "레이아웃 유틸"],
  ["rounded-2xl border border-[var(--line-strong)] p-1", "장식 유틸"],
  ["min-w-[220px] flex-1", "임의값 크기"],
  ["bg-white/72", "슬래시 투명도(배경만 반투명 — 층 상자 아님)"],
];

describe("스태킹 컨텍스트 판정 — 두 모집단이 갈린다", () => {
  it.each(CREATES)("층 상자를 만든다: %s (%s)", (cls) => {
    expect(createsStackingContext(cls), `층 상자로 판정해야 한다: ${cls}`).toBe(true);
  });

  it.each(DOES_NOT)("층 상자를 만들지 않는다: %s (%s)", (cls) => {
    expect(createsStackingContext(cls), `정상 코드를 위반으로 잡으면 안 된다: ${cls}`).toBe(false);
  });

  it("★두 모집단이 실제로 다른 답을 낸다 — 차가 0이면 잠금이 아니다", () => {
    const yes = CREATES.filter(([c]) => createsStackingContext(c)).length;
    const no = DOES_NOT.filter(([c]) => !createsStackingContext(c)).length;
    expect(yes).toBe(CREATES.length);
    expect(no).toBe(DOES_NOT.length);
    expect(yes, "긍정 모집단이 비었다").toBeGreaterThan(10);
    expect(no, "부정 모집단이 비었다").toBeGreaterThan(10);
  });

  it("★종전 v3 가드가 놓치던 유틸을 실제로 잡는다(이 회귀의 근원)", () => {
    const V3_GUARD = /(?:^|\s)(?:[a-z0-9-]+:)*(?:isolate|transform|filter|backdrop-filter)(?=\s|$)/;
    const missedByV3 = [
      "backdrop-blur-3xl",
      "opacity-40",
      "blur-[60px]",
      "drop-shadow-lg",
      "scale-105",
      "contain-paint",
      "sticky",
      "@4xl:sticky",
      "group-hover/sensor:scale-105",
    ];
    for (const cls of missedByV3) {
      expect(V3_GUARD.test(cls), `전제 확인: v3 가드는 ${cls} 를 못 봐야 한다`).toBe(false);
      expect(createsStackingContext(cls), `새 판정기는 ${cls} 를 봐야 한다`).toBe(true);
    }
  });

  it("★반대로, v3 가드가 잡던 것 중 v4 에서 **위반이 아닌** 셋을 놓아준다", () => {
    // 이 방향을 안 잠그면 "넓히기만 한" 정규식이 되고, v4 위양성 3종이 그대로 남는다.
    const V3_GUARD = /(?:^|\s)(?:[a-z0-9-]+:)*(?:isolate|transform|filter|backdrop-filter)(?=\s|$)/;
    for (const cls of ["transform", "filter", "backdrop-filter"]) {
      expect(V3_GUARD.test(cls), `전제 확인: v3 가드는 ${cls} 를 위반으로 봤다`).toBe(true);
      expect(createsStackingContext(cls), `v4 에서는 ${cls} 가 위반이 아니다`).toBe(false);
    }
  });
});

// ── 부채(초록 안에 드러낸다) ──
// flex/grid 아이템의 `z-index` 는 `position:static` 이어도 층 상자를 만드는데, 클래스 문자열만
// 보는 이 판정기는 **부모의 display 를 모른다**. 부모 요소를 함께 받는 오버로드가 필요하다.
it.todo("flex/grid 아이템의 z-index — 부모 display 를 함께 봐야 판정할 수 있다");

// 수작업 CSS(`.glass`·`.cc-panel`·`.leaflet-container`)와 인라인 style·framer-motion 의
// 인라인 transform 은 클래스 토큰으로 원리적으로 못 본다 — 브라우저 페인트 순서로만 잡힌다.
// ★2026-08-18 — 이 위임은 **수신됐다.** 종전에는 여기서 e2e 로 넘겼는데 그 e2e 가 받지
//   않아 위임이 공중에 떠 있었다(저장소 전체에서 `elementFromPoint` 를 실제로 호출하는 곳은
//   `e2e/popover-layer.spec.ts` 한 곳뿐이었고 대상은 주소 팝오버 vs z-[600] 헤더였다).
//   그 공백에서 `.leaflet-pane` 평탄화가 지도 내부 사다리를 죽인 채 초록이 유지됐다.
//   → `e2e/satong-pane-ladder.spec.ts` 가 실브라우저에서 **계산된 pane z 와 페인트 순서**를
//     잰다(음성 대조군 포함). jsdom 은 CSS 계단을 재현하지 않아 여기서는 못 한다.
it.todo("수작업 CSS·인라인 style 층 — e2e/satong-pane-ladder.spec.ts 가 수신함(지도 층)");

describe("클리핑 판정", () => {
  it.each([
    "overflow-hidden",
    "overflow-x-auto",
    "overflow-y-scroll",
    "overflow-clip",
    "sm:overflow-hidden",
    "overflow-hidden rounded-[var(--r-panel)] border shadow-[var(--shadow-lg)]",
  ])("잘라낸다: %s", (cls) => {
    expect(clipsDescendants(cls)).toBe(true);
  });

  it.each(["overflow-visible", "flex flex-col", "", "rounded-2xl p-1"])("잘라내지 않는다: %s", (cls) => {
    expect(clipsDescendants(cls)).toBe(false);
  });
});

describe("조상 훑기", () => {
  function chain(classes: string[]): HTMLElement {
    // 바깥→안쪽 순서로 중첩한 뒤 가장 안쪽 요소를 돌려준다.
    let parent: HTMLElement = document.body;
    let leaf: HTMLElement = document.body;
    for (const cls of classes) {
      const el = document.createElement("div");
      el.className = cls;
      parent.appendChild(el);
      parent = el;
      leaf = el;
    }
    const target = document.createElement("ul");
    leaf.appendChild(target);
    return target;
  }

  it("조상 깊이를 세고 위반만 모은다", () => {
    document.body.innerHTML = "";
    const target = chain(["flex flex-col", "relative z-10", "px-4 py-3"]);
    const scan = scanAncestorTraps(target);
    expect(scan.depth, "조상을 훑지 못했다 — 검사가 공허해진다").toBe(3);
    expect(scan.traps).toHaveLength(1);
    expect(scan.traps[0].kind).toBe("stacking");
  });

  it("클리핑은 명시적으로 켤 때만 위반이다(기하에 따라 무해할 수 있다)", () => {
    document.body.innerHTML = "";
    const target = chain(["overflow-hidden rounded-xl", "px-4"]);
    expect(scanAncestorTraps(target).traps).toHaveLength(0);
    const withClip = scanAncestorTraps(target, { kinds: ["stacking", "clipping"] });
    expect(withClip.traps).toHaveLength(1);
    expect(withClip.traps[0].kind).toBe("clipping");
  });

  // ★진단 메시지도 계약이다 — 실패 출력이 "어디의 무엇을 고쳐야 하는지"를 말하지 못하면
  //   가드가 빨개져도 다음 사람이 못 고친다. 그리고 이 메시지는 어떤 단언에도 안 쓰여
  //   **변이 검증에서 실제로 생존**했다(2026-08-12 실측) — 그래서 여기서 잠근다.
  it("진단 메시지가 깊이·종류·클래스를 모두 담는다", () => {
    document.body.innerHTML = "";
    const target = chain(["overflow-hidden rounded-xl", "relative z-10", "px-4"]);
    const scan = scanAncestorTraps(target, { kinds: ["stacking", "clipping"] });
    const msg = describeTraps(scan.traps);
    expect(scan.traps.length, "전제: 두 종류가 모두 잡혀야 이 검사가 의미가 있다").toBe(2);
    expect(msg, "층 상자 위반을 그렇게 부르지 않는다").toContain("층 상자 생성");
    expect(msg, "클리핑 위반을 그렇게 부르지 않는다").toContain("잘라냄");
    expect(msg, "어느 조상인지(깊이)를 말하지 않는다").toMatch(/조상 \d+/);
    expect(msg, "무엇을 고쳐야 하는지(클래스)를 말하지 않는다").toContain("relative z-10");
    expect(msg, "클리핑 조상의 클래스를 말하지 않는다").toContain("overflow-hidden");

    // ★범인 토큰을 **종류별로** 단언한다. 메시지 문자열만 보면 클래스 줄에 같은 토큰이 이미
    //   들어 있어, `culpritTokens` 의 클리핑 분기를 망가뜨려도 초록이었다(변이 실측 2건 생존).
    const clip = scan.traps.find((t) => t.kind === "clipping");
    const stack = scan.traps.find((t) => t.kind === "stacking");
    expect(clip?.culprits, "클리핑 범인은 `overflow-hidden` 하나여야 한다").toEqual(["overflow-hidden"]);
    expect(stack?.culprits, "층 상자 범인은 positioned+z 두 토큰이어야 한다").toEqual(["relative", "z-10"]);
  });

  it("자기 자신은 기본적으로 검사하지 않는다 — 자기 z 는 자기를 가두지 않는다", () => {
    document.body.innerHTML = "";
    const target = chain(["px-4"]);
    target.className = "absolute z-[650]";
    expect(scanAncestorTraps(target).traps).toHaveLength(0);
    expect(scanAncestorTraps(target, { skipSelf: false }).traps).toHaveLength(1);
  });
});

// ── 적대검증(2026-08-12)이 짚은 미탐을 잠근다 ──
describe("★종전 미탐 — 실제 저장소 표기에서 새던 것들", () => {
  it.each([
    ["blur-[var(--glass-blur)]", "SatongMapShell 의 유리효과 — `var()` 때문에 통째로 미탐이었다"],
    ["opacity-[var(--x)]", "런타임 변수 투명도"],
    ["blur-[calc(2px*3)]", "calc 임의값"],
    ["opacity-(--my-op)", "v4 CSS 변수 단축 표기"],
    ["opacity-40!", "v4 후행 important — 종전엔 v3 식 선행 `!` 만 처리했다"],
    ["drop-shadow", "맨몸 drop-shadow"],
  ])("이제 잡는다: %s (%s)", (cls) => {
    expect(createsStackingContext(cls)).toBe(true);
  });

  it.each([
    ["truncate", "= overflow:hidden — 저장소 112건"],
    ["line-clamp-3", "= overflow:hidden — 저장소 9건"],
    ["overflow-hidden!", "후행 important"],
  ])("클리핑으로 잡는다: %s (%s)", (cls) => {
    expect(clipsDescendants(cls)).toBe(true);
  });

  it.each([
    ["line-clamp-none", "클램프 해제는 자르지 않는다"],
    ["perspective-origin-center", "원점만 옮긴다 — 층 상자 아님"],
    ["mask-type-alpha", "SVG 마스크 종류 — 마스크를 거는 게 아니다"],
  ])("여전히 놓아준다: %s (%s)", (cls) => {
    expect(createsStackingContext(cls) || clipsDescendants(cls)).toBe(false);
  });

  it("★진단이 범인 토큰을 잘라먹지 않는다 — 인용하던 그 모양에서 실제로 잘렸다", () => {
    document.body.innerHTML = "";
    const outer = document.createElement("div");
    // SiteInitiator.tsx:140 verbatim(길이 117) — 범인 `backdrop-blur-3xl` 이 맨 뒤라
    // 종전 90자 절단에서 사라졌다.
    outer.className =
      "relative rounded-[var(--radius-lg)] border border-[var(--line)] bg-[var(--glass-bg)] p-8 shadow-2xl backdrop-blur-3xl";
    document.body.appendChild(outer);
    const target = document.createElement("ul");
    outer.appendChild(target);

    const msg = describeTraps(scanAncestorTraps(target).traps);
    expect(msg, "범인 토큰이 진단에 없다 — 무엇을 고쳐야 하는지 말하지 못한다").toContain("backdrop-blur-3xl");
  });

  it("★상한에 닿으면 조용히 부분 결과를 돌려주지 않고 던진다", () => {
    document.body.innerHTML = "";
    let parent: HTMLElement = document.body;
    for (let i = 0; i < 205; i += 1) {
      const el = document.createElement("div");
      parent.appendChild(el);
      parent = el;
    }
    const target = document.createElement("ul");
    parent.appendChild(target);
    expect(() => scanAncestorTraps(target)).toThrow(/조상 200단을 넘었다/);
  });
});
