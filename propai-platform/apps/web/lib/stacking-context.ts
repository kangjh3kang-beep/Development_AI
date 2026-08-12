/**
 * 스태킹 컨텍스트·클리핑 조상 판정 — **층위 계약의 전제 조건**을 검사하는 공용 도구.
 *
 * ★왜 필요한가(쉬운 말로):
 *   `z-[650]` 같은 층위 값은 "화면 전체에서 650번째로 위"라는 뜻이 아니다.
 *   조상 중 하나가 **자기만의 층 상자**(스태킹 컨텍스트)를 만들면, 그 안에서만 650이고
 *   바깥에서는 **조상의 층**으로 취급된다. 조상이 `z-10`이면 실효 10이다.
 *   또 조상 중 하나가 `overflow-hidden`이면 아무리 위에 있어도 **상자 밖은 잘린다.**
 *   즉 층위 계약값은 **조상이 깨끗할 때만** 의미가 있다.
 *
 * ★이 파일이 생긴 경위 — 같은 함정을 세 번 밟았다:
 *   ① CAD 전체화면 `z-[9990]`이 `DesignWorkspace`의 `relative z-10`에 갇혀 실효 10이었다.
 *   ② 그 교훈으로 만든 조상 가드가 **`isolate` 하나만** 봤다(`DesignWorkspace.test.tsx`).
 *   ③ 주소 팝오버 가드는 `isolate|transform|filter|backdrop-filter`를 봤는데, 이건
 *      **Tailwind v3 토큰**이다. 저장소는 v4다 — v4에서 실제로 층 상자를 만드는
 *      `backdrop-blur-*`·`opacity-N`·`blur-*`는 **한 건도 못 봤다**.
 *      실측(2026-08-12 · `className` 안의 토큰만 세어 877개 파일 스캔):
 *        · 종전 가드가 찾던 것 — `backdrop-filter` **0** · `filter` 2 · `isolate` 2 · `transform*` 2
 *        · 종전 가드가 못 보던 것 — `backdrop-blur-*` **120** · `opacity-N` **603** · `blur-*` **27**
 *      즉 "조상이 깨끗한지 검사한다"는 선언이 실제 생성자의 **대부분을 비껴갔다.**
 *   → 판정을 **한 곳**으로 모은다. 한 곳을 고치면 모든 가드가 따라오게.
 *
 * ★"공용화"의 **현재 범위**(과장하지 않기 위해 적는다 — 소비처는 아직 둘이다):
 *   · 결속됨 — `GlobalAddressSearch.popoverRung.test.tsx` · `DesignWorkspace.test.tsx`
 *   · **남은 미러(부채)** — `lib/source-invariant.ts` 의 `Z_UTIL`(접두사가 `[\w-]+:` 라
 *     이 파일이 지적한 바로 그 표기 구멍을 그대로 갖고 있다. `layer-ladder.contract.test.tsx` 를
 *     구동하므로 손대면 그쪽 계약이 함께 움직인다 — 별도 티켓) · `floating-layer.contract.test.tsx` ·
 *     `layer-ladder.contract.test.tsx` · `SatongMapShell.contentLayer.test.tsx` 의 지역 `z-[N]` 정규식.
 *
 * ★한계(정직하게 — 이걸 모르면 "전수 검사했다"고 착각한다):
 *   · **클래스 문자열만 본다.** 인라인 `style={{ isolation:"isolate" }}`·framer-motion 이 넣는
 *     인라인 `transform`·수작업 CSS는 **전부 사각지대**다. 실측된 사각 예(2026-08-12 재측정):
 *     `app/globals.css` 의 `.glass`(backdrop-filter · 사용 19회/5파일) · `.leaflet-container`
 *     (isolation:isolate) · `.cc-panel`(overflow:hidden · 사용 72회/32파일) ·
 *     `.sa-di-block`(overflow:hidden). jsdom 은 CSS 를 로드하지 않으므로 `getComputedStyle` 로도
 *     구제되지 않는다 — 이 층까지 보려면 **실제 브라우저에서 페인트 순서(`elementFromPoint`)로** 재야 한다.
 *   · **클래스 토큰 층 자체도 완전하지 않다.** 값이 런타임 변수인 임의값(`opacity-[var(--x)]`)은
 *     이제 형태로는 잡지만 **실제 값이 층 상자를 만드는지는 정적으로 알 수 없어** 안전한 쪽(위반)으로
 *     센다. 반대로 자식 대상 variant(`[&>div]:z-10`)는 그 요소가 아니라 자식에 적용되므로
 *     **위양성**이 될 수 있다(저장소 실사용 0건 — 실측).
 *   · `<body>`·`<html>` 은 훑지 않는다. 모달 스크롤 락이 `body` 에 거는 `overflow-hidden` 은
 *     이 도구로 보이지 않는다.
 *   · `overflow-hidden`이 **실제로 잘라내는지**는 기하(높이 여유)에 달렸다 — 이 도구는
 *     "잘릴 수 있는 상태인가"만 말한다. 실제 잘림은 라이브 측정의 몫이다.
 */

