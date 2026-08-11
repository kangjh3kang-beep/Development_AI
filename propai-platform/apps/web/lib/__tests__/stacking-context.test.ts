/**
 * 스태킹 컨텍스트 판정기 자체의 계약.
 *
 * ★왜 판정기에 테스트를 다는가 — 이 저장소가 실제로 데인 자리다. 조상 가드는 두 벌 있었고
 *   둘 다 **Tailwind v3 토큰**을 찾고 있었다(`backdrop-filter` 저장소 실재 0건 vs
 *   `backdrop-blur-*` 106건). "가드가 있다"와 "그 가드가 현재 스택에서 성립한다"는 다르다.
 *
 * ★픽스처는 **두 모집단을 가른다**(규율 A-2·B): 층 상자를 만드는 표기와, 이름이 비슷하지만
 *   만들지 **않는** 표기를 짝으로 둔다. 둘이 같은 답을 내면 정규식을 아무렇게나 고쳐도 초록이다.
 */
import { describe, expect, it } from "vitest";

import { clipsDescendants, createsStackingContext, scanAncestorTraps } from "@/lib/stacking-context";

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
  ["z-10", "positioned 아닌 z 는 무효"],
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

  it("자기 자신은 기본적으로 검사하지 않는다 — 자기 z 는 자기를 가두지 않는다", () => {
    document.body.innerHTML = "";
    const target = chain(["px-4"]);
    target.className = "absolute z-[650]";
    expect(scanAncestorTraps(target).traps).toHaveLength(0);
    expect(scanAncestorTraps(target, { skipSelf: false }).traps).toHaveLength(1);
  });
});