/**
 * variant 접두사와 `!` 중요 표시를 허용하는 앞머리.
 *
 * ★여기가 실제로 뚫렸던 자리다 — 종전 가드의 접두사는 `[a-z0-9-]+:` 뿐이라
 *   `@4xl:` · `group-hover/sensor:` · `[&>div]:` 같은 **내가 안 떠올린 표기**를 통째로 놓쳤다
 *   (저장소에 `@4xl:sticky` 실재). "아는 형태만 막는 가드"는 모르는 형태로 관통된다.
 */
const PREFIX = String.raw`(?:^|\s)!?(?:(?:[@a-z0-9_-]+(?:\/[a-z0-9_-]+)?(?:-?\[[^\]]*\])?|\[[^\]]*\]):)*!?-?`;

/**
 * 토큰 끝. v4의 **후행 `!`**(`opacity-40!`)까지 받는다 — v3는 선행, v4는 후행이다.
 * ★이 PR의 주제가 "v3 표기만 알고 있었다"인데 정작 v3식 `!`만 처리하고 있었다(적대검증 지적).
 */
const END = String.raw`!?(?=\s|$)`;

/**
 * 유틸의 **값** 부분. 임의값 `[...]`·v4 CSS변수 단축 `(...)`·일반 값을 모두 받는다.
 * ★`(`·`)`를 빼먹어 `blur-[var(--glass-blur)]`·`opacity-[var(--x)]`가 통째로 미탐이었다
 *   (적대검증이 저장소 실물 3건을 짚었다 — `SatongMapShell.tsx` 의 유리효과 레이어).
 *   같은 파일 안에서 `scale-[...]`만 임의값 분기를 갖고 있어 규칙이 서로 달랐다.
 */
const VAL = String.raw`(?:\[[^\]]*\]|\([^)]*\)|[a-z0-9%./-]+)`;

function util(body: string): RegExp {
  return new RegExp(`${PREFIX}(?:${body})${END}`);
}

/** `absolute|relative|sticky|fixed` — z 유틸과 **함께** 있어야 층 상자를 만든다. */
export const POSITIONED_UTIL = util(String.raw`absolute|relative|sticky|fixed`);

/** `sticky`·`fixed` 는 z 가 없어도 그 자체로 층 상자를 만든다(CSS 위치 명세). */
const SELF_POSITIONED_UTIL = util(String.raw`sticky|fixed`);

/** `z-10`·`z-[650]`·`-z-1`. */
export const Z_UTIL = util(String.raw`z-(?:\[\d+\]|\d+)`);

/**
 * 값 하나만으로 층 상자를 만드는 유틸(Tailwind v4 표기).
 *
 * ★제외한 것들(= 위양성 방지, 규율 A-6): CSS 명세상 `none`/항등값은 층 상자를 만들지 않는다.
 *   `transform-none`·`blur-none`·`backdrop-blur-none`·`filter-none`·`mask-none`·
 *   `drop-shadow-none`·`mix-blend-normal`·`opacity-100`·`will-change-auto`.
 *   ※ 반대로 `grayscale-0`·`brightness-100`·`rotate-0`·`scale-100` 같은 **항등값은 제외하지 않는다** —
 *     `filter: grayscale(0%)`·`rotate: 0deg`는 `none`이 아니므로 명세상 층 상자를 만든다.
 *
 * ★★`transform`·`filter`·`backdrop-filter` **맨몸 표기는 여기 없다.** v3에서는 층 상자를
 *   만들었지만 v4는 이들을 **빈 변수 합성**으로 내보내므로(저장소 tailwind 4.2.1 로 직접 컴파일해
 *   확인: `transform: var(--tw-rotate-x,) var(--tw-rotate-y,) …`) 값이 전부 비면 선언이 무효가 되어
 *   `none`으로 계산된다 → 층 상자 없음. 종전 가드는 **바로 이 세 토큰만** 찾고 있었다 —
 *   즉 v3 토큰을 찾은 게 문제이기 전에 **v4에서는 그 셋이 애초에 위반이 아니었다.**
 */
export const STACKING_UTIL = util(
  [
    // isolation
    String.raw`isolate`,
    // transform 계열 — 개별 속성(scale/rotate/translate)도 `none`이 아니면 층 상자를 만든다
    String.raw`transform-(?:gpu|3d|\[[^\]]*\])`,
    String.raw`(?:scale|rotate|translate|skew)(?:-[xyz])?-${VAL}`,
    // ※ `perspective-origin-*` 은 뺐다 — 원점만 옮기는 것이라 명세상 층 상자를 만들지 않는다.
    String.raw`perspective-${VAL}`,
    // filter 계열 — `filter: <fn>`은 none이 아니면 전부 층 상자
    String.raw`(?:backdrop-)?blur(?:-${VAL})?`,
    String.raw`(?:backdrop-)?(?:brightness|contrast|saturate|hue-rotate|opacity)-${VAL}`,
    String.raw`(?:backdrop-)?drop-shadow(?:-${VAL})?`,
    String.raw`(?:backdrop-)?(?:grayscale|invert|sepia)(?:-${VAL})?`,
    String.raw`(?:backdrop-)?filter-\[[^\]]*\]`,
    // 합성·격리
    String.raw`mix-blend-[a-z-]+`,
    String.raw`will-change-[a-z-[\]]+`,
    String.raw`contain-(?:layout|paint|content|strict)`,
    // ※ 마스크는 **애매**하다: 명세·MDN 은 `mask`(≠none)를 층 상자 생성으로 적지만
    //   Chrome 실측은 아니라고 나온다. 안전한 쪽(위반)으로 두되 이 불일치를 남긴다.
    //   `mask-type-*`(SVG 마스크 종류)는 마스크를 거는 게 아니므로 아래 면제에 둔다.
    String.raw`mask-${VAL}`,
  ].join("|"),
);

/** 층 상자를 만들지 **않는** 항등·해제 표기(위 정규식에 걸려도 무죄). */
const STACKING_EXEMPT = util(
  [
    String.raw`transform-none`,
    String.raw`(?:backdrop-)?blur-none`,
    String.raw`(?:backdrop-)?filter-none`,
    String.raw`drop-shadow-none`,
    String.raw`mask-none`,
    String.raw`mask-type-[a-z]+`,
    // `perspective-origin-*` 는 원점만 옮긴다 — 값 패턴이 `-` 를 포함해 위 규칙에 걸리므로 여기서 면제.
    String.raw`perspective-origin-[a-z0-9./-]+`,
    String.raw`perspective-none`,
    String.raw`mix-blend-normal`,
    String.raw`will-change-auto`,
    // opacity-100 = 불투명 = 층 상자 없음. (opacity-99 이하는 만든다)
    String.raw`(?:backdrop-)?opacity-(?:100|\[1\]|\[100%\])`,
  ].join("|"),
);

/**
 * 자손을 **잘라내는** 유틸.
 *
 * ★`overflow-*` 만 보면 안 된다 — `truncate`(= `overflow:hidden`+ellipsis)와 `line-clamp-N`
 *   (= `overflow:hidden`)도 **클래스 토큰인데** 종전엔 미탐이었다.
 *   실측(2026-08-12 · className 토큰): `truncate` **112** · `line-clamp-N` **9**.
 */
export const CLIPPING_UTIL = util(
  String.raw`overflow(?:-[xy])?-(?:hidden|clip|auto|scroll)|truncate|line-clamp-\d+`,
);

/** 클래스 문자열이 **자체로** 스태킹 컨텍스트를 만드는가. */
export function createsStackingContext(className: string): boolean {
  const cls = String(className ?? "");
  if (!cls) return false;
  if (POSITIONED_UTIL.test(cls) && Z_UTIL.test(cls)) return true;
  // `sticky`·`fixed` 는 z 가 없어도 그 자체로 층 상자다(`absolute`·`relative` 는 아니다).
  if (SELF_POSITIONED_UTIL.test(cls)) return true;
  if (!STACKING_UTIL.test(cls)) return false;
  // 항등·해제 표기만 있는 경우를 걸러낸다 — 예: `transform-none` 하나뿐이면 무죄.
  return cls
    .split(/\s+/)
    .filter(Boolean)
    .some((token) => STACKING_UTIL.test(token) && !STACKING_EXEMPT.test(token));
}

/** 클래스 문자열이 자손을 잘라내는가(`overflow-*`·`truncate`·`line-clamp-N`). */
export function clipsDescendants(className: string): boolean {
  return CLIPPING_UTIL.test(String(className ?? ""));
}

/**
 * 위반을 만든 **토큰만** 골라낸다 — 진단 메시지가 "무엇을 지우면 되는지"를 가리키게.
 *
 * ★왜 필요한가: 종전 진단은 클래스를 앞 90자로 잘라 보여줬는데, 이 저장소에서 실제로 인용하던
 *   `SiteInitiator.tsx:140`(길이 117)은 범인 `backdrop-blur-3xl` 이 **맨 뒤**라 잘려 나갔다.
 *   "무엇을 고쳐야 하는지까지 말하게 한다"고 적어 둔 바로 그 자리가 성립하지 않았다.
 */
export function culpritTokens(className: string, kind: "stacking" | "clipping"): string[] {
  const tokens = String(className ?? "").split(/\s+/).filter(Boolean);
  if (kind === "clipping") return tokens.filter((t) => CLIPPING_UTIL.test(t));
  const positioned = tokens.filter((t) => POSITIONED_UTIL.test(t));
  const zs = tokens.filter((t) => Z_UTIL.test(t));
  const self = tokens.filter((t) => SELF_POSITIONED_UTIL.test(t));
  const own = tokens.filter((t) => STACKING_UTIL.test(t) && !STACKING_EXEMPT.test(t));
  if (own.length || self.length) return [...new Set([...self, ...own])];
  return positioned.length && zs.length ? [...positioned, ...zs] : [];
}

export type LayerTrap = {
  /** 위반한 조상 요소 자체(호출자가 그 안의 기하 전제를 다시 볼 수 있게). */
  element: Element;
  /** `list.parentElement`를 0으로 세는 조상 깊이. */
  depth: number;
  /** 위반 클래스(진단 메시지용, 앞 90자). */
  className: string;
  /** 위반을 만든 토큰만 — 잘림 없이 항상 보인다. */
  culprits: string[];
  /** 왜 위반인가. */
  kind: "stacking" | "clipping";
};

export type AncestorTrapScan = {
  /** 훑은 조상 수 — **0이면 검사가 공허하다**(호출자가 반드시 하한을 단언할 것). */
  depth: number;
  traps: LayerTrap[];
};

/**
 * `el`의 조상을 `document.body`까지 훑어 층위 계약을 무력화하는 조상을 모은다.
 *
 * @param el 층위 값을 건 요소(팝오버·전체화면 오버레이 등)
 * @param opts.kinds 무엇을 위반으로 볼지. 기본은 스태킹만 — 클리핑은 기하에 따라
 *   무해할 수 있어 호출자가 명시적으로 켠다(위양성 방지).
 * @param opts.skipSelf 기본 true — `el` 자신은 검사하지 않는다(자기 z는 자기를 안 가둔다).
 */
export function scanAncestorTraps(
  el: Element,
  opts: { kinds?: Array<"stacking" | "clipping">; skipSelf?: boolean } = {},
): AncestorTrapScan {
  const kinds = opts.kinds ?? ["stacking"];
  const traps: LayerTrap[] = [];
  let node: Element | null = opts.skipSelf === false ? el : el.parentElement;
  let depth = 0;

  // ★상한을 두는 이유(변이 검증이 알려줬다): 이 순회는 **동기 루프**라 전진이 멈추면
  //   테스트 러너가 통째로 멈춘다 — vitest 의 `testTimeout` 은 동기 루프를 끊지 못한다.
  //   실제로 `node = node.parentElement` 를 지운 변이가 러너를 무한정 붙잡아
  //   변이 검증 실행 전체가 50분 타임아웃으로 죽었다(생존/사망 판정 자체가 불가능했다).
  //   상한이 있으면 같은 변이가 **멈춤 대신 실패**로 드러난다. 실제 DOM 깊이는 10 안팎이다.
  //   ★상한에 닿으면 **조용히 부분 결과를 돌려주지 않고 던진다** — 조용한 절단은
  //   "위반 0"이라는 거짓 초록을 만든다(적대검증 지적 L3).
  const MAX_DEPTH = 200;

  while (node && node !== node.ownerDocument?.body) {
    if (depth >= MAX_DEPTH) {
      throw new Error(
        `scanAncestorTraps: 조상 ${MAX_DEPTH}단을 넘었다 — 순회가 전진하지 않거나 DOM 이 비정상이다. ` +
          `부분 결과를 "위반 없음"으로 돌려주지 않기 위해 중단한다.`,
      );
    }
    // ★`className` 대신 속성으로 읽는다 — SVG 요소의 `className` 은 문자열이 아니라
    //   `SVGAnimatedString` 이라 `String(...)` 이 "[object SVGAnimatedString]" 이 된다(미탐).
    const cls = node.getAttribute("class") ?? "";
    if (kinds.includes("stacking") && createsStackingContext(cls)) {
      traps.push({
        element: node,
        depth,
        className: cls.slice(0, 90),
        culprits: culpritTokens(cls, "stacking"),
        kind: "stacking",
      });
    }
    if (kinds.includes("clipping") && clipsDescendants(cls)) {
      traps.push({
        element: node,
        depth,
        className: cls.slice(0, 90),
        culprits: culpritTokens(cls, "clipping"),
        kind: "clipping",
      });
    }
    node = node.parentElement;
    depth += 1;
  }

  return { depth, traps };
}

/** 진단 메시지 — 실패 출력이 "무엇을 고쳐야 하는지"까지 말하게 한다. */
export function describeTraps(traps: LayerTrap[]): string {
  return traps
    .map(
      (t) =>
        `  · [조상 ${t.depth}] ${t.kind === "stacking" ? "층 상자 생성" : "잘라냄"}` +
        ` — 범인 토큰: ${t.culprits.join(" ") || "(판정 불일치)"}` +
        `\n      클래스: ${t.className}`,
    )
    .join("\n");
}
